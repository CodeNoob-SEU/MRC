$ErrorActionPreference = "Stop"
$env:MRC_HARDWARE_MODE = "mock"

Push-Location "$PSScriptRoot\..\frontend"
npm run dev
Pop-Location

