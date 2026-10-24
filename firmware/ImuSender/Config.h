#pragma once
// ESP32-WROOM carrier pinout and MPU breakout power requirements must be checked.
#define VERITY_IMU_SDA -1
#define VERITY_IMU_SCL -1
#define VERITY_IMU_ADDRESS 0 // 0 = probe 0x68 and 0x69
#define VERITY_PITCH_AXIS 0 // 0=X, 1=Y, 2=Z accelerometer component
#define VERITY_PITCH_DIRECTION 1 // change to -1 if downward pitch is negative
#define VERITY_IMU_DEBUG 0
#define VERITY_ESPNOW_CHANNEL 1
static const uint8_t VERITY_CAMERA_MAC[6]={0,0,0,0,0,0}; // camera STA MAC
