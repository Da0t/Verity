"""One-turn-at-a-time session controller for head gestures, voice, camera and coach."""
import asyncio
import copy
import logging
import time
from verity.agents.coach import snapshot
from verity.agents.models import Result, result

log = logging.getLogger('verity.session')


class Session:
    def __init__(self, device, voice, coach, recipe, *, turn_timeout=60, cooldown=0.35):
        self.device=device; self.voice=voice; self.coach=coach
        self.data=snapshot({**recipe, 'step_index':0, 'history':[]})
        self.data['last_observation']=None
        self.state='IDLE'; self.last_answer=''; self.turn_timeout=turn_timeout
        self.cooldown=cooldown; self.last_activation=float('-inf')
        self.turn_id=0; self.task=None; self.stop=asyncio.Event()
        self.idle=asyncio.Event(); self.idle.set()
        self.turn_started=asyncio.Event()

    def transition(self, state):
        self.state=state
        log.info('state=%s turn=%s',state,self.turn_id)

    async def _cancel(self):
        self.turn_id+=1
        if self.task and not self.task.done():
            self.task.cancel()
            done,_=await asyncio.wait([self.task],timeout=2)
            if not done: raise RuntimeError('Previous turn did not stop; refusing concurrent execution')
        if self.task:
            await asyncio.gather(self.task,return_exceptions=True)
        self.task=None
        await self.voice.stop_speaking()

    async def activate(self, question=None):
        """Start a turn. question=None listens (double nod); 'next'/'back' navigate without listening."""
        now=time.monotonic()
        if (question is None and self.state=='LISTENING') or now-self.last_activation < self.cooldown: return
        self.last_activation=now
        await self._cancel()
        self.idle.clear(); self.turn_started.set()
        self.task=asyncio.create_task(self._turn(self.turn_id,question))

    async def run(self):
        gesture=stopper=None
        try:
            async with asyncio.timeout(15): await self.voice.start()
            async with asyncio.timeout(30): await self.device.connect()
            log.info('ready: double nod to speak, double left/right for previous/next step')
            stopper=asyncio.create_task(self.stop.wait())
            gesture=asyncio.create_task(self.device.wait_for_gesture())
            while not self.stop.is_set():
                done,_=await asyncio.wait([gesture,stopper],return_when=asyncio.FIRST_COMPLETED)
                if stopper in done: break
                kind=await gesture  # propagate disconnection, never spin on a failed waiter
                await self.activate(None if kind=='speak' else kind)
                gesture=asyncio.create_task(self.device.wait_for_gesture())
        finally:
            for task in (gesture,stopper):
                if task: task.cancel()
            await asyncio.gather(*(t for t in (gesture,stopper) if t),return_exceptions=True)
            try: await self._cancel()
            finally:
                # Close every resource even if another cleanup fails.
                for component in (self.device,self.voice,self.coach):
                    try:
                        async with asyncio.timeout(5): await component.close()
                    except Exception as exc: log.error('cleanup failed: %s',type(exc).__name__)
                self.transition('IDLE'); self.idle.set()

    def local(self, question):
        normalized=question.lower().strip().rstrip('.!?')
        if normalized in ('quit','exit','end session'):
            self.stop.set(); return result('Session ended.',intent='stop')
        if normalized in ('stop','cancel'): return result('Stopped.',intent='stop')
        if normalized in ('repeat','say that again'):
            return result(self.last_answer or 'There is no previous answer to repeat.',intent='repeat')
        if normalized in ('what next','what is the next step',"what's next",'what should i do','current step'):
            return result(self.data['steps'][self.data['step_index']]['instruction'][:600],intent='question')
        if normalized in ('next','next step'):
            index=self.data['step_index']+1
            if index >= len(self.data['steps']): return result('You are on the last step.',intent='next')
            output=result(self.data['steps'][index]['instruction'][:600],intent='next')
            output['suggested_step_index']=index
            return output
        if normalized in ('back','go back','previous','previous step'):
            index=self.data['step_index']-1
            if index < 0: return result('You are on the first step.',intent='back')
            output=result(self.data['steps'][index]['instruction'][:600],intent='back')
            output['suggested_step_index']=index
            return output
        return None

    async def _turn(self, serial, question=None):
        captured=False
        async def capture():
            nonlocal captured
            if serial != self.turn_id: raise asyncio.CancelledError
            self.transition('CAPTURING')
            try:
                image=await self.device.capture_jpeg()
                if serial != self.turn_id: raise asyncio.CancelledError
                captured=True
                return image
            finally:
                if serial==self.turn_id: self.transition('THINKING')
        try:
            async with asyncio.timeout(self.turn_timeout):
                if question is None:
                    self.transition('LISTENING')
                    await self.voice.cue('listening')
                    question=(await self.voice.listen(timeout=10)).strip()
                if not question: return
                if serial != self.turn_id: return
                output=self.local(question)
                if output is None:
                    self.transition('THINKING')
                    await self.voice.cue('working')
                    output=await self.coach.respond(question=question,session=copy.deepcopy(self.data),
                                                    capture_image=capture)
                if serial != self.turn_id: return
                validated=Result.model_validate(output).model_dump()
                next_index=validated['suggested_step_index']
                step={'next':1,'back':-1}.get(validated['intent'])
                if next_index is not None and (step is None or
                        not (next_index == self.data['step_index']+step and 0 <= next_index < len(self.data['steps']))):
                    raise ValueError('Invalid step change')
                if validated['verdict'] in ('pass','issue') and not captured:
                    raise ValueError('Visual result without capture')
                self.transition('SPEAKING')
                await self.voice.speak(validated['speech'])
                if serial != self.turn_id: return
                if next_index is not None: self.data['step_index']=next_index
                self.last_answer=validated['speech']
                self.data['history']=(self.data['history']+[
                    {'role':'user','text':question}, {'role':'assistant','text':self.last_answer}])[-8:]
                if validated['verdict']!='not_checked': self.data['last_observation']=validated
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning('turn failed: %s',type(exc).__name__)
            if serial==self.turn_id:
                self.transition('SPEAKING')
                try:
                    async with asyncio.timeout(10):
                        await self.voice.cue('error')
                        await self.voice.speak('I could not complete that request. Please double nod and try again.')
                except Exception: log.error('Could not play error feedback')
        finally:
            if serial==self.turn_id:
                self.transition('IDLE'); self.idle.set()
