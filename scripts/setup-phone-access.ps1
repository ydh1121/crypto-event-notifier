$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "Crypto Auto Trader - phone access setup"
Write-Host "Primary method: Cloudflare HTTPS tunnel. No VPN app is required on the phone."
Write-Host ""

# Remove the old Tailscale-only firewall rule if it exists. This is safe even if
# Tailscale has already been uninstalled.
$oldRuleName = "Crypto Auto Trader - Tailscale 8765"
if (Get-Command Get-NetFirewallRule -ErrorAction SilentlyContinue) {
  $oldRule = Get-NetFirewallRule -DisplayName $oldRuleName -ErrorAction SilentlyContinue
  if ($oldRule) {
    try {
      Remove-NetFirewallRule -DisplayName $oldRuleName -ErrorAction Stop
      Write-Host "Removed the old Tailscale-only firewall rule."
    } catch {
      Write-Warning "The old Tailscale firewall rule still exists. Run this script once as Administrator if you want to remove it."
    }
  }
}

Write-Host ""
Write-Host "Use this launcher from now on:"
Write-Host "  .\start-trader-secure.bat"
Write-Host ""
Write-Host "It will:"
Write-Host "1. bind the local dashboard only to 127.0.0.1:8765"
Write-Host "2. install/find cloudflared on the PC if needed"
Write-Host "3. create a temporary HTTPS trycloudflare.com address"
Write-Host "4. keep the phone connection code as the remote dashboard password"
Write-Host ""
Write-Host "Do not use the public/WAN IP on port 8765 and do not configure router port-forwarding, DMZ, or UPnP for this app."
Write-Host "Tailscale is no longer required for the approved phone-access path."
