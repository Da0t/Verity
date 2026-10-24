#pragma once
#include "Config.h"
#include <VerityMotion.h>
namespace Imu {
static Verity::MotionSensor motion;
static bool begin() {
  Verity::MotionConfig config; config.sda=VERITY_IMU_SDA; config.scl=VERITY_IMU_SCL;
  config.direction=VERITY_PITCH_DIRECTION; config.yawDirection=VERITY_YAW_DIRECTION;
  return motion.begin(config);
}
static uint8_t poll() { return motion.poll(millis()); } // Verity::Gesture
static bool settled() { return (motion.flags(millis()) & Verity::Settled)!=0; }
}
