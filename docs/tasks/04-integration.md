# Person 4 — Session controller and integration owner

Branch: `codex/session-integration`

## Goal

Own the complete nod → speech → inspection/question → spoken feedback experience.
Implement the controller in ../CONTRACTS.md, starting with mocked components so
the other three workstreams can proceed independently.

## Owned paths

* `verity/app.py`, `verity/session.py`, `verity/mocks.py`
* `recipes/`, `tests/test_session.py`
* Root `README.md`, `.gitignore`, `.env.example`, `requirements.txt`
* `requirements/app.txt`
* `docs/CONTRACTS.md`, `docs/DEMO.md`, integration CI if useful

## Work order

1. Freeze a three-to-five-step circuit recipe and coordinate its correctness with
   Person 3. Define reference labels and one deliberate visible error.
2. Implement mock Device/Voice/Coach adapters and a runnable --mock mode.
3. Implement state transitions and exactly one active turn. Maintain a bounded
   history, current step, previous answer, last observation and turn identifier.
4. Connect nod activation and interruption. Stop active playback before listening.
   Cancel a thinking turn on a new deliberate activation; discard late results.
5. Handle repeat and stop locally, next as manual unverified progression, and all
   model results through schema validation. Never silently skip steps.
6. Add per-turn timeout, brief spoken errors and return-to-idle recovery. Report
   internet failure truthfully; offline mode can repeat cached instructions but
   cannot claim a fresh AI inspection happened.
7. Merge the three component branches incrementally, consolidate dependency files,
   and document one Windows launch command. Do not deploy a cloud service.
8. Measure end-to-end latency on real hardware, freeze features and rehearse.

## Integration flow

Ask each owner for a pushed commit and smoke-check results. Merge their branches
into this branch, resolve contract mismatches with the owner, and test each merge.
Run receiver tests and session tests; then perform the real acceptance run.
Only then merge this branch to main. No force pushes. Do not overwrite teammates'
work or reimplement components in parallel without coordination.

## Acceptance

Mock session tests cover normal flow, repeated nods, interruption, stale model
results, capture failure, empty transcript, model timeout and manual progression.
Real wearer completes the team acceptance run three times without screen input.
If a component is still mocked, explicitly label that limitation in the demo.

## Demo script

1. Nod: “What is the next step?” → concise instruction.
2. Leave a visible connection wrong; nod: “Check this.” → useful correction.
3. Fix it; nod: “Check again.” → supported observation.
4. Nod: ask why that connection is needed → contextual explanation from docs.
5. Show hands remained on the work and show bounded tool logs to judges if useful.

Ship a backup recording and honest limitations: fixed demo circuit, camera
visibility constraints, BLE latency, hosted API dependence, no electrical test.
