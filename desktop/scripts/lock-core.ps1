# Regenerates desktop\core\requirements-core.txt, the hash-locked list of
# everything build-core.ps1 installs into the core's build venv: the
# dependencies in pyproject.toml with the reader, mcp, and search extras, and
# the build tools in core\build-requirements.in. Resolved for 64-bit Windows
# and Python 3.11, the platform the frozen core is built for. Run it after
# changing either input, or to take newer versions, and commit the result.
#
# Needs uv (https://docs.astral.sh/uv/) on PATH. Extra arguments go to
# `uv pip compile`, for example --upgrade-package starlette.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

Push-Location $repo
try {
  # Relative paths keep the "# via" comments in the lock file free of local paths.
  & uv pip compile pyproject.toml desktop/core/build-requirements.in `
    --extra reader --extra mcp --extra search `
    --python-version 3.11 --python-platform x86_64-pc-windows-msvc `
    --generate-hashes --annotation-style line `
    --custom-compile-command 'desktop\scripts\lock-core.ps1' `
    --output-file desktop/core/requirements-core.txt @args
  if ($LASTEXITCODE -ne 0) { throw "uv pip compile failed (exit code $LASTEXITCODE)." }
} finally {
  Pop-Location
}
