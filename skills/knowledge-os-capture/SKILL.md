---
name: knowledge-os-capture
description: Detects durable decisions, reusable lessons, and recurring user preferences in ordinary conversations, then batches approval-gated proposals and captures only approved records in a configured Knowledge OS workspace. Not for chatter, tentative ideas, one-off tasks, transient facts, or unverified claims.
---

# Knowledge OS capture

This automatic Knowledge OS plugin skill keeps possible durable content ephemeral until a natural
pause. Across ordinary conversations, notice only:

- a settled decision that will shape later work;
- a reusable lesson or recurring preference supported by the conversation.

Do not notice ordinary chatter, a one-off task or fact, a tentative idea, or an uncertain claim as
durable knowledge. Do not interrupt active work to propose a record. At a natural pause, batch the
short list rather than proposing after every message. Each proposal must say **what** would be
recorded, the **destination and scope**, and **why** it is durable. Let the user approve, edit, or
decline each item. `save this` or `spara detta` is direct save intent; ask only when the content or
destination is materially ambiguous. Approval of a proposal is the approval to capture it; do not
add another approval ceremony.

## Capture boundary

Never write before approval. If no item is approved, do not create a candidate file and do not call
Knowledge OS. Do not use Agentic Work OS, a daemon, hook, cloud service, background worker, silent
save, model verification, or fact checking. The only server this skill uses is the Knowledge OS MCP
server described below, and only after approval. Saving preserves the conversation's provenance and
uncertainty; it does not verify the claim.

## Capture with the Knowledge OS MCP tools

When the `knowledge-os` MCP server's tools are available in this session (the plugin registers
the server), capture through them instead of the CLI. They write to the knowledge base open in the
Knowledge OS desktop app, with its validation, conflict checks, and a Git commit that names this
agent, and they record this agent as the author in provenance. They need no Python setup and no
`KNOWLEDGE_OS_ROOT`.

1. Before proposing, `search`, `list_proposed_changes` (writes already waiting for review), and
   `list_proposed_decisions` for decisions, so a proposal extends or points at what already exists
   or waits instead of duplicating it. `read_proposed_change` shows a waiting change in full. Use
   `list_projects` to name the destination project in the proposal.
2. After approval, save an approved lesson or preference with `write_note` (title, content,
   project and folder when it belongs to a project, `status: draft` unless the person asked for it
   to be current). Save a standing preference or working agreement with `destination: memory`
   (and `project` when it applies to one project). To change an existing page, `read_page` it
   and send the complete new content with its `content_sha256` as `expected_sha256`.
3. Save an approved decision with `propose_decision`, with `supersedes` when it replaces a decision
   in force. It is stored as a proposal that governs nothing until the person accepts it in the
   app's Decide inbox; say so. There is no tool to accept, withdraw, or supersede, and approval to
   save is not acceptance.
4. When a write returns `action: waiting_for_review`, it is not saved: the knowledge base's review
   rules held it back, nothing is written yet, and the page is unchanged or does not exist. Tell the
   person that the change waits in the app's Decide inbox, where they accept or discard it, and
   name the `rule` from the result. Do not say it was saved and do not write it again.
5. Otherwise report the returned `id`, `path`, and whether `commit.committed` is true. A
   `conflict`, `duplicate`, or `validation` result wrote nothing; follow its `next_step`.

If a tool reports `app_not_open` or `app_not_responding`, nothing was written: tell the person to
open the Knowledge OS app with their knowledge base and offer to save again then. Do not fall back
to the CLI to write while the app is closed.

## CLI fallback

Use this path only when the MCP tools are not available in the session. Every command runs as
`<python> -m knowledge_os --root <root> ...` with the launcher and root selected below, never as a
bare `kos`: a bare `kos` may reach a different install on PATH and would infer the workspace from
the conversation's working directory, which is usually another repository.

Before creating any candidate, derive `pluginRoot` from the absolute path of this loaded
`skills/knowledge-os-capture/SKILL.md`: it is the directory two levels above that file. Verify that
`pluginRoot` contains `.codex-plugin/plugin.json` and `pyproject.toml`; never derive it from the
conversation cwd.

Select one Python launcher and reuse it for import preflight, optional setup, and capture. On
Windows, probe `py -3.11`, then `py -3`, and keep the first that proves Python >=3.11; safe-no-op
if neither does. In PowerShell, the selected launcher is an array such as `$python = @('py',
'-3.11')` and is invoked as `& $python[0] $python[1] ...`:

