# Knowledge OS Reader — v1 plan

Status: proposed. This plan describes a read-only human reading surface over an
existing Knowledge OS workspace. It is not an accepted decision, and it changes
the frozen v0.0.1 contract, which excludes a GUI
([`docs/architecture.md`](../architecture.md)). Acceptance requires a decision
record; see "Open decisions".

## 1. Who it is for and what it solves

One person returning to a workspace they have not read for a while, on a desktop,
locally, without a network.

The v1 task is: understand what currently governs, what is merely proposed, and
why. Concretely the reader must let that person

1. open a project and see its governing decisions, open proposals, and retired
   history in that order;
2. read one record comfortably with provenance available but not dominant;
3. move between related records in both directions;
4. find a half-remembered record through search and filters;
5. see that an observation is unconfirmed before believing it.

Everything outside that list is out of scope for v1 (section 8).

## 2. Relationship to the core and to the OpenKnowledge pivot

`projects/knowledge-os/decisions/openknowledge-pivot.md` is a `draft` decision with no
`decision-acceptance` provenance, so under the current model it is proposed and
not governing. Its content still constrains this work: it says not to compete on
storage, editing, search, linking, agent integration, or Git collaboration, and
not to extend the standalone product direction before a comparison finds a
material capability that OpenKnowledge and OKF do not provide.

A read-only projection is compatible with that draft, and arguably serves it: it
makes approval-gated capture, trust boundaries, discovery review, and context
export visible enough to evaluate. An editing, syncing, or shared-service surface
would not be compatible, and would collide with the Gate 0 question about who
owns canonical Markdown writes after a pivot. A reader avoids that question
entirely.

The Gate 0 check in
[`docs/openknowledge-governance-compatibility.md`](../openknowledge-governance-compatibility.md)
reaches the same shape from the write side: the local CLI stays the reference
backend, and an adapter may change how bytes are read and committed as long as
the observable governance outcomes survive. The reader is the read-side mirror of
that boundary.

Two structural consequences follow, and they are binding on the implementation:

- **One adapter.** Exactly one module (`knowledge_os/reader/library.py`) imports
  from `knowledge_os.*`. Views consume its dataclasses only. A backend swap
  replaces the adapter, not the views.
- **No second model.** The reader never parses YAML itself, never reimplements
  validation, trust classification, or lifecycle rules, and never writes to the
  workspace. It calls `validate_workspace`, `trust_label`, `search_index`, and
  `content_sha256`.

## 3. What the core already provides, and what is missing

Provided and used directly:

| Need | Core surface |
| --- | --- |
| Parsed, validated records | `workspace.validate_workspace` |
| Trust classification | `context_policy.trust_label` |
| Lifecycle and decision semantics | `model.validate_metadata`, `record_kind`, `decision-acceptance` provenance |
| Decision supersession pairs | `workspace._validate_decision_supersession` |
| Full-text search | `index.search_index` |
| Stale-cache detection | `index.validate_index` |
| Exact content identity | `model.content_sha256` |
| Skills | `skills.load_skills` |
| Project identity invariant | `workspace._validate_project_overviews` |

Missing, and added inside the reader without touching the core:

- **Inbound relationships.** `related`, `sources`, and `supersedes` are directed,
  and the contract deliberately excludes a backlink subsystem. The reader builds
  an in-memory inbound map per request so "what points here" is answerable.
- **Per-file degradation.** `cli._inspect` refuses to work in an invalid corpus.
  The reader must parse per file, render valid records normally, and show an
  invalid record as broken with its lint message, so one bad file cannot hide
  the whole library.
- **Grouping by meaning.** No core surface groups a project's content into
  governing, proposed, historical, observed, and raw. The reader derives that
  from `status`, `record_kind`, and `type`.
- **Repo documents.** `docs/`, `SYSTEM.md`, and `README.md` are outside the
  record contract. The reader reads them as a separate, clearly labelled tier.

Explicitly not added: no new record type, no new status, no new metadata field,
no cache of its own, no write path.

## 4. Information architecture

Three zones, but the middle zone changes nature by location rather than always
being a document list. Type is a filter dimension, not a navigation axis:
`project` and `knowledge` say where a file lives, while `status` and
`record_kind` say what the reader should believe.

Five views:

- **Start, "back in".** Recently changed, open decisions awaiting a position,
  entry points per project, and a health line. No invented metrics.
- **Project.** The overview record read in full, then content grouped by meaning:
  governing now, proposed, historical, observations, raw material, and the
  separately marked tier outside the record contract. General knowledge, memory,
  and skills that are relevant appear as a side group, because they do not belong
  to the project.
