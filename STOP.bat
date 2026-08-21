@echo off
setlocal
cd /d "%~dp0"
python -m src_auto stop --run-id "%~1"
exit /b %ERRORLEVEL%
