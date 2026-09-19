---
id: knowledge-os-reader
title: Read-only reader for Knowledge OS
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-12'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-12:knowledge-os-reader-planning
- kind: decision-acceptance
  reference: conversation:2026-09-12:knowledge-os-reader-batch-approval
  captured: '2026-09-12T17:25:26.389843Z'
---

## Decision

Knowledge OS gets a human reading surface: a local, read-only reader over an
existing workspace. It never writes to the workspace and introduces no competing
data model.

## Why this needs a decision

The frozen v0.0.1 contract lists a GUI among the things the product does not
include. A reader is therefore a contract change and cannot be introduced as
ordinary implementation work.

## Boundaries

Exactly one module reads through the `knowledge_os` library and returns plain
data. Views never import the core directly, never parse YAML, and never
reimplement validation, trust classification, or lifecycle rules. Markdown stays
canonical. The reader adds no record type, status, metadata field, or cache of
its own.

Out of scope: every write path, capture, acceptance and supersession from the
interface, authentication, remote or shared hosting, sync, and real-time
collaboration. The reader binds to localhost and serves one workspace per
process.

## Compatibility with the pivot

The draft `openknowledge-pivot` decision says not to compete on storage,
editing, search, linking, agent integration, or Git collaboration, and not to
extend the standalone product direction before a comparison finds a material
capability that OpenKnowledge and OKF lack. A read-only projection stays inside
that instruction and serves the evaluation it asks for, by making
approval-gated capture, trust boundaries, discovery review, and context export
legible enough to judge. An editing or shared-service surface would not, and
would collide with the open question of who owns canonical writes after a pivot.

The governance compatibility gate reaches the same shape from the write side:
the local CLI remains the reference backend, and an adapter may change how bytes
are read and committed as long as the observable outcomes survive. This reader is
the read-side mirror of that boundary, so a backend change replaces the adapter
and not the views.

## Uncertainty

Whether the reader stays in this repository or moves to its own package after a
pivot is not decided here.
