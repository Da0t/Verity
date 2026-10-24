#pragma once
#include <Arduino.h>
#include <Wire.h>
#include "VerityLink.h"
namespace Verity {
// yawDirection: flip to -1 if double-left and double-right come out swapped.
struct MotionConfig { int sda=-1,scl=-1; uint8_t address=0; int axis=0, direction=1, yawDirection=1; bool debug=false; };
class MotionSensor {
 public:
  bool begin(MotionConfig config) {
    cfg_=config;
    if (cfg_.sda<0 || cfg_.scl<0 || cfg_.sda==cfg_.scl || cfg_.axis<0 || cfg_.axis>2 ||
        abs(cfg_.direction)!=1 || abs(cfg_.yawDirection)!=1) {
      Serial.println("Configure confirmed MPU SDA/SCL pins, pitch axis and pitch/yaw direction."); return false;
    }
    Wire.begin(cfg_.sda,cfg_.scl,100000); Wire.setTimeOut(20);
    for (uint8_t candidate : {uint8_t(0x68),uint8_t(0x69)}) {
      if (cfg_.address && cfg_.address!=candidate) continue;
      address_=candidate; uint8_t who=0;
      if (read(0x75,&who,1) && who==0x68) { ready_=true; break; }
    }
    ready_=ready_ && write(0x6b,0) && write(0x1c,0) && write(0x1b,0) && write(0x1a,3);
    Serial.println(ready_ ? "MPU found. Hold still for two seconds to calibrate." : "MPU unavailable; check wiring/address then restart.");
    return ready_;
  }
  uint8_t flags(uint32_t now) const {
    if (!ready_ || !sample_ || elapsed(now,validAt_)>200) return 0;
    uint8_t f=SensorOk;
    if (count_>=100) { f|=Calibrated; if (gyroStill_ && gestures_.settled(now)) f|=Settled; }
    return f;
  }
  // Returns a Gesture (NoGesture when nothing completed).
  uint8_t poll(uint32_t now) {
    if (!ready_ || elapsed(now,last_)<20) return NoGesture;
    if (sample_ && elapsed(now,validAt_)>200) reset();
    const float dt=elapsed(now,last_)/1000.0f;
    last_=now; uint8_t raw[14];
    if (!read(0x3b,raw,14)) { reset(); return NoGesture; }
    float a[3]; for (int i=0;i<3;++i) a[i]=signed16(raw+2*i)/16384.0f;
    float g[3], gyro=0; for(int i=0;i<3;++i) { g[i]=signed16(raw+8+2*i)/131.0f; gyro+=fabsf(g[i]); }
    gyroStill_=gyro<=15;
    float gravity=sqrtf(a[0]*a[0]+a[1]*a[1]+a[2]*a[2]);
    if (gravity<0.75f || gravity>1.25f) { reset(); return NoGesture; }
    sample_=true; validAt_=now;
    float component=a[cfg_.axis];
    float pitch=atan2f(-component,sqrtf(fmaxf(0,gravity*gravity-component*component)))*57.29578f*cfg_.direction;
    // Rotation about gravity, whatever the mounting: positive = head turning LEFT.
    float yawRate=(g[0]*a[0]+g[1]*a[1]+g[2]*a[2])/gravity*cfg_.yawDirection;
    if (count_<100) {
      if (gyro>15) { reset(); return NoGesture; }
      neutral_+=pitch; yawBias_+=yawRate; ++count_;
      if (count_==100) {
        neutral_/=100; yawBias_/=100; filtered_=pitch; yaw_=0;
        gestures_.update(0,0,now); Serial.println("IMU calibrated.");
      }
      return NoGesture;
    }
    filtered_=0.7f*filtered_+0.3f*pitch;
    // Integrated gyro drifts; the detectors' slow neutral tracking absorbs it.
    yaw_+=(yawRate-yawBias_)*dt;
    uint8_t gesture=gestures_.update(filtered_-neutral_,yaw_,now);
    if (cfg_.debug && elapsed(now,debugAt_)>=100) { debugAt_=now; Serial.printf("pitch %.1f yaw %.1f flags %u\n",filtered_-neutral_,yaw_,flags(now)); }
    return gesture;
  }
 private:
  MotionConfig cfg_; GestureDetector gestures_; bool ready_=false,sample_=false,gyroStill_=false;
  uint8_t address_=0x68; uint16_t count_=0; uint32_t last_=0,validAt_=0,debugAt_=0;
  float neutral_=0,filtered_=0,yawBias_=0,yaw_=0;
  void reset() { count_=0; neutral_=0; yawBias_=0; yaw_=0; sample_=false; gestures_=GestureDetector{}; }
  static int16_t signed16(const uint8_t* p) { return int16_t(uint16_t(p[0])<<8|p[1]); }
  bool read(uint8_t reg,uint8_t* data,uint8_t size) {
    Wire.beginTransmission(address_); Wire.write(reg);
    if (Wire.endTransmission(false) || Wire.requestFrom(address_,size)!=size) return false;
    for(uint8_t i=0;i<size;++i) data[i]=Wire.read(); return true;
  }
  bool write(uint8_t reg,uint8_t value) { Wire.beginTransmission(address_); Wire.write(reg); Wire.write(value); return Wire.endTransmission()==0; }
};
}
