---
id: agent-access
title: How agents work with the knowledge base
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-09-23'
updated: '2026-09-23'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-23:agent-access
- kind: decision-acceptance
  reference: conversation:2026-09-23:agent-access-accepted
  captured: '2026-09-23T18:11:20.890754Z'
related:
- write-approval-policy
- knowledge-os-editable-interface
---

## Decision

Agents get their own narrow interface to the knowledge base: an MCP server.
People and scripts keep the `kos` command line. The first agents to use it are
Claude Code and Codex working in other repositories, where decisions and
lessons come up during coding.

Through MCP an agent can search and read, write notes, and propose decisions as
drafts. It has no tool to accept, withdraw, or replace a decision; those stay
human actions in the app or the command line.

## How it works

The MCP server works through the running desktop app's local API, against the
knowledge base that is open there. Agents can only use the knowledge base while
the app is open; when it is closed, the tools say so instead of writing
anything. Going through the app means agent writes get the same validation,
conflict checks, and automatic Git commits as your own edits, and you can see
them appear as they happen.

It follows `write-approval-policy`: notes an agent writes are saved directly,
and decisions are always drafts. Every agent write records which agent wrote it
and from where in its provenance, so the decision inbox and the history show
who proposed what.

## Why

A dedicated tool surface keeps agents to the actions they should take and
labels their work without relying on each agent to do it right. The same tools
can later serve agents that run inside the app, so the agent interface is built
once.

## Limits

This is a guardrail, not a lock. An agent with shell access can still run the
command line or edit files directly. The protection is visibility: provenance
and Git history make every agent write and every acceptance traceable.
