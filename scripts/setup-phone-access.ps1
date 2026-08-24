$ErrorActionPreference = "Stop"

Write-Host "Crypto Auto Trader - secure phone access setup"
Write-Host "This uses Tailscale. It does NOT open or port-forward TCP 8765 to the public internet."
Write-Host ""

function Resolve-Tailscale {
  $command = Get-Command tailscale -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }
  $candidates = @(
    "C:\Program Files\Tailscale\tailscale.exe",
    "C:\Program Files (x86)\Tailscale\tailscale.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) { return $candidate }
  }
  return $null
}

function Test-IsAdmin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$tailscale = Resolve-Tailscale
if (-not $tailscale) {
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) {
    throw "Tailscale is not installed and winget is unavailable. Install Tailscale from tailscale.com, then run this script again."
  }
  Write-Host "Tailscale is not installed. Installing with winget..."
  & winget install --id Tailscale.Tailscale --exact --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw "Tailscale installation failed with exit code $LASTEXITCODE" }
  Start-Sleep -Seconds 3
  $tailscale = Resolve-Tailscale
}

if (-not $tailscale) { throw "Tailscale executable was not found after installation." }

Write-Host "Starting Tailscale sign-in. A browser window may open."
& $tailscale up
if ($LASTEXITCODE -ne 0) {
  Write-Warning "'tailscale up' did not finish successfully. Open the Tailscale app from the Start menu and sign in, then continue."
}

$tailIp = (& $tailscale ip -4 | Select-Object -First 1).Trim()
Write-Host ""
Write-Host "Current Tailscale IPv4: $tailIp"
if ($tailIp) {
  Write-Host "Direct dashboard URL: http://$tailIp`:8765"
}

$ruleName = "Crypto Auto Trader - Tailscale 8765"
if (Get-Command Get-NetFirewallRule -ErrorAction SilentlyContinue) {
  $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
  if (-not $rule) {
    if (Test-IsAdmin) {
      New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -RemoteAddress "100.64.0.0/10" -Profile Any | Out-Null
      Write-Host "Added a Windows Firewall rule limited to Tailscale addresses (100.64.0.0/10)."
    } else {
      Write-Warning "Windows Firewall rule was not added because PowerShell is not running as Administrator. If the 100.x address does not open on the phone, run this script once from an Administrator PowerShell."
    }
  }
}

Write-Host ""
Write-Host "Next:"
Write-Host "1. Install/open Tailscale on the phone and sign in to the SAME account/tailnet."
Write-Host "2. Make sure the Tailscale VPN switch on the phone is ON."
Write-Host "3. Use the direct 100.x address shown above, including :8765. Do not rely on the ts.net name first."
Write-Host "4. Enter the phone connection code shown in the local PC dashboard."
Write-Host ""
Write-Host "Do NOT use your public/WAN IP and do NOT configure router port-forwarding/DMZ/UPnP for port 8765."
