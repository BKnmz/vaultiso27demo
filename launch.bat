@echo off
setlocal
title VaultISO27 Demo

:: Guard — make sure install.bat has been run
if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo  ERROR: Virtual environment not found.
    echo  Please run install.bat first to set up VaultISO27 Demo.
    echo.
    pause & exit /b 1
)

:: Kill any previous instance on port 8502
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8502" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

call .venv\Scripts\activate.bat
python launch.py
pause
