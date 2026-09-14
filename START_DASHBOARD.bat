@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0START_SYSTEM.ps1" -Dashboard
if errorlevel 1 pause
exit /b %ERRORLEVEL%
