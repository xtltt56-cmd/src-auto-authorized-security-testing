@echo off
setlocal
cd /d "%~dp0"
python -m src_auto status %*
exit /b %ERRORLEVEL%
