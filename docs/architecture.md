# Knowledge OS — v0.0.1 contract freeze

This document is the authoritative product and metadata contract for the
stabilization release. The package version is `0.0.1`; the workspace schema
version remains the integer `1`.

## Authority and boundaries

Knowledge OS is a local-first, filesystem-native knowledge store. Markdown
records are canonical truth and Git may version them. `indexes/` contains only
derived, disposable state. Context packages and discovery review packets are
generated views and are never canonical knowledge.

Knowledge OS owns durable records, provenance, validation, indexing, search,
bounded context, the explicit discovery return path, and the deterministic
create-only capture primitive for approved records. The root Codex plugin also
owns the automatic conversational detection, proposal batching, and approval
workflow that calls that primitive. Agentic Work OS owns execution and
orchestration; this repository has no runtime dependency on either Agent OS or
Agentic Work OS.

The product does not include URLs, PDFs, embeddings, semantic search or
reranking, LLM trust decisions, contradiction or backlink subsystems, merge or
supersession automation, MCP/API, GUI, cloud or multi-user behavior, a database
as canonical storage, WAL/journal/transaction infrastructure, or background
workers. The Codex plugin is a thin distribution surface for the conversational
capture skill, not a second storage or execution system.

## Workspace and filesystem

`knowledge-os.toml` marks a workspace and must contain:

```toml
[workspace]
name = "knowledge-os"
version = 1
```

The parser rejects a missing, non-integer, or unsupported
`[workspace].version`; v0.0.1 accepts only `1`. There are no per-record
versions or migrations.

The managed roots are:

| Root | Record type and meaning |
| --- | --- |
| `sources/` | raw local material captured with provenance |
| `knowledge/` | durable general knowledge |
| `projects/` | durable project-scoped records |
| `memory/` | durable user or agent memory |
| `syntheses/` | explicitly synthesized durable material |
| `discoveries/` | evidence-bearing external observations |
| `skills/` | operational Markdown guidance, outside the record schema |
| `indexes/` | generated catalog and SQLite FTS cache |

Every managed record is one UTF-8 `.md` or `.markdown` file directly or
recursively below the directory matching its `type`; its filename stem equals
its globally unique lowercase kebab-case `id`. `README.md` files at managed
root level are documentation, not records. Managed files and directories,
including skill paths, must not be symlinks, and resolved managed paths must
remain below the workspace root.

## Record metadata

All managed records require `id`, `title`, `type`, `status`, `scope`, `created`,
`updated`, and a non-empty `provenance` list. Dates are ISO calendar dates and
`updated` cannot precede `created`. Unknown top-level fields are errors.

The record types are `source`, `knowledge`, `project`, `memory`, `synthesis`,
and `discovery`. `knowledge` records require `scope: general`. `project`
records require `scope: project:<lowercase-kebab>`; other records may use
either allowed scope when their content warrants it.

Ordinary records use exactly these lifecycle statuses:
`draft`, `active`, `deprecated`, `superseded`, and `archived`. `verified` is
not a status. A record may instead have an optional `verified` ISO date,
independent of lifecycle status, bounded by `created..updated`. Context trust
is verified only when this date is present; an `active` or `draft` status does
not imply verification.

`record_kind` is optional and is accepted only on `knowledge` and `project`
records. Its values are `ordinary` and `decision`; absence means `ordinary`.
A decision is still an ordinary durable record with an explicit body stating
the chosen rule and rationale. `record_kind` on any other type, unknown values,
and unknown metadata fields are rejected.

Every `project:<slug>` scope present in the corpus must have exactly one usable
overview with `type: project`, `id: <slug>`, and that same scope. The overview
must use `draft` or `active` status. `kos lint` enforces this globally;
context repeats the exact check when resolving its requested project.

Discoveries use their own workflow statuses:
`proposed -> retained | rejected | promoted`. Retained discoveries must be
project-scoped. Rejected and promoted are terminal. Discovery evidence and
review history remain distinct from ordinary lifecycle and verification.

## Provenance, evidence, and relationships

These fields have different meanings:

