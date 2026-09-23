@echo off
setlocal
rem Forwards every argument to the bundled frozen core (resources\core\kos-core.exe),
rem which runs the reader server as "kos-core.exe -m knowledge_os.reader ARGS".
rem %* preserves quoting, so arguments containing spaces or quotes pass
rem through unchanged, and %~dp0 handles an install path that itself
rem contains spaces.
set "KOS_CORE_EXE=%~dp0..\resources\core\kos-core.exe"
if not exist "%KOS_CORE_EXE%" (
  echo kos-read: could not find "%KOS_CORE_EXE%" 1>&2
  exit /b 1
)
"%KOS_CORE_EXE%" -m knowledge_os.reader %*
exit /b %ERRORLEVEL%
