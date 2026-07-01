$ErrorActionPreference = "Stop"

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
