# Build BMT5000.exe for production line (run from repo root or this folder).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Python = Join-Path $Root "venv\Scripts\python.exe"
$Pip = Join-Path $Root "venv\Scripts\pip.exe"
if (-not (Test-Path $Python)) {
    Write-Error "找不到 venv。請先在專案根目錄建立虛擬環境並安裝 requirements.txt。"
}

& $Pip install -q pyinstaller
& $Python -m PyInstaller packaging\bmt5000.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller 結束代碼 $LASTEXITCODE"
}

$Out = Join-Path $Root "dist\BMT5000.exe"
if (Test-Path $Out) {
    Write-Host ""
    Write-Host "完成: $Out"
    Write-Host "請將 dist\BMT5000.exe 複製給產線（可放桌面雙擊）。"
} else {
    Write-Error "打包失敗，未產生 BMT5000.exe"
}
