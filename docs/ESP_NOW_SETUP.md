# Two-board setup: remote MPU-6050 over ESP-NOW

This local feature branch changes the glasses to:

```text
MPU-6050 -- I2C --> ESP32-WROOM -- ESP-NOW --> ESP32-CAM -- BLE --> Windows laptop
Headset microphone / audio ------------------------------------> laptop + hosted API
```

ESP-NOW carries nods and motion status, **not images**. JPEG capture stays on the
existing BLE pull protocol. Neither ESP32 joins a router; the laptop still needs
internet for hosted APIs. This does not remove 2.4 GHz interference. ESP-NOW and
BLE share the camera's radio and need a real coexistence/latency test.

## What is confirmed

The sensor board has an ESP32-WROOM module and an MPU-6050. The exact carrier
board and breakout regulator/pull-up circuit remain unidentified. A VCC label
alone does not establish its voltage requirements. Verify the breakout's supply
requirements and that SDA/SCL pull-ups use ESP32-compatible 3.3 V logic before
powering it. Do not apply 5 V to ESP32 GPIOs. Use a common ground between the
sensor and its ESP32; the two wireless boards need no signal wire between them.

The camera sketch assumes an **AI Thinker-compatible original ESP32-CAM pinout**;
an MB USB baseboard does not confirm that pinout. Confirm before uploading.

## Install and select sketches

1. Install Arduino IDE 2, Espressif ESP32 board package **3.3.3**, and
   **NimBLE-Arduino 2.3.6** from Library Manager. Wire/WiFi/ESP-NOW ship with the core.
2. Copy the whole `firmware/libraries/VerityLink` folder into your Arduino
   sketchbook's `libraries` folder; restart IDE. Keep this copy synchronized after
   changes. This is a repo-local shared library, not a Library Manager package.
3. Camera: open `firmware/CircuitGlasses/CircuitGlasses.ino`; select **AI Thinker
   ESP32-CAM** only after confirming the module pinout. Keep `VERITY_USE_ESPNOW_IMU=1`.
4. Sensor: open `firmware/ImuSender/ImuSender.ino`. **ESP32 Dev Module** is the
   original ESP32-WROOM compile reference; verify your carrier's upload/flash
   settings and pinout. The default sensor SDA/SCL are **-1**, intentionally unset.
5. Choose the correct COM port for each board. Serial Monitor is **115200 baud**.
   Follow each carrier's boot/reset procedure. The software work here does not
   flash either board.

## Configure wiring and peer MACs

On the sensor board, connect the verified MPU SDA/SCL pins to available
bidirectional GPIOs and set `VERITY_IMU_SDA` / `VERITY_IMU_SCL` in its `Config.h`.
GPIO21/22 are common candidates on many original ESP32 development boards, **not
confirmed wiring for this carrier**. Avoid flash, input-only, reserved and boot
strap pins according to its pinout. Set MPU AD0 to a defined level per its
breakout documentation. Address `0` probes 0x68 and 0x69; an explicit address is
also supported. WHO_AM_I must identify an MPU-6050.

For each board's initial diagnostic startup, the sketch prints its **STA MAC**
even with an unset peer. Use the other board's printed MAC as six hexadecimal
bytes, e.g. `{0x24,0x6f,0x28,0x12,0x34,0x56}` (example only):

| Configuration | Enter |
| --- | --- |
| Camera `VERITY_SENSOR_MAC` | Sensor board STA MAC |
| Sensor `VERITY_CAMERA_MAC` | Camera board STA MAC |
| Both `VERITY_ESPNOW_CHANNEL` | Same fixed channel, 1–11 |

Zero, broadcast, multicast and self MACs fail closed with a diagnostic. Do not
use a Bluetooth MAC. Rebuild and upload after configuration. These settings do
not contain Wi-Fi credentials; do not add `WiFi.begin()` or an access point.

## Calibrate and test in stages

