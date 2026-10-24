# Device setup: camera, IMU nod and BLE (Windows)

Owner: Person 1 (`codex/device-transport`). Interface: `Device` in
[CONTRACTS.md](CONTRACTS.md).

## Status

Software tests pass with simulated BLE clients (`tests/test_device.py`,
`tests/test_receiver.py`). The nod detector logic was checked in simulation.
**Not yet done on hardware:** firmware compilation, flashing, real photo
transfer, latency, IMU wiring and wearer nod tuning. Camera board and IMU part
are still unconfirmed. Do not treat these results as hardware validation.

## Laptop setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/device.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Flash the firmware

Follow README "Firmware integration" (Arduino-ESP32 3.x, NimBLE-Arduino 2.x,
AI Thinker ESP32-CAM, PSRAM enabled, Serial Monitor 115200). The sketch folder
now contains `BleCamera.h` and `NodDetector.h`; keep both beside the `.ino`.

Without IMU defines the sketch is camera-only, as before, and still exposes
the nod characteristic, which never notifies.

## Enable the IMU

The sketch reads an MPU-6050-compatible IMU (register map at 0x68) over
Arduino `Wire`. Confirm the actual part first; other IMUs need a different
read in `imuPoll()`.

1. Pick two free pins. On AI Thinker boards every exposed pin is shared:
   * 2, 4, 12, 13, 14, 15 are SD card pins (4 also drives the flash LED).
   * 12 is a boot strapping pin: an I2C pull-up on it can stop the board booting.
   * 0 (camera clock, boot), 16 (PSRAM) and 1/3 (serial) are unavailable.
   * With the SD card unused, 13/14/15 are the candidates to **verify**, not a
     decision. Confirm boot, flashing and camera still work after wiring.
2. Uncomment `VERITY_IMU_SDA`/`VERITY_IMU_SCL` in `CircuitGlasses.ino` with
   those pins, plus `VERITY_IMU_DEBUG` for tuning.
3. With the glasses worn, watch Serial Monitor: looking down must INCREASE
   pitch. If not, change the axis/sign in the `raw` line of `imuPoll()`.
4. Tune the `NodDetector` fields (top of `NodDetector.h`, or set them on `nod`
   in `setup()`): `downDeg`, `returnDeg`, `minDownMs`, `maxDownMs`, `cooldownMs`.
   Test deliberate nods, looking down at the bench, reaching for parts and
   turning to talk. Each deliberate nod should print `Nod` exactly once.

Detector behavior: a nod is pitch going `downDeg` below neutral and returning
within `returnDeg` in 80-900 ms. Holding down longer (looking at the bench)
makes that the new neutral rather than a nod. Neutral otherwise follows
posture slowly. Nods inside the 1.5 s cooldown are ignored. A requested photo
waits up to 1.5 s for pitch to stay still for 250 ms before capturing.

Known limits: accelerometer-only pitch (no gyro fusion), so walking or sharp
movement can cause false nods; a quick glance down and back looks like a nod.

Host-side check for the detector, where a C++ compiler is available:

```sh
g++ -std=c++17 -I firmware/CircuitGlasses firmware/tests/nod_detector_test.cpp -o nod_test && ./nod_test
```

## BLE protocol addition

Same service as README "Protocol", plus:

* NOD `369f0005-7d5c-4f30-a16b-8c578d930001`: read/notify. One notification
  per detected nod, payload `seq:u32` little-endian, counting up from 1.

Raw IMU samples stay on the device.

## Smoke tests

```powershell
# Ten back-to-back photos, camera-only firmware; prints size and seconds each
.\.venv\Scripts\python.exe -m verity.device --no-nods --count 10
# Nod-triggered: each nod captures and saves latest.jpg
.\.venv\Scripts\python.exe -m verity.device --count 10
```

Failed photos are reported and the next one reconnects. To test the disconnect
case, unplug the camera power during a transfer: that photo must fail, and the
next one must succeed after power returns.

## Using Device

```python
from verity.device import Device
device = Device(address=None, scan_timeout=15.0, nods=True, nod_max_age=1.5)
await device.connect()
await device.wait_for_nod()        # once per fresh nod
jpeg = await device.capture_jpeg(timeout=30.0)
await device.close()
```

* `address`: BLE address to use instead of the first device advertising the service.
* `nods=False`: camera-only firmware; `connect()` otherwise fails if the nod
  characteristic is missing.
* `nod_max_age`: nods not consumed within this many seconds are discarded.
  Pending nods are coalesced into one.
* `capture_jpeg` and `wait_for_nod` reconnect if the link dropped. They raise
  `RuntimeError` if the camera cannot be found. A failed capture raises; it never
  returns an older image. Captures are serialized.
* After `close()`, a pending `wait_for_nod` raises `ConnectionError`.
* Run from the repository root: `verity.device` imports `receiver.py`.

## Handoff to Person 4 (fill in after hardware testing)

| Item | Value |
|---|---|
| Camera board | unconfirmed |
| IMU part / pins | unconfirmed |
| Photo size / latency (10 runs) | not measured |
| Nod-to-notification timing | not measured |
| Commit SHA | see `git log` on `codex/device-transport` |
