@echo off
setlocal
set "PYTHONIOENCODING=utf-8"
if "%~1"=="" (
  echo 用法：START.bat RUN_ID
  echo 请先创建运行记录：python -m src_auto new --target-id local-lab --scope config\targets\local-lab\scope_confirmed.yaml --mode local --json
  exit /b 2
)
cd /d "%~dp0"
python -m src_auto run --run-id "%~1" --scope config\targets\local-lab\scope_confirmed.yaml --local-lab
exit /b %ERRORLEVEL%
