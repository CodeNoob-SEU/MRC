$ErrorActionPreference = "Stop"
$env:MRC_HARDWARE_MODE = "real"
$env:MRC_BACKEND_PORT = if ($env:MRC_BACKEND_PORT) { $env:MRC_BACKEND_PORT } else { "7876" }
$env:MRC_CAMERA_DEVICE_INDEX = if ($env:MRC_CAMERA_DEVICE_INDEX) { $env:MRC_CAMERA_DEVICE_INDEX } else { "0" }
$env:MRC_DAQ_DEVICE_INDEX = if ($env:MRC_DAQ_DEVICE_INDEX) { $env:MRC_DAQ_DEVICE_INDEX } else { "0" }

& "$PSScriptRoot\ensure_backend_port_windows.ps1" -Port ([int]$env:MRC_BACKEND_PORT)

try {
  Push-Location "$PSScriptRoot\..\frontend"
  npm run dev
} finally {
  Pop-Location
}
