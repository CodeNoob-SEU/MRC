# Launcher for the CI-built portable bundles (MRC-windows-x64.zip /
# MRC-windows-x86.zip). Detects which bundled Python is present and picks
# the matching vendor DLL architecture (x86 Python -> win32 DLLs). No dev
# server or venv setup needed.
param(
  [ValidateSet("real", "mock")]
  [string]$Mode = "real",
  [int]$Port = 7876,
  [int]$CameraDeviceIndex = 0,
  [switch]$EnableCamera2,
  [int]$Camera2DeviceIndex = 1,
  [int]$DaqDeviceIndex = 0,
  [int]$VideoSourceIndex = 0,
  [int]$VideoSourceIndex2 = -1,
  [ValidateSet("mp4", "avi")]
  [string]$CaptureFormat = "mp4"
)

$ErrorActionPreference = "Stop"

$repoRoot = $PSScriptRoot
$pythonX86 = Join-Path $repoRoot "backend\python-x86\python.exe"
$pythonX64 = Join-Path $repoRoot "backend\python-x64\python.exe"
if (Test-Path $pythonX86) {
  $pythonExe = $pythonX86
  $vendorArch = "win32"
} elseif (Test-Path $pythonX64) {
  $pythonExe = $pythonX64
  $vendorArch = "x64"
} else {
  throw "Bundled Python was not found (backend\python-x86 or backend\python-x64). This script is for the CI-built bundle; for a source checkout use scripts\run_windows.ps1."
}
$electronExe = Join-Path $repoRoot "frontend\node_modules\electron\dist\electron.exe"
$ffmpegExe = Join-Path $repoRoot "vendor\ffmpeg\windows\bin\ffmpeg.exe"
if (!(Test-Path $electronExe)) {
  throw "Bundled Electron was not found ($electronExe)."
}
if (!(Test-Path (Join-Path $repoRoot "frontend\dist\index.html"))) {
  throw "Built frontend was not found (frontend\dist). This script is for the CI-built bundle."
}

$env:MRC_PYTHON = $pythonExe
$env:MRC_BACKEND_PORT = [string]$Port
$env:MRC_HARDWARE_MODE = $Mode
$env:MRC_UI_MODE = "dist"
$env:MRC_FAST_BACKEND_SHUTDOWN = if ($env:MRC_FAST_BACKEND_SHUTDOWN) { $env:MRC_FAST_BACKEND_SHUTDOWN } else { "1" }

if ($Mode -eq "real") {
  $env:MRC_VENDOR_ARCH = $vendorArch
  $env:MRC_CAMERA_DEVICE_INDEX = [string]$CameraDeviceIndex
  $env:MRC_CAMERA2_ENABLED = if ($EnableCamera2) { "1" } else { "0" }
  $env:MRC_CAMERA2_DEVICE_INDEX = [string]$Camera2DeviceIndex
  $env:MRC_DAQ_DEVICE_INDEX = [string]$DaqDeviceIndex
  $env:MRC_CAMERA_VIDEO_SOURCE_INDEX = [string]$VideoSourceIndex
  $effectiveVideoSourceIndex2 = if ($VideoSourceIndex2 -ge 0) { $VideoSourceIndex2 } else { $VideoSourceIndex }
  $env:MRC_CAMERA2_VIDEO_SOURCE_INDEX = [string]$effectiveVideoSourceIndex2
  $env:MRC_CAMERA_WIDTH = if ($env:MRC_CAMERA_WIDTH) { $env:MRC_CAMERA_WIDTH } else { "720" }
  $env:MRC_CAMERA_HEIGHT = if ($env:MRC_CAMERA_HEIGHT) { $env:MRC_CAMERA_HEIGHT } else { "480" }
  $env:MRC_CAMERA_FPS = if ($env:MRC_CAMERA_FPS) { $env:MRC_CAMERA_FPS } else { "30" }
  $env:MRC_CAMERA_VIDEO_STANDARD = if ($env:MRC_CAMERA_VIDEO_STANDARD) { $env:MRC_CAMERA_VIDEO_STANDARD } else { "1" }
  $env:MRC_CAMERA_COLORSPACE = if ($env:MRC_CAMERA_COLORSPACE) { $env:MRC_CAMERA_COLORSPACE } else { "2" }
  $env:MRC_CAMERA_CAPTURE_FORMAT = if ($CaptureFormat -eq "avi") { "1" } else { "2" }
  $env:MRC_CAMERA_VIDEO_CODEC = if ($env:MRC_CAMERA_VIDEO_CODEC) { $env:MRC_CAMERA_VIDEO_CODEC } else { "x264 Codec" }
  $env:MRC_CAMERA_PREVIEW_MODE = if ($env:MRC_CAMERA_PREVIEW_MODE) { $env:MRC_CAMERA_PREVIEW_MODE } else { "2" }
  $env:MRC_CAMERA_PREVIEW_FPS = if ($env:MRC_CAMERA_PREVIEW_FPS) { $env:MRC_CAMERA_PREVIEW_FPS } else { "0" }
}

if (!$env:MRC_FFMPEG -and (Test-Path $ffmpegExe)) {
  $env:MRC_FFMPEG = (Resolve-Path $ffmpegExe).Path
}

Write-Host "Starting MRC Integrated Acquisition (portable bundle, vendor arch: $vendorArch)" -ForegroundColor Cyan
Write-Host "  Mode:          $Mode"
Write-Host "  Backend port:  $env:MRC_BACKEND_PORT"
Write-Host "  Python:        $env:MRC_PYTHON"
if ($Mode -eq "real") {
  Write-Host "  Vendor arch:   $env:MRC_VENDOR_ARCH"
  Write-Host "  Camera index:  $env:MRC_CAMERA_DEVICE_INDEX  (camera2: $env:MRC_CAMERA2_ENABLED)"
  Write-Host "  DAQ index:     $env:MRC_DAQ_DEVICE_INDEX"
}
if ($env:MRC_FFMPEG) {
  Write-Host "  FFmpeg:        $env:MRC_FFMPEG"
} else {
  Write-Warning "FFmpeg was not found. Aligned trimming and frame extraction will be unavailable."
}

& (Join-Path $repoRoot "scripts\ensure_backend_port_windows.ps1") -Port $Port

& $electronExe (Join-Path $repoRoot "frontend")
