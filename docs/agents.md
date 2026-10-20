# Agents and Knowledge OS

Agents such as Claude Code and Codex use a knowledge base through an MCP server, `kos mcp`, and
through the skills in this repository's plugin. People and scripts use the desktop app and the
`kos` command line. This page covers the agent side: installing the plugin, what the MCP server
offers and refuses, how agent writes are labelled, and the skills. The contract behind it is "Agent
access over MCP" in [`architecture.md`](architecture.md); the accepted decision is
`projects/knowledge-os/decisions/agent-access.md`.

## Install the plugin

The plugin is distributed from this repository through `.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json` for Claude Code, and through `.codex-plugin/plugin.json` and
`.agents/plugins/marketplace.json` for Codex. It contains the skills and registers the
`knowledge-os` MCP server.

- Claude Code:

  ```
  /plugin marketplace add sockulags/knowledge-os
  /plugin install knowledge-os
  ```

  Without the plugin, register only the server: `claude mcp add knowledge-os -- kos mcp` (add
  `--scope user` to use it in every project).
- Codex: install the `knowledge-os` plugin from this repository's marketplace;
  `.codex-plugin/mcp.json` registers the server. Without the plugin, add to
  `~/.codex/config.toml`:

  ```toml
  [mcp_servers.knowledge-os]
  command = "kos"
  args = ["mcp"]
  ```

`kos` comes from the desktop app installer, which puts it on PATH with the MCP server built in, or,
in a checkout, from `pip install -e ".[reader,mcp]"`.

## How the server reaches the knowledge base

`kos mcp` works only through the running desktop app: it talks to the app's local API and acts on
the knowledge base open there, so agent writes get the same validation, conflict checks, and Git
commits as your own edits and show up in the app as they happen. When the app is closed or no
knowledge base is open, every tool says so and nothing is written. Open the knowledge base in the
app before asking the agent to use it.

The server finds the app through a runtime file the app keeps in its user-data folder while a
knowledge base is open (see "Agents and the runtime file" in
[`desktop-architecture.md`](desktop-architecture.md)).

## Tools

| Tool | What it does |
| --- | --- |
| `search` | Search by words and, with the search model installed, by meaning (`query`, optional `project`, `limit`). |
| `read_page` | One page by `id`: Markdown content, state, project, folder, links, provenance, and `content_sha256`. |
| `list_projects` | Project ids, titles, and top-level folders. |
| `list_folder` | A project folder's overview, pages, and subfolders (`project`, optional `folder`). |
| `write_note` | Create a note (`title`, `content`, optional `project`, `folder`, `tags`, `status`, and `destination: memory` for a preference) or edit one (`id`, `content`, `expected_sha256`). Decisions cannot be edited. A write the review rules hold back answers `waiting_for_review` and writes nothing yet. |
| `propose_decision` | Create a decision as a draft (`title`, `content`, optional `project`, `folder`, `supersedes`, `related`). |
| `list_proposed_decisions` | The Decide inbox: drafts waiting for a person, with who proposed them. |
| `list_proposed_changes` | Writes the review rules held back, waiting in Decide: new pages and edits, with the rule and who proposed them. |
| `read_proposed_change` | One proposed change: a new page's Markdown, or an edit as a diff against the page as it is now. |
| `check_documentation` | What changed in a project's linked code repositories since the last check, and the page updates and decisions that suggests, with their commits. Read-only. |
| `read_commit` | One commit of a linked repository: message, files, and diff. |
| `propose_documentation_decision` | Draft a decision the check suggests (`key`), with its commits as provenance. |
| `mark_documentation_checked` | Record the commit a check covered, so the next check starts there. |
| `link_repository` | Link a Git repository (absolute `path`) to a project. |

There is no tool to accept, withdraw, or supersede a decision; those stay yours, in the app or the
command line. Failures come back as structured results with an `error` kind (`app_not_open`,
`app_not_responding`, `conflict`, `duplicate`, `validation`, `not_found`, `not_allowed`, ...), a
`message`, a `next_step`, and whether anything was `written`.

## Provenance of agent writes

