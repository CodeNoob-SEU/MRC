$ErrorActionPreference = "Stop"

$sdkDir = Resolve-Path "$PSScriptRoot\..\vendor\camera\win32"
$demo = Join-Path $sdkDir "VCDemo.exe"

if (!(Test-Path $demo)) {
  throw "Vendor win32 demo not found: $demo"
}

Push-Location $sdkDir
Start-Process -FilePath $demo
Pop-Location

