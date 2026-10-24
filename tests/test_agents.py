"""Behavior and failure-path tests; simulated providers, not accuracy benchmarks."""
import asyncio
import copy
from contextlib import redirect_stdout
from types import SimpleNamespace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx
from PIL import Image
from verity.agents.coach import Coach
from verity.agents.knowledge import KnowledgeStore
from verity.agents.provider import GeminiProvider, ProviderError
from verity.agents.setup import configure


def session():
    return {"recipe_id": "test", "step_index": 0, "steps": [
        {"id": "signal", "instruction": "Connect the marked connector.",
         "expected": "Connector is visibly seated in the labeled socket."},
        {"id": "finish", "instruction": "Inspect the connection.", "expected": "Connector seated."}],
        "history": [], "last_observation": None}


def answer(**overrides):
    value = {"speech": "The connector appears unplugged. Seat it in the labeled socket.",
             "intent": "check", "verdict": "issue", "evidence": ["Connector is visibly detached."],
             "suggested_step_index": None, "source_ids": [], "needs_clarification": False}
    value.update(overrides)
    return value


def plan(**overrides):
    value = {"intent": "question", "inspect": False, "queries": [], "clarification": ""}
    value.update(overrides)
    return value


def jpeg():
    image = Image.new("RGB", (64, 64), "white")
    data = io.BytesIO()
    image.save(data, format="JPEG")
    return data.getvalue()


class FakeProvider:
    def __init__(self, *outputs, delay=0):
        self.outputs = list(outputs)
        self.calls = []
        self.delay = delay
        self.cancelled = False
        self.closed = False

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return copy.deepcopy(output)

    async def close(self):
        self.closed = True


class CoachTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.capture_count = 0

    def coach(self, *outputs, **options):
        provider = FakeProvider(*outputs)
        coach = Coach(provider=provider, knowledge_dir=self.directory.name, **options)
        self.addAsyncCleanup(coach.close)
        return coach, provider

    async def capture(self):
        self.capture_count += 1
        return jpeg()

    async def ask(self, coach, question="check this", state=None, capture=None):
        return await coach.respond(question=question, session=state or session(),
                                   capture_image=capture or self.capture)

    async def test_issue_pass_and_occlusion(self):
        for verdict in ("issue", "pass", "unclear"):
            with self.subTest(verdict=verdict):
                coach, provider = self.coach(answer(verdict=verdict))
                response = await self.ask(coach)
                self.assertEqual(response["verdict"], verdict)
                self.assertEqual(len(provider.calls), 1)
                self.assertEqual(len(provider.calls[0]["images"]), 1)
                self.assertIsNone(response["suggested_step_index"])
                self.assertEqual(response["needs_clarification"], verdict == "unclear")
        self.assertEqual(self.capture_count, 3)

    async def test_question_needs_no_photo(self):
        coach, provider = self.coach(plan(), answer(intent="question", verdict="not_checked", evidence=[]))
        response = await self.ask(coach, "Why use a resistor?")
        self.assertEqual(response["verdict"], "not_checked")
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(self.capture_count, 0)

    async def test_ambiguous_part_clarifies_before_capture(self):
        coach, provider = self.coach(plan(clarification="Which exact board and revision are you using?"))
        response = await self.ask(coach, "Which pin is power?")
        self.assertTrue(response["needs_clarification"])
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(self.capture_count, 0)

    async def test_planner_cannot_bypass_check_capture(self):
        coach, _ = self.coach(plan(intent="check"), answer())
        response = await self.ask(coach, "Please inspect that connector for me")
        self.assertEqual(response["verdict"], "issue")
        self.assertEqual(self.capture_count, 1)

    async def test_reference_is_separately_labeled(self):
        path = Path(self.directory.name)/"ref.jpg"
        path.write_bytes(jpeg())
        coach, provider = self.coach(answer(), references={("test", "signal"): path})
        await self.ask(coach)
        labels = [label for label, _ in provider.calls[0]["images"]]
        self.assertTrue(labels[0].startswith("CURRENT"))
        self.assertTrue(labels[1].startswith("REFERENCE"))
        self.assertEqual(self.capture_count, 1)

    async def test_image_error_does_not_call_model(self):
        async def broken():
            raise ConnectionError("camera disconnected")
        coach, provider = self.coach()
        response = await self.ask(coach, capture=broken)
        self.assertEqual(response["verdict"], "unclear")
        self.assertFalse(provider.calls)

    async def test_invalid_jpeg_does_not_call_model(self):
        async def broken():
            return b"\xff\xd8this is not a real jpeg\xff\xd9"
        coach, provider = self.coach()
        self.assertEqual((await self.ask(coach, capture=broken))["verdict"], "unclear")
        self.assertFalse(provider.calls)

    async def test_model_output_failures_are_not_spoken(self):
        for invalid in ({"speech": "bad"}, answer(source_ids=["invented"]),
                        answer(evidence=[]), answer(suggested_step_index=1),
                        answer(intent="next"), answer(speech=" "),
                        answer(verdict="pass", needs_clarification=True)):
            with self.subTest(invalid=invalid):
                coach, _ = self.coach(invalid)
                response = await self.ask(coach)
                self.assertEqual(response["verdict"], "not_checked")
                self.assertTrue(response["needs_clarification"])

    async def test_visual_claim_without_image_is_rejected(self):
        coach, _ = self.coach(plan(), answer(intent="question"))
        response = await self.ask(coach, "Why is this needed?")
        self.assertEqual(response["verdict"], "not_checked")
        self.assertTrue(response["needs_clarification"])

    async def test_tool_budget_excess_rejected(self):
        coach, provider = self.coach(plan(queries=["a", "b", "c"]))
        response = await self.ask(coach, "Research this")
        self.assertTrue(response["needs_clarification"])
        self.assertEqual(len(provider.calls), 1)

    async def test_docs_are_scoped_and_citations_are_verbatim(self):
        document = {"id": "doc", "title": "Synthetic test document", "locator": "test:fixture",
                    "component": "Fixture connector", "revision": "test-only", "recipe_ids": ["test"],
                    "approved": True, "passages": ["The fixture connector has a keyed socket."]}
        (Path(self.directory.name)/"doc.json").write_text(json.dumps(document))
        coach, provider = self.coach(plan(queries=["connector keyed"]),
            answer(intent="question", verdict="not_checked", evidence=[], source_ids=["doc:0"]))
        response = await self.ask(coach, "What is a keyed connector?")
        self.assertEqual(response["sources"][0]["excerpt"], document["passages"][0])
        self.assertEqual(provider.calls[-1]["context"]["documents"][0]["revision"], "test-only")
        self.assertFalse(KnowledgeStore(self.directory.name).lookup("connector", "other-recipe"))
        document["approved"] = False
        (Path(self.directory.name)/"doc.json").write_text(json.dumps(document))
        self.assertFalse(KnowledgeStore(self.directory.name).lookup("connector", "test"))

    async def test_timeout_cancels_provider(self):
        coach, provider = self.coach(answer(), timeout=0.02)
        provider.delay = 1
        response = await self.ask(coach)
        self.assertTrue(response["needs_clarification"])
        self.assertTrue(provider.cancelled)

    async def test_external_cancel_propagates_and_next_turn_works(self):
        coach, provider = self.coach(answer())
        provider.delay = 1
        task = asyncio.create_task(self.ask(coach))
        await asyncio.sleep(0.01)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        provider.delay = 0
        self.assertEqual((await self.ask(coach))["verdict"], "issue")

    async def test_close_cancels_active_turn(self):
        coach, provider = self.coach(answer())
        provider.delay = 1
        task = asyncio.create_task(self.ask(coach))
        await asyncio.sleep(0.01)
        await coach.close()
        self.assertTrue(task.cancelled())
        self.assertTrue(provider.closed)

    async def test_concurrent_turn_rejected(self):
        coach, provider = self.coach(answer())
        provider.delay = 1
        task = asyncio.create_task(self.ask(coach))
        await asyncio.sleep(0.01)
        with self.assertRaises(RuntimeError):
            await self.ask(coach)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

    async def test_state_is_read_only_and_history_bounded(self):
        state = session()
        state["history"] = [{"role": "user", "text": "x"*1500} for _ in range(100)]
        original = copy.deepcopy(state)
        coach, provider = self.coach(answer())
        await self.ask(coach, state=state)
        self.assertEqual(state, original)
        context = provider.calls[0]["context"]
        self.assertEqual(len(context["history"]), 8)
        self.assertEqual(len(context["history"][0]["text"]), 1000)
        self.assertNotIn("last_observation", context)

    async def test_local_controls_have_no_api_or_capture(self):
        coach, provider = self.coach()
        state = session()
        state["history"] = [{"role": "assistant", "text": "Previous answer."}]
        self.assertEqual((await self.ask(coach, "repeat", state))["speech"], "Previous answer.")
        self.assertEqual((await self.ask(coach, "stop"))["intent"], "stop")
        response = await self.ask(coach, "next")
        self.assertEqual(response["suggested_step_index"], 1)
        self.assertEqual(response["verdict"], "not_checked")
        self.assertFalse(provider.calls)
        self.assertEqual(self.capture_count, 0)

    async def test_paraphrased_control_does_not_run_tools(self):
        coach, provider = self.coach(plan(intent="next", inspect=True, queries=["unused"]))
        response = await self.ask(coach, "What should I do after this step?")
        self.assertEqual(response["suggested_step_index"], 1)
        self.assertEqual(response["verdict"], "not_checked")
        self.assertEqual(self.capture_count, 0)
        self.assertEqual(len(provider.calls), 1)

    async def test_invalid_session_rejected_before_api(self):
        coach, provider = self.coach()
        state = session()
        state["step_index"] = -1
        with self.assertRaises(ValueError):
            await self.ask(coach, state=state)
        self.assertFalse(provider.calls)


class SetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_dotted_auth_key_accepted_without_printing_secret(self):
        secret = "AQ.test-key-not-real"
        async def handle(request):
            self.assertEqual(request.headers["x-goog-api-key"], secret)
            return httpx.Response(200, json={"models": [{"name": "models/test-model",
                "supportedGenerationMethods": ["generateContent"]}]})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
        provider = FakeProvider({"black_rectangle_visible": True})
        output = io.StringIO()
        with patch.dict("os.environ", {}, clear=True), \
             patch("verity.agents.setup.load_config", return_value={"GEMINI_API_KEY": secret}), \
             patch("verity.agents.setup.httpx.AsyncClient", return_value=client), \
             patch("verity.agents.setup.GeminiProvider", return_value=provider), \
             redirect_stdout(output):
            await configure(SimpleNamespace(model="test-model", save=False))
        self.assertIn("PASS", output.getvalue())
        self.assertNotIn(secret, output.getvalue())
        self.assertTrue(provider.closed)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_wire_format_and_no_secret_in_url(self):
        async def handle(request):
            self.assertNotIn("key=", str(request.url))
            self.assertEqual(request.headers["x-goog-api-key"], "fake-key")
            body = json.loads(request.content)
            self.assertIn("responseJsonSchema", body["generationConfig"])
            self.assertNotIn("thinkingConfig", body["generationConfig"])
            self.assertEqual(body["contents"][0]["parts"][2]["inlineData"]["mimeType"], "image/jpeg")
            return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
                "parts": [{"text": '{"ok": true}'}]}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            provider = GeminiProvider(api_key="fake-key", model="test-model", client=client)
            output = await provider.generate(system="test", context={}, images=[("current", jpeg())], schema={})
            self.assertEqual(output, {"ok": True})
            await provider.close()
            self.assertFalse(client.is_closed)

    async def test_bad_api_responses_are_sanitized(self):
        for status, body in ((429, {"secret": "must-not-log"}), (200, {}),
                             (200, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
                             (200, {"candidates": [{"finishReason": "STOP", "content": {
                                 "parts": [{"text": "not json"}]}}]})):
            async def handle(request):
                return httpx.Response(status, json=body)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                provider = GeminiProvider(api_key="fake-key", model="test-model", client=client)
                with self.assertRaises(ProviderError) as caught:
                    await provider.generate(system="test", context={}, images=[], schema={})
                self.assertNotIn("must-not-log", str(caught.exception))

    async def test_total_deadline_cancels_slow_request(self):
        cancelled = False
        async def handle(request):
            nonlocal cancelled
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled = True
                raise
            return httpx.Response(200, json={})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            provider = GeminiProvider(api_key="fake-key", model="test-model", client=client, timeout=0.01)
            with self.assertRaisesRegex(TimeoutError, "Hosted model timed out"):
                await provider.generate(system="test", context={}, images=[], schema={})
        self.assertTrue(cancelled)

    async def test_missing_credentials_fail_clearly(self):
        with patch.dict("os.environ", {}, clear=True), patch("verity.agents.provider.load_config", return_value={}):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                GeminiProvider()


if __name__ == "__main__":
    unittest.main()
