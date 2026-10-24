"""Small curated document store. No network access or embedding service required."""
import json
import re
from pathlib import Path
from pydantic import Field
from .models import StrictModel


class Document(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    locator: str = Field(min_length=1, max_length=1000)
    component: str = Field(min_length=1, max_length=200)
    revision: str = Field(min_length=1, max_length=100)
    recipe_ids: list[str] = Field(min_length=1)
    approved: bool
    passages: list[str] = Field(min_length=1, max_length=100)


class KnowledgeStore:
    def __init__(self, directory="knowledge"):
        self.documents = []
        directory = Path(directory)
        ids = set()
        for path in sorted(directory.glob("*.json")):
            if path.stat().st_size > 512_000:
                raise ValueError(f"Knowledge document too large: {path.name}")
            document = Document.model_validate_json(path.read_text(encoding="utf-8"))
            if document.id in ids:
                raise ValueError("Duplicate knowledge document ID")
            ids.add(document.id)
            if document.approved:
                self.documents.append(document)

    def lookup(self, query, recipe_id):
        words = set(re.findall(r"[a-z0-9]+", query.lower())) - {
            "the", "this", "that", "what", "does", "with", "from", "which", "have",
            "and", "for", "how", "why", "are", "can", "you", "is", "it", "a", "to", "of"}
        scored = []
        for doc in self.documents:
            if recipe_id not in doc.recipe_ids:
                continue
            for index, passage in enumerate(doc.passages):
                # Return verbatim excerpts; never ask the model to fabricate sources.
                excerpt = passage[:500]
                tokens = set(re.findall(r"[a-z0-9]+", (doc.component+" "+doc.title+" "+excerpt).lower()))
                score = len(words & tokens)
                if score:
                    scored.append((score, {"id": f"{doc.id}:{index}", "title": doc.title,
                        "locator": doc.locator, "excerpt": excerpt,
                        "component": doc.component, "revision": doc.revision}))
        scored.sort(key=lambda pair: (-pair[0], pair[1]["id"]))
        return [item for _, item in scored[:3]]
