# Guarded end-to-end test of the installer, the `kos` PATH shim, and the
# uninstaller, run with `npm run test:installer` from desktop/. It always
# builds and exercises the TEST build variant (electron-builder.test.yml,
# see that file and desktop/README.md, "Testing the installer"), and refuses
# to run at all if anything about the test variant's identifiers would let it
# touch the real app's install folder, registry entry, or PATH entry.
#
# What it does, once the guard passes:
#   1. Builds the test variant (`npm run dist:test`).
#   2. Records the current user PATH exactly as stored in the registry.
#   3. Installs the test variant silently, kills the copy it auto-launches.
#   4. Runs `kos --help` through the test variant's shim, from a brand-new
#      process whose PATH is rebuilt from the registry (not inherited from
#      this session), the way a newly opened terminal would see it.
#   5. Uninstalls the test variant silently.
#   6. Verifies the user PATH is byte-identical to what was recorded in step
#      2. If it is not, the recorded value is restored immediately and the
#      script fails loudly instead of leaving PATH altered.
#
# The real app (installed to %LOCALAPPDATA%\Programs\knowledge-os-desktop,
# see desktop/README.md) is never installed, updated, or uninstalled by this
# script. If it happens to be installed, the script only reads its folder
# listing, version, and PATH entry, to report that they are unaffected.

$ErrorActionPreference = 'Stop'

$scripts = $PSScriptRoot
$desktop = Split-Path -Parent $scripts

# --- Identifiers, read from the two electron-builder configs so a real
# config change is caught automatically instead of drifting from a hardcoded
# copy here. ---
function Read-YamlScalar([string]$Path, [string]$Key) {
  $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^\s*${Key}:\s*(.+?)\s*$" } | Select-Object -First 1
  if ($null -eq $line) { return $null }
  if ($line -match "^\s*${Key}:\s*(.+?)\s*$") { return $Matches[1].Trim('"''') }
  return $null
}

$realYml = Join-Path $desktop 'electron-builder.yml'
$testYml = Join-Path $desktop 'electron-builder.test.yml'

$realAppId = Read-YamlScalar $realYml 'appId'
$realProductName = Read-YamlScalar $realYml 'productName'
# The real config has no extraMetadata.name override, so the real app name is
# the npm package name in package.json.
$packageJson = Get-Content -LiteralPath (Join-Path $desktop 'package.json') -Raw | ConvertFrom-Json
$realName = $packageJson.name

$testAppId = Read-YamlScalar $testYml 'appId'
$testProductName = Read-YamlScalar $testYml 'productName'
# extraMetadata.name, the only indented "name:" line in the file.
$testNameMatch = Select-String -Path $testYml -Pattern '^\s+name:\s*(.+)$' | Select-Object -Last 1
$testName = if ($testNameMatch) { $testNameMatch.Matches[0].Groups[1].Value.Trim('"''') } else { $null }

Write-Host "Real identifiers : name=$realName appId=$realAppId productName='$realProductName'"
Write-Host "Test identifiers : name=$testName appId=$testAppId productName='$testProductName'"

if (-not $realName -or -not $realAppId -or -not $realProductName -or -not $testName -or -not $testAppId -or -not $testProductName) {
  throw "Could not read all identifiers from electron-builder.yml / electron-builder.test.yml / package.json. Refusing to continue."
}

# --- The guard: refuse if the test variant's identifiers are not cleanly
# separate from the real ones. ---
$collisions = @()
if ($testName -ieq $realName) { $collisions += "extraMetadata.name ('$testName') equals the real app name" }
if ($testAppId -ieq $realAppId) { $collisions += "appId ('$testAppId') equals the real appId" }
if ($testProductName -ieq $realProductName) { $collisions += "productName ('$testProductName') equals the real productName" }

$realInstallDir = Join-Path $env:LOCALAPPDATA "Programs\$realName"
$testInstallDir = Join-Path $env:LOCALAPPDATA "Programs\$testName"
if ($testInstallDir -ieq $realInstallDir) { $collisions += "test install dir equals the real install dir ($realInstallDir)" }

$realBinDir = Join-Path $realInstallDir 'bin'
$testBinDir = Join-Path $testInstallDir 'bin'
if ($testBinDir -ieq $realBinDir) { $collisions += "test PATH entry equals the real PATH entry ($realBinDir)" }

