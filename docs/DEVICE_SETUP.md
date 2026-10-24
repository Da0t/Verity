# Device adapter and nod firmware

The Device adapter now subscribes to nod notifications and exposes the shared
connect/wait_for_nod/capture_jpeg/close interface. It uses the existing verified
JPEG protocol and waits 350ms after activation for the head to settle. A disconnect prompts one fresh discovery/connection attempt; if that fails, the
controller exits cleanly. A failed capture raises and never returns an older photo. No unlimited reconnection loop or stale image reuse.

Nod characteristic: `369f0005-7d5c-4f30-a16b-8c578d930001`, NOTIFY.
Packet: four bytes, little-endian uint32 sequence. The adapter also accepts an
eight-byte sequence + timestamp packet for compatibility with the other prototype.
The laptop timestamps reception, deduplicates sequence values, coalesces events,
and drops activations older than one second. The camera service UUID is unchanged.

## IMU configuration

The team confirmed the MPU-6050. Its driver is enabled by default in Imu.h.
Set VERITY_ENABLE_MPU6050 to 0 for camera-only diagnostics. It checks WHO_AM_I, wakes the
chip, uses +/-2g and +/-250deg/s ranges, and calibrates a neutral posture from
100 still samples. Then it detects a deliberate pitch-down and return gesture.
Default threshold 15 degrees, return within 6 degrees, 80–900ms duration,
1500ms cooldown. Neutral posture follows sustained changes rather than treating
looking down at the bench as an activation. Camera capture waits for 250ms of
stillness, with a 1500ms maximum settling delay. These values need wearer testing, not just software tests.

For the included AI Thinker ESP32-CAM example ONLY: candidate SDA=13, SCL=14,
3.3V logic, common ground. This assumes **no SD card**, no other peripheral using
those pins, and the confirmed AI Thinker pinout. Check the module's power and
pull-up requirements. GPIO13/14 also serve the SD interface; never enable both.
Change VERITY_IMU_SDA/SCL for your verified wiring. Camera SCCB pins 26/27 remain
reserved for the camera. If a downward nod decreases pitch, change
VERITY_PITCH_DIRECTION to -1. Other mounting axes need a corresponding pitch formula. Set VERITY_IMU_DEBUG
to 1 in Imu.h for 10Hz pitch/neutral/settled logs; each detected event also
prints Nod once on Serial Monitor.

Another IMU requires its own sensor readout; the pure NodDetector can be reused.
Do not claim an MPU-6050 driver works for an unidentified sensor. Camera capture
can briefly block IMU sampling in the Arduino loop; test activation during checks.

## Tests and hardware status

`python -m unittest discover -s tests -v` tests the laptop adapter with a fake BLE
client. On hosts with g++, a test compiles and exercises the pure gesture detector.
The complete camera + enabled MPU-6050 sketch **compiled successfully** for
`esp32:esp32:esp32cam`, Arduino-ESP32 3.3.3 and NimBLE-Arduino 2.3.6. It uses
708,967 bytes of flash and 47,996 bytes of static global RAM; dynamic heap use
and physical behavior have not been measured. It has **not been flashed here**. BLE, pin assignments,
IMU direction/calibration and gesture false positives need actual hardware testing.
In Arduino IDE select AI Thinker ESP32-CAM for the confirmed compatible board,
select its COM port, enable the board's PSRAM configuration, and choose an
application partition large enough for the compiled binary. Open
firmware/CircuitGlasses/CircuitGlasses.ino with BleCamera.h, Imu.h and NodDetector.h
in the same sketch folder. Upload using the baseboard's boot/reset procedure,
then reset into normal operation. Read the startup/calibration messages at 115200
baud. Test ten photos and deliberate nods before attempting the hands-free demo.

Sensor register reference:
https://invensense.tdk.com/wp-content/uploads/2015/02/MPU-6000-Register-Map1.pdf

## Device smoke CLI

`python -m verity.device --count 10` captures on each nod; `--no-nods --count 10`
captures back-to-back for camera-only checks. The tool reports size and latency
and saves each successful JPEG atomically. `--address` selects a device.

This branch merges the concurrent device implementation rather than replacing
its history. It retains its posture-adapting detector, firmware settling gate,
atomic save helper, reconnect behavior and diagnostic CLI, while adding explicit
MPU identity/calibration, packet compatibility, deduplication and total deadlines.
