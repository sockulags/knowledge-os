# Documentation workflow

## Select records

1. Read `~/.knowledge-os/config.toml` and the nearest optional `.knowledge-os-project.toml`.
2. Run `kos search` with task terms before inspecting records or exporting context.
3. Select only task-relevant records from general knowledge and memory. Search relevance is not
   verification.
4. Run `kos context` for each bound project affected by the request or changed paths.
5. Read the selected project's overview at `projects/<project-id>/README.md`.
6. Read the nearest relevant folder `README.md` records below that project root.

Keep these categories separate:

- Current behavior records describe what the repository does now.
- Accepted decisions describe governing choices and their acceptance provenance.
- Drafts describe proposals that do not govern current behavior.
- Raw sources preserve captured material and are not established knowledge.
- Discoveries preserve external observations and their review state. Retention does not make one
  established knowledge.

Do not treat an absent result as proof that no record exists. Narrow the search terms, check the
relevant project context, and report the missing evidence when retrieval remains empty.

## Write records

The current request or repository policy must authorize a documentation write. Without that
authority, report the concrete gap, affected project, and proposed record location without changing
files.

Create a new record with `kos capture` after preparing a complete candidate with valid metadata and
provenance. Never use capture to preserve conversational memory. The `knowledge-os-capture` skill
owns conversational memory proposals and approvals.

For an existing record, run `kos inspect ID` first and keep its exact `content_sha256`. Prepare the
complete replacement, then run `kos update PATH --expected-sha256 HASH`. A stale hash is a conflict,
not permission to overwrite. Keep scope, identity, lifecycle, decision acceptance, and discovery
lineage unchanged unless the command contract explicitly permits the requested operation.

After an authorized write, run `kos lint`, `kos index`, and a `kos search` that retrieves every
changed record. Report the changed paths and the validation results.
