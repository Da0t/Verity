# Build-agents branch: setup and integration

## What is implemented

The laptop-side Coach conforms to docs/CONTRACTS.md. It plans a turn, performs
bounded visual inspection/documentation lookups, and returns the shared result
schema. Gemini is the first hosted provider. No server deployment or GPU needed.
The controller, voice pipeline, BLE device adapter and IMU belong to other branches.

* Explicit “check this” requests use a deterministic inspection route and one model call.
* Natural questions use a structured planning call, at most one capture and two
  cached-document queries, then one structured answer call: maximum two model
  calls total. There are no retries or recursive agent loops.
* Stop/repeat/next use local handling for known phrases; natural paraphrases can
  be classified by the planner and then handled deterministically.
* The 45-second overall deadline includes capture, lookup and model time. Each
  provider call also has a 30-second total deadline, a 10-second connection limit,
  and read timeouts. Setup fails cleanly if any deadline is exceeded.
* Async cancellation propagates through capture and HTTP calls. An already sent
  provider request may still be processed/billed; cancellation prevents its result
  being returned to the app. The controller must also discard outdated turn IDs.
* Logs on `verity.agents` contain turn IDs, stage names, timing, sizes and verdicts.
  They omit keys, image bytes, transcripts and document text.

## Windows setup

From your own clone:

```powershell
git fetch origin
git switch codex/build-agents
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements/agents.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Create a Gemini API key in https://aistudio.google.com/apikey using your Google
account and appropriate project. Check the project's quota/billing status in AI
Studio if access is denied or requests are rate-limited. The setup test makes one
small hosted inference request; account pricing/quota applies.

Then run:

```powershell
.\.venv\Scripts\python.exe -m verity.agents.setup --save
```

Paste the key into the terminal's hidden prompt. The script lists models accessible
with that key and asks for a model ID. Choose a current general multimodal Flash
model supporting image input and structured output. Current official model docs
list `gemini-3.8-flash`; for this time-sensitive build we recommend the tested
`gemini-3.5-flash-lite` configuration below. Availability is checked against your
key rather than assumed. If the selected model does not accept the required request, setup fails
instead of silently switching providers/models.

For the tested hackathon configuration, use:

```powershell
.\.venv\Scripts\python.exe -m verity.agents.setup --model gemini-3.5-flash-lite --save
```

`gemini-3.5-flash-lite` passed live text, image and structured-output checks on
October 24, 2026. The heavier `gemini-flash-latest` alias and Interactions route
exceeded our short latency targets in diagnostics. Model listing may include
older models unavailable to new accounts, so the actual generation test matters.
No model-specific thinking-budget override is sent: the tested model rejects the
zero-budget override tried during diagnosis. Keep the explicit, tested model ID
for this demo. There is no automatic switch to a different model on failure.

The check sends a synthetic black-rectangle JPEG and requires a correct structured
JSON response. On success it saves only the validated key/model to **.env.agents**,
which is ignored by the repository's existing `.env.*` rule. Do not share that file.
Start the app from the repository root so it can find this local configuration.
Model listing alone does not prove that generation quota is available; the image
request tests generation as well.

On macOS/Linux, use `python3` or the appropriate virtual environment executable
for the same module commands. If packages are already installed in your current
Python, `python3 -m verity.agents.setup --save` also works.

Optional environment configuration (no saved file required): set `GEMINI_API_KEY`
and `VERITY_MODEL` in the process environment. Precedence is explicit constructor
arguments, environment, then `.env.agents`. No generic `.env` loader or shell
interpolation is used. Supported model IDs exclude a `models/` prefix.

## Circuit data required before a real demo

The team has not supplied an exact demo circuit, manufacturer documentation,
reference image or real capture yet. Do not treat the generic example session as
an approved circuit recipe. Replace `knowledge/examples/session.json` with your
own real session snapshot or provide one from the integration owner.

For cached documentation, add approved JSON records as explained in
`knowledge/README.md`. Search is local keyword retrieval scoped to recipe IDs.
There is intentionally no broad live-web research in this implementation. The
model can ask for clarification when component-specific evidence is missing.

For a reference image, pass a trusted configuration map keyed by recipe and step
IDs to Coach. References must be real JPEGs <=1 MiB. Camera captures must also be
JPEG bytes <=1 MiB; files are decoded/verified before sending to the provider.
Current and reference views receive separate labels.

## Agent-only diagnostic

After API setup, use an actual session JSON and a real JPEG:

```powershell
.\.venv\Scripts\python.exe -m verity.agents.demo --session path\to\session.json --question "check this" --image path\to\fresh.jpg --reference path\to\expected.jpg --logs
.\.venv\Scripts\python.exe -m verity.agents.demo --session path\to\session.json --question "Why is this connector keyed?" --logs
```

`--reference` is optional. The diagnostic CLI reads a supplied fixture; it does
not connect to BLE or claim the image is live. It prints the validated answer or
a safe failure response. This is separate from the final hands-free app.

## Integration owner: copy this interface

```python
from verity.agents.coach import Coach

