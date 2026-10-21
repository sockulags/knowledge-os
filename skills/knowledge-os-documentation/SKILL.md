---
name: knowledge-os-documentation
description: Use when setting up Knowledge OS for a user or repository, or when reading and updating a project's documentation pages to match its code ("initialize knowledge os", "bind this repo", "update the project docs", "check the docs against recent commits", "what do the docs say about X"). Not for saving decisions, lessons or preferences from a conversation (use knowledge-os-capture), importing a single file as a source (use ingest-source), or reviewing an external agent's observation (use review-discovery).
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
the server), use them instead of the command line. They act on the knowledge base open in the
Knowledge OS desktop app, go through its validation and conflict checks, and commit every write
under this agent's name:

- `search` before anything else, then `read_page` for the full text and its `content_sha256`;
  `list_projects` and `list_folder` to find a project's overview and the nearest folder pages.
- `write_note` to create a page (title, content, project, folder) or to edit one (id, the complete
  new content, and `expected_sha256` from `read_page`). A `conflict` result means the page changed:
  read it again and reapply the change, never overwrite blindly.
- A write that returns `action: waiting_for_review` is not saved: the knowledge base's review rules
  held it back and nothing is written yet. Tell the person that the change waits in the app's
  Decide inbox, where they accept or discard it, and name the `rule` from the result; do not say the
  page was updated and do not write it again. Before writing, `list_proposed_changes` shows the
  changes already waiting (`read_proposed_change` shows one in full), so you do not propose the same
  change twice.
- `propose_decision` for a decision; it is always a draft that the person accepts or withdraws in
  the app. `list_proposed_decisions` shows what is already waiting. No tool accepts decisions.
- To keep a project's pages in step with its code: `link_repository` once (the repository's
  absolute path), then after new commits `check_documentation`. For each suggested page update,
  `read_commit` for what changed, `read_page`, and `write_note`, naming the commits you used; for
  each suggested decision not already there, `propose_documentation_decision` with its `key`. Call
  `mark_documentation_checked` with the check's head commit only when the pages are up to date.

If a tool reports `app_not_open` or `app_not_responding`, tell the person to open the Knowledge OS
app with the knowledge base, and wait; do not switch to the CLI to write behind the app's back.
The rules for every write below apply to the MCP tools unchanged.

## CLI fallback

Without the MCP tools, run every command as `<python> -m knowledge_os --root <root> ...`, never as
a bare `kos`. `<python>` is a launcher proven to be Python >=3.11 that imports `knowledge_os`, and
`<root>` is `KNOWLEDGE_OS_ROOT` or else `workspace` from `~/.knowledge-os/config.toml`; the
`knowledge-os-capture` skill's setup reference (`setup.md`) shows how to select both and the
one-time setup. When
no launcher or root is available, report the gap and write nothing.

Normal work starts by reading the global config and optional repository binding. Run
`<python> -m knowledge_os --root <root> search QUERY --json` before `inspect` or `context`. Select
only task-relevant general knowledge and memory. Use `<python> -m knowledge_os --root <root> context
--project ID --task TEXT` for every bound project affected by the request or changed paths. Read the
project overview and the nearest relevant folder `README.md` records. Create new records with
`<python> -m knowledge_os --root <root> capture PATH --writer agent --json`. For an existing record,
run `<python> -m knowledge_os --root <root> inspect ID` to obtain its exact hash, then
`<python> -m knowledge_os --root <root> update PATH --expected-sha256 HASH --writer agent --json`.
`--writer agent` applies the review rules: a result with `action: waiting_for_review` wrote nothing
yet, and you report it exactly as for the MCP tools above.

## Rules for every write

Keep current behavior, accepted decisions, drafts, raw sources, and discoveries distinct. The
current request or repository policy must authorize every write. Otherwise report a concrete
documentation gap without writing. Never capture conversational memory. The `knowledge-os-capture`
skill owns that workflow. Missing or ambiguous project bindings are safe no-ops during normal work.
