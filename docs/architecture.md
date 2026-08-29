# Knowledge OS architecture

## Boundaries and ownership

The filesystem and Markdown are the source of truth. Knowledge OS owns durable records, provenance, deterministic validation, indexing, retrieval, and the explicit discovery return path. Agentic Work OS owns task execution and orchestration; this project has no runtime dependency on it. `inbox/` is untrusted intake, `sources/` preserves raw ingested material, and `discoveries/` preserves external-agent observations with evidence. None is asserted to be knowledge implicitly.

## Core concepts

- **Source:** raw material captured from a local file, retaining original path and byte digest.
- **Knowledge:** durable general knowledge.
- **Project:** durable knowledge scoped to one project.
- **Memory:** durable user or agent memory.
- **Synthesis:** explicitly derived durable material with provenance.
- **Discovery:** an evidence-bearing observation proposed by an external agent or workflow; it is canonical as an observation record, not as established knowledge.
- **Relationship:** an ID link between durable records.
- **Index:** rebuildable catalog and FTS cache, never authoritative.

## Filesystem contract

Each managed record is one `.md` or `.markdown` file in the directory matching its `type`: `sources/`, `knowledge/`, `projects/`, `memory/`, `syntheses/`, or `discoveries/`. Its filename stem equals its globally unique `id`. `inbox/` is outside this contract. `knowledge-os.toml` marks the workspace root.

## Metadata model

Required fields are `id`, `title`, `type`, `status`, `scope`, `created`, `updated`, and non-empty `provenance`. Dates are ISO dates and `updated` cannot precede `created`. IDs are lowercase kebab-case. `verified` is required for `status: verified`; `related`, `sources`, and `supersedes` are ID lists. `extensions` is the only general extension point; unknown top-level fields are errors.

Discoveries use only `proposed`, `retained`, `rejected`, or `promoted` statuses and require a non-empty body and non-empty `evidence` list. Each evidence item has non-empty `kind` and `reference`, with optional ISO `captured` and lowercase SHA-256. `origin` may contain only `project`, `work_item`, and `run`; an origin project must equal the discovery's `project:<id>` scope. `confidence` is `low`, `medium`, or `high`. Review events have `decision` (`retain`, `reject`, or `promote`) and `date`, with optional `reviewer`, `reason`, and `target`; rejects require a reason and promotes require a target. Review dates are nondecreasing and fall within `created..updated`. The current non-proposed status must equal the latest review outcome, and its final review date must equal `updated`. Retained discoveries require project scope.

Project records require a `project:<lowercase-kebab>` scope. A verification date must fall between creation and the latest update.

## CLI and tool boundaries

`kos ingest` accepts one local `.md`, `.markdown`, or `.txt`, writes a provenance-bearing source atomically, and refreshes indexes. `kos lint` validates the corpus. `kos index` validates then rebuilds `catalog.md` and SQLite FTS5. `kos search` reads the existing SQLite cache and returns compact ranked records. Generic `kos inspect` preserves the compact metadata/excerpt contract; `kos discovery inspect` adds full discovery evidence, origin, reviews, relationships, and body. `kos discovery add` validates a proposed structured Markdown candidate and resulting corpus in temporary state before creating `discoveries/<id>.md`. `kos discovery review` requires a valid current index and emits a deterministic, non-canonical packet. `retain`, `reject`, and `promote` append review events and rebuild indexes only after staged validation.

Promotion is promote-new only. The target type is `knowledge` for `general` and `project` for `project:<id>`, always with `draft` status and the discovery body as its initial body. Its provenance is directly `kind: discovery, reference: <discovery-id>` and its `sources` contains the discovery ID. The discovery becomes `promoted` and adds the target to `related`; these links, destination type/scope, target existence, and non-self lineage are corpus invariants enforced by lint. No existing record is overwritten or superseded. Related candidates are computed before promotion from current SQLite FTS, metadata, and explicit relationships, restricted to general and current-project `knowledge`, `project`, `memory`, and `synthesis` records. Acknowledging candidates does not merge them. Project-to-general promotion requires `--allow-scope-broadening`; cross-project promotion fails.

`kos context --project ID --task TEXT --budget N [--work-item TEXT]` is a read-only provider boundary for external agents. Knowledge OS chooses and packages context; it does not execute the downstream task, call a model, rewrite records, or integrate with Agentic Work OS. The package is emitted as Markdown on stdout and is explicitly non-canonical.

## Context request and staged pipeline

The request is the project ID, a required task description, an optional work-item description, and a positive estimated-token budget. Generation has visible deterministic stages:

