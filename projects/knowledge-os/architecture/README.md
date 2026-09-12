---
id: knowledge-os-architecture
title: Knowledge OS architecture
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
    reference: indexes/catalog.md
  - kind: repository-file
    reference: docs/architecture.md
  - kind: repository-file
    reference: knowledge_os/model.py
  - kind: repository-file
    reference: knowledge_os/context_policy.py
  - kind: repository-file
    reference: knowledge_os/workspace.py
  - kind: repository-file
    reference: projects/knowledge-os/README.md
  - kind: repository-file
    reference: projects/knowledge-os/architecture/project-layout/README.md
  - kind: repository-file
    reference: projects/knowledge-os/decisions/openknowledge-pivot.md
---

# Architecture records

This folder describes the implemented v0.0.1 system contract. Markdown records
are canonical. The CLI validates records, indexes them, searches them, exports
bounded context, reviews discoveries, and captures approved records.

Read the [system model](knowledge-os-system-model.md) for ownership, flow,
trust boundaries, mutation, recovery, and non-goals.

Read the [record model](knowledge-os-record-model.md) for managed roots,
metadata, scope, lifecycle, provenance, discovery review, context eligibility,
and disposable indexes.

The [project layout record](project-layout/README.md) defines project directory
placement and project root records.

The [OpenKnowledge pivot decision](../decisions/openknowledge-pivot.md) is a
draft evaluation decision. It does not describe current system behavior.
