---
id: knowledge-os-editable-interface
title: Editable desktop interface for Knowledge OS
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-09-22'
updated: '2026-09-22'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-22:knowledge-os-product-vision
- kind: decision-acceptance
  reference: conversation:2026-09-22:knowledge-os-editable-interface-accepted
  captured: '2026-09-22T21:02:52.585291Z'
supersedes:
- knowledge-os-reader
related:
- standalone-learning-direction
---

## Decision

The Knowledge OS interface may write to the workspace. From the desktop app a
person can create and edit Markdown records and accept, withdraw, and supersede
decisions. This replaces the read-only boundary in `knowledge-os-reader`.

## Why this needs a decision

`knowledge-os-reader` made the interface read-only, partly to stay inside the
now-withdrawn OpenKnowledge pivot. With `standalone-learning-direction`
accepted, the product is a local desktop app for documentation and knowledge,
and editing and acting on decisions are its core use.

## Boundaries

Markdown stays canonical and the SQLite index stays disposable. Every write from
the interface goes through the core's existing validation and mutation code and
is guarded by the SHA-256 of the file it replaces, as `kos update` is; a stale
write is refused, never merged silently. The interface adds no data model of its
own, and exactly one adapter module talks to the core.

Automatic and agent-written content follows an approval policy: ordinary notes
are written directly with Git history as the safety net, while decisions are
always created as drafts and need explicit acceptance. The policy may later be
configured per document type, project, or folder.

Still out of scope: authentication, remote or shared hosting, and real-time
collaboration. The app runs locally, serves one workspace per core process, and
syncs through Git on request.
