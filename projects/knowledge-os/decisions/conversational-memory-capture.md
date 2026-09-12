---
id: conversational-memory-capture
title: Conversational memory capture
type: project
status: active
scope: project:knowledge-os
record_kind: decision
created: '2026-08-29'
updated: '2026-08-30'
provenance:
  - kind: decision-acceptance
    reference: conversation:2026-08-29:durable-product-principle-and-conversational-capture
    captured: '2026-08-30T00:00:00Z'
---

## Decision

Knowledge OS should proactively identify potentially memorable information in conversations, while keeping the user in control of every proposed durable capture. The user may also say “save this” for an explicit direct-save path.

## Rationale

Durable memory should not depend on the user noticing and initiating every save, but unsolicited storage would make ordinary conversation unsafe and distracting. Proposals make the suggested content, destination, and reason visible before proactive capture.

## v0 conversational flow

1. During conversation, identify candidates without interrupting.
2. At a natural pause, batch candidates into a short proposal. For each item, show the proposed title, record destination and scope, content to retain, and why it appears durable.
3. Let the user approve, edit, or decline each proposal. Write only approved results and report what was saved.
4. Treat “save this” as direct save intent for the addressed content. If its content or destination is ambiguous, ask before writing; otherwise report the exact record saved.

The approved result is materialized through the create-only Knowledge OS
primitive `kos --root <ROOT> capture <approved-candidate.md> [--json]`. The
Knowledge OS Codex plugin ships the automatic detection, natural-pause proposal
batching, direct-save handling, and approval workflow. It supplies the explicit
configured root for cross-chat reachability; capture validates and indexes the
candidate but does not infer meaning or approval.

The plugin is distributed by this repository as `knowledge-os` with the
automatic `knowledge-os-capture` skill. It has no Agent OS or Agentic Work OS
dependency. Standalone means the skill and companion CLI source are owned and
distributed here, not that a clean plugin install has zero prerequisites: the
skill may offer one explicit, one-time package installation from the plugin
root, after user approval, when `knowledge_os` is not importable.
The selected launcher detects whether `sys.prefix != sys.base_prefix`; setup
installs without `--user` in an active virtual environment and uses `--user`
otherwise.

Decisions default to the current project scope. Reusable lessons use general knowledge or the current project scope as appropriate. Recurring user preferences use user memory, with a project scope when the preference is project-specific.

## Capture criteria

Propose only a durable decision, reusable lesson, or recurring preference with enough context to state what should be retained and where it belongs.

## Do not capture

Do not proactively propose ordinary chatter, tentative ideas, one-off tasks, transient facts, or content with no clear durable destination. Explicit “save this” intent may override this trigger rule, but not the trust rules below.

## Trust handling and boundary

Saving records provenance and preserves uncertainty or attribution; it does not verify a claim. Uncertain content must remain an unverified draft or raw source and must never be presented as established knowledge without separate review and evidence. v0 covers conversation detection, batched proposals, user confirmation, and canonical record writing only. It does not add silent saving, background workers, runtime automation, semantic fact checking, or model-controlled verification.
