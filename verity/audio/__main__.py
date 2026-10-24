"""Voice-only diagnostics; these are development controls, not the controller."""

import argparse
import asyncio
from contextlib import suppress
import math
import time

from .io import SoundDeviceIO
from .io import earcon
from .synthesis import SystemSynthesizer
from ..voice import Voice, device_setting


async def diagnose(args):
    if args.list_devices:
        import sounddevice as sd
        print(sd.query_devices())
        print(f"Default input/output: {sd.default.device}")
        return
    audio = SoundDeviceIO(input_device=device_setting(args.input), output_device=device_setting(args.output),
                          threshold=args.threshold, silence=args.silence)
    if args.audio_test:
        await audio.start()
        await audio.play(earcon("listening"))
        print(f"Recording {args.duration:g}s locally, then replaying; no upload or saved file.")
        started = time.monotonic()
        wav = await audio.record(args.duration, detect_silence=False)
        elapsed = time.monotonic() - started
        await audio.play(wav)
        print(f"Capture complete: {len(wav)} WAV bytes in {elapsed:.2f}s. Confirm audibility by ear.")
        return
    if args.speech_test:
        await audio.start()
        for kind in ("listening", "working", "error"):
            await audio.play(earcon(kind))
        synthesizer = SystemSynthesizer(voice_name=args.voice)
        started = time.monotonic()
        wav = await synthesizer.synthesize("Verity is ready. Check the signal connector.")
        print(f"Local synthesis: {time.monotonic() - started:.2f}s")
        await audio.play(wav)

        class LocalTranscriber:
            async def close(self):
                pass

        class PreparedSpeech:
            async def synthesize(self, text):
                return wav

        voice = Voice(audio=audio, transcriber=LocalTranscriber(), synthesizer=PreparedSpeech())
        await voice.start()
        try:
            speaking = asyncio.create_task(voice.speak("Prepared local speech"))
            await asyncio.sleep(.5)
            started = time.monotonic()
            await voice.stop_speaking()
            elapsed = time.monotonic() - started
            with suppress(asyncio.CancelledError):
                await speaking
            print(f"Playback interruption: {elapsed:.3f}s. Confirm speech stopped by ear.")
            if elapsed > .5:
                raise RuntimeError("Playback interruption exceeded the 500 ms smoke-test budget")
        finally:
            await voice.close()
        return

    voice = Voice(audio=audio, voice_name=args.voice, max_duration=args.duration)
    try:
        await voice.start()
        await voice.cue("listening")
        print("Microphone open after cue; one utterance will be sent to Gemini.")
        started = time.monotonic()
        transcript = await voice.listen(timeout=args.duration)
        print(f"Capture + transcription: {time.monotonic() - started:.2f}s")
        print(f"Transcript: {transcript!r}")
        await voice.speak(transcript or "I did not hear clear speech. Please try again.")
    finally:
        await voice.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list-devices", action="store_true")
    mode.add_argument("--audio-test", action="store_true", help="Local record/replay; no API key needed")
    mode.add_argument("--speech-test", action="store_true", help="Local cues, Windows voice and interruption")
    mode.add_argument("--round-trip", action="store_true", help="One real microphone/Gemini/spoken round trip")
    parser.add_argument("--input", help="Device index or unique name substring; default: VERITY_INPUT_DEVICE or OS default")
    parser.add_argument("--output", help="Device index or unique name substring; default: VERITY_OUTPUT_DEVICE or OS default")
    parser.add_argument("--voice", help="Installed Windows voice name")
    parser.add_argument("--duration", type=float, default=3, help="Recording cap in seconds (0 < seconds <= 30)")
    parser.add_argument("--threshold", type=float, default=.015, help="Speech RMS threshold as a fraction of full scale (0..1)")
    parser.add_argument("--silence", type=float, default=.8, help="Trailing silence in seconds, 0.1..3")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 0 < args.duration <= 30:
        parser.error("--duration must be positive and at most 30 seconds")
    # Use the same environment defaults as the application constructor.
    import os
    if args.input is None:
        args.input = os.environ.get("VERITY_INPUT_DEVICE")
    if args.output is None:
        args.output = os.environ.get("VERITY_OUTPUT_DEVICE")
    try:
        asyncio.run(diagnose(args))
    except KeyboardInterrupt:
        pass
    except Exception as error:
        parser.exit(1, f"Voice diagnostic failed ({type(error).__name__}): {error}\n")


if __name__ == "__main__":
    main()
