param(
  [int]$Port = 7876
)

$ErrorActionPreference = "Stop"

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique

foreach ($processId in $listeners) {
  if ($processId -eq $PID) {
    continue
  }

  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($null -eq $process) {
    continue
  }

  Write-Host "Port $Port is occupied by PID $processId ($($process.ProcessName)); killing it..."
  Stop-Process -Id $processId -Force
}

for ($attempt = 0; $attempt -lt 20; $attempt++) {
  $stillListening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  if ($null -eq $stillListening) {
    break
  }
  Start-Sleep -Milliseconds 250
}

$remaining = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique

if ($remaining) {
  throw "Port $Port is still occupied after cleanup by PID(s): $($remaining -join ', ')"
}
