@echo off
setlocal
set "SRC_AUTO_ROOT=%~dp0..\.."
if not exist "%SRC_AUTO_ROOT%\vendor\docker-state\bbot\scans" mkdir "%SRC_AUTO_ROOT%\vendor\docker-state\bbot\scans"
if not exist "%SRC_AUTO_ROOT%\vendor\docker-state\bbot\config" mkdir "%SRC_AUTO_ROOT%\vendor\docker-state\bbot\config"
docker run --rm -v "%SRC_AUTO_ROOT%\vendor\docker-state\bbot\scans:/root/.bbot/scans" -v "%SRC_AUTO_ROOT%\vendor\docker-state\bbot\config:/root/.config/bbot" blacklanternsecurity/bbot@sha256:0b5c3904e3f3f270e8cd31dd84655317de28064bc380d7fa1fd9b78a7d89a47e %*
exit /b %ERRORLEVEL%
