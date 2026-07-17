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
  [string]$CaptureFormat = "mp4",
  [switch]$Dev,
  [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.Platform -and $PSVersionTable.Platform -ne "Win32NT") {
  throw "This run script is intended for Windows PowerShell."
}

$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$frontendDir = Join-Path $repoRoot "frontend"
$pythonExe = Join-Path $repoRoot "backend\.venv32\Scripts\python.exe"
$ffmpegExe = Join-Path $repoRoot "vendor\ffmpeg\windows\bin\ffmpeg.exe"

if (!(Test-Path $pythonExe)) {
  throw "32-bit backend environment was not found. Run .\scripts\init_windows.ps1 first."
}

if (!(Test-Path (Join-Path $frontendDir "node_modules"))) {
  throw "Frontend dependencies were not found. Run .\scripts\init_windows.ps1 first."
}

$env:MRC_HARDWARE_MODE = $Mode
$env:MRC_BACKEND_PORT = [string]$Port
$env:MRC_PYTHON = (Resolve-Path $pythonExe).Path
$env:MRC_FAST_BACKEND_SHUTDOWN = if ($env:MRC_FAST_BACKEND_SHUTDOWN) { $env:MRC_FAST_BACKEND_SHUTDOWN } else { "1" }

if ($Mode -eq "real") {
  $env:MRC_VENDOR_ARCH = "win32"
  $env:MRC_CAMERA_DEVICE_INDEX = [string]$CameraDeviceIndex
  $env:MRC_CAMERA2_ENABLED = if ($EnableCamera2) { "1" } elseif ($env:MRC_CAMERA2_ENABLED) { $env:MRC_CAMERA2_ENABLED } else { "auto" }
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

Write-Host "Starting MRC Integrated Acquisition" -ForegroundColor Cyan
Write-Host "  Mode:             $Mode"
Write-Host "  Backend port:     $env:MRC_BACKEND_PORT"
Write-Host "  Python:           $env:MRC_PYTHON"
Write-Host "  Fast shutdown:    $env:MRC_FAST_BACKEND_SHUTDOWN"
if ($Mode -eq "real") {
  Write-Host "  Vendor arch:      $env:MRC_VENDOR_ARCH"
  Write-Host "  Camera index:     $env:MRC_CAMERA_DEVICE_INDEX"
  Write-Host "  Camera 2 enabled: $env:MRC_CAMERA2_ENABLED"
  if ($EnableCamera2) {
    Write-Host "  Camera 2 index:   $env:MRC_CAMERA2_DEVICE_INDEX"
  }
  Write-Host "  DAQ index:        $env:MRC_DAQ_DEVICE_INDEX"
  Write-Host "  Video source:     $env:MRC_CAMERA_VIDEO_SOURCE_INDEX"
  if ($EnableCamera2) {
    Write-Host "  Video source 2:   $env:MRC_CAMERA2_VIDEO_SOURCE_INDEX"
  }
  Write-Host "  Camera format:    $env:MRC_CAMERA_WIDTH x $env:MRC_CAMERA_HEIGHT @ $env:MRC_CAMERA_FPS fps"
}
if ($env:MRC_FFMPEG) {
  Write-Host "  FFmpeg:           $env:MRC_FFMPEG"
} else {
  Write-Warning "FFmpeg was not found. Aligned trimming and first/last frame extraction will be unavailable."
}

Write-Host "[1/3] Checking backend port $Port..." -ForegroundColor Cyan
& "$PSScriptRoot\ensure_backend_port_windows.ps1" -Port $Port

if ($Dev) {
  # Development mode: vite dev server + tsc watch + HMR (slow startup).
  try {
    Push-Location $frontendDir
    npm run dev
  } finally {
    Pop-Location
  }
  return
}

# Fast start (default): run the built renderer directly. Rebuild only when
# no build exists, -Rebuild was given, or sources are newer than the build.
$distIndex = Join-Path $frontendDir "dist\index.html"
$distMain = Join-Path $frontendDir "dist-electron\main.js"
$needBuild = $Rebuild -or !(Test-Path $distIndex) -or !(Test-Path $distMain)
if (-not $needBuild) {
  $sourcePaths = @(
    (Join-Path $frontendDir "src"),
    (Join-Path $frontendDir "electron"),
    (Join-Path $frontendDir "index.html"),
    (Join-Path $frontendDir "vite.config.ts"),
    (Join-Path $frontendDir "package.json")
  )
  $newestSource = Get-ChildItem -Path $sourcePaths -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  $builtIndex = (Get-Item $distIndex).LastWriteTime
  $builtMain = (Get-Item $distMain).LastWriteTime
  $builtTime = if ($builtIndex -lt $builtMain) { $builtIndex } else { $builtMain }
  if ($newestSource -and $newestSource.LastWriteTime -gt $builtTime) {
    Write-Host "Frontend sources changed; rebuilding once..." -ForegroundColor Yellow
    $needBuild = $true
  }
}
if ($needBuild) {
  Write-Host "[2/3] Building frontend (first run or sources changed; takes a moment)..." -ForegroundColor Yellow
  try {
    Push-Location $frontendDir
    npm run build:fast
    if ($LASTEXITCODE -ne 0) {
      throw "Frontend build failed (exit code $LASTEXITCODE)."
    }
  } finally {
    Pop-Location
  }
} else {
  Write-Host "[2/3] Frontend build is up to date (skipped)." -ForegroundColor Cyan
}

$electronExe = Join-Path $frontendDir "node_modules\electron\dist\electron.exe"
if (!(Test-Path $electronExe)) {
  throw "Electron runtime was not found at $electronExe. Run .\scripts\init_windows.ps1 first."
}
$env:MRC_UI_MODE = "dist"
Write-Host "[3/3] Launching app (add -Dev for development mode with HMR)..." -ForegroundColor Cyan
& $electronExe $frontendDir
