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


class NativeCallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_completion_callback_returns_none_for_portaudio(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        from verity.audio.io import SoundDeviceIO, wav_bytes
        observed = []
        class Stop(Exception): pass
        class Output:
            def __init__(self, **options): self.options = options
            def start(self):
                try:
                    self.options['callback'](np.zeros((4096, 1), dtype=np.float32), 4096, None, False)
                except Stop:
                    observed.append(self.options['finished_callback']())
            def abort(self): pass
            def close(self): pass
        with patch.dict(sys.modules, {'sounddevice': SimpleNamespace(OutputStream=Output, CallbackStop=Stop)}):
            await SoundDeviceIO().play(wav_bytes(np.ones(320, dtype=np.int16)))
        self.assertEqual(observed, [None])


# Lifecycle and hosted-provider checks from the isolated Windows acceptance work.
import base64
from contextlib import suppress
import json
import os
from unittest.mock import patch
from verity.audio.io import wav_bytes, earcon
from verity.audio.transcription import GeminiTranscriber
from verity.audio.synthesis import SystemSynthesizer as WindowsSpeech

def frame(level=0):
    return np.tile(np.array([level, -level], dtype=np.int16), 160)

class FakeAudio:

    def __init__(self):
        self.events = []
        self.wav = wav_bytes(frame(2000))
        self.playing = asyncio.Event()
        self.recording = asyncio.Event()
        self.hold_play = False
        self.hold_record = False

    async def start(self):
        self.events.append('start')

    async def play(self, wav):
        self.events.append('play')
        self.playing.set()
        try:
            if self.hold_play:
                await asyncio.Event().wait()
        finally:
            self.events.append('output_closed')

    async def record(self, duration):
        self.events.append(('record', duration))
        self.recording.set()
        try:
            if self.hold_record:
                await asyncio.Event().wait()
            return self.wav
        finally:
            self.events.append('input_closed')

    async def close(self):
        self.events.append('audio_closed')

class FakeTranscriber:

    def __init__(self):
        self.calls = []
        self.closed = False
        self.hold = False
        self.entered = asyncio.Event()
        self.cancelled = False

    async def transcribe(self, wav):
        self.calls.append(wav)
        self.entered.set()
        try:
            if self.hold:
                await asyncio.Event().wait()
            return '  check this  '
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def close(self):
        self.closed = True

class FakeSpeech:

    def __init__(self):
        self.hold = False
        self.entered = asyncio.Event()
        self.cancelled = False

    async def synthesize(self, text):
        self.entered.set()
        try:
            if self.hold:
                await asyncio.Event().wait()
            return earcon('working')
        except asyncio.CancelledError:
            self.cancelled = True
            raise

class AdditionalVoiceTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.audio = FakeAudio()
        self.stt = FakeTranscriber()
        self.speech = FakeSpeech()
        self.voice = Voice(audio=self.audio, transcriber=self.stt, synthesizer=self.speech, provider_timeout=0.05)
        await self.voice.start()

    async def asyncTearDown(self):
        await self.voice.close()

    async def test_contract_and_cue_before_recording(self):
        await self.voice.cue('listening')
        self.assertEqual(await self.voice.listen(), 'check this')
        self.assertLess(self.audio.events.index('output_closed'), self.audio.events.index(('record', 10)))
        self.assertEqual(self.stt.calls, [self.audio.wav])

    async def test_empty_audio_does_not_upload(self):
        self.audio.wav = b''
        self.assertEqual(await self.voice.listen(), '')
        self.assertEqual(self.stt.calls, [])

    async def test_recording_duration_is_capped(self):
        await self.voice.listen(timeout=100)
        self.assertIn(('record', 10), self.audio.events)

    async def test_stop_interrupts_playback_before_recording(self):
        self.audio.hold_play = True
        task = asyncio.create_task(self.voice.speak('a long answer'))
        await self.audio.playing.wait()
        self.assertEqual(await self.voice.listen(), 'check this')
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertLess(self.audio.events.index('output_closed'), self.audio.events.index(('record', 10)))

    async def test_stop_interrupts_synthesis_without_late_playback(self):
        self.speech.hold = True
        task = asyncio.create_task(self.voice.speak('a long answer'))
        await self.speech.entered.wait()
        await asyncio.wait_for(self.voice.stop_speaking(), 0.2)
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.speech.cancelled)
        self.assertNotIn('play', self.audio.events)

    async def test_provider_timeout_cancels_request(self):
        self.stt.hold = True
        with self.assertRaises(TimeoutError):
            await self.voice.listen()
        self.assertTrue(self.stt.cancelled)
        self.stt.hold = False
        self.assertEqual(await self.voice.listen(), 'check this')

    async def test_close_cancels_recording_and_closes_provider(self):
        self.audio.hold_record = True
        task = asyncio.create_task(self.voice.listen())
        await self.audio.recording.wait()
        await self.voice.close()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertIn('input_closed', self.audio.events)
        self.assertTrue(self.stt.closed)
        with self.assertRaises(RuntimeError):
            await self.voice.start()

    async def test_close_cancels_active_provider(self):
        self.stt.hold = True
        task = asyncio.create_task(self.voice.listen())
        await self.stt.entered.wait()
        await self.voice.close()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.stt.cancelled)
        self.assertTrue(self.stt.closed)

    async def test_no_output_or_second_listen_while_microphone_open(self):
        self.audio.hold_record = True
        task = asyncio.create_task(self.voice.listen())
        await self.audio.recording.wait()
        for operation in (self.voice.listen(), self.voice.speak('hello'), self.voice.cue('working')):
            with self.assertRaises(RuntimeError):
                await operation
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def test_cancelled_listener_cancels_provider_and_recovers(self):
        self.stt.hold = True
        task = asyncio.create_task(self.voice.listen())
        await self.stt.entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(self.stt.cancelled)
        self.stt.hold = False
        self.assertEqual(await self.voice.listen(), 'check this')

    async def test_device_failure_surfaces_and_recovers(self):
        with patch.object(self.audio, 'record', side_effect=RuntimeError('device lost')):
            with self.assertRaisesRegex(RuntimeError, 'device lost'):
                await self.voice.listen()
        self.assertEqual(await self.voice.listen(), 'check this')

    async def test_not_started_and_invalid_settings(self):
        voice = Voice(audio=self.audio, transcriber=self.stt)
        with self.assertRaises(RuntimeError):
            await voice.listen()
        for duration in (-1, 0, float('nan'), 31):
            with self.assertRaises(ValueError):
                Voice(max_duration=duration)
        with self.assertRaises(ValueError):
            await self.voice.listen(timeout=0)

