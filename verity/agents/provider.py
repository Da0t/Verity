"""Async Gemini REST adapter; no retries, background threads, or API-key logging."""
import asyncio
import base64
import json
import os
import re
from pathlib import Path
from typing import Protocol
import httpx


def load_config(path=".env.agents"):
    file = Path(path)
    if not file.exists():
        return {}
    config = {}
    for line in file.read_text(encoding="utf-8").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() in ("GEMINI_API_KEY", "VERITY_MODEL"):
            config[name.strip()] = value.strip()
    return config


class ProviderError(RuntimeError):
    pass


class Provider(Protocol):
    async def generate(self, *, system: str, context: dict,
                       images: list[tuple[str, bytes]], schema: dict) -> dict: ...
    async def close(self) -> None: ...


class GeminiProvider:
    def __init__(self, *, api_key=None, model=None, timeout=30.0, client=None):
        config = load_config()
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or config.get("GEMINI_API_KEY")
        self.model = model or os.getenv("VERITY_MODEL") or config.get("VERITY_MODEL")
        if not self.api_key or not self.model:
            raise ValueError("Set GEMINI_API_KEY and VERITY_MODEL before using the hosted coach")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", self.model):
            raise ValueError("VERITY_MODEL must be a model ID without URL or models/ prefix")
        if not 0 < timeout <= 180:
            raise ValueError("Provider timeout must be positive and at most 180 seconds")
        self.timeout = timeout
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=min(10, timeout)))
        self.owns_client = client is None

    async def generate(self, *, system, context, images, schema):
        parts = [{"text": json.dumps(context, ensure_ascii=False)}]
        for label, jpeg in images:
            parts.extend([{"text": label}, {"inlineData": {
                "mimeType": "image/jpeg", "data": base64.b64encode(jpeg).decode("ascii")}}])
        try:
            # httpx read timeouts apply per read; enforce a total request deadline.
            async with asyncio.timeout(self.timeout):
                response = await self.client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                    headers={"x-goog-api-key": self.api_key},
                    json={"systemInstruction": {"parts": [{"text": system}]},
                          "contents": [{"role": "user", "parts": parts}],
                          "generationConfig": {
                              "responseMimeType": "application/json",
                              "responseJsonSchema": schema,
                              "maxOutputTokens": 4096}})
        except (httpx.TimeoutException, TimeoutError):
            raise TimeoutError("Hosted model timed out") from None
        except httpx.HTTPError:
            raise ProviderError("Hosted model connection failed") from None
        if response.status_code != 200:
            raise ProviderError(f"Hosted model returned HTTP {response.status_code}")
        try:
            body = response.json()
            candidate = body["candidates"][0]
            if candidate.get("finishReason") != "STOP":
                raise ValueError("Incomplete or blocked output")
            text = "".join(p.get("text", "") for p in candidate["content"]["parts"]
                           if not p.get("thought", False))
            answer = json.loads(text)
            if not isinstance(answer, dict):
                raise ValueError("Expected object")
            return answer
        except (KeyError, IndexError, TypeError, ValueError):
            raise ProviderError("Hosted model returned incomplete or malformed JSON") from None

    async def close(self):
        if self.owns_client:
            await self.client.aclose()
