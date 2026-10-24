import asyncio
import unittest
from verity.session import Session
from verity.mocks import MockDevice, MockVoice, MockCoach
from verity.agents.models import result


def recipe():
    return {'recipe_id':'test','steps':[
        {'id':'one','instruction':'First instruction.','expected':'First visible connection.'},
        {'id':'two','instruction':'Second instruction.','expected':'Second visible connection.'}]}


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def make(self, coach=None, timeout=1):
        device=MockDevice(); voice=MockVoice()
        controller=Session(device,voice,coach or MockCoach(),recipe(),cooldown=0,turn_timeout=timeout)
        self.addAsyncCleanup(controller._cancel)
        return controller,device,voice

    async def turn(self, controller, voice, question):
        voice.questions.put_nowait(question)
        await controller.activate()
        await asyncio.wait_for(controller.idle.wait(),1)

    async def test_local_commands_and_manual_progression(self):
        controller,device,voice=await self.make()
        await self.turn(controller,voice,'what is the next step')
        self.assertEqual(voice.spoken[-1],'First instruction.')
        self.assertEqual(controller.data['step_index'],0)
        await self.turn(controller,voice,'next')
        self.assertEqual(controller.data['step_index'],1)
        await self.turn(controller,voice,'repeat')
        self.assertEqual(voice.spoken[-1],'Second instruction.')
        self.assertEqual(device.captures,0)

    async def test_gesture_navigation_skips_listening(self):
        controller,_,voice=await self.make()
        for kind,index,spoken in [('back',0,'You are on the first step.'),('next',1,'Second instruction.'),
                                  ('next',1,'You are on the last step.'),('back',0,'First instruction.')]:
            await controller.activate(kind); await asyncio.wait_for(controller.idle.wait(),1)
            self.assertEqual((controller.data['step_index'],voice.spoken[-1]),(index,spoken))
        self.assertTrue(voice.questions.empty())
        await self.turn(controller,voice,'repeat')
        self.assertEqual(voice.spoken[-1],'First instruction.')

    async def test_gesture_interrupts_listening(self):
        controller,_,voice=await self.make()
        await controller.activate(); await asyncio.sleep(0)
        self.assertEqual(controller.state,'LISTENING')
        await controller.activate('next'); await asyncio.wait_for(controller.idle.wait(),1)
        self.assertEqual((controller.data['step_index'],voice.spoken),(1,['Second instruction.']))

    async def test_gesture_loop_routes_kinds(self):
        controller,device,voice=await self.make()
        task=asyncio.create_task(controller.run())
        device.gesture('next')
        await asyncio.wait_for(controller.turn_started.wait(),1)
        await controller.idle.wait()
        controller.stop.set(); await task
        self.assertEqual((controller.data['step_index'],voice.spoken),(1,['Second instruction.']))

    async def test_check_invokes_capture(self):
        controller,device,voice=await self.make()
        await self.turn(controller,voice,'check this')
        self.assertEqual(device.captures,1)
        self.assertEqual(controller.data['last_observation']['verdict'],'unclear')
        self.assertEqual(controller.data['step_index'],0)

    async def test_silence_returns_idle(self):
        controller,_,voice=await self.make()
        await self.turn(controller,voice,'')
        self.assertEqual(controller.state,'IDLE')
        self.assertFalse(voice.spoken)

    async def test_repeated_nod_ignored_while_listening(self):
        controller,_,voice=await self.make()
        await controller.activate(); await asyncio.sleep(0)
        task=controller.task
        await controller.activate()
        self.assertIs(controller.task,task)
        voice.questions.put_nowait('stop')
        await controller.idle.wait()

    async def test_thinking_interruption_discards_old_answer(self):
        started=asyncio.Event()
        class Slow:
            async def respond(self,**kwargs):
                started.set()
                # Simulate an SDK that delivers a late response after cancellation.
                try: await asyncio.sleep(10)
                except asyncio.CancelledError: return result('STALE ANSWER',intent='question')
            async def close(self): pass
        controller,_,voice=await self.make(Slow())
        voice.questions.put_nowait('question')
        await controller.activate(); await started.wait()
        voice.questions.put_nowait('stop')
        await controller.activate(); await controller.idle.wait()
        self.assertNotIn('STALE ANSWER',voice.spoken)
        self.assertEqual(voice.spoken[-1],'Stopped.')

    async def test_speaking_interruption(self):
        controller,_,voice=await self.make()
        started=asyncio.Event(); original=voice.speak
        async def slow(text):
            if text=='First instruction.':
                started.set(); await asyncio.sleep(10)
            await original(text)
        voice.speak=slow
        voice.questions.put_nowait('current step')
        await controller.activate(); await started.wait()
        voice.questions.put_nowait('stop')
        await controller.activate(); await controller.idle.wait()
        self.assertEqual(voice.spoken,['Stopped.'])

    async def test_timeout_returns_idle_with_spoken_error(self):
        class Slow:
            async def respond(self,**kwargs): await asyncio.sleep(10)
            async def close(self): pass
        controller,_,voice=await self.make(Slow(),timeout=0.01)
        await self.turn(controller,voice,'question')
        self.assertEqual(controller.state,'IDLE')
        self.assertIn('could not complete',voice.spoken[-1])

    async def test_invalid_model_result_rejected(self):
        class Invalid:
            async def respond(self,**kwargs): return {'speech':'bad'}
            async def close(self): pass
        controller,_,voice=await self.make(Invalid())
        await self.turn(controller,voice,'question')
        self.assertNotIn('bad',voice.spoken)

    async def test_visual_pass_without_capture_rejected(self):
        class Invalid:
            async def respond(self,**kwargs): return result('False pass',intent='check',verdict='pass')
            async def close(self): pass
        controller,_,voice=await self.make(Invalid())
        await self.turn(controller,voice,'question')
        self.assertNotIn('False pass',voice.spoken)

    async def test_capture_failure_returns_error(self):
        controller,device,voice=await self.make()
        async def broken(**kwargs): raise ConnectionError('camera')
        device.capture_jpeg=broken
        await self.turn(controller,voice,'check this')
        self.assertIn('could not complete',voice.spoken[-1])

    async def test_nod_loop_and_shutdown_cleanup(self):
        controller,device,voice=await self.make()
        closed=[]
        async def close(): closed.append(True)
        device.close=close; voice.close=close; controller.coach.close=close
        task=asyncio.create_task(controller.run())
        voice.questions.put_nowait('stop'); device.gesture()
        await asyncio.wait_for(controller.turn_started.wait(),1)
        await controller.idle.wait()
        controller.stop.set(); await task
        self.assertEqual(len(closed),3)
        self.assertEqual(voice.spoken[-1],'Stopped.')
