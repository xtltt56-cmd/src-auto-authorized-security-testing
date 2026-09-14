@echo off
setlocal
set "SRC_AUTO_ROOT=%~dp0..\.."
if not exist "%SRC_AUTO_ROOT%\vendor\docker-state\testssl" mkdir "%SRC_AUTO_ROOT%\vendor\docker-state\testssl"
docker run --rm -v "%SRC_AUTO_ROOT%\vendor\docker-state\testssl:/data" ghcr.io/testssl/testssl.sh@sha256:47d623064463c66ce3b02d37486c75dd1bff8fcef0d9947b37a5051b937ccd69 %*
exit /b %ERRORLEVEL%
