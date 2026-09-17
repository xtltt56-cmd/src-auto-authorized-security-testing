@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\stop_dashboard.ps1" %*
if errorlevel 1 pause
exit /b %ERRORLEVEL%
