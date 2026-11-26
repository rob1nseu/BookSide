@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0BookSide.ps1" %*
set "booksideExit=%errorlevel%"
if not "%booksideExit%"=="0" pause
exit /b %booksideExit%