- **Document.** Reading column at 68–72 characters, metadata rail on the right
  (status, trust, provenance, scope, relations in both directions, path,
  `content_sha256`), collapsible for deep reading. For long documents the rail
  swaps to a table of contents on scroll.
- **Search.** A view, not a modal. Filters on type, status, scope, `record_kind`,
  and trust. Filter state survives navigating into a document and back.
- **Everything.** Flat catalog of the whole corpus including raw sources and
  rejected discoveries, each carrying its trust label.

Four central flows: start to project to decision to provenance to related record;
search to filtered results to document and back with filters intact; decision to
supersedes or superseded-by with a side-by-side comparison; discovery to evidence
to the record the evidence points at.

Permalinks: `/r/<record-id>` for records, `/s/<skill-name>` for skills, and
`/f/<repo-relative-path>` for the unmanaged tier.

## 5. Visual direction

Direction B, "the workshop": three columns, sans typography with a clear scale,
persistent metadata rail, muted status labels, lineage visible in the reading
surface. One adjustment borrowed from direction A: the reading column takes the
archive's measure and leading (68–72 characters, 1.7 line-height), and the rail
can be switched off for single-column deep reading.

Principles:

- Status carries colour only where it changes what the reader should believe:
  proposed, unverified, retired, raw. Everything else stays neutral.
- Provenance is always one glance away and never inside the reading column.
- The unmanaged tier is visually separated by a dashed rule and an explicit label
  on every page it appears on, and never merges into a validated group.
- Own identity through typography, spacing, and restraint, not by imitating a
  known app and not through decorative chrome.
- Code and tables render properly; diagrams are deferred (section 8).

Responsive: desktop is the working surface. Below roughly 900 px the rail
collapses into a disclosure under the title; below roughly 600 px navigation
becomes a top menu. The reading column never exceeds its measure.

### Language and technical detail

The interface is in English throughout, matching the repository and the record
titles themselves. Every user-facing string lives in one module.

The reader speaks to a person, not to the schema. Contract vocabulary
(`draft`, `scope`, `provenance`, `content_sha256`, trust labels, file paths)
never appears in the primary reading path. It stays exact and reachable one
click away, under a collapsed "technical details" disclosure on every document
and project page. Titles are shown, never filenames; for unmanaged repo
documents the first heading is the title.

| Contract | What the reader says |
| --- | --- |
| decision, `draft` | "Proposal — nobody has taken a position yet" |
| decision, `active` | "In force — accepted 30 August" |
| decision, `superseded` | "Replaced by <title> on <date>" |
| ordinary `active` | "Current" |
| `deprecated` / `archived` | "Discouraged" / "Archived" |
| `verified: <date>` | "Confirmed 29 August" |
| `draft durable; not verified` | "Draft, not confirmed" |
| `active durable; not verified` | "In use, but never confirmed" |
| `raw source; not established knowledge` | "Raw material. Nobody has checked it." |
| retained discovery | "Observation — reviewed, but not knowledge" |
| proposed / rejected discovery | "Unconfirmed observation" / "Dismissed observation" |
| `scope: general` | "Applies everywhere" |
| `scope: project:<slug>` | the project's title |
| provenance `user-approved-conversation` | "A conversation you approved on 30 August 2026" |
| provenance `decision-acceptance` | "Accepted in <reference>" |
| provenance `discovery` | "Came from the observation <title>" |
| stale index | "Search may be missing recent changes. Run `kos index` to refresh." |
| outside the record contract | "Lives in the repository, not in the library. Agents never read these." |

Empty groups get a sentence, not a dash: "No decision has been superseded yet",
"No agent has left an observation here."

## 6. States that must be designed, not discovered

| State | Behaviour |
| --- | --- |
| Empty project group | The group header stays visible with an explaining sentence, for example "No decision has been superseded yet." Never hidden. |
| Empty workspace | The start page explains what a record is and points at `kos capture`, instead of rendering an empty shell. |
| Long document | The rail becomes a table of contents with anchors; `docs/architecture.md` is the real test case. |
| Broken record | Rendered in place as broken with the exact lint message and path; neighbours stay readable. |
| Broken relation | Shown as "points at unknown id X", flagged, never silently dropped. |
| Stale index | The health line says so; search is disabled with the reason and the `kos index` command; browsing still works. |
| Missing index | The same, reported as "search unavailable" rather than as an error page. |
| Unreadable content | Non-UTF-8, deleted mid-session, or rejected by `assert_safe_path`: the entry stays listed and states why it cannot be read. |
| Lint failing globally | The health line shows the count and links to the affected records; the library does not go down. |