```powershell
$loadedSkillPath = '<absolute path to the loaded SKILL.md>'
$pluginRoot = (Resolve-Path (Join-Path (Split-Path -Parent $loadedSkillPath) '..\..')).Path
$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
  foreach ($launcher in @(@('py', '-3.11'), @('py', '-3'))) {
    & $launcher[0] $launcher[1] -c "import sys; assert sys.version_info >= (3, 11)" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $launcher; break }
  }
}
if (-not $python) {
  # Safe-no-op: no proven Python >=3.11 launcher is available.
  exit 0
}
```

On macOS/Linux, probe `python3.11`; only if that is unavailable may you probe `python3` with the
same version assertion, then reuse the proven launcher. Do not use a bare `python` fallback:

```sh
loaded_skill_path='<absolute path to the loaded SKILL.md>'
plugin_root="$(cd "$(dirname "$loaded_skill_path")/../.." && pwd -P)"
if command -v python3.11 >/dev/null 2>&1 && python3.11 -c 'import sys; assert sys.version_info >= (3, 11)' >/dev/null 2>&1; then
  python_cmd=python3.11
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; assert sys.version_info >= (3, 11)' >/dev/null 2>&1; then
  python_cmd=python3
else
  # Safe-no-op: no proven Python >=3.11 launcher is available.
  exit 0
fi
```

Resolve the workspace root from `KNOWLEDGE_OS_ROOT`; when it is unset, use `workspace` under
`[knowledge_os]` in `~/.knowledge-os/config.toml`, which global documentation initialization
writes. Never take it from the conversation cwd. Safe-no-op when neither gives a directory that
contains `knowledge-os.toml`:

```powershell
$root = $env:KNOWLEDGE_OS_ROOT
if (-not $root) {
  $root = "$(& $python[0] $python[1] -c "import pathlib, tomllib; p = pathlib.Path.home() / '.knowledge-os' / 'config.toml'; print(tomllib.loads(p.read_text(encoding='utf-8')).get('knowledge_os', {}).get('workspace', '') if p.is_file() else '')")".Trim()
}
if (-not $root -or -not (Test-Path -LiteralPath (Join-Path $root 'knowledge-os.toml'))) {
  # Safe-no-op: no configured Knowledge OS workspace.
  exit 0
}
```

```sh
root="${KNOWLEDGE_OS_ROOT:-}"
if [ -z "$root" ]; then
  root=$("$python_cmd" -c 'import pathlib, tomllib; p = pathlib.Path.home() / ".knowledge-os" / "config.toml"; print(tomllib.loads(p.read_text(encoding="utf-8")).get("knowledge_os", {}).get("workspace", "") if p.is_file() else "")')
fi
if [ -z "$root" ] || [ ! -f "$root/knowledge-os.toml" ]; then
  # Safe-no-op: no configured Knowledge OS workspace.
  exit 0
fi
```

Run the import preflight with the selected launcher before creating a candidate:

```powershell
& $python[0] $python[1] -c "import knowledge_os"
```

```sh
"$python_cmd" -c 'import knowledge_os'
```

If this import fails, safe-no-op before candidate creation and offer the one-time companion CLI
setup below. Installing mutates the user's Python environment and may fetch declared dependencies,
so ask for explicit approval immediately before running it; never install silently. The install
includes the `mcp` extra so the plugin's MCP server also starts without the desktop app's bundled
core. First detect whether the selected launcher is running inside a virtual environment with
`sys.prefix != sys.base_prefix`. Use the actual `pluginRoot` derived from the loaded skill path.
Run exactly one approved branch:

```powershell
$venv = "$(& $python[0] $python[1] -c "import sys; print(sys.prefix != sys.base_prefix)")".Trim()
if ($venv -eq 'True') {
  # After explicit user approval, install into the active virtual environment.
  & $python[0] $python[1] -m pip install "${pluginRoot}[mcp]"
} elseif ($venv -eq 'False') {
  # After explicit user approval, install into the user's Python environment.
  & $python[0] $python[1] -m pip install --user "${pluginRoot}[mcp]"
} else {
  # Safe-no-op: the environment check did not return True or False.
  exit 0
}
```

