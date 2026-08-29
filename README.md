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

## Export bounded context

After indexing a workspace, export Markdown-first context for an external agent. The generated UTF-8/LF output is non-canonical and goes to stdout, so shell redirection is safe:

```powershell
kos --root examples/context-workspace index
kos --root examples/context-workspace context --project knowledge-os --task "Add URL ingestion while preserving provenance" --budget 12000 > context.md
```

`kos context` selects the mandatory project overview, deterministic FTS matches, one-hop explicit relationships, and selectively relevant skills. It never edits canonical records or rebuilds indexes. See [`examples/context-workspace/README.md`](examples/context-workspace/README.md) for the runnable dogfooding fixture.

## MVP boundaries

The CLI and standard-library SQLite FTS5 cache are local only. No server, GUI, vector database, MCP implementation, or Agentic Work OS coupling is included. See [`docs/architecture.md`](docs/architecture.md) and [`docs/decisions/0001-stack-and-index.md`](docs/decisions/0001-stack-and-index.md).

## Prioritized next issues

1. Add explicit promotion and maintenance workflows from raw sources to durable records.
2. Model source variants and remote URLs without weakening provenance.
3. Add richer relationship indexes and backlinks.
4. Consider embeddings only after evidence shows deterministic retrieval is insufficient.
