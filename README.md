# Knowledge OS

Knowledge OS `0.0.1` is a local-first durable knowledge system for Markdown
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
status, and no `verified` field. It maps the type to `knowledge/`, `projects/`,
or `memory/`, derives `<id>.md`, refuses duplicate IDs and overwrites, checks
project overview invariants in a staged whole-corpus validation, and refreshes
the indexes on success. `--json` reports the exact captured `id`, `type`,
`scope`, canonical relative `path`, and `status`. The bundled `knowledge-os`
Codex plugin owns detection, natural-pause proposal batching, and approval
handling; it invokes this CLI only after approval. There is no Agent OS
dependency and no background saving.

The plugin is distributed from this repository through
`.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`. Its
`knowledge-os-capture` skill remains automatically discoverable. Standalone
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

`knowledge-os.toml` must contain `[workspace].version = 1`. `kos lint` validates
the workspace version, all managed records, cross-record provenance and
relationship invariants, managed paths, and every skill. Skills use
`skills/<name>/SKILL.md` with validated frontmatter and a non-empty body.

## Recovery and disposable indexes

Ingest, discovery mutations, and `kos index` share one workspace advisory
lock. Mutations validate the current and intended corpus, write only minimal
canonical files, then rebuild `indexes/catalog.md` and
`indexes/catalog.sqlite3`. Promotion is not crash-atomic and no journal or
rollback system is used. If a partial lineage or index failure occurs, repair
or inspect canonical Markdown and run:

```powershell
kos lint
kos index
```

Deleting both generated index files leaves canonical Markdown valid and they
can be rebuilt with `kos index`.

## Scope

The CLI and standard-library SQLite FTS5 cache are local only. Retrieval and
review are deterministic lexical FTS plus metadata and explicit relationships;
they are not semantic fact checking or contradiction detection. No URL/PDF
ingestion, embeddings, model calls, server, GUI, MCP/API, cloud sync, or
Agentic Work OS coupling is included in v0.0.1.
