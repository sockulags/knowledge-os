# Knowledge OS

Knowledge OS `0.5.0` is a local-first durable knowledge system for Markdown
and text. Markdown is canonical truth. Sources and external-agent discoveries
remain separate trust boundaries, while SQLite and the catalog are disposable
indexes. Its root Codex plugin provides automatic, approval-gated conversational
capture; the deterministic storage boundary remains the local CLI. The complete
frozen contract is [`docs/architecture.md`](docs/architecture.md).

## Bootstrap

PowerShell:

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
contract.

## Create a separate knowledge base

A knowledge base does not have to live in this repository. `kos init PATH`
creates an empty, valid workspace in a new or empty folder: the
`knowledge-os.toml` marker, the managed directories with their README files, a
`.gitignore` for the generated indexes, and fresh indexes. It refuses a folder that
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

## Command line

The desktop app installer puts a `kos` command on PATH (see "The `kos` command" in
[`desktop/README.md`](desktop/README.md)); a checkout gets the same command from `pip install -e .`
instead. Both can end up on PATH at once, and whichever directory comes first wins for a bare `kos`
invocation, which can silently run the wrong one. `where kos` (PowerShell) or `which kos` (POSIX
shells) lists every `kos` on PATH in the order Windows or the shell will try them, with the one that
actually runs listed first. `kos --version` reports the version and where that particular `kos` runs
from: `installed app (bundled core at ...)` for the app's bundled core, or `Python X.Y.Z at
<interpreter>, package at <path>` (with `(editable install)` appended when detectable) for a Python
install. When the app's `kos` runs but a bare `kos` on PATH would reach a different one, or a Python
`kos` runs while the app is also installed, `kos` prints a one-line warning to stderr (never stdout,
so `--json` output and `kos mcp`'s stdio protocol stay clean) saying how to fix it: uninstall the pip
package (`py -3.11 -m pip uninstall knowledge-os`) or reorder PATH. Set `KOS_NO_PATH_WARNING=1` to
silence it.

Agents reach the knowledge base through `kos mcp` (below), never a bare `kos`; people and scripts
use the plain `kos` command directly.

## Agents (MCP)

Agents such as Claude Code and Codex working in other repositories use the knowledge base through
an MCP server, `kos mcp`; people and scripts keep the `kos` command line (see the accepted decision
`projects/knowledge-os/decisions/agent-access.md`). The server works only through the running
desktop app: it talks to the app's local API and acts on the knowledge base open there, so agent
writes get the same validation, conflict checks, and Git commits as your own edits and show up in
the app as they happen. When the app is closed or no knowledge base is open, every tool says so and
nothing is written.

| Tool | What it does |
| --- | --- |
| `search` | Full-text search (`query`, optional `project`, `limit`). |
| `read_page` | One page by `id`: Markdown content, state, project, folder, links, provenance, and `content_sha256`. |
| `list_projects` | Project ids, titles, and top-level folders. |
| `list_folder` | A project folder's overview, pages, and subfolders (`project`, optional `folder`). |
| `write_note` | Create a note (`title`, `content`, optional `project`, `folder`, `tags`, `status`) or edit one (`id`, `content`, `expected_sha256`). Decisions cannot be edited. |
| `propose_decision` | Create a decision as a draft (`title`, `content`, optional `project`, `folder`, `supersedes`, `related`). |
| `list_proposed_decisions` | The Decide inbox: drafts waiting for a person, with who proposed them. |

There is no tool to accept, withdraw, or supersede a decision; those stay yours, in the app or the
command line. Failures come back as structured results with an `error` kind (`app_not_open`,
`app_not_responding`, `conflict`, `duplicate`, `validation`, `not_found`, `not_allowed`, ...), a
`message`, a `next_step`, and whether anything was `written`.

Every agent write carries provenance `agent-authored` with reference `agent:<client>:<place>`:
the client name the agent reports over MCP (`claude-code`, `codex-mcp-client`, ...) and where it
ran, which is `kos mcp --place LABEL`, else `KOS_AGENT_PLACE`, else the name (never the path) of
the directory the agent started the server in. The app shows it as "Proposed by Claude Code in
my-repo", and the commit reads `Claude Code: Create <title>`. This is a guardrail, not a lock: an
agent with shell access can still run `kos` or edit files; provenance and Git history make its
writes visible.

**Setup.** Install the desktop app (it puts `kos` on PATH with the MCP server built in) or, in a
checkout, `pip install -e ".[reader,mcp]"`. Then:

- Claude Code: install the plugin (below); it registers the `knowledge-os` MCP server. Without the
  plugin: `claude mcp add knowledge-os -- kos mcp` (add `--scope user` to use it in every project).
- Codex: install the plugin from this repository's marketplace; `.codex-plugin/mcp.json`
  registers the server. Without the plugin, add to `~/.codex/config.toml`:

  ```toml
  [mcp_servers.knowledge-os]
  command = "kos"
  args = ["mcp"]
  ```

Open the knowledge base in the app before asking the agent to use it. The server finds the app
through a runtime file the app keeps in its user-data folder while a knowledge base is open (see
"Agents and the runtime file" in [`desktop/README.md`](desktop/README.md)).

## Documentation skill

The automatically discoverable `knowledge-os-documentation` skill supports one-time setup and
normal documentation retrieval. Global setup requires direct authorization because it writes the
managed blocks in the user-level Codex and Claude files and `~/.knowledge-os/config.toml`:

```text
kos documentation init-global --workspace PATH [--host codex] [--host claude] [--user-home PATH] [--replace] [--json]
```

Repository setup writes `.knowledge-os-project.toml` with one or more project bindings:

```text
kos documentation init-repo --repo PATH --project ID[=RELATIVE_PATH] [--project ...] [--user-home PATH] [--replace] [--json]
```

After setup, the skill searches before inspection or context export, reads each affected project's
overview and nearest relevant folder `README.md`, and keeps current behavior, decisions, drafts,
raw sources, and discoveries distinct. Search results are not automatically verified. Writes need
authorization from the current request or repository policy. See
[`skills/knowledge-os-documentation/references/init.md`](skills/knowledge-os-documentation/references/init.md)
and [`skills/knowledge-os-documentation/references/documentation-workflow.md`](skills/knowledge-os-documentation/references/documentation-workflow.md).

Project documentation is contained by project directory. The required project
overview is `projects/<project-id>/README.md`; arbitrary folders may be nested
below it, and each folder may have its own metadata-bearing `README.md` root
record. Other records use `<id>.md`. Create a record at a chosen nested path
with `kos capture CANDIDATE.md --project-path architecture/decisions/README.md`.

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
`id`, `type`, `scope`, canonical relative `path`, and `status`. The bundled `knowledge-os`
Codex plugin owns detection, natural-pause proposal batching, and approval
handling; it invokes this CLI only after approval. There is no Agent OS
dependency and no background saving.

Decision records are always captured as `draft`. Activate an accepted decision
with the exact hash returned by `kos inspect ID`:

```powershell
$hash = (kos inspect decision-id | ConvertFrom-Json).content_sha256
kos decision accept decision-id --expected-sha256 $hash --acceptance-reference conversation:approval
```

The transition adds explicit `decision-acceptance` provenance. Ordinary capture
or update cannot make a decision active.

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

The plugin is distributed from this repository through
`.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json` for Codex,
and through `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`
for Claude Code. Install the Claude Code plugin with:

```
/plugin marketplace add sockulags/knowledge-os
/plugin install knowledge-os
```

Its `knowledge-os-capture` skill remains automatically discoverable. Standalone
means the skill and its companion CLI source are owned and distributed here;
the CLI package still needs one explicit, one-time local setup when it is not
already importable. The skill derives the plugin root from its loaded
`SKILL.md`, asks before installing, and safely does nothing when setup is
declined or unavailable.

On Windows PowerShell, set `$loadedSkillPath` to the absolute path of the
loaded `skills/knowledge-os-capture/SKILL.md`, derive `$pluginRoot` from it, and
use the selected Python 3.11 launcher for setup:

```powershell
$loadedSkillPath = '<absolute path to the loaded SKILL.md>'
$pluginRoot = (Resolve-Path (Join-Path (Split-Path -Parent $loadedSkillPath) '..\..')).Path
$python = @('py', '-3.11')
$venv = (& $python[0] $python[1] -c "import sys; print(sys.prefix != sys.base_prefix)").Trim()
if ($venv -eq 'True') {
  & $python[0] $python[1] -m pip install "$pluginRoot"
} elseif ($venv -eq 'False') {
  & $python[0] $python[1] -m pip install --user "$pluginRoot"
} else {
  Write-Output 'No valid virtual-environment state; safe-no-op.'
  exit 0
}
```

On macOS/Linux, derive the root from the loaded skill path and use
`python3.11`, or a `python3` fallback only after proving it is Python >=3.11:

```sh
loaded_skill_path='<absolute path to the loaded SKILL.md>'
plugin_root="$(cd "$(dirname "$loaded_skill_path")/../.." && pwd -P)"
if command -v python3.11 >/dev/null 2>&1 && python3.11 -c 'import sys; assert sys.version_info >= (3, 11)' >/dev/null; then
  python_cmd=python3.11
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; assert sys.version_info >= (3, 11)' >/dev/null; then
  python_cmd=python3
