"""Contract-compatible bounded coach: plan → tools → validated response."""
import asyncio
import copy
import io
import json
import logging
import time
import uuid
import warnings
from pathlib import Path

from PIL import Image
from pydantic import ValidationError
from .knowledge import KnowledgeStore
from .models import Answer, Plan, Result, result
from .provider import GeminiProvider, ProviderError
from . import prompts

logger = logging.getLogger("verity.agents")


def validate_jpeg(data):
    if not isinstance(data, bytes) or not 4 <= len(data) <= 1024 * 1024:
        raise ValueError("Capture must be JPEG bytes up to 1 MiB")
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG" or image.width * image.height > 16_000_000:
                raise ValueError("Unsupported camera image")
            image.verify()
    return data


def snapshot(session):
    if not isinstance(session, dict):
        raise ValueError("Session must be a dict")
    recipe = session.get("recipe_id")
    steps = session.get("steps")
    index = session.get("step_index")
    if not isinstance(recipe, str) or not recipe or len(recipe) > 100:
        raise ValueError("Session requires recipe_id")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 30:
        raise ValueError("Session requires 1–30 steps")
    if type(index) is not int or not 0 <= index < len(steps):
        raise ValueError("Invalid step_index")
    cleaned = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Invalid step")
        item = {}
        for field in ("id", "instruction", "expected"):
            value = step.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise ValueError(f"Step requires bounded {field}")
            item[field] = value
        cleaned.append(item)
    history = session.get("history", [])
    if not isinstance(history, list):
        raise ValueError("History must be a list")
    bounded = []
    for entry in history[-8:]:
        if (isinstance(entry, dict) and entry.get("role") in ("user", "assistant")
                and isinstance(entry.get("text"), str)):
            bounded.append({"role": entry["role"], "text": entry["text"][:1000]})
    # Prior observations are deliberately excluded: only a new image verifies now.
    return {"recipe_id": recipe, "step_index": index, "steps": cleaned, "history": bounded}


