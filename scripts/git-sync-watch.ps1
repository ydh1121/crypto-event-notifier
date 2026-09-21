$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$branch = "b3-auto-trader-phase1"
$controlPaths = @("control/assets.json", "control/runtime.json")
$dataDir = Join-Path $repo "b3_trader\data"
$stateFile = Join-Path $dataDir "git-sync-watch.json"
$runtimeBuildFile = Join-Path $repo "dashboard\runtime-build.json"
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

function Git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
  $previous = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $lines = & git @Args 2>&1
    $code = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $previous
  }
  $text = if ($null -eq $lines) { "" } else { (($lines | ForEach-Object { $_.ToString() }) -join "`n").Trim() }
  return [PSCustomObject]@{ Code = $code; Text = $text }
}

function Write-State {
  param([string]$Status,[string]$Local,[string]$Remote,[string[]]$Changed,[string]$Message="")
  $payload = [ordered]@{
    ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    status = $Status
    local = $Local
    remote = $Remote
    changed = @($Changed)
    message = $Message
  }
  $payload | ConvertTo-Json -Depth 5 | Set-Content -Path $stateFile -Encoding UTF8
}

function Write-RuntimeBuild {
  param([string]$Commit)
  if (-not $Commit) { return }
  $payload = [ordered]@{
    commit = $Commit
    ts = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  }
  $tmp = "$runtimeBuildFile.tmp"
  $payload | ConvertTo-Json -Depth 3 | Set-Content -Path $tmp -Encoding UTF8
  Move-Item -Force $tmp $runtimeBuildFile
}

function Dirty-Paths {
  $status = Git status --porcelain
  if ($status.Code -ne 0 -or -not $status.Text) { return @() }
  return @($status.Text -split "`n" | ForEach-Object {
    $line = $_.TrimEnd("`r")
    if ($line.Length -ge 4) { $line.Substring(3).Trim() }
  } | Where-Object { $_ })
}

function Control-Only {
  param([string[]]$Paths)
  if (-not $Paths -or $Paths.Count -eq 0) { return $true }
  foreach ($path in $Paths) {
    if ($path -notin $controlPaths) { return $false }
  }
  return $true
}

function Preserve-Control {
  $saved = @{}
  foreach ($relative in $controlPaths) {
    $path = Join-Path $repo $relative
    if (Test-Path $path) { $saved[$relative] = [System.IO.File]::ReadAllBytes($path) }
  }
  return $saved
}

function Restore-Control {
  param($Saved)
  foreach ($entry in $Saved.GetEnumerator()) {
    $path = Join-Path $repo $entry.Key
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $path) | Out-Null
    [System.IO.File]::WriteAllBytes($path, $entry.Value)
  }
}

function NonControl-LocalCommitsExist {
  param([string]$Local,[string]$Remote)
  $base = Git merge-base $Local $Remote
  if ($base.Code -ne 0 -or -not $base.Text) { return $true }
  $localOnly = Git diff --name-only "$($base.Text)..$Local"
  if ($localOnly.Code -ne 0) { return $true }
  $paths = @($localOnly.Text -split "`n" | Where-Object { $_ })
  return -not (Control-Only $paths)
}

function Restart-RuntimeIfNeeded {
  param([string[]]$Changed)
  $needsRestart = $false
  foreach ($path in $Changed) {
    if (($path -like "b3_trader/*.py") -or $path -eq "b3_trader/requirements.txt" -or $path -eq "scripts/run-local.ps1") {
      $needsRestart = $true
      break
    }
  }
  if (-not $needsRestart) { return }
  try {
    $listeners = @(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
      if ($listener.OwningProcess -gt 0) {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {}
}

if (-not (Get-Command git -ErrorAction SilentlyContinue) -or -not (Test-Path (Join-Path $repo ".git"))) {
  Write-State -Status "disabled" -Local "" -Remote "" -Changed @() -Message "not_a_git_clone"
  exit 0
}

$lastRemote = ""
$seenCount = 0

while ($true) {
  try {
    $fetch = Git fetch origin $branch
    if ($fetch.Code -ne 0) {
      Write-State -Status "fetch_error" -Local "" -Remote "" -Changed @() -Message $fetch.Text
      Start-Sleep -Seconds 20
      continue
    }

    $local = (Git rev-parse HEAD).Text.Trim()
    $remote = (Git rev-parse "origin/$branch").Text.Trim()
    Write-RuntimeBuild -Commit $local

    if (-not $local -or -not $remote -or $local -eq $remote) {
      $lastRemote = $remote
      $seenCount = 0
      Write-State -Status "up_to_date" -Local $local -Remote $remote -Changed @()
      Start-Sleep -Seconds 20
      continue
    }

    if ($remote -eq $lastRemote) { $seenCount++ } else { $lastRemote = $remote; $seenCount = 1 }
    if ($seenCount -lt 2) {
      Write-State -Status "remote_seen" -Local $local -Remote $remote -Changed @() -Message "Waiting one cycle for the in-app updater first."
      Start-Sleep -Seconds 20
      continue
    }

    $dirty = @(Dirty-Paths)
    if (-not (Control-Only $dirty)) {
      Write-State -Status "blocked_noncontrol_dirty" -Local $local -Remote $remote -Changed $dirty -Message "Non-control local edits were preserved; watchdog did not reset them."
      Start-Sleep -Seconds 20
      continue
    }

    if (NonControl-LocalCommitsExist -Local $local -Remote $remote) {
      Write-State -Status "blocked_noncontrol_commits" -Local $local -Remote $remote -Changed @() -Message "Local non-control commits exist; manual review required."
      Start-Sleep -Seconds 20
      continue
    }

    $changedResult = Git diff --name-only "$local..$remote"
    $changed = if ($changedResult.Code -eq 0) { @($changedResult.Text -split "`n" | Where-Object { $_ }) } else { @() }
    $saved = Preserve-Control
    $reset = Git reset --hard "origin/$branch"
    if ($reset.Code -ne 0) { throw $reset.Text }
    Restore-Control -Saved $saved
    Write-RuntimeBuild -Commit $remote
    Write-State -Status "updated" -Local $local -Remote $remote -Changed $changed -Message "Independent watchdog applied remote code while preserving local control files."
    Restart-RuntimeIfNeeded -Changed $changed
    $lastRemote = $remote
    $seenCount = 0
  } catch {
    Write-State -Status "error" -Local "" -Remote "" -Changed @() -Message $_.Exception.Message
  }
  Start-Sleep -Seconds 20
}
