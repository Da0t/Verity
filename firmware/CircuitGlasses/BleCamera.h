#pragma once
// Arduino-ESP32 + NimBLE-Arduino 2.x. Call begin() AFTER esp_camera_init().
// Camera must produce JPEG. Call poll() frequently from Arduino loop().
// Optional IMU: call notifyNod(gesture) per detected head gesture; pass poll(settled) so a
// capture waits (bounded) for head motion to stop.
#include <Arduino.h>
#include <atomic>
#include <NimBLEDevice.h>
#include <esp_camera.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

namespace BleCamera {
static const char* SERVICE = "369f0001-7d5c-4f30-a16b-8c578d930001";
static const char* COMMAND = "369f0002-7d5c-4f30-a16b-8c578d930001";
static const char* STATUS = "369f0003-7d5c-4f30-a16b-8c578d930001";
static const char* DATA = "369f0004-7d5c-4f30-a16b-8c578d930001";
static const char* NOD = "369f0005-7d5c-4f30-a16b-8c578d930001";
static const uint32_t SETTLE_WAIT_MS = 1500;
static SemaphoreHandle_t mutex, nodMutex;
static uint16_t nodConnection=BLE_HS_CONN_HANDLE_NONE;
static NimBLECharacteristic *statusChar, *dataChar, *nodChar;
static camera_fb_t* frame = nullptr;
static uint32_t requestId = 0, touched = 0, nodSeq = 0;
static bool pending = false;
static std::atomic<bool> nodSubscribed{false};
static std::atomic<uint32_t> connectionEpoch{0};
static bool canNotifyNod() { return nodSubscribed.load(); }
static uint32_t epoch() { return connectionEpoch.load(); }
static uint8_t state = 0; // idle=0, capturing=1, ready=2, error=3

static uint32_t read32(const uint8_t* p) {
  return uint32_t(p[0]) | uint32_t(p[1])<<8 | uint32_t(p[2])<<16 | uint32_t(p[3])<<24;
}
static void put32(uint8_t* p, uint32_t n) {
  for (int i=0; i<4; ++i) p[i] = uint8_t(n >> (8*i));
}
static uint32_t crc32(const uint8_t* p, size_t n) {
  uint32_t c = 0xffffffff;
  while (n--) {
    c ^= *p++;
    for (int i=0; i<8; ++i) c = (c>>1) ^ (0xedb88320u & (0u-(c&1)));
  }
  return ~c;
}
static void publish(uint32_t crc = 0) {
  uint8_t b[13]; b[0] = state;
  put32(b+1, requestId); put32(b+5, frame ? frame->len : 0); put32(b+9, crc);
  statusChar->setValue(b, sizeof(b));
}
class Commands : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& peer) override {
    auto value = c->getValue();
    const auto* p = reinterpret_cast<const uint8_t*>(value.data());
    xSemaphoreTake(mutex, portMAX_DELAY);
    if (value.size() == 5 && p[0] == 1 && state != 1) {
      if (frame) { esp_camera_fb_return(frame); frame = nullptr; }
      dataChar->setValue("");
      requestId = read32(p+1); state = 1; pending = true; publish();
      touched = millis();
    } else if (value.size() == 9 && p[0] == 2 && state == 2 &&
               read32(p+1) == requestId && frame) {
      uint32_t offset = read32(p+5);
      if (offset < frame->len) {
        uint8_t b[512]; put32(b, offset);
        // Each read fits a SINGLE ATT response, including at the minimum MTU.
        size_t count = peer.getMTU() > 5 ? peer.getMTU()-5 : 18;
        count = min(count, sizeof(b)-4);
        count = min(count, static_cast<size_t>(frame->len-offset));
        memcpy(b+4, frame->buf+offset, count);
        dataChar->setValue(b, count+4); touched = millis();
      } else dataChar->setValue("");
    }
    xSemaphoreGive(mutex);
  }
};
class Connections : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* s, NimBLEConnInfo& peer) override {
    if (s->getConnectedCount() > 1) s->disconnect(peer.getConnHandle());
  }
  void onDisconnect(NimBLEServer*, NimBLEConnInfo& peer, int) override {
    xSemaphoreTake(nodMutex, portMAX_DELAY);
    if (nodConnection==peer.getConnHandle()) {
      nodSubscribed=false; nodConnection=BLE_HS_CONN_HANDLE_NONE; ++connectionEpoch;
    }
    xSemaphoreGive(nodMutex);
    NimBLEDevice::startAdvertising();
  }
};
class NodSubscriptions : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic*, NimBLEConnInfo& peer, uint16_t value) override {
    xSemaphoreTake(nodMutex, portMAX_DELAY);
    nodSubscribed=(value & 1)!=0; nodConnection=peer.getConnHandle(); ++connectionEpoch;
    xSemaphoreGive(nodMutex);
  }
};
static NodSubscriptions subscriptions;
static Commands commands;
static Connections connections;
static void begin() {
  mutex = xSemaphoreCreateMutex(); nodMutex=xSemaphoreCreateMutex();
  configASSERT(mutex && nodMutex);
  NimBLEDevice::init("CircuitGlasses"); NimBLEDevice::setMTU(247);
  auto* server = NimBLEDevice::createServer(); server->setCallbacks(&connections);
  auto* service = server->createService(SERVICE);
  auto* command = service->createCharacteristic(COMMAND, NIMBLE_PROPERTY::WRITE);
  command->setCallbacks(&commands);
  statusChar = service->createCharacteristic(STATUS, NIMBLE_PROPERTY::READ);
  dataChar = service->createCharacteristic(DATA, NIMBLE_PROPERTY::READ, 512);
  nodChar = service->createCharacteristic(NOD, NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
  nodChar->setCallbacks(&subscriptions);
  publish(); service->start();
  auto* ad = NimBLEDevice::getAdvertising();
  ad->addServiceUUID(SERVICE); ad->setName("CircuitGlasses");
  ad->enableScanResponse(true); ad->start();
}
// Notify subscribers of one head gesture: payload is seq:u32 little-endian,
// then gesture:u8 (Verity::Gesture: 1=double nod, 2=double left, 3=double right).
static bool notifyNod(uint8_t gesture, uint32_t expectedEpoch) {
  xSemaphoreTake(nodMutex, portMAX_DELAY);
  bool sent=false;
  if (canNotifyNod() && epoch()==expectedEpoch) {
    uint8_t b[5]; put32(b, ++nodSeq); b[4]=gesture;
    nodChar->setValue(b, sizeof(b));
    sent=nodChar->notify(b, sizeof(b), nodConnection);
  }
  xSemaphoreGive(nodMutex);
  return sent;
}
static bool notifyNod(uint8_t gesture) { return notifyNod(gesture, epoch()); }
static void poll(bool settled = true) {
  xSemaphoreTake(mutex, portMAX_DELAY);
  // Wait for the head to settle so the photo is not motion-blurred, but not forever.
  bool capture = pending && (settled || uint32_t(millis()-touched) > SETTLE_WAIT_MS);
  if (capture) {
    pending = false;
    if (!settled) Serial.println("Capture timeout: proceeding without settled IMU confirmation.");
  }
  xSemaphoreGive(mutex);
  if (capture) {
    // Discard a buffered frame so the check uses a newly captured view.
    auto* old = esp_camera_fb_get();
    if (old) esp_camera_fb_return(old);
    auto* fresh = esp_camera_fb_get();
    uint32_t crc = 0;
    if (fresh && fresh->format == PIXFORMAT_JPEG && fresh->len <= 1024*1024)
      crc = crc32(fresh->buf, fresh->len);
    else { if (fresh) esp_camera_fb_return(fresh); fresh = nullptr; }
    xSemaphoreTake(mutex, portMAX_DELAY);
    frame = fresh; state = frame ? 2 : 3; touched = millis(); publish(crc);
    xSemaphoreGive(mutex);
  }
  xSemaphoreTake(mutex, portMAX_DELAY);
  if (frame && uint32_t(millis()-touched) > 90000) {
    esp_camera_fb_return(frame); frame = nullptr; state = 0;
    dataChar->setValue(""); publish();
  }
  xSemaphoreGive(mutex);
}
} // namespace BleCamera
