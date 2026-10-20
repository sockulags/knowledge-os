# Builds kos-core.exe, the frozen Knowledge OS core that the packaged desktop
# app runs, into desktop\build-core\dist\kos-core. The build venv and
# PyInstaller's work folder also live under desktop\build-core (git-ignored).
#
# Knowledge OS itself is frozen from this checkout; only its runtime
# dependencies (from pyproject.toml, including the reader, mcp, and search
# extras) and PyInstaller are installed into the build venv. Installing the
# package would write setuptools build output into the repository.
#
# The dependencies come from core\requirements-core.txt, which pins every
# package, transitive ones included, by version and sha256, so two builds of
# the same commit freeze the same Python packages. Regenerate it with
# scripts\lock-core.ps1 after changing the dependencies in pyproject.toml.

$ErrorActionPreference = 'Stop'

$desktop = Split-Path -Parent $PSScriptRoot
$build = Join-Path $desktop 'build-core'
$venv = Join-Path $build 'venv'
$python = Join-Path $venv 'Scripts\python.exe'

function Invoke-Checked([string]$what, [scriptblock]$command) {
  & $command
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)." }
}

if (-not (Test-Path -LiteralPath $python)) {
  Invoke-Checked 'Creating the build venv with py -3.11' { py -3.11 -m venv $venv }
}

$lock = Join-Path $desktop 'core\requirements-core.txt'
# --only-binary: every locked package installs from a wheel, so nothing is
# built from source with unlocked build tools.
Invoke-Checked 'Installing the locked core dependencies' {
  & $python -m pip install --disable-pip-version-check --quiet `
    --require-hashes --only-binary ':all:' -r $lock
}

Invoke-Checked 'PyInstaller' {
  & $python -m PyInstaller --noconfirm --clean --log-level WARN `
    --distpath (Join-Path $build 'dist') --workpath (Join-Path $build 'work') `
    (Join-Path $desktop 'core\kos-core.spec')
}

# Smoke test: the frozen core runs and both entry modules are present.
$core = Join-Path $build 'dist\kos-core\kos-core.exe'
Invoke-Checked 'kos-core -m knowledge_os --help' { & $core -m knowledge_os --help | Out-Null }
Invoke-Checked 'kos-core -m knowledge_os.reader --help' { & $core -m knowledge_os.reader --help | Out-Null }
# The search runtime (the 'search' extra) is frozen in and loads, so search by meaning works once the model is
# downloaded; 'model status' imports it and fails when it cannot.
Invoke-Checked 'kos-core -m knowledge_os model status' { & $core -m knowledge_os model status | Out-Null }
# The MCP server imports the MCP SDK at start and exits cleanly when stdin
# closes, so an empty stdin proves the SDK was bundled. The in-app agent starts
# it with a leading -P (src/main/agents/service.ts), so test that form too.
Invoke-Checked 'kos-core -m knowledge_os mcp' { $null | & $core -m knowledge_os mcp | Out-Null }
Invoke-Checked 'kos-core -P -m knowledge_os mcp' { $null | & $core -P -m knowledge_os mcp --place 'Knowledge OS app' | Out-Null }

$size = (Get-ChildItem -LiteralPath (Split-Path -Parent $core) -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Built {0} ({1:N1} MB)" -f $core, ($size / 1MB))