1. Validate the request, all managed Markdown, and the existing SQLite cache. A missing or stale index is an error; context generation never rebuilds it.
2. Resolve records in `scope: project:<id>` and distinguish a missing project from one whose records are all unusable. A usable `project` record whose ID equals the project ID is the mandatory overview. If that exact record is absent, the lowest-ID usable project-scoped record is a documented deterministic fallback.
3. Query SQLite FTS5 once per distinct task/work-item term, filtering to general and requested-project scopes and usable statuses. Retained discoveries use a separate query restricted to the requested project and `retained` status, so discovery retention does not change ordinary-record ranking. Rank eligible matches by the number of distinct SQLite-matched request terms, then ID; excluded scopes and statuses do not participate in this rank. An explicit relationship may deliberately cross the scope boundary for ordinary records. Deprecated, superseded, and archived optional records are excluded, as are proposed, rejected, and promoted discoveries.
4. Add one-hop candidates from explicit `related`, `sources`, and `supersedes` links, including links touching direct FTS candidates or the project overview. When a direct FTS match is also related, both discovery reasons and both score contributions survive.
5. Parse `skills/*/SKILL.md` in path order. A skill is selected only when at least two distinct request terms match its name, description, or discovery tags. The body is included after selection but is not searched, which keeps incidental prose from activating a skill. Skills are operational context, not managed durable knowledge; their file path is shown as provenance.
6. Rank candidates with this additive score: requested-project scope +100; each lexical FTS match +25; FTS rank +`max(0, 30-rank)`; type weight project/knowledge/synthesis/memory/source/discovery +30/+20/+15/+10/+5/+10; status verified/active/draft/retained +25/+15/+5/+15; one-hop relationship +20. A relevant skill scores +25 per distinct match plus 18. Ties use FTS rank, ID, and path. The manifest exposes the resulting score and match evidence. This is lexical retrieval, not semantic perfection.
7. Keep the overview mandatory, then greedily fit whole optional items in rank order. No body is truncated. The estimator is centralized and documented as `ceil(Unicode character count / 4)`. The final rendered package, including its manifest, must fit the configured budget; a too-small mandatory envelope reports its required estimate.
8. Render a warning, request, budget, selection reasons, discovery/type/scope/status/path/provenance manifest, and complete item bodies with boundaries. A retained discovery is marked `reviewed observation; not established knowledge` in both manifest and rendered item. The used-token field is stabilized deterministically before output.

The package contract is `kos-context/v1`, encoded as UTF-8 with LF line endings. Repeating a request against unchanged Markdown, skills, and index state produces byte-identical output. The provider-only boundary deliberately postpones URL ingestion, model-generated summaries or rewriting, semantic reranking, embeddings, vector databases, background services, MCP, and execution orchestration.

## Context limitations

Retrieval and discovery review matching are lexical FTS plus metadata and explicit relationships; they use SQLite's tokenizer but have no stemming, synonyms, semantic deduplication, semantic contradiction detection, or claim that the score captures meaning perfectly. Skill discovery uses the same request terms and a two-distinct-match threshold. The character-based budget is model-independent but only approximates a tokenizer. Whole items that do not fit are omitted, and an oversized mandatory overview causes a clear failure because this version neither truncates nor summarizes canonical records. Merge-to-existing, supersession decisions, URL ingestion, maintenance automation, LLM fact checking, embeddings, and semantic review remain outside this round.

## Invariants

Duplicate IDs across all managed directories, filename/type mismatches, malformed metadata, invalid digests, invalid relationships, unresolved `kind: record` discovery evidence, invalid discovery review history or promoted lineage, and invalid origin scope prevent indexing. Ingest IDs include a bounded source slug and 64-bit SHA-256 prefix; provenance retains the full digest, and a detected ID collision is never overwritten. Identical ingest is idempotent. Round 3 mutations hold a cross-platform advisory workspace lock from current validation through commit, stage records and indexes, compare live path snapshots immediately before writing, and exclusively create new canonical records. Caught write and validation failures roll back only files written by that transaction.

The Round 3 commit is not a transaction journal and is not crash-atomic across multiple files. An abrupt process or OS termination between per-file atomic replacements can leave canonical records and generated indexes out of sync; recovery requires `kos lint`, `kos index`, and manual inspection of affected records before retrying.

## Deliberately postponed

Merge-to-existing and supersession are deliberately postponed: Round 3 can only create a new draft target, because choosing how to reconcile an observation with an existing record is a product and semantic decision not solved by lexical matching. Source variants and URLs, backlinks, remote synchronization policy, maintenance automation, LLM decisions/fact checking, evidence-gated embeddings, graph storage, and external execution integration are future decisions. No server, GUI, vector database, MCP implementation, or hidden memory layer is part of this slice.
