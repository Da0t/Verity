# Device adapter and nod firmware

The Device adapter now subscribes to nod notifications and exposes the shared
connect/wait_for_nod/capture_jpeg/close interface. It uses the existing verified
JPEG protocol and waits 350ms after activation for the head to settle. Disconnect
wakes the waiter with an error; the controller exits cleanly so the operator can
reconnect by restarting. No unlimited reconnection loop or stale image reuse.

Nod characteristic: `369f0005-7d5c-4f30-a16b-8c578d930001`, NOTIFY.
Packet: eight bytes, little-endian uint32 sequence followed by uint32 device millis.
The laptop timestamps reception, deduplicates sequence values, coalesces events,
and drops activations older than one second. The camera service UUID is unchanged.

## IMU configuration

The team confirmed the MPU-6050. Its driver is enabled by default in Imu.h.
Set VERITY_ENABLE_MPU6050 to 0 for camera-only diagnostics. It checks WHO_AM_I, wakes the
chip, uses +/-2g and +/-250deg/s ranges, and calibrates a neutral posture from
100 still samples. Then it detects a deliberate pitch-down and return gesture.
Default threshold 18 degrees, return within 6 degrees, 180–1500ms duration,
1800ms cooldown. These values need wearer testing, not just software tests.

For the included AI Thinker ESP32-CAM example ONLY: candidate SDA=13, SCL=14,
3.3V logic, common ground. This assumes **no SD card**, no other peripheral using
those pins, and the confirmed AI Thinker pinout. Check the module's power and
pull-up requirements. GPIO13/14 also serve the SD interface; never enable both.
Change VERITY_IMU_SDA/SCL for your verified wiring. Camera SCCB pins 26/27 remain
reserved for the camera. If a downward nod decreases pitch, change
VERITY_PITCH_DIRECTION to -1. Other mounting axes need a corresponding pitch formula.

Another IMU requires its own sensor readout; the pure NodDetector can be reused.
Do not claim an MPU-6050 driver works for an unidentified sensor. Camera capture
can briefly block IMU sampling in the Arduino loop; test activation during checks.

## Tests and hardware status

`python -m unittest discover -s tests -v` tests the laptop adapter with a fake BLE
client. On hosts with g++, a test compiles and exercises the pure gesture detector.
The Arduino/ESP32 sketch is **not compiled or flashed here**. BLE, pin assignments,
IMU direction/calibration and gesture false positives need actual hardware testing.
Start from the camera setup in README.md, then test ten photos and deliberate nods.

Sensor register reference:
https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map1.pdf
