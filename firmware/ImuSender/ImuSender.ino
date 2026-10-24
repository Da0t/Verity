#include <Arduino.h>
#include <esp_system.h>
#include <VerityEspNow.h>
#include <VerityMotion.h>
#include "Config.h"
#if !CONFIG_IDF_TARGET_ESP32
#error "Reference target is original ESP32-WROOM. Confirm carrier pinout before flashing."
#endif
Verity::Radio radio;
Verity::MotionSensor motion;
Verity::SenderLink* senderLink;
void setup() {
  Serial.begin(115200);
  senderLink=new Verity::SenderLink(esp_random()|1u,esp_random()|1u);
  radio.begin(VERITY_CAMERA_MAC,VERITY_ESPNOW_CHANNEL);
  Verity::MotionConfig config;
  config.sda=VERITY_IMU_SDA; config.scl=VERITY_IMU_SCL; config.address=VERITY_IMU_ADDRESS;
  config.axis=VERITY_PITCH_AXIS; config.direction=VERITY_PITCH_DIRECTION; config.debug=VERITY_IMU_DEBUG;
  motion.begin(config);
}
void loop() {
  Verity::Received received;
  while(radio.receive(received)) senderLink->receive(received.packet,received.at,millis());
  uint32_t now=millis();
  if(motion.poll(now)) { senderLink->nod(now,motion.flags(now)); Serial.println("Local nod"); }
  Verity::Packet packet;
  if(radio.ready() && senderLink->poll(now,motion.flags(now),packet)) radio.send(packet);
  static uint32_t logged=0;
  if(Verity::elapsed(now,logged)>=5000) {
    logged=now; Serial.printf("senderLink=%d motion=%u acknowledged=%lu dropped=%lu queueDrops=%lu txBusy=%d txErrors=%lu\n",senderLink->active(),motion.flags(now),
      (unsigned long)senderLink->acknowledged(),(unsigned long)senderLink->dropped(),(unsigned long)radio.queueDrops(),radio.busy(),(unsigned long)radio.sendErrors());
  }
  delay(2);
}
