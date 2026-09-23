# Knowledge OS — v0.0.1 contract freeze

This document is the authoritative product and metadata contract for the
stabilization release. The package version is `0.0.1`; the workspace schema
version remains the integer `1`.

## Authority and boundaries

Knowledge OS is a local-first, filesystem-native knowledge store. Markdown
records are canonical truth and Git may version them. `indexes/` contains only
derived, disposable state. Context packages and discovery review packets are
generated views and are never canonical knowledge.

Knowledge OS owns durable records, provenance, validation, indexing, search,
bounded context, the explicit discovery return path, and the deterministic
create-only capture primitive for approved records. The root Codex plugin also
owns the automatic conversational detection, proposal batching, and approval
workflow that calls that primitive. Agentic Work OS owns execution and
orchestration; this repository has no runtime dependency on either Agent OS or
Agentic Work OS.

The product does not include URLs, PDFs, embeddings, semantic search or
reranking, LLM trust decisions, contradiction or backlink subsystems, arbitrary
record merging, MCP, a remote or shared API, cloud or multi-user behavior, a
database as canonical storage, WAL/journal/transaction infrastructure, or
background workers. The local interface (the `kos-read` JSON API and the
desktop app that shows it) reads one workspace and writes to it only through
the core mutations described under "Local interface write API". The Codex plugin is a thin distribution surface for the conversational
capture skill, not a second storage or execution system.

## Workspace and filesystem

`knowledge-os.toml` marks a workspace and must contain:

```toml
[workspace]
name = "knowledge-os"
version = 1
```

The parser rejects a missing, non-integer, or unsupported
`[workspace].version`; v0.0.1 accepts only `1`. There are no per-record
versions or migrations.

The managed roots are:

| Root | Record type and meaning |
| --- | --- |
| `sources/` | raw local material captured with provenance |
| `knowledge/` | durable general knowledge |
| `projects/` | durable project-scoped records |
| `memory/` | durable user or agent memory |
| `syntheses/` | explicitly synthesized durable material |
| `discoveries/` | evidence-bearing external observations |
| `skills/` | operational Markdown guidance, outside the record schema |
| `indexes/` | generated catalog and SQLite FTS cache |

Every managed record is one UTF-8 `.md` or `.markdown` file directly or
recursively below the directory matching its `type`; its filename stem equals
its globally unique lowercase kebab-case `id`, except for project folder root
records named `README.md`. `README.md` files at managed root level are
documentation, not records. Managed files and directories,
including skill paths, must not be symlinks, and resolved managed paths must
remain below the workspace root.

Each project scope is physically contained at `projects/<project-id>/`. Its
required overview is `projects/<project-id>/README.md`. All other `project`
records with that scope must remain below the same directory. Descendant folder
names and nesting depth are not prescribed. Any descendant folder may contain
a metadata-bearing `README.md` root record; ordinary files retain `<id>.md`.

## Record metadata

All managed records require `id`, `title`, `type`, `status`, `scope`, `created`,
`updated`, and a non-empty `provenance` list. Dates are ISO calendar dates and
`updated` cannot precede `created`. Unknown top-level fields are errors.

The record types are `source`, `knowledge`, `project`, `memory`, `synthesis`,
and `discovery`. `knowledge` records require `scope: general`. `project`
records require `scope: project:<lowercase-kebab>`; other records may use
either allowed scope when their content warrants it.

Ordinary records use exactly these lifecycle statuses:
`draft`, `active`, `deprecated`, `superseded`, and `archived`. `verified` is
not a status. A record may instead have an optional `verified` ISO date,
independent of lifecycle status, bounded by `created..updated`. Context trust
is verified only when this date is present; an `active` or `draft` status does
not imply verification.

`record_kind` is optional and is accepted only on `knowledge` and `project`
records. Its values are `ordinary` and `decision`; absence means `ordinary`.
A decision is still an ordinary durable record with an explicit body stating
the chosen rule and rationale. `record_kind` on any other type, unknown values,
and unknown metadata fields are rejected.

