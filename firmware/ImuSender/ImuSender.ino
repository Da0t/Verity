#include <Arduino.h>
#include "Config.h"
#include <VerityMotion.h>
#if VERITY_ENABLE_CAMERA_LINK
#include <esp_system.h>
#include <VerityEspNow.h>
#endif
#if !CONFIG_IDF_TARGET_ESP32
#error "Reference target is original ESP32-WROOM. Confirm carrier pinout before flashing."
#endif
Verity::MotionSensor motion;
#if VERITY_ENABLE_CAMERA_LINK
Verity::Radio radio;
Verity::SenderLink* senderLink;
#endif
void setup() {
  Serial.begin(115200);
#if VERITY_ENABLE_CAMERA_LINK
  senderLink=new Verity::SenderLink(esp_random()|1u,esp_random()|1u);
  radio.begin(VERITY_CAMERA_MAC,VERITY_ESPNOW_CHANNEL);
#else
  Serial.println("Standalone IMU mode; camera link disabled. Gestures: 1=double nod, 2=double left, 3=double right.");
#endif
  Verity::MotionConfig config;
  config.sda=VERITY_IMU_SDA; config.scl=VERITY_IMU_SCL; config.address=VERITY_IMU_ADDRESS;
  config.axis=VERITY_PITCH_AXIS; config.direction=VERITY_PITCH_DIRECTION; config.yawDirection=VERITY_YAW_DIRECTION; config.debug=VERITY_IMU_DEBUG;
  motion.begin(config);
}
void loop() {
#if VERITY_ENABLE_CAMERA_LINK
  Verity::Received received;
  while(radio.receive(received)) senderLink->receive(received.packet,received.at,millis());
#endif
  uint32_t now=millis();
  if(uint8_t gesture=motion.poll(now)) {
#if VERITY_ENABLE_CAMERA_LINK
    senderLink->nod(now,motion.flags(now),gesture);
#endif
    Serial.printf("Local gesture %u\n",gesture);
  }
#if VERITY_ENABLE_CAMERA_LINK
  Verity::Packet packet;
  if(radio.ready() && senderLink->poll(now,motion.flags(now),packet)) radio.send(packet);
#endif
  static uint32_t logged=0;
  if(Verity::elapsed(now,logged)>=5000) {
    logged=now;
#if VERITY_ENABLE_CAMERA_LINK
    Serial.printf("senderLink=%d motion=%u acknowledged=%lu dropped=%lu queueDrops=%lu txBusy=%d txErrors=%lu\n",senderLink->active(),motion.flags(now),
      (unsigned long)senderLink->acknowledged(),(unsigned long)senderLink->dropped(),(unsigned long)radio.queueDrops(),radio.busy(),(unsigned long)radio.sendErrors());
#else
    Serial.printf("Standalone IMU motion=%u\n",motion.flags(now));
#endif
  }
  delay(2);
}
