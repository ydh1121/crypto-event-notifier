$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$targetBranch = "b3-auto-trader-phase1"

# Windows PowerShell 5.1 can surface stderr from a successful native command
# (for example Git's normal "From https://..." fetch progress) as an ErrorRecord.
# With ErrorActionPreference=Stop that incorrectly aborts startup. Capture native
# Git output under Continue semantics and decide success only from the exit code.
function Invoke-GitCapture {
  param([Parameter(Mandatory = $true)][string[]]$GitArgs)

  $previousPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $lines = & git @GitArgs 2>&1
    $exitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousPreference
  }

  $text = if ($null -eq $lines) { "" } else { (($lines | ForEach-Object { $_.ToString() }) -join "`n").Trim() }
  return [PSCustomObject]@{
    ExitCode = $exitCode
    Output = $text
  }
}

function Test-GitRepository {
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) { return $false }
  if (-not (Test-Path (Join-Path $repo ".git"))) { return $false }
  $probe = Invoke-GitCapture -GitArgs @("-C", $repo, "rev-parse", "--is-inside-work-tree")
  return ($probe.ExitCode -eq 0 -and $probe.Output -match "true")
}

$isGitRepo = Test-GitRepository
if ($isGitRepo) {
  $status = Invoke-GitCapture -GitArgs @("status", "--porcelain")
  if ($status.ExitCode -ne 0) {
    Write-Warning "Could not read Git working-tree status. Starting with the local copy."
  } elseif (-not $status.Output) {
    $fetch = Invoke-GitCapture -GitArgs @("fetch", "origin", $targetBranch)
    if ($fetch.ExitCode -eq 0) {
      $branch = Invoke-GitCapture -GitArgs @("branch", "--show-current")
      $current = $branch.Output.Trim()
      if ($branch.ExitCode -eq 0 -and $current -and $current -ne $targetBranch) {
        $checkout = Invoke-GitCapture -GitArgs @("checkout", "-B", $targetBranch, "origin/$targetBranch")
        if ($checkout.ExitCode -ne 0) {
          Write-Warning "Could not switch to $targetBranch. Starting with the current local branch. $($checkout.Output)"
        }
      } elseif ($branch.ExitCode -eq 0 -and $current -eq $targetBranch) {
        $update = Invoke-GitCapture -GitArgs @("merge", "--ff-only", "origin/$targetBranch")
        if ($update.ExitCode -ne 0) {
          Write-Warning "Could not fast-forward $targetBranch before startup. Starting with the current local copy; runtime auto-sync will retry. $($update.Output)"
        } elseif ($update.Output) {
          Write-Host $update.Output
        }
      }
    } else {
      Write-Warning "GitHub fetch failed. Starting with the local copy; automatic Git sync may also be unavailable until Git authentication/network is fixed. $($fetch.Output)"
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
    $previousPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "Continue"
      & py -3.12 -c "import sys" *> $null
      $py312 = $LASTEXITCODE
      if ($py312 -eq 0) { return @("py", "-3.12") }
      & py -3 -c "import sys" *> $null
      $py3 = $LASTEXITCODE
      if ($py3 -eq 0) { return @("py", "-3") }
    } finally {
      $ErrorActionPreference = $previousPreference
    }
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    $previousPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "Continue"
      & python -c "import sys" *> $null
      $pythonCode = $LASTEXITCODE
      if ($pythonCode -eq 0) { return @("python") }
    } finally {
      $ErrorActionPreference = $previousPreference
    }
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
  if ($LASTEXITCODE -ne 0) { throw "Python virtual environment creation failed." }
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