- `provenance` explains why or how a record came to exist. A provenance entry
  has `kind` and `reference`, with optional capture time and digest. For
  `kind: record`, `reference` resolves to any canonical record ID. For
  `kind: discovery`, it resolves to a canonical discovery ID. Other kinds are
  opaque external/local references.
- `evidence` supports the statement in a discovery. An evidence item has a
  kind and reference; `kind: record` references a canonical record, while
  other kinds remain opaque.
- `related` is a weak, directed domain association. It is not implicitly
  symmetric and is never a substitute for provenance.
- `sources` is a directed ordinary input/support relationship. It is not
  required for discovery promotion and does not duplicate promotion lineage.
- `supersedes` means that the record on the left replaces the referenced
  record. Self-links and deterministic cycles are invalid.

All relationship IDs resolve. Self-`sources`, self-`supersedes`, unresolved
canonical provenance, and invalid canonical provenance types are lint errors.

Promotion is **promote-new** only. The new draft target has one authoritative
lineage edge:

```text
target.provenance: [{kind: discovery, reference: <discovery-id>}]
discovery.reviews[-1]: {decision: promote, target: <target-id>}
```

Promotion does not add the discovery to `target.sources` or
`discovery.related`. The target must have the type implied by its scope and a
project-scoped discovery may target only its own project, unless explicitly
broadened to `general`. Existing records are never overwritten, merged, or
superseded.

This is a frozen invariant, not only a producer convention: lint rejects a
promoted pair when `target.sources` contains its discovery ID or when the
promoted discovery's `related` contains its promote review target. Unrelated
`sources` and `related` relationships remain valid.

Approved conversational candidates use the separate capture path
`kos --root PATH capture CANDIDATE.md [--json]`. Capture accepts only
`knowledge`, `project`, and `memory` records, maps each type to its canonical
managed root, derives the filename from the ID, and refuses existing IDs or
destination paths. Candidates must have valid metadata, a non-empty body and
provenance, `draft` or `active` lifecycle status, and no `verified` field.
Project scope and overview invariants are checked by whole-corpus staged
validation before the canonical exclusive create. Capture does not infer
meaning, decide approval, verify claims, or alter cwd discovery; a cross-chat
caller supplies the configured `--root` explicitly.

Lint also detects practical partial promotion states: a promoted discovery
whose target is missing, a target whose discovery provenance is missing or
invalid, a target provenance edge pointing at a proposed/retained discovery,
and disagreement between a provenance edge and the promote review target.

## Trust and context

The trust classifications are deliberately small:

| Classification | Meaning |
| --- | --- |
| `raw source; not established knowledge` | captured source material; never default context |
| `reviewed observation; not established knowledge` | retained project discovery |
| `draft durable; not verified` | draft durable record without a verified date |
| `active durable; not verified` | active durable record without a verified date |
| `verified durable` | durable record with an optional verified date |
| `operational guidance` | selected skill content |

Sources remain searchable and inspectable, but are excluded from default
context even when their body matches task terms. Only ordinary durable types
`knowledge`, `project`, `memory`, and `synthesis` with status `draft` or
`active`, plus retained discoveries in the requested project, can be selected.
Every selected item exposes type, record kind where applicable, scope, status,
trust classification, path, provenance, and selection evidence.

For `kos context --project ID`, the only eligible ordinary scopes are
`general` and `project:ID`. FTS and one-hop relationship expansion use this
same policy; neither can import `project:other` or any other project scope.
The requested scope must contain exactly one usable project overview whose
type is `project`, ID is `ID`, and scope is `project:ID`. Missing, invalid,
ambiguous, or non-usable identity fails clearly; there is no fallback record.

Context selection is deterministic lexical FTS plus explicit one-hop
relationships and metadata. Skills are selected when at least two distinct
request terms match their name, description, or tags; skill bodies do not
activate selection. Whole items are greedily fitted to the configured budget
using `ceil(Unicode character count / 4)`. The UTF-8/LF package contract is
`kos-context/v1`, emitted to stdout, read-only, and non-canonical.

