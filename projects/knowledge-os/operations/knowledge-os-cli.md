---
id: knowledge-os-cli
title: Knowledge OS CLI operations
type: project
status: active
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-22'
provenance:
- kind: repository-file
  reference: knowledge_os/cli.py
- kind: repository-file
  reference: docs/architecture.md
- kind: repository-file
  reference: README.md
- kind: repository-file
  reference: knowledge_os/workspace.py
---

# Knowledge OS CLI operations

Run commands from a discovered workspace or pass `--root PATH`. The command
uses the existing index for search, context export, and discovery review. It
does not rebuild that index during a read operation.

## Read only commands

`kos lint` validates the workspace version, every managed record, cross record
invariants, and every skill. It requires a valid workspace marker.

`kos search QUERY [--limit N] [--json]` reads the SQLite FTS index and returns
record type, record kind, status, scope, path, and a snippet. `QUERY` must not
be empty. The command refuses an absent index and reports that `kos index` must
run first.

`kos inspect ID [--full]` validates the corpus and returns metadata, provenance,
trust, and the exact content SHA-256. `ID` must identify one record. `--full`
also returns the body.

`kos context --project ID --task TEXT --budget N [--work-item TEXT] [--require ID]`
exports a generated package to standard output. `--require ID` may repeat.
The project, task, and budget are required. The budget must be at least `1`.

`kos context verify PACKAGE.md [--json]` checks a generated package without
rebuilding indexes. Package verification is described in
[Knowledge OS context export](knowledge-os-context-export.md).

`kos discovery inspect ID` returns one discovery record. `kos discovery review
ID` returns a generated review packet. Both commands require a valid corpus
and a current search index.

Read operations refuse invalid managed records, missing project overviews, and
stale or missing indexes where index data is required. Read operations never
make a canonical write.

## Mutating commands

`kos index` validates the corpus and replaces `indexes/catalog.md` and
`indexes/catalog.sqlite3`. It refuses to index an invalid corpus.

`kos ingest PATH` captures one local UTF-8 Markdown or text source with a
stable ID and full SHA-256 provenance. The input must be a readable file.
Identical input is idempotent. Divergent input for an existing source refuses
the write.

`kos capture CANDIDATE.md [--project-path PATH] [--json]` creates one approved
`knowledge`, `project`, or `memory` record. The candidate needs valid metadata,
a body that is not empty, provenance that is not empty, and `draft` or `active` status. It must
not contain `verified`. The ID and destination path must not already exist.
Project records must remain under their matching project directory, and staged
whole corpus validation must pass.

`kos update PATH --expected-sha256 HASH [--confirm-non-material
--change-reference REF]` replaces one existing record. The candidate must
preserve identity, scope, creation date, record kind, lifecycle status,
supersession, discovery lineage, and decision acceptance lineage. A stale hash
or an immutable field change refuses the update. An accepted decision body
requires both `--confirm-non-material` and a non-empty `--change-reference`.
Material decision changes require a new draft and `kos supersede`.

`kos decision accept ID --expected-sha256 HASH --acceptance-reference REF`
activates one draft decision and appends decision acceptance provenance. It
refuses records that are not decisions, decisions that are not draft, stale hashes, and draft decisions
that declare `supersedes`.

`kos decision withdraw ID --expected-sha256 HASH --reason TEXT [--json]`
archives one draft decision and appends decision withdrawal provenance
recording the reason. It uses the same locked mutation, exact-revision guard,
and atomic write as `kos decision accept`, and refuses records that are not
decisions, decisions that are not draft, and stale hashes. An active decision
is retired through `kos supersede`, not withdrawal.

`kos supersede OLD_ID NEW_ID --expected-old-sha256 HASH
--expected-new-sha256 HASH --acceptance-reference REF` activates a draft
replacement and marks the old decision superseded. Both hashes must match. The
old record must be active, the new record must be draft, both records must be
decisions in the same scope, and the new record must declare exactly the old
record in `supersedes`. Competing draft replacements refuse the operation.

`kos discovery add PATH` accepts only a structured UTF-8 Markdown file with
`type: discovery`, `status: proposed`, and no review events.

`kos discovery retain ID` changes a proposed discovery to `retained`. Retained
discoveries must use a project scope. `kos discovery reject ID --reason TEXT`
moves a proposed or retained discovery to terminal `rejected` and requires a
reason.

`kos discovery promote ID --target-id ID --title TITLE --scope SCOPE` creates a
new draft knowledge or project record and moves the discovery to terminal
`promoted`. It refuses existing target IDs or paths, cross-project targets,
unacknowledged related records, targets in another project, and project to general promotion without
`--allow-scope-broadening`. It never overwrites, merges, or supersedes a
record. Use `--acknowledge-related` when the review packet lists related
records.

## Documentation initialization

`kos documentation init-global --workspace PATH` validates the Knowledge OS
workspace and writes the global workspace config plus short managed blocks for
Codex and Claude. This command changes user-level files and requires direct
authorization. Omit `--host` to configure both hosts. Use `--replace` only to
replace a conflicting configuration intentionally.

`kos documentation init-repo --repo PATH --project ID[=RELATIVE_PATH]` reads
the global config and writes `.knowledge-os-project.toml`. Repeat `--project`
for a monorepo. Each ID must have one usable project overview. Each relative
path must resolve to one distinct directory inside the repository.

Both initialization commands are idempotent. They write integration config,
not canonical records, and do not rebuild the Knowledge OS indexes.

All mutating commands refuse an invalid current corpus. They stage the
intended result before canonical writes, use the shared workspace lock, and
refresh generated indexes after canonical writes.

### Example

```powershell
kos --root C:\work\knowledge-os context --project knowledge-os `
  --task "Review provenance boundaries" --budget 12000 --require knowledge-os
```
