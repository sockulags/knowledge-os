---
id: local-semantic-search
title: Search by meaning with a local multilingual model next to full-text search
type: project
record_kind: decision
status: draft
scope: project:knowledge-os
created: '2026-09-29'
updated: '2026-09-29'
provenance:
- kind: user-request
  reference: github:sockulags/knowledge-os#102
related:
- knowledge-os-reader
- agent-access
---

## Decision

Search finds pages by meaning as well as by their words. A multilingual
embedding model, bge-m3 (quantized ONNX, about 590 MB), runs on this
computer with onnxruntime on the CPU; nothing is sent anywhere. The model is
optional and downloaded once, on request, from a pre-release of this
repository that mirrors the Hugging Face files (`model-bge-m3-<revision>`),
and every file is checked against a sha256 pinned in
`knowledge_os/semantic.py` before it is kept. It lives outside every
knowledge base, in the user's cache folder (`KOS_MODELS_DIR` overrides it).

Each page, except raw sources, is cut into passages of at most 1,500
characters that start with its title and heading. Their vectors are kept in
`indexes/semantic.sqlite3`, a disposable index like the full-text catalog,
ignored by Git; a rebuild embeds only passages whose text changed. A passage
matches when its score stands at least 0.11 above the median score of every
passage for the query, so a query about something the knowledge base does
not hold returns nothing instead of the nearest page.

Full-text and meaning results are merged by reciprocal rank fusion; on a tie
the full-text hit comes first. Each result says how it was found (`text`,
`meaning`, or `both`), and the app labels pages found only by meaning
"Similar in meaning". The Search page, Ctrl+K, and the MCP `search` tool use
the merged results. Serving a page never writes: the index is refreshed in
the background after `kos index`, or when the app or the MCP server sees a
search report it as behind the catalog and asks for a refresh through the
write API. Until then the older index is used.

## Why

Exact-phrase full-text search misses a page worded differently from the
question, and a Swedish question never finds an English page. A local model
answers both without a service, an account, or sending the knowledge base
anywhere, which also suits work computers.

The model was chosen on a bilingual test set of 16 pages and 22 queries
(`tooling/eval_search_models.py`, run by
`.github/workflows/eval-search-models.yml`): questions worded differently
from their page, questions in the other language, and four that match
nothing.

| Model | Right page first | MRR | Margin, real match | Margin, no match | Download |
| --- | --- | --- | --- | --- | --- |
| multilingual-e5-small (q8) | 9/18 | 0.652 | 0.051 | 0.037 | 118 MB |
| multilingual-e5-small (fp32) | 10/18 | 0.715 | 0.052 | 0.037 | 470 MB |
| multilingual-e5-base (q8) | 14/18 | 0.856 | 0.055 | 0.030 | 279 MB |
| bge-m3 (q8) | 18/18 | 1.000 | 0.233 | 0.064 | 570 MB |

EmbeddingGemma 300M and Qwen3-Embedding 0.6B could not be loaded from their
ONNX exports with this runtime. bge-m3 was the only candidate that both
ranked every answer first and separated real matches from queries that match
nothing; with the pinned build, every real match stood at least 0.123 above
the median and no empty query more than 0.095, so the threshold sits between
them.

## Consequences

- Search by meaning costs a 590 MB download and about 1 GB of memory while
  the app runs; the model takes a few seconds to load, so the core loads it
  in the background at start. Without the model, search is exactly the
  full-text search it was.
- The first indexing of a large knowledge base takes a while (the test
  set's 16 short pages took just under a second on a CI runner); later
  refreshes embed only what changed.
- The runtime (`onnxruntime`, `tokenizers`, `numpy`) is the `search` extra
  and is frozen into the desktop core.
- The threshold was set on a small test set; a knowledge base very unlike
  it may show a stray match or miss a weak one. Results by meaning are leads,
  like every search result.
- Changing the model means mirroring it, pinning its hashes and threshold,
  and re-running the evaluation; indexes built by another model are rebuilt.
