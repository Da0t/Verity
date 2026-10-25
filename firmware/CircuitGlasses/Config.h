#pragma once
#ifndef VERITY_USE_ESPNOW_IMU
#define VERITY_USE_ESPNOW_IMU 1
#endif
#define VERITY_ESPNOW_CHANNEL 1
static const uint8_t VERITY_SENSOR_MAC[6]={0x20,0x50,0x0D,0x1A,0x5C,0x8C}; // sensor STA MAC
// Only used with VERITY_USE_ESPNOW_IMU=0; original direct MPU wiring, no SD card.
#ifndef VERITY_IMU_SDA
#define VERITY_IMU_SDA 13
#endif
#ifndef VERITY_IMU_SCL
#define VERITY_IMU_SCL 14
#endif
#ifndef VERITY_YAW_DIRECTION
#define VERITY_YAW_DIRECTION 1 // -1 if double-left and double-right are swapped
#endif
#ifndef VERITY_PITCH_DIRECTION
#define VERITY_PITCH_DIRECTION 1
#endif