if ($collisions.Count -gt 0) {
  Write-Error "Refusing to run: the test variant is not isolated from the real app:`n - $($collisions -join "`n - ")"
  exit 1
}

Write-Host "Guard passed: the test variant's install dir, PATH entry, appId and productName are all distinct from the real app's." -ForegroundColor Green

# --- Snapshot the real install (if present) so we can prove afterwards it
# was not touched. This script never installs, updates, or uninstalls it. ---
function Get-RealSnapshot {
  $exists = Test-Path -LiteralPath $realInstallDir
  $snapshot = [ordered]@{
    Exists  = $exists
    Files   = @()
    UserData = @()
  }
  if ($exists) {
    $snapshot.Files = @(Get-ChildItem -LiteralPath $realInstallDir -Recurse -File | ForEach-Object { $_.FullName.Substring($realInstallDir.Length) } | Sort-Object)
    $exe = Join-Path $realInstallDir 'knowledge-os.exe'
    if (Test-Path -LiteralPath $exe) { $snapshot.Version = (Get-Item -LiteralPath $exe).VersionInfo.FileVersion }
  }
  $realUserData = Join-Path $env:APPDATA $realName
  if (Test-Path -LiteralPath $realUserData) {
    $snapshot.UserData = @(Get-ChildItem -LiteralPath $realUserData -Recurse -File | ForEach-Object { $_.FullName.Substring($realUserData.Length) } | Sort-Object)
  }
  return $snapshot
}

$realBefore = Get-RealSnapshot
Write-Host "Real install present before: $($realBefore.Exists)$(if ($realBefore.Exists) { " (version $($realBefore.Version), $($realBefore.Files.Count) files, $($realBefore.UserData.Count) userData files)" })"

# --- Record the user PATH exactly as stored in the registry (not the
# process's possibly-stale env block), the same way manage-path.ps1 reads it. ---
function Get-UserPathRaw {
  $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $false)
  try {
    $kind = try { $key.GetValueKind('Path') } catch { [Microsoft.Win32.RegistryValueKind]::ExpandString }
    $value = $key.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
  } finally { $key.Close() }
  if ($null -eq $value) { $value = '' }
  return [PSCustomObject]@{ Value = [string]$value; Kind = $kind }
}

function Set-UserPathRaw($state) {
  $key = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true)
  try { $key.SetValue('Path', $state.Value, $state.Kind) } finally { $key.Close() }
}

$pathBefore = Get-UserPathRaw
Write-Host "Recorded user PATH ($($pathBefore.Value.Length) chars, kind=$($pathBefore.Kind))."

# --- 1. Build the test variant. ---
Write-Host "`n== Building the test variant (npm run dist:test) ==" -ForegroundColor Cyan
Push-Location $desktop
try {
  & npm run dist:test
  if ($LASTEXITCODE -ne 0) { throw "npm run dist:test failed (exit code $LASTEXITCODE)." }
} finally {
  Pop-Location
}

$installer = Join-Path $desktop 'dist-test\knowledge-os-test-setup.exe'
if (-not (Test-Path -LiteralPath $installer)) { throw "Expected installer not found: $installer" }

# app-update.yml must not exist / must not name the real repo's GitHub feed,
# since electron-builder.test.yml sets publish: null.
$appUpdateYml = Get-ChildItem -LiteralPath (Join-Path $desktop 'dist-test\win-unpacked\resources') -Filter 'app-update.yml' -ErrorAction SilentlyContinue
if ($appUpdateYml) { throw "Test build unexpectedly has an app-update.yml; publish: null should have removed the update feed." }
Write-Host "Confirmed: the test build has no app-update.yml (no update feed)." -ForegroundColor Green

# --- 2. Install silently. ---
Write-Host "`n== Installing the test variant silently ==" -ForegroundColor Cyan
Start-Process -FilePath $installer -ArgumentList '/S' -Wait
Start-Sleep -Seconds 2

if (-not (Test-Path -LiteralPath $testInstallDir)) { throw "Install did not create $testInstallDir" }
Write-Host "Installed to $testInstallDir" -ForegroundColor Green

# oneClick + runAfterFinish launches the app; stop it before continuing.
Get-Process -Name 'knowledge-os-test' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

# Sanity: the registry uninstall entry must be the test product, never the
# real one, before we go anywhere near uninstalling anything.
$uninstallKey = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
  ForEach-Object { Get-ItemProperty $_.PSPath } |
  Where-Object { $_.DisplayName -eq $testProductName }
if (-not $uninstallKey) { throw "No uninstall registry entry found for '$testProductName'." }
$realUninstallKey = Get-ChildItem 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall' -ErrorAction SilentlyContinue |
  ForEach-Object { Get-ItemProperty $_.PSPath } |
  Where-Object { $_.DisplayName -eq $realProductName }
Write-Host "Uninstall registry entry for '$testProductName' found; entry for '$realProductName' $(if ($realUninstallKey) { 'also exists (pre-existing real install)' } else { 'does not exist' })."

# --- 3. Run `kos --help` via the shim, from a new process with a freshly
# rebuilt PATH (as a newly opened terminal would see it), not this session's
# possibly-stale inherited PATH. ---
Write-Host "`n== Running 'kos --help' from a new process ==" -ForegroundColor Cyan
$machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$freshPath = "$machinePath;$userPath"
if ($freshPath -notmatch [regex]::Escape($testBinDir)) {
  throw "Freshly read PATH does not contain $testBinDir; the installer's PATH step did not take effect."
}

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = 'cmd.exe'
$psi.Arguments = '/c kos --help'
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.EnvironmentVariables['Path'] = $freshPath
$proc = [System.Diagnostics.Process]::Start($psi)
$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()

Write-Host "kos --help exit code: $($proc.ExitCode)"
if ($stdout) { Write-Host "--- stdout ---`n$stdout" }
if ($stderr) { Write-Host "--- stderr ---`n$stderr" }
if ($proc.ExitCode -ne 0) { throw "kos --help exited with code $($proc.ExitCode) via the test shim." }
Write-Host "'kos --help' ran successfully through the test variant's PATH shim." -ForegroundColor Green

# --- 4. Uninstall silently. ---
Write-Host "`n== Uninstalling the test variant silently ==" -ForegroundColor Cyan
$uninstallString = $uninstallKey.UninstallString
if (-not $uninstallString) { throw "Uninstall registry entry has no UninstallString." }
# UninstallString is like `"C:\...\Uninstall Knowledge OS Test.exe"`; run it silently.
$uninstallExe = ($uninstallString -replace '^"([^"]+)".*$', '$1')
if (-not (Test-Path -LiteralPath $uninstallExe)) { throw "Uninstaller not found at $uninstallExe" }
if ($uninstallExe -notlike "$testInstallDir*") { throw "Refusing to run uninstaller outside the test install dir: $uninstallExe" }

Start-Process -FilePath $uninstallExe -ArgumentList '/S' -Wait
Start-Sleep -Seconds 2
Get-Process -Name 'knowledge-os-test' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

$stillThere = Test-Path -LiteralPath $testInstallDir
if ($stillThere) {
  # NSIS leaves an empty dir with the uninstaller's own temp log briefly; give it a moment.
  Start-Sleep -Seconds 2
  $stillThere = (Test-Path -LiteralPath $testInstallDir) -and ((Get-ChildItem -LiteralPath $testInstallDir -Recurse -File -ErrorAction SilentlyContinue).Count -gt 0)
}
if ($stillThere) { Write-Warning "Test install dir still has files after uninstall: $testInstallDir" } else { Write-Host "Test install dir removed." -ForegroundColor Green }

# --- 5. Verify the user PATH is byte-identical to what was recorded before
# any of this ran. Restore immediately if not. ---
Write-Host "`n== Verifying the user PATH is unchanged from before the test ==" -ForegroundColor Cyan
$pathAfter = Get-UserPathRaw
if ($pathAfter.Value -ceq $pathBefore.Value -and $pathAfter.Kind -eq $pathBefore.Kind) {
  Write-Host "User PATH is byte-identical to the recorded value ($($pathBefore.Value.Length) chars)." -ForegroundColor Green
} else {
  Write-Warning "User PATH changed! Restoring the recorded value immediately."
  Set-UserPathRaw $pathBefore
  $restored = Get-UserPathRaw
  if ($restored.Value -ceq $pathBefore.Value) {
    Write-Host "PATH restored successfully." -ForegroundColor Yellow
  } else {
    Write-Error "PATH restore failed! Recorded value:`n$($pathBefore.Value)`nCurrent value:`n$($restored.Value)"
  }
  throw "The installer/uninstaller left the user PATH different from before the test (now restored). This must be investigated before trusting the installer."
}

# --- 6. Confirm the real install was never touched. ---
Write-Host "`n== Confirming the real app is unaffected ==" -ForegroundColor Cyan
$realAfter = Get-RealSnapshot
$realUnchanged = ($realBefore.Exists -eq $realAfter.Exists) -and
  (@($realBefore.Files) -join "`n") -ceq (@($realAfter.Files) -join "`n") -and
  (@($realBefore.UserData) -join "`n") -ceq (@($realAfter.UserData) -join "`n") -and
  ($realBefore.Version -eq $realAfter.Version)
if ($realUnchanged) {
  Write-Host "Real install unchanged (present before/after: $($realBefore.Exists)/$($realAfter.Exists))." -ForegroundColor Green
} else {
  Write-Error "Real install changed! Before: $($realBefore | ConvertTo-Json -Compress) After: $($realAfter | ConvertTo-Json -Compress)"
  throw "The real app's install folder or userData folder changed during this test run."
}

Write-Host "`nAll checks passed." -ForegroundColor Green
