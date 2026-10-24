# Verity: four-person build plan

Architecture decision: Windows laptop owns Bluetooth, microphone, speaker,
session state and API credentials. Hosted APIs provide speech/model inference.
Glasses provide camera snapshots and IMU activation events. No cloud deployment
or rented GPU is required for this prototype.

## Assignment

| Person | Branch | Owns | Instructions |
|---|---|---|---|
| 1 | `codex/device-transport` | Camera, IMU, BLE, Windows device adapter | [Device](tasks/01-device.md) |
| 2 | `codex/voice-interface` | Microphone, transcription, speech output, cancellation | [Voice](tasks/02-voice.md) |
| 3 | `codex/build-agents` | Hosted model, visual inspection, document research | [Agents](tasks/03-agents.md) |
| 4 | `codex/session-integration` | Session state machine, mocks, integration and demo | [Integration](tasks/04-integration.md) |

Person 4 is the integration owner. Everyone reads [CONTRACTS.md](CONTRACTS.md)
before implementing. All four branches begin at the same planning commit.
Implementation work is assigned, not already implemented by these documents.

## Starting work

Each person uses their OWN clone:

```sh
git clone https://github.com/Da0t/Verity.git
cd Verity
git fetch origin
git switch --track origin/codex/device-transport
```

Replace the final branch with the assigned branch. Existing clones can use
`git switch <branch>` after fetching. Do not switch branches in a checkout
another teammate is using. Repository access must be granted to each teammate.

## Shared decisions to make in the first 10 minutes

* Identify the IMU, camera pinout, Windows Bluetooth adapter, headset, and exact
  demonstration circuit. Person 1 owns hardware confirmation.
* Person 3 selects a hosted provider supported by an available API key, checks
  current documentation/model availability, and tells Person 2 whether they
  can reuse that provider. Do not block voice on the same provider if a working
  alternative is already available.
* Person 4 freezes a three-to-five-step demo recipe. Person 3 checks its reference
  content. Capture real images of the correct build and chosen visible mistake.
* Agree on the circuit's visible labels; do not depend on reliably identifying
  individual breadboard holes from a distant ESP32 image.

## Checkpoints (relative to starting this split)

| Time | Required result |
|---|---|
| +30 min | Each component imports and exposes its contract; mocks work |
| +60 min | Real BLE photo; real spoken round trip; agent response from fixture; full mock session |
| +120 min | First integrated nod → question → photo → spoken answer |
| +180 min | Real error and correction work; cancellation/timeouts tested; feature freeze |
| +240 min | Rehearsed demo, backup recording, submission |

Shorten feature work if less time remains. Keep the last 45 minutes for actual
wearer tests and presentation. Research and automatic planning are the first cuts.

## Ownership and merge rules

* Do not edit another person's paths without coordinating. Contract changes need
  Person 4 approval and an update to CONTRACTS.md before implementation diverges.
* Each person adds dependencies to `requirements/<component>.txt`. Person 4 owns
  root requirements.txt and the final setup instructions.
* Keep credentials in environment variables/local ignored `.env` files. Never
  commit recordings, camera captures or keys by default. Use intentional fixtures
  only when the team has agreed they may be stored in the private repository.
* Push incremental commits and provide the integration owner the commit SHA,
  smoke-test command, and remaining limitations. Do not claim mock results are
  hardware or hosted-API validation.
* Person 4 merges the device, voice, and agent branches into their integration
  branch after each component smoke check. Run the end-to-end demo there. Merge
  the integration branch into main only after the acceptance run succeeds.
* Avoid force pushes and unrelated refactors. No framework migration.

## Acceptance run

Without touching a screen: deliberate nod → listening tone → “check this” →
fresh photo → specific spoken observation → correction → nod and recheck →
contextual question with a useful answer. Also demonstrate repeat and stop.
Run this three times with the actual glasses. Record real capture/response latency.
An uncertain observation must ask for a clearer view, not report success.