else
  echo 'No proven Python >=3.11 launcher; safe-no-op.'
  exit 0
fi
venv_state=$("$python_cmd" -c 'import sys; print(sys.prefix != sys.base_prefix)')
case "$venv_state" in
  True) "$python_cmd" -m pip install "$plugin_root" ;;
  False) "$python_cmd" -m pip install --user "$plugin_root" ;;
  *) echo 'No valid virtual-environment state; safe-no-op.'; exit 0 ;;
esac
```

The skill asks for approval immediately before the selected install command,
then rechecks `import knowledge_os` with that same launcher before any
candidate is created.

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
can be rebuilt with `kos index`.

## Scope

The CLI, the local reader server and desktop app, and the standard-library
SQLite FTS5 cache are local only; there is no cloud or remote service.
Retrieval and review are deterministic lexical FTS plus metadata and explicit
relationships; they are not semantic fact checking or contradiction
detection. No URL/PDF ingestion, embeddings, model calls, or Agentic Work OS
coupling is included. The only MCP surface is `kos mcp`, which works through
the running desktop app (see [Agents (MCP)](#agents-mcp)). The local reader exposes a JSON API for
editing records and decision actions, and workspaces that are their own Git
repository get versioned writes and Git-based sync (pull, push, and conflict
resolution) through it; see "[Sync a knowledge base with
Git](#sync-a-knowledge-base-with-git)" above.
