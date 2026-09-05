$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir ".." )).Path
Set-Location $repoRoot

Write-Host ""
Write-Host "Crypto Auto Trader - Cloudflare Pages Viewer Setup"
Write-Host "----------------------------------------------------"
Write-Host "이 작업은 Cloudflare 브라우저 로그인을 한 번 요청할 수 있습니다."
Write-Host "API 토큰이나 관리자 생성 키를 이 콘솔/채팅에 출력하지 않습니다."
Write-Host ""

$python = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} else {
    throw "Python을 찾지 못했습니다. 먼저 일반 트레이더 실행 환경이 정상인지 확인하세요."
}

if ($python -eq "py") {
    & py -3 -m b3_trader.cloudflare_pages_setup
} else {
    & python -m b3_trader.cloudflare_pages_setup
}

if ($LASTEXITCODE -ne 0) {
    throw "Cloudflare Pages Viewer 설정이 완료되지 않았습니다."
}

Write-Host ""
Write-Host "설정 완료. 이후 GitHub에서 cloudflare-pages 코드가 바뀌면 24시간 PC가 변경을 받아 Pages에 자동 배포합니다."
Write-Host "실제 주문 기능은 추가되지 않았고, 웹 화면은 조회 전용입니다."
