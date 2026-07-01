$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path "$PSScriptRoot\.."
$env:MRC_VENDOR_ARCH = if ($env:MRC_VENDOR_ARCH) { $env:MRC_VENDOR_ARCH } else { "win32" }
$env:MRC_CAMERA_DEVICE_INDEX = if ($env:MRC_CAMERA_DEVICE_INDEX) { $env:MRC_CAMERA_DEVICE_INDEX } else { "0" }
$env:MRC_CAMERA_VIDEO_CODEC = if ($env:MRC_CAMERA_VIDEO_CODEC) { $env:MRC_CAMERA_VIDEO_CODEC } else { "x264 Codec" }

$python = if ($env:MRC_PYTHON32) {
  $env:MRC_PYTHON32
} else {
  Join-Path $repoRoot "backend\.venv32\Scripts\python.exe"
}

if (!(Test-Path $python)) {
  throw "32-bit Python not found: $python. Run .\scripts\setup_windows_x86.ps1 first, or set MRC_PYTHON32."
}

try {
  & "$PSScriptRoot\ensure_backend_port_windows.ps1" -Port 7876
} catch {
  Write-Warning "Could not clear backend port 7876. Continue only if no backend is holding the camera. $($_.Exception.Message)"
}

Push-Location $repoRoot
try {
  & $python "backend\tools\camera_probe.py" @args
} finally {
  Pop-Location
}
