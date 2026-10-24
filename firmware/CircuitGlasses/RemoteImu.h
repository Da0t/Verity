#pragma once
#include <esp_system.h>
#include <VerityEspNow.h>
namespace Imu {
static Verity::Radio radio;
static Verity::CameraLink* link;
static uint32_t epoch=0;
static bool begin() {
  link=new Verity::CameraLink(esp_random()|1u,esp_random()|1u);
  epoch=BleCamera::epoch();
  return radio.begin(VERITY_SENSOR_MAC,VERITY_ESPNOW_CHANNEL);
}
static bool settled() { return link && link->settled(millis()); }
static uint8_t poll() {
  if (!link) return false;
  if (epoch!=BleCamera::epoch()) { epoch=BleCamera::epoch(); link->invalidate(); }
  Verity::Received received;
  while(radio.receive(received)) {
    if (epoch!=BleCamera::epoch()) { epoch=BleCamera::epoch(); link->invalidate(); }
    auto action=link->receive(received.packet,received.at,millis(),BleCamera::canNotifyNod());
    if(action.nod) {
      if (!BleCamera::notifyNod(received.packet.gesture,epoch)) action.packet.code=Verity::Ack::Dropped;
      else Serial.println("Remote gesture forwarded to BLE");
    }
    if(action.reply) radio.send(action.packet);
  }
  link->tick(millis());
  static uint32_t logged=0;
  if(Verity::elapsed(millis(),logged)>=5000) {
    logged=millis(); Serial.printf("%s; BLE nod subscriber=%d queueDrops=%lu txBusy=%d txErrors=%lu\n",link->reason(logged),BleCamera::canNotifyNod(),(unsigned long)radio.queueDrops(),radio.busy(),(unsigned long)radio.sendErrors());
  }
  return 0; // Notification already handled once above, in the main loop.
}
}
