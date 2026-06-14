[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ResourceDir = Join-Path $RepoRoot "frontend\src-tauri\resources"
$SidecarDir = Join-Path $RepoRoot "dist\vision-ui-backend"
$SidecarExe = Join-Path $SidecarDir "vision-ui-backend.exe"
$LegacySidecarExe = Join-Path $RepoRoot "dist\vision-ui-backend.exe"
$ResourceSidecarDir = Join-Path $ResourceDir "vision-ui-backend"
$ResourceLegacyExe = Join-Path $ResourceDir "vision-ui-backend.exe"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

New-Item -ItemType Directory -Force -Path $ResourceDir | Out-Null
if (Test-Path $SidecarDir) {
    Remove-Item -LiteralPath $SidecarDir -Recurse -Force
}
if (Test-Path $LegacySidecarExe) {
    Remove-Item -LiteralPath $LegacySidecarExe -Force
}
if (Test-Path $ResourceSidecarDir) {
    Remove-Item -LiteralPath $ResourceSidecarDir -Recurse -Force
}
if (Test-Path $ResourceLegacyExe) {
    Remove-Item -LiteralPath $ResourceLegacyExe -Force
}

Write-Host "Building Python bridge sidecar..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & $PythonExe -m PyInstaller ui_backend_sidecar.spec --noconfirm --clean
    $PyInstallerExitCode = $LASTEXITCODE
    if ($null -ne $PyInstallerExitCode -and $PyInstallerExitCode -ne 0) {
        throw "PyInstaller failed with exit code $PyInstallerExitCode"
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $SidecarExe)) {
    throw "PyInstaller did not create onedir sidecar executable $SidecarExe"
}

Copy-Item -LiteralPath $SidecarDir -Destination $ResourceSidecarDir -Recurse -Force
Write-Host "Copied onedir sidecar to $ResourceSidecarDir" -ForegroundColor Green
