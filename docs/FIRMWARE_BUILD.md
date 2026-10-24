# Firmware verification

The ESP-NOW feature is on local branch `codex/espnow-imu-bridge`, based on pulled
main commit `486ff77`. No push, merge or hardware flash was performed.

Toolchain: Arduino-ESP32 **3.3.3**, NimBLE-Arduino **2.3.6**, repo-local
**VerityLink 0.1.0**. ESP-NOW callbacks were checked against the installed ESP-IDF
5.5 headers; the send callback uses `esp_now_send_info_t` for that version.

## Reproduce builds

After installing the core/library versions and from the repository root:

```sh
arduino-cli compile --fqbn esp32:esp32:esp32cam --libraries firmware/libraries firmware/CircuitGlasses
arduino-cli compile --fqbn esp32:esp32:esp32 --libraries firmware/libraries firmware/ImuSender
arduino-cli compile --fqbn esp32:esp32:esp32cam --libraries firmware/libraries --build-property compiler.cpp.extra_flags=-DVERITY_USE_ESPNOW_IMU=0 firmware/CircuitGlasses
```

The first target assumes the AI Thinker-compatible original ESP32-CAM pinout.
The sensor target is an original ESP32-WROOM **compile reference**, not
confirmation of the unidentified carrier's wiring or upload settings. Unset
sensor pins and peer MACs compile but fail closed at runtime until configured.
See [beginner setup](ESP_NOW_SETUP.md). Arduino IDE users must install the shared
library into their sketchbook as described there.

These builds establish source/API compatibility, not runtime heap sufficiency,
RF latency, physical camera compatibility or gesture reliability. Flash/global
RAM sizes exclude dynamic camera, BLE and network allocations. Final compile results (bytes):

| Sketch / mode | Flash | Static global RAM |
| --- | ---: | ---: |
| Camera, ESP-NOW + BLE | 1,247,183 | 65,508 |
| ESP32-WROOM sensor reference | 923,427 | 44,976 |
| Camera, direct MPU fallback | 709,971 | 48,052 |

## Host tests

`python -m unittest discover -s tests -v` includes fake BLE/controller/audio tests
and host C++ assertions for nod detection plus ESP-NOW parsing/lifecycle behavior.
The C++ link test uses `-std=c++17 -Wall -Wextra -Werror -pedantic`.

An existing credentials-negative voice test reads `.env.agents` from its working
directory even while its environment is cleared. If you have configured that
file, run discovery from a clean temporary working directory with the repo on
PYTHONPATH, rather than modifying/deleting credentials. The full suite was run
that way here: **88 tests, successful, 2 skipped** (Windows process lifecycle
tests on this Mac). No live hosted API was needed for this firmware task.

For a credentials-independent run, in PowerShell from the repo root:

```powershell
$verityRoot = (Get-Location).Path
$verityPython = Join-Path $verityRoot ".venv\Scripts\python.exe"
$verityPreviousPythonPath = $env:PYTHONPATH
$env:PYTHONPATH = $verityRoot + [IO.Path]::PathSeparator + $env:PYTHONPATH
$verityTemp = New-Item -ItemType Directory (Join-Path $env:TEMP ([guid]::NewGuid()))
Push-Location $verityTemp.FullName
try { & $verityPython -m unittest discover -s (Join-Path $verityRoot "tests") -v }
finally {
    Pop-Location
    $env:PYTHONPATH = $verityPreviousPythonPath
    Remove-Item $verityTemp.FullName
}
```


Hardware validation remains outstanding: verified sensor carrier/power/pins,
mutual STA MACs, calibration/direction, nod ACK loss/restarts, Windows BLE JPEG
transfer alongside ESP-NOW, and the complete headset/app flow.
