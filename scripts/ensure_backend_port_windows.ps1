param(
  [int]$Port = 7876
)

$ErrorActionPreference = "Stop"

function Get-PortListeners {
  @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -and $_ -ne $PID })
}

for ($attempt = 1; $attempt -le 5; $attempt++) {
  $listeners = Get-PortListeners
  if ($listeners.Count -eq 0) {
    exit 0
  }

  foreach ($processId in $listeners) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $processName = if ($null -eq $process) { "unknown" } else { $process.ProcessName }
    Write-Host "Port $Port is occupied by PID $processId ($processName); killing process tree... attempt $attempt"

    & taskkill.exe /PID $processId /T /F 2>$null | Out-Host
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    try {
      Wait-Process -Id $processId -Timeout 2 -ErrorAction SilentlyContinue
    } catch {
      # Continue to port-level verification below.
    }
  }

  for ($wait = 0; $wait -lt 20; $wait++) {
    Start-Sleep -Milliseconds 250
    $remaining = Get-PortListeners
    if ($remaining.Count -eq 0) {
      exit 0
    }
  }
}

$remaining = Get-PortListeners
if ($remaining.Count -gt 0) {
  $details = foreach ($processId in $remaining) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
      "$processId (unknown)"
    } else {
      "$processId ($($process.ProcessName))"
    }
  }
  throw "Port $Port is still occupied after cleanup by PID(s): $($details -join ', '). Try running PowerShell as Administrator or run: taskkill /PID $($remaining -join ' /PID ') /T /F"
}
