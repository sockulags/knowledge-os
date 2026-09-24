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
record merging, a remote or shared API, cloud or multi-user behavior, a
database as canonical storage, WAL/journal/transaction infrastructure, or
background workers. The local interface (the `kos-read` JSON API and the
desktop app that shows it) reads one workspace and writes to it only through
the core mutations described under "Local interface write API". The one MCP
surface, `kos mcp` (see "Agent access over MCP"), is a client of that local
API and never opens a workspace itself. The Codex plugin is a thin distribution surface for the conversational
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
Folders created through `kos folder create` or the interface always get such a
root record (see "Structure editing").

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
Knowledge OS. When the plugin's MCP server tools are available (see "Agent
access over MCP"), the capture and documentation skills use them after
approval instead of the CLI, which stays as the fallback.

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
withdrawal, decision supersession, discovery add/retain/reject/promote, the
structure changes (project and folder creation, page and folder moves and
renames), and index replacement all use one workspace-scoped advisory mutation
lock owned by workspace infrastructure.
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

Both routes accept an optional `"agent": {"client": "...", "place": "..."}`
that marks the write as an agent's (see "Agent access over MCP"). `client` is
required in it; both parts are cleaned to letters, digits, spaces, `.`, `_`,
and `-`, and at most 60 characters. A create puts `{"kind":
"agent-authored", "reference": "agent:<client>:<place>", "captured": "<UTC
timestamp>"}` first in the record's provenance (`:<place>` is omitted when
there is none); an edit appends the same entry unless one with that reference
is already there. The auto-commit message then starts with the agent's name,
e.g. `Claude Code: Create <title>`. Any caller holding the write token may
send `agent` or write `agent-authored` provenance directly: the kind labels
agent work, it does not authenticate it.

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
It also carries `summary` (the sentence above the buttons) and `dialogs`,
the finished text of each available action's confirmation (`title`, `body`,
`confirm`, `history`, and `changes: [{"subject", "from", "to"}]`). A
decision's payload adds `decision_language` (button labels and the "How
decisions work" guide, one line per state); it is `null` for other records.
All of these words come from `strings.py`.

`GET /api/decisions/proposed` is the Decide inbox: every draft decision,
newest first by the `captured` time of its first provenance entry that is
not an acceptance or withdrawal (the record's `created` date when there is
none), then by title. `?project=<id>` narrows it to one project, and
`general` to decisions that apply everywhere. The answer is `{"title",
"intro", "count", "count_label", "project", "filter_label",
"all_projects_label", "projects": [{"id", "title", "count"}], "items",
"empty": {"title", "body"}, "open_label", "language"}`, where `count` and
`projects` ignore the filter and `language` is `decision_language`. Each
item is `{"id", "title", "excerpt", "project": {"id", "title"},
"proposed_by": {"source", "label", "kind"}, "proposed_at",
"proposed_display", "proposed_exact", "replaces": {"id", "title",
"sentence"} | null, "effect", "status_pill", "content_sha256", "actions"}`,
with `actions` shaped like `decision_actions`. `proposed_by.source` is
`you`, `conversation`, `meeting`, `agent`, `observation`, or `other`; a
provenance kind without a sentence in `strings.PROPOSED_BY` reads as a
generic fallback. `GET /api/nav` adds `decide: {"label", "count"}` for the
sidebar.

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

Records imported by the desktop app's Referat plugin (see
[`desktop/README.md`](../desktop/README.md)) carry provenance
`{"kind": "referat-meeting", "reference": "referat:<meeting id>",
"captured": "<UTC timestamp>", "sha256": "<SHA-256 of the imported summary
Markdown>"}`. Referat's meeting id is the meeting's UTC start time
(`YYYYMMDDhhmmss`) plus a short random suffix, so the reader names the
meeting date: "Imported from a Referat meeting on 20 September 2026". Like
`interface-authored`, the kind is opaque to the core: lint does not resolve
the reference, and nothing outside the plugin writes it. The plugin creates
records only through `POST /api/records`, so the imported note and its draft
decisions follow capture's rules and the approval policy, and each one is
auto-committed like any other interface write. The plugin finds an earlier
import of the same meeting by this reference.

