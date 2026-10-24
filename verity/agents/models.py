"""Strict boundaries between model output and the session controller."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


Intent = Literal["check", "question", "next", "repeat", "stop", "unknown"]
Verdict = Literal["pass", "issue", "unclear", "not_checked"]


class Plan(StrictModel):
    intent: Intent
    inspect: bool
    queries: list[str] = Field(max_length=2)
    clarification: str = Field(max_length=300)


class Answer(StrictModel):
    speech: str = Field(min_length=1, max_length=600)
    intent: Intent
    verdict: Verdict
    evidence: list[str] = Field(max_length=6)
    suggested_step_index: int | None
    source_ids: list[str] = Field(max_length=6)
    needs_clarification: bool


class Source(StrictModel):
    title: str
    locator: str
    excerpt: str


class Result(StrictModel):
    speech: str = Field(min_length=1, max_length=600)
    intent: Intent
    verdict: Verdict
    evidence: list[str]
    suggested_step_index: int | None
    sources: list[Source]
    needs_clarification: bool


def result(speech, *, intent="unknown", verdict="not_checked", clarify=False):
    return Result(speech=speech, intent=intent, verdict=verdict, evidence=[],
                  suggested_step_index=None, sources=[],
                  needs_clarification=clarify).model_dump()
