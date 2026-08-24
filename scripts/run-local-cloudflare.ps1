$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "Crypto Auto Trader - secure phone access (Cloudflare Tunnel)"
Write-Host "No VPN app is required on the phone. The trader will listen only on 127.0.0.1."
Write-Host ""

function Resolve-Cloudflared {
  $command = Get-Command cloudflared.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($command -and $command.Source) { return [string]$command.Source }

  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\cloudflared.exe"),
    "C:\Program Files\cloudflared\cloudflared.exe",
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    (Join-Path $repo "b3_trader\data\tools\cloudflared.exe")
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) { return [string]$candidate }
  }
  return $null
}

function Install-Cloudflared {
  $binary = Resolve-Cloudflared
  if ($binary) { return [string]$binary }

  $winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($winget -and $winget.Source) {
    Write-Host "cloudflared is not installed. Trying winget..."
    $wingetArgs = @(
      "install",
      "--id", "Cloudflare.cloudflared",
      "--exact",
      "--accept-package-agreements",
      "--accept-source-agreements"
    )
    # Start-Process avoids Windows PowerShell 5.1 turning native stderr/status text
    # into pipeline ErrorRecords and also guarantees this function returns only a path.
    $install = Start-Process -FilePath ([string]$winget.Source) -ArgumentList $wingetArgs -Wait -PassThru
    if ($install.ExitCode -eq 0) {
      Start-Sleep -Seconds 2
      $binary = Resolve-Cloudflared
      if ($binary) { return [string]$binary }
    } else {
      Write-Warning "winget cloudflared install returned exit code $($install.ExitCode). Falling back to the official binary download."
    }
  }

  Write-Host "Downloading the official Cloudflare Windows binary..."
  $toolDir = Join-Path $repo "b3_trader\data\tools"
  New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
  $binary = Join-Path $toolDir "cloudflared.exe"
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $binary
  if (-not (Test-Path $binary)) { throw "cloudflared download did not create the expected executable." }
  return [string]$binary
}

function Test-PortInUse {
  param([int]$Port)
  try {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    return $null -ne $listener
  } catch {
    return $false
  }
}

if (Test-PortInUse -Port 8765) {
  Write-Host ""
  Write-Warning "Port 8765 is already in use. Stop the existing trader window with Ctrl+C first, then run start-trader-secure.bat again."
  exit 2
}

# Force a scalar string even if an older PowerShell/native command unexpectedly emits extra output.
$cloudflared = [string](@(Install-Cloudflared) | Select-Object -Last 1)
if (-not $cloudflared -or -not (Test-Path $cloudflared)) {
  throw "cloudflared executable could not be resolved. Resolved value: '$cloudflared'"
}
Write-Host "Using cloudflared: $cloudflared"

$dataDir = Join-Path $repo "b3_trader\data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$urlFile = Join-Path $dataDir "cloudflare-tunnel-url.txt"
$outLog = Join-Path $dataDir "cloudflare-tunnel-out.log"
$errLog = Join-Path $dataDir "cloudflare-tunnel-err.log"
Remove-Item $urlFile,$outLog,$errLog -Force -ErrorAction SilentlyContinue

# Override .env for this process tree only. This makes router port-forwarding ineffective
# because Uvicorn no longer listens on LAN/WAN interfaces.
$env:DASHBOARD_HOST = "127.0.0.1"

$traderArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $repo "scripts\run-local.ps1")
)
$trader = Start-Process -FilePath "powershell.exe" -ArgumentList $traderArgs -PassThru

try {
  Write-Host "Waiting for the local dashboard..."
  $healthy = $false
  for ($i = 0; $i -lt 60; $i++) {
    if ($trader.HasExited) { throw "Trader exited before the dashboard became ready." }
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 2
      if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
  }
  if (-not $healthy) { throw "Dashboard did not become ready on 127.0.0.1:8765." }

  $tunnelArgs = @("tunnel", "--url", "http://127.0.0.1:8765", "--no-autoupdate")
  $tunnel = Start-Process -FilePath $cloudflared -ArgumentList $tunnelArgs -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
  try {
    $url = $null
    for ($i = 0; $i -lt 45; $i++) {
      if ($tunnel.HasExited) {
        $detail = ((Get-Content $errLog -Raw -ErrorAction SilentlyContinue) + "`n" + (Get-Content $outLog -Raw -ErrorAction SilentlyContinue)).Trim()
        throw "Cloudflare Tunnel exited early. $detail"
      }
      $combined = ((Get-Content $errLog -Raw -ErrorAction SilentlyContinue) + "`n" + (Get-Content $outLog -Raw -ErrorAction SilentlyContinue))
      $match = [regex]::Match($combined, 'https://[a-zA-Z0-9-]+\.trycloudflare\.com')
      if ($match.Success) { $url = $match.Value; break }
      Start-Sleep -Seconds 1
    }
    if (-not $url) { throw "Could not find the trycloudflare.com URL in cloudflared output. Check $errLog" }

    Set-Content -Path $urlFile -Value $url -Encoding UTF8
    Write-Host ""
    Write-Host "Secure phone URL: $url" -ForegroundColor Green
    Write-Host "Open this HTTPS address on the phone. No phone VPN is required."
    Write-Host "Enter the phone connection code when asked."
    Write-Host ""
    Write-Host "While this mode is running, the trader listens only on 127.0.0.1."
    Write-Host "Your old public-IP :8765 address should not reach this process."
    Write-Host "Quick Tunnel URLs change when this script is restarted."
    Write-Host "Press Ctrl+C here to stop both the trader and tunnel."

    while (-not $trader.HasExited -and -not $tunnel.HasExited) {
      Start-Sleep -Seconds 2
      $trader.Refresh(); $tunnel.Refresh()
    }
    if ($tunnel.HasExited -and -not $trader.HasExited) {
      throw "Cloudflare Tunnel stopped unexpectedly. Check $errLog"
    }
  } finally {
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item $urlFile -Force -ErrorAction SilentlyContinue
  }
} finally {
  if ($trader -and -not $trader.HasExited) { Stop-Process -Id $trader.Id -Force -ErrorAction SilentlyContinue }
}
