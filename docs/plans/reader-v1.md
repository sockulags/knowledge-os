# Knowledge OS Reader — v1 plan

> **Note (2026-09-22):** the `openknowledge-pivot` decision referenced below
> was withdrawn on 2026-09-22. Knowledge OS continues as a standalone project;
> see the draft decision
> `projects/knowledge-os/decisions/standalone-learning-direction.md`. This
> document is kept as-is for historical context and is not rewritten.

Status: accepted. This plan describes a read-only human reading surface over an
existing Knowledge OS workspace. It changes the frozen v0.0.1 contract, which
excludes a GUI ([`docs/architecture.md`](../architecture.md)), and is authorized
by the `knowledge-os-reader` decision, accepted on 12 September 2026. The visual
direction (section 5) and the stack (section 7) were revised on 19 September 2026
after the first server-rendered build proved hard to use.

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
- **Repo documents.** Most project documentation now lives in the corpus under
  `projects/knowledge-os/`. What remains outside the record contract is
  `docs/architecture.md`, `docs/architecture-audit-v0.1.md`,
  `docs/openknowledge-governance-compatibility.md`, `docs/decisions/`,
  `docs/plans/`, `SYSTEM.md`, and `README.md`. The reader shows them as a
  separate, clearly labelled tier. The tier is smaller than when this plan was
  first written and may shrink further.

Explicitly not added: no new record type, no new status, no new metadata field,
no cache of its own, no write path.

## 4. Information architecture

The project directory tree is the navigation, following the accepted
`project-directory-layout` decision: each project owns
`projects/<project-id>/`, directories nest freely, and any directory may carry a
root `README.md` record. Grouping by meaning applies within a project and
primarily to decisions.

Three zones, but the middle zone changes nature by location rather than always
being a document list. Type is a filter dimension, not a navigation axis:
`project` and `knowledge` say where a file lives, while `status` and
`record_kind` say what the reader should believe.

Five views:

- **Start, "back in".** Recently changed, open decisions awaiting a position,
  entry points per project, and a health line. No invented metrics.
- **Project.** Opens with the project's decisions grouped by meaning: in force
  now, waiting on you, and replaced. Then the overview record's body, the pages in
  the project, observations, raw material, and the separately marked tier outside
  the record contract. General knowledge, memory,
  and skills that are relevant appear as a side group, because they do not belong
  to the project.
- **Document.** Reading column at 68–72 characters. Under the title, a compact
  properties block: status, trust, what it applies to, when it was updated, and
  where it came from. The exact contract values (path, `content_sha256`, raw
  provenance) sit in a collapsed technical details toggle. Relations in both
  directions appear at the end of the page as "Linked from" and "Links to". Long
  documents get an "On this page" outline on wide screens.
- **Search.** A full view with filters on type, status, scope, `record_kind`, and
  trust. Filter state survives navigating into a document and back. A quick-find
  palette (`Ctrl K`) jumps to any record by title, even without a search index.
- **Everything.** Flat catalog of the whole corpus including raw sources and
  rejected discoveries, each carrying its trust label.

Four central flows: start to project to decision to provenance to related record;
search to filtered results to document and back with filters intact; decision to
supersedes or superseded-by with a side-by-side comparison; discovery to evidence
to the record the evidence points at.

Permalinks: `/r/<record-id>` for records, `/s/<skill-name>` for skills, and
`/f/<repo-relative-path>` for the unmanaged tier.

## 5. Visual direction

A calm, modern workspace in the spirit of Notion: a left sidebar holding the
project tree, skills, and repository documents; a centred reading column at the
archive's measure and leading (68–72 characters, 1.6–1.7 line-height); page
properties under the title instead of a side rail; and relations as backlinks at
the end of the page.

Principles:

- Status carries colour only where it changes what the reader should believe: in
  force, proposed, unverified, retired, raw. Everything else stays neutral.
- Provenance is always one glance away, in the properties block, and never inside
  the body text.
- The unmanaged tier carries an explicit label on every page it appears on and
  never merges into a validated group.
- Match the feel of modern knowledge tools (whitespace, soft radii, hairline
  borders, light and dark themes) without copying any product's brand.
- Code and tables render properly; diagrams are deferred (section 8).

Responsive: desktop is the working surface. Below roughly 768 px the sidebar
becomes a drawer and the page is a single column. The reading column never
exceeds its measure.

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
| Long document | An "On this page" outline with anchors appears on wide screens; `docs/architecture-audit-v0.1.md` is the real test case. |
| Broken record | Rendered in place as broken with the exact lint message and path; neighbours stay readable. |
| Broken relation | Shown as "points at unknown id X", flagged, never silently dropped. |
| Stale index | The health line says so; search is disabled with the reason and the `kos index` command; browsing still works. |
| Missing index | The same, reported as "search unavailable" rather than as an error page. |
| Unreadable content | Non-UTF-8, deleted mid-session, or rejected by `assert_safe_path`: the entry stays listed and states why it cannot be read. |
| Lint failing globally | The health line shows the count and links to the affected records; the library does not go down. |

## 7. Technical recommendation

A Python backend with a React client.

- Package: `knowledge_os/reader/` inside this repository, installed as an
  optional extra (`pip install -e ".[reader]"`). The core stays PyYAML-only.
- Entry point: a separate console script `kos-read`, not a `kos` subcommand, so
  the frozen CLI contract in `docs/architecture.md` stays untouched and the
  reader remains physically detachable if the pivot is accepted.
- Backend: `starlette` and `uvicorn` serve a local, read-only JSON API under
  `/api/` and the built client. `markdown-it-py` and `pygments` render Markdown on
  the server, so link rewriting and every contract-to-language translation stay
  in Python. No CDN and no network access at runtime.
- Client: React, TypeScript, Vite, and Tailwind CSS in `reader-ui/`. The built
  bundle is committed under `knowledge_os/reader/static/app/`, so installing and
  running the reader needs no Node toolchain; Node is only needed to change the
  interface.
- Binding: `127.0.0.1` only, no authentication, one workspace per process, and
  `--root` semantics identical to the CLI.

The JSON API is a local interface between the reader's own server and client, not
a public surface; it carries no stability promise beyond the reader. The first
build was server-rendered HTML with hand-written CSS. It was correct but hard to
use, and a component-based client makes a modern interface much cheaper to build
and to change.

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
2. The start page lists every record in the corpus, the skills, and the
   repo-document tier.
3. The `knowledge-os` project view reproduces the directory tree under
   `projects/knowledge-os/`, and its decisions group as in force now
   (`conversational-memory-capture`, `project-directory-layout`,
   `knowledge-os-reader`) and waiting on you (`openknowledge-pivot`), with
   replaced decisions,
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
   becomes a single column with the sidebar as a drawer below 768 px.
10. Sources and rejected discoveries are reachable, carry their trust label, and
    never appear inside a governing group.
11. The unmanaged tier is labelled as outside the record contract on every page
    where it appears.
12. `kos lint` and the existing test suite pass unchanged, and the reader is
    absent from a plain `pip install -e .`.

## 9. Open decisions and experiments

1. **Accepting the reader decision.** Resolved: `knowledge-os-reader` was
   accepted with `kos decision accept` on 12 September 2026, before
   implementation started. The direction is recorded separately as
   `knowledge-os-reader-design`.
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
