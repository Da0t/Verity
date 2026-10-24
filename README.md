# Verity

Hands-free electronics assembly guidance: nod to activate, ask a question or
request a visual check, and hear a short response through a headset.

All four software components are implemented and merged on
**`codex/session-integration`**: device/IMU, voice, build agents and controller.
The software scenario and hosted speech/vision path have been tested. Firmware
builds successfully for AI Thinker ESP32-CAM using Arduino-ESP32 3.3.3 and
NimBLE-Arduino 2.3.6. Real glasses,
MPU-6050 calibration, BLE performance and a Windows headset still need bench testing.

## Architecture

```text
ESP32-CAM JPEG + MPU-6050 nod ── BLE ──► Windows session controller
Headset microphone ── Gemini transcription ──► build coach / inspection / docs
                                                     │
Headset ◄── local system TTS + cancellable playback ◄──┘
```

The laptop owns Bluetooth, audio, state and API keys. Hosted Gemini handles
transcription and model inference. No cloud server or rented GPU is required.
The tested model is `gemini-3.5-flash-lite`. Live inspection requests one fresh
photo rather than continuously streaming video. BLE still shares the 2.4GHz band;
laptop internet is required for hosted calls.

## Windows quick start

Use your own clone and the integration branch:

```powershell
git clone https://github.com/Da0t/Verity.git
cd Verity
git switch codex/session-integration
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m verity.agents.setup --model gemini-3.5-flash-lite --save
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m verity.app --mock
```

Enter the Gemini key at the hidden terminal prompt. Successful setup writes local
`.env.agents`, ignored by Git. Each machine needs its own configuration; credentials
are not included in the repository. This is a private repository requiring access.

Mock mode runs a scripted six-turn scenario and exits. It uses simulated nod,
audio, camera and model behavior, and labels all outputs as simulated. It requires
no BLE hardware, microphone or API key after dependencies are installed.

## Configure the hardware and audio

1. Confirm the **AI Thinker-compatible original ESP32-CAM** pinout. The MB USB
   baseboard alone does not identify the camera board. Follow
   [device setup](docs/DEVICE_SETUP.md) and open
   `firmware/CircuitGlasses/CircuitGlasses.ino` in Arduino IDE.
2. Use the tested Arduino-ESP32 **3.3.3** and NimBLE-Arduino **2.3.6**. The confirmed IMU is MPU-6050.
   Proposed I2C pins are **SDA13/SCL14**, only with the matching board pinout,
   unused SD interface and verified module power/pull-ups. Camera pins stay reserved.
   See Imu.h for configuration and gesture direction. Serial Monitor: 115200.
3. Power the camera and keep the glasses still for about two seconds for calibration.
   Missing IMU or disabled driver is reported on Serial Monitor. The prototype
   BLE device still advertises as `CircuitGlasses`.
4. Enable laptop Bluetooth and connect a USB/wired headset with microphone.
   Windows must allow microphone access for desktop apps. List audio devices:

   ```powershell
   .\.venv\Scripts\python.exe -m verity.app --list-audio-devices
   .\.venv\Scripts\python.exe -m verity.app --audio-check
   ```

   Use `--input-device ID --output-device ID` to select the headset.
   `--vad-threshold 0.015` controls the recording energy threshold; tune for the room.

For a camera-only diagnostic, `python receiver.py --interactive` saves verified
JPEGs and prints transfer latency. This keyboard diagnostic is separate from the
hands-free app. Failed captures do not overwrite an older image.

## Supply the actual circuit and run

`recipes/demo.json` is a **generic template**, not an approved circuit. Copy it,
replace all steps/expected connections with your verified build, and set
`template` to false. Add optional `reference_image` paths to steps, relative to
the recipe JSON. Use real JPEG references and approved documentation records as
explained in [knowledge/README.md](knowledge/README.md).

```powershell
.\.venv\Scripts\python.exe -m verity.app --recipe recipes/your-circuit.json
```

`--allow-template` permits generic diagnostics without pretending the template is
an electrically verified circuit. `--address` selects a particular BLE device.
Use a fresh session JSON and actual photo for the agent-only diagnostic described
in [AGENTS_SETUP.md](docs/AGENTS_SETUP.md).

## Hands-free behavior

* Nod down and return → listening tone → ask one question.
* “Check this” requests a fresh photo and a pass / issue / unclear observation.
* “What is the next step?” reads the current instruction. “Next” manually advances;
  it does not claim the prior step was verified.
* “Repeat” replays the previous answer without a model request.
* Nod during speech or processing to interrupt and reopen listening. Nods while
  recording are ignored. Say “stop” after activation to cancel that request.
* “End session” exits. Ctrl+C is available to the demo operator.

The controller serializes turns and drops cancelled results. Calls have deadlines;
there are no unlimited retries or model loops. The coach uses at most one capture,
two scoped document lookups and two model calls per turn. Documentation research
uses curated local records; broad live-web search is not implemented.

## Validation

Automated tests cover BLE protocol/adapter behavior, pure C++ nod detection,
recording endpoint logic, voice cancellation, agent schemas/tool limits, HTTP
failures and controller interruption/recovery. `python -m verity.diagnostics`
performs an explicit live hosted test with synthesized speech and a blank image,
without accessing microphone/BLE hardware or playing through a speaker. Hosted
API usage applies. That diagnostic needs local system TTS (Windows or macOS).

A real wearer must still validate ten photo transfers, gesture false positives,
Windows headset recording/playback and the chosen wiring-error demo. A photo does
not establish continuity or electrical safety. No circuit-specific accuracy is
claimed from the synthetic tests.

Further guides: [team ownership](docs/TEAM_PLAN.md), [interfaces](docs/CONTRACTS.md),
[device](docs/DEVICE_SETUP.md), [voice](docs/VOICE_SETUP.md),
[agents](docs/AGENTS_SETUP.md), [demo/integration](docs/DEMO.md).
