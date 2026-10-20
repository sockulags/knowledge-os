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

Use when a local `.md`, `.markdown`, or `.txt` file should become a raw, provenance-bearing Knowledge OS source. Do not use this as a claim-verification or synthesis step; sources remain searchable for audit but are excluded from default context.

## Inputs

- One local source path.
- The Knowledge OS workspace root, `<root>`: `KNOWLEDGE_OS_ROOT`, or else `workspace` under `[knowledge_os]` in `~/.knowledge-os/config.toml`. Never infer it from the current directory, which is usually another repository. When neither names a directory containing `knowledge-os.toml`, do nothing and say that no workspace is configured.
- A Python launcher, `<python>`, proven to be Python >=3.11 that imports `knowledge_os` (`py -3.11` or `py -3` on Windows, `python3.11` or `python3` elsewhere). The `knowledge-os-capture` skill's CLI fallback shows the probe and the one-time setup; without a launcher, do nothing.

Run every command as `<python> -m knowledge_os --root <root> ...`, never as a bare `kos`.

## Workflow

1. Inspect `SYSTEM.md`, `README.md`, and `indexes/` in `<root>`.
2. Run `<python> -m knowledge_os --root <root> ingest PATH`; it creates `sources/<stable-id>.md` only after current and intended-state validation, then refreshes disposable indexes under the workspace mutation lock.
3. Run `<python> -m knowledge_os --root <root> lint` to validate all durable records.
4. Use `<python> -m knowledge_os --root <root> inspect ID` for the compact metadata and excerpt.
5. Use `<python> -m knowledge_os --root <root> index` to explicitly rebuild the catalog when other durable mutations occurred.
6. Use `<python> -m knowledge_os --root <root> search QUERY --limit 10 --json` for progressive disclosure rather than recursive reads.

## Allowed mutations

Only the `ingest` command may create the generated source and refresh generated indexes in this workflow. Do not hand-edit `indexes/catalog.md` or `indexes/catalog.sqlite3`; do not mutate durable knowledge or claim verification implicitly.

## Expected outputs

The command reports the stable source ID and an explicit index refresh. Re-ingesting identical bytes is a no-op. Search returns compact `id`, `title`, `type`, `record_kind`, `status`, `scope`, `path`, and `snippet` fields.

## Verification

Confirm `lint` succeeds, `inspect` shows the source provenance and excerpt, and `search` returns the expected body term. When working on the Knowledge OS repository itself, run its relevant `unittest` suite after code changes.

## Failure behavior

Reject unsupported paths, invalid UTF-8, malformed metadata, divergent existing IDs, and invalid workspaces without writing partial durable content. Fix the reported path/message, then rerun `lint` and `index` as appropriate.

## Relevant scripts and references

- CLI commands (each run as `<python> -m knowledge_os --root <root> COMMAND`): `ingest`, `lint`, `inspect`, `index`, `search`
- Contracts: `SYSTEM.md`, `README.md`, `docs/architecture.md`
