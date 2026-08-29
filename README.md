# Knowledge OS

Knowledge OS is a local-first durable knowledge system for Markdown and text. It keeps raw sources separate from durable knowledge, preserves provenance, and provides deterministic validation, indexing, search, and retrieval.

## Bootstrap

PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\Activate.ps1
kos lint
kos index
```

Cross-platform:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
kos lint
kos index
```

The workspace root is found from the current directory or with `kos --root PATH`. Try `kos ingest examples/sample.md`, then `kos search xylophone --json`, and `kos inspect <id>`. `inbox/` is intentionally not governed by durable metadata.

## MVP boundaries

The CLI and standard-library SQLite FTS5 cache are local only. No server, GUI, vector database, MCP implementation, or Agentic Work OS coupling is included. See [`docs/architecture.md`](docs/architecture.md) and [`docs/decisions/0001-stack-and-index.md`](docs/decisions/0001-stack-and-index.md).

## Prioritized next issues

1. Define a stable context-export contract for agents.
2. Add explicit promotion and maintenance workflows from raw sources to durable records.
3. Model source variants and remote URLs without weakening provenance.
4. Add richer relationship indexes and backlinks.
5. Consider embeddings only after evidence shows deterministic retrieval is insufficient.
