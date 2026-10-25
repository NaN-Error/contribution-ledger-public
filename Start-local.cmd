@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Do not delete your database volume or .env file.
  echo Keep the error shown above and read docs\user-guide\start_here.md.
  pause
  exit /b 1
)
echo.
echo First installation only: run scripts\setup-owner.ps1 and finish the owner form.
echo Existing users should sign in normally.
pause
