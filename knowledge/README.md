# Curated component knowledge

No circuit has been selected yet, so this directory intentionally contains no
approved technical claims or invented pinouts. Add UTF-8 JSON files using this
schema, replacing every placeholder with reviewed manufacturer information:

```json
{
  "id": "unique-component-document",
  "title": "Manufacturer document title and section",
  "locator": "https://manufacturer.example/exact-document",
  "component": "Exact manufacturer and part number",
  "revision": "Exact board/document revision",
  "recipe_ids": ["your-recipe-id"],
  "approved": true,
  "passages": ["A short, verbatim relevant passage with sufficient context."]
}
```

Use `approved: false` while reviewing. Only approved records with the exact
session recipe ID are searched. No wildcard scope. IDs must be unique. Split
passages into short coherent excerpts (at most 500 characters for retrieval),
retain units and qualifications, and record the actual source. Do not add
entire third-party manuals when a few permitted excerpts suffice. Files must
be <=512 KB and have at most 100 passages. No embedding or database setup needed.

The agent can supply general explanations without documentation, but must ask
for component identification/documentation for ungrounded pinout or rating claims.
The model still needs human evaluation; citation validation establishes provenance,
not that every generated sentence is entailed by the cited excerpt.