For a decision, `draft` means proposed and not governing, `active` means
explicitly accepted and governing, `superseded` means replaced by an
accepted successor, and `archived` means withdrawn from consideration without
ever being accepted. Active and superseded decisions require a provenance
entry with `kind: decision-acceptance`; a draft decision must not contain one.
Acceptance records the basis for authority. It does not mean that the decision
was implemented or that any factual claim was verified. An archived decision
that was withdrawn requires a provenance entry with `kind:
decision-withdrawal` recording the reason; that provenance kind is rejected on
any record that is not an archived decision. `kos decision withdraw` is the
only path from `draft` to `archived`; an active decision is retired through
`kos supersede`, never withdrawn. Capture creates
decisions only as drafts, and ordinary update cannot change lifecycle status.

Every `project:<slug>` scope present in the corpus must have exactly one usable
overview with `type: project`, `id: <slug>`, and that same scope. The overview
must use `draft` or `active` status. `kos lint` enforces this globally;
context repeats the exact check when resolving its requested project.

Discoveries use their own workflow statuses:
`proposed -> retained | rejected | promoted`. Retained discoveries must be
project-scoped. Rejected and promoted are terminal. Discovery evidence and
review history remain distinct from ordinary lifecycle and verification.

## Provenance, evidence, and relationships

These fields have different meanings:

- `provenance` explains why or how a record came to exist. A provenance entry
  has `kind` and `reference`, with optional capture time and digest. For
  `kind: record`, `reference` resolves to any canonical record ID. For
  `kind: discovery`, it resolves to a canonical discovery ID. Other kinds are
  opaque external/local references.
- `evidence` supports the statement in a discovery. An evidence item has a
  kind and reference; `kind: record` references a canonical record, while
  other kinds remain opaque.
- `related` is a weak, directed domain association. It is not implicitly
  symmetric and is never a substitute for provenance.
- `sources` is a directed ordinary input/support relationship. It is not
  required for discovery promotion and does not duplicate promotion lineage.
- `supersedes` means that the record on the left replaces the referenced
  record. Self-links and deterministic cycles are invalid.

All relationship IDs resolve. Self-`sources`, self-`supersedes`, unresolved
canonical provenance, and invalid canonical provenance types are lint errors.

Promotion is **promote-new** only. The new draft target has one authoritative
lineage edge:

```text
target.provenance: [{kind: discovery, reference: <discovery-id>}]
discovery.reviews[-1]: {decision: promote, target: <target-id>}
```

Promotion does not add the discovery to `target.sources` or
`discovery.related`. The target must have the type implied by its scope and a
project-scoped discovery may target only its own project, unless explicitly
broadened to `general`. Existing records are never overwritten, merged, or
superseded.

This is a frozen invariant, not only a producer convention: lint rejects a
promoted pair when `target.sources` contains its discovery ID or when the
promoted discovery's `related` contains its promote review target. Unrelated
`sources` and `related` relationships remain valid.

Approved conversational candidates use the separate capture path
`kos --root PATH capture CANDIDATE.md [--project-path PATH] [--json]`. Capture accepts only
`knowledge`, `project`, and `memory` records, maps each type to its canonical
managed location, and refuses existing IDs or destination paths. Project
records default inside their scoped project directory; `--project-path`
selects a safe relative nested location there. Candidates must have valid metadata, a non-empty body and
provenance, `draft` or `active` lifecycle status, and no `verified` field.
Project scope and overview invariants are checked by whole-corpus staged
validation before the canonical exclusive create. Capture does not infer
meaning, decide approval, verify claims, or alter cwd discovery; a cross-chat
caller supplies the configured `--root` explicitly.

Lint also detects practical partial promotion states: a promoted discovery
whose target is missing, a target whose discovery provenance is missing or
invalid, a target provenance edge pointing at a proposed/retained discovery,
and disagreement between a provenance edge and the promote review target.

## Trust and context

The trust classifications are deliberately small:

| Classification | Meaning |
| --- | --- |
| `raw source; not established knowledge` | captured source material; never default context |
| `reviewed observation; not established knowledge` | retained project discovery |
| `draft durable; not verified` | draft durable record without a verified date |
| `active durable; not verified` | active durable record without a verified date |
| `verified durable` | durable record with an optional verified date |
| `operational guidance` | selected skill content |

