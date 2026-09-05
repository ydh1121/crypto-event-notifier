$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$branch = "b3-auto-trader-phase1"
Set-Location $repo

Write-Host "Crypto Auto Trader - local Git sync repair"
Write-Host "This preserves control state and generated PAPER runtime files, then realigns code to origin/$branch."

if (-not (Test-Path ".git")) { throw "This folder is not a Git clone." }

$controlFiles = @("control/assets.json", "control/runtime.json")
$selfPath = "scripts/repair-local-sync.ps1"
$safeDirtyExact = @(
  $controlFiles +
  $selfPath +
  "dashboard/runtime-demo.json" +
  "dashboard/runtime-demo.tmp" +
  "dashboard/runtime-demo.json.tmp" +
  "dashboard/runtime-demo-upbit.json" +
  "dashboard/runtime-demo-upbit.tmp" +
  "dashboard/runtime-demo-upbit.json.tmp" +
  "dashboard/runtime-build.json" +
  "dashboard/runtime-build.json.tmp"
)
$safeDirtyPrefixes = @(
  "dashboard/demo-runtime/",
  "dashboard/demo-runtime-upbit/",
  "b3_trader/data/"
)

function Test-SafeDirtyPath([string]$Path) {
  if ($Path -in $safeDirtyExact) { return $true }
  if ($Path -like "dashboard/runtime-demo*.tmp") { return $true }
  foreach ($prefix in $safeDirtyPrefixes) {
    if ($Path.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
  }
  return $false
}

# The recovery command may check out the newest copy of this script before
# running it. Generated PAPER runtime files are also expected to change while
# the 24/7 server is running. Treat only those known runtime/control paths as
# safe; every other local code change still blocks the reset.
$dirtyLines = @(& git status --porcelain) | Where-Object { $_ }
$dirtyPaths = @($dirtyLines | ForEach-Object {
  if ($_.Length -ge 4) { $_.Substring(3).Trim() }
}) | Where-Object { $_ }
$unsafeDirty = @($dirtyPaths | Where-Object { -not (Test-SafeDirtyPath $_) })
if ($unsafeDirty.Count -gt 0) {
  Write-Host "Repair stopped because non-runtime local changes exist:" -ForegroundColor Yellow
  $unsafeDirty | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" }
  Write-Host "No reset was performed. Ask GPT to review these files before continuing."
  exit 2
}

$temp = Join-Path $env:TEMP ("crypto-trader-control-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp | Out-Null
foreach ($relative in $controlFiles) {
  if (Test-Path $relative) {
    $dest = Join-Path $temp ([IO.Path]::GetFileName($relative))
    Copy-Item $relative $dest -Force
  }
}

try {
  & git fetch origin $branch
  if ($LASTEXITCODE -ne 0) { throw "GitHub fetch failed." }

  $remote = "origin/$branch"
  $base = (& git merge-base HEAD $remote).Trim()
  if (-not $base) { throw "Could not find a common Git ancestor." }
  $localOnly = @(& git diff --name-only "$base..HEAD") | Where-Object { $_ }
  $unsafe = @($localOnly | Where-Object { $_ -notin $controlFiles })
  if ($unsafe.Count -gt 0) {
    Write-Host "Repair stopped because local-only code/files exist:" -ForegroundColor Yellow
    $unsafe | ForEach-Object { Write-Host "  $_" }
    Write-Host "No reset was performed. Ask GPT to review these files before continuing."
    exit 2
  }

  $before = (& git rev-parse --short HEAD).Trim()
  $remoteShort = (& git rev-parse --short $remote).Trim()
  Write-Host "Updating local code: $before -> $remoteShort"

  & git reset --hard $remote
  if ($LASTEXITCODE -ne 0) { throw "Git reset failed." }

  foreach ($relative in $controlFiles) {
    $source = Join-Path $temp ([IO.Path]::GetFileName($relative))
    if (Test-Path $source) {
      $parent = Split-Path -Parent $relative
      if ($parent -and -not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent | Out-Null }
      Copy-Item $source $relative -Force
    }
  }
} finally {
  Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}

$after = (& git rev-parse --short HEAD).Trim()
Write-Host "Repair complete. Local code now matches origin/$branch at $after." -ForegroundColor Green
Write-Host "Your local .env, dashboard token, Telegram settings, SQLite data, Bithumb/Upbit PAPER runtime, holdings, averaging plans, and backups were not deleted."
if (Test-Path "dashboard/navigation-v3.js") {
  Write-Host "Dashboard navigation v3 files are present."
} else {
  Write-Warning "dashboard/navigation-v3.js is missing after repair."
}
Write-Host "Next: .\start-trader-secure.bat"
& git status --short
