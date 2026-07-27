@echo off
REM Windows double-click entry point. Runs the PowerShell installer with a
REM relaxed execution policy so no manual setup is needed.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
echo.
pause
