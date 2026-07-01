param(
  [string]$DownloadUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
  [string]$InstallDir = "$PSScriptRoot\..\vendor\ffmpeg\windows"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$targetDir = [System.IO.Path]::GetFullPath($InstallDir)
$binDir = Join-Path $targetDir "bin"
$ffmpegExe = Join-Path $binDir "ffmpeg.exe"
$ffprobeExe = Join-Path $binDir "ffprobe.exe"

if ((Test-Path $ffmpegExe) -and (Test-Path $ffprobeExe)) {
  Write-Host "Bundled ffmpeg already exists: $ffmpegExe"
  return
}

$downloadDir = Join-Path $repoRoot ".download"
$zipPath = Join-Path $downloadDir "ffmpeg-release-essentials.zip"
$extractDir = Join-Path $downloadDir "ffmpeg_extract"

New-Item -ItemType Directory -Force -Path $downloadDir | Out-Null
New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

Write-Host "Downloading Windows ffmpeg runtime..."
Write-Host $DownloadUrl
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $DownloadUrl -OutFile $zipPath

if (Test-Path $extractDir) {
  Remove-Item -Recurse -Force $extractDir
}
New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

Write-Host "Extracting ffmpeg runtime..."
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

$ffmpegSource = Get-ChildItem -Path $extractDir -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
$ffprobeSource = Get-ChildItem -Path $extractDir -Filter "ffprobe.exe" -Recurse | Select-Object -First 1

if (!$ffmpegSource) {
  throw "ffmpeg.exe was not found in downloaded archive."
}

New-Item -ItemType Directory -Force -Path $binDir | Out-Null
Copy-Item -Force $ffmpegSource.FullName $ffmpegExe
if ($ffprobeSource) {
  Copy-Item -Force $ffprobeSource.FullName $ffprobeExe
}

$licenseFiles = Get-ChildItem -Path $extractDir -Include "LICENSE*", "COPYING*", "README*" -File -Recurse
foreach ($licenseFile in $licenseFiles) {
  Copy-Item -Force $licenseFile.FullName (Join-Path $targetDir $licenseFile.Name)
}

Write-Host "Bundled ffmpeg installed:"
& $ffmpegExe -version | Select-Object -First 1
Write-Host $ffmpegExe