1. **Sensor alone:** hold the mounted glasses still for about two seconds. Wait
   for `IMU calibrated`. Enable `VERITY_IMU_DEBUG=1` to see pitch and flags. Pitch
   must increase on a downward nod: change `VERITY_PITCH_DIRECTION` from 1 to -1
   if reversed. `VERITY_PITCH_AXIS` selects the accelerometer component (0=X,
   1=Y, 2=Z); mounting orientation must match. Default gesture: down >15 degrees,
   return within 6 degrees in 80–900 ms, with 1500 ms cooldown.
2. **ESP-NOW only:** power both boards; verify sensor `senderLink=1`, camera fresh
   motion diagnostics, and local nod messages. Without a BLE subscriber, camera
   consumes and drops nods deliberately. Those gestures will never play later.
   Motion flags: 0=unknown, 1=sensor fresh/calibrating, 3=calibrated/moving,
   7=calibrated/settled. Stop/restart the sensor: camera must become stale within
   1200 ms; reconnect must not generate an old nod.
3. **BLE camera:** enable Windows Bluetooth, use one laptop client at a time,
   run `python -m verity.device --no-nods --count 10` for JPEGs. Then run
   `python -m verity.device --count 10` and nod deliberately. Verify one photo per
   gesture, no replay after reconnect, and actual image clarity. Nod ACK counters
   confirm camera processing; they do not prove laptop audio or user perception.
4. **Full app:** follow VOICE_SETUP.md and run `python -m verity.app`. Test headset
   microphone, spoken questions and responses. No Python API or BLE UUID changed.
5. **Fault tests:** disconnect MPU, rotate/move during capture, power-cycle each
   board, disconnect/reconnect laptop, and test alongside ten JPEG captures.
   Measure gesture latency and false positives in the venue before demoing.

A read failure or implausible acceleration resets calibration. Unavailable or
older-than-200 ms sensor samples are unknown. Remote status expires after
1200 ms, and unknown/stale status is never settled. Capture waits up to 1500 ms
for settled confirmation, then **captures anyway** and prints a timeout warning;
this preserves the existing laptop capture contract and may produce a blurred
image. It does not claim the head is still. Camera frame capture can temporarily
block radio queue processing, so gestures may be dropped during busy periods.

## Troubleshooting

* No STA MAC/camera startup: check serial port, normal boot mode, supply, camera
  ribbon and matching camera pinout. The camera initialization precedes radio startup.
* `senderLink=0`: compare mutual STA MACs and channel, ensure both firmware versions
  match, move boards closer, inspect power/reset logs. Do not pair ESP-NOW in
  Windows Bluetooth settings; only connect to BLE `CircuitGlasses` there.
* No calibration: verify MPU power, ground, SDA/SCL, AD0/address and 3.3 V pull-ups;
  stay still. Restart after fixing an absent sensor detected at boot.
* Wrong nod direction: use pitch debug, correct axis/sign, then recalibrate.
* Local nod but no photo: check camera BLE subscriber diagnostic and run one
  client only. Gesture delivery is bounded; after link loss, wait for recovery
  and nod again. There is no persistent gesture backlog.
* Queue drops or missing nods during JPEG transfer: measure with the headset and
  venue traffic; try another common fixed channel and lower image size if needed.
  Do not promise routerless means interference-free.

## Direct-wired fallback

Set camera `VERITY_USE_ESPNOW_IMU=0` to use the shared MPU driver directly on the
camera, with configurable pins in camera `Config.h`. The retained defaults 13/14
apply only to the matching AI Thinker board with **no SD card** and no conflicting
peripherals. Camera SCCB pins 26/27 stay reserved. This mode has no ESP-NOW link
and needs no sensor ESP32. Both modes require the shared VerityLink library.

## References

The implementation follows Espressif's [ESP-NOW API and callback guidance](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-reference/network/esp_now.html)
and [radio coexistence guidance](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32/api-guides/coexist.html).
MAC send success is not an application acknowledgement. Callbacks only decode,
filter and enqueue; camera, BLE and Serial work happens in the main loop. See
[wire protocol](ESP_NOW_PROTOCOL.md) and [compile results](FIRMWARE_BUILD.md).
