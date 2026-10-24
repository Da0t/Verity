# Laptop voice setup

Implemented: listening/working/error tones, 16kHz mono recording, amplitude-based
speech/silence detection, hosted Gemini transcription, local system TTS and
cancellable playback. Audio never traverses the ESP32 BLE link.

Install `requirements/voice.txt` and merge the build-agents branch for the shared
Gemini configuration loader. Configure `.env.agents` using the setup checker.
The transcriber defaults to the tested `gemini-3.5-flash-lite` API; override its
model through VERITY_STT_MODEL if needed. Audio is kept in memory for transcription.
Synthesized speech uses temporary files deleted after loading the WAV bytes.

## Windows

Use a USB/wired headset. Enable Windows microphone access for desktop apps. The
app uses sounddevice/PortAudio for recording and playback. It uses installed
Windows System.Speech voices through powershell.exe for synthesis; no cloud TTS
account needed. Text/path are sent through a JSON stdin payload, not shell commands.
The synthesis subprocess is killed on cancellation and playback streams abort.

Run `python -m sounddevice` to list device IDs. The integrated app accepts
--input-device and --output-device. Recording requires 16kHz mono and the output
must accept the generated WAV rate. Choose the same physical headset for output
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
