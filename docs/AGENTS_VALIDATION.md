# Live API validation — October 24, 2026

Tested configuration: Gemini Developer API, `gemini-3.5-flash-lite`, generateContent
REST route, image input and responseJsonSchema. Credentials remain in the local
ignored `.env.agents` file, not in this report or repository.

## Observed results

| Check | Result | Observed latency |
|---|---|---|
| Small text request | Successful hosted response | 0.7 seconds |
| Black JPEG + structured color response | Correct `black` result | 0.9 seconds |
| Setup checker: black rectangle + JSON boolean | PASS; local model configuration saved | Not recorded |
| Full Coach: general resistor question | Useful answer; not_checked; no photo | 1.8 seconds |
| Full Coach: check a blank white JPEG | unclear; requested a clearer view | 4.6 seconds |
| Capture count across the two Coach turns | Exactly one | — |
| Automated regression suite | 30 tests pass | — |

These are individual observations, not a latency benchmark or reliability SLA.
Full Coach tests used the real hosted provider and shared result validation,
but synthetic image input and a generic session. They did not test BLE, voice,
an actual assembly, electrical correctness or recognition of a wiring mistake.

## Diagnosis and fix

The original model alias exceeded the 20–30 second request targets for several
text/image calls. A small alias text request with reduced thinking eventually
succeeded in 18.8 seconds, but the image setup check still timed out. Interactions
requests also timed out in these diagnostics, so the tested generateContent route
was retained. A listed 2.5 model returned a specific error saying it was unavailable
to new users; a successful models listing is not proof a model can generate.

The explicit `gemini-3.5-flash-lite` model completed the required image/JSON
workflow quickly without a thinking override. A zero-budget override with that
model returned HTTP 400; the adapter does not send it. No automatic model retry
or fallback has been introduced.

Provider calls now have a total asyncio deadline in addition to HTTP connection
and read limits. Cancellation terminates the client wait. The setup checker
reports timeout cleanly instead of an uncaught traceback. Automated tests cover
cancelling a slow HTTP request and the intended request format.

## Repeat from another machine

Install `requirements/agents.txt` and run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m verity.agents.setup --model gemini-3.5-flash-lite --save
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The local credential file is not shared through Git. Enter the team's current
key through the setup tool's hidden terminal prompt. Follow docs/AGENTS_SETUP.md
for real session/image diagnostic commands and integration instructions.
