---
id: knowledge-os-operations
title: Knowledge OS operations
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
    reference: docs/architecture.md
  - kind: repository-file
    reference: knowledge_os/cli.py
---

# Knowledge OS operations

Use this guide for local Knowledge OS work. Markdown under managed roots is
canonical. Catalog and SQLite files are generated indexes.

## Setup

Create a Python 3.11 or newer virtual environment and install the package in
editable mode.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
kos lint
kos index
```

Use the equivalent `python3.11` commands on macOS or Linux. Run commands from
the workspace or pass `--root PATH`.

## Workspace discovery

`knowledge-os.toml` marks a workspace. `kos` discovers it from the current
directory and its parents. Use `--root PATH` when the command runs elsewhere.

The managed roots are `knowledge/`, `projects/`, `memory/`, `syntheses/`,
`discoveries/`, `sources/`, and `skills/`. `inbox/` is untrusted intake.

## Canonical and generated data

Markdown records are canonical and may be versioned with Git. Sources are raw
material. Discoveries are evidence backed observations with a separate review
status. Neither source claims nor retained discoveries become established
knowledge automatically.

`indexes/catalog.md` and `indexes/catalog.sqlite3` are disposable outputs from
`kos index`. Context packages and discovery review packets are also generated
and not canonical. Do not edit generated files by hand.

## Normal read loop

1. Run `kos lint` when the corpus or its validity is uncertain.
2. Run `kos search QUERY` to find candidate records in the existing index.
3. Run `kos inspect ID` to check metadata, provenance, trust, and the exact
   content hash. Add `--full` when the body is required.
4. Treat `sources/` as raw claims and `discoveries/` as reviewed observations,
   not as established knowledge.
5. Use `kos context` only after the corpus and indexes are current.

## Approved write loop

1. Prepare a complete candidate with valid metadata, a body that is not empty, and
   provenance.
2. Obtain approval before creating a durable record.
3. Use `kos capture CANDIDATE.md` for an approved record created only once. Use
   `--project-path PATH` for a nested project path.
4. Use `kos update PATH --expected-sha256 HASH` for a conflict safe replacement.
5. Use `kos decision accept` for a draft decision and `kos supersede` for an
   accepted replacement.
6. Use the discovery commands for proposed observations. Review first, then
   retain, reject, or promote exactly one outcome.

The CLI validates the current and intended corpus under one workspace lock. It
refreshes generated indexes after successful canonical writes.

## Verification after a change

Run `kos lint` after every canonical change. Run `kos index` after lint passes
to rebuild generated indexes. Run the relevant `kos inspect`, `kos search`,
`kos context`, or `kos context verify` command when the change affects that
operation.

See the detailed records for command contracts and recovery rules:

- [Knowledge OS CLI](knowledge-os-cli.md)
- [Knowledge OS context export](knowledge-os-context-export.md)
- [Knowledge OS review and recovery](knowledge-os-review-recovery.md)
