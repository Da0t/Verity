# Person 2 — Hands-free audio interface

Branch: `codex/voice-interface`

## Goal

Deliver the Voice interface in ../CONTRACTS.md on the receiving Windows laptop.
Use a wired/USB headset with microphone initially. Audio goes through the laptop,
not through the ESP32 camera transport.

## Owned paths

* `verity/voice.py`, `verity/audio/`
* `requirements/voice.txt`
* `tests/test_voice.py`
* `docs/VOICE_SETUP.md`

## Work order

1. Enumerate/select input and output devices and record/play a short test on
   Windows. Make device selection configurable, with sensible defaults.
2. Implement listening/working/error earcons. Listening must begin after the cue.
3. Record one utterance using silence detection and a hard duration cap.
4. Integrate a working hosted speech-to-text provider; coordinate API access with
   Person 3. Do not assume an existing provider key or silently embed one.
5. Implement spoken output using hosted TTS or a working local Windows voice.
   Prefer the option already reliable on the actual machine.
6. Implement prompt playback interruption and clean resource release. An IMU nod
   is handled by Person 4, which calls stop_speaking before reopening listening.
7. Handle empty/noisy recordings, unavailable devices and provider timeout.

## Do not build

IMU detection, BLE, visual inspection, conversation policy or the main controller.
Do not add an always-open microphone loop or a realtime audio framework unless
the simpler path is already working and the integration owner approves.

## Acceptance

On Windows, a cue is audible; a spoken sentence produces a transcript; a supplied
sentence is spoken; stop_speaking interrupts a long answer promptly. Empty audio
returns an empty string. Device/API failures surface without hanging. Test with
actual event-room background noise if possible. No credentials or recordings in Git.

## Handoff

Provide the required environment-variable names, dependencies, constructor options,
device selection instructions, smoke-test command, measured latency and commit SHA.
Tests may mock providers, but label real microphone/provider checks separately.
