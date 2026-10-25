#pragma once
#ifndef VERITY_ENABLE_CAMERA_LINK
#define VERITY_ENABLE_CAMERA_LINK 0 // 1 restores the ESP-NOW camera bridge
#endif
// ESP32-WROOM carrier pinout and MPU breakout power requirements must be checked.
#define VERITY_IMU_SDA 21
#define VERITY_IMU_SCL 22
#define VERITY_IMU_ADDRESS 0 // 0 = probe 0x68 and 0x69
#define VERITY_PITCH_AXIS 2 // 0=X, 1=Y, 2=Z accelerometer component (Z confirmed on bench 2026-10-24)
#define VERITY_PITCH_DIRECTION 1 // change to -1 if downward pitch is negative
#define VERITY_YAW_DIRECTION 1 // change to -1 if double-left and double-right are swapped
#define VERITY_IMU_DEBUG 1
#define VERITY_ESPNOW_CHANNEL 1
static const uint8_t VERITY_CAMERA_MAC[6]={0xE0,0x8C,0xFE,0xB6,0x28,0xC4}; // camera STA MAC
