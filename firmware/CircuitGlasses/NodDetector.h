#pragma once
// Down-and-return head nod detector. Plain C++, no Arduino dependency.
// Feed filtered pitch in degrees (positive = head tilted DOWN) at ~50-100 Hz.
// Thresholds are untested starting points: tune per wearer with VERITY_IMU_DEBUG.
#include <math.h>
#include <stdint.h>

struct NodDetector {
  float downDeg = 15;         // pitch below neutral that starts a nod
  float returnDeg = 6;        // must come back within this to finish it (hysteresis)
  uint32_t minDownMs = 80;    // shorter dips are jitter
  uint32_t maxDownMs = 900;   // longer is looking at the bench: becomes new neutral
  uint32_t cooldownMs = 1500; // ignore nods this soon after the last one
  float neutralTauS = 1.5f;   // neutral pose slowly follows the wearer's posture
  float stillDeg = 3;         // settled = pitch within this band...
  uint32_t settleMs = 250;    // ...for this long

  float neutral = NAN, anchor = 0;
  bool down = false;
  uint32_t downAt = 0, lastNod = 0, lastT = 0, stillSince = 0, nods = 0;

  // Returns true exactly once per completed nod.
  bool update(float pitch, uint32_t now) {
    if (isnan(neutral)) { neutral = anchor = pitch; lastT = stillSince = now; return false; }
    float dt = (now - lastT) / 1000.0f; lastT = now;
    if (fabsf(pitch - anchor) > stillDeg) { anchor = pitch; stillSince = now; }
    float rel = pitch - neutral;
    if (!down) {
      if (rel > downDeg) { down = true; downAt = now; }
      else neutral += (pitch - neutral) * fminf(1.0f, dt / neutralTauS);
      return false;
    }
    uint32_t held = now - downAt;
    if (held > maxDownMs) { down = false; neutral = pitch; return false; }
    if (rel >= returnDeg) return false;
    down = false;
    if (held < minDownMs || (nods && now - lastNod < cooldownMs)) return false;
    ++nods; lastNod = now;
    return true;
  }

  bool settled(uint32_t now) const { return !down && now - stillSince >= settleMs; }
};
