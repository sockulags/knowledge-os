# Adds or removes one folder from the current user's PATH (HKCU\Environment),
# called by the NSIS installer/uninstaller (installer.nsh) with -Action Add or
# -Action Remove and -Dir the folder to add or remove.
#
# The registry value is read and written through .NET's Registry API rather
# than through NSIS string variables, so there is no NSIS string-length limit
# to worry about (NSIS's default build caps strings at 1024 characters, which
# a long PATH can exceed) and no risk of truncating the rest of the user's
# PATH. The value's REG_EXPAND_SZ/REG_SZ kind is preserved. Matching is
# case-insensitive and ignores a trailing backslash, so the entry is not
# duplicated on reinstall/upgrade and is removed cleanly on uninstall. Other
# entries are left in their original order and are never touched.

param(
  [Parameter(Mandatory = $true)][ValidateSet('Add', 'Remove')][string]$Action,
  [Parameter(Mandatory = $true)][string]$Dir
)

$ErrorActionPreference = 'Stop'

function Get-UserPathState {
  $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $false)
  try {
    try {
      $kind = $key.GetValueKind('Path')
    } catch {
      $kind = [Microsoft.Win32.RegistryValueKind]::ExpandString
    }
    $value = $key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
  } finally {
    $key.Close()
  }
  if ($null -eq $value) { $value = '' }
  return [PSCustomObject]@{ Value = [string]$value; Kind = $kind }
}

function Set-UserPathValue([string]$Value, $Kind) {
  if ($null -eq $Kind -or $Kind -eq [Microsoft.Win32.RegistryValueKind]::None) {
    $Kind = [Microsoft.Win32.RegistryValueKind]::ExpandString
  }
  $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
  try {
    $key.SetValue('Path', $Value, $Kind)
  } finally {
    $key.Close()
  }
}

function Send-EnvironmentChangeBroadcast {
  Add-Type -Namespace KosPathTool -Name NativeMethods -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll", SetLastError = true, CharSet = System.Runtime.InteropServices.CharSet.Auto)]
public static extern System.IntPtr SendMessageTimeout(System.IntPtr hWnd, uint Msg, System.UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out System.UIntPtr lpdwResult);
'@ -ErrorAction SilentlyContinue

  $HWND_BROADCAST = [System.IntPtr]0xffff
  $WM_SETTINGCHANGE = 0x001A
  $SMTO_ABORTIFHUNG = 0x0002
  $result = [System.UIntPtr]::Zero
  [KosPathTool.NativeMethods]::SendMessageTimeout($HWND_BROADCAST, $WM_SETTINGCHANGE, [System.UIntPtr]::Zero, 'Environment', $SMTO_ABORTIFHUNG, 5000, [ref]$result) | Out-Null
}

function Test-SameEntry([string]$a, [string]$b) {
  return $a.TrimEnd('\') -ieq $b.TrimEnd('\')
}

$state = Get-UserPathState
$entries = @()
if ($state.Value.Length -gt 0) {
  $entries = @($state.Value -split ';' | Where-Object { $_.Length -gt 0 })
}

$target = $Dir.TrimEnd('\')
$alreadyPresent = [bool]($entries | Where-Object { Test-SameEntry $_ $target })

if ($Action -eq 'Add') {
  if ($alreadyPresent) {
    Write-Output "kos: $Dir is already on the user PATH."
    exit 0
  }
  $newEntries = $entries + $Dir
  Set-UserPathValue ($newEntries -join ';') $state.Kind
  Send-EnvironmentChangeBroadcast
  Write-Output "kos: added $Dir to the user PATH."
} else {
  if (-not $alreadyPresent) {
    Write-Output "kos: $Dir was not on the user PATH."
    exit 0
  }
  $newEntries = @($entries | Where-Object { -not (Test-SameEntry $_ $target) })
  Set-UserPathValue ($newEntries -join ';') $state.Kind
  Send-EnvironmentChangeBroadcast
  Write-Output "kos: removed $Dir from the user PATH."
}
