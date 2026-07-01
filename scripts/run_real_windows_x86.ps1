$ErrorActionPreference = "Stop"
$env:MRC_HARDWARE_MODE = "real"
$env:MRC_VENDOR_ARCH = "win32"
$env:MRC_PYTHON = Resolve-Path "$PSScriptRoot\..\backend\.venv32\Scripts\python.exe"
$env:MRC_BACKEND_PORT = if ($env:MRC_BACKEND_PORT) { $env:MRC_BACKEND_PORT } else { "7876" }
$env:MRC_CAMERA_DEVICE_INDEX = if ($env:MRC_CAMERA_DEVICE_INDEX) { $env:MRC_CAMERA_DEVICE_INDEX } else { "0" }
$env:MRC_DAQ_DEVICE_INDEX = if ($env:MRC_DAQ_DEVICE_INDEX) { $env:MRC_DAQ_DEVICE_INDEX } else { "0" }

if (!(Test-Path $env:MRC_PYTHON)) {
  throw "32-bit Python venv not found. Run .\scripts\setup_windows_x86.ps1 first."
}

& "$PSScriptRoot\ensure_backend_port_windows.ps1" -Port ([int]$env:MRC_BACKEND_PORT)

Push-Location "$PSScriptRoot\..\frontend"
npm run dev
Pop-Location