## 7. Technical recommendation

Server-rendered Python, no build pipeline, no React.

- Package: `knowledge_os/reader/` inside this repository, installed as an
  optional extra (`pip install -e ".[reader]"`). The core stays PyYAML-only.
- Entry point: a separate console script `kos-read`, not a `kos` subcommand, so
  the frozen CLI contract in `docs/architecture.md` stays untouched and the
  reader remains physically detachable if the pivot is accepted.
- Dependencies: `starlette` and `uvicorn` for the local server, `jinja2` for
  templates, `markdown-it-py` and `pygments` for rendering. No CDN and no network
  access at runtime.
- Client: hand-written CSS and roughly 50 lines of vanilla JavaScript for
  incremental search and the rail toggle. No SPA router, no node toolchain, no
  JSON API.
- Binding: `127.0.0.1` only, no authentication, one workspace per process, and
  `--root` semantics identical to the CLI.

Why not a thin Python API plus a React client: a JSON API becomes a second public
surface to keep stable, a node build chain contradicts decision 0001's small
local stack, and the reader must be cheap to discard if the pivot is accepted.
Reading quality lives in typography and CSS, which server-rendered HTML delivers
identically.

## 8. First delivery

One coherent delivery, sequenced internally as adapter and health handling, then
views and navigation, then reading typography and responsiveness.

In scope: the five views, the adapter, the inbound-relationship map, the
unmanaged repo-document tier, every state in section 6, and the visual direction
in section 5.

Out of scope for v1: any write path, capture, acceptance or supersession from the
UI, authentication, remote or shared hosting, sync, real-time collaboration,
semantic search, a graph visualisation, dashboards or metrics, multi-workspace
switching, and Mermaid rendering. No record in the corpus uses Mermaid today; the
existing diagrams are fenced `text` blocks that render correctly as code.

### Acceptance criteria

1. `kos-read --root .` serves the library and the workspace is byte-identical
   afterwards; `git status` stays clean and no file mtime changes.
2. The start page lists the 3 records, the 3 skills, and the repo-document tier.
3. The `knowledge-os` project view shows `conversational-memory-capture` under
   governing now and `openknowledge-pivot` under proposed, with historical,
   observations, and raw material rendered as explained empty groups.
4. The document view for `openknowledge-pivot` reads as a proposal nobody has
   taken a position on, sourced from an approved conversation on 30 August 2026,
   with no contract vocabulary in the reading path. Its technical details
   disclosure holds the exact `status`, trust label, scope, path, and a
   `content_sha256` identical to `kos inspect openknowledge-pivot`.
5. Inbound relations work: in `examples/context-workspace`, opening
   `provenance-boundaries` shows that `url-ingestion-provenance` points at it
   through `related`.
6. A deliberately corrupted frontmatter file renders as broken with its lint
   message while every other record stays readable.
7. With `indexes/catalog.sqlite3` removed, browsing still works and search
   reports that it is unavailable and how to rebuild it.
8. After a record is edited without running `kos index`, the health line reports
   the index as stale.
9. The reading column measures 68–72 characters at 1440 px, and the layout
   degrades to one column below 900 px.
10. Sources and rejected discoveries are reachable, carry their trust label, and
    never appear inside a governing group.
11. The unmanaged tier is labelled as outside the record contract on every page
    where it appears.
12. `kos lint` and the existing test suite pass unchanged, and the reader is
    absent from a plain `pip install -e .`.

## 9. Open decisions and experiments

1. **A decision record allowing a read-only GUI.** The frozen contract excludes a
   GUI. Capture a `draft` decision stating that a read-only, backend-independent
   reader is permitted and that editing, sync, and shared hosting remain out of
   scope, then accept it with `kos decision accept` before implementation starts.
   This is also the first real non-plugin use of the capture path.
2. **Distribution after a pivot.** Whether the reader stays in this repository or
   moves to its own package is deferred; the adapter boundary makes it cheap
   either way.
3. **Relation to Gate 0.** If OpenKnowledge ends up owning canonical writes, the
   reader keeps its views and replaces its adapter. No reader work should assume
   the local writer.
4. **Whether to ingest the unmanaged docs.** The repo-document tier makes the gap
   visible. Deciding to ingest `docs/architecture.md` and its neighbours as
   records is a content decision, not an interface decision.
5. **Possible experiment.** If grouping by meaning proves unconvincing on real
   content, a bounded clickable prototype of the project view and one decision
   record settles it. It is not required to start.
