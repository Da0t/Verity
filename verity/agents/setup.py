"""Interactive Gemini setup: python -m verity.agents.setup --save"""
import argparse
import asyncio
import getpass
import io
import json
import os
from pathlib import Path
import re

import httpx
from PIL import Image, ImageDraw
from .provider import GeminiProvider, ProviderError, load_config


async def configure(args):
    config = load_config()
    key = os.getenv("GEMINI_API_KEY") or config.get("GEMINI_API_KEY")
    if not key:
        key = getpass.getpass("Gemini API key (hidden): ").strip()
    if not key or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise ValueError("Expected a nonempty Gemini API key")
    available = []
    async with httpx.AsyncClient(timeout=20) as client:
        token = None
        for _ in range(10):
            params = {"pageSize": 100}
            if token:
                params["pageToken"] = token
            response = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                        headers={"x-goog-api-key": key}, params=params)
            if response.status_code != 200:
                raise ProviderError(f"Model listing returned HTTP {response.status_code}; check key and project access")
            body = response.json()
            for item in body.get("models", []):
                if "generateContent" in item.get("supportedGenerationMethods", []):
                    available.append(item["name"].removeprefix("models/"))
            token = body.get("nextPageToken")
            if not token:
                break
    if not available:
        raise ProviderError("No generateContent models available for this key")
    print("Models available to your key (choose a general multimodal Flash model):")
    for model in available:
        print(f"  {model}")
    model = args.model or os.getenv("VERITY_MODEL") or config.get("VERITY_MODEL")
    if not model:
        model = input("Model ID from the list: ").strip()
    if model not in available:
        raise ValueError("Selected model was not in the accessible model list")
    # This exercises real JPEG input AND schema-constrained JSON, not just auth.
    image = Image.new("RGB", (160, 120), "white")
    ImageDraw.Draw(image).rectangle((45, 25, 115, 95), fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    provider = GeminiProvider(api_key=key, model=model)
    try:
        answer = await provider.generate(
            system="Inspect the supplied test image and return JSON matching the schema.",
            context={"question": "Is there a black rectangle on a white background?"},
            images=[("Synthetic setup test image; not a circuit evaluation", buffer.getvalue())],
            schema={"type": "object", "properties": {"black_rectangle_visible": {"type": "boolean"}},
                    "required": ["black_rectangle_visible"], "additionalProperties": False})
        if answer != {"black_rectangle_visible": True}:
            raise ProviderError("Model did not pass the image + structured response setup test")
    finally:
        await provider.close()
    print(f"PASS: {model} accepted a JPEG and returned the expected structured response.")
    print("This verifies API integration; it does not evaluate circuit inspection accuracy.")
    if args.save:
        path = Path(".env.agents")
        # Configuration loader accepts only these two names; no shell expansion.
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"GEMINI_API_KEY={key}\nVERITY_MODEL={model}\n")
        print("Saved local .env.agents (ignored by Git). Run the app from this folder.")
    else:
        print("Key was used only for this process. Use --save for local ignored configuration.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", help="Model ID; otherwise use environment/config or prompt")
    parser.add_argument("--save", action="store_true", help="Save validated credentials to local .env.agents")
    args = parser.parse_args()
    try:
        asyncio.run(configure(args))
    except (httpx.HTTPError, ValueError, ProviderError, EOFError, KeyboardInterrupt) as exc:
        # Never emit SDK request objects, headers or secrets.
        message = str(exc) if isinstance(exc, (ValueError, ProviderError)) else type(exc).__name__
        parser.exit(1, f"Setup failed: {message}\n")


if __name__ == "__main__":
    main()
