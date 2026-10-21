---
id: in-app-agent-provider-isolation
title: In-app agents run over ACP, and Codex is turned on by the person because it
  is less isolated
description: How the in-app agent is bounded per provider, and why Codex needs an
  explicit opt-in.
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-10-21'
updated: '2026-10-21'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-10-21:agentbeslut
- kind: decision-acceptance
  reference: conversation:2026-10-21:agentbeslut-codex-opt-in
  captured: '2026-10-20T23:41:18.517610Z'
supersedes:
- in-app-agent-over-acp
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

The providers are Claude Code through `@agentclientprotocol/claude-agent-acp`
and Codex through `@agentclientprotocol/codex-acp`, each reusing the login
already on the computer. Adapter versions are pinned to the version tested
and installed on demand, each npm package checked against its integrity hash,
rather than shipped with the app: the Claude adapter depends on Anthropic's
proprietary Claude Agent SDK, which the person fetches themselves.

## How it is bounded

Every session gets the knowledge base's own MCP server (`kos mcp`). The
client advertises no file or terminal capabilities.

The knowledge base's read tools run without asking: `search`, `read_page`,
`list_projects`, `list_folder`, `list_proposed_decisions`,
`list_proposed_changes`, `read_proposed_change`, `check_documentation`, and
`read_commit`. They are the tools marked `read_only` in
`knowledge_os/agent_access/tools.py`; the desktop app lists them as
`KOS_READ_TOOLS` in `desktop/src/main/agents/acpSession.ts`, and
`readTools.test.ts` fails when the two lists differ. A call counts as one of
them only when every field that names the tool names the same `kos mcp` tool.
Every write and every other tool, including the agent's own, is put to the
person with the tool's input shown, so they see what it would write or run.

Through `kos mcp` the in-app agent has the same limits as external agents
under `agent-access`: it cannot accept, withdraw, supersede, or delete, its
writes carry agent provenance, and they follow the knowledge base's review
rules.

Claude Code is told to disable its built-in file, shell, and web tools, and
`kos mcp` is its only MCP server.

Codex has no switch that removes its built-in tools, and the MCP servers in
the person's own `~/.codex/config.toml` load as well. The session starts in
codex-acp's `read-only` mode: Codex's read-only sandbox blocks writing files
and the network, but does not limit which files can be read, and its
`on-request` approval lets commands that stay inside the sandbox run without
asking. Codex can therefore read files anywhere the person's account can,
not only the knowledge base, without a permission request. Writes and network
access still need the person's permission.

Because of that, Codex is not used until the person turns it on in the agent
panel, after a notice that says what it can read. While Codex is the agent,
the panel keeps a notice saying its isolation is weaker than Claude Code's.

## Why

ACP gives structured streaming, tool calls, and permission requests instead of
terminal scraping, reuses the logins people already have, so no secret is
stored in the knowledge base, and lets one client serve several agents.
Projects that use it, such as kandev, show that the protocol is shared but the
adapters differ and change often; one contract with explicit per-provider
quirks and pinned versions keeps those differences in one place.

Asking before every read of the knowledge base made the agent slow to use
without protecting anything: the read tools see only what the person can
already read in the app. Codex stays available because it is the second
provider that proves the contract and some people only have a Codex login,
but its weaker isolation is the person's choice to make, not a default.
