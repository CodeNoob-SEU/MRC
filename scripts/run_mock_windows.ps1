$ErrorActionPreference = "Stop"
$env:MRC_HARDWARE_MODE = "mock"
$env:MRC_BACKEND_PORT = if ($env:MRC_BACKEND_PORT) { $env:MRC_BACKEND_PORT } else { "7876" }

& "$PSScriptRoot\ensure_backend_port_windows.ps1" -Port ([int]$env:MRC_BACKEND_PORT)

try {
  Push-Location "$PSScriptRoot\..\frontend"
  npm run dev
} finally {
  Pop-Location
}
