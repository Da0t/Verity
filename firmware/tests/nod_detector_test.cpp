// Host-side check for NodDetector (not part of the Arduino sketch).
// g++ -std=c++17 -I firmware/CircuitGlasses firmware/tests/nod_detector_test.cpp -o nod_test && ./nod_test
#include <assert.h>
#include <stdio.h>
#include "NodDetector.h"

// Hold `deg` for `ms` at 100 Hz; return number of nods reported.
static int hold(NodDetector& d, uint32_t& t, float deg, uint32_t ms) {
  int n = 0;
  for (uint32_t end = t + ms; t < end; t += 10) n += d.update(deg, t);
  return n;
}

int main() {
  NodDetector d; uint32_t t = 0;
  assert(hold(d, t, 0, 1000) == 0);
  assert(hold(d, t, 25, 300) == 0);            // down...
  assert(hold(d, t, 0, 100) == 1);             // ...and back: one nod
  assert(hold(d, t, 25, 300) + hold(d, t, 0, 100) == 0); // inside cooldown
  hold(d, t, 0, 2000);
  assert(hold(d, t, 35, 3000) == 0);           // looking down at the bench
  assert(d.settled(t));
  assert(hold(d, t, 60, 300) + hold(d, t, 35, 100) == 1); // nod from bench posture
  hold(d, t, 35, 2000);
  assert(hold(d, t, 45, 300) + hold(d, t, 35, 100) == 0); // too small
  assert(hold(d, t, 60, 30) + hold(d, t, 35, 100) == 0);  // too brief
  puts("NodDetector OK");
}
