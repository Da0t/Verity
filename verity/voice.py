"""Voice contract: laptop microphone, hosted STT, cancellable system speech."""
import asyncio
import numpy as np
from verity.audio.io import SoundDeviceIO, wav_bytes
from verity.audio.synthesis import SystemSynthesizer


class Voice:
    def __init__(self, *, input_device=None, output_device=None, threshold=0.015,
                 audio=None, transcriber=None, synthesizer=None):
        self.audio = audio or SoundDeviceIO(input_device=input_device, output_device=output_device,
                                            threshold=threshold)
        self.transcriber = transcriber
        self.synthesizer = synthesizer or SystemSynthesizer()
        self.playback = None
        self.listening = False

    async def start(self):
        if self.transcriber is None:
            from verity.audio.transcription import GeminiTranscriber
            self.transcriber = GeminiTranscriber()
        await self.audio.start()

    async def cue(self, kind):
        frequency={'listening':880, 'working':440, 'error':220}[kind]
        t=np.arange(2205)/22050
        samples=(np.sin(2*np.pi*frequency*t)*np.hanning(len(t))*3500).astype(np.int16)
        await self._play(wav_bytes(samples, 22050))

    async def _play(self, wav):
        if self.listening: raise RuntimeError('Cannot play audio while recording')
        task=asyncio.create_task(self.audio.play(wav)); self.playback=task
        try: await task
        finally:
            if self.playback is task: self.playback=None

    async def listen(self, timeout=10.0):
        await self.stop_speaking()
        if self.listening: raise RuntimeError('Already listening')
        self.listening=True
        try:
            wav=await self.audio.record(timeout)
        finally:
            self.listening=False
        if not wav: return ''
        return await self.transcriber.transcribe(wav)

    async def speak(self, text):
        if not text.strip(): return
        if self.listening: raise RuntimeError('Cannot speak while recording')
        await self.stop_speaking()
        async def synthesize_and_play():
            wav=await self.synthesizer.synthesize(text[:1000])
            await self.audio.play(wav)
        task=asyncio.create_task(synthesize_and_play()); self.playback=task
        try: await task
        finally:
            if self.playback is task: self.playback=None

    async def stop_speaking(self):
        task=self.playback
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        if self.playback is task: self.playback=None

    async def close(self):
        await self.stop_speaking()
        await self.audio.close()
        if self.transcriber: await self.transcriber.close()
