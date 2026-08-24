$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$targetBranch = "b3-auto-trader-phase1"

function Test-GitRepository {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return $false }
  if (-not (Test-Path (Join-Path $repo ".git"))) { return $false }
  & git -C $repo rev-parse --is-inside-work-tree *> $null
  return ($LASTEXITCODE -eq 0)
}

$isGitRepo = Test-GitRepository
if ($isGitRepo) {
  $dirty = & git status --porcelain
  if (-not $dirty) {
    & git fetch origin $targetBranch 2>$null
    if ($LASTEXITCODE -eq 0) {
      $current = & git branch --show-current
      if ($current -ne $targetBranch) {
        & git checkout -B $targetBranch "origin/$targetBranch"
      }
    } else {
      Write-Warning "GitHub fetch failed. Starting with the local copy; automatic Git sync may also be unavailable until Git authentication/network is fixed."
    }
  } else {
    Write-Warning "Local Git working tree has changes. Startup update was skipped to avoid overwriting them."
  }
} else {
  Write-Warning "This folder is a GitHub ZIP/export (no .git metadata). The trader will still run locally, but GPT/GitHub automatic sync is disabled for this copy."
  Write-Host "For automatic GPT/GitHub sync later, use 'git clone' instead of Download ZIP."
  $env:AUTO_GIT_SYNC = "false"
  $env:AUTO_GIT_PUSH_CONTROL = "false"
}

function Resolve-PythonLauncher {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 -c "import sys" *> $null
    if ($LASTEXITCODE -eq 0) { return @("py", "-3.12") }
    & py -3 -c "import sys" *> $null
    if ($LASTEXITCODE -eq 0) { return @("py", "-3") }
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    & python -c "import sys" *> $null
    if ($LASTEXITCODE -eq 0) { return @("python") }
  }
  throw "Python 3 was not found. Install Python 3.12+ and enable 'py' or 'python' in PATH."
}

if (-not (Test-Path ".venv")) {
  $launcher = Resolve-PythonLauncher
  if ($launcher.Count -eq 2) {
    & $launcher[0] $launcher[1] -m venv .venv
  } else {
    & $launcher[0] -m venv .venv
  }
}

$python = Join-Path (Resolve-Path ".venv") "Scripts\python.exe"
& $python -m pip install --disable-pip-version-check -r b3_trader\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

if (-not (Test-Path ".env")) {
  Copy-Item "b3_trader\.env.example" ".env"
  Write-Host ".env created. PAPER mode needs no Bithumb API key."
}

Write-Host "Starting Crypto Auto Trader..."
Write-Host "Dashboard will be available at http://127.0.0.1:8765"
while ($true) {
  & $python -m b3_trader.local_app
  $code = $LASTEXITCODE
  if ($code -eq 0) { break }
  if ($code -eq 75) {
    Write-Host "GitHub update applied. Restarting trader..."
    Start-Sleep -Seconds 2
    continue
  }
  Write-Host "Trader stopped with exit code $code. Restarting in 5 seconds..."
  Start-Sleep -Seconds 5
}
