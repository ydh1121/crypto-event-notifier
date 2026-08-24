$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "Crypto Auto Trader - secure phone access (Cloudflare Tunnel)"
Write-Host "No VPN app is required on the phone. The trader will listen only on 127.0.0.1."
Write-Host ""

function Resolve-Cloudflared {
  $command = Get-Command cloudflared -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $candidates = @(
    "C:\Program Files\cloudflared\cloudflared.exe",
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    (Join-Path $repo "b3_trader\data\tools\cloudflared.exe")
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) { return $candidate }
  }
  return $null
}

function Install-Cloudflared {
  $binary = Resolve-Cloudflared
  if ($binary) { return $binary }

  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    Write-Host "cloudflared is not installed. Trying winget..."
    & winget install --id Cloudflare.cloudflared --exact --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) {
      Start-Sleep -Seconds 2
      $binary = Resolve-Cloudflared
      if ($binary) { return $binary }
    }
  }

  Write-Host "Downloading the official Cloudflare Windows binary..."
  $toolDir = Join-Path $repo "b3_trader\data\tools"
  New-Item -ItemType Directory -Force -Path $toolDir | Out-Null
  $binary = Join-Path $toolDir "cloudflared.exe"
  Invoke-WebRequest -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" -OutFile $binary
  return $binary
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
  Write-Warning "Port 8765 is already in use. Stop the existing start-trader.bat window with Ctrl+C first, then run this script again."
  exit 2
}

$cloudflared = Install-Cloudflared
$dataDir = Join-Path $repo "b3_trader\data"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
$urlFile = Join-Path $dataDir "cloudflare-tunnel-url.txt"
$outLog = Join-Path $dataDir "cloudflare-tunnel-out.log"
$errLog = Join-Path $dataDir "cloudflare-tunnel-err.log"
Remove-Item $urlFile,$outLog,$errLog -Force -ErrorAction SilentlyContinue

# Override .env for this process tree only. This makes router port-forwarding ineffective
# because Uvicorn no longer listens on the LAN/WAN interfaces.
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
    if (-not $url) { throw "Could not find the trycloudflare.com URL in cloudflared output." }

    Set-Content -Path $urlFile -Value $url -Encoding UTF8
    Write-Host ""
    Write-Host "Secure phone URL: $url" -ForegroundColor Green
    Write-Host "Open this HTTPS address on the phone. No phone VPN is required."
    Write-Host "Enter the phone connection code when asked."
    Write-Host ""
    Write-Host "While this mode is running, the trader listens only on 127.0.0.1."
    Write-Host "Your old public-IP :8765 address should stop working after the previous trader process is fully stopped."
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