```sh
venv_state=$("$python_cmd" -c 'import sys; print(sys.prefix != sys.base_prefix)')
case "$venv_state" in
  True)
    # After explicit user approval, install into the active virtual environment.
    "$python_cmd" -m pip install "${plugin_root}[mcp]"
    ;;
  False)
    # After explicit user approval, install into the user's Python environment.
    "$python_cmd" -m pip install --user "${plugin_root}[mcp]"
    ;;
  *)
    # Safe-no-op: the environment check did not return True or False.
    exit 0
    ;;
esac
```

After explicit approval and a successful install, repeat the import preflight with the same
launcher. If setup is declined, fails, or the import still fails, safe-no-op and explain what is
missing. Also safe-no-op before candidate creation when the root is missing or invalid, the
candidate maps to more than one project, or the launcher/module remains unavailable. Never guess a
workspace or project scope.

## Approved capture

For each approved candidate, exclusively create a unique directory in the operating system's temp
directory, outside the Knowledge OS root and all canonical roots (`inbox/`, `sources/`,
`discoveries/`, `knowledge/`, `projects/`, `memory/`, and `syntheses/`). Write the candidate as
`<temp-directory>/<id>.md`. Create both only after approval, refuse an unexpected existing path,
and remove only that file and the empty directory created by this skill in a `finally`-style
cleanup. Never recursively remove a broad or unresolved path.

The candidate must be a complete record with valid frontmatter. Include these fields, using the
workspace's supported values: `id`, `title`, `type` (`knowledge`, `project`, or `memory`), `status`
(`draft`), `scope`, `created`, `updated`, and non-empty `provenance`. A decision also needs
`record_kind: decision`, which only `knowledge` and `project` records may carry, with `status:
draft`; without it the record is an ordinary page, not a decision. Make `id` lowercase kebab-case
and match the `<id>.md` filename. Every provenance entry may use only `kind`, `reference`, and the
optional schema-supported `captured` or `sha256` fields. Put the user-approved conversation basis
and relevant context in `reference` and the body; do not invent approval or verification metadata.
Include uncertainty in the body, omit `verified`, and never fabricate a `sha256`. Keep the body
limited to the approved durable statement and useful context.

For a `project` record, the proposal must also identify its path relative to
`projects/<project-id>/`. Use the project root by default. When the approved
destination is a nested folder or its root `README.md`, pass that exact relative
path with `--project-path`; never invent a folder that the user did not approve.

Invoke the storage boundary only after the approved file exists:

```powershell
& $python[0] $python[1] -m knowledge_os --root "$root" capture "$candidate" --writer agent --json
```

For an approved nested project destination, append `--project-path
"$approvedProjectPath"`.

POSIX shells use the same selected launcher and root, including the documented `python3` fallback:

```sh
"$python_cmd" -m knowledge_os --root "$root" capture "$candidate" --writer agent --json
```

For an approved nested project destination, append `--project-path
"$approved_project_path"`.

`--writer agent` applies the knowledge base's review rules. When a rule holds the write back, the
result's `action` is `waiting_for_review` and the change is stored as a proposed change, not as a
record: nothing is written yet. Tell the person that it waits in the app's Decide inbox, where they
accept or discard it, and name the `rule` from the result. Do not report it as saved and do not
capture it again.

Call once per approved candidate; never pass an unapproved batch. Report the exact returned fields
that identify the outcome and record, preserving their values without inference; dump the full JSON
only when its additional fields are needed to explain an error or ambiguity. Clean up the temporary
candidate after success or failure and report any cleanup failure as a blocker.

Capturing a decision stores it as a non-governing draft. Approval to store the candidate is not by
itself authority to make the decision active. Run `<python> -m knowledge_os --root <root> decision
accept ID --expected-sha256 HASH --acceptance-reference REFERENCE --json` only when the user has
also explicitly accepted the decision as governing in the current conversation. In that case, run
`<python> -m knowledge_os --root <root> inspect ID` to obtain the new record's exact
`content_sha256`, use the accepted conversation as the acceptance reference, and report the
separate activation. Never activate a replacement draft with this command; accepted replacements
must use the coordinated `<python> -m knowledge_os --root <root> supersede OLD_ID NEW_ID
--expected-old-sha256 HASH --expected-new-sha256 HASH --acceptance-reference REFERENCE --json`
operation.
