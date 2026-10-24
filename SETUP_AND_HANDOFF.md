# Verity — Setup and team handoff

Updated: October 24, 2026

## What we are building

Verity is a hands-free assistant for electronics assembly. A user wearing camera
glasses nods to activate listening, asks a question or requests a wiring check,
and hears a short answer through a headset. Their hands stay on the build.

Hackathon target: one known circuit, three to five assembly steps, and one clearly
visible wiring mistake that the assistant can identify and help correct.

Repository: https://github.com/Da0t/Verity (private; teammates need access).

## Architecture decisions

```text
ESP32-CAM ── BLE JPEG snapshot ──┐
IMU ─────── BLE nod event ──────┤
                              ▼
Headset microphone ─────► Windows laptop ─────► Hosted AI API
                              │                    │
                              ◄──── answer ────────┘
                              ▼
                       Headset audio output
```

* Windows owns Bluetooth, microphone, audio playback, session state and API keys.
* Camera images are requested on demand, not streamed as continuous video.
* The IMU is an additional component; its model and wiring are not yet confirmed.
* A wired/USB headset with a microphone is the preferred initial audio device.
* Use a hosted model API. No cloud server deployment or rented GPU is required.
* BLE avoids joining venue Wi-Fi but still uses the 2.4 GHz band. Hosted inference
  still needs laptop internet; phone USB tethering is a possible connection.
* Cloud provider/model selection is still pending available team credentials.

## Current status — read before starting

Implemented and committed:

* Arduino camera/BLE snapshot prototype using NimBLE-Arduino 2.x.
* Example sketch for the AI Thinker-compatible original ESP32-CAM pinout.
* Python receiver with chunk offsets, CRC32 checks, timeouts and atomic image save.
* Six passing simulated receiver tests.
* Four development branches, component instructions and shared interfaces.

Not yet implemented or verified:

* Firmware compilation, flashing and real BLE image transfer on the team's board.
* Actual image quality and transfer latency at the working distance.
* IMU nod detection and BLE gesture events.
* Speech recognition, playback and cancellation.
* Hosted AI coach, visual inspection and documentation tools.
* The integrated session controller and hands-free demo.

The current tests validate receiver behavior with simulated data. They do not
establish radio performance, firmware compatibility or visual inspection quality.

## 1. Get repository access and clone

The owner must grant each teammate access to the private repository. Everyone
uses their own clone; do not switch branches in another person's active checkout.

Install Git, Python 3.11 or newer, and Arduino IDE if working on firmware.
Then run in Windows PowerShell:

```powershell
git clone https://github.com/Da0t/Verity.git
cd Verity
git fetch origin
git switch codex/device-transport
```

Replace the final branch with your assigned branch from the table below.
If Git cannot resolve the local branch, use:

```powershell
git switch --track origin/codex/device-transport
```

## 2. Set up the existing Python receiver on Windows

From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Using the virtual environment's executable directly avoids PowerShell activation
policy changes. The current dependency is Bleak; each component owner will add
their own dependency file as implementation proceeds.

Enable Bluetooth in Windows and confirm the laptop has a BLE-capable adapter.
The ESP32's USB baseboard provides programming/power; it does not supply Bluetooth
to the receiving computer. Keep the camera close for the first transfer test.

## 3. Configure and flash the camera

The description “ESP32-CAM with baseboard” is not enough to prove the pinout.
Confirm the camera board is AI Thinker-compatible before using the example.

1. Install the Espressif Arduino-ESP32 **3.x** board package in Arduino IDE.
2. Install **NimBLE-Arduino 2.x** through Library Manager.
3. Open `firmware/CircuitGlasses/CircuitGlasses.ino`. Keep `BleCamera.h` beside it.
4. For the compatible board, select **AI Thinker ESP32-CAM** and its COM port.
5. Use the board's PSRAM-enabled configuration and an application partition large
   enough for the compiled binary. Compile before attempting upload.
6. Upload using the baseboard's boot/reset procedure, then reset into normal mode.
7. Open Serial Monitor at **115200 baud**. Expected successful startup message:
   `CircuitGlasses BLE ready; no Wi-Fi connection required.`

The device still advertises as **CircuitGlasses**; that is the prototype BLE name,
while the product/repository name is Verity. Renaming it is optional and should be
coordinated with the device owner.

The example uses JPEG, a single frame buffer, VGA with PSRAM and QVGA otherwise.
For another board, preserve its known-working camera configuration and integrate
the transport as described in README.md. Do not guess alternate camera/IMU pins.

## 4. Receive a real photo

Once firmware is running:

```powershell
.\.venv\Scripts\python.exe receiver.py --output latest.jpg --interactive
```

The script discovers the BLE service and connects directly. Settings pairing is
not required by this prototype. It captures one image immediately, then Enter
captures another and `q` quits. This keyboard workflow is a development diagnostic;
the final product will activate through the IMU and speech.

Open `latest.jpg`, check that the relevant connector is visible, and record the
printed transfer time. Repeat while wearing the glasses. The receiver accepts
`--address` for selecting a device and `--timeout 90` for a longer transfer limit.
Increasing timeout does not improve throughput.

On failure, the receiver does not replace the previous image. Do not treat an
older file as a successful new capture. The integrated app should consume bytes
from a successful `capture_jpeg()` call instead.

## 5. Team assignments