## Structure editing

Projects and folders are created, and pages and folders moved and renamed,
only through `knowledge_os/structure.py`. The CLI, the local API, and the
interface's drag and drop all call it; the interface never touches files.

**Creating.** `kos project create ID --title TITLE` writes the required
overview `projects/<ID>/README.md` (status `active`) through capture's
create-only path; the body defaults to a heading with the title. A new folder
is created as its `README.md` root record: `kos folder create PROJECT PATH
--title TITLE` writes `projects/<PROJECT>/<PATH>/README.md` with the ID
`<PROJECT>-<PATH parts joined by hyphens>` (a numeric suffix when taken, or
`--id`). The parent folder must exist, the new folder's name must be lowercase
kebab-case, and an existing directory is refused. A folder is therefore a real,
lintable page that Git tracks from the moment it exists, and it keeps its title
and ID when it is renamed or moved. The alternative, a folder that exists only
in the interface until the first page is saved there, was rejected: Git does
not track empty directories, so such a folder would vanish on sync or reload.
Records created from the CLI carry provenance `{"kind": "cli-authored",
"reference": "cli:<UTC timestamp>:<action>", "captured": ...}`; from the
interface, `interface-authored`.

**Moving and renaming.** `kos move ID --expected-sha256 HASH [--folder PATH]
[--to-project ID --allow-scope-change]` moves one `project` page into an
existing folder (default: the project's top level). `kos folder move PROJECT
PATH [--to-parent PATH] [--to-project ID --allow-scope-change] [--name NAME]
[--title TITLE]` moves a folder with every file in it; `kos folder rename
PROJECT PATH --name NAME [--title TITLE]` renames it in place, and `--title`
retitles its `README.md`. `kos rename ID --title TITLE --expected-sha256 HASH`
changes a page's title with `kos update`'s rules. Moves keep every record ID
and filename, since a filename is its ID; that is why renaming a page changes
only its title. The project overview cannot be moved, a folder's `README.md` is
moved with its folder rather than on its own, a folder cannot move into
itself, and an existing destination is refused. A folder left empty by a move
is removed.

**Links.** Every relative Markdown link that pointed at a moved file keeps
pointing at it, and links inside moved files are recomputed from their new
directory. A link resolves as the reader resolves it: a destination with a URI
scheme, `//`, or only a `#fragment` is external; otherwise the part before
`#` is joined to the linking file's directory and normalized. A link into a
moved folder (a page, the folder's `README.md`, or the folder itself as
`folder/`) is rewritten, the `#fragment` and `<angle brackets>` are kept, and
only the destination text changes. Inline links and images and reference
definitions are rewritten; fenced code, inline code, links split across lines,
indented code, and raw HTML are not. Sources are never rewritten. A rewrite
alone does not change a record's `updated` date; a scope change or a new title
does.

**Scope.** A move to another project changes the `scope` of every moved record
and is refused without `--allow-scope-change` (`allow_scope_change` in the
API). A decision whose `supersedes` lineage links it to a decision that stays
behind is refused; a pair that moves together may move. Anything else lint
would reject, such as a promoted discovery's target leaving the discovery's
project, is refused by the staged validation below.

**All or nothing.** A move holds the workspace lock, validates the current
corpus, checks the caller's SHA-256 for the moved page (and any optional
`expected` hashes), reads every file it will change, applies all changes to a
staged copy, and lints the whole staged corpus before touching the canonical
files. A caught failure while writing undoes every file and directory it had
changed. As with supersession this is not crash-atomic: if the process stops
midway, `kos lint` reports the partial state; repair it, then run `kos lint`
and `kos index`.

