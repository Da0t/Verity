import asyncio
import io
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave
import numpy as np
from verity.audio.io import SoundDeviceIO, noise_threshold, wav_bytes


class AudioIOTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_rates_and_stereo_mic_downmix(self):
        calls=[]
        class Input:
            def __init__(self,**kwargs): self.options=kwargs
            def start(self):
                block=int(self.options['samplerate']*.02)
                for amplitude in [2000]*10+[0]*45:
                    self.options['callback'](np.full((block,2),amplitude,dtype=np.int16),block,None,False)
            def abort(self): calls.append('abort')
            def close(self): calls.append('close')
        fake=SimpleNamespace(query_devices=lambda *args: {'default_samplerate':48000,
            'max_input_channels':2,'max_output_channels':2}, check_input_settings=Mock(),
            check_output_settings=Mock(),InputStream=Input)
        with patch.dict(sys.modules,{'sounddevice':fake}):
            audio=SoundDeviceIO(); await audio.start(); wav=await audio.record(timeout=1)
        with wave.open(io.BytesIO(wav),'rb') as source:
            self.assertEqual(source.getframerate(),48000)
            self.assertEqual(source.getnchannels(),1)
        self.assertEqual(calls,['abort','close'])
        self.assertEqual(fake.check_input_settings.call_args.kwargs['samplerate'],48000)

    async def test_cancel_recording_closes_stream(self):
        calls=[]
        class Input:
            def __init__(self,**kwargs): pass
            def start(self): pass
            def abort(self): calls.append('abort')
            def close(self): calls.append('close')
        with patch.dict(sys.modules,{'sounddevice':SimpleNamespace(InputStream=Input)}):
            task=asyncio.create_task(SoundDeviceIO().record(10))
            await asyncio.sleep(0); task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(calls,['abort','close'])

    async def test_playback_adapts_rate_and_channels(self):
        calls=[]
        class Stop(Exception): pass
        class Output:
            def __init__(self,**kwargs): self.options=kwargs; calls.append(kwargs)
            def start(self):
                try:
                    for _ in range(20):
                        data=np.empty((1024,self.options['channels']),dtype=np.float32)
                        self.options['callback'](data,1024,None,False)
                except Stop: self.options['finished_callback']()
            def abort(self): calls.append('abort')
            def close(self): calls.append('close')
        fake=SimpleNamespace(OutputStream=Output,CallbackStop=Stop)
        with patch.dict(sys.modules,{'sounddevice':fake}):
            audio=SoundDeviceIO(); audio.output_rate=48000; audio.output_channels=2
            await audio.play(wav_bytes(np.full(1600,2000,dtype=np.int16),16000))
        self.assertEqual(calls[0]['samplerate'],48000)
        self.assertEqual(calls[0]['channels'],2)
        self.assertEqual(calls[-2:],['abort','close'])

    async def test_playback_survives_transient_output_underflow(self):
        class Stop(Exception): pass
        class Status:
            output_underflow = True
            def __bool__(self): return True
        class Output:
            def __init__(self, **options): self.options = options
            def start(self):
                try:
                    self.options['callback'](np.empty((1024,1), dtype=np.float32),
                                             1024, None, Status())
                except Stop:
                    self.options['finished_callback']()
            def abort(self): pass
            def close(self): pass
        fake = SimpleNamespace(OutputStream=Output, CallbackStop=Stop)
        with patch.dict(sys.modules, {'sounddevice': fake}):
            await SoundDeviceIO().play(wav_bytes(np.ones(320, dtype=np.int16)))

    async def test_auto_threshold_calibrates_from_room_noise(self):
        self.assertEqual(noise_threshold(wav_bytes(np.zeros(1600,dtype=np.int16))),0.01)
        self.assertEqual(noise_threshold(wav_bytes(np.full(1600,30000,dtype=np.int16))),0.1)
        audio=SoundDeviceIO(threshold=None); audio._check_settings=lambda: None
        async def noise(timeout, detect_silence=True):
            self.assertFalse(detect_silence)
            return wav_bytes(np.full(1600,1000,dtype=np.int16))
        audio.record=noise
        await audio.start()
        self.assertAlmostEqual(audio.threshold,3*1000/32768,places=4)
