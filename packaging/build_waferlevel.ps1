# Build WaferLevel.exe for the full wafer-level GUI (run from repo root or this folder).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
$Pip = Join-Path $Root "venv\Scripts\pip.exe"
if (-not (Test-Path $Python)) {
    Write-Error "venv not found. Create venv and install requirements.txt first."
}

& $Pip install -q -r requirements-build.txt
& $Python -m PyInstaller packaging\waferlevel.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller exit code $LASTEXITCODE"
}

$Dist = Join-Path $Root "dist"
$Out = Join-Path $Dist "WaferLevel.exe"
if (-not (Test-Path $Out)) {
    Write-Error "Build failed: WaferLevel.exe was not created."
}

Copy-Item (Join-Path $Root "prober_tcp_settings.json") (Join-Path $Dist "prober_tcp_settings.json") -Force
Copy-Item (Join-Path $Root "instruments\panels\dsa\Settings_DSA.toml") (Join-Path $Dist "Settings_DSA.toml") -Force

Write-Host ""
Write-Host "Done: $Out"
Write-Host "Copy dist\WaferLevel.exe together with:"
Write-Host "  dist\prober_tcp_settings.json"
Write-Host "  dist\Settings_DSA.toml"
Write-Host "First launch may be slow (one-file extract). Install NI-VISA / NI-DAQmx / libusb on the target PC."
