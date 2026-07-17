@echo off
rem Double-click to run run_windows.ps1 elevated (UAC prompt appears).
rem Edit PS_SCRIPT below if this bat is not next to run_windows.ps1.

set "PS_SCRIPT=%~dp0run_windows.ps1"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-NoExit','-File','%PS_SCRIPT%'"
