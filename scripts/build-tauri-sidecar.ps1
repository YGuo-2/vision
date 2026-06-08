[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ResourceDir = Join-Path $RepoRoot "frontend\src-tauri\resources"
$SidecarExe = Join-Path $RepoRoot "dist\vision-ui-backend.exe"
$ResourceExe = Join-Path $ResourceDir "vision-ui-backend.exe"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

New-Item -ItemType Directory -Force -Path $ResourceDir | Out-Null

Write-Host "Building Python bridge sidecar..." -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    & $PythonExe -m PyInstaller ui_backend_sidecar.spec --noconfirm --clean
}
finally {
    Pop-Location
}

if (-not (Test-Path $SidecarExe)) {
    throw "PyInstaller did not create $SidecarExe"
}

Copy-Item -LiteralPath $SidecarExe -Destination $ResourceExe -Force
Write-Host "Copied sidecar to $ResourceExe" -ForegroundColor Green
