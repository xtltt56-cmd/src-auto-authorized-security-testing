@echo off
setlocal
set "ZAP_HOME=%~dp0..\zap\ZAP_2.17.0"
if not exist "%ZAP_HOME%\zap.bat" exit /b 3
pushd "%ZAP_HOME%"
call "%ZAP_HOME%\zap.bat" %*
set "ZAP_EXIT=%ERRORLEVEL%"
popd
exit /b %ZAP_EXIT%
