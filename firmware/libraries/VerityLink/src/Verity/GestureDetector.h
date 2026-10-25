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
  // Bench 2026-10-24: deliberate doubles finish ~1.2 s apart and each move is held up to ~1.2 s.
  uint32_t doubleMs = 1500;  // second gesture must finish this soon after the first
  uint32_t lockoutMs = 1200; // after a double, ignore everything (swallows a third)

  uint32_t lastAt[4] = {}, firedAt = 0;
  uint8_t pending = 0; // bit per gesture kind completed once, awaiting its second
  bool fired = false;

  GestureDetector() {
    nod.cooldownMs = 0; nod.maxDownMs = 1250; // timing is owned by the double logic below
    for (NodDetector* turn : {&left, &right}) {
      turn->downDeg = 25; turn->returnDeg = 10; turn->maxDownMs = 1250; turn->cooldownMs = 0;
    }
  }

  // Returns a Gesture exactly once per completed double, else NoGesture.
  uint8_t update(float pitch, float yaw, uint32_t now) {
    // Update every detector every sample: their neutral tracking must keep running.
    const bool n = nod.update(pitch, now), l = left.update(yaw, now), r = right.update(-yaw, now);
    const uint8_t g = n ? DoubleNod : l ? DoubleLeft : r ? DoubleRight : NoGesture;
    if (g == NoGesture || (fired && now - firedAt < lockoutMs)) return NoGesture;
    // Pair per kind: a head turn also tilts, and that stray nod must not cancel the turn's pair.
    if ((pending & (1u << g)) && now - lastAt[g] <= doubleMs) {
      pending = 0; fired = true; firedAt = now; return g;
    }
    pending |= 1u << g; lastAt[g] = now;
    return NoGesture;
  }

  bool settled(uint32_t now) const { return nod.settled(now) && !left.down && !right.down; }
};
}
