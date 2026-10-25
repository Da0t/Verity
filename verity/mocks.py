"""Explicit simulated interfaces for the development scenario; no hardware claims."""
import asyncio
import io
import sys
import threading
from pathlib import Path
from PIL import Image
from verity.agents.models import result


class MockDevice:
    def __init__(self): self.events=asyncio.Queue(); self.captures=0
    async def connect(self): pass
    def gesture(self, kind='speak'): self.events.put_nowait(kind)
    async def wait_for_gesture(self): return await self.events.get()
    async def capture_jpeg(self, timeout=30):
        self.captures+=1
        buffer=io.BytesIO(); Image.new('RGB',(64,64),'white').save(buffer,format='JPEG')
        return buffer.getvalue()
    async def close(self): pass


class KeyboardDevice:
    """Real laptop stand-in for the glasses: Enter = double nod, n/b = next/back, q = quit.

    Checks use a fixed photo file when given; it is not a fresh view of the bench.
    """
    keys={'':'speak','n':'next','b':'back','q':'quit'}

    def __init__(self, photo=None, stream=None):
        self.photo=photo; self.stream=stream or sys.stdin; self.captures=0; self.events=None

    async def connect(self):
        if self.events is not None: return
        loop=asyncio.get_running_loop(); self.events=asyncio.Queue()
        def read():
            # Daemon thread: a blocked stdin read must never hold up shutdown.
            while line:=self.stream.readline():
                if (kind:=self.keys.get(line.strip().lower())): loop.call_soon_threadsafe(self.events.put_nowait,kind)
            loop.call_soon_threadsafe(self.events.put_nowait,'quit')
        threading.Thread(target=read,daemon=True).start()
        print('KEYBOARD MODE: Enter = ask a question (or interrupt), n = next step, b = previous step, q = quit.')

    async def wait_for_gesture(self): return await self.events.get()

    async def capture_jpeg(self, timeout=30):
        if not self.photo: raise RuntimeError('Keyboard mode has no camera; pass --photo to test checks')
        self.captures+=1
        return Path(self.photo).read_bytes()

    async def close(self): pass


class MockVoice:
    def __init__(self): self.questions=asyncio.Queue(); self.spoken=[]
    async def start(self): pass
    async def cue(self,kind): print(f'[MOCK cue] {kind}')
    async def listen(self, timeout=10):
        question=await self.questions.get()
        print(f'[MOCK user] {question}')
        return question
    async def speak(self,text):
        self.spoken.append(text); print(f'[MOCK Verity] {text}')
    async def stop_speaking(self): pass
    async def close(self): pass


class MockCoach:
    async def respond(self, *, question, session, capture_image):
        if 'check' in question.lower():
            await capture_image()
            return result('This is a simulated inspection. Supply a real camera image for verification.',
                          intent='check',verdict='unclear',clarify=True)
        return result('This is a simulated answer. Use the hosted coach for a real explanation.',intent='question')
    async def close(self): pass