@unittest.skipUnless(os.name == 'nt', 'Windows process lifecycle')
class WindowsSpeechTests(unittest.IsolatedAsyncioTestCase):

    async def test_cancellation_kills_and_reaps_synthesizer(self):
        entered = asyncio.Event()

        class Process:
            returncode = None
            waited = False

            async def communicate(self, text):
                entered.set()
                await asyncio.Event().wait()

            def kill(self):
                self.returncode = -9

            async def wait(self):
                self.waited = True
        process = Process()
        with patch('asyncio.create_subprocess_exec', AsyncMock(return_value=process)):
            task = asyncio.create_task(WindowsSpeech().synthesize('hello'))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(process.returncode, -9)
        self.assertTrue(process.waited)

    async def test_cancellation_during_process_creation_reaps_child(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        class Process:
            returncode = None
            waited = False

            def kill(self):
                self.returncode = -9

            async def wait(self):
                self.waited = True
        process = Process()

        async def launch(*args, **kwargs):
            entered.set()
            await release.wait()
            return process
        with patch('asyncio.create_subprocess_exec', launch):
            task = asyncio.create_task(WindowsSpeech().synthesize('hello'))
            await entered.wait()
            task.cancel()
            release.set()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(process.returncode, -9)
        self.assertTrue(process.waited)

class ProviderTests(unittest.IsolatedAsyncioTestCase):

    async def make_provider(self, handler):
        import httpx
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        provider = GeminiTranscriber(api_key='test-secret', model='gemini-3.1-flash-lite', client=client)
        self.addAsyncCleanup(client.aclose)
        self.addAsyncCleanup(provider.close)
        return provider

    async def test_audio_payload_and_stripped_transcript(self):
        import httpx
        wav = wav_bytes(frame(2000))

        def handler(request):
            self.assertEqual(request.headers['x-goog-api-key'], 'test-secret')
            self.assertNotIn('test-secret', str(request.url))
            payload = json.loads(request.content)
            audio = payload['contents'][0]['parts'][0]['inlineData']
            self.assertEqual(audio['mimeType'], 'audio/wav')
            self.assertEqual(base64.b64decode(audio['data']), wav)
            return httpx.Response(200, json={'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"transcript": "  check this  "}'}]}}]})
        provider = await self.make_provider(handler)
        self.assertEqual(await provider.transcribe(wav), 'check this')

    async def test_failed_or_malformed_responses_do_not_leak_details(self):
        import httpx
        for status, body in ((401, {'error': 'test-secret'}), (200, {}), (200, {'candidates': [{'finishReason': 'MAX_TOKENS'}]}), (200, {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"transcript": 123}'}]}}]})):
            provider = await self.make_provider(lambda request: httpx.Response(status, json=body))
            with self.assertRaises(RuntimeError) as raised:
                await provider.transcribe(wav_bytes(frame()))
            self.assertNotIn('test-secret', str(raised.exception))

    async def test_missing_credentials_and_invalid_model_fail_locally(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'GEMINI_API_KEY'):
                GeminiTranscriber()
        for model in ('models/test', '../test', 'test?key=secret'):
            with self.assertRaises(ValueError):
                GeminiTranscriber(api_key='test', model=model)

    async def test_network_errors_are_actionable(self):
        import httpx
        for failure, expected in ((httpx.ReadTimeout, TimeoutError), (httpx.ConnectError, ConnectionError)):

            def handler(request):
                raise failure('private provider details', request=request)
            provider = await self.make_provider(handler)
            with self.assertRaises(expected) as raised:
                await provider.transcribe(wav_bytes(frame()))
            self.assertNotIn('private provider details', str(raised.exception))
