#pragma once
#include <stdint.h>
#include <math.h>

// Pitch degrees relative to a calibrated neutral posture. Pure, host-testable logic.
class NodDetector {
 public:
  float downDegrees = 18, neutralDegrees = 6;
  uint32_t minDuration = 180, maxDuration = 1500, cooldown = 1800;
  bool update(float pitch, uint32_t now) {
    if (!isfinite(pitch)) { active = false; return false; }
    if (cooling && uint32_t(now-lastEvent) < cooldown) return false;
    cooling = false;
    if (!armed) {
      if (fabsf(pitch) < neutralDegrees) armed = true;
      return false;
    }
    if (!active) {
      if (pitch >= downDegrees) { active = true; started = now; }
      return false;
    }
    uint32_t elapsed = now-started;
    if (elapsed > maxDuration || pitch < -downDegrees) {
      active = false; armed = false; return false;
    }
    if (fabsf(pitch) < neutralDegrees) {
      active = false; armed = false;
      if (elapsed < minDuration) return false;
      cooling = true; lastEvent = now; return true;
    }
    return false;
  }
 private:
  bool active = false, armed = false, cooling = false;
  uint32_t started = 0, lastEvent = 0;
};
