"""Short mono recordings with energy-based end-of-utterance detection."""
import asyncio
from collections import deque
import io
import logging
import math
import time
import wave
import numpy as np

log = logging.getLogger('verity.audio')

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


def noise_threshold(wav):
    """Speech threshold from a room-noise sample: 3x its RMS, clamped to a sane range."""
    with wave.open(io.BytesIO(wav), 'rb') as source:
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2')
    rms = float(np.sqrt(np.mean((pcm.astype(np.float32)/32768)**2))) if len(pcm) else 0.0
    return min(max(3*rms, 0.01), 0.1)


class SoundDeviceIO:
    def __init__(self, *, input_device=None, output_device=None, threshold=0.015, silence=.8):
        """threshold=None calibrates from one second of room noise in start()."""
        if threshold is not None and (not math.isfinite(threshold) or not 0 < threshold <= 1):
            raise ValueError("threshold must be in (0, 1]")
        if not math.isfinite(silence) or not .1 <= silence <= 3:
            raise ValueError("silence must be between 0.1 and 3 seconds")
        self.silence = silence
        self.input_device = input_device; self.output_device = output_device
        self.threshold = threshold
        self.input_rate=16000; self.output_rate=22050
        self.input_channels=1; self.output_channels=1

    async def start(self):
        await asyncio.to_thread(self._check_settings)
        if self.threshold is None:
            # ponytail: one-shot calibration; recalibrate per activation if venue noise changes mid-session
            self.threshold = noise_threshold(await self.record(1, detect_silence=False))
            log.info('calibrated VAD threshold=%.4f', self.threshold)

    def _check_settings(self):
        import sounddevice as sd
        microphone=sd.query_devices(self.input_device, 'input')
        speaker=sd.query_devices(self.output_device, 'output')
        self.input_rate=int(microphone['default_samplerate'])
        self.output_rate=int(speaker['default_samplerate'])
        self.input_channels=min(2,int(microphone['max_input_channels']))
        self.output_channels=min(2,int(speaker['max_output_channels']))
        sd.check_input_settings(device=self.input_device, channels=self.input_channels,
                                dtype='int16', samplerate=self.input_rate)
        sd.check_output_settings(device=self.output_device, channels=self.output_channels,
                                 dtype='float32', samplerate=self.output_rate)

    async def record(self, timeout, *, detect_silence=True):
        import sounddevice as sd
        loop = asyncio.get_running_loop(); queue = asyncio.Queue(maxsize=64)
        utterance = Utterance(rate=self.input_rate, threshold=self.threshold, silence=self.silence)
        raw = []; received = False; active = True
        def deliver(value):
            if not active: return
            if queue.full():
                queue.get_nowait()
                queue.put_nowait(RuntimeError('Microphone queue overflow'))
            else: queue.put_nowait(value)
        def callback(indata, frames, timing, status):
            value = (RuntimeError('Microphone input overflow') if status else
                     indata.astype(np.int32).mean(axis=1).astype(np.int16))
            loop.call_soon_threadsafe(deliver, value)
        stream = sd.InputStream(samplerate=self.input_rate, blocksize=int(self.input_rate*0.02),
                                channels=self.input_channels,
                                dtype='int16', device=self.input_device, callback=callback)
        deadline = time.monotonic()+timeout
        try:
            stream.start()
            while True:
                remaining = deadline-time.monotonic()
                if remaining <= 0: break
                try: value = await asyncio.wait_for(queue.get(), remaining)
                except TimeoutError: break
                if isinstance(value, Exception): raise value
                received = True
                if not detect_silence: raw.append(value)
                elif utterance.feed(value): break
        finally:
            active = False
            try: stream.abort()
            finally: stream.close()
        if not received: raise RuntimeError("Microphone delivered no audio frames")
        return utterance.finish() if detect_silence else wav_bytes(np.concatenate(raw), self.input_rate)

    async def play(self, wav):
        import sounddevice as sd
        with wave.open(io.BytesIO(wav), 'rb') as source:
            if source.getsampwidth() != 2: raise ValueError('Playback requires 16-bit PCM WAV')
            rate=source.getframerate(); channels=source.getnchannels()
            samples=np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').reshape(-1,channels)
        samples = samples.astype(np.float32)/32768
        samples = samples.mean(axis=1)
        if rate != self.output_rate:
            count=max(1,round(len(samples)*self.output_rate/rate))
            samples=np.interp(np.arange(count)*rate/self.output_rate,
                              np.arange(len(samples)),samples).astype(np.float32)
        samples=np.repeat(samples[:,None],self.output_channels,axis=1)
        rate=self.output_rate; channels=self.output_channels
        failed = False
        offset = 0; loop = asyncio.get_running_loop(); done = asyncio.Event()
        def callback(outdata, frames, timing, status):
            nonlocal offset, failed
            # PortAudio can report a brief output underflow when a device starts,
            # especially for the 100 ms listening cue. Keep feeding samples;
            # a transient underflow should not abort the entire voice turn.
            failed = failed or bool(status and not status.output_underflow)
            count=min(frames, len(samples)-offset); outdata.fill(0)
            if count: outdata[:count] = samples[offset:offset+count]
            offset += count
            if offset >= len(samples): raise sd.CallbackStop
        def finished():
            loop.call_soon_threadsafe(done.set)
        stream=sd.OutputStream(samplerate=rate, channels=channels, dtype='float32',
            device=self.output_device, callback=callback,
            finished_callback=finished)
        try:
            stream.start()
            await asyncio.wait_for(done.wait(), len(samples)/rate+5)
            if failed: raise RuntimeError("Audio output underflowed")
        finally:
            try: stream.abort()
            finally: stream.close()

    async def close(self): pass


def earcon(kind):
    frequencies = {'listening': 880, 'working': 440, 'error': 220}
    if kind not in frequencies: raise ValueError(f'Unknown cue: {kind}')
    t = np.arange(2205)/22050
    samples = (np.sin(2*np.pi*frequencies[kind]*t)*np.hanning(len(t))*3500).astype(np.int16)
    return wav_bytes(samples, 22050)
