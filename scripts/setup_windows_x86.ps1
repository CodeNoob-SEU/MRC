$ErrorActionPreference = "Stop"

try {
  & "$PSScriptRoot\setup_ffmpeg_windows.ps1"
} catch {
  Write-Warning "Bundled ffmpeg setup failed: $($_.Exception.Message)"
  Write-Warning "Setup will continue. Trigger recording can still run, but aligned video trimming needs ffmpeg."
}

function New-X86Venv {
  param(
    [string]$VenvPath = ".venv32"
  )

  if ($env:MRC_PYTHON32) {
    if (!(Test-Path $env:MRC_PYTHON32)) {
      throw "MRC_PYTHON32 points to a missing file: $env:MRC_PYTHON32"
    }
    Write-Host "Using MRC_PYTHON32: $env:MRC_PYTHON32"
    & $env:MRC_PYTHON32 -m venv $VenvPath
    return
  }

  $candidates = @(
    @("-3.10-32", "Python 3.10 32-bit"),
    @("-3-32", "any installed 32-bit Python")
  )

  foreach ($candidate in $candidates) {
    $selector = $candidate[0]
    $label = $candidate[1]
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
      py $selector --version *> $null
      $exitCode = $LASTEXITCODE
    } catch {
      $exitCode = 1
    } finally {
      $ErrorActionPreference = $oldErrorActionPreference
    }

    if ($exitCode -eq 0) {
      Write-Host "Using $label via py $selector"
      py $selector -m venv $VenvPath
      return
    }
  }

  throw @"
No 32-bit Python runtime was found.

Install Windows x86 Python 3.10, then verify:
  py -3.10-32 --version

Or set MRC_PYTHON32 to an explicit 32-bit python.exe path:
  `$env:MRC_PYTHON32="C:\Path\To\Python310-32\python.exe"
  .\scripts\setup_windows_x86.ps1
"@
}

try {
  Push-Location "$PSScriptRoot\..\backend"
  if (!(Test-Path ".venv32")) {
    New-X86Venv -VenvPath ".venv32"
  }
  .\.venv32\Scripts\python.exe -m pip install -r requirements.txt
} finally {
  Pop-Location
}

try {
  Push-Location "$PSScriptRoot\..\frontend"
  npm install --cache .npm-cache
} finally {
  Pop-Location
}

Write-Host "32-bit backend setup complete."
