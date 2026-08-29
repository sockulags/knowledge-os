---
id: url-ingestion-provenance
title: URL ingestion and provenance decision
type: project
status: draft
scope: project:knowledge-os
created: '2026-08-29'
updated: '2026-08-29'
provenance:
  - kind: fixture
    reference: examples/context-workspace/projects/url-ingestion-provenance.md
tags:
  - url
  - ingestion
  - provenance
related:
  - provenance-boundaries
---

URL ingestion is postponed until the source model can retain the original URL, capture date, retrieved bytes, and a SHA-256 digest. The implementation must preserve provenance rather than silently turning a remote claim into verified knowledge.
