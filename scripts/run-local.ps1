$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$targetBranch = "b3-auto-trader-phase1"
$dirty = git status --porcelain
if (-not $dirty) {
  git fetch origin $targetBranch 2>$null
  $current = git branch --show-current
  if ($current -ne $targetBranch) { git checkout -B $targetBranch "origin/$targetBranch" }
}
if (-not (Test-Path ".venv")) { py -3.12 -m venv .venv }
$python = Join-Path (Resolve-Path ".venv") "Scripts\python.exe"
& $python -m pip install --disable-pip-version-check -r b3_trader\requirements.txt
if (-not (Test-Path ".env")) {
  Copy-Item "b3_trader\.env.example" ".env"
  Write-Host ".env created. Paper mode needs no Bithumb API key."
}
while ($true) {
  & $python -m b3_trader.local_app
  $code = $LASTEXITCODE
  if ($code -eq 0) { break }
  if ($code -eq 75) { Write-Host "GitHub update applied. Restarting trader..."; Start-Sleep -Seconds 2; continue }
  Write-Host "Trader stopped with exit code $code. Restarting in 5 seconds..."
  Start-Sleep -Seconds 5
}
