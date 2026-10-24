"""Explicit live synthetic speech test; no microphone, BLE hardware or speaker used."""
import asyncio
import io
import time
from PIL import Image
from verity.agents.coach import Coach
from verity.audio.synthesis import SystemSynthesizer
from verity.audio.transcription import GeminiTranscriber
from verity.voice import Voice
from verity.session import Session
from verity.mocks import MockDevice


async def main():
    synth=SystemSynthesizer()
    question='Check this.'
    wav=await synth.synthesize(question)
    class SyntheticAudio:
        spoken_wavs=0
        async def start(self): pass
        async def record(self, timeout): return wav
        async def play(self, data):
            if not data.startswith(b'RIFF'): raise ValueError('Invalid playback WAV')
            self.spoken_wavs+=1
        async def close(self): pass
    audio=SyntheticAudio()
    voice=Voice(audio=audio, transcriber=GeminiTranscriber(), synthesizer=synth)
    device=MockDevice(); coach=Coach()
    session=Session(device,voice,coach,{'recipe_id':'diagnostic','steps':[{
        'id':'connector','instruction':'Inspect the labeled connector.',
        'expected':'Connector fully seated in its matching labeled socket.'}]},cooldown=0)
    # Real STT + Coach + TTS; synthetic double nod, microphone, blank camera and playback sink.
    task=asyncio.create_task(session.run())
    started=time.monotonic()
    try:
        device.gesture()
        async with asyncio.timeout(60):
            await session.turn_started.wait(); await session.idle.wait()
        observation=session.data['last_observation']
        if not observation or observation['verdict']!='unclear':
            raise RuntimeError('Live diagnostic did not return expected uncertainty for blank image')
        if device.captures!=1 or audio.spoken_wavs<3:
            raise RuntimeError('Missing capture or synthesized playback')
        print('PASS: synthetic double nod → real speech transcription → real coach image check → real synthesized WAV.')
        print('Answer:', session.last_answer)
        print(f'Elapsed: {time.monotonic()-started:.1f}s; capture count: {device.captures}.')
        print('Hardware inputs/output were simulated; this does not verify an actual circuit or Windows headset.')
    finally:
        session.stop.set()
        await task


if __name__=='__main__':
    asyncio.run(main())