Discovery review is also deterministic lexical matching and explicit links,
not semantic contradiction detection or fact checking. Review output is
generated Markdown and does not decide an outcome.

## Codex plugin distribution

The repository root is a standalone Codex plugin named `knowledge-os`.
`.codex-plugin/plugin.json` exposes `skills/`, and the repo-owned marketplace
manifest at `.agents/plugins/marketplace.json` publishes the plugin from `./`.
The automatically discoverable `skills/knowledge-os-capture/SKILL.md` detects
durable decisions, reusable lessons, and recurring preferences, batches
approval proposals at natural pauses, and supports direct `save this` or
`spara detta` intent. It creates no candidate before approval and safe-no-ops
when `KNOWLEDGE_OS_ROOT` or the Python 3.11 `knowledge_os` dependency is not
available. When the dependency is missing, it offers an explicit one-time
installation from the plugin root derived from the loaded skill path; it never
installs silently. Launcher selection is cross-platform: `py -3.11` on
Windows, `python3.11` on macOS/Linux, and only a proven Python >=3.11 `python3`
fallback. After setup and approval it invokes the selected launcher with
`knowledge_os --root ... capture ... --json`. Setup detects
`sys.prefix != sys.base_prefix` with that launcher and omits `--user` inside a
virtual environment; non-venv setup uses `--user`. Deterministic storage,
schema validation, provenance, locking, and index refresh remain owned by
Knowledge OS.

## Skills

Each skill is `skills/<name>/SKILL.md`. Shared parsing and validation require
UTF-8 text with frontmatter containing a non-empty lowercase-kebab `name`, a
non-empty `description`, optional non-empty lowercase-kebab `tags`, and a
non-empty body. The directory name must equal the frontmatter name. Duplicate
names, unknown fields, malformed frontmatter, unsafe paths, and malformed
tags are errors. `kos lint` validates every skill, not only skills selected by
context.

## Mutation and recovery contract

Ingest, capture, discovery add/retain/reject/promote, and index replacement all use one
workspace-scoped advisory mutation lock owned by workspace infrastructure.
Each mutation follows this order:

1. acquire the lock and validate the current canonical corpus and skills;
2. validate the intended result in a disposable staged workspace;
3. write only the required canonical Markdown files, atomically replacing
   existing files and exclusively creating new records;
4. keep canonical Markdown as authoritative and rebuild disposable indexes;
5. release the lock.

There is no WAL, journal, multi-file transaction, or rollback of canonical
truth to preserve a cache. Promotion is not crash-atomic. If a process stops
between its two canonical writes, the resulting partial lineage is detected
by `kos lint`; repair the affected Markdown, then run `kos lint` and `kos
index`. If canonical writes succeed but index rebuilding fails, the canonical
records remain; the command reports recovery instructions to run `kos lint`
and then `kos index`.

Deleting `indexes/catalog.md` and `indexes/catalog.sqlite3` does not affect
corpus validity. `kos lint` remains usable and `kos index` recreates both
derived files from Markdown.

## CLI contract

- `kos ingest PATH` captures one local UTF-8 Markdown/text source with a full
  SHA-256 provenance digest and stable ID; identical input is idempotent.
- `kos lint` validates workspace version, all managed records, cross-record
  invariants, and all skills.
- `kos index` validates the corpus and rebuilds `catalog.md` and SQLite FTS5.
- `kos search QUERY` reads the existing cache for compact audit results,
  including type, record kind, status, scope, path, and snippet.
- `kos inspect ID` provides compact record metadata; `--full` adds the body.
- `kos context` emits bounded, trust-aware, project-scoped generated context.
- `kos capture PATH` creates one approved, create-only `knowledge`, `project`,
  or `memory` record after staged whole-corpus validation; `--json` reports
  its exact ID, type, scope, canonical path, and status.
- `kos discovery add PATH`, `review ID`, `retain ID`, `reject ID`, and
  `promote ID` implement the explicit discovery return path.

Read-only context and review require a current SQLite cache and never rebuild
it implicitly. `kos index` is always safe to run as the derived-state repair
step after canonical Markdown has been repaired or a cache has been removed.
