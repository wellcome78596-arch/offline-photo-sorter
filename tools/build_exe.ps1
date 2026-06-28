$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$entryPoint = Join-Path $projectRoot "src\photo_sorter\__main__.py"
$srcPath = Join-Path $projectRoot "src"

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Cannot find .venv. Please create the virtual environment first."
    Write-Host "Example: python -m venv .venv"
    exit 1
}

Set-Location -LiteralPath $projectRoot

& $venvPython -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller is not installed in .venv."
    Write-Host "Install it first:"
    Write-Host ".\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt"
    exit 1
}

$env:PYTHONPATH = $srcPath

& $venvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name OfflinePhotoSorter `
    --paths $srcPath `
    $entryPoint

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed."
    exit $LASTEXITCODE
}

$exePath = Join-Path $projectRoot "dist\OfflinePhotoSorter.exe"
if (Test-Path -LiteralPath $exePath) {
    Write-Host "Build complete:"
    Write-Host $exePath
} else {
    Write-Host "Build finished, but the expected exe was not found:"
    Write-Host $exePath
    exit 1
}

