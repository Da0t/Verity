# Person 3 — Build coach, inspection and documentation agents

Branch: `codex/build-agents`

## Goal

Implement Coach in ../CONTRACTS.md using a hosted multimodal API. Build one
bounded coordinator with specialist tools; separate agent processes are not
required. The laptop runs orchestration; the provider runs model inference.

## Owned paths

* `verity/agents/`
* `requirements/agents.txt`
* `tests/test_agents.py`
* `knowledge/` (approved component documentation and source metadata)
* `docs/AGENTS_SETUP.md`

## Work order

1. Verify the team's available API provider/key and current SDK/model support.
   Make model and credentials environment-configurable. No GPU provisioning.
2. Implement a coach that uses the current recipe, step, transcript and bounded
   conversation history. Return the exact validated result schema.
3. Add an inspect_build tool: call injected capture_image once, compare with the
   expected step/reference, and return visible evidence plus pass/issue/unclear.
4. Add a lookup_docs tool scoped to the exact demo components. Start with cached
   manufacturer documentation under knowledge/, with source and revision metadata.
   This is the MVP research capability; it works without a live web-search tool.
5. For a question such as “what does this pin do?”, look up relevant documentation
   and explain it. Ask for the exact part/revision when unknown. Retrieved text is
   reference data, not instructions that override system behavior.
6. Optional only after integration: live official-document search with strict
   query count/deadline and caching. No broad recursive web research.
7. Implement timeout, malformed-result handling and tool-call caps. Propagate
   cancellation; no background model calls after the turn has been cancelled.

## Agent workflow

User intent → coach selects inspect_build and/or lookup_docs → tool observations
→ coach gives a short answer. Expose tool-call logs for the demo operator. A
hardcoded route is acceptable for “check”; do not market it as open-ended research.
Max one image capture, two lookups, bounded model calls (suggest max three) per
turn. No automatic repeated checking or direct changes to session state.

## Do not build

Microphone, TTS, BLE, arbitrary circuit generation, automatic power control,
cloud deployment or a large agent framework. Do not claim an image establishes
continuity or safety. The agent cannot invent verification or sources.

## Acceptance

Test a visible mistake, corrected build, occluded connector, ambiguous component,
documentation question, malformed output and provider timeout. Verify uncertainty
instead of hallucinated certainty. Evidence must agree with the actual fixture.
Use at least one real API run; distinguish mocks from real evaluation.

## Handoff

Give Person 4 model configuration, dependency file, required knowledge files,
example validated outputs, tool limits, known failure cases and commit SHA.
Coordinate recipe IDs and reference images with Person 4 before hardcoding paths.
