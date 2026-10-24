#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <esp_idf_version.h>
#include <atomic>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include "VerityLink.h"
namespace Verity {
struct Received { Packet packet; uint32_t at; };
class Radio {
 public:
  bool begin(const uint8_t* peer, uint8_t channel) {
    WiFi.mode(WIFI_STA);
    Serial.printf("ESP-NOW STA MAC: %s; channel %u\n", WiFi.macAddress().c_str(), channel);
    uint8_t own[6]; WiFi.macAddress(own);
    bool nonzero=false; for (int i=0;i<6;++i) nonzero |= peer[i]!=0;
    if (!nonzero || (peer[0]&1) || !memcmp(own,peer,6) || channel<1 || channel>11) {
      Serial.println("Configure a unique unicast peer STA MAC and channel 1..11 in Config.h."); return false;
    }
    memcpy(peer_,peer,6); queue_=xQueueCreate(8,sizeof(Received));
    if (!queue_ || esp_wifi_set_channel(channel,WIFI_SECOND_CHAN_NONE)!=ESP_OK || esp_now_init()!=ESP_OK) return false;
    instance_=this;
    esp_now_peer_info_t info={}; memcpy(info.peer_addr,peer_,6);
    info.channel=channel; info.ifidx=WIFI_IF_STA; info.encrypt=false;
    if (esp_now_add_peer(&info)!=ESP_OK) return false;
    if (esp_now_register_recv_cb(onReceive)!=ESP_OK || esp_now_register_send_cb(onSent)!=ESP_OK) return false;
    ready_=true; return true;
  }
  bool ready() const { return ready_; }
  bool receive(Received& r) { return queue_ && xQueueReceive(queue_,&r,0)==pdTRUE; }
  bool send(const Packet& p) {
    uint8_t data[PACKET_SIZE];
    if (!ready_ || !encode(p,data,sizeof(data)) || busy_.exchange(true)) return false;
    if (esp_now_send(peer_,data,sizeof(data))!=ESP_OK) { busy_=false; ++sendErrors_; return false; }
    return true;
  }
  bool busy() const { return busy_.load(); }
  uint32_t sendErrors() const { return sendErrors_.load(); }
  uint32_t queueDrops() const { return drops_.load(); }
 private:
  inline static Radio* instance_=nullptr;
  QueueHandle_t queue_=nullptr; uint8_t peer_[6]={}; bool ready_=false;
  std::atomic<bool> busy_{false}; std::atomic<uint32_t> drops_{0},sendErrors_{0};
  static void onReceive(const esp_now_recv_info_t* info,const uint8_t* data,int len) {
    auto* self=instance_; if (!self || !info || len!=int(PACKET_SIZE) || !matchesPeer(self->peer_,info->src_addr)) return;
    Received r; r.at=millis();
    if (!decode(data,len,r.packet)) return;
    if (xQueueSend(self->queue_,&r,0)!=pdTRUE) ++self->drops_;
  }
#if ESP_IDF_VERSION >= ESP_IDF_VERSION_VAL(5,5,0)
  static void onSent(const esp_now_send_info_t*,esp_now_send_status_t) {
#else
  static void onSent(const uint8_t*,esp_now_send_status_t) {
#endif
    if (instance_) instance_->busy_=false; // MAC completion only; application ACK is separate.
  }
};
}
