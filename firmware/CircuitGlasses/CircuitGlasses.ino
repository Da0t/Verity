// Example ONLY for the AI Thinker-compatible original ESP32-CAM pinout.
// Check the module marking/pinout; an MB USB baseboard alone does not identify it.
#include "BleCamera.h"
#include "Imu.h"

#if !CONFIG_IDF_TARGET_ESP32
#error "This example pinout targets original ESP32, not ESP32-S3/S2."
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
  Imu::begin();
  Serial.println("CircuitGlasses BLE ready; no Wi-Fi connection required.");
}

void loop() {
  if (Imu::poll()) BleCamera::notifyNod();
  BleCamera::poll(Imu::settled());
  delay(2);
}
