---
id: page-ids-fold-accents
title: Page ids made from titles fold accented letters
type: project
record_kind: decision
status: draft
scope: project:knowledge-os
created: '2026-10-17'
updated: '2026-10-17'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-10-17:simplifier-audit
related:
- knowledge-os-editable-interface
- agent-access
---

## Decision

Every place that turns a title or a name into a page id uses one rule:
accented letters fold to their plain letter, everything else that is not a
lowercase letter or digit becomes a hyphen. "Skärmbild från mötet" becomes
`skarmbild-fran-motet`. In the core the rule is `knowledge_os.model.kebab`;
the agent tools keep a copy because they import no core modules, and a test
keeps the two in step. The reader UI already worked this way.

## Why

The same title gave different ids depending on where the page was made.
Ingest, attachments and the reader UI folded accents, while the reader's
decision drafts, the agent tools, workspace names and folder ids dropped
them, so "Skärm" became `sk-rm` there. One rule removes six copies of the
code and makes ids predictable.

## What changes

Only new ids change, and only for names with accented letters made by the
agent tools, documentation-check decision drafts, `kos init` workspace
names and new folder ids. Existing pages keep their ids.
