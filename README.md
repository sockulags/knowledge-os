# Knowledge OS

Knowledge OS keeps notes, decisions, and project documentation as Markdown
files in a folder on your computer. The desktop app lets you browse, search,
write, and review them; agents such as Claude Code and Codex read and write the
same folder through the app, and decisions they propose wait for you to accept
them. Nothing leaves the computer unless you sync the folder with Git.

## Get started

**Install the app.** Download `knowledge-os-setup.exe` from the latest
[release](https://github.com/sockulags/knowledge-os/releases/latest) and run
it. It is a per-user Windows installer that needs no administrator rights and
no Python. Windows SmartScreen warns about it on first run because it is not
signed. The app updates itself from later releases, and the installer puts a
`kos` command on PATH for the command line and for agents.

**Make your first page.** On the start page, choose *Create new knowledge
base…* and pick an empty folder. The app sets it up and opens it. Home then
offers *Create your first project* and *Create a page*: pages live in projects,
so *Create a page* creates the project first and then opens the new page.
Write, save, and the page is a Markdown file in the folder.

**Connect Claude Code or Codex.** In Claude Code, install the plugin:

```
/plugin marketplace add sockulags/knowledge-os
/plugin install knowledge-os
```

In Codex, install the `knowledge-os` plugin from this repository's marketplace,
or add `kos mcp` as an MCP server (see [`docs/agents.md`](docs/agents.md)).
Keep the knowledge base open in the app, then ask the agent, for example, to
write a note about what you just decided; the note appears in the app,
labelled with the agent that wrote it. The app also has its own agent panel
(Ctrl+J). [`docs/agents.md`](docs/agents.md) describes the tools, their limits,
and the skills.

The rest of this page covers the features in more detail and the `kos` command
line. The complete contract is [`docs/architecture.md`](docs/architecture.md);
the desktop app is described in [`desktop/README.md`](desktop/README.md).

## Create a separate knowledge base

The app's *Create new knowledge base…* runs `kos init`. From the command line,
`kos init PATH` creates an empty, valid workspace in a new or empty folder: the
`knowledge-os.toml` marker, the managed directories with their README files, an
`AGENTS.md` guide for agents working in the folder, a `.gitignore` for the
generated indexes, and fresh indexes, and prints the next steps. It refuses a folder that
is not empty, that already is a workspace, or that lies inside another
workspace. The workspace name defaults to the folder name in kebab-case; pass
`--name` to choose it.

```powershell
kos init D:\notes\my-kb
kos --root D:\notes\my-kb lint
kos-read --root D:\notes\my-kb
```

Every command, indexing, and the reader work against any workspace root; the
reader's UI bundle ships inside the installed package. The records in this
repository remain its own project documentation. The desktop shell in
[`desktop/`](desktop/README.md) opens and creates knowledge bases the same way.

## Organize projects and folders

`kos project create ID --title TITLE` creates a project, and `kos folder
create PROJECT PATH --title TITLE` a folder, which is written as the folder's
own `README.md` page so Git keeps it. `kos move`, `kos folder move`, `kos folder
rename`, and `kos rename` move and rename pages and folders; record IDs stay the
same and relative links to moved files are rewritten. Moving to another project
changes scope and needs `--allow-scope-change`. In the app, use "New project"
in the sidebar, each row's menu, or drag pages and folders in the project tree.
See "Structure editing" in [`docs/architecture.md`](docs/architecture.md).

Project documentation is contained by project directory. The required project
overview is `projects/<project-id>/README.md`; arbitrary folders may be nested
below it, and each folder may have its own metadata-bearing `README.md` root
record. Other records use `<id>.md`. Create a record at a chosen nested path
with `kos capture CANDIDATE.md --project-path architecture/decisions/README.md`.

## Write pages: templates, images, and files

*New page* starts from a template: blank, meeting notes, how-to, decision
(Context / Decision / Alternatives considered / Consequences, which creates a
proposed decision), requirement, or plan.
Templates are ordinary Markdown files in the knowledge base's `templates/`
folder, which `kos init` fills with the built-in ones; edit them, or add
`templates/<name>.md` with optional `title`, `description`, and `kind: note`
or `kind: decision` frontmatter. `{{date}}` becomes the day the page is
created. A file named like a built-in template replaces it, and a knowledge
base without `templates/` gets the built-in templates. A template that cannot
be read is shown with the reason instead of being offered.

In the editor, paste or drop an image or a file into the text, or use
*Attach file*. It is stored in an `assets/` folder next to the page (for
example `projects/acme/notes/assets/diagram.png`), linked with a relative
path such as `![diagram](assets/diagram.png)`, shown in the preview and on
the page, and committed like any other change. Moving a page moves the files
only it links to; deleting a page deletes them, and the confirmation says so.
A file another page also links to stays where it is. Files up to 25 MB can
be attached; Markdown files cannot. A folder cannot be named `assets`. See
"Attachments" in [`docs/architecture.md`](docs/architecture.md).

A folder's own page (its `README.md`) and a project's overview are edited
like any other page.

## Review before writes land

Notes are written directly by default and decisions are always drafts. To
look at some writes first, add rules to `knowledge-os.toml`:

```toml
[[review.rule]]
folder = "drafts"      # everything in a drafts/ folder is direct
action = "direct"

[[review.rule]]
writer = "agent"       # notes agents write in project acme need review
project = "acme"

[[review.rule]]
writer = "referat"     # Referat imports go to review
```

A rule may name `writer` (`agent`, `agent:claude-code`, `referat`, `person`,
`any`), `project` (or `general`), `folder`, `writes` (`create`, `edit`,
`any`), and `action` (`review` or `direct`); the first match decides. A held
back write is stored in `proposals/` and waits in **Decide** next to proposed
decisions, where Accept writes it and Discard drops it, each in one click with
Undo. An edit whose page changed in the meantime can only be discarded.
Agents are told in the tool result that their write waits for review; an
agent on the command line passes `--writer agent` to `kos capture` or `kos
update` to get the same treatment. On the command line, `kos proposal list`
and `kos proposal show ID` list and show proposed changes, and `kos proposal
accept|discard ID --expected-sha256 HASH` (the hash `show` prints) accepts or
discards one as Decide does, without the Git commit. `kos lint` checks the
rules. See
"Configurable review" in [`docs/architecture.md`](docs/architecture.md).

## Sync a knowledge base with Git

The knowledge base folder must be its own Git repository with an upstream
branch. In the app, the Sync page walks you through it: start versioning (a
first commit of the current files), paste the address of an empty repository,
test it, and publish. On another computer, File → Clone Knowledge Base… clones
it from its URL and opens it (`kos clone URL PATH` does the same from the
command line). By hand, the setup is:

```powershell
cd D:\notes\my-kb
git init -b main
git add -A
git commit -m "Initial knowledge base"
git remote add origin <url>
git push -u origin main
```

The app then commits every change it writes (only the files that change, with
messages such as `Edit <title>`), shows branch, commits to push and pull,
uncommitted changes, and the last sync time in its header, and syncs with the
Sync button: fetch and merge, rebuild the indexes, then push. Conflicting files
are shown side by side on the Sync page; choose a version or write a merged one,
and the sync finishes only when the result passes `kos lint`. Git must be on
`PATH` and uses your own identity, credential helper, and SSH agent; the app
never asks for credentials. CLI commands do not commit. See "Git versioning and
sync" in [`docs/architecture.md`](docs/architecture.md).

## Search by meaning

Search finds exact words out of the box. The Search page also offers to
download a search model (about 590 MB, bge-m3, stays on this computer), after
which search also finds pages close in meaning, in Swedish or English, even
when they use other words; such results are labeled "Similar in meaning".
Nothing is sent anywhere: the model runs locally and its files are checked
against pinned hashes. From the command line, `kos model install` downloads it
(a Python install needs `pip install -e ".[search]"` for the runtime) and `kos
index` then builds `indexes/semantic.sqlite3`. See the decision
`local-semantic-search` and "Search by meaning" in
[`docs/architecture.md`](docs/architecture.md).

## Command line

Most of what the app does also has a `kos` command, and the sections below
describe the commands that have no button in the app. `kos --help` lists them
all, and `kos COMMAND --help` describes one. `--root PATH` names the knowledge
base; without it, the knowledge base is found from the current directory. Many
commands take `--json` for scripts.

The installer puts `kos` on PATH (see "The `kos` command" in
[`desktop/README.md`](desktop/README.md)); a checkout gets the same command from
`pip install -e .`. When both are on PATH, whichever directory comes first wins
for a bare `kos`. `where kos` (PowerShell) or `which kos` (POSIX shells) lists
them in the order they are tried, and `kos --version` reports the version and
where that `kos` runs from: `installed app (bundled core at ...)`, or `Python
X.Y.Z at <interpreter>, package at <path>` (with `(editable install)` when
detectable). When the app's `kos` runs but a bare `kos` would reach another
one, or a Python `kos` runs while the app is also installed, `kos` prints a
one-line warning to stderr (never stdout, so `--json` output and `kos mcp`'s
stdio protocol stay clean) saying how to fix it: uninstall the pip package
(`py -3.11 -m pip uninstall knowledge-os`) or reorder PATH. Set
`KOS_NO_PATH_WARNING=1` to silence it.

Agents do not run a bare `kos`; see "When the MCP tools are not available" in
[`docs/agents.md`](docs/agents.md).

## Run from source

To work on Knowledge OS itself, or to use it without the app, install it from a
checkout with Python 3.11 or newer. PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\Activate.ps1
kos lint
kos index
```

Cross-platform:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
kos lint
kos index
```

The workspace root is found from the current directory or with `kos --root
PATH`. Try `kos ingest examples/sample.md`, then `kos search xylophone --json`,
and `kos inspect <id>`. `inbox/` is intentionally outside the managed record
contract. Add the `reader` and `mcp` extras (`pip install -e ".[reader,mcp]"`)
for `kos-read` and `kos mcp`; running and building the desktop app from source
is described in [`desktop/README.md`](desktop/README.md).

## Agents (MCP)

Agents reach the knowledge base through `kos mcp`, an MCP server that works
only through the running desktop app, so agent writes get the same validation,
review rules, and Git commits as your own edits. It cannot accept, withdraw, or
supersede a decision. Every agent write carries `agent-authored` provenance
naming the agent and where it ran. The tools, the error results, the in-app
agent panel, the documentation check for linked code repositories, and the
capture and documentation skills are described in
[`docs/agents.md`](docs/agents.md).

## Capture an approved record

The cross-chat integration writes only after approval by passing a complete
Markdown candidate to the create-only capture primitive:

```powershell
kos --root $env:KNOWLEDGE_OS_ROOT capture .\approved-candidate.md --json
# Or from another cwd:
py -3.11 -m knowledge_os --root $env:KNOWLEDGE_OS_ROOT capture .\approved-candidate.md --json
```

Capture accepts only `knowledge`, `project`, and `memory` records with valid
schema/frontmatter, a non-empty body and provenance, `draft` or `active`
status, and no `verified` field. It maps the type to `knowledge/`, a scoped
project directory, or `memory/`, refuses duplicate IDs and overwrites, checks
project overview invariants in a staged whole-corpus validation, and refreshes
the indexes on success. Project records default to
`projects/<project-id>/<id>.md`, while the overview defaults to
`projects/<project-id>/README.md`; `--project-path` chooses any safe nested
Markdown path below that project directory. `--json` reports the exact captured
`id`, `type`, `scope`, canonical relative `path`, and `status`. The plugin's
`knowledge-os-capture` skill owns detection, proposal batching, and approval
handling, and calls capture only after approval (see "Capture skill" in
[`docs/agents.md`](docs/agents.md)).

Decision records are always captured as `draft`. Activate an accepted decision
with the exact hash returned by `kos inspect ID`:

```powershell
$hash = (kos inspect decision-id | ConvertFrom-Json).content_sha256
kos decision accept decision-id --expected-sha256 $hash --acceptance-reference conversation:approval
```

The transition adds explicit `decision-acceptance` provenance. Ordinary capture
or update cannot make a decision active.

A draft that is not a decision, such as a draft promoted from a discovery, is
made active by a person with `kos activate` (or "Make active" on its page in
the app), which adds `draft-activation` provenance:

```powershell
kos activate record-id --expected-sha256 $hash --activation-reference conversation:approval
```

## Update and supersede records safely

`kos update` uses optimistic concurrency. Supply a complete candidate and the
SHA-256 of the exact canonical bytes it was based on:

```powershell
kos update .\updated-record.md --expected-sha256 $hash
```

A stale hash fails without changing Markdown or indexes. Identity, lifecycle,
`supersedes`, discovery lineage, and decision acceptance lineage cannot be
changed through this operation. Changing the body of an accepted decision is
reserved for an explicitly non-material correction:

```powershell
kos update .\editorial-correction.md --expected-sha256 $hash `
  --confirm-non-material --change-reference conversation:editorial-approval
```

A material decision change is a new draft. It declares exactly one prior
decision in `supersedes`; the prior decision remains active while the draft is
reviewed. Acceptance uses the coordinated operation:

```powershell
kos supersede old-decision new-decision `
  --expected-old-sha256 $oldHash `
  --expected-new-sha256 $newHash `
  --acceptance-reference conversation:replacement-approval
```

This makes the replacement active and the prior decision superseded under one
workspace lock. Caught write failures restore both original records when
possible. Abrupt process termination is still not crash-atomic; inspect both
records and run `kos lint` followed by `kos index` when partial-state recovery
is reported.

## Export bounded context

After indexing a workspace, export deterministic, trust-aware, project-scoped
context for an external agent:

```powershell
kos --root examples/context-workspace index
kos --root examples/context-workspace context --project knowledge-os --task "Add URL ingestion while preserving provenance" --budget 12000 > context.md
```

Use repeatable `--require ID` options for governing records that must be present
regardless of lexical ranking. Required IDs still obey the requested project's
scope, lifecycle, type, and trust policy; they cannot import another project's
records. All mandatory items must fit in full or generation fails.

Each package manifest records workspace name/schema marker and the exact content
SHA-256 of every selected record and skill. Check later drift with:

```powershell
kos context verify .\context.md --json
```

The verifier reports each item as `unchanged`, `changed`, `missing`, or
`ineligible`, and separately reports whether the workspace identity still
matches.

Context includes the exact project overview, eligible general/project durable
records, retained discoveries from that project, and relevant skills. Raw
sources, other project scopes, and non-eligible lifecycle states are excluded.
Every selected item exposes its type, record kind, scope, status, trust label,
path, provenance, and selection evidence. The output is generated,
non-canonical Markdown and is safe to discard. See
[`examples/context-workspace/README.md`](examples/context-workspace/README.md).

## Record an external discovery safely

An external agent may write a structured proposed discovery, but it does not
become knowledge implicitly. Review it, retain it only as project-scoped
reviewed memory, or promote it into a new draft record:

```powershell
kos discovery add .\examples\discovery.md
kos discovery review observed-provenance-boundary
kos discovery retain observed-provenance-boundary --reviewer Lucas --reason "Evidence is sufficient for project memory"
kos discovery promote observed-provenance-boundary --target-id provenance-boundary-draft --title "Provenance boundary" --scope project:knowledge-os --acknowledge-related
```

Promotion is promote-new only. The target's direct provenance and the
discovery's promote review target are the only promotion lineage. Promotion
never merges, overwrites, supersedes, or adds duplicate `sources`/`related`
links. A project-scoped discovery promoted to `general` additionally requires
`--allow-scope-broadening`.

## Trust and metadata

Sources are raw captured material and remain searchable for audit, but are not
default context. Ordinary lifecycle statuses are exactly `draft`, `active`,
`deprecated`, `superseded`, and `archived`; `verified` is not a status. An
optional `verified` ISO date independently produces the `verified durable`
classification. `record_kind` is optional only for `knowledge` and `project`
records, with `ordinary` (the default) or `decision`.

For decisions, `draft` means proposed, `active` means explicitly accepted and
current, and `superseded` means replaced by an accepted successor. Active and
superseded decisions require `decision-acceptance` provenance. Acceptance does
not imply implementation or verification.

Existing version-1 workspaces with older active decision records need one
explicit, reviewable metadata correction: add `decision-acceptance` provenance
that references the real acceptance basis, or return the record to `draft` when
no such acceptance exists. Do not invent acceptance merely to satisfy lint.

`knowledge-os.toml` must contain `[workspace].version = 1`. `kos lint` validates
the workspace version, all managed records, cross-record provenance and
relationship invariants, managed paths, and every skill. Skills use
`skills/<name>/SKILL.md` with validated frontmatter and a non-empty body.

## Recovery and disposable indexes

Ingest, capture, update, decision acceptance, supersession, discovery mutations,
and `kos index` share one workspace advisory
lock. Mutations validate the current and intended corpus, write only minimal
canonical files, then rebuild `indexes/catalog.md` and
`indexes/catalog.sqlite3`. Promotion and supersession are not crash-atomic and no journal or
rollback system is used. If a partial lineage or index failure occurs, repair
or inspect canonical Markdown and run:

```powershell
kos lint
kos index
```

Deleting both generated index files leaves canonical Markdown valid and they
can be rebuilt with `kos index`. The reader (`kos-read` and the desktop app)
also rebuilds a stale or missing index by itself in the background; start it
with `--no-index-refresh` to leave the index alone.

## Scope

The CLI, the local reader server and desktop app, and the standard-library
SQLite FTS5 cache are local only; there is no cloud or remote service.
Retrieval is lexical FTS plus metadata and explicit relationships, and, with
the optional local search model, similarity in meaning; neither is fact
checking or contradiction detection. No URL/PDF ingestion, calls to a hosted
model, or Agentic Work OS coupling is included. The only MCP surface is `kos mcp`, which works through
the running desktop app (see [Agents (MCP)](#agents-mcp)). The local reader exposes a JSON API for
editing records and decision actions, and workspaces that are their own Git
repository get versioned writes and Git-based sync (pull, push, and conflict
resolution) through it; see "[Sync a knowledge base with
Git](#sync-a-knowledge-base-with-git)" above.
