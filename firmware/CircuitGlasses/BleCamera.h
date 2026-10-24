#pragma once
// Arduino-ESP32 + NimBLE-Arduino 2.x. Call begin() AFTER esp_camera_init().
// Camera must produce JPEG. Call poll() frequently from Arduino loop().
#include <Arduino.h>
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
static NimBLECharacteristic* nodChar;
static uint32_t nodSequence = 0;
static SemaphoreHandle_t mutex;
static NimBLECharacteristic *statusChar, *dataChar;
static camera_fb_t* frame = nullptr;
static uint32_t requestId = 0, touched = 0;
static bool pending = false;
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
        count = min(count, frame->len-offset);
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
  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int) override {
    NimBLEDevice::startAdvertising();
  }
};
static Commands commands;
static Connections connections;
static void begin() {
  mutex = xSemaphoreCreateMutex();
  configASSERT(mutex);
  NimBLEDevice::init("CircuitGlasses"); NimBLEDevice::setMTU(247);
  auto* server = NimBLEDevice::createServer(); server->setCallbacks(&connections);
  auto* service = server->createService(SERVICE);
  auto* command = service->createCharacteristic(COMMAND, NIMBLE_PROPERTY::WRITE);
  command->setCallbacks(&commands);
  statusChar = service->createCharacteristic(STATUS, NIMBLE_PROPERTY::READ);
  dataChar = service->createCharacteristic(DATA, NIMBLE_PROPERTY::READ, 512);
  nodChar = service->createCharacteristic(NOD, NIMBLE_PROPERTY::NOTIFY);
  publish(); service->start();
  auto* ad = NimBLEDevice::getAdvertising();
  ad->addServiceUUID(SERVICE); ad->setName("CircuitGlasses");
  ad->enableScanResponse(true); ad->start();
}
static void notifyNod() {
  uint8_t packet[8]; put32(packet, ++nodSequence); put32(packet+4, millis());
  nodChar->setValue(packet, sizeof(packet)); nodChar->notify();
}
static void poll() {
  xSemaphoreTake(mutex, portMAX_DELAY);
  bool capture = pending; pending = false;
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
