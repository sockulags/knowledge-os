---
name: ingest-source
description: Ingest one local Markdown or text source into Knowledge OS while preserving provenance and validating the resulting durable record.
tags:
  - ingest
  - ingestion
  - provenance
  - local-file
  - validation
---

# Ingest source

## Purpose and triggers

Use when a local `.md`, `.markdown`, or `.txt` file should become a raw, provenance-bearing Knowledge OS source. Do not use this as a claim-verification or synthesis step.

## Inputs

- One local source path.
- The Knowledge OS workspace root, inferred from the current directory or supplied with `--root`.

## Workflow

1. Inspect `SYSTEM.md`, `README.md`, and `indexes/`.
2. Run `kos ingest PATH`; it creates `sources/<stable-id>.md` only after validation and refreshes indexes.
3. Run `kos lint` to validate all durable records.
4. Use `kos inspect <id>` for the compact metadata and excerpt.
5. Use `kos index` to explicitly rebuild the catalog when other durable mutations occurred.
6. Use `kos search QUERY --limit N --json` for progressive disclosure rather than recursive reads.

## Allowed mutations

Only `kos ingest` may create the generated source and refresh generated indexes in this workflow. Do not hand-edit `indexes/catalog.md` or `indexes/catalog.sqlite3`; do not mutate durable knowledge or claim verification implicitly.

## Expected outputs

The command reports the stable source ID and an explicit index refresh. Re-ingesting identical bytes is a no-op. Search returns compact `id`, `title`, `type`, `status`, `scope`, `path`, and `snippet` fields.

## Verification

Confirm `kos lint` succeeds, `kos inspect <id>` shows the source provenance and excerpt, and `kos search` returns the expected body term. Run the relevant `unittest` suite after code changes.

## Failure behavior

Reject unsupported paths, invalid UTF-8, malformed metadata, divergent existing IDs, and invalid workspaces without writing partial durable content. Fix the reported path/message, then rerun `kos lint` and `kos index` as appropriate.

## Relevant scripts and references

- CLI: `kos ingest`, `kos lint`, `kos inspect`, `kos index`, `kos search`
- Contracts: `SYSTEM.md`, `README.md`, `docs/architecture.md`
