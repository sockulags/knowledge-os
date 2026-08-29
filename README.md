# Knowledge OS

Knowledge OS `0.0.1` is a local-first durable knowledge system for Markdown
and text. Markdown is canonical truth. Sources and external-agent discoveries
remain separate trust boundaries, while SQLite and the catalog are disposable
indexes. The complete frozen contract is [`docs/architecture.md`](docs/architecture.md).

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

The workspace root is found from the current directory or with `kos --root
PATH`. Try `kos ingest examples/sample.md`, then `kos search xylophone --json`,
and `kos inspect <id>`. `inbox/` is intentionally outside the managed record
contract.

## Export bounded context

After indexing a workspace, export deterministic, trust-aware, project-scoped
context for an external agent:

```powershell
kos --root examples/context-workspace index
kos --root examples/context-workspace context --project knowledge-os --task "Add URL ingestion while preserving provenance" --budget 12000 > context.md
```

Context includes the exact project overview, eligible general/project durable
records, retained discoveries from that project, and relevant skills. Raw
sources, other project scopes, and non-eligible lifecycle states are excluded.
Every selected item exposes its type, record kind, scope, status, trust label,
path, provenance, and selection evidence. The output is generated,
non-canonical Markdown and is safe to discard. See
[`examples/context-workspace/README.md`](examples/context-workspace/README.md).

## Record an external discovery safely

An external agent may write a structured proposed discovery, but it does not
become knowledge implicitly. Review it, retain it only as project-scoped
reviewed memory, or promote it into a new draft record:

```powershell
kos discovery add .\examples\discovery.md
kos discovery review observed-provenance-boundary
kos discovery retain observed-provenance-boundary --reviewer Lucas --reason "Evidence is sufficient for project memory"
kos discovery promote observed-provenance-boundary --target-id provenance-boundary-draft --title "Provenance boundary" --scope project:knowledge-os --acknowledge-related
```

Promotion is promote-new only. The target's direct provenance and the
discovery's promote review target are the only promotion lineage. Promotion
never merges, overwrites, supersedes, or adds duplicate `sources`/`related`
links. A project-scoped discovery promoted to `general` additionally requires
`--allow-scope-broadening`.

## Trust and metadata

Sources are raw captured material and remain searchable for audit, but are not
default context. Ordinary lifecycle statuses are exactly `draft`, `active`,
`deprecated`, `superseded`, and `archived`; `verified` is not a status. An
optional `verified` ISO date independently produces the `verified durable`
classification. `record_kind` is optional only for `knowledge` and `project`
records, with `ordinary` (the default) or `decision`.

`knowledge-os.toml` must contain `[workspace].version = 1`. `kos lint` validates
the workspace version, all managed records, cross-record provenance and
relationship invariants, managed paths, and every skill. Skills use
`skills/<name>/SKILL.md` with validated frontmatter and a non-empty body.

## Recovery and disposable indexes

Ingest, discovery mutations, and `kos index` share one workspace advisory
lock. Mutations validate the current and intended corpus, write only minimal
canonical files, then rebuild `indexes/catalog.md` and
`indexes/catalog.sqlite3`. Promotion is not crash-atomic and no journal or
rollback system is used. If a partial lineage or index failure occurs, repair
or inspect canonical Markdown and run:

```powershell
kos lint
kos index
```

Deleting both generated index files leaves canonical Markdown valid and they
can be rebuilt with `kos index`.

## Scope

The CLI and standard-library SQLite FTS5 cache are local only. Retrieval and
review are deterministic lexical FTS plus metadata and explicit relationships;
they are not semantic fact checking or contradiction detection. No URL/PDF
ingestion, embeddings, model calls, server, GUI, MCP/API, cloud sync, or
Agentic Work OS coupling is included in v0.0.1.
