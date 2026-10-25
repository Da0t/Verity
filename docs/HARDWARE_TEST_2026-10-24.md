# Hardware bench test: October 24, 2026

This records tests on Bryan's Windows x64 PC. Compile and hardware results are
separate; an existing firmware log does not prove the local source was flashed.

## Current scope: standalone IMU

The camera work was paused at the user's request. Its code is retained, but the
WROOM now defaults to `VERITY_ENABLE_CAMERA_LINK=0` in `firmware/ImuSender/Config.h`.
This disables its ESP-NOW radio and camera peer traffic. The MPU6050 remains on
SDA 21 / SCL 22. `VERITY_IMU_DEBUG=1` prints pitch, yaw and flags at 115200 baud.
After calibration, test two deliberate out-and-back gestures in quick succession:
`Local gesture 1` = double nod, `2` = double left, `3` = double right.

Keep the MPU still for calibration before moving it. Axis/sign and thresholds
still require a test with its actual mounting. Set `VERITY_ENABLE_CAMERA_LINK=1`
to restore the retained camera bridge later. Earlier camera results below are
historical; no camera upload or additional camera test is planned in this scope.

Standalone build passed with Arduino-ESP32 3.3.10: **310,740 bytes flash,
23,756 bytes static RAM**. The configured source keeps camera traffic disabled.
It was uploaded to COM4 and all flash hashes verified. After a normal reset,
the board printed `Standalone IMU mode; camera link disabled`, detected the MPU,
calibrated, and emitted pitch/yaw readings with flags 7 (calibrated/settled).
The retained camera-link mode was separately compiled using a verification copy
with the switch set to 1: **928,460 bytes flash, 47,040 bytes static RAM**. The
actual source and flashed firmware remain in standalone mode.

The first 90-second movement recording contained **500 calibrated samples**,
with pitch from -4.1 to +2.9 degrees and yaw from -41.4 to +3.1 degrees. No
gesture was emitted. Pitch never crossed the 15-degree nod threshold, and
calibration restarted during parts of the movement test. Gesture reliability
is not established by the successful raw sensor test.

A second focused 90-second test captured **611 samples**, pitch -2.4 to +3.9
degrees and yaw -122.3 to 0 degrees, again with no gesture events. Unknown and
calibrating heartbeat states appeared while the board was moved, followed by
recovery when still. The logs do not distinguish an I2C read failure from rejected
acceleration samples. Do not lower gesture thresholds until the loss of valid
motion samples and mounting/axis selection have been investigated.

## Command retest after calibration

The user performed each requested double gesture twice. A continuous COM4
recorder labeled each test phase and used the application's actual command map
from `verity.device.GESTURES`. No firmware or threshold changes were made for
this retest.

| Requested gesture | Expected event / command | Observed result |
| --- | --- | --- |
| Double nod | 1 / speak | No event; 41 debug samples, two calibration messages and two unknown-status heartbeats |
| Double left | 2 / back | No event; no valid debug samples and four unknown-status heartbeats |
| Double right | 3 / next | No event; 239 debug samples, three calibration messages and two unknown-status heartbeats |

The final stationary comparison recorded 299 samples with pitch -0.6 to +0.6
degrees, no gesture events, no unknown-status heartbeats, and a final settled
flag of 7. Valid readings recover at rest, but **hardware command acceptance
failed**. The exact cause of the lost valid motion samples is not established;
the current logs do not distinguish read failures from rejected acceleration.

Three targeted software tests passed: gesture kind mapping, local gesture
navigation, and gesture-loop routing. These use simulated device inputs and do
not establish hardware success. With the camera link disabled, this test checks
local WROOM command events; it does not exercise voice or full app transport.

Raw timestamped lines and per-phase results are in the ignored directory
`runs/hardware-2026-10-24/command-check/` (`serial.jsonl` and `summary.json`).

## Configuration

| Device | USB adapter / port | Arduino target | Peer STA MAC |
| --- | --- | --- | --- |
| ESP32-CAM | FT232R / COM3 | AI Thinker ESP32-CAM (`esp32:esp32:esp32cam`) | Sensor `20:50:0D:1A:5C:8C` |
| ESP32-WROOM + MPU6050 | CH340 / COM4 | ESP32 Dev Module (`esp32:esp32:esp32`) | Camera `E0:8C:FE:B6:28:C4` |

Sensor SDA is GPIO21 and SCL is GPIO22. Both use ESP-NOW channel 1.
COM4's chip MAC was read successfully with esptool: `20:50:0D:1A:5C:8C`
(ESP32-D0WD-V3, revision 3.1). The camera STA MAC remains supplied rather than
independently verified. The constant names in the supplied settings match the
verified sensor identity; the accompanying prose had the roles reversed.

## Dependencies

- Arduino IDE 2.3.10; existing Arduino-ESP32 3.3.10 provides both board targets.
- NimBLE-Arduino 2.3.6 installed.
- Repo-local VerityLink copied into the Arduino sketchbook's `libraries` folder.
- Project Python requirements verified in `.venv`; pyserial 3.5 installed for
  bench diagnostics. The application itself does not require pyserial.
- Both USB adapters enumerate as working COM ports. No driver installer was run
  by this test session.

## Results so far

