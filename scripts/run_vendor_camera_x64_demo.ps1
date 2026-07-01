$ErrorActionPreference = "Stop"

$sdkDir = Resolve-Path "$PSScriptRoot\..\vendor\camera\x64"
$demo = Join-Path $sdkDir "VS2010dmeoX64.exe"

if (!(Test-Path $demo)) {
  throw "Vendor x64 demo not found: $demo"
}

Push-Location $sdkDir
Start-Process -FilePath $demo
Pop-Location