coach = Coach(knowledge_dir="knowledge", timeout=45.0)
# Optional trusted map: references={("recipe-id", "step-id"): "path/to/reference.jpg"}
try:
    result = await coach.respond(
        question=transcript,
        session=session_snapshot,
        capture_image=device.capture_jpeg,
    )
    # Check the current turn ID before using results after an interruption.
    # Speak result["speech"]. Controller owns suggested step changes.
finally:
    await coach.close()  # session shutdown, not after every normal turn
```

One active turn per Coach. Constructor performs local configuration only; no
network calls. `respond()` raises on invalid session input or concurrent calls.
Provider/image/output failures return a brief clarification response. Cancellation
raises CancelledError. `close()` cancels an active turn and closes owned resources.
An injected provider must expose async `generate(...)` and `close()`; Coach owns it.

Session fields: recipe_id, step_index, steps (id/instruction/expected), history.
Only the last eight history messages are sent, each capped at 1,000 characters.
Prior visual observations are omitted to avoid treating old checks as fresh.
See the complete shared contract for return keys and enum values.

No new image means not_checked and no visual evidence. A visual pass/issue requires
nonempty evidence. Unclear forces needs_clarification. Invalid citations and model
step changes are rejected. Sources are constructed from exact retrieved excerpts,
not model-supplied URLs. These structural checks cannot prove the semantic truth
of every spoken sentence; real image evaluation is still necessary.

## Validation and known limits

Run `python -m unittest discover -s tests -v` with the agent dependencies installed.
Tests use simulated providers and synthetic images/documents. They cover verdicts,
uncertainty, tool caps, document scoping, invalid citations/output, image failures,
cancellation, timeouts, concurrency, HTTP failures and read-only session behavior.
They are not evidence of circuit-recognition accuracy or a successful live API call.

Before declaring the agent demo-ready:

1. Pass `verity.agents.setup` with the team's actual API key/model.
2. Supply a verified recipe, real component docs and reference image.
3. Evaluate real images: deliberate error, corrected build, obscured connector,
   and ambiguous part. Require useful evidence and appropriate uncertainty.
4. Ask a documentation question and check that the returned excerpt supports it.
5. Integrate with real voice/BLE and test interruption, rate limits and network loss.

Current prototype does not provide electrical continuity testing, guaranteed
pin identification from blurry images, automatic build planning or live web search.
Do not claim a circuit is safe to power based on the camera alone.

Official references checked October 24, 2026:
* https://ai.google.dev/gemini-api/docs/api-key
* https://ai.google.dev/gemini-api/docs/models
* https://ai.google.dev/gemini-api/docs/image-understanding
* https://ai.google.dev/gemini-api/docs/structured-output
* https://ai.google.dev/api/generate-content
