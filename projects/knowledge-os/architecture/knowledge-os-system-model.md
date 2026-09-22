---
id: knowledge-os-system-model
title: Knowledge OS system model
type: project
status: active
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-22'
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

# System model

## Ownership

Knowledge OS owns durable Markdown records, provenance, validation, indexing,
search, bounded context, discovery review, and the create-only capture
primitive for approved records.

The root Codex plugin owns conversational candidate detection, proposal
batching, approval handling, and the call to capture. It does not own storage
or validation.

Agentic Work OS owns execution and orchestration. This repository has no
runtime dependency on Agentic Work OS or Agent OS.

## Component flow

`knowledge-os.toml` identifies a workspace with schema version `1`.

The CLI reads Markdown from managed roots and validates metadata, paths,
relationships, project overviews, and skills. `kos ingest` captures raw local
material in `sources/`. Approved capture writes durable `knowledge`, `project`,
or `memory` records. Discovery commands add and review external observations.

`kos index` validates the corpus, then rebuilds the catalog and SQLite FTS cache.
`kos search` reads the SQLite cache. `kos inspect` reads canonical Markdown.
`kos context` filters eligible records by project scope and lifecycle, ranks
lexical matches, and emits a disposable bounded context package.

## Trust boundaries

Canonical Markdown is the authoritative record store. `sources/` contains raw
material and is searchable, but it is excluded from default context.

`discoveries/` contains evidence-bearing external observations. A retained
discovery is labeled `reviewed observation; not established knowledge` and is
eligible only in its project context. Promotion creates a new draft record and
keeps discovery provenance and review history explicit.

Durable records without a `verified` date are labeled as draft or active and
not verified. A `verified` date produces the `verified durable` label. Lifecycle
status does not verify a claim.

The [OpenKnowledge pivot decision](../decisions/openknowledge-pivot.md) was
withdrawn on 2026-09-22. It never became a current integration or a change to
the v0.0.1 ownership model; see the draft decision [Keep Knowledge OS
standalone, built for learning](../decisions/standalone-learning-direction.md)
for the current direction.

## Mutation and recovery

Ingest, capture, update, decision acceptance, decision supersession, discovery
mutations, and index replacement use one workspace-scoped advisory lock.

Each mutation validates the current corpus, validates the intended result in a
temporary staged workspace, writes only the required canonical Markdown, and
rebuilds disposable indexes. New records use exclusive creation. Existing
records use the operation-specific conflict checks.

There is no write-ahead log, journal, or multi-file transaction. Promotion and
supersession are not crash-atomic. A caught supersession write failure attempts
to restore both original records. If canonical writes leave partial lineage or
replacement state, inspect the Markdown and run `kos lint` followed by
`kos index`.

If index replacement fails after canonical writes, the Markdown remains
authoritative. Run `kos lint` followed by `kos index` to rebuild derived state.
Deleting the catalog and SQLite cache does not invalidate the canonical corpus.

## Stable v0.0.1 non-goals

The v0.0.1 contract does not include URL or PDF ingestion, embeddings,
semantic search, reranking, model-driven trust decisions, contradiction
detection, arbitrary record merging, backlink subsystems, MCP or API services,
a GUI, cloud sync, multi-user behavior, database canonical storage, background
workers, or Agentic Work OS coupling.

The Codex plugin is a distribution surface for the capture skill. It is not a
second storage or execution system.
