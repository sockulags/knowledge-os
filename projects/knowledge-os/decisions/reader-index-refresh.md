---
id: reader-index-refresh
title: The reader may rebuild stale search indexes
type: project
record_kind: decision
status: draft
scope: project:knowledge-os
created: '2026-10-13'
updated: '2026-10-13'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-10-13:reader-index-refresh
related:
- knowledge-os-editable-interface
- knowledge-os-reader
---

## Decision

When the reader finds the search index stale or missing, it rebuilds it in the
background through the same entry point as `kos index`, under the same
workspace lock. It never changes records or any other canonical file to do
this. `kos-read --no-index-refresh` turns the rebuild off.

## Why

The desktop app has no terminal, so a notice telling a person to run
`kos index` leaves them stuck with incomplete search. Indexes are disposable:
canonical Markdown is the source of truth, and `kos index` would write the
same files. The promise that matters is that the reader never touches a
person's records, and that promise still holds.

## What changes

Acceptance criterion 1 of the reader v1 plan said serving leaves the
workspace byte-identical. It now covers canonical files only; files under
`indexes/` may be rewritten when they are stale. The read-only guard test
allows `rebuild_indexes` in the reader's adapter module and nowhere else in
the reader.

A repository that tracks generated index files in Git, as this one does with
`indexes/catalog.md`, can see those files change after the reader runs.
Workspaces made with `kos init` ignore their indexes and are not affected.
