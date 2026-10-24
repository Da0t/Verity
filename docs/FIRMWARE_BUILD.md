# Verified firmware build

Complete camera + BLE + enabled MPU-6050 sketch compiled October 24, 2026.

* Board FQBN: `esp32:esp32:esp32cam` (AI Thinker-compatible original ESP32-CAM).
* Arduino-ESP32: **3.3.3**.
* NimBLE-Arduino: **2.3.6**.
* Flash: **708,967 bytes**, 22% of the configured 3,145,728-byte app partition.
* Static global RAM: **47,996 bytes**, 14% of 327,680 bytes.
* This is a compile result, not a measurement of runtime camera/BLE heap usage.
* No board has been flashed or physically validated by this build check.

Arduino IDE: install those specific board/library versions, open
`firmware/CircuitGlasses/CircuitGlasses.ino` with all three headers beside it,
select AI Thinker ESP32-CAM and the appropriate COM port, then verify/upload
according to your baseboard's boot/reset procedure. Serial Monitor is 115200.
Confirm the pinout before uploading to a different camera module.

Equivalent Arduino CLI command after installing the ESP32 board package and library:

```sh
arduino-cli compile --fqbn esp32:esp32:esp32cam firmware/CircuitGlasses
```

The compile caught a C++ type mismatch between camera length and size_t in the
chunk-size calculation; the explicit bounded conversion fixes it. MPU identity,
I2C configuration, gesture detection and BLE APIs compiled successfully together.

See DEVICE_SETUP.md for the confirmed MPU-6050, proposed GPIO13/14 wiring,
calibration, pitch-direction and debug settings. The SD interface must be unused
with those pins. Real BLE latency, connector visibility and gesture reliability
must still be measured with the glasses.
