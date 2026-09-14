@echo off
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "TERM=dumb"
"%~dp0..\pytools\schemathesis\Scripts\schemathesis.exe" %*
exit /b %ERRORLEVEL%
