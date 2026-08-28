$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
  exit 0
}

$expectedPython = [System.IO.Path]::GetFullPath($python)
$moduleNames = @(
  "b3_trader.research_supervisor",
  "b3_trader.paper_runtime_supervisor"
)
$stopped = @()

try {
  $processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
} catch {
  Write-Warning "Could not inspect existing runtime supervisors. Startup will continue without cleanup: $($_.Exception.Message)"
  exit 0
}

foreach ($process in $processes) {
  $pidValue = [int]$process.ProcessId
  if ($pidValue -le 0 -or $pidValue -eq $PID) { continue }

  $executable = [string]$process.ExecutablePath
  $commandLine = [string]$process.CommandLine
  if (-not $executable -or -not $commandLine) { continue }

  try {
    $candidatePython = [System.IO.Path]::GetFullPath($executable)
  } catch {
    continue
  }

  if (-not [string]::Equals($candidatePython, $expectedPython, [System.StringComparison]::OrdinalIgnoreCase)) {
    continue
  }

  $matchedModule = $null
  foreach ($moduleName in $moduleNames) {
    if ($commandLine -match [regex]::Escape($moduleName)) {
      $matchedModule = $moduleName
      break
    }
  }
  if (-not $matchedModule) { continue }

  try {
    Stop-Process -Id $pidValue -Force -ErrorAction Stop
    $stopped += [PSCustomObject]@{ pid = $pidValue; module = $matchedModule }
  } catch {
    Write-Warning "Could not stop stale $matchedModule process ${pidValue}: $($_.Exception.Message)"
  }
}

if ($stopped.Count -gt 0) {
  Start-Sleep -Milliseconds 500
  foreach ($row in $stopped) {
    Write-Host "Stopped stale runtime supervisor: $($row.module) (PID $($row.pid))" -ForegroundColor Yellow
  }
}
