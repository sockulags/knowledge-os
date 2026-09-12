---
id: knowledge-os-record-model
title: Knowledge OS record model
type: project
status: active
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-12'
provenance:
  - kind: repository-file
    reference: SYSTEM.md
  - kind: repository-file
    reference: README.md
  - kind: repository-file
    reference: indexes/catalog.md
  - kind: repository-file
    reference: docs/architecture.md
  - kind: repository-file
    reference: knowledge_os/model.py
  - kind: repository-file
    reference: knowledge_os/context_policy.py
  - kind: repository-file
    reference: knowledge_os/workspace.py
  - kind: repository-file
    reference: projects/knowledge-os/README.md
  - kind: repository-file
    reference: projects/knowledge-os/architecture/project-layout/README.md
  - kind: repository-file
    reference: projects/knowledge-os/decisions/openknowledge-pivot.md
---

# Record model

## Managed roots

The workspace marker is `knowledge-os.toml` with `[workspace].version = 1`.
The managed roots are:

| Root | Type and meaning |
| --- | --- |
| `sources/` | Raw local material with provenance |
| `knowledge/` | Durable general knowledge |
| `projects/` | Durable project-scoped records |
| `memory/` | Durable user or agent memory |
| `syntheses/` | Explicitly synthesized durable material |
| `discoveries/` | Evidence-bearing external observations |
| `skills/` | Operational Markdown guidance outside the record schema |
| `indexes/` | Generated catalog and SQLite FTS cache |

Managed records are UTF-8 Markdown files below the root matching their type.
Their filename stem matches the globally unique lowercase kebab-case `id`,
except for project folder root records named `README.md`. Project records stay
inside `projects/<project-id>/`, and that directory requires an active or draft
project overview with the matching `id` and scope.

## Required metadata

Every managed record requires `id`, `title`, `type`, `status`, `scope`,
`created`, `updated`, and a non-empty `provenance` list. Dates use ISO calendar
format. `updated` cannot precede `created`. Unknown top-level metadata fields
are invalid.

`record_kind` is optional for `knowledge` and `project` records. Its values are
`ordinary` and `decision`. Active and superseded decisions require
`decision-acceptance` provenance. Draft decisions cannot contain that
provenance.

## Scope and lifecycle

Scopes are `general` or `project:<lowercase-kebab>`. `knowledge` records use
`general`. `project` records use a project scope. Other managed types may use
either scope when their content warrants it.

Ordinary lifecycle statuses are `draft`, `active`, `deprecated`, `superseded`,
and `archived`. `verified` is an optional date, not a lifecycle status. Its
date must fall between `created` and `updated`.

For decisions, `draft` means proposed, `active` means explicitly accepted and
governing, and `superseded` means replaced by an accepted successor. Acceptance
does not verify factual claims or prove implementation.

## Provenance and relationships

Provenance explains why or how a record exists. Each entry has `kind` and
`reference`, with optional `captured` and `sha256`. `kind: record` resolves to
a canonical record. `kind: discovery` resolves to a discovery. Other kinds
name opaque local or external references.

`related` is a directed domain association. `sources` is a directed input or
support relationship. `supersedes` identifies the record replaced by the
current record. Relationship IDs must resolve. Self-sources, self-supersedes,
and deterministic supersession cycles are invalid.

Discovery promotion uses one lineage pair. The target has provenance with
`kind: discovery` and the discovery has a final review with
`decision: promote` and the target ID. Promotion does not add redundant
`sources` or `related` links and does not overwrite, merge, or supersede an
existing record.

## Discovery lifecycle

Discovery status follows `proposed -> retained`, `proposed -> rejected`, or
`proposed -> promoted`. A retained discovery is project-scoped and remains a
reviewed observation. Rejected and promoted discoveries are terminal.

Discovery evidence and review history are distinct from ordinary lifecycle and
verification. Promotion creates a new `draft` knowledge record for `general`
scope or a new `project` record for a project scope. A project discovery can
promote only within its project unless an explicit scope-broadening operation
allows `general` scope.

## Context eligibility

For a requested project, ordinary context uses only `general` and
`project:<project-id>` scopes. Eligible durable types are `knowledge`,
`project`, `memory`, and `synthesis` with `draft` or `active` status.

Sources never enter default context. Only retained discoveries from the
requested project enter context. Context labels them
`reviewed observation; not established knowledge`. Durable records without a
`verified` date receive a draft or active not verified label. A `verified` date
receives `verified durable`.

Context selection is read-only. The package contains selected records and
skills with metadata, provenance, trust labels, selection evidence, workspace
identity, and content hashes.

## Disposable indexes

`indexes/catalog.md` and `indexes/catalog.sqlite3` are generated from canonical
Markdown. The catalog provides a compact listing. SQLite provides the lexical
FTS cache for search and context ranking.

The indexes are not records and are not a second source of truth. `kos lint`
validates canonical files without requiring index replacement. `kos index`
validates the corpus and rebuilds both files. Deleting both generated files
leaves the canonical corpus valid and permits a later rebuild.
