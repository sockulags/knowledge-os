# Knowledge OS

Knowledge OS is a local-first durable knowledge system for Markdown and text. It keeps raw sources and external-agent discoveries separate from durable knowledge, preserves provenance and evidence, and provides deterministic validation, indexing, search, retrieval, review, and explicit promotion.

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

## Record an external discovery safely

An external agent may write a structured proposed discovery, but it does not become knowledge implicitly. Review it, retain it only as project-scoped reviewed memory, or promote it into a new draft record:

```powershell
kos discovery add .\examples\discovery.md
kos discovery review observed-provenance-boundary
kos discovery retain observed-provenance-boundary --reviewer Lucas --reason "Evidence is sufficient for project memory"
kos discovery promote observed-provenance-boundary --target-id provenance-boundary-draft --title "Provenance boundary" --scope project:knowledge-os --acknowledge-related
```

The complete input is [`examples/discovery.md`](examples/discovery.md), and every command uses its actual ID. `discovery review` is read-only generated Markdown. `retain`, `reject`, and `promote` append explicit review history. Promotion copies the observation body into a new `draft`, links its provenance directly to the discovery, and never merges, overwrites, or supersedes an existing record. A project-scoped discovery promoted to `general` additionally requires `--allow-scope-broadening`.

## Export bounded context

After indexing a workspace, export Markdown-first context for an external agent. The generated UTF-8/LF output is non-canonical and goes to stdout, so shell redirection is safe:

```powershell
kos --root examples/context-workspace index
kos --root examples/context-workspace context --project knowledge-os --task "Add URL ingestion while preserving provenance" --budget 12000 > context.md
```

`kos context` selects the mandatory project overview, deterministic FTS matches, one-hop explicit relationships, and selectively relevant skills. It never edits canonical records or rebuilds indexes. See [`examples/context-workspace/README.md`](examples/context-workspace/README.md) for the runnable dogfooding fixture.

## Discovery trust boundary

Discoveries live under `discoveries/` with globally unique IDs, required non-empty evidence and provenance, and optional origin, confidence (`low`, `medium`, or `high`), and review history. Evidence references with `kind: record` must resolve to a Knowledge OS ID; other references stay opaque. The lifecycle is `proposed -> retained | rejected | promoted`, with `rejected` and `promoted` terminal. Only retained discoveries in the requested project scope enter context, and they are labeled reviewed observations rather than established knowledge. Ordinary search can still find every discovery status for audit.

## MVP boundaries

The CLI and standard-library SQLite FTS5 cache are local only. Review matching is deterministic lexical FTS plus metadata and explicit relationships; it is not semantic contradiction detection or fact checking. Promotion is promote-new only: merge-to-existing and supersession are postponed. Round 3 serializes cooperating mutations and rolls back caught write or validation failures, but it is not crash-atomic across several files. An abrupt process or OS interruption between replacements may require `kos lint`, `kos index`, and manual inspection before retrying. No URL ingestion, maintenance automation, LLM decisions, embeddings, graph database, server, GUI, vector database, MCP implementation, or Agentic Work OS coupling is included. See [`docs/architecture.md`](docs/architecture.md) and [`docs/decisions/0001-stack-and-index.md`](docs/decisions/0001-stack-and-index.md).

## Prioritized next issues

1. Model source variants and remote URLs without weakening provenance.
2. Add richer relationship indexes and backlinks.
3. Decide whether merge-to-existing is safe; it is deliberately not part of Round 3.
4. Consider embeddings only after evidence shows deterministic retrieval is insufficient.
