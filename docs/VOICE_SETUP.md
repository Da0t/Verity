# Laptop voice setup

Implemented: listening/working/error tones, mono recording at the microphone’s native sample rate, amplitude-based
speech/silence detection, hosted Gemini transcription, local system TTS and
cancellable playback. Audio never traverses the ESP32 BLE link.

Install `requirements/voice.txt`. Set `GEMINI_API_KEY` for standalone voice use;
after merging build-agents, its shared `.env.agents` configuration loader also works.
The transcriber defaults to the tested `gemini-3.1-flash-lite` API; override its
model through VERITY_STT_MODEL if needed. Audio is kept in memory for transcription.
Synthesized speech uses temporary files deleted after loading the WAV bytes.

## Windows

Use a USB/wired headset. Enable Windows microphone access for desktop apps. The
app uses sounddevice/PortAudio for recording and playback. It uses installed
Windows System.Speech voices through powershell.exe for synthesis; no cloud TTS
account needed. Text/path are sent through a JSON stdin payload, not shell commands.
The synthesis subprocess is killed on cancellation and playback streams abort.

Run `python -m sounddevice` to list device IDs. The integrated app accepts
--input-device and --output-device. Recording uses the device’s default rate and downmixes to mono. Playback is
resampled to the selected output device’s default rate/channels. Choose the same physical headset for output
and microphone input. No browser Web Bluetooth or browser microphone is needed.

For macOS development, system synthesis uses say + afconvert. Linux requires an
injected synthesizer; the standard integrated CLI currently targets Windows/macOS.

The default energy threshold is 0.015 full-scale RMS. --vad-threshold tunes it for
the actual microphone/room. Speech must exceed 120ms; recording ends after 800ms
of silence or a 10-second hard cap. Silence skips the hosted API. This is simple
energy detection: a loud room may need a closer boom mic and tuning.

## Interaction

Nod → listening tone → speak one question. The microphone closes before the
assistant speaks. A new deliberate nod during playback cancels it and starts a
new listening turn. “Stop” is recognized after that activation; always-listening
voice interruption is not implemented. Empty recordings return to idle.

## Verification

`python -m unittest discover -s tests -v` exercises the voice contract with fake
audio/provider objects plus real PCM endpoint detection. These tests do not open
a microphone or establish Windows device/driver compatibility. Use the integrated
`python -m verity.app --audio-check` for a real listening/transcription/playback
round trip after dependencies and credentials are installed. No recordings are
saved by that diagnostic. Real Windows headset tests remain required.

References:
https://python-sounddevice.readthedocs.io/en/0.5.3/api/streams.html
https://learn.microsoft.com/en-us/dotnet/api/system.speech.synthesis.speechsynthesizer
https://ai.google.dev/gemini-api/docs/audio

## Standalone Windows diagnostics

From your own clone, with Python 3.11+:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/voice.txt
.\.venv\Scripts\python.exe -m verity.audio --list-devices
$env:VERITY_INPUT_DEVICE = '2'  # replace with YOUR input index or unique name
$env:VERITY_OUTPUT_DEVICE = '4' # replace with YOUR output index or unique name
.\.venv\Scripts\python.exe -m verity.audio --audio-test --duration 3
.\.venv\Scripts\python.exe -m verity.audio --speech-test
```

The first diagnostic records a fixed local clip and replays it without saving or
uploading it. The speech test plays all cues and a sentence, then interrupts a
second playback and reports its latency. Confirm clarity and volume by ear.
`--input`/`--output` override the environment; otherwise OS defaults apply.
This laptop initially defaulted to a Steam virtual microphone, so choose the
actual headset explicitly. Indices can change after reconnecting devices.

Set the key in the launching terminal using a hidden prompt:

```powershell
$voiceKey = Read-Host 'Gemini API key' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $voiceKey).Password
Remove-Variable voiceKey
$env:VERITY_STT_MODEL = 'gemini-3.1-flash-lite'
.\.venv\Scripts\python.exe -m verity.audio --round-trip --duration 10
```

The cue finishes before recording begins. Say a short sentence, then pause.
This sends one utterance to Gemini and consumes provider quota. Only this
diagnostic prints its transcript. There are no automatic retries or model
fallbacks. The supplied development key was used in memory, never saved in Git
or a local credential file. Do not paste keys into scripts or committed files.

## Constructor and cancellation handoff

`Voice()` performs no audio or network work until `await start()`. Constructor
options retain `input_device`, `output_device`, `threshold` (fraction of full
scale), `audio`, `transcriber` and `synthesizer`. Additional options:

| Option | Default |
|---|---|
| `api_key` | `GEMINI_API_KEY`, then the agent configuration loader if installed |
| `stt_model` | `VERITY_STT_MODEL`, then `gemini-3.1-flash-lite` |
| `voice_name` | `VERITY_TTS_VOICE`, then the installed Windows default |
| `silence` | 0.8 s trailing quiet (0.1–3 s) |
| `max_duration` | 10 s including initial quiet; configurable up to 30 s |
| `provider_timeout` | 20 s per transcription |

The coach's `VERITY_MODEL` is independent. `listen(timeout)` records for at most
`min(timeout, max_duration)`, then applies a separate provider deadline. Device
opening/closing adds overhead; include both stages in the controller's overall
turn deadline. Clips over 2 MB are rejected by the transcriber, so a long cap at
a high native microphone rate may require shortening the recording duration.

Await `cue('listening')` before `listen()`. `listen()` first stops any remaining
output. `stop_speaking()` cancels synthesis/playback; the original `speak()` or
`cue()` awaiter receives `asyncio.CancelledError`. `close()` cancels active
recording/transcription/output, releases audio and closes the owned provider.
Close is idempotent; a closed instance cannot restart. Audio cannot play while
listening or transcribing. The nod consumer and turn IDs belong to the controller.

`VERITY_TTS_VOICE` selects an installed Windows voice. Native audio uses the
headset's sample rate/channels; the microphone is downmixed and playback is
resampled. Microphone recordings remain in memory. Local TTS uses deleted OS
temporary files. Native driver calls may delay cancellation if a driver hangs.

## Measured validation, October 24, 2026

`python -m unittest discover -s tests -v` passes 38 tests, retaining all tests from
the concurrent voice commits. Added checks cover provider errors/validation,
listening/transcription shutdown, timeout recovery, interruption during process
creation, and PortAudio's requirement that completion callbacks return `None`.
Mocks do not establish headset clarity or transcription accuracy.

Real Windows checks used Python 3.12.10, sounddevice 0.5.6, input 2 (AMD microphone
array) and output 4 (Realtek). Local capture/replay and speech completed. The
first native-format run captured 84,716 WAV bytes in 1.30 s for a 1 s recording
cap including device overhead. After correcting the native callback, final local
synthesis took 0.81 s and playback stopped in 0.047 s without callback errors.
These are operator diagnostics; audibility needs human confirmation.

A real Gemini request using `gemini-3.1-flash-lite` transcribed known synthesized
speech exactly: “Check the signal connector.” in 1.06 s through the final adapter
(7.36 s in the initial development check). A separate live microphone
run returned an empty transcript after 7.41 s, so this does not establish a
successful human spoken round trip. The initial `gemini-3.8-flash` and Flash alias
attempts timed out; listed `gemini-2.5-flash` returned HTTP 404. Model listing alone
did not establish generation access. The verified Flash Lite model is configurable.

Still required: actual headset audibility, a human spoken round trip, event-room
noise calibration, and wearer/IMU integration. Loud background noise can pass the
simple energy gate; there is no acoustic echo cancellation or always-on spoken
interruption. No claim of a complete hands-free acceptance run is made.
