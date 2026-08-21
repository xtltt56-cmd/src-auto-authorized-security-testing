@echo off
setlocal
if "%~1"=="" (
  echo Usage: START.bat RUN_ID
  echo Create a run first with: python -m src_auto new --target-id local-lab --scope config\targets\local-lab\scope_confirmed.yaml --mode local
  exit /b 2
)
cd /d "%~dp0"
python -m src_auto run --run-id "%~1" --scope config\targets\local-lab\scope_confirmed.yaml --local-lab
exit /b %ERRORLEVEL%
