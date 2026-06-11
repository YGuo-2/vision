param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"

if (Test-Path $cargoBin) {
    $env:Path = "$cargoBin;$env:Path"
}

Set-Location $repoRoot

if ($DryRun) {
    Write-Host "Would run from $repoRoot"
    Write-Host "npm --prefix frontend run tauri dev"
    exit 0
}

Write-Host "Starting Vision Tauri desktop dev..."
npm --prefix frontend run tauri dev
exit $LASTEXITCODE
