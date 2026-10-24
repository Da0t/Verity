"""Offline system TTS, isolated in cancellable subprocesses, with no shell interpolation."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile


class SystemSynthesizer:
    async def synthesize(self, text):
        with tempfile.TemporaryDirectory(prefix='verity-tts-') as directory:
            wav = Path(directory)/'speech.wav'
            if sys.platform == 'win32':
                script = '''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$p = [Console]::In.ReadToEnd() | ConvertFrom-Json
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SetOutputToWaveFile($p.path); $s.Speak($p.text) } finally { $s.Dispose() }
'''
                await self._run('powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script,
                                data=json.dumps({'text': text, 'path': str(wav)}).encode('utf-8'))
            elif sys.platform == 'darwin':
                source = Path(directory)/'text.txt'; source.write_text(text, encoding='utf-8')
                aiff = Path(directory)/'speech.aiff'
                await self._run('/usr/bin/say', '-f', str(source), '-o', str(aiff))
                await self._run('/usr/bin/afconvert', '-f', 'WAVE', '-d', 'LEI16', str(aiff), str(wav))
            else:
                raise RuntimeError('System speech supports Windows and macOS; inject another synthesizer on Linux')
            return wav.read_bytes()

    async def _run(self, *args, data=None):
        process = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE if data else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try:
            async with asyncio.timeout(20):
                await process.communicate(data)
            if process.returncode:
                raise RuntimeError('System speech synthesis failed')
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
