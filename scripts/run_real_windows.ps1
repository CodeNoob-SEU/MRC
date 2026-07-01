$ErrorActionPreference = "Stop"
$env:MRC_HARDWARE_MODE = "real"

Push-Location "$PSScriptRoot\..\frontend"
npm run dev
Pop-Location

