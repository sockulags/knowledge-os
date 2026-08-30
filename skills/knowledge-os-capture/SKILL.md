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
Knowledge OS. Do not use Agentic Work OS, a daemon, hook, cloud service, server, MCP, background
worker, silent save, model verification, or fact checking. Saving preserves the conversation's
provenance and uncertainty; it does not verify the claim.

Before creating any candidate, derive `pluginRoot` from the absolute path of this loaded
`skills/knowledge-os-capture/SKILL.md`: it is the directory two levels above that file. Verify that
`pluginRoot` contains `.codex-plugin/plugin.json` and `pyproject.toml`; never derive it from the
conversation cwd. Resolve `KNOWLEDGE_OS_ROOT` from the environment, not from the conversation cwd.

Select one Python launcher and reuse it for import preflight, optional setup, and capture. On
Windows, probe `py -3.11` and safe-no-op if it is unavailable or does not prove Python >=3.11. In
PowerShell, the selected launcher is represented by `$python = @('py', '-3.11')` and is invoked as
`& $python[0] $python[1] ...`:

```powershell
& $python[0] $python[1] -c "import sys; assert sys.version_info >= (3, 11); print(sys.executable)"
```

On macOS/Linux, probe `python3.11`; only if that is unavailable may you probe `python3` with the
same version assertion, then reuse the proven launcher. Do not use a bare `python` fallback:

```sh
if command -v python3.11 >/dev/null 2>&1 && python3.11 -c 'import sys; assert sys.version_info >= (3, 11); print(sys.executable)' >/dev/null; then
  python_cmd=python3.11
elif command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; assert sys.version_info >= (3, 11); print(sys.executable)' >/dev/null; then
  python_cmd=python3
else
  # Safe-no-op: no proven Python >=3.11 launcher is available.
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
so ask for explicit approval immediately before running it; never install silently. First detect
whether the selected launcher is running inside a virtual environment with
`sys.prefix != sys.base_prefix`. Use the actual `pluginRoot` derived from the loaded skill path.
Run exactly one approved branch:

```powershell
$venv = (& $python[0] $python[1] -c "import sys; print(sys.prefix != sys.base_prefix)").Trim()
if ($venv -eq 'True') {
  # After explicit user approval, install into the active virtual environment.
  & $python[0] $python[1] -m pip install "$pluginRoot"
} elseif ($venv -eq 'False') {
  # After explicit user approval, install into the user's Python environment.
  & $python[0] $python[1] -m pip install --user "$pluginRoot"
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
    "$python_cmd" -m pip install "$plugin_root"
    ;;
  False)
    # After explicit user approval, install into the user's Python environment.
    "$python_cmd" -m pip install --user "$plugin_root"
    ;;
  *)
    # Safe-no-op: the environment check did not return True or False.
    exit 0
    ;;
esac
```

After explicit approval and a successful install, repeat the import preflight with the same
launcher. If setup is declined, fails, or the import still fails, safe-no-op and explain what is
missing. Also safe-no-op before candidate creation when `KNOWLEDGE_OS_ROOT` is unset, missing,
invalid, maps the candidate to more than one project, or the launcher/module remains unavailable.
Never guess a workspace or project scope.

## Approved capture

For each approved candidate, exclusively create a unique directory in the operating system's temp
directory, outside the Knowledge OS root and all canonical roots (`inbox/`, `sources/`,
`discoveries/`, `knowledge/`, `projects/`, `memory/`, and `syntheses/`). Write the candidate as
`<temp-directory>/<id>.md`. Create both only after approval, refuse an unexpected existing path,
and remove only that file and the empty directory created by this skill in a `finally`-style
cleanup. Never recursively remove a broad or unresolved path.

The candidate must be a complete record with valid frontmatter. Include these fields, using the
workspace's supported values: `id`, `title`, `type` (`knowledge`, `project`, or `memory`), `status`
(`draft`), `scope`, `created`, `updated`, and non-empty `provenance`. Make `id` lowercase kebab-case
and match the `<id>.md` filename. Every provenance entry may use only `kind`, `reference`, and the
optional schema-supported `captured` or `sha256` fields. Put the user-approved conversation basis
and relevant context in `reference` and the body; do not invent approval or verification metadata.
Include uncertainty in the body, omit `verified`, and never fabricate a `sha256`. Keep the body
limited to the approved durable statement and useful context.

Invoke the storage boundary only after the approved file exists:

```powershell
& $python[0] $python[1] -m knowledge_os --root "$env:KNOWLEDGE_OS_ROOT" capture "$candidate" --json
```

POSIX shells use the same selected launcher variable, including the documented `python3` fallback:

```sh
"$python_cmd" -m knowledge_os --root "$KNOWLEDGE_OS_ROOT" capture "$candidate" --json
```

Call once per approved candidate; never pass an unapproved batch. Report the exact returned fields
that identify the outcome and record, preserving their values without inference; dump the full JSON
only when its additional fields are needed to explain an error or ambiguity. Clean up the temporary
candidate after success or failure and report any cleanup failure as a blocker.
