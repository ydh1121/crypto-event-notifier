$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$targetBranch = "b3-auto-trader-phase1"
$controlPaths = @("control/assets.json", "control/runtime.json")

# This launcher is the normal always-on mode for the project. Keep GitHub polling
# enabled and reasonably quick even when an older .env still contains the original
# template values. python-dotenv does not override process environment.
$env:AUTO_GIT_SYNC = "true"
$env:AUTO_GIT_PUSH_CONTROL = "true"
$env:GIT_SYNC_INTERVAL_SECONDS = "15"

# Windows PowerShell 5.1 can surface stderr from a successful native command
# (for example Git's normal "From https://..." fetch progress) as an ErrorRecord.
# Capture native Git output and decide success from the exit code.
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

function Get-DirtyPaths {
  param([string]$StatusText)
  if (-not $StatusText) { return @() }
  return @($StatusText -split "`n" | ForEach-Object {
    $line = $_.TrimEnd("`r")
    if ($line.Length -ge 4) { $line.Substring(3).Trim() }
  } | Where-Object { $_ })
}

function Test-ControlOnlyDirty {
  param([string[]]$Paths)
  if (-not $Paths -or $Paths.Count -eq 0) { return $false }
  foreach ($path in $Paths) {
    if ($path -notin $controlPaths) { return $false }
  }
  return $true
}

function Invoke-SafeControlPreservingRepair {
  $repairScript = Join-Path $repo "scripts\repair-local-sync.ps1"
  if (-not (Test-Path $repairScript)) {
    Write-Warning "Local control state exists, but the safe sync-repair script is missing. Starting with the current local copy."
    return $false
  }

  Write-Host "Local coin/control settings found. Preserving them while updating application code from GitHub..." -ForegroundColor Cyan
  $previousPreference = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $repairScript
    $repairCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previousPreference
  }
  if ($repairCode -ne 0) {
    Write-Warning "Safe startup sync could not complete. The trader will start from the existing local copy."
    return $false
  }
  Write-Host "Startup GitHub sync complete. Local coin settings were preserved." -ForegroundColor Green
  return $true
}

$isGitRepo = Test-GitRepository
if ($isGitRepo) {
  $status = Invoke-GitCapture -GitArgs @("status", "--porcelain")
  if ($status.ExitCode -ne 0) {
    Write-Warning "Could not read Git working-tree status. Starting with the local copy."
  } else {
    $dirtyPaths = @(Get-DirtyPaths -StatusText $status.Output)
    if ($dirtyPaths.Count -eq 0) {
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
    } elseif (Test-ControlOnlyDirty -Paths $dirtyPaths) {
      [void](Invoke-SafeControlPreservingRepair)
    } else {
      Write-Warning "Local Git working tree has non-control changes. Startup update was skipped so those files are not overwritten."
      $dirtyPaths | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" -ForegroundColor Yellow }
    }
  }

  $localHead = Invoke-GitCapture -GitArgs @("rev-parse", "--short", "HEAD")
  $remoteHead = Invoke-GitCapture -GitArgs @("rev-parse", "--short", "origin/$targetBranch")
  if ($localHead.ExitCode -eq 0 -and $remoteHead.ExitCode -eq 0) {
    if ($localHead.Output.Trim() -eq $remoteHead.Output.Trim()) {
      Write-Host "GitHub sync: latest ($($localHead.Output.Trim()))" -ForegroundColor Green
    } else {
      Write-Warning "GitHub sync: local $($localHead.Output.Trim()) / remote $($remoteHead.Output.Trim()). Runtime auto-sync will keep retrying."
    }
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
    Write-Host "GitHub runtime update applied. Restarting trader automatically..."
    Start-Sleep -Seconds 2
    continue
  }
  Write-Host "Trader stopped with exit code $code. Restarting in 5 seconds..."
  Start-Sleep -Seconds 5
}