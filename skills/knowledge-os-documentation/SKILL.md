---
name: knowledge-os-documentation
description: Initializes and maintains repository documentation retrieval through Knowledge OS without treating search results as verified or writing without authorization.
tags:
  - documentation
  - initialization
  - retrieval
---

# Knowledge OS documentation

Use this skill for one-time setup and for documentation work after setup.

## Responsibilities

- Run one-time global initialization for the user's Codex and Claude configuration.
- Run repository initialization for project bindings.
- Retrieve and maintain task-relevant documentation after initialization.

Global initialization edits user-level files. Require direct user authorization immediately before
running it. Repository initialization writes `.knowledge-os-project.toml` and is safe to run only
when the user explicitly requests initialization.

Use the exact commands and binding format in [references/init.md](references/init.md). Use the
selection and update rules in [references/documentation-workflow.md](references/documentation-workflow.md).

## With the Knowledge OS MCP tools

When the `knowledge-os` MCP server's tools are available in this session (the plugin registers
`kos mcp`), use them instead of shelling out to `kos`. They act on the knowledge base open in the
Knowledge OS desktop app, go through its validation and conflict checks, and commit every write
under this agent's name:

- `search` before anything else, then `read_page` for the full text and its `content_sha256`;
  `list_projects` and `list_folder` to find a project's overview and the nearest folder pages.
- `write_note` to create a page (title, content, project, folder) or to edit one (id, the complete
  new content, and `expected_sha256` from `read_page`). A `conflict` result means the page changed:
  read it again and reapply the change, never overwrite blindly.
- `propose_decision` for a decision; it is always a draft that the person accepts or withdraws in
  the app. `list_proposed_decisions` shows what is already waiting. No tool accepts decisions.

If a tool reports `app_not_open` or `app_not_responding`, tell the person to open the Knowledge OS
app with the knowledge base, and wait; do not switch to the CLI to write behind the app's back.
The rules for every write below apply to the MCP tools unchanged.

## CLI fallback

Without the MCP tools, normal work starts by reading the global config and optional repository
binding. Run `kos search` before `kos inspect` or `kos context`. Select only task-relevant general
knowledge and memory. Use `kos context` for every bound project affected by the request or changed
paths. Read the project overview and the nearest relevant folder `README.md` records. Create new
records with `kos capture`. For an existing record, run `kos inspect` to obtain its exact hash, then
use `kos update` with that hash.

## Rules for every write

Keep current behavior, accepted decisions, drafts, raw sources, and discoveries distinct. The
current request or repository policy must authorize every write. Otherwise report a concrete
documentation gap without writing. Never capture conversational memory. The `knowledge-os-capture`
skill owns that workflow. Missing or ambiguous project bindings are safe no-ops during normal work.
