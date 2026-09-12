---
id: knowledge-os
title: Knowledge OS project overview
type: project
status: active
scope: project:knowledge-os
created: '2026-08-29'
updated: '2026-09-12'
provenance:
- kind: project-definition
  reference: conversation:2026-08-29:knowledge-os-product-contract
- kind: repository-documentation
  reference: conversation:2026-09-12:populate-knowledge-os-project
---

Knowledge OS is a local-first, filesystem-native knowledge store. Markdown
records are canonical. The project owns provenance, validation, indexing,
bounded context, discovery review, and approved capture. Sources and
discoveries remain separate trust boundaries. Agentic Work OS owns execution
and orchestration.

## Project documentation

- [Architecture](architecture/README.md) describes the system, record model,
  trust boundaries, and project layout.
- [Operations](operations/README.md) describes setup, CLI use, context export,
  review, verification, and recovery.
- [Decisions](decisions/) contains accepted and proposed project decisions.

## Current boundary

Version 0.0.1 excludes background workers, model-driven trust decisions,
semantic fact checking, and runtime automation. The
[OpenKnowledge pivot](decisions/openknowledge-pivot.md) remains a draft
decision. The proposed reader plan under `docs/plans/` is not an accepted
product contract.
