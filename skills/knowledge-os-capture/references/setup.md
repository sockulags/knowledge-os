# Setup for the CLI fallback

Read this only when the Knowledge OS MCP tools are not available and you need a Python launcher,
the workspace root, or the one-time install of the companion CLI. Every command runs as
`<python> -m knowledge_os --root <root> ...` with the launcher and root selected below, never as a
bare `kos`: a bare `kos` may reach a different install on PATH and would infer the workspace from
the conversation's working directory, which is usually another repository.

## Plugin root

Before creating any candidate, derive `pluginRoot` from the absolute path of the loaded
`skills/knowledge-os-capture/SKILL.md` (not of this reference file): it is the directory two levels
above that file. Verify that `pluginRoot` contains `.codex-plugin/plugin.json` and
`pyproject.toml`; never derive it from the conversation cwd.

## Python launcher

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

## Workspace root

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

## Import preflight and one-time install

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
