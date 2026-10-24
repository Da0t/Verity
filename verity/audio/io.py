"""Short mono recordings with energy-based end-of-utterance detection."""
import asyncio
from collections import deque
import io
import time
import wave
import numpy as np


def wav_bytes(pcm, rate=16000):
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setnchannels(1); target.setsampwidth(2); target.setframerate(rate)
        target.writeframes(np.asarray(pcm, dtype='<i2').tobytes())
    return output.getvalue()


class Utterance:
    def __init__(self, rate=16000, threshold=0.015, silence=0.8, min_speech=0.12):
        self.rate = rate; self.threshold = threshold
        self.silence = silence; self.min_speech = min_speech
        self.pre = deque(maxlen=10)
        self.frames = []; self.voiced = 0; self.quiet = 0

    def feed(self, samples):
        samples = np.asarray(samples, dtype=np.int16).reshape(-1)
        duration = len(samples)/self.rate
        loud = np.sqrt(np.mean((samples.astype(np.float32)/32768)**2)) >= self.threshold
        if not self.frames:
            self.pre.append(samples.copy())
            if not loud: return False
            self.frames.extend(self.pre); self.pre.clear()
        else:
            self.frames.append(samples.copy())
        if loud:
            self.voiced += duration; self.quiet = 0
        else: self.quiet += duration
        return self.voiced >= self.min_speech and self.quiet >= self.silence

    def finish(self):
        if self.voiced < self.min_speech: return None
        return wav_bytes(np.concatenate(self.frames), self.rate)


class SoundDeviceIO:
    def __init__(self, *, input_device=None, output_device=None, threshold=0.015):
        self.input_device = input_device; self.output_device = output_device
        self.threshold = threshold

    async def start(self):
        import sounddevice as sd
        sd.check_input_settings(device=self.input_device, channels=1, dtype='int16', samplerate=16000)
        sd.check_output_settings(device=self.output_device, channels=1, dtype='float32', samplerate=22050)

    async def record(self, timeout):
        import sounddevice as sd
        loop = asyncio.get_running_loop(); queue = asyncio.Queue(maxsize=64)
        utterance = Utterance(threshold=self.threshold)
        def deliver(value):
            if queue.full():
                queue.get_nowait()
                queue.put_nowait(RuntimeError('Microphone queue overflow'))
            else: queue.put_nowait(value)
        def callback(indata, frames, timing, status):
            value = RuntimeError('Microphone input overflow') if status else indata.copy()
            loop.call_soon_threadsafe(deliver, value)
        stream = sd.InputStream(samplerate=16000, blocksize=320, channels=1,
                                dtype='int16', device=self.input_device, callback=callback)
        stream.start()
        deadline = time.monotonic()+timeout
        try:
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0: break
                try: value = await asyncio.wait_for(queue.get(), remaining)
                except TimeoutError: break
                if isinstance(value, Exception): raise value
                if utterance.feed(value): break
        finally:
            stream.abort(); stream.close()
        return utterance.finish()

    async def play(self, wav):
        import sounddevice as sd
        with wave.open(io.BytesIO(wav), 'rb') as source:
            if source.getsampwidth() != 2: raise ValueError('Playback requires 16-bit PCM WAV')
            rate=source.getframerate(); channels=source.getnchannels()
            samples=np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').reshape(-1,channels)
        samples = samples.astype(np.float32)/32768
        offset = 0; loop = asyncio.get_running_loop(); done = asyncio.Event()
        def callback(outdata, frames, timing, status):
            nonlocal offset
            count=min(frames, len(samples)-offset); outdata.fill(0)
            if count: outdata[:count] = samples[offset:offset+count]
            offset += count
            if offset >= len(samples): raise sd.CallbackStop
        stream=sd.OutputStream(samplerate=rate, channels=channels, dtype='float32',
            device=self.output_device, callback=callback,
            finished_callback=lambda: loop.call_soon_threadsafe(done.set))
        stream.start()
        try:
            await asyncio.wait_for(done.wait(), len(samples)/rate+5)
        finally:
            stream.abort(); stream.close()

    async def close(self): pass