Sources remain searchable and inspectable, but are excluded from default
context even when their body matches task terms. Only ordinary durable types
`knowledge`, `project`, `memory`, and `synthesis` with status `draft` or
`active`, plus retained discoveries in the requested project, can be selected.
Every selected item exposes type, record kind where applicable, scope, status,
trust classification, path, provenance, exact content SHA-256, and selection
evidence. The manifest also identifies the workspace by configured name,
workspace schema version, and exact marker hash.

For `kos context --project ID`, the only eligible ordinary scopes are
`general` and `project:ID`. FTS and one-hop relationship expansion use this
same policy; neither can import `project:other` or any other project scope.
The requested scope must contain exactly one usable project overview whose
type is `project`, ID is `ID`, and scope is `project:ID`. Missing, invalid,
ambiguous, or non-usable identity fails clearly; there is no fallback record.

Context selection is deterministic lexical FTS plus explicit one-hop
relationships and metadata. Skills are selected when at least two distinct
request terms match their name, description, or tags; skill bodies do not
activate selection. Whole items are greedily fitted to the configured budget
using `ceil(Unicode character count / 4)`. The UTF-8/LF package contract is
`kos-context/v1`, emitted to stdout, read-only, and non-canonical.

Repeatable `--require ID` values add governing records to the mandatory
envelope after the project overview. Required records do not use lexical
ranking, but they must pass the same type, lifecycle, trust, and scope policy;
an ID from another project remains ineligible. Every mandatory item is rendered
whole or package generation fails. `kos context verify PACKAGE.md` compares the
manifest with the current workspace and reports each selected item as
`unchanged`, `changed`, `missing`, or `ineligible`.

Discovery review is also deterministic lexical matching and explicit links,
not semantic contradiction detection or fact checking. Review output is
generated Markdown and does not decide an outcome.

## Codex plugin distribution

The repository root is a standalone Codex plugin named `knowledge-os`.
`.codex-plugin/plugin.json` exposes `skills/`, and the repo-owned marketplace
manifest at `.agents/plugins/marketplace.json` publishes the plugin from `./`.
The automatically discoverable `skills/knowledge-os-capture/SKILL.md` detects
durable decisions, reusable lessons, and recurring preferences, batches
approval proposals at natural pauses, and supports direct `save this` or
`spara detta` intent. It creates no candidate before approval and safe-no-ops
when `KNOWLEDGE_OS_ROOT` or the Python 3.11 `knowledge_os` dependency is not
available. When the dependency is missing, it offers an explicit one-time
installation from the plugin root derived from the loaded skill path; it never
installs silently. Launcher selection is cross-platform: `py -3.11` on
Windows, `python3.11` on macOS/Linux, and only a proven Python >=3.11 `python3`
fallback. After setup and approval it invokes the selected launcher with
`knowledge_os --root ... capture ... --json`. Setup detects
`sys.prefix != sys.base_prefix` with that launcher and omits `--user` inside a
virtual environment; non-venv setup uses `--user`. Deterministic storage,
schema validation, provenance, locking, and index refresh remain owned by
Knowledge OS.

## Skills

Each skill is `skills/<name>/SKILL.md`. Shared parsing and validation require
UTF-8 text with frontmatter containing a non-empty lowercase-kebab `name`, a
non-empty `description`, optional non-empty lowercase-kebab `tags`, and a
non-empty body. The directory name must equal the frontmatter name. Duplicate
names, unknown fields, malformed frontmatter, unsafe paths, and malformed
tags are errors. `kos lint` validates every skill, not only skills selected by
context.

## Mutation and recovery contract

Ingest, capture, conflict-safe update, decision acceptance, decision
withdrawal, decision supersession, discovery add/retain/reject/promote, and
index replacement all use one workspace-scoped advisory mutation lock owned by
workspace infrastructure.
Each mutation follows this order:

1. acquire the lock and validate the current canonical corpus and skills;
2. validate the intended result in a disposable staged workspace;
3. write only the required canonical Markdown files, atomically replacing
   existing files and exclusively creating new records;
4. keep canonical Markdown as authoritative and rebuild disposable indexes;
5. release the lock.

