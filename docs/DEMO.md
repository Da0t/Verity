# Integrated demo and validation

Use branch `codex/session-integration`. It merges the actual implementations from
codex/build-agents, codex/device-transport and codex/voice-interface. The entry point
is `python -m verity.app`; component contracts remain in docs/CONTRACTS.md.

## Validation performed October 24, 2026

* Complete firmware builds for AI Thinker ESP32-CAM using Arduino-ESP32 3.3.3
  and NimBLE-Arduino 2.3.6 (MPU-6050 enabled). Not flashed or tested on a board.
* A clean virtual environment installed requirements.txt successfully.
* 68 automated tests pass across component contracts and the session state machine.
* Scripted `python -m verity.app --mock` completes six turns: instruction, check,
  question, repeat, next, stop. One simulated photo, clearly labeled mock feedback.
* Live synthetic speech “Check this” was transcribed correctly by the hosted API.
* `python -m verity.diagnostics` completed real transcription → hosted coach/image
  analysis → real local speech synthesis in 6.1 seconds after input generation.
  The blank image correctly caused uncertainty and a request for a clearer view.
* That diagnostic used simulated nod, microphone, blank camera and playback sink.
  It did not test the physical glasses, circuit or Windows sound device.

## Hardware checks still required

1. Flash for the actual ESP32-CAM board (the software build is verified), then verify MPU-6050 identity,
   neutral calibration and nod direction. Confirm no SD/pin conflict.
2. Capture ten actual JPEGs at the working distance; measure transfer latency and
   whether the intended connection is visible. Ensure disconnect causes a clear
   error rather than reusing a cached frame. The adapter attempts a fresh connection; restart the app if discovery fails.
3. Use the Windows headset `--audio-check`. Tune VAD, verify noise handling and
   interrupt a long spoken answer with a deliberate nod.
4. Replace the generic template with the actual three-to-five-step circuit,
   manufacturer documentation and correct reference photos.
5. Perform three consecutive runs: instruction → visible mistake → check → useful
   correction → fix → recheck → contextual question. No screen interaction.

## Operator commands

```powershell
.\.venv\Scripts\python.exe -m verity.app --mock
.\.venv\Scripts\python.exe -m verity.app --list-audio-devices
.\.venv\Scripts\python.exe -m verity.app --audio-check
.\.venv\Scripts\python.exe -m verity.app --recipe recipes/your-circuit.json
```

The app refuses the template in live mode unless --allow-template is explicitly
provided. This permits diagnostics but does not establish recipe correctness.

On failure, the turn is cancelled or returns brief spoken feedback and returns
idle. Disconnection starts one bounded discovery/reconnection attempt; a failed scan
ends the session with cleanup. There is no unlimited reconnect or cost loop. Capture/model/STT results from cancelled turns are discarded. Normal
listening and speech playback do not overlap. “Next” is manual progression and
passes do not automatically advance. Only one model turn/capture runs at a time.

## Merge and release

All software changes are integrated on the session-integration branch and can be
reviewed/tested there. Keep main unchanged until the physical acceptance run is
complete. Record a backup video and report remaining hardware limitations honestly.
