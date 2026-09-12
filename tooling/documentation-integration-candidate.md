---
id: documentation-integration
title: Documentation integration
type: project
record_kind: decision
status: draft
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-12'
provenance:
  - kind: user-request
    reference: conversation:2026-09-12:documentation-integration
---

## Decision

Knowledge OS provides one documentation skill with global initialization,
repository initialization, and normal documentation maintenance.

Global initialization is a one-time, user-authorized operation. It stores the
Knowledge OS workspace location and adds a short managed instruction block to
the user-level Codex and Claude files. Normal retrieval may use task-relevant
general knowledge and memory, but search relevance does not verify a record.

Repository initialization creates a portable `.knowledge-os-project.toml`
binding. One repository may bind one or more Knowledge OS projects to relative
paths. The longest matching path selects the project inside a monorepo.

The skill searches before inspection, reads the affected project context and
folder root records, and writes only when the current request or repository
policy authorizes documentation changes. It does not capture conversational
memory. The `knowledge-os-capture` skill owns that workflow.
