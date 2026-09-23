---
id: write-approval-policy
title: Approval policy for automatic and interface writes
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-09-23'
updated: '2026-09-23'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-22:knowledge-os-product-vision
- kind: decision-acceptance
  reference: conversation:2026-09-23:write-approval-policy-accepted
  captured: '2026-09-23T07:02:02.598863Z'
related:
- knowledge-os-editable-interface
---

## Decision

Content reaches the knowledge base in two tiers. Ordinary notes and
documentation are written directly, whether a person types them in the app or
an agent, a repository scan, a meeting import, or pasted material produces them.
Decisions are always created as drafts and govern nothing until a person accepts
them.

## Why

Most automatic content is cheap to correct. Git history keeps every earlier
version, so a direct write can be undone without a review queue slowing capture
down. A decision is different: an accepted decision governs later work, so it
needs a deliberate human act. That act is the point of the exercise this
project exists for.

## How it is enforced

The core's create path refuses a decision whose status is not `draft`, for the
CLI and the local write API alike. Accepting, withdrawing, and superseding are
separate, explicit actions with their own provenance. Nothing an automatic
source writes can set a decision's status.

## Later

The policy may become configurable per document type, project, or folder, for
example to send meeting notes in one project to review before they are written.
Until that exists, the two tiers above apply everywhere.
