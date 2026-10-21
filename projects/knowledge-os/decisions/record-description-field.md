---
id: record-description-field
title: Every record may carry an optional one-line description
description: Why records have an optional description field and how it is used.
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-10-21'
updated: '2026-10-21'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-10-21:agentbeslut
- kind: decision-acceptance
  reference: conversation:2026-10-21:record-description-field-accepted
  captured: '2026-10-20T23:41:17.894048Z'
related:
- knowledge-os-editable-interface
---

## Decision

`description` is an optional metadata field on every record type. When
present it is a non-empty string summing up the page in a sentence. It is
the only new field: unknown metadata fields are still rejected.

The reader shows it under the title, the editor changes it like the title,
and the reader API returns it with a page (`null` when it is absent). A
record without a description stays valid; nothing fills one in on its own.

## Why

A title alone often does not say what a page covers, and the reader had no
place for a short summary other than the first paragraph of the body. A
separate field keeps the summary out of the body, can be shown wherever
the title is, and is cheap to leave out.
