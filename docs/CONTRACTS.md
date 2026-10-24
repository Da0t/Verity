# Shared component contracts (v1)

Python 3.11+ on Windows. Use asyncio at the application boundary; move blocking
SDK/audio work to threads or use async clients. One active user turn and one
camera request at a time. Cancellation must release audio/device resources.
No implementation may call asyncio.run() inside the running application loop.

Implement these files as namespace-package modules under `verity/`. No shared
`verity/__init__.py` is required. Person 4 owns the entry point.

## Device — `verity/device.py`

```python
class Device:
    async def connect(self) -> None: ...
    async def wait_for_gesture(self) -> str: ...  # "speak" | "back" | "next"
    async def capture_jpeg(self, timeout: float = 30.0) -> bytes: ...
    async def close(self) -> None: ...
```

Constructor takes configuration, never connects implicitly. `wait_for_gesture()`
returns once per deliberate head gesture: "speak" (double nod), "back" (double
left turn) or "next" (double right turn). Use an asyncio queue; coalesce or
discard stale activations rather than replaying them after a long model request.
Capture returns verified fresh JPEG bytes or raises an exception. A disconnect
is an explicit failure, never a cached image. Existing receiver.py is the starting
point. Person 1 owns any wire-protocol additions, including the nod characteristic.

## Audio — `verity/voice.py`

```python
class Voice:
    async def start(self) -> None: ...
    async def cue(self, kind: str) -> None: ...
    async def listen(self, timeout: float = 10.0) -> str: ...
    async def speak(self, text: str) -> None: ...
    async def stop_speaking(self) -> None: ...
    async def close(self) -> None: ...
```

Cue kinds: `listening`, `working`, `error`. `listen` records one utterance,
ends on silence or timeout, returns stripped transcript, and returns `""` if
no speech. Normal listening does not record the assistant's own output. Playback
must be interruptible; `stop_speaking` returns promptly, not after the whole answer.
The controller stops playback before opening the microphone.

## Agent — `verity/agents/coach.py`

```python
class Coach:
    async def respond(self, *, question: str, session: dict,
                      capture_image) -> dict: ...
    async def close(self) -> None: ...
```

`capture_image` is an async callable with no arguments returning fresh JPEG bytes.
The coach may call it once per turn; it does not access BLE directly. `session`
is a read-only snapshot:

```json
{
  "recipe_id": "demo",
  "step_index": 0,
  "steps": [{"id": "connect_signal", "instruction": "...", "expected": "..."}],
  "history": [{"role": "user", "text": "..."}, {"role": "assistant", "text": "..."}],
  "last_observation": null
}
```

Return a validated dictionary containing all these keys:

```json
{
  "speech": "The signal connector appears unplugged. Connect it to the pin marked S.",
  "intent": "check",
  "verdict": "issue",
  "evidence": ["Signal connector is visibly disconnected."],
  "suggested_step_index": null,
  "sources": [],
  "needs_clarification": false
}
```

Intents: `check`, `question`, `next`, `repeat`, `stop`, `unknown`.
Verdicts: `pass`, `issue`, `unclear`, `not_checked`.
Sources: objects with `title`, `locator` (URL or local document identifier), and
`excerpt` containing a brief supporting passage. No fabricated citations.
Suggested step index is null or a valid integer; never a direct state mutation.
Keep speech to one or two useful sentences. The controller owns all state changes.
Plain answers without a new inspection must use `not_checked`.

## Session controller — `verity/app.py`

Owns initialization, cleanup, state machine, history, recipe loading, error
messages, model-call limits, and overall turn timeout. CLI entry:

```sh
python -m verity.app --recipe recipes/demo.json
python -m verity.app --mock --recipe recipes/demo.json
```

Normal flow: IDLE → LISTENING → THINKING (optional CAPTURING) → SPEAKING → IDLE.
One long-lived gesture consumer. A double nod: in IDLE it starts listening; in
SPEAKING it cancels playback then starts listening; in THINKING it cancels the
current turn then starts listening. Ignore/coalesce double nods during LISTENING.
A double left/right turn cancels any turn (including LISTENING) and reads the
previous/next step without listening. Apply gesture cooldown.
Thus a user can double nod, say “stop,” and cancel without a keyboard. No always-on
spoken interruption is promised by v1.

Handle repeat/stop locally before the model where possible. A user-requested
next step is manual progression and must not be labeled visually verified.
A pass does not automatically advance; invite “next” to avoid accidental skipping.
Controller handles exceptions with a brief spoken error and returns to idle.

## Agent limits and freshness

At most one capture and two documentation lookups per turn, with a configurable
overall deadline (initially 45 seconds). No unbounded retries. Reject outdated
results after cancellation using a turn identifier. History is bounded. Model
output is validated before speech or use. Never infer electrical continuity,
component ratings or exact pin identity from an ambiguous photo.

Default text commands in mock mode are development controls only; the demo must
use real IMU activation and audio. Clearly label mock results and offline mode.
