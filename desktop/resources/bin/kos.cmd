@echo off
setlocal
rem Forwards every argument to the bundled frozen core (resources\core\kos-core.exe),
rem which runs the CLI as "kos-core.exe -m knowledge_os ARGS". %* preserves
rem quoting, so arguments containing spaces or quotes pass through unchanged,
rem and %~dp0 handles an install path that itself contains spaces.
set "KOS_CORE_EXE=%~dp0..\resources\core\kos-core.exe"
if not exist "%KOS_CORE_EXE%" (
  echo kos: could not find "%KOS_CORE_EXE%" 1>&2
  exit /b 1
)
rem This shim's own full path, so the core can tell whether a bare "kos" on
rem PATH (as an agent config or another terminal would invoke it) actually
rem resolves back to this same file — see knowledge_os/version_info.py.
set "KOS_LAUNCHED_BY_SHIM=%~f0"
"%KOS_CORE_EXE%" -m knowledge_os %*
exit /b %ERRORLEVEL%
