# Build LCRMeter.exe for standalone E4980A control (run from repo root or this folder).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
$Pip = Join-Path $Root "venv\Scripts\pip.exe"
if (-not (Test-Path $Python)) {
    Write-Error "venv not found. Create venv and install requirements.txt first."
}

& $Pip install -q -r requirements-build.txt
& $Python -m PyInstaller packaging\lcr_meter.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller exit code $LASTEXITCODE"
}

$Out = Join-Path $Root "dist\LCRMeter.exe"
if (Test-Path $Out) {
    Write-Host ""
    Write-Host "Done: $Out"
    Write-Host "Copy dist\LCRMeter.exe and double-click to run."
    Write-Host "Target PC needs NI-VISA installed. First launch may be slow (one-file extract)."
} else {
    Write-Error "Build failed: LCRMeter.exe was not created."
}
