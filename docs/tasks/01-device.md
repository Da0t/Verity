# Person 1 — Camera, IMU and BLE

Branch: `codex/device-transport`

## Goal

Deliver verified JPEG snapshots and deliberate nod events to the Windows
controller through the Device interface in ../CONTRACTS.md.

## Owned paths

* `firmware/`
* `receiver.py`
* `verity/device.py`
* `requirements/device.txt`
* `tests/test_receiver.py`, `tests/test_device.py`
* `docs/DEVICE_SETUP.md`

## Work order

1. Confirm camera model, IMU part number and pin allocation. The included sketch
   assumes AI Thinker original ESP32 pinout; the MB baseboard is not proof.
   Do not assign IMU I2C pins until camera, SD and boot-pin conflicts are checked.
2. Compile and flash the existing sketch. Receive a real image on Windows.
   Record image size, transfer time and whether required connections are visible.
3. Wrap the existing capture transport in Device. Own BLE lifecycle and errors.
4. Add IMU sampling/calibration and a down-and-return nod detector with hysteresis,
   cooldown and wearer-adjustable thresholds. Test looking down at the workbench
   and ordinary assembly motions for false activations.
5. Add a BLE nod notification characteristic and subscription. Document UUID and
   event format. Notify from firmware; queue through the adapter to wait_for_nod.
   Keep high-rate IMU samples on-device; send gesture events, not a raw stream.
6. Ensure camera capture happens after head motion settles. Support clean close,
   reconnect after explicit failure, and stale-event flushing.

## Do not build

Speech processing, vision prompts, agent logic, UI, cloud deployment or audio
streaming from the ESP32. Coordinate with Person 4 if a second IMU board is needed.

## Acceptance

Ten real photos transfer correctly; actual latency is reported. Deliberate nods
arrive once each. Normal looking-down motions are tested. Disconnect mid-transfer
causes an error; reconnect yields a new photo. Existing receiver tests pass.
Provide a short Windows setup and flash guide, plus known limitations.

## Handoff

Tell Person 4 constructor options, board/IMU identity, nod timing, measured photo
latency, commit SHA and smoke-test command. If BLE is too slow, report immediately;
do not silently change transport or claim a recorded fixture is live.
