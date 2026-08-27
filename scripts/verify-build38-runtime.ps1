param(
    [switch]$StatusOnly,
    [int]$Rows = 4
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

if (-not $StatusOnly) {
    Write-Host "`n=== BUILD 38 CONTRACT ==="
    & $python -X utf8 .\scripts\check-sector-build38.py
    if ($LASTEXITCODE -ne 0) { throw "Build 38 contract failed." }

    Write-Host "`n=== OFFICIAL NOTICE COLLECT ==="
    & $python -X utf8 -m b3_trader.market_notice_collector
    if ($LASTEXITCODE -ne 0) { throw "Official notice collector failed for all sources." }

    Write-Host "`n=== NOTICE AUDIT ==="
    & $python -X utf8 -m b3_trader.market_notice_audit --rows ([Math]::Max(0, [Math]::Min(20, $Rows)))
    if ($LASTEXITCODE -ne 0) { throw "Market notice audit failed." }

    Write-Host "`n=== CLOUDFLARE PAGES DEPLOY ==="
    & $python -X utf8 -m b3_trader.cloudflare_pages_deployer --force
    if ($LASTEXITCODE -ne 0) { throw "Cloudflare Pages deploy failed." }

    Write-Host "`nPython runtime/launcher files changed. Restart start-trader-secure.bat once, wait about 40 seconds, then run:"
    Write-Host ".\scripts\verify-build38-runtime.ps1 -StatusOnly"
    exit 0
}

Write-Host "`n=== RESEARCH PLATFORM STATUS ==="
$statusPath = Join-Path $root "b3_trader\data\research-platform\status.json"
if (-not (Test-Path $statusPath)) {
    throw "Research platform status file not found: $statusPath"
}
$status = Get-Content $statusPath -Raw -Encoding UTF8 | ConvertFrom-Json

foreach ($name in @("market-notice-watch", "cloudflare-snapshot-publish", "cloudflare-market-detail-publish")) {
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
    } | Format-List
}

Write-Host "`n=== PAPER RUNTIME SUPERVISOR ==="
$paperSupervisorPath = Join-Path $root "b3_trader\data\paper-runtime-supervisor.json"
if (Test-Path $paperSupervisorPath) {
    try {
        $paperSupervisor = Get-Content $paperSupervisorPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $pidAlive = $false
        if ($paperSupervisor.pid) {
            $pidAlive = $null -ne (Get-Process -Id ([int]$paperSupervisor.pid) -ErrorAction SilentlyContinue)
        }
        [PSCustomObject]@{
            running         = $paperSupervisor.running
            pid             = $paperSupervisor.pid
            pid_alive       = $pidAlive
            updated_at      = Show-Time $paperSupervisor.updated_at
            attempts        = $paperSupervisor.attempts
            restarts        = $paperSupervisor.restarts
            last_error      = $paperSupervisor.last_error
            can_real_orders = $paperSupervisor.can_place_real_orders
        } | Format-List
    }
    catch {
        Write-Host "PAPER SUPERVISOR STATUS ERROR: $($_.Exception.Message)"
    }
}
else {
    Write-Host "paper-runtime-supervisor.json : missing"
}

Write-Host "`n=== LOCAL PAPER LIFECYCLE ==="
try {
    $demo = Invoke-RestMethod "http://127.0.0.1:8765/api/demo" -TimeoutSec 10
    $lifecycle = $demo.market_lifecycle
    [PSCustomObject]@{
        running                = $demo.running
        fresh                  = $demo.fresh
        state                  = $demo.state
        worker_mode            = $demo.worker_mode
        pid                    = $demo.pid
        updated_at             = Show-Time $demo.updated_at
        last_scan_completed    = Show-Time $demo.last_scan_completed
        lifecycle_market_count = $lifecycle.market_count
        notice_state_count     = $lifecycle.notice_state_count
        entry_blocked_markets  = $lifecycle.entry_blocked_markets
        paper_gate             = $lifecycle.paper_gate
        error                  = $demo.error
    } | Format-List
}
catch {
    Write-Host "LOCAL DEMO ERROR: $($_.Exception.Message)"
}

Write-Host "`n=== LOCAL APP / ASSET REGISTRY ==="
try {
    $appState = Invoke-RestMethod "http://127.0.0.1:8765/api/state" -TimeoutSec 10
    $assetResponse = Invoke-RestMethod "http://127.0.0.1:8765/api/assets" -TimeoutSec 10
    # Invoke-RestMethod can preserve a top-level JSON array as one Object[] value.
    # Pipe once to force normal PowerShell enumeration before validating each market.
    $assets = @($assetResponse | ForEach-Object { $_ })
    $invalidMarkets = @(
        $assets |
            Where-Object { [string]$_.market -notmatch '^KRW-[A-Z0-9]+$' } |
            ForEach-Object { [string]$_.market }
    )
    $lastError = $appState.last_error
    [PSCustomObject]@{
        active_assets        = $assets.Count
        invalid_asset_count = $invalidMarkets.Count
        invalid_assets      = if ($invalidMarkets.Count) { $invalidMarkets -join ', ' } else { '' }
        last_error_scope     = if ($lastError) { $lastError.scope } else { '' }
        last_error_type      = if ($lastError) { $lastError.type } else { '' }
        last_error_message   = if ($lastError) { $lastError.message } else { '' }
    } | Format-List
}
catch {
    Write-Host "LOCAL APP STATUS ERROR: $($_.Exception.Message)"
}

Write-Host "`n=== REMOTE VIEWER HEALTH ==="
try {
    $remote = Invoke-RestMethod `
        "https://crypto-paper-viewer-ydh1121-cf36.pages.dev/api/health" `
        -Headers @{"Cache-Control"="no-cache"} `
        -TimeoutSec 15
    [PSCustomObject]@{
        ok                 = $remote.ok
        has_snapshot       = $remote.has_snapshot
        last_received_at   = Show-Time $remote.last_received_at
        age_seconds        = $remote.age_seconds
        snapshot_count     = $remote.snapshot_count
        oldest_received_at = Show-Time $remote.oldest_received_at
    } | Format-List
}
catch {
    Write-Host "REMOTE HEALTH ERROR: $($_.Exception.Message)"
}
