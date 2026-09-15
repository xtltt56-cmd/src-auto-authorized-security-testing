@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\check_update.ps1" -OpenLatest
set "SRC_AUTO_EXIT=%ERRORLEVEL%"
if "%SRC_AUTO_EXIT%"=="10" set "SRC_AUTO_EXIT=0"
pause
exit /b %SRC_AUTO_EXIT%
