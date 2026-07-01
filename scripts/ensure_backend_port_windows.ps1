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
