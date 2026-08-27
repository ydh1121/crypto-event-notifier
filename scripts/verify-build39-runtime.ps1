param(
    [switch]$StatusOnly,
    [int]$Rows = 6
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python virtual environment not found: $python"
}

function Show-Time($value) {
    if (-not $value -or [double]$value -le 0) { return "-" }
    return [DateTimeOffset]::FromUnixTimeSeconds([long][double]$value).ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss")
}

function Show-ListingAudit {
    Write-Host "`n=== LISTING HISTORY AUDIT ==="
    & $python -X utf8 -m b3_trader.listing_history_audit --rows ([Math]::Max(1, [Math]::Min(20, $Rows)))
    if ($LASTEXITCODE -ne 0) { throw "Listing-history audit failed." }
}

if (-not $StatusOnly) {
    Write-Host "`n=== BUILD 39 CONTRACT ==="
    & $python -X utf8 .\scripts\check-listing-build39.py
    if ($LASTEXITCODE -ne 0) { throw "Build 39 contract failed." }

    # The identity bridge is a Pages Function, so deploy before the first live
    # listing-history cycle attempts to resolve a verified profile identity.
    Write-Host "`n=== CLOUDFLARE PAGES DEPLOY ==="
    & $python -X utf8 -m b3_trader.cloudflare_pages_deployer --force
    if ($LASTEXITCODE -ne 0) { throw "Cloudflare Pages deploy failed." }

    # Build 39 consumes normalized Build 38 notice timing. Refresh official
    # notices with the current parser/store first so historical zero-timing rows
    # can be hydrated and promotional listing-event false positives are not
    # allowed to seed new research cases.
    Write-Host "`n=== OFFICIAL NOTICE REFRESH ==="
    & $python -X utf8 -m b3_trader.market_notice_collector
    if ($LASTEXITCODE -ne 0) { throw "Official notice refresh failed for all sources." }

    Write-Host "`n=== LISTING HISTORY RESEARCH CYCLE ==="
    & $python -X utf8 -m b3_trader.listing_history_research_cycle
    if ($LASTEXITCODE -ne 0) { throw "Listing-history research cycle failed." }

    Show-ListingAudit

    Write-Host "`nPython supervisor/runtime files changed. Restart start-trader-secure.bat once, wait about 40 seconds, then run:"
    Write-Host ".\scripts\verify-build39-runtime.ps1 -StatusOnly"
    exit 0
}

Write-Host "`n=== RESEARCH PLATFORM / BUILD 39 ==="
$statusPath = Join-Path $root "b3_trader\data\research-platform\status.json"
if (-not (Test-Path $statusPath)) {
    throw "Research platform status file not found: $statusPath"
}
$status = Get-Content $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json

foreach ($name in @("listing-history-research", "market-notice-watch", "cloudflare-snapshot-publish", "cloudflare-market-detail-publish")) {
    $component = $status.components.$name
    if (-not $component) {
        Write-Host "$name : missing"
        continue
    }
    [PSCustomObject]@{
        component        = $name
        status           = $component.status
        interval_seconds = $component.interval_seconds
        last_success_at  = Show-Time $component.last_success_at
        last_error       = $component.last_error
        runs             = $component.runs
        result_status    = if ($component.last_result) { $component.last_result.status } else { '' }
        pending_cases    = if ($component.last_result) { $component.last_result.pending_cases } else { $null }
        processed        = if ($component.last_result) { $component.last_result.processed } else { $null }
        identity_waiting = if ($component.last_result) { $component.last_result.identity_waiting } else { $null }
        collected        = if ($component.last_result) { $component.last_result.collected } else { $null }
        source_errors    = if ($component.last_result) { $component.last_result.source_errors } else { $null }
    } | Format-List
}

Show-ListingAudit

Write-Host "`n=== PAPER SAFETY ==="
try {
    $demo = Invoke-RestMethod "http://127.0.0.1:8765/api/demo" -TimeoutSec 10
    [PSCustomObject]@{
        running     = $demo.running
        fresh       = $demo.fresh
        worker_mode = $demo.worker_mode
        paper_gate  = $demo.market_lifecycle.paper_gate
        error       = $demo.error
    } | Format-List
}
catch {
    Write-Host "LOCAL DEMO ERROR: $($_.Exception.Message)"
}

Write-Host "`n=== REMOTE VIEWER HEALTH ==="
try {
    $remote = Invoke-RestMethod `
        "https://crypto-paper-viewer-ydh1121-cf36.pages.dev/api/health" `
        -Headers @{"Cache-Control"="no-cache"} `
        -TimeoutSec 15
    [PSCustomObject]@{
        ok               = $remote.ok
        has_snapshot     = $remote.has_snapshot
        last_received_at = Show-Time $remote.last_received_at
        age_seconds      = $remote.age_seconds
        snapshot_count   = $remote.snapshot_count
    } | Format-List
}
catch {
    Write-Host "REMOTE HEALTH ERROR: $($_.Exception.Message)"
}
