"""Agent-only diagnostic using a session JSON and optional real image fixture."""
import argparse
import asyncio
import json
import logging
from pathlib import Path
from .coach import Coach


async def run(args):
    session = json.loads(Path(args.session).read_text(encoding="utf-8"))
    references = None
    if args.reference:
        step = session["steps"][session["step_index"]]
        references = {(session["recipe_id"], step["id"]): args.reference}
    coach = Coach(knowledge_dir=args.knowledge, references=references)
    async def capture():
        if not args.image:
            raise ValueError("Use --image for an inspection; no camera fixture was supplied")
        return Path(args.image).read_bytes()
    try:
        answer = await coach.respond(question=args.question, session=session, capture_image=capture)
        print(json.dumps(answer, indent=2, ensure_ascii=False))
    finally:
        await coach.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="Session JSON matching docs/CONTRACTS.md")
    parser.add_argument("--question", required=True)
    parser.add_argument("--image", help="Fresh real JPEG fixture; this CLI does not connect BLE")
    parser.add_argument("--reference", help="Expected assembly JPEG, separately labeled")
    parser.add_argument("--knowledge", default="knowledge")
    parser.add_argument("--logs", action="store_true")
    args = parser.parse_args()
    if args.logs:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(run(args))
    except (ValueError, OSError, KeyboardInterrupt) as exc:
        parser.exit(1, f"Agent diagnostic stopped: {type(exc).__name__}. Check local configuration/input files.\n")


if __name__ == "__main__":
    main()
