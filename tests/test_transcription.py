import json
import unittest
import httpx
from verity.audio.transcription import GeminiTranscriber


class TranscriptionTests(unittest.IsolatedAsyncioTestCase):
    async def test_wav_request_and_transcript_validation(self):
        async def handle(request):
            self.assertNotIn('key=',str(request.url))
            body=json.loads(request.content)
            self.assertEqual(body['contents'][0]['parts'][0]['inlineData']['mimeType'],'audio/wav')
            return httpx.Response(200,json={'candidates':[{'finishReason':'STOP',
                'content':{'parts':[{'text':'{"transcript":"Check this."}'}]}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            transcriber=GeminiTranscriber(api_key='test-key',client=client)
            self.assertEqual(await transcriber.transcribe(b'RIFFtest'), 'Check this.')
            await transcriber.close(); self.assertFalse(client.is_closed)

    async def test_invalid_output_rejected(self):
        for text in ('{"transcript":12}', '{"transcript":"ok","unexpected":true}', 'bad json'):
            async def handle(request):
                return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}]})
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                transcriber=GeminiTranscriber(api_key='test-key',client=client)
                with self.assertRaises(RuntimeError): await transcriber.transcribe(b'RIFFtest')

    async def test_api_failure_is_sanitized(self):
        async def handle(request): return httpx.Response(429,json={'key':'never-log'})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            transcriber=GeminiTranscriber(api_key='test-key',client=client)
            with self.assertRaisesRegex(RuntimeError,'HTTP 429'):
                await transcriber.transcribe(b'RIFFtest')
