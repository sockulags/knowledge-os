# Knowledge OS architecture

## Boundaries and ownership

The filesystem and Markdown are the source of truth. Knowledge OS owns durable records, provenance, deterministic validation, indexing, and retrieval. Agentic Work OS owns task execution and orchestration; this project has no runtime dependency on it. `inbox/` is untrusted intake, while `sources/` preserves raw ingested material. Neither is asserted to be knowledge by ingest.

## Core concepts

- **Source:** raw material captured from a local file, retaining original path and byte digest.
- **Knowledge:** durable general knowledge.
- **Project:** durable knowledge scoped to one project.
- **Memory:** durable user or agent memory.
- **Synthesis:** explicitly derived durable material with provenance.
- **Relationship:** an ID link between durable records.
- **Index:** rebuildable catalog and FTS cache, never authoritative.

## Filesystem contract

Each managed record is one `.md` or `.markdown` file in the directory matching its `type`: `sources/`, `knowledge/`, `projects/`, `memory/`, or `syntheses/`. Its filename stem equals its globally unique `id`. `inbox/` is outside this contract. `knowledge-os.toml` marks the workspace root.

## Metadata model

Required fields are `id`, `title`, `type`, `status`, `scope`, `created`, `updated`, and non-empty `provenance`. Dates are ISO dates and `updated` cannot precede `created`. IDs are lowercase kebab-case. `verified` is required for `status: verified`; `related`, `sources`, and `supersedes` are ID lists. `extensions` is the only extension point; unknown top-level fields are errors.

Project records require a `project:<lowercase-kebab>` scope. A verification date must fall between creation and the latest update.

## CLI and tool boundaries

`kos ingest` accepts one local `.md`, `.markdown`, or `.txt`, writes a provenance-bearing source atomically, and refreshes indexes. `kos lint` validates the corpus. `kos index` validates then rebuilds `catalog.md` and SQLite FTS5. `kos search` reads the existing SQLite cache and returns compact ranked records. `kos inspect` reads authoritative Markdown and returns metadata plus an excerpt.

`kos context --project ID --task TEXT --budget N [--work-item TEXT]` is a read-only provider boundary for external agents. Knowledge OS chooses and packages context; it does not execute the downstream task, call a model, rewrite records, or integrate with Agentic Work OS. The package is emitted as Markdown on stdout and is explicitly non-canonical.

## Context request and staged pipeline

The request is the project ID, a required task description, an optional work-item description, and a positive estimated-token budget. Generation has visible deterministic stages:

1. Validate the request, all managed Markdown, and the existing SQLite cache. A missing or stale index is an error; context generation never rebuilds it.
2. Resolve records in `scope: project:<id>` and distinguish a missing project from one whose records are all unusable. A usable `project` record whose ID equals the project ID is the mandatory overview. If that exact record is absent, the lowest-ID usable project-scoped record is a documented deterministic fallback.
3. Query SQLite FTS5 once per distinct task/work-item term, filtering to general and requested-project scopes and usable statuses. Rank the eligible matches by the number of distinct SQLite-matched request terms, then ID; excluded scopes and statuses do not participate in this rank. An explicit relationship may deliberately cross the scope boundary. Deprecated, superseded, and archived optional records are excluded.
4. Add one-hop candidates from explicit `related`, `sources`, and `supersedes` links, including links touching direct FTS candidates or the project overview. When a direct FTS match is also related, both discovery reasons and both score contributions survive.
5. Parse `skills/*/SKILL.md` in path order. A skill is selected only when at least two distinct request terms match its name, description, or discovery tags. The body is included after selection but is not searched, which keeps incidental prose from activating a skill. Skills are operational context, not managed durable knowledge; their file path is shown as provenance.
6. Rank candidates with this additive score: requested-project scope +100; each lexical FTS match +25; FTS rank +`max(0, 30-rank)`; type weight project/knowledge/synthesis/memory/source +30/+20/+15/+10/+5; status verified/active/draft +25/+15/+5; one-hop relationship +20. A relevant skill scores +25 per distinct match plus 18. Ties use FTS rank, ID, and path. The manifest exposes the resulting score and match evidence. This is lexical retrieval, not semantic perfection.
7. Keep the overview mandatory, then greedily fit whole optional items in rank order. No body is truncated. The estimator is centralized and documented as `ceil(Unicode character count / 4)`. The final rendered package, including its manifest, must fit the configured budget; a too-small mandatory envelope reports its required estimate.
8. Render a warning, request, budget, selection reasons, discovery/type/scope/status/path/provenance manifest, and complete item bodies with boundaries. The used-token field is stabilized deterministically before output.

The package contract is `kos-context/v1`, encoded as UTF-8 with LF line endings. Repeating a request against unchanged Markdown, skills, and index state produces byte-identical output. The provider-only boundary deliberately postpones URL ingestion, model-generated summaries or rewriting, semantic reranking, embeddings, vector databases, background services, MCP, and execution orchestration.

## Context limitations

Retrieval is lexical FTS plus metadata and one relationship hop; it uses SQLite's tokenizer but has no stemming, synonyms, semantic deduplication, or claim that the score captures meaning perfectly. Skill discovery uses the same request terms and a two-distinct-match threshold. The character-based budget is model-independent but only approximates a tokenizer. Whole items that do not fit are omitted, and an oversized mandatory overview causes a clear failure because this version neither truncates nor summarizes canonical records.

## Invariants

Duplicate IDs, filename/type mismatches, malformed metadata, invalid digests, invalid relationships, and unresolved local links prevent indexing. Ingest IDs include a bounded source slug and 64-bit SHA-256 prefix; provenance retains the full digest, and a detected ID collision is never overwritten. Identical ingest is idempotent. Generated artifacts are atomically replaced where practical.

## Deliberately postponed

Promotion/maintenance, source variants and URLs, backlinks, remote synchronization policy, and evidence-gated embeddings are future decisions. No server, GUI, vector database, MCP implementation, or hidden memory layer is part of this slice.
