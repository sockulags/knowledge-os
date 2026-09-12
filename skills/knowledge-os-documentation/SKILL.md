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

Normal work starts by reading the global config and optional repository binding. Run `kos search`
before `kos inspect` or `kos context`. Select only task-relevant general knowledge and memory. Use
`kos context` for every bound project affected by the request or changed paths. Read the project
overview and the nearest relevant folder `README.md` records.

Keep current behavior, accepted decisions, drafts, raw sources, and discoveries distinct. Create
new records with `kos capture`. For an existing record, run `kos inspect` to obtain its exact hash,
then use `kos update` with that hash.

The current request or repository policy must authorize every write. Otherwise report a concrete
documentation gap without writing. Never capture conversational memory. The `knowledge-os-capture`
skill owns that workflow. Missing or ambiguous project bindings are safe no-ops during normal work.
