import asyncio
import unittest
from unittest.mock import AsyncMock
import numpy as np
from verity.audio.io import Utterance
from verity.voice import Voice


class VoiceTests(unittest.IsolatedAsyncioTestCase):
    async def make(self):
        audio=type('Audio', (), {})()
        audio.start=AsyncMock(); audio.close=AsyncMock()
        audio.record=AsyncMock(return_value=b'wav'); audio.play=AsyncMock()
        transcriber=type('STT', (), {})()
        transcriber.transcribe=AsyncMock(return_value='check this'); transcriber.close=AsyncMock()
        synthesizer=type('TTS', (), {})(); synthesizer.synthesize=AsyncMock(return_value=b'wav')
        voice=Voice(audio=audio,transcriber=transcriber,synthesizer=synthesizer)
        await voice.start(); self.addAsyncCleanup(voice.close)
        return voice

    async def test_record_then_transcribe(self):
        voice=await self.make()
        self.assertEqual(await voice.listen(), 'check this')
        voice.transcriber.transcribe.assert_awaited_once_with(b'wav')

    async def test_silence_skips_api(self):
        voice=await self.make(); voice.audio.record.return_value=None
        self.assertEqual(await voice.listen(), '')
        voice.transcriber.transcribe.assert_not_awaited()

    async def test_playback_can_be_interrupted(self):
        voice=await self.make()
        async def slow(wav): await asyncio.sleep(10)
        voice.audio.play=slow
        task=asyncio.create_task(voice.speak('Long answer'))
        await asyncio.sleep(0.01)
        await asyncio.wait_for(voice.stop_speaking(),0.1)
        with self.assertRaises(asyncio.CancelledError): await task

    async def test_cancel_during_synthesis(self):
        voice=await self.make()
        async def slow(text): await asyncio.sleep(10)
        voice.synthesizer.synthesize=slow
        task=asyncio.create_task(voice.speak('Long answer'))
        await asyncio.sleep(0.01); await voice.stop_speaking()
        with self.assertRaises(asyncio.CancelledError): await task
        voice.audio.play.assert_not_awaited()

    async def test_cues_are_wav(self):
        voice=await self.make(); await voice.cue('listening')
        self.assertTrue(voice.audio.play.call_args.args[0].startswith(b'RIFF'))

    async def test_record_failure_releases_listening_flag(self):
        voice=await self.make(); voice.audio.record.side_effect=RuntimeError('microphone')
        with self.assertRaises(RuntimeError): await voice.listen()
        self.assertFalse(voice.listening)

    async def test_no_simultaneous_playback_and_recording(self):
        voice=await self.make(); voice.listening=True
        with self.assertRaises(RuntimeError): await voice.speak('hello')
        voice.listening=False


class UtteranceTests(unittest.TestCase):
    def test_speech_then_silence(self):
        utterance=Utterance(silence=0.1)
        self.assertFalse(utterance.feed(np.zeros(320,dtype=np.int16)))
        for _ in range(10): self.assertFalse(utterance.feed(np.full(320,2000,dtype=np.int16)))
        done=False
        for _ in range(6): done=utterance.feed(np.zeros(320,dtype=np.int16))
        self.assertTrue(done)
        self.assertTrue(utterance.finish().startswith(b'RIFF'))

    def test_background_silence_is_empty(self):
        utterance=Utterance()
        for _ in range(100): utterance.feed(np.zeros(320,dtype=np.int16))
        self.assertIsNone(utterance.finish())

    def test_click_is_not_an_utterance(self):
        utterance=Utterance()
        utterance.feed(np.full(320,5000,dtype=np.int16))
        for _ in range(50): utterance.feed(np.zeros(320,dtype=np.int16))
        self.assertIsNone(utterance.finish())
