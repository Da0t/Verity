// Example ONLY for the AI Thinker-compatible original ESP32-CAM pinout.
// Check the module marking/pinout; an MB USB baseboard alone does not identify it.
#include "BleCamera.h"

#if !CONFIG_IDF_TARGET_ESP32
#error "This example pinout targets original ESP32, not ESP32-S3/S2."
#endif

// IMU nod detection is OFF until the IMU part and two free I2C pins are confirmed;
// camera, SD-card and boot-strapping pins conflict (see docs/DEVICE_SETUP.md).
// Assumes an MPU-6050-compatible register map at address 0x68. To enable:
// #define VERITY_IMU_SDA <pin>
// #define VERITY_IMU_SCL <pin>
// #define VERITY_IMU_DEBUG // print pitch at 10 Hz to tune NodDetector thresholds
#ifdef VERITY_IMU_SDA
#include <Wire.h>
#include "NodDetector.h"
static NodDetector nod;
static float pitch = NAN;
static uint32_t lastSample = 0, lastPrint = 0;

static bool imuBegin() {
  Wire.begin(VERITY_IMU_SDA, VERITY_IMU_SCL, 400000);
  Wire.beginTransmission(0x68); Wire.write(0x6B); Wire.write(0); // wake from sleep
  return Wire.endTransmission() == 0;
}

// Samples at 100 Hz, notifies nods, and returns whether the head is settled.
static bool imuPoll() {
  uint32_t now = millis();
  if (now - lastSample >= 10) {
    lastSample = now;
    Wire.beginTransmission(0x68); Wire.write(0x3B); // ACCEL_XOUT_H
    if (Wire.endTransmission(false) == 0 && Wire.requestFrom(0x68, 6) == 6) {
      int16_t a[3];
      for (auto& v : a) { int hi = Wire.read(); v = int16_t(hi << 8 | Wire.read()); }
      // Mounting-dependent: confirm looking DOWN increases pitch; swap axis/sign if not.
      float raw = atan2f(a[0], sqrtf(float(a[1])*a[1] + float(a[2])*a[2])) * 57.2958f;
      // ponytail: accelerometer-only pitch + low-pass; add gyro fusion if walking causes false nods
      pitch = isnan(pitch) ? raw : pitch + 0.3f * (raw - pitch);
      if (nod.update(pitch, now)) { BleCamera::notifyNod(); Serial.println("Nod"); }
    }
  }
#ifdef VERITY_IMU_DEBUG
  if (now - lastPrint >= 100) {
    lastPrint = now; Serial.printf("pitch %.1f neutral %.1f\n", pitch, nod.neutral);
  }
#endif
  return nod.settled(now);
}
#endif

void setup() {
  Serial.begin(115200);
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5; config.pin_d1 = 18;
  config.pin_d2 = 19; config.pin_d3 = 21;
  config.pin_d4 = 36; config.pin_d5 = 39;
  config.pin_d6 = 34; config.pin_d7 = 35;
  config.pin_xclk = 0; config.pin_pclk = 22;
  config.pin_vsync = 25; config.pin_href = 23;
  config.pin_sccb_sda = 26; config.pin_sccb_scl = 27;
  config.pin_pwdn = 32; config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? FRAMESIZE_VGA : FRAMESIZE_QVGA;
  config.jpeg_quality = 16;
  config.fb_count = 1;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
  esp_err_t result = esp_camera_init(&config);
  if (result != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x. Check pinout, power, ribbon and PSRAM.\n", result);
    while (true) delay(1000);
  }
  BleCamera::begin();
#ifdef VERITY_IMU_SDA
  if (!imuBegin()) Serial.println("IMU not found at 0x68; check part, wiring and pins.");
#endif
  Serial.println("CircuitGlasses BLE ready; no Wi-Fi connection required.");
}

void loop() {
#ifdef VERITY_IMU_SDA
  BleCamera::poll(imuPoll());
#else
  BleCamera::poll();
#endif
  delay(2);
}