There is no WAL, journal, or multi-file transaction. Promotion and supersession
are not crash-atomic, although a caught supersession write failure attempts to
restore both original records. If a process stops between canonical writes,
the resulting partial lineage or replacement is detected by `kos lint`; repair
the affected Markdown, then run `kos lint` and `kos index`. If canonical writes
succeed but index rebuilding fails, the canonical
records remain; the command reports recovery instructions to run `kos lint`
and then `kos index`.

Deleting `indexes/catalog.md` and `indexes/catalog.sqlite3` does not affect
corpus validity. `kos lint` remains usable and `kos index` recreates both
derived files from Markdown.

`kos update` requires the SHA-256 of the exact current canonical bytes and
rejects stale writers before staging. It preserves ID, type, scope, creation
date, record kind, lifecycle status, supersession, discovery lineage, and
decision-acceptance lineage. An accepted decision body may change only with an
explicit non-material confirmation and a recorded change reference. Material
changes use a new draft decision.

`kos decision withdraw ID --expected-sha256 HASH --reason TEXT` moves one
draft decision to `archived` and appends `decision-withdrawal` provenance
with the given reason. It uses the same exact-revision SHA-256 guard, shared
workspace lock, and atomic canonical write as `kos decision accept`, and
refuses records that are not decisions, decisions that are not draft, and a
stale hash. Withdrawal ends consideration of a proposal without accepting it;
an active decision is retired through `kos supersede` instead.

A draft decision may declare exactly one active decision in `supersedes`; this
is only a proposed replacement and does not retire the target. `kos supersede`
checks both exact revisions and the acceptance reference, then stages the new
decision as active and the old decision as superseded before writing either.
It writes the active replacement first so an abrupt stop does not remove the
last governing decision. Caught write failures restore both original byte
snapshots when possible. Lint detects effective replacements without a matching
superseded target and superseded decisions without exactly one effective
successor. Partial-state errors name the affected repair targets and require
canonical inspection followed by `kos lint` and `kos index`.

Documentation initialization writes integration configuration, not canonical
records. `kos documentation init-global` validates the selected workspace,
writes `~/.knowledge-os/config.toml`, and maintains a delimited block in the
user-level Codex and Claude instruction files. This command requires direct
user authorization. `kos documentation init-repo` validates the global config,
project overviews, and repository-relative project paths before writing
`.knowledge-os-project.toml`. Both commands are idempotent, refuse conflicting
configuration unless `--replace` is supplied, use atomic file replacement, and
attempt to restore writes after a caught failure.

## Local interface write API

`kos-read` (and the desktop app, which runs the same server) serves a JSON API
on a loopback address. `GET` routes never write. The write routes call the same
core functions as `kos capture`, `kos update`, `kos decision accept`, `kos
decision withdraw`, and `kos supersede`, so they share the mutation
lock, staged whole-corpus validation, exact-revision SHA-256 guard, and index
refresh described above; `knowledge_os/reader/library.py` is the only reader
module that calls them. The routes create and edit only `knowledge`,
`project`, and `memory` records, the types capture creates.

- `GET /api/session` returns `{"write_token": ..., "write_token_header":
  "X-KOS-Write-Token"}`. The token is random per server process.
- `POST /api/records` creates one record with capture's rules. Body:
  `{"metadata": {...}, "body": "...", "project_path": "optional/relative.md"}`.
  `metadata` holds the frontmatter fields; `created` and `updated` default to
  today (UTC), and provenance is required. `project_path` has
  `--project-path` semantics. Decisions are created only as `draft`.
  Answers `201`.
- `PATCH /api/records/{id}` edits one record with `kos update`'s rules. Body:
  `{"expected_sha256": "...", "metadata": {"field": value}, "body": "...",
  "confirm_non_material": false, "change_reference": "..."}`. Only
  `expected_sha256` is required. `metadata` replaces the named top-level
  fields on the revision identified by `expected_sha256` (`null` removes a
  field), and an omitted `body` keeps the current body. Unless `metadata`
  sets `updated`, it becomes today or keeps its later current value. Changes
  to identity, lifecycle, supersession, and system provenance are refused.
  An accepted decision's body changes only with `confirm_non_material` and
  `change_reference`. Answers `200`.

