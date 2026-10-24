"""Verity laptop entry point: python -m verity.app --mock"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
from verity.session import Session


def load_recipe(path):
    recipe=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(recipe,dict): raise ValueError('Recipe must be an object')
    return recipe


async def run(args):
    if args.list_audio_devices:
        import sounddevice as sd
        print(sd.query_devices()); return
    if args.audio_check:
        from verity.voice import Voice
        voice=Voice(input_device=args.input_device,output_device=args.output_device,threshold=args.vad_threshold)
        try:
            await voice.start(); await voice.cue('listening')
            text=await voice.listen(); print('Transcription:',text)
            await voice.speak(text or 'No speech detected.')
        finally: await voice.close()
        return
    recipe=load_recipe(args.recipe)
    if not args.mock and recipe.get('template',False) and not args.allow_template:
        raise ValueError('Replace the template recipe with your verified circuit, or explicitly use --allow-template for diagnostics')
    if args.mock:
        from verity.mocks import MockDevice,MockVoice,MockCoach
        device=MockDevice(); voice=MockVoice(); coach=MockCoach()
        print('MOCK MODE: simulated nods, microphone, camera, model and playback.')
    else:
        from verity.device import Device
        from verity.voice import Voice
        from verity.agents.coach import Coach
        references={}
        for step in recipe['steps']:
            if step.get('reference_image'):
                references[(recipe['recipe_id'],step['id'])]=(Path(args.recipe).parent/step['reference_image']).resolve()
        device=Device(address=args.address)
        voice=Voice(input_device=args.input_device,output_device=args.output_device,threshold=args.vad_threshold)
        coach=Coach(references=references)
    controller=Session(device,voice,coach,recipe,cooldown=0 if args.mock else 0.35)
    if args.mock:
        scenario=json.loads(Path(args.scenario).read_text()) if args.scenario else [
            'what is the next step','check this','why use a resistor','repeat','next','stop']
        async def replay():
            try:
                for question in scenario:
                    await controller.idle.wait()
                    controller.turn_started.clear()
                    voice.questions.put_nowait(question); device.nod()
                    await controller.turn_started.wait()
                    await controller.idle.wait()
            finally: controller.stop.set()
        async with asyncio.timeout(60):
            task=asyncio.create_task(controller.run()); replay_task=asyncio.create_task(replay())
            try: await asyncio.gather(task,replay_task)
            finally:
                for pending in (task,replay_task): pending.cancel()
                await asyncio.gather(task,replay_task,return_exceptions=True)
        print(f'MOCK scenario completed: {len(voice.spoken)} replies, {device.captures} capture(s).')
    else:
        await controller.run()


def device_id(value):
    return int(value) if value.isdecimal() else value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe',default='recipes/demo.json')
    parser.add_argument('--mock',action='store_true')
    parser.add_argument('--scenario',help='Mock-only JSON list of questions')
    parser.add_argument('--address',help='BLE device address or peripheral UUID')
    parser.add_argument('--input-device',type=device_id)
    parser.add_argument('--output-device',type=device_id)
    parser.add_argument('--vad-threshold',type=float,default=0.015)
    parser.add_argument('--allow-template',action='store_true',help='Allow generic recipe for diagnostics; not a verified circuit')
    parser.add_argument('--audio-check',action='store_true')
    parser.add_argument('--list-audio-devices',action='store_true')
    args=parser.parse_args()
    if not 0 < args.vad_threshold < 1: parser.error('VAD threshold must be between zero and one')
    logging.basicConfig(level=logging.INFO,format='%(name)s: %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    try: asyncio.run(run(args))
    except KeyboardInterrupt: pass
    except Exception as exc:
        parser.exit(1,f'Verity stopped: {type(exc).__name__}: {exc}\n')


if __name__=='__main__': main()
