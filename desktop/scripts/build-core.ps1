# Builds kos-core.exe, the frozen Knowledge OS core that the packaged desktop
# app runs, into desktop\build-core\dist\kos-core. The build venv and
# PyInstaller's work folder also live under desktop\build-core (git-ignored).
#
# Knowledge OS itself is frozen from this checkout; only its runtime
# dependencies (from pyproject.toml, including the reader and mcp extras) and
# PyInstaller are installed into the build venv. Installing the package would
# write setuptools build output into the repository.

$ErrorActionPreference = 'Stop'
$PyInstaller = 'pyinstaller==6.22.3'

$desktop = Split-Path -Parent $PSScriptRoot
$repo = Split-Path -Parent $desktop
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

$pyproject = Join-Path $repo 'pyproject.toml'
$requirements = & $python -c @"
import sys, tomllib
project = tomllib.load(open(sys.argv[1], 'rb'))['project']
extras = project['optional-dependencies']
print('\n'.join(project['dependencies'] + extras['reader'] + extras['mcp']))
"@ $pyproject
if ($LASTEXITCODE -ne 0) { throw 'Reading the dependencies from pyproject.toml failed.' }

Invoke-Checked 'Installing the core dependencies' {
  & $python -m pip install --disable-pip-version-check --quiet $PyInstaller @($requirements -split "`r?`n" | Where-Object { $_ })
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
# The MCP server imports the MCP SDK at start and exits cleanly when stdin
# closes, so an empty stdin proves the SDK was bundled.
Invoke-Checked 'kos-core -m knowledge_os mcp' { $null | & $core -m knowledge_os mcp | Out-Null }

$size = (Get-ChildItem -LiteralPath (Split-Path -Parent $core) -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Built {0} ({1:N1} MB)" -f $core, ($size / 1MB))
