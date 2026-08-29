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

## Invariants

Duplicate IDs, filename/type mismatches, malformed metadata, invalid digests, invalid relationships, and unresolved local links prevent indexing. Ingest IDs include a bounded source slug and 64-bit SHA-256 prefix; provenance retains the full digest, and a detected ID collision is never overwritten. Identical ingest is idempotent. Generated artifacts are atomically replaced where practical.

## Deliberately postponed

Context export, promotion/maintenance, source variants and URLs, backlinks, remote synchronization policy, and evidence-gated embeddings are future decisions. No server, GUI, vector database, MCP implementation, or hidden memory layer is part of this slice.
