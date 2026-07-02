param(
  [switch]$SkipBuild,
  [switch]$SkipFfmpeg
)

$ErrorActionPreference = "Stop"

if ($PSVersionTable.Platform -and $PSVersionTable.Platform -ne "Win32NT") {
  throw "This initialization script is intended for Windows PowerShell."
}

$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$venvDir = Join-Path $backendDir ".venv32"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-Command {
  param([string]$Name)
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  return $null -ne $command
}

function New-X86Venv {
  param([string]$VenvPath)

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
  .\scripts\init_windows.ps1
"@
}

Write-Step "Checking required tools"
if (!(Test-Command "node")) {
  throw "Node.js was not found. Install Node.js LTS for Windows, then rerun .\scripts\init_windows.ps1."
}
if (!(Test-Command "npm")) {
  throw "npm was not found. Install Node.js LTS for Windows, then rerun .\scripts\init_windows.ps1."
}
if (!(Test-Command "py") -and !$env:MRC_PYTHON32) {
  throw "Python launcher 'py' was not found. Install Windows x86 Python 3.10, or set MRC_PYTHON32 to python.exe."
}

node --version
npm --version

if (!$SkipFfmpeg) {
  Write-Step "Installing bundled ffmpeg"
  try {
    & "$PSScriptRoot\setup_ffmpeg_windows.ps1"
  } catch {
    Write-Warning "Bundled ffmpeg setup failed: $($_.Exception.Message)"
    Write-Warning "Initialization will continue. Trigger recording can run, but aligned trimming and check-frame extraction need ffmpeg."
  }
}

Write-Step "Preparing 32-bit Python backend environment"
Push-Location $backendDir
try {
  if (!(Test-Path $pythonExe)) {
    if (Test-Path $venvDir) {
      Write-Warning "Existing .venv32 does not contain Scripts\python.exe. Recreating it."
      Remove-Item -Recurse -Force $venvDir
    }
    New-X86Venv -VenvPath ".venv32"
  }

  & $pythonExe -m pip install --upgrade pip
  & $pythonExe -m pip install -r requirements.txt
} finally {
  Pop-Location
}

Write-Step "Installing Electron/Vue dependencies"
Push-Location $frontendDir
try {
  npm install --cache .npm-cache
  if (!$SkipBuild) {
    Write-Step "Verifying frontend and Electron build"
    npm run build
  }
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "Initialization complete." -ForegroundColor Green
Write-Host "Start the app with:"
Write-Host "  .\scripts\run_windows.ps1"