**API.** The routes use the write API's guard, error mapping, and response
fields, and add `title`, `project`, `folder`, `scope_changed`, and `changed:
[{"id", "old_path", "path", "content_sha256"}]`, every file created, moved, or
rewritten (`id` is `null` for a file that is not a record). `id` and
`content_sha256` describe the main record, or are `null` for a moved folder
without a `README.md`. All touched paths are one commit.

- `POST /api/projects` with `{"id", "title", "description"?}` answers `201`.
- `POST /api/projects/{project_id}/folders` with `{"path", "title", "id"?,
  "description"?}` answers `201`.
- `POST /api/projects/{project_id}/folders/move` with `{"path", "to_parent"?,
  "to_project"?, "name"?, "title"?, "allow_scope_change"?, "expected"?}`.
  `to_parent` `""` is the top level and an omitted one keeps the parent.
- `POST /api/records/{id}/move` with `{"expected_sha256", "folder",
  "project"?, "allow_scope_change"?, "expected"?}`; `folder` `""` is the top
  level.
- `POST /api/records/{id}/rename` with `{"expected_sha256", "title"}`.

The precondition model: the moved page's `expected_sha256` is required and
answers `409 conflict` when stale. The other files a move rewrites are read
under the lock, so no concurrent write is lost, and an editor still holding
their old hash gets `409` on its next save. `expected` maps workspace-relative
paths to SHA-256 hashes a caller wants unchanged. A missing record, project,
or folder answers `404`, an existing destination `409 duplicate`, a refusal
(no scope confirmation, lineage, nothing to move, a bad name) or an invalid
staged corpus `422`, and malformed fields `400`.

Project trees in `GET /api/nav` and `GET /api/projects/{id}` carry each
folder's `path` inside the project and `in_project`, false for a folder that
only groups project-scoped records filed outside the project directory (such
as observations), which cannot be moved.

