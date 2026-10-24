"""Voice contract v1. Initialization is explicit; microphone is never always on."""

import asyncio
from contextlib import suppress
import math
import os

from .audio.io import SoundDeviceIO
from .audio.transcription import GeminiTranscriber
from .audio.io import earcon
from .audio.synthesis import SystemSynthesizer


def device_setting(value):
    if value is None or value == "":
        return None
    return int(value) if isinstance(value, str) and value.isdecimal() else value


class Voice:
    def __init__(self, *, input_device=None, output_device=None, api_key=None,
                 stt_model=None, voice_name=None, threshold=.015, silence=.8,
                 max_duration=10, provider_timeout=20, audio=None,
                 transcriber=None, synthesizer=None):
        for name, value, limit in (("max_duration", max_duration, 30),
                                   ("provider_timeout", provider_timeout, 120)):
            if not math.isfinite(value) or not 0 < value <= limit:
                raise ValueError(f"{name} must be positive and at most {limit} seconds")
        self.audio = audio or SoundDeviceIO(
            input_device=device_setting(input_device if input_device is not None else os.environ.get("VERITY_INPUT_DEVICE")),
            output_device=device_setting(output_device if output_device is not None else os.environ.get("VERITY_OUTPUT_DEVICE")),
            threshold=threshold, silence=silence)
        self.transcriber = transcriber
        self.synthesizer = synthesizer or SystemSynthesizer(voice_name=voice_name)
        self._api_key = api_key
        self._stt_model = stt_model
        self.max_duration = max_duration
        self.provider_timeout = provider_timeout
        self.playback = None
        self._listening_task = None
        self.listening = False
        self._started = False
        self._closed = False

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("Voice is closed")
        if self._started:
            return
        await self.audio.start()
        if self.transcriber is None:
            self.transcriber = GeminiTranscriber(api_key=self._api_key, model=self._stt_model, timeout=self.provider_timeout)
        self._started = True

    def _ready(self):
        if not self._started or self._closed:
            raise RuntimeError("Call Voice.start() before using audio")

    async def _play(self, operation):
        self._ready()
        if self.listening or self.playback is not None:
            raise RuntimeError("Voice already has an active audio operation")
        task = asyncio.create_task(operation())
        self.playback = task
        try:
            await task
        finally:
            if self.playback is task:
                self.playback = None

    async def cue(self, kind: str) -> None:
        wav = earcon(kind)
        await self._play(lambda: self.audio.play(wav))

    async def listen(self, timeout: float = 10.0) -> str:
        self._ready()
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Listening timeout must be positive")
        if self.listening:
            raise RuntimeError("Voice is already listening")
        # Reserve input before stopping output so concurrent callers cannot enter.
        task = asyncio.create_task(self._listen(min(timeout, self.max_duration)))
        self._listening_task = task
        self.listening = True
        try:
            return await task
        finally:
            if self._listening_task is task:
                self._listening_task = None
                self.listening = False

    async def _listen(self, duration):
        await self.stop_speaking()
        wav = await self.audio.record(duration)
        if not wav:
            return ""
        async with asyncio.timeout(self.provider_timeout):
            transcript = await self.transcriber.transcribe(wav)
        if not isinstance(transcript, str):
            raise RuntimeError("Transcriber must return text")
        return transcript.strip()

    async def speak(self, text: str) -> None:
        if not isinstance(text, str) or len(text) > 4000:
            raise ValueError("Speech must be text of at most 4000 characters")
        self._ready()
        if not text.strip():
            return
        async def output():
            wav = await self.synthesizer.synthesize(text.strip())
            await self.audio.play(wav)
        await self._play(output)

    async def stop_speaking(self) -> None:
        task = self.playback
        if task is not None:
            if not task.cancelling():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            if self.playback is task:
                self.playback = None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            tasks = [task for task in (self.playback, self._listening_task) if task is not None]
            for task in tasks:
                if not task.cancelling():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            try:
                await self.audio.close()
            finally:
                if self.transcriber is not None:
                    await self.transcriber.close()
                self._started = False
