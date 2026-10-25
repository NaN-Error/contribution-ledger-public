@echo off
setlocal
cd /d "%~dp0"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\portable.ps1" -Action start %*
if errorlevel 1 (
  echo.
  echo Startup could not finish. Your saved data has been kept.
  echo Read the message above and QUICK-START.txt. Do not delete your data folder.
  pause
  exit /b 1
)
