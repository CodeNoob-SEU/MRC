$ErrorActionPreference = "Stop"

Push-Location "$PSScriptRoot\..\backend"
if (!(Test-Path ".venv")) {
  py -3 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Pop-Location

Push-Location "$PSScriptRoot\..\frontend"
npm install --cache .npm-cache
Pop-Location

Write-Host "Setup complete."

