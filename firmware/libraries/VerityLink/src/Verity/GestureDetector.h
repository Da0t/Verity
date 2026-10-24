#pragma once
// Double head gestures from pitch and yaw. Plain C++, no Arduino dependency.
// Feed pitch (positive = DOWN) and integrated yaw (positive = LEFT) in degrees.
// A single gesture does nothing: the same one must complete twice within doubleMs.
// Thresholds are untested starting points: tune per wearer with VERITY_IMU_DEBUG.
#include <initializer_list>
#include "NodDetector.h"
#include "Protocol.h"

namespace Verity {
struct GestureDetector {
  NodDetector nod, left, right; // NodDetector is a generic out-and-back excursion detector
  uint32_t doubleMs = 900;  // second gesture must finish this soon after the first
  uint32_t lockoutMs = 1200; // after a double, ignore everything (swallows a third)

  uint8_t last = NoGesture;
  uint32_t lastAt = 0, firedAt = 0;
  bool fired = false;

  GestureDetector() {
    nod.cooldownMs = 0; // timing is owned by the double logic below
    for (NodDetector* turn : {&left, &right}) {
      turn->downDeg = 25; turn->returnDeg = 10; turn->maxDownMs = 1000; turn->cooldownMs = 0;
    }
  }

  // Returns a Gesture exactly once per completed double, else NoGesture.
  uint8_t update(float pitch, float yaw, uint32_t now) {
    // Update every detector every sample: their neutral tracking must keep running.
    const bool n = nod.update(pitch, now), l = left.update(yaw, now), r = right.update(-yaw, now);
    const uint8_t g = n ? DoubleNod : l ? DoubleLeft : r ? DoubleRight : NoGesture;
    if (g == NoGesture || (fired && now - firedAt < lockoutMs)) return NoGesture;
    if (g == last && now - lastAt <= doubleMs) {
      last = NoGesture; fired = true; firedAt = now; return g;
    }
    last = g; lastAt = now;
    return NoGesture;
  }

  bool settled(uint32_t now) const { return nod.settled(now) && !left.down && !right.down; }
};
}
