---
id: configurable-review-policy
title: Configurable review for automatic and interface writes
type: project
record_kind: decision
status: draft
scope: project:knowledge-os
created: '2026-09-27'
updated: '2026-09-27'
provenance:
- kind: user-request
  reference: github:sockulags/knowledge-os#86
supersedes:
- write-approval-policy
related:
- agent-access
---

## Decision

Content still reaches the knowledge base in two tiers by default: notes are
written directly, and decisions are always created as drafts that govern
nothing until a person accepts them.

A knowledge base may send some note writes to review instead, with rules in
its own `knowledge-os.toml`. A rule names who writes (an agent, one agent
client, the Referat import, or a person in the app), where (a project,
general knowledge, or a folder and everything below it), and which writes
(new pages, edits, or both), and says `review` or `direct`. The first rule
that matches decides; no match means direct. Without rules nothing changes.

A write that needs review is validated exactly as if it were applied and is
stored as a proposed change in `proposals/`, a new page or an edit against
the page's current revision. It waits in Decide next to proposed decisions,
where a person accepts or discards it in one click with Undo. Accepting
applies it with the direct write's rules, and an edit whose page changed in
the meantime can only be discarded.

## Why

Agents and meeting imports now write more than people type, and some places
in a knowledge base deserve a look before anything lands there. The owner of
the knowledge base, not the code, should decide where that is. Keeping the
rules in the knowledge base's own file means they are versioned, synced, and
read the same way by the app, the MCP server, and every import.

## How it is enforced

The rules are applied in the core's local write API, which the app, `kos
mcp`, and the Referat import all use, so they apply the same way to each. An
agent is told in its tool result that its write waits for review and that
nothing was written. If the rules cannot be read, every write they would
govern is refused rather than let through unreviewed. Decisions are not
governed by the rules: they remain drafts, accepted, withdrawn, or
superseded only by a person. The command line writes directly, as before.

## Consequences

A proposed change is a plain Markdown file committed like other writes, so
it syncs to other computers and survives restarts. Proposals are not records:
they are not indexed, linted, or given to agents as context until accepted.
