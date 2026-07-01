$ErrorActionPreference = "Stop"
$env:MRC_HARDWARE_MODE = "real"
$env:MRC_CAMERA_DEVICE_INDEX = if ($env:MRC_CAMERA_DEVICE_INDEX) { $env:MRC_CAMERA_DEVICE_INDEX } else { "0" }
$env:MRC_DAQ_DEVICE_INDEX = if ($env:MRC_DAQ_DEVICE_INDEX) { $env:MRC_DAQ_DEVICE_INDEX } else { "0" }

Push-Location "$PSScriptRoot\..\frontend"
npm run dev
Pop-Location
