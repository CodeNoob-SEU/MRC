$ErrorActionPreference = "Stop"

try {
  & "$PSScriptRoot\setup_ffmpeg_windows.ps1"
} catch {
  Write-Warning "Bundled ffmpeg setup failed: $($_.Exception.Message)"
  Write-Warning "Setup will continue. Trigger recording can still run, but aligned video trimming needs ffmpeg."
}

try {
  Push-Location "$PSScriptRoot\..\backend"
  if (!(Test-Path ".venv")) {
    py -3 -m venv .venv
  }
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt
} finally {
  Pop-Location
}

try {
  Push-Location "$PSScriptRoot\..\frontend"
  npm install --cache .npm-cache
} finally {
  Pop-Location
}

Write-Host "Setup complete."
