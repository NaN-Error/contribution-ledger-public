@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\test.ps1"
if errorlevel 1 (
  echo.
  echo Test or dependency installation failed. Keep the error; do not reset application data.
  pause
  exit /b 1
)
echo.
echo Source and container tests finished. Native database, actual browser and human checks remain separate.
pause
