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

Write-Host ""
Write-Host "Current Tailscale IPv4:"
& $tailscale ip -4
Write-Host ""
Write-Host "Next:"
Write-Host "1. Install Tailscale on the phone and sign in to the same tailnet."
Write-Host "2. Open the Crypto Auto Trader dashboard on this PC."
Write-Host "3. In Settings > Phone access, copy the Tailscale URL."
Write-Host "4. On the phone, enter the Dashboard token shown by the local PC console."
Write-Host ""
Write-Host "Do not configure public router port-forwarding for port 8765."