A successful write returns `{"id", "status", "path", "content_sha256",
"index": {"refreshed", "count", "error"}, "commit": {"committed", "sha",
"message", "skipped", "detail"}}` (see "Git versioning and sync" below for
`commit`). `content_sha256` is the new
revision's hash, which the next edit sends as `expected_sha256`. If the
canonical write succeeded but reindexing failed, the write still answers
`201`/`200` with `index.refreshed: false` and the recovery message in
`index.error`; run `kos lint` and then `kos index`.

A refused write returns `{"error": KIND, "detail": MESSAGE}` and writes
nothing. The kinds and statuses are `bad_request` `400` (malformed JSON or
field types), `forbidden` `403` (origin checks below), `not_found` `404`,
`conflict` `409` (stale `expected_sha256`; the body adds `current_sha256`),
`duplicate` `409` (the ID or destination already exists), and `validation`
`422` (the core rejected the candidate or the resulting corpus; the body adds
`issues: [{"path", "message"}]` with lint findings when the staged corpus is
invalid). The message is the same text the CLI prints for the same rule.

Writes are protected against requests caused by web pages the user visits.
A write must address the server by a loopback host name (`127.0.0.1`,
`localhost`, or `::1`), which defeats DNS rebinding. It must not carry a
non-loopback `Origin` or `Sec-Fetch-Site: cross-site`, and it must be
`application/json` with the process's token in `X-KOS-Write-Token`.
`GET /api/session` applies the same host and origin checks. No route sends
CORS headers, so a page on another origin can neither read the token nor
send the custom header. The UI reads the token from its own origin; the Vite
dev server's loopback origin passes the same checks through its proxy. The
loopback host check applies to every request the server handles, not only
writes: a middleware in front of the whole route table refuses any request
whose `Host` is not loopback, so DNS rebinding can't be used to read the
JSON API or the served SPA either.

The decision lifecycle routes call the same core functions as `kos decision
accept`, `kos decision withdraw`, and `kos supersede`, with the same guard,
response, and error mapping. The core's refusals (not a decision, wrong
lifecycle state, missing `supersedes` declaration, competing replacement)
answer `422 validation`.

- `POST /api/records/{id}/accept` makes draft decision `id` active. Body:
  `{"expected_sha256": "..."}`. The acceptance reference is
  `interface:<UTC timestamp>:accept`.
- `POST /api/records/{id}/withdraw` archives draft decision `id`. Body:
  `{"expected_sha256": "...", "reason": "..."}`. `reason` is required and
  becomes the `decision-withdrawal` provenance reference.
- `POST /api/records/{id}/supersede` is called on the draft replacement,
  which must declare `supersedes: [old_id]`: `id` becomes active and
  `old_id` becomes superseded. Body: `{"expected_sha256": "<draft hash>",
  "old_id": "...", "old_expected_sha256": "<active decision hash>"}`. The
  acceptance reference is `interface:<UTC timestamp>:supersede`. The response
  describes the replacement and adds `replaced: {"id", "status", "path",
  "content_sha256"}` for the retired decision. A reindex failure after both
  canonical writes is reported in `index` like any other write.

`POST /api/preview` renders unsaved editor text for the preview toggle:
`{"body": "...", "path": "optional record path for link resolution"}`
answers `{"html": ...}`, rendered the way the record page renders a saved
body. It writes nothing but requires the same guard and token.

