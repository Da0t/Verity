#pragma once
#include "NodDetector.h"

// Enable only after confirming your sensor and the available pins. No SD card use.
#ifndef VERITY_ENABLE_MPU6050
#define VERITY_ENABLE_MPU6050 0
#endif
#ifndef VERITY_IMU_SDA
#define VERITY_IMU_SDA 13
#endif
#ifndef VERITY_IMU_SCL
#define VERITY_IMU_SCL 14
#endif
#ifndef VERITY_PITCH_DIRECTION
#define VERITY_PITCH_DIRECTION 1
#endif

#if VERITY_ENABLE_MPU6050
#include <Wire.h>
namespace Imu {
static NodDetector detector;
static uint8_t address = 0x68;
static uint32_t last = 0;
static float filtered = 0, neutral = 0;
static uint16_t calibrated = 0;
static bool ready = false;
static bool read(uint8_t reg, uint8_t* out, uint8_t count) {
  Wire.beginTransmission(address); Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(address, count) != count) return false;
  for (uint8_t i=0; i<count; ++i) out[i] = Wire.read();
  return true;
}
static bool write(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address); Wire.write(reg); Wire.write(value);
  return Wire.endTransmission() == 0;
}
static int16_t signed16(const uint8_t* p) { return int16_t(uint16_t(p[0])<<8 | p[1]); }
static bool begin() {
  Wire.begin(VERITY_IMU_SDA, VERITY_IMU_SCL, 100000); Wire.setTimeOut(20);
  uint8_t who = 0;
  for (uint8_t candidate : {uint8_t(0x68), uint8_t(0x69)}) {
    address = candidate;
    if (read(0x75, &who, 1) && who == 0x68) { ready = true; break; }
  }
  if (!ready) { Serial.println("MPU-6050 not found; IMU activation unavailable."); return false; }
  // Wake; +/-2g accelerometer, +/-250 deg/s gyro; ~44Hz low-pass filter.
  ready = write(0x6b, 0x00) && write(0x1c, 0x00) && write(0x1b, 0x00) && write(0x1a, 0x03);
  Serial.println("Keep glasses still for two seconds to calibrate nod activation.");
  return ready;
}
static bool poll() {
  uint32_t now = millis();
  if (!ready || uint32_t(now-last) < 20) return false;
  last = now;
  uint8_t raw[14];
  if (!read(0x3b, raw, sizeof(raw))) { calibrated=0; return false; }
  float ax=signed16(raw)/16384.0f, ay=signed16(raw+2)/16384.0f, az=signed16(raw+4)/16384.0f;
  float gx=signed16(raw+8)/131.0f, gy=signed16(raw+10)/131.0f, gz=signed16(raw+12)/131.0f;
  float gravity = sqrtf(ax*ax+ay*ay+az*az);
  if (gravity < 0.75f || gravity > 1.25f) return false;
  float pitch = atan2f(-ax, sqrtf(ay*ay+az*az))*57.29578f*VERITY_PITCH_DIRECTION;
  if (calibrated < 100) {
    if (fabsf(gx)+fabsf(gy)+fabsf(gz) > 15) { calibrated=0; neutral=0; return false; }
    neutral += pitch; ++calibrated;
    if (calibrated == 100) { neutral /= 100; filtered=pitch; Serial.println("IMU calibrated; nod down and return to activate."); }
    return false;
  }
  filtered = 0.7f*filtered+0.3f*pitch;
  return detector.update(filtered-neutral, now);
}
}
#else
namespace Imu {
static bool begin() { Serial.println("IMU driver disabled. Configure Imu.h for real nod activation."); return false; }
static bool poll() { return false; }
}
#endif
