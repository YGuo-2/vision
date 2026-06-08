[CmdletBinding()]
param(
    [switch]$FullTests
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$FrontendRoot = Join-Path $RepoRoot "frontend"
$TauriRoot = Join-Path $FrontendRoot "src-tauri"
$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path $CargoBin) {
    $env:Path = "$CargoBin;$env:Path"
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Action
}

$DesktopTests = @(
    "tests/test_ui_backend_contract.py",
    "tests/test_ui_backend_jobs.py",
    "tests/test_ui_backend_sessions.py",
    "tests/test_ui_backend_analysis.py",
    "tests/test_ui_backend_models.py",
    "tests/test_camera_enum.py",
    "tests/test_input_source_state.py",
    "tests/test_app_controls.py",
    "tests/test_ui_controls.py",
    "tests/test_pose33_v3_golden.py",
    "tests/test_template_metadata.py",
    "tests/test_tech_eval_contract.py",
    "tests/test_valid_mask_migration.py"
)

Invoke-Step "Frontend build" {
    npm --prefix $FrontendRoot run build
}

Invoke-Step "Tauri cargo check" {
    Push-Location $TauriRoot
    try {
        cargo check
    }
    finally {
        Pop-Location
    }
}

Invoke-Step "Python compile smoke" {
    & $PythonExe -m py_compile `
        (Join-Path $RepoRoot "apps\app_ui.py") `
        (Join-Path $RepoRoot "apps\ui_backend.py") `
        (Join-Path $RepoRoot "core\vision_pipeline.py")
}

Invoke-Step "Python desktop regression tests" {
    if ($FullTests) {
        & $PythonExe -m pytest (Join-Path $RepoRoot "tests") -q
    }
    else {
        $ResolvedTests = $DesktopTests | ForEach-Object { Join-Path $RepoRoot $_ }
        & $PythonExe -m pytest @ResolvedTests -q
    }
}

Write-Host ""
Write-Host "Desktop stack verification passed." -ForegroundColor Green
