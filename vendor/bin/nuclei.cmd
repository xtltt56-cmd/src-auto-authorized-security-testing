@echo off
setlocal
set "SRC_AUTO_ROOT=%~dp0..\.."
if not exist "%SRC_AUTO_ROOT%\vendor\docker-state\nuclei" mkdir "%SRC_AUTO_ROOT%\vendor\docker-state\nuclei"
docker run --rm -v "%SRC_AUTO_ROOT%\vendor\docker-state\nuclei:/root/.config/nuclei" projectdiscovery/nuclei@sha256:582d5546902e67052097cb2d07296c642d50a1afc5e44623cb038845df9a32eb %*
exit /b %ERRORLEVEL%