class Coach:
    def __init__(self, *, provider=None, knowledge_dir="knowledge", references=None,
                 timeout=45.0):
        """references: trusted {(recipe_id, step_id): Path} map, never model paths.

        Provider is async generate(system, context, images, schema) -> dict + close().
        The coach owns and closes the provider; use one coach per session.
        """
        if not 0 < timeout <= 180:
            raise ValueError("timeout must be positive and at most 180 seconds")
        self.store = KnowledgeStore(knowledge_dir)
        self.references = dict(references or {})
        self.provider = provider if provider is not None else GeminiProvider()
        self.timeout = timeout
        self.lock = asyncio.Lock()
        self.active = None
        self.closed = False

    def event(self, turn, name, **metadata):
        logger.info(json.dumps({"turn": turn, "event": name, **metadata}))

    async def respond(self, *, question, session, capture_image):
        if self.closed:
            raise RuntimeError("Coach is closed")
        if self.lock.locked():
            raise RuntimeError("Coach accepts one active turn; cancel or await the previous turn")
        # Validate before invoking a hosted model; never modify the caller's objects.
        context = snapshot(session)
        if not isinstance(question, str) or not question.strip() or len(question) > 2000:
            raise ValueError("Question must contain 1–2000 characters")
        context["question"] = question.strip()
        normalized = question.strip().lower().rstrip(".!?")
        if normalized in ("stop", "cancel"):
            return result("Stopped.", intent="stop")
        if normalized in ("repeat", "say that again"):
            previous = next((h["text"] for h in reversed(context["history"])
                             if h["role"] == "assistant"), "There is no previous answer to repeat.")
            return result(previous[:600], intent="repeat")
        if normalized in ("next", "next step", "what next", "what's next", "what is the next step"):
            index = context["step_index"] + 1
            if index == len(context["steps"]):
                return result("You are on the last step. This does not verify the electrical build.", intent="next")
            answer = result(context["steps"][index]["instruction"][:600], intent="next")
            answer["suggested_step_index"] = index
            return answer
        async with self.lock:
            self.active = asyncio.current_task()
            turn = uuid.uuid4().hex[:12]
            started = time.monotonic()
            self.event(turn, "turn_start")
            try:
                async with asyncio.timeout(self.timeout):
                    return await self._respond(context, normalized, capture_image, turn)
            except asyncio.CancelledError:
                self.event(turn, "cancelled")
                raise
            except TimeoutError:
                self.event(turn, "timeout")
                return result("That check timed out. Please try again when the connection is ready.", clarify=True)
            except (ProviderError, ValidationError, ValueError, OSError, Image.DecompressionBombError,
                    Image.DecompressionBombWarning) as exc:
                self.event(turn, "failed", error_type=type(exc).__name__)
                return result("I couldn't verify that response. Please try again or clarify the component.", clarify=True)
            finally:
                self.active = None
                self.event(turn, "turn_end", elapsed_ms=round((time.monotonic()-started)*1000))

    async def _respond(self, context, normalized, capture_image, turn):
        if normalized in ("check", "check this", "check again", "check my work", "is this connected correctly"):
            plan = Plan(intent="check", inspect=True, queries=[], clarification="")
        else:
            self.event(turn, "model_start", stage="plan")
            raw = await self.provider.generate(system=prompts.PLAN, context=context,
                                               images=[], schema=Plan.model_json_schema())
            plan = Plan.model_validate(raw)
        if plan.intent in ("next", "repeat", "stop"):
            # Natural paraphrases can be classified by the planner; controls
            # remain deterministic and never reach the answer model/tools.
            if plan.intent == "stop":
                return result("Stopped.", intent="stop")
            if plan.intent == "repeat":
                previous = next((h["text"] for h in reversed(context["history"])
                                 if h["role"] == "assistant"), "There is no previous answer to repeat.")
                return result(previous[:600], intent="repeat")
            index = context["step_index"] + 1
            if index == len(context["steps"]):
                return result("You are on the last step.", intent="next")
            output = result(context["steps"][index]["instruction"][:600], intent="next")
            output["suggested_step_index"] = index
            return output
        if plan.clarification:
            return result(plan.clarification, intent=plan.intent, clarify=True)
        if plan.intent == "check" and not plan.inspect:
            # The planner cannot bypass observation for a check.
            plan.inspect = True
        sources = {}
        for query in plan.queries:
            if not query.strip() or len(query) > 200:
                raise ValueError("Invalid lookup query")
            self.event(turn, "lookup_docs", recipe_id=context["recipe_id"])
            for hit in self.store.lookup(query, context["recipe_id"]):
                sources[hit["id"]] = hit
        images = []
        if plan.inspect:
            self.event(turn, "inspect_build_start")
            try:
                jpeg = validate_jpeg(await capture_image())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.event(turn, "capture_failed", error_type=type(exc).__name__)
                return result("I couldn't get a clear fresh photo. Hold still and ask me to check again.",
                              intent=plan.intent, verdict="unclear", clarify=True)
            images.append(("CURRENT: fresh view of the user's assembly", jpeg))
            step = context["steps"][context["step_index"]]
            ref = self.references.get((context["recipe_id"], step["id"]))
            if ref is not None:
                path = Path(ref)
                if path.stat().st_size > 1024 * 1024:
                    raise ValueError("Reference image too large")
                images.append(("REFERENCE: expected assembly, not current evidence", validate_jpeg(path.read_bytes())))
            self.event(turn, "inspect_build_ready", bytes=len(jpeg))
        payload = copy.deepcopy(context)
        payload.update({"plan": plan.model_dump(), "documents": list(sources.values()),
                        "has_current_image": bool(images)})
        self.event(turn, "model_start", stage="answer")
        raw = await self.provider.generate(system=prompts.ANSWER, context=payload,
                                           images=images, schema=Answer.model_json_schema())
        answer = Answer.model_validate(raw)
        if not answer.speech.strip() or any(not e.strip() or len(e) > 500 for e in answer.evidence):
            raise ValueError("Empty speech or invalid evidence")
        if not images and (answer.verdict != "not_checked" or answer.evidence):
            raise ValueError("Visual verdict without a new image")
        if plan.inspect and answer.verdict == "not_checked":
            raise ValueError("Inspection did not provide a verdict")
        if answer.verdict in ("pass", "issue") and not answer.evidence:
            raise ValueError("Visual verdict needs evidence")
        if answer.verdict == "pass" and answer.needs_clarification:
            raise ValueError("Cannot pass an unclear inspection")
        if answer.verdict == "unclear":
            answer.needs_clarification = True
        if answer.suggested_step_index is not None:
            raise ValueError("Model cannot advance assembly steps")
        if answer.intent in ("next", "repeat", "stop") or answer.intent != plan.intent:
            raise ValueError("Answer cannot change planned intent or control state")
        selected = []
        for source_id in dict.fromkeys(answer.source_ids):
            if source_id not in sources:
                raise ValueError("Unretrieved citation")
            source = sources[source_id]
            selected.append({k: source[k] for k in ("title", "locator", "excerpt")})
        output = answer.model_dump(exclude={"source_ids"})
        output["sources"] = selected
        self.event(turn, "answer_validated", verdict=answer.verdict, source_count=len(selected))
        return Result.model_validate(output).model_dump()

    async def close(self):
        self.closed = True
        task = self.active
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await self.provider.close()
