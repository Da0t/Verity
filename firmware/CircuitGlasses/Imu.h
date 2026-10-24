#pragma once
#include "Config.h"
#include <VerityMotion.h>
namespace Imu {
static Verity::MotionSensor motion;
static bool begin() {
  Verity::MotionConfig config; config.sda=VERITY_IMU_SDA; config.scl=VERITY_IMU_SCL;
  config.direction=VERITY_PITCH_DIRECTION; return motion.begin(config);
}
static bool poll() { return motion.poll(millis()); }
static bool settled() { return (motion.flags(millis()) & Verity::Settled)!=0; }
}
