param(
  [string]$Hostname = "",
  [string]$TunnelName = "crypto-auto-trader"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

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

$cloudflared = Resolve-Cloudflared
if (-not $cloudflared) {
  throw "cloudflared가 없습니다. 먼저 .\start-trader-secure.bat 을 한 번 실행해 cloudflared를 설치하세요."
}

$dataDir = Join-Path $repo "b3_trader\data"
$tunnelDir = Join-Path $dataDir "cloudflare"
New-Item -ItemType Directory -Force -Path $tunnelDir | Out-Null
$stateFile = Join-Path $dataDir "cloudflare-stable.json"
$configFile = Join-Path $tunnelDir "config.yml"

Write-Host "Crypto Auto Trader - Cloudflare 고정 주소 설정" -ForegroundColor Cyan
Write-Host ""
Write-Host "이 설정은 한 번만 하면 됩니다."
Write-Host "Cloudflare에서 관리 중인 도메인의 하위 주소가 필요합니다."
Write-Host "예: trader.example.com"
Write-Host ""

if (Test-Path $stateFile) {
  try {
    $existing = Get-Content $stateFile -Raw | ConvertFrom-Json
    if ($existing.hostname -and $existing.tunnel_id -and (Test-Path $configFile)) {
      Write-Host "이미 고정 주소가 설정되어 있습니다:" -ForegroundColor Green
      Write-Host "https://$($existing.hostname)"
      Write-Host ""
      Write-Host "변경하려면 b3_trader\data\cloudflare-stable.json 과 b3_trader\data\cloudflare\config.yml 을 삭제한 뒤 다시 실행하세요."
      exit 0
    }
  } catch {}
}

if (-not $Hostname) {
  $Hostname = (Read-Host "사용할 고정 주소를 입력하세요").Trim().ToLowerInvariant()
}
if ($Hostname -notmatch '^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$' -or $Hostname -notmatch '\.') {
  throw "주소 형식이 올바르지 않습니다. 예: trader.example.com"
}

Write-Host ""
Write-Host "1/4 Cloudflare 계정 인증"
Write-Host "브라우저가 열리면 이 주소의 도메인이 들어 있는 Cloudflare 계정을 선택하세요."
& $cloudflared tunnel login
if ($LASTEXITCODE -ne 0) { throw "Cloudflare 로그인에 실패했습니다." }

Write-Host ""
Write-Host "2/4 Tunnel 확인/생성"
$tunnelId = $null
try {
  $listText = (& $cloudflared tunnel list --output json 2>$null | Out-String).Trim()
  if ($LASTEXITCODE -eq 0 -and $listText) {
    $rows = $listText | ConvertFrom-Json
    $match = @($rows | Where-Object { $_.name -eq $TunnelName }) | Select-Object -First 1
    if ($match) { $tunnelId = [string]$match.id }
  }
} catch {}

if (-not $tunnelId) {
  $createText = (& $cloudflared tunnel create $TunnelName 2>&1 | Out-String)
  if ($LASTEXITCODE -ne 0) { throw "Tunnel 생성 실패:`n$createText" }
  $idMatch = [regex]::Match($createText, '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
  if ($idMatch.Success) { $tunnelId = $idMatch.Value }
}

if (-not $tunnelId) {
  try {
    $listText = (& $cloudflared tunnel list --output json 2>$null | Out-String).Trim()
    $rows = $listText | ConvertFrom-Json
    $match = @($rows | Where-Object { $_.name -eq $TunnelName }) | Select-Object -First 1
    if ($match) { $tunnelId = [string]$match.id }
  } catch {}
}
if (-not $tunnelId) { throw "Tunnel ID를 확인하지 못했습니다." }

$credentials = Join-Path (Join-Path $env:USERPROFILE ".cloudflared") "$tunnelId.json"
if (-not (Test-Path $credentials)) {
  throw "Tunnel 인증 파일을 찾지 못했습니다: $credentials"
}

Write-Host ""
Write-Host "3/4 DNS 고정 주소 연결"
$routeText = (& $cloudflared tunnel route dns $tunnelId $Hostname 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
  throw "DNS 연결 실패. 입력한 도메인이 같은 Cloudflare 계정에서 관리되는지 확인하세요.`n$routeText"
}

Write-Host ""
Write-Host "4/4 로컬 설정 저장"
$escapedCredentials = $credentials.Replace("'", "''")
$config = @"
tunnel: $tunnelId
credentials-file: '$escapedCredentials'
ingress:
  - hostname: $Hostname
    service: http://127.0.0.1:8765
  - service: http_status:404
"@
Set-Content -Path $configFile -Value $config -Encoding UTF8

$state = [ordered]@{
  schema_version = 1
  tunnel_name = $TunnelName
  tunnel_id = $tunnelId
  hostname = $Hostname
  config_file = $configFile
  credentials_file = $credentials
}
$state | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8

Write-Host ""
Write-Host "설정 완료" -ForegroundColor Green
Write-Host "고정 휴대폰 주소: https://$Hostname" -ForegroundColor Green
Write-Host ""
Write-Host "앞으로는 평소처럼 .\start-trader-secure.bat 만 실행하면 됩니다."
Write-Host "서버를 껐다 켜도 같은 주소를 사용하고, 같은 브라우저에서는 휴대폰 연결 코드도 다시 입력할 필요가 없습니다."
