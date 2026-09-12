---
id: knowledge-os-review-recovery
title: Knowledge OS review and recovery
type: project
status: active
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-12'
provenance:
  - kind: repository-file
    reference: knowledge_os/discovery.py
  - kind: repository-file
    reference: knowledge_os/mutations.py
  - kind: repository-file
    reference: knowledge_os/workspace.py
  - kind: repository-file
    reference: docs/architecture.md
  - kind: repository-file
    reference: SYSTEM.md
---

# Knowledge OS review and recovery

Review packets propose decisions. They do not change canonical records or
decide whether an observation is true.

## Discovery outcomes

`kos discovery add PATH` creates a `proposed` discovery from structured
Markdown. The input must have no review events.

`kos discovery review ID` renders deterministic lexical and explicit link
matches. Human review must select exactly one outcome:

- `retain` changes a proposed discovery to `retained`. The discovery must use
  a project scope and remains a reviewed observation, not established
  knowledge.
- `reject` changes a proposed or retained discovery to terminal `rejected` and
  requires a reason.
- `promote` creates a new `draft` knowledge or project record and changes the
  discovery to terminal `promoted`. The target provenance points directly to
  the discovery, and the discovery review points to the target.

Promotion is promote new only. It never overwrites, merges, or supersedes an
existing record. Related records require `--acknowledge-related`. A
project scoped discovery can target only the same project unless
`--allow-scope-broadening` is supplied for a general target.

## Decision acceptance and supersession

A draft decision is proposed and does not govern. `kos decision accept ID`
requires the exact current content hash and an acceptance reference. It changes
the decision to `active` and adds decision acceptance provenance. A draft that
declares `supersedes` must use `kos supersede` instead.

An accepted decision body may receive only an update that is not material.
That update requires the exact current hash, `--confirm-non-material`, and a
`--change-reference` value that is not empty. A material change starts as a new draft.

`kos supersede OLD_ID NEW_ID` requires exact hashes for both records and an
acceptance reference. The old decision must be active. The replacement must be
draft, use the same scope, and declare exactly the old decision in
`supersedes`. The operation activates the replacement and marks the old
decision `superseded`. Competing draft replacements are refused.

Active and superseded decisions require decision acceptance provenance. A
decision transition records authority. It does not prove implementation or
verify factual claims.

## Shared locking and write order

Ingest, capture, update, decision acceptance, decision supersession, discovery
mutations, and index replacement use one workspace scoped advisory mutation
lock.

Each mutation follows this order:

1. Acquire the lock and validate the current canonical corpus and skills.
2. Validate the intended result in a disposable staged workspace.
3. Write the required canonical Markdown files with atomic replacement or
   exclusive creation.
4. Rebuild the disposable indexes.
5. Release the lock.

Canonical Markdown remains authoritative. Catalog and SQLite files remain
derived state.

## Recovery limits

The lock serializes cooperating processes. It is not a write ahead log or a
transaction over multiple files. Discovery promotion and decision supersession are not
crash atomic.

Promotion writes the new target before it updates the discovery. An abrupt stop
can leave partial promotion lineage. Supersession writes the replacement first
and then the old decision. A caught write failure attempts to restore both
original files, but process termination can still leave a partial replacement.

If canonical writes succeed and index rebuilding fails, canonical Markdown
remains authoritative. There is no rollback or journal for the derived index
failure.

## Exact recovery checklist

Use this checklist after a reported partial lineage, partial replacement, or
index failure:

1. Inspect every affected canonical Markdown record, including status,
   provenance, review target, and `supersedes` fields.
2. Run `kos lint` and record every reported issue.
3. Repair only the affected canonical Markdown so the intended lineage and
   lifecycle are explicit.
4. Run `kos lint` again and stop if it fails.
5. Run `kos index` to rebuild `indexes/catalog.md` and
   `indexes/catalog.sqlite3`.
6. Run `kos lint` once more.
7. Re-run the affected read operation, such as `kos discovery review`,
   `kos inspect`, `kos search`, or `kos context verify`.

Deleting both generated index files does not invalidate canonical Markdown.
Run the same checklist beginning with `kos lint`, then `kos index`.
