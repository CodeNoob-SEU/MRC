param(
  [int]$Port = 7876,
  [string]$DeviceNamePattern = "ZhongAn|US2000|Video Capture",
  [switch]$NoSelfElevate,
  [switch]$IncludeAllNodeInRepo,
  [switch]$SkipDeviceReset
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.Platform -and $PSVersionTable.Platform -ne "Win32NT") {
  throw "This cleanup script is intended for Windows PowerShell."
}

$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$repoRootLower = $repoRoot.ToLowerInvariant()

function Test-IsAdministrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Restart-AsAdministrator {
  if ($NoSelfElevate) {
    throw "Access denied is expected from a non-admin shell. Open PowerShell as Administrator and rerun this script."
  }
  $arguments = @(
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "`"$PSCommandPath`"",
    "-Port",
    "$Port"
  )
  if ($IncludeAllNodeInRepo) {
    $arguments += "-IncludeAllNodeInRepo"
  }
  if ($SkipDeviceReset) {
    $arguments += "-SkipDeviceReset"
  }
  $arguments += @("-DeviceNamePattern", "`"$DeviceNamePattern`"")
  Write-Host "Requesting Administrator privileges for system-level cleanup..."
  Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -Verb RunAs | Out-Null
  exit 0
}

if (!(Test-IsAdministrator)) {
  Restart-AsAdministrator
}

function Get-PortListeners {
  $listenerPids = @()
  try {
    $listenerPids += Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique
  } catch {
    # Fall back to netstat below.
  }

  try {
    $netstat = & netstat.exe -ano -p tcp 2>$null
    foreach ($line in $netstat) {
      if ($line -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
        $listenerPids += [int]$Matches[1]
      }
    }
  } catch {
    # Ignore fallback failure; the final verification will report remaining listeners.
  }

  @($listenerPids | Where-Object { $_ -and $_ -ne $PID } | Sort-Object -Unique)
}

function Get-ProcessTable {
  @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name, CommandLine, ExecutablePath)
}

function Add-Pid {
  param(
    [System.Collections.Generic.HashSet[int]]$Set,
    [int]$ProcessId
  )
  if ($ProcessId -and $ProcessId -ne $PID) {
    [void]$Set.Add($ProcessId)
  }
}

function Add-ProcessTree {
  param(
    [System.Collections.Generic.HashSet[int]]$Set,
    [array]$ProcessTable,
    [int]$RootPid
  )
  Add-Pid -Set $Set -ProcessId $RootPid
  $children = @($ProcessTable | Where-Object { [int]$_.ParentProcessId -eq $RootPid })
  foreach ($child in $children) {
    Add-ProcessTree -Set $Set -ProcessTable $ProcessTable -RootPid ([int]$child.ProcessId)
  }
}

function Get-MrcCandidatePids {
  $processTable = Get-ProcessTable
  $candidatePids = New-Object "System.Collections.Generic.HashSet[int]"

  foreach ($listenerPid in Get-PortListeners) {
    Add-ProcessTree -Set $candidatePids -ProcessTable $processTable -RootPid ([int]$listenerPid)
  }

  foreach ($process in $processTable) {
    $commandLine = [string]$process.CommandLine
    $commandLower = $commandLine.ToLowerInvariant()
    $nameLower = ([string]$process.Name).ToLowerInvariant()
    $isMrcBackend = $commandLower.Contains("mrc_backend.run_backend")
    $isRepoProcess = $commandLower.Contains($repoRootLower)
    $isRuntimeProcess = $nameLower -in @(
      "python.exe",
      "pythonw.exe",
      "node.exe",
      "npm.cmd",
      "electron.exe",
      "powershell.exe"
    )

    if ($isMrcBackend -or ($isRepoProcess -and ($IncludeAllNodeInRepo -or $isRuntimeProcess))) {
      Add-ProcessTree -Set $candidatePids -ProcessTable $processTable -RootPid ([int]$process.ProcessId)
    }
  }

  @($candidatePids | Sort-Object)
}

