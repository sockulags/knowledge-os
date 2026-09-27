---
id: in-app-agent-over-acp
title: In-app agents run over ACP behind one provider contract
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-09-27'
updated: '2026-09-27'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-27:in-app-agent-provider
- kind: decision-acceptance
  reference: conversation:2026-09-27:in-app-agent-over-acp-accepted
  captured: '2026-09-27T20:31:48.756881Z'
related:
- agent-access
---

## Decision

The agent inside the app talks to a coding agent over the Agent Client
Protocol (ACP): JSON-RPC over the agent process's standard input and output,
through the official TypeScript SDK in the desktop app's main process. The app
does not drive an agent's terminal interface or parse its output.

Every agent provider implements one contract (identity, discovery, launch,
authentication, session options, small per-provider quirks, and
capabilities), and a shared ACP client owns everything else: the process, the
session, streamed updates, and permission requests. A provider is done when
it passes one provider-independent conformance suite run against a mock ACP
agent.

The first provider is Claude Code through `@agentclientprotocol/claude-agent-acp`,
which reuses the Claude Code login already on the computer. Codex through
`@agentclientprotocol/codex-acp` is the second and proves the contract. An API
key kept in the operating system's credential store may become a later
provider. Adapter versions are pinned and shipped with the app.

## Why

ACP gives structured streaming, tool calls, and permission requests instead of
terminal scraping, reuses the logins people already have, so no secret is
stored in the knowledge base, and lets one client serve several agents.
Projects that use it, such as kandev, show that the protocol is shared but the
adapters differ and change often; one contract with explicit per-provider
quirks and pinned versions keeps those differences in one place.

## How it is bounded

A session gets the knowledge base's own MCP server (`kos mcp`) as its only
MCP server, and each provider is told to disable its built-in file, shell,
and web tools. The in-app agent therefore has the same tools and the same
limits as external agents under `agent-access`: it cannot accept, withdraw,
supersede, or delete, its writes carry agent provenance, and they follow the
knowledge base's review rules. The client advertises no file or terminal
capabilities, and every permission request is put to the person rather than
approved automatically.
