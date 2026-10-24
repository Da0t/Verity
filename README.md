# Verity

Hands-free guidance for building electronics. Verity uses camera glasses to
observe an assembly and aims to provide spoken, step-by-step feedback.

## Team development

Start with the [four-person work plan](docs/TEAM_PLAN.md), then read the
[shared interfaces](docs/CONTRACTS.md) and your assigned component instructions.
The target architecture is a Windows laptop with hosted AI APIs, IMU activation,
headset audio, and bounded inspection/documentation tools.

## Current prototype: BLE camera transport

Transfers one JPEG from an ESP32 camera to a laptop without joining a Wi-Fi
network. This is a conservative, request/read transport, not a video streamer.
No voice or vision integration is included yet. Call `capture_jpeg()` from the
assistant's “check” handler to obtain image bytes.

## Status and hardware assumptions

The Python protocol tests run without hardware. The firmware has NOT been
compiled or tested on a device: no Arduino toolchain or attached camera was
available. Board identity and camera pins must be confirmed before flashing.
Original ESP32 and ESP32-S3 support BLE; ESP32-S2 does not.

BLE avoids venue Wi-Fi association, credentials, and client isolation. It is
still a 2.4 GHz radio link and does not guarantee freedom from interference.
Cloud model requests still require laptop internet, for example a phone's USB
tethering connection. This prototype is an unpaired, single-client demo service;
it is not an authenticated camera deployment.

## Firmware integration

For the common **AI Thinker ESP32-CAM + ESP32-CAM-MB baseboard**, an example is
included at `firmware/CircuitGlasses/CircuitGlasses.ino`. Confirm the camera board
uses the AI Thinker pinout, then open that sketch in Arduino IDE. Install the
Espressif Arduino-ESP32 3.x board package and NimBLE-Arduino 2.x library, select
**AI Thinker ESP32-CAM** and your baseboard's COM port, then compile/upload.
Use the board's PSRAM-enabled configuration and an application partition large
enough for the reported binary. If upload fails, follow your baseboard's boot/reset
procedure; reset into normal operation after upload. Serial Monitor is 115200.
The pin mapping follows Espressif's CameraWebServer AI Thinker definition.

For existing firmware or a different camera board:

1. Start with camera firmware known to work on YOUR exact board. Preserve its
   camera pin definitions. Install **NimBLE-Arduino 2.x** in Arduino Library Manager.
2. Copy `firmware/CircuitGlasses/BleCamera.h` beside your `.ino` file and include it:

   ```cpp
   #include "BleCamera.h"
   ```

3. Before `esp_camera_init(&config)`, configure:

   ```cpp
   config.pixel_format = PIXFORMAT_JPEG;
   config.frame_size = FRAMESIZE_VGA; // 640x480 initial detail/transfer compromise
   config.jpeg_quality = 16;        // lower numbers mean better quality/larger file
   config.fb_count = 1;             // required for the fresh-frame strategy here
   ```

   VGA needs sufficient memory; enable PSRAM when your board has it. Use QVGA
   if memory or transfer speed requires it, and check whether connectors remain
   visible. Do not assume a low-resolution image can resolve breadboard holes.

4. After successful camera initialization, call `BleCamera::begin();`.
   Remove Wi-Fi connection/wait loops and HTTP server startup. Do not run a
   second camera consumer or initialize another BLE library alongside this one.
5. In Arduino `loop()`, call:

   ```cpp
   BleCamera::poll();
   delay(2);
   ```

Capture runs in the Arduino loop, outside BLE callbacks. One frame is retained
until another capture or 90 seconds without chunk requests. After reconnecting,
request a new capture. The receiver intentionally fails on disconnect rather
than silently reusing an old photo.

## Laptop setup

**Windows PowerShell**, from this folder (no activation-policy changes needed):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe receiver.py --output latest.jpg --interactive
```

Turn on Bluetooth in Windows and ensure the machine has a BLE-capable adapter.
The script discovers and connects directly; OS Settings pairing is not required
by this prototype. The USB baseboard is for flashing/power; it does not replace
the laptop's Bluetooth adapter. Keep the powered camera close for the first test.

From this folder, using Python 3.10 or newer:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python receiver.py --output latest.jpg --interactive
```

Windows activation is `.venv\Scripts\activate`. Allow Bluetooth access to the
terminal/Python host on macOS if prompted. Use the native Python receiver;
browser Web Bluetooth is not required. Close other camera clients first.

The first photo is captured immediately. Enter captures another; `q` quits.
For multiple nearby devices use `--address` with the device address (a peripheral
UUID on macOS). The CLI prints transfer size and elapsed time. Measure these
before deciding that BLE is suitable for your demo. `--timeout 90` permits a
longer transfer, but does not improve speed. Failed transfers exit nonzero and
do not replace the last saved file. Downstream callers must act on success,
not merely on the existence of an older `latest.jpg`.

To integrate in an existing async assistant with a connected BleakClient:

```python
from receiver import capture_jpeg
jpeg = await capture_jpeg(client, timeout=60)
# Send these fresh bytes to the vision model only after this call succeeds.
```

Serialize capture calls. The interactive CLI is a transport diagnostic, not
the final hands-free interface.

## Protocol

All integers are unsigned little-endian. UUIDs are in both source files.

* COMMAND write-with-response: `0x01 + request_id:u32` requests capture.
* STATUS read: `state:u8 + request_id:u32 + size:u32 + crc32:u32` (13 bytes).
  States: idle 0, capturing 1, ready 2, camera error 3.
* COMMAND: `0x02 + request_id:u32 + offset:u32` selects a JPEG chunk.
* DATA read: `offset:u32 + bytes`. Response length is limited to negotiated
  ATT MTU minus one; JPEG payload is at most MTU minus five, capped at 508.
* Client verifies offset, total length, standard CRC32, and JPEG start/end
  markers before atomically saving the result.

This intentionally avoids notification queue loss and long GATT reads. It costs
a write/read round trip per chunk and may be slow, especially at default MTU.
There is no claimed throughput or latency until device testing. If too slow,
reduce JPEG size, then consider a windowed notification protocol. For a four-hour
deadline, compare against a private Wi-Fi access point before spending time on
that optimization.

## Tests and hardware acceptance

```sh
python3 -m unittest discover -s tests -v
```

Before using it in a demo: compile for the actual board; capture ten photos at
the working distance; open the saved JPEGs; measure latency and connector
visibility; disconnect mid-transfer and verify failure; reconnect and confirm a
fresh photo. Software tests do not establish radio performance or image quality.

References:
* https://github.com/h2zero/NimBLE-Arduino/blob/master/docs/Migration_guide.md
* https://bleak.readthedocs.io/en/latest/api/client.html
* https://github.com/espressif/esp32-camera
* https://github.com/espressif/arduino-esp32/blob/master/libraries/ESP32/examples/Camera/CameraWebServer/camera_pins.h