function Stop-ProcessHard {
  param([int]$ProcessId)

  $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
  if ($null -eq $process) {
    return
  }

  $name = $process.ProcessName
  Write-Host "Stopping PID $ProcessId ($name)..."

  $errors = New-Object System.Collections.Generic.List[string]

  try {
    & taskkill.exe /PID $ProcessId /T /F 2>&1 | Out-Host
  } catch {
    $errors.Add("taskkill: $($_.Exception.Message)")
  }

  try {
    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
  } catch {
    $errors.Add("Stop-Process: $($_.Exception.Message)")
  }

  try {
    $cimProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
    if ($null -ne $cimProcess) {
      Invoke-CimMethod -InputObject $cimProcess -MethodName Terminate -ErrorAction Stop | Out-Null
    }
  } catch {
    $errors.Add("CIM Terminate: $($_.Exception.Message)")
  }

  try {
    Wait-Process -Id $ProcessId -Timeout 3 -ErrorAction SilentlyContinue
  } catch {
    # Process may already be gone.
  }

  if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
    Write-Warning "PID $ProcessId is still alive. Attempts: $($errors -join '; ')"
  }
}

function Get-CaptureDevices {
  if (!(Get-Command Get-PnpDevice -ErrorAction SilentlyContinue)) {
    return @()
  }

  @(Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
    Where-Object {
      ($_.FriendlyName -and $_.FriendlyName -match $DeviceNamePattern) -or
      ($_.InstanceId -and $_.InstanceId -match $DeviceNamePattern)
    })
}

function Restart-CaptureDevices {
  $devices = @(Get-CaptureDevices)
  if ($devices.Count -eq 0) {
    Write-Warning "No PnP capture devices matched pattern: $DeviceNamePattern"
    return
  }

  Write-Host "Resetting matching PnP capture device(s):"
  foreach ($device in $devices) {
    Write-Host "  $($device.FriendlyName) [$($device.InstanceId)]"
  }

  foreach ($device in $devices) {
    try {
      Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false -ErrorAction Stop | Out-Null
    } catch {
      Write-Warning "Disable-PnpDevice failed for $($device.FriendlyName): $($_.Exception.Message)"
    }
  }

  Start-Sleep -Seconds 2

  foreach ($device in $devices) {
    try {
      Enable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false -ErrorAction Stop | Out-Null
    } catch {
      Write-Warning "Enable-PnpDevice failed for $($device.FriendlyName): $($_.Exception.Message)"
    }
  }

  Start-Sleep -Seconds 2
}

Write-Host "MRC system-level cleanup"
Write-Host "  Repo: $repoRoot"
Write-Host "  Backend port: $Port"
Write-Host "  Device reset pattern: $DeviceNamePattern"

$candidatePids = @(Get-MrcCandidatePids)
if ($candidatePids.Count -eq 0) {
  Write-Host "No MRC backend/Electron processes found."
} else {
  Write-Host "Candidate PID(s): $($candidatePids -join ', ')"
}

foreach ($processId in $candidatePids) {
  Stop-ProcessHard -ProcessId ([int]$processId)
}

Start-Sleep -Milliseconds 500
$remainingListeners = @(Get-PortListeners)
if ($remainingListeners.Count -gt 0 -and !$SkipDeviceReset) {
  Write-Warning "Port $Port is still occupied after process termination attempts. Trying PnP capture-device reset..."
  Restart-CaptureDevices
  foreach ($processId in @(Get-MrcCandidatePids)) {
    Stop-ProcessHard -ProcessId ([int]$processId)
  }
  Start-Sleep -Milliseconds 500
  $remainingListeners = @(Get-PortListeners)
}

if ($remainingListeners.Count -gt 0) {
  $details = foreach ($processId in $remainingListeners) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $process) {
      "$processId (unknown)"
    } else {
      "$processId ($($process.ProcessName))"
    }
  }
  throw "Port $Port is still occupied by PID(s): $($details -join ', '). Reboot Windows if this PID cannot be killed even from Administrator PowerShell."
}

Write-Host "Cleanup complete. Port $Port is free." -ForegroundColor Green