- Python unittest discovery: **96 run, 94 passed, 2 skipped**. Tests ran from a
  temporary working directory with the repository on PYTHONPATH to avoid loading
  local credentials. The skipped tests require a host `g++` compiler.
- Configured IMU sender compiles: 928,456 bytes flash, 47,040 bytes static RAM.
- Configured camera with BLE startup diagnostics compiles: 1,256,149 bytes flash,
  67,392 bytes static RAM. The compiled Config.h contains the supplied sensor MAC.
- Configured IMU firmware uploaded on COM4 with esptool `--before no-reset`;
  bootloader, partition table, boot selector and application hashes all verified.
- Existing COM4 firmware reported `MPU found`, `IMU calibrated`, `senderLink=1`,
  and `motion=7` (calibrated/settled).
- Existing COM3 firmware reported camera/BLE startup and `remote IMU settled`.
  No gestures were exercised, so these logs do not establish gesture delivery.
- BLE adapter is enabled and discovers surrounding peripherals. Repeated scans
  did not find CircuitGlasses or its service; `python -m verity.device --no-nods
  --count 1` failed with `Camera not found`. **No new JPEG was captured.**
- Current firmware printed a zero STA MAC in startup logs on both ports. The
  separate esptool read verified the sensor's actual hardware MAC. Startup text
  alone should not be used to verify the camera MAC.
- Automatic upload reset on COM4 returns to normal flash boot (`0x13`). A manual
  BOOT/EN sequence on the WROOM allowed the MAC read. The camera's BOOT button
  does not control COM4.

## Deferred camera work

Camera upload, camera MAC verification, BLE JPEG capture and camera fault/reconnect
tests remain unperformed and are outside the current standalone IMU scope.
Use the BOOT button on the board corresponding to the selected COM port when
resuming hardware uploads.

Diagnostic serial captures and build logs are kept under
`runs/hardware-2026-10-24/` when available; this directory is ignored by Git.

## IMU dropout fix and gesture validation (Claude Code, evening session)

**Root cause of "lost readings during movement":** `MotionSensor::poll()` in
`firmware/libraries/VerityLink/src/VerityMotion.h` called `reset()` (wiping
calibration *and* the gesture detector) whenever one sample's accel magnitude
left 0.75–1.25 g, and on any single failed I2C read. Real nods/turns measured
0.18–2.62 g, so every gesture wiped calibration, and recalibration needs ~2 s of
stillness. Logs showed telemetry stopping at each movement onset followed by
`IMU calibrated.`.

Fixes, each confirmed on the WROOM + MPU6050 (sensor wiring was fine: 0 I2C
failures across all runs):

1. **Dropout:** out-of-range accel samples are skipped (pitch held, yaw keeps
   integrating against the last good gravity direction); failed reads are
   counted and skipped; full reset only after 1 s with no good read. Debug line
   now also prints `g`, `i2c`, `rej` counters and raw accel `a x y z`.
   Result: one calibration per session, max telemetry gap 0.2 s.
2. **Pitch axis:** slow orientation test showed looking down moves gravity from
   −Y to −Z, so `VERITY_PITCH_AXIS` 0 → **2** in `firmware/ImuSender/Config.h`.
   Pitch/yaw signs (`DIRECTION 1`, `YAW_DIRECTION 1`) confirmed correct.
3. **Gesture timing** (`Verity/GestureDetector.h`): deliberate doubles finished
   ~1.2 s apart and moves were held up to ~1.2 s, beyond the untested defaults.
   `doubleMs` 900 → 1500, nod/turn `maxDownMs` → 1250, and doubles now pair per
   gesture kind so a stray nod from a head turn can't cancel a left/right pair.
   `firmware/tests/link_test.cpp` updated (slow-pair gap, cross-talk case).

**Final hardware run** (board already calibrated, ~5 rounds of nod/left/right):
16 commands fired; **14/14 doubles from 34–91 s were correct**. Two misses:
the very first double nod (second nod held ~1.36 s, past 1250 ms) and one left
turn whose return tilted the board, firing a nod instead. Slow single movements
fired nothing (no false positives).

**Host C++ tests now run** via WSL Ubuntu `g++` (the earlier "2 skipped" were for
lack of a Windows compiler): `link_test` and `nod_detector_test` pass.

**Known gaps / next steps**
- Startup calibration needs stillness and gives no visible signal; a gesture run
  started before calibration finished silently did nothing. Consider an LED cue.
- Possible follow-ups backed by the two misses: `maxDownMs` 1500, and ignore a
  nod that completes while a turn is in progress. Not applied — the 10 Hz debug
  log is too coarse to tune against (the replay scored worse than the firmware
  itself). Log at 50 Hz before further threshold tuning.
- Yaw bias drifts ~0.5°/s at rest; harmless (detectors track neutral) but worth
  revisiting if turns get flaky.
- Thresholds were tuned with the board hand-held; re-check once mounted on the
  glasses frame.
- Camera link still disabled (`VERITY_ENABLE_CAMERA_LINK 0`); the camera sketch
  compiles against the fixed library but is untested on hardware.

Tools: `runs/hardware-2026-10-24/motionfix/record.py` (serial capture + summary)
and `replay.py` (Python port of the detectors for offline replay of debug logs).
