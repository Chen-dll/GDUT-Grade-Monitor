@echo off
setlocal
set "SCRIPT=%~dp0cleanup_residue.ps1"
if not exist "%SCRIPT%" (
  set "SCRIPT=%~dp0GDUTGradeMonitor-Cleanup.ps1"
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
endlocal
