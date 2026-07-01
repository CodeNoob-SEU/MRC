$ErrorActionPreference = "Stop"

Push-Location "$PSScriptRoot\..\backend"
if (!(Test-Path ".venv32")) {
  py -3-32 -m venv .venv32
}
.\.venv32\Scripts\python.exe -m pip install -r requirements.txt
Pop-Location

Push-Location "$PSScriptRoot\..\frontend"
npm install --cache .npm-cache
Pop-Location

Write-Host "32-bit backend setup complete."

