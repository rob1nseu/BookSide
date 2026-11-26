@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "learnestExit=%errorlevel%"
if not "%learnestExit%"=="0" pause
exit /b %learnestExit%
