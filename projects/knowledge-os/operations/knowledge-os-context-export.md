---
id: knowledge-os-context-export
title: Knowledge OS context export
type: project
status: active
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-12'
provenance:
  - kind: repository-file
    reference: knowledge_os/context.py
  - kind: repository-file
    reference: knowledge_os/context_policy.py
  - kind: repository-file
    reference: knowledge_os/context_verify.py
  - kind: repository-file
    reference: docs/architecture.md
  - kind: repository-file
    reference: README.md
---

# Knowledge OS context export

`kos context` emits a `kos-context/v1` Markdown package to standard output. The
package is read only, generated, and not canonical.

## Inputs

An export requires `--project ID`, `--task TEXT`, and `--budget N`. `--work-item
TEXT` adds optional task terms. Repeat `--require ID` to add mandatory records.
The project and required IDs must use lowercase kebab case. The task and work
item must not be empty. The budget must be an integer of at least `1`.

The workspace must pass validation and have a current SQLite index. Export
does not rebuild indexes. The requested project must have exactly one usable
overview with `type: project`, matching ID and scope, and `draft` or `active`
status.

## Eligibility

Ordinary context records use types `knowledge`, `project`, `memory`, and
`synthesis`, with `draft` or `active` status. Their scope must be `general` or
`project:<ID>`. Sources are excluded even when their text matches the task.
Other project scopes and ineligible lifecycle states are excluded.

Retained discoveries are eligible only when their scope is the requested
project. They remain labeled as reviewed observations and not established
knowledge.

Skills are eligible when at least two distinct request terms match the skill
name, description, or tags. Matching the skill body does not activate skill
selection.

Required records use the same type, scope, status, and trust policy as ranked
records. `--require` cannot import another project's record or bypass an
ineligible status.

Selection uses deterministic lexical FTS matching, metadata, explicit
relationships, and one hop relationship expansion. The project overview is
always mandatory. Other mandatory records follow it. Optional candidates are
ranked deterministically.

## Hard budget behavior

The estimator is `ceil(unicode_character_count / 4)` over the complete rendered
package. The estimate includes the manifest, item metadata, headers, and item
bodies.

Every mandatory item must fit in full. If the project overview and required
records exceed the budget, export fails instead of truncating them. Optional
records are added greedily only when the complete package remains within the
budget. No record is partially rendered.

The manifest records the configured budget, used estimate, estimator, ranked
candidate count, count excluded by the budget, and up to ten excluded IDs.

## Manifest hashes

The manifest identifies contract `kos-context/v1` and the workspace identity.
Workspace identity contains the configured name, schema version, and the
SHA-256 of `knowledge-os.toml`.

Each selected record or skill includes its path, type, scope, status, trust
label, provenance, selection evidence, and exact `content_sha256`. A record
with a `verified` date also exposes that date. The hash covers the current
canonical file bytes used for the package.

## Context verification

`kos context verify PACKAGE.md` reads the package manifest and compares it with
the current workspace. It reports one item status for each selected record or
skill:

- `unchanged` means the item is eligible, at the recorded path, and has the
  recorded hash.
- `changed` means the item exists but its path or hash differs.
- `missing` means the item is absent.
- `ineligible` means the item exists but no longer passes context policy.

Verification separately reports whether workspace identity matches. The JSON
result has `ok: true` only when the workspace has no current validation issues,
workspace identity matches, and every item is `unchanged`.

### Example

```powershell
kos --root examples/context-workspace context `
  --project knowledge-os `
  --task "Preserve provenance during URL ingestion" `
  --budget 12000 > context.md
kos --root examples/context-workspace context verify context.md --json
```