`GET /api/records/{id}` carries an `editing` object for the editor, apart
from the reader's prose fields: `editable` (the record is a type the routes
edit), `raw_body` and `metadata` (`title`, `tags`, `related`, `sources`)
read from the same bytes as `content_sha256`, `path`, `project_id`,
`folder` (the record's folder below its project directory),
`body_change_needs_confirmation` (an accepted decision's body changes only
as a confirmed non-material edit), and `decision_actions` (`null` for a
non-decision, otherwise `accept`, `withdraw`, `propose_replacement`, and
`supersede`, which names the active decision a draft replacement would
retire with its current `content_sha256`). `decision_actions` only decides
which buttons the interface shows; the core re-checks every precondition.

Records authored in the interface carry provenance
`{"kind": "interface-authored", "reference": "interface:<UTC
timestamp>:create", "captured": "<UTC timestamp>"}`. No existing kind
fits: `user-approved-conversation` and `user-request` describe content an
agent wrote from a conversation, while this content was typed by the person
directly. The kind is opaque to the core, like every provenance kind except
`record`, `discovery`, `decision-acceptance`, and `decision-withdrawal`, and
the interface uses it only when creating a record. Edits add no provenance,
as with `kos update`; Git history records them. A confirmed non-material
edit of an accepted decision body gets change reference
`interface:<UTC timestamp>:edit`.

## Git versioning and sync

A knowledge base is meant to be its own Git repository. `knowledge_os/gitsync.py`
calls the `git` executable found on `PATH` (no Git library); in the packaged
app a missing `git` is reported as `git_missing` with an install hint. The
workspace root must be the repository's top level: a workspace nested inside
another repository is treated as not versioned, so the interface never commits
into an unrelated project. `kos init` ignores `indexes/catalog.md` and the
SQLite files; `indexes/` is never committed by the interface, and the status
warns when generated index files are still tracked.

**Auto-commit.** After each successful interface write (create, edit, accept,
withdraw, supersede) the adapter commits exactly the paths that write touched
(`git add --all -- PATHS` then `git commit --only -- PATHS`), so unrelated
modified, untracked, or staged changes stay as they were. Messages are
`Create <title>`, `Edit <title>`, `Accept decision <title>`, `Withdraw
decision <title>`, and `Supersede decision <old title> with <new title>`. The
commit uses the repository's configured identity; when `user.name` or
`user.email` is missing, nothing is committed and `commit.skipped` is
`no_identity`. The write itself never fails because of Git: `commit` is
`{"committed": false, "skipped": KIND, "detail": MESSAGE}` for `not_a_repo`,
`git_missing`, `no_identity`, `merge_in_progress`, `nothing_to_commit`, or a
Git failure. CLI mutations (`kos capture`, `kos update`, `kos decision ...`,
`kos supersede`, discovery commands, `kos ingest`) do not commit; commit their
results with Git yourself.

**Sync.** Sync pulls, then pushes, against the current branch's configured
upstream (`branch.<name>.remote` and `.merge`). Pull is `git fetch` followed by
`git merge` of the remote-tracking branch, not a rebase: a merge stops at most
once, leaves the standard recoverable `MERGE_HEAD` state that `git merge
--abort` undoes, never rewrites local commits, and Git refuses to start it
when uncommitted changes would be overwritten or the index holds staged
changes. After a pull that changed files the indexes are rebuilt. The time of the last successful sync is
kept in `.git/kos-last-sync`, outside the working tree.

Every Git call runs under the workspace advisory lock, with a timeout (45 s
for fetch and push, 30 s for local commands) after which the process tree is
killed, with no terminal (`stdin` closed) and with prompts disabled
(`GIT_TERMINAL_PROMPT=0`, empty `GIT_ASKPASS`, `SSH_ASKPASS_REQUIRE=never`,
`GCM_INTERACTIVE=never`, and `ssh -o BatchMode=yes` unless the user set their
own SSH command). Existing credential helpers and SSH agents keep working; a
credential Git would have to ask for becomes an `auth` error. Credentials are
never requested, stored, or logged, and `user:password@` in URLs is redacted
from every message.

**Conflicts.** When the merge stops on conflicts the repository stays in the
merge state. The conflicted files are listed with both versions; each is
resolved by choosing this computer's version (`ours`), the incoming version
(`theirs`), or a merged text, which is written and staged. A file resolved
earlier in the same merge can be chosen again (it is put back in conflict with
`git checkout -m`). Only files this merge put in conflict can be written.
Running sync again with no conflicts left runs `kos lint` over the whole
corpus; if it fails, nothing is committed and the issues are returned.
Otherwise the merge is committed as `Sync with <upstream> (resolved
conflicts)`, the indexes are rebuilt, and the result is pushed. Aborting
restores the state before the pull.

Endpoints use the write API's guard: every route applies the loopback host
and origin checks, and the `POST` routes also need the write token and a JSON
body. Git runs in a worker thread so a slow remote does not stall other
requests. Every sync response carries a fresh `status`.

- `GET /api/sync/status` never contacts the remote and answers
  `{"available", "reason", "detail", "branch", "upstream", "remotes",
  "ahead", "behind", "uncommitted", "merging", "conflicts", "last_sync",
  "identity": {"name", "email"} | null, "warnings"}`. `ahead` and `behind`
  are counted against the remote-tracking branch as of the last fetch;
  `uncommitted` counts changed paths outside `indexes/`.
- `POST /api/sync` with `{}` answers `{"state": "synced", "pulled",
  "pushed", "reindexed", "index_error", "status"}`, or finishes a merge whose
  conflicts are all resolved.
- `GET /api/sync/conflicts` answers `{"files": [{"path", "ours", "theirs",
  "working", "binary", "resolved"}], "status"}`; `ours`/`theirs` are `null`
  when that side deleted the file.
- `POST /api/sync/resolve` with `{"path", "choice": "ours" | "theirs" |
  "merged", "content"}` (`content` only for `merged`) answers `{"path",
  "remaining", "issues", "status"}`, where `issues` are the lint findings for
  that file.
- `POST /api/sync/abort` with `{}` runs `git merge --abort` and answers
  `{"status"}`.

A refused sync answers `{"error": KIND, "detail", "status"}` plus
`conflicts: [PATH]` for `conflict` and `issues` for `lint`. Statuses: `409`
for `git_missing`, `not_a_repo`, `no_branch`, `no_identity`, `no_upstream`
(the detail says how to add a remote or set an upstream), `blocked` (the pull
would overwrite uncommitted changes), `conflict`, and `no_merge`; `400` for
`not_conflicted` and malformed bodies; `422` for `lint`; `502` for `auth`,
`network`, `timeout`, and `rejected` (the remote moved during the sync); `500`
for any other Git failure.

## CLI contract

- `kos ingest PATH` captures one local UTF-8 Markdown/text source with a full
  SHA-256 provenance digest and stable ID; identical input is idempotent.
- `kos lint` validates workspace version, all managed records, cross-record
  invariants, and all skills.
- `kos index` validates the corpus and rebuilds `catalog.md` and SQLite FTS5.
- `kos search QUERY` reads the existing cache for compact audit results,
  including type, record kind, status, scope, path, and snippet.
- `kos inspect ID` provides compact record metadata and exact content SHA-256;
  `--full` adds the body.
- `kos context` emits bounded, trust-aware, project-scoped generated context;
  repeatable `--require ID` values form a scope-safe mandatory envelope.
- `kos context verify PACKAGE.md` reports workspace and selected-item drift.
- `kos capture PATH [--project-path PATH]` creates one approved, create-only `knowledge`, `project`,
  or `memory` record after staged whole-corpus validation; `--json` reports
  its exact ID, type, scope, canonical path, and status. `--project-path` is a
  safe path relative to `projects/<project-id>/` and may create arbitrary nested
  folders or a folder root `README.md`.
- `kos update PATH --expected-sha256 HASH` performs a conflict-safe,
  lifecycle-preserving replacement.
- `kos decision accept ID` activates a draft decision with explicit acceptance
  provenance.
- `kos decision withdraw ID --reason TEXT` archives a draft decision with
  explicit withdrawal provenance, ending consideration without acceptance.
- `kos supersede OLD_ID NEW_ID` activates an accepted draft replacement and
  retires the prior decision as one coordinated mutation.
- `kos discovery add PATH`, `review ID`, `retain ID`, `reject ID`, and
  `promote ID` implement the explicit discovery return path.
- `kos documentation init-global --workspace PATH` installs user-level host
  guidance and the global workspace location after direct authorization.
- `kos documentation init-repo --repo PATH --project ID[=RELATIVE_PATH]`
  writes one portable repository binding for one or more project scopes.

Read-only context and review require a current SQLite cache and never rebuild
it implicitly. `kos index` is always safe to run as the derived-state repair
step after canonical Markdown has been repaired or a cache has been removed.