The interface has "New project" in the sidebar, and each project, folder, and
page row has a menu with "New page here", "New folder", "Rename" (inline), and
"Move to…" (a keyboard-usable dialog with every project's folders). Pages and
folders can be dragged onto a folder or a project; dropping onto another
project first shows a confirmation explaining the scope change. Moves and
renames wait while an editor holds unsaved text.

MCP gets no move or rename tool. `list_projects` and `list_folder` need no
change: they read the same trees, name folders by directory name, and show a
created folder's `README.md` as its overview.

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
decision <title>`, and `Supersede decision <old title> with <new title>`, and
for structure changes `Create project <title>`, `Create folder <title>`,
`Rename <old> to <new>`, `Move <title> to <folder>` (`<folder> in <project>`
across projects, the project's title for its top level), `Move folder <title>
to <folder>`, and `Rename folder <old> to <new>`; a structure commit includes
every path the change created, removed, or rewrote. Paths removed by a move
that Git never tracked are left out. A
create or edit that carries `agent` is prefixed with the agent's name, as in
`Claude Code: Create <title>` or `Codex: Edit <title>`. The
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

**Clone.** `kos clone URL PATH` (`knowledge_os/gitsetup.py`) clones a
knowledge base into a folder that does not exist yet or is empty; a folder
with anything in it is refused (`target_not_empty`). The URL must be an
`https://`, `http://`, `ssh://`, `git://`, or `file://` address, the scp-like
`git@host:path`, or an absolute local path; a URL that carries a password or
token is refused (`bad_url`) so no credential is ever written into
`.git/config`. Git runs through the same runner as sync, with `git clone
--progress` streamed so progress can be shown, and is stopped (process tree
killed) after 30 minutes in total, after 60 seconds without any output from
Git, or on cancel. After a failed, timed-out, or cancelled clone everything
the clone wrote is removed (an empty folder that existed before stays).
After a successful clone the result must have `knowledge-os.toml` at its top
level and load as a workspace; otherwise it is `not_a_knowledge_base` and the
folder is left as it is. Then `kos lint` runs: without findings the indexes
are rebuilt; with findings they are returned and the indexes are not built.
Failures use the sync kinds plus `not_found` (no repository at that address)
and `cancelled`. With `--json` every stdout line is one JSON object:
`{"event": "progress", "phase": "clone" | "check" | "index", "line",
"percent"}`, then `{"event": "done", "root", "name", "reindexed",
"index_error", "issues"}` or `{"event": "error", "error", "detail"}`.
`--cancel-on-stdin-eof` cancels when stdin closes, which is how the desktop
app's Cancel button (and a quitting app) stops a clone.

**Guided setup.** For a knowledge base that is not in Git, has no remote, or
has never published its branch, the reader offers the steps that used to
need the command line. The setup state is `init` (not a repository, or no
commit yet), `remote` (no remote), `publish` (a remote but no upstream),
`ready`, or one the app does not set up: `git_missing`, `source_repo` (the
Knowledge OS source repository, checked before anything else, so it is never
offered `git init` either), `nested` (inside another repository), `detached`,
or `repo_error`.

- *Initialise*: `git init` (branch `main` unless `init.defaultBranch` is
  configured), add the generated-index rules to `.gitignore` when they are
  missing, stage every file Git does not ignore (unstaging any generated
  index file), and commit it as `Start versioning this knowledge base`.
  Without a Git identity the step stops before changing anything
  (`no_identity`) unless a name and email are given; those are stored in the
  repository's own configuration, never globally.
- *Identity*: store `user.name` and `user.email` repository-locally
  (`bad_identity` for an empty name or an address without `@`).
- *Check a remote*: `git ls-remote` under the no-prompt rules with the
  network timeout. A remote without any ref is empty. For a remote with
  branches, the branch to sync with (this branch's name if the remote has it,
  else the remote's default) is fetched into a temporary ref, removed again,
  to see whether it shares history with this knowledge base.
- *Connect*: add (or re-point) the remote `origin`. An empty remote gets
  `git push --set-upstream origin HEAD:refs/heads/<branch>`. A remote whose
  branch shares history becomes the upstream and an ordinary sync follows,
  which merges and may stop on conflicts like any sync. A remote with
  unrelated commits is refused as `remote_not_empty` before anything
  changes, with the advice to use an empty repository or clone that one
  instead; nothing is ever force-pushed or overwritten.

Each step checks that it still applies (`wrong_step` otherwise) and holds
the workspace lock.

- `GET /api/sync/setup` answers `{"state", "sentence", "label", "branch",
  "remote", "remote_url", "identity", "language"}`; `sentence` and `label`
  (the sync bar's text) come from `strings.SYNC_SETUP_*`, and every sync
  status also carries `"setup": {"state", "sentence", "label"}`.
- `POST /api/sync/setup/init` with `{}` or `{"name", "email"}` answers
  `{"created_repository", "files", "sha", "setup", "status"}`.
- `POST /api/sync/setup/identity` with `{"name", "email"}` answers
  `{"identity", "setup", "status"}`.
- `POST /api/sync/setup/check` with `{"url"}` (omit it to test the remote
  already configured) answers `{"check": {"url", "empty", "branches",
  "branch", "related"}, "setup", "status"}`.
- `POST /api/sync/setup/connect` with `{"url"}` (or `{}`) answers `{"state":
  "published" | "synced", "remote", "branch", "pushed", "pulled",
  "reindexed", "index_error", "setup", "status"}`, or `409 conflict` when the
  sync that follows stops on conflicts.

Refusals use the sync error shape; `bad_url` and `bad_identity` are `400`,
`remote_not_empty` and `wrong_step` `409`, `not_found` `502`.

## Agent access over MCP

The accepted `agent-access` decision gives agents a narrow interface: `kos
mcp` (`knowledge_os/agent_access/`), an MCP server on stdio built on the
official MCP Python SDK (the optional `mcp` extra, bundled in the desktop
app's frozen core, so the installed `kos` shim runs it without Python). It
serves seven tools: `search`, `read_page`, `list_projects`, `list_folder`,
`write_note`, `propose_decision`, and `list_proposed_decisions`. None accepts,
withdraws, or supersedes a decision; `write_note` refuses to edit a decision
(or a source, synthesis, or discovery), and `propose_decision` always creates
a `draft` decision, optionally declaring `supersedes`.

The server never opens a workspace. On every tool call it reads the desktop
app's runtime file, `runtime.json` in the app's user-data folder
(`%APPDATA%\knowledge-os-desktop` on Windows, `KOS_DESKTOP_USER_DATA` when
set, or `KOS_RUNTIME_FILE` naming the file). The app writes it while a
knowledge base is open and removes it when the core stops:

```json
{"version": 1, "app_version": "0.2.0", "port": 51234,
 "url": "http://127.0.0.1:51234", "write_token": "...",
 "workspace": {"root": "D:\notes\kb", "name": "kb"},
 "core_pid": 1234, "shell_pid": 999, "written_at": "2026-09-23T20:00:00.000Z"}
```

The file is readable only by the current user (on Windows an access list with
that user as the only entry, without inheritance; elsewhere mode `0600`). A
file is used only when `core_pid` is alive and `GET /api/session` on its port
returns the same write token; otherwise it is stale. The server then calls the
local API above with that token, sending `agent` with the MCP client's
`clientInfo.name` and a place: `--place`, else `KOS_AGENT_PLACE`, else the
name of the working directory the client started it in. Only a directory name
is used, never a path.

Tool results are JSON objects, also sent as text. A refusal is an error
result `{"ok": false, "error", "message", "next_step", "written"}`:
`app_not_open` (no runtime file) and `app_not_responding` (stale file) write
nothing; `request_failed` means the app stopped answering during a request,
so a write may have happened (`written: "unknown"`); `bad_request`,
`not_found`, `conflict` (with `current_sha256`), `duplicate`, `validation`
(with `issues`), `forbidden`, `not_allowed`, and `search_unavailable` wrote
nothing.

The reader describes `agent-authored` provenance as "Written by <agent> in
<place>" and the Decide inbox as "Proposed by <agent> in <place>", where a
known client name reads as the product (`claude-code` is Claude Code,
`codex-mcp-client` Codex) and any other name as itself.
`knowledge_os/agent_identity.py` holds the reference format and the names.

The protection is a guardrail, not a lock: an agent with shell access can
still run `kos` or edit Markdown directly, and any holder of the write token
can claim to be an agent. Provenance and Git history make agent writes and
every acceptance visible. The Claude Code and Codex plugins register the
server as `kos mcp` (`.claude-plugin/plugin.json` `mcpServers`,
`.codex-plugin/mcp.json`).

## CLI contract

- `kos clone URL PATH [--json] [--cancel-on-stdin-eof]` clones a knowledge base
  from Git into a new or empty folder, checks it, and rebuilds its indexes (see
  "Git versioning and sync").
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
- `kos project create`, `kos folder create`, `kos folder move`, `kos folder
  rename`, `kos move`, and `kos rename` create projects and folders and move
  or rename pages and folders (see "Structure editing").
- `kos discovery add PATH`, `review ID`, `retain ID`, `reject ID`, and
  `promote ID` implement the explicit discovery return path.
- `kos documentation init-global --workspace PATH` installs user-level host
  guidance and the global workspace location after direct authorization.
- `kos documentation init-repo --repo PATH --project ID[=RELATIVE_PATH]`
  writes one portable repository binding for one or more project scopes.
- `kos mcp [--place LABEL]` serves the agent tools over MCP on stdio through
  the running desktop app (see "Agent access over MCP"); it ignores `--root`.

Read-only context and review require a current SQLite cache and never rebuild
it implicitly. `kos index` is always safe to run as the derived-state repair
step after canonical Markdown has been repaired or a cache has been removed.
