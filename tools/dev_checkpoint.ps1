param(
    [string]$Message = "checkpoint: backup after two software fixes"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath ".git")) {
    git init
}

$counterPath = ".dev_checkpoint_count"
$count = 0
if (Test-Path -LiteralPath $counterPath) {
    $raw = Get-Content -LiteralPath $counterPath -Raw
    [int]::TryParse($raw.Trim(), [ref]$count) | Out-Null
}

$count += 1
Set-Content -LiteralPath $counterPath -Value $count -Encoding UTF8

Write-Host "Checkpoint count: $count"

if (($count % 2) -ne 0) {
    Write-Host "This is the first software fix in the pair. No Git backup commit is created yet."
    exit 0
}

$status = git status --porcelain
if ([string]::IsNullOrWhiteSpace($status)) {
    Write-Host "No program changes found. Git backup commit skipped."
    exit 0
}

git add README.md pyproject.toml .gitignore src tests tools
git commit -m $Message
Write-Host "Git backup commit created."
