"""Explicit simulated interfaces for the development scenario; no hardware claims."""
import asyncio
import io
from PIL import Image
from verity.agents.models import result


class MockDevice:
    def __init__(self): self.events=asyncio.Queue(); self.captures=0
    async def connect(self): pass
    def nod(self): self.events.put_nowait(None)
    async def wait_for_nod(self): await self.events.get()
    async def capture_jpeg(self, timeout=30):
        self.captures+=1
        buffer=io.BytesIO(); Image.new('RGB',(64,64),'white').save(buffer,format='JPEG')
        return buffer.getvalue()
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
