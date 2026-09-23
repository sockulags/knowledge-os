; Custom NSIS include for the per-user installer (see desktop/electron-builder.yml,
; nsis.include). Adds "$INSTDIR\bin" (the kos.cmd shim, see
; desktop/resources/bin/kos.cmd) to the current user's PATH on install, and
; removes exactly that entry on uninstall.
;
; The PATH itself is never read into an NSIS string variable: NSIS's default
; build limits strings to 1024 characters, which a real-world PATH can
; exceed, and a naive ReadRegStr/WriteRegStr round-trip through such a
; variable would silently truncate the rest of the user's PATH. Instead this
; hands the job to build/manage-path.ps1, which reads and writes the
; HKCU\Environment\Path registry value directly through .NET's Registry API
; (no NSIS-imposed length limit) and broadcasts WM_SETTINGCHANGE so newly
; opened terminals pick up the change without a reboot. manage-path.ps1 also
; skips adding a duplicate entry on reinstall/upgrade and only ever touches
; the one entry it owns.

; ${__FILEDIR__} is not used here: electron-builder !includes this file from
; its own NSIS templates, so at expansion time it resolves to the template's
; directory, not this file's. BUILD_RESOURCES_DIR is electron-builder's own
; build-time define for this project's build/ directory (visible as
; "Command line defined: BUILD_RESOURCES_DIR=..." in makensis output) and
; points at the right place in both the installer and the uninstaller.

!macro customInstall
  SetOutPath "$PLUGINSDIR"
  File "${BUILD_RESOURCES_DIR}\manage-path.ps1"
  DetailPrint "Adding $INSTDIR\bin to your PATH"
  nsExec::ExecToLog '"powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\manage-path.ps1" -Action Add -Dir "$INSTDIR\bin"'
  Pop $0
!macroend

!macro customUnInstall
  SetOutPath "$PLUGINSDIR"
  File "${BUILD_RESOURCES_DIR}\manage-path.ps1"
  DetailPrint "Removing $INSTDIR\bin from your PATH"
  nsExec::ExecToLog '"powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\manage-path.ps1" -Action Remove -Dir "$INSTDIR\bin"'
  Pop $0
!macroend
