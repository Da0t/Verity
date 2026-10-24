# Device adapter and firmware

The default hardware path is MPU-6050 → separate ESP32-WROOM → ESP-NOW →
ESP32-CAM → BLE → Windows. Follow [two-board setup](ESP_NOW_SETUP.md) for wiring,
configuration, installation, calibration and staged tests. The explicit direct
MPU fallback is documented there too. See [build results](FIRMWARE_BUILD.md).

The Python Device adapter is unchanged. It exposes
`connect` / `wait_for_nod` / `capture_jpeg` / `close`, using the existing JPEG
protocol and a 350 ms post-nod settling delay. A disconnect prompts one fresh
connection attempt; a failed capture raises instead of reusing an older photo.

Nod characteristic: `369f0005-7d5c-4f30-a16b-8c578d930001`, NOTIFY.
Camera notifications remain four-byte little-endian uint32 sequence numbers.
The adapter also accepts eight-byte sequence + timestamp packets for prototype
compatibility. It timestamps reception, deduplicates, coalesces and drops stale
activations. Camera BLE service and JPEG command/status/data layouts are unchanged.

Use one BLE client at a time. Start with camera-only checks:

```sh
python -m verity.device --no-nods --count 10
python -m verity.device --count 10
```

The second command captures on nods; the first requests photos without activation.
The tool reports image sizes/latency and saves successful JPEGs atomically.
Use `--address` to select a device. Close it before running `python -m verity.app`.
Neither successful compilation nor fake BLE tests validate physical RF performance.