| Person | Branch | Owned work | Detailed instructions |
|---|---|---|---|
| 1 | `codex/device-transport` | Camera, IMU, BLE and Windows adapter | `docs/tasks/01-device.md` |
| 2 | `codex/voice-interface` | Microphone, transcription, speech and interruption | `docs/tasks/02-voice.md` |
| 3 | `codex/build-agents` | Hosted coach, image inspection and document research | `docs/tasks/03-agents.md` |
| 4 | `codex/session-integration` | State machine, mocks, merging and demo | `docs/tasks/04-integration.md` |

Everyone reads `docs/CONTRACTS.md` before implementing. Person 4 owns integration
and approves interface changes. All four branches were created from the same
planning commit; a branch existing does not mean its component is implemented.

Use these boundaries:

* `Device`: connect, wait for nod, capture verified JPEG, close.
* `Voice`: start, play cue, listen, speak, stop speaking, close.
* `Coach`: answer using session context and an injected image-capture callback.
* Controller: own state, history, step progression, timeouts and cancellation.

Component dependencies go in `requirements/device.txt`, `requirements/voice.txt`,
`requirements/agents.txt`, or `requirements/app.txt` as those files are created.
Person 4 consolidates installation instructions. Do not independently rewrite
the root dependency file in all four branches.

## 6. Agent behavior

Implement one bounded coach with two specialist tools:

1. **Inspect build:** request one fresh photo, compare against the known step,
   return pass / issue / unclear with visible evidence.
2. **Look up documentation:** search cached, approved documentation for the exact
   demonstration components and return supporting sources. Live official-web
   research is optional after the core integration works.

The coach answers natural questions such as “where does this connect?” and “why
do I need this resistor?” using the current recipe, observation and documents.
It cannot directly change the controller's state or invent a completed check.

Initial limits: one capture, two document lookups and at most three model calls
per turn, inside an overall deadline. No unlimited retry or research loops.
If the connector cannot be seen, ask for a clearer view. A photo is not evidence
of electrical continuity or a guarantee that the circuit is safe to power.

## 7. Hands-free interaction and state

```text
IDLE → nod → listening tone → LISTENING
     → question → THINKING / optional CAPTURING
     → spoken answer → IDLE
```

* Wait for the head to settle before capturing a photo.
* A nod activates listening; it does not verify a completed wiring step.
* A new deliberate nod during speech interrupts playback and reopens listening.
* A new deliberate nod during processing cancels that turn; discard late results.
* Handle “repeat” and “stop” locally where possible.
* “Next” is manual progression, not a claim that the previous step was verified.
* Keep normal recording and playback separate to avoid hearing the assistant's
  own speech as a user command.

## 8. Credentials and configuration

Person 3 chooses a hosted provider based on credentials the team actually has,
verifies its current SDK/model support, and shares configuration variable names.
Person 2 coordinates speech-provider access. There is no configured API key yet.

Store keys in environment variables or a local ignored `.env` file. Never paste
keys into source, documentation, commits, recordings or screenshots. Person 4
will create `.env.example` containing variable names and placeholders only.
Local `.env` files are not loaded automatically unless the implementation adds
that behavior. Do not assume the existing receiver uses a hosted API—it does not.

## 9. Integration schedule and Git workflow

Relative to starting implementation:

| Checkpoint | Goal |
|---|---|
| 30 minutes | Component interfaces and mocks work |
| 60 minutes | Real photo, real voice round trip, agent fixture response |
| 120 minutes | First integrated nod-to-spoken-answer loop |
| 180 minutes | Actual correction, timeout handling, feature freeze |
| 240 minutes | Rehearsed demo, backup recording, submission |

Reserve the final 45 minutes for rehearsal if the available time is shorter.
Cut live research and automatic planning before cutting end-to-end reliability.

Each owner commits and pushes only their assigned work:

```powershell
git status
git add <your-specific-files>
git commit -m "Describe the implemented component change"
git push -u origin HEAD
```

Send Person 4 the commit SHA, smoke-test command, required configuration and known
limitations. Person 4 merges each component into `codex/session-integration`,
tests the combined system, then merges to main after the acceptance run. No force
pushes or shared-checkout branch switching.

## 10. Demo acceptance and immediate next decisions

Acceptance: a wearer nods, asks for an instruction, creates the chosen visible
mistake, requests a check, hears a useful correction, fixes it, rechecks and asks
a contextual question—all without touching a screen. Repeat successfully three
times with the real hardware. Also test stop, unclear images and disconnection.

Still needed from the team:

* Exact camera board and IMU identification; available pins.
* Headset/microphone and working Windows Bluetooth adapter.
* Exact demonstration circuit, correct reference photos and documentation.
* Hosted API provider access and agreed model configuration.
* Assignment of actual teammate names to Persons 1–4.

## Troubleshooting

| Symptom | First checks |
|---|---|
| Private clone fails | Repository invitation accepted; correct GitHub account |
| No camera found | Power, firmware startup, Bluetooth adapter, proximity, other connected clients |
| Camera initialization fails | Correct pinout, ribbon connection, power and PSRAM configuration |
| Transfer is slow | Measure image size/MTU behavior; try smaller JPEG; do not assume streaming is feasible |
| Image is unreadable | Lens focus, lighting, head position and connector size |
| Hosted response fails | Laptop internet, provider credentials, model access and timeout |
| False nod activations | Wearer calibration, pitch thresholds, return-to-neutral condition and cooldown |

Further detail: README.md, docs/TEAM_PLAN.md, docs/CONTRACTS.md and the assigned
task document. These files are the source of truth for team integration.