Every agent write carries provenance `agent-authored` with reference `agent:<client>:<place>`:
the client name the agent reports over MCP (`claude-code`, `codex-mcp-client`, ...) and where it
ran, which is `kos mcp --place LABEL`, else `KOS_AGENT_PLACE`, else the name (never the path) of
the directory the agent started the server in. The app shows it as "Proposed by Claude Code in
my-repo", and the commit reads `Claude Code: Create <title>`. This is a guardrail, not a lock: an
agent with shell access can still run `kos` or edit files; provenance and Git history make its
writes visible. The review rules in `knowledge-os.toml` (see "Review before writes land" in the
[README](../README.md)) can hold agent writes back for a person to accept.

## The agent inside the app

The desktop app has its own agent panel (Ctrl+J, or the robot button in the reader): it runs the
Claude Code or Codex you installed over the Agent Client Protocol with `kos mcp` as its only tools,
so it has exactly these limits. *Ask* answers with links to the pages it read; *Draft* writes notes
and proposes decisions, shown as written or proposed by the agent "in Knowledge OS app"; *Review*
goes through what waits in Decide and recommends an action for each item. File → New Page (Ctrl+N)
can start a page from one line with the agent. See "In-app agents (ACP)" in
[`desktop-architecture.md`](desktop-architecture.md).

## Keeping documentation in step with code

A project can link the code repositories it describes (the *Code* section of the project page, or
`kos code link PROJECT PATH`). *Check documentation* then lists what changed in them since the last
check (commits, dependencies, commands and API routes, configuration, modules, READMEs), which
pages to update and why, and which decisions to propose (a new or removed dependency or module),
each with the commits it came from. Nothing is rewritten: a suggested decision is proposed as a
draft with its commits as provenance, pages are updated by you or by the agent (`read_commit` lets
it read the commits), and *Mark as checked* records the commit covered, so the next check starts
there. Agents get the same through `check_documentation`, `read_commit`,
`propose_documentation_decision`, `mark_documentation_checked`, and `link_repository`.

## Capture skill

The automatically discoverable `knowledge-os-capture` skill detects durable decisions, reusable
lessons, and recurring preferences in a conversation, batches proposals at natural pauses, and
writes only what you approve: through the MCP tools when they are available, otherwise by passing
a complete candidate to `kos capture` (see "Capture an approved record" in the
[README](../README.md)). There is no Agent OS dependency and no background saving.

Standalone means the skill and its companion CLI source are owned and distributed here; the CLI
package still needs one explicit, one-time local setup when it is not already importable. The
skill derives the plugin root from its loaded `SKILL.md`, asks before installing, and safely does
nothing when setup is declined or unavailable. The launcher detection and install commands for
PowerShell and POSIX shells live in one place,
[`skills/knowledge-os-capture/references/setup.md`](../skills/knowledge-os-capture/references/setup.md).
The install includes the `mcp` extra so `kos mcp` also runs without the desktop app. The skill asks
for approval immediately before the selected install command, then rechecks `import knowledge_os`
with that same launcher before any candidate is created.

## Documentation skill

The automatically discoverable `knowledge-os-documentation` skill supports one-time setup and
normal documentation retrieval. Global setup requires direct authorization because it writes the
managed blocks in the user-level Codex and Claude files and `~/.knowledge-os/config.toml`:

```text
kos documentation init-global --workspace PATH [--host codex] [--host claude] [--user-home PATH] [--replace] [--json]
```

Repository setup writes `.knowledge-os-project.toml` with one or more project bindings:

```text
kos documentation init-repo --repo PATH --project ID[=RELATIVE_PATH] [--project ...] [--user-home PATH] [--replace] [--json]
```

After setup, the skill searches before inspection or context export, reads each affected project's
overview and nearest relevant folder `README.md`, and keeps current behavior, decisions, drafts,
raw sources, and discoveries distinct. Search results are not automatically verified. Writes need
authorization from the current request or repository policy. See
[`init.md`](../skills/knowledge-os-documentation/references/init.md) and
[`documentation-workflow.md`](../skills/knowledge-os-documentation/references/documentation-workflow.md).

## When the MCP tools are not available

The plugin skills then run the command line as `<python> -m knowledge_os --root <root> ...`, with a
proven Python >=3.11 launcher and the root from `KNOWLEDGE_OS_ROOT` or
`~/.knowledge-os/config.toml`, and never as a bare `kos`, which could reach another install and
would look for the workspace in the agent's working directory. People and scripts use the plain
`kos` command directly.
