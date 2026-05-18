@echo off
setlocal enabledelayedexpansion
title VaultISO27 — Setup

cls
echo.
echo  ============================================================
echo   VaultISO27  --  ISO 27001:2022 Document Generator
echo   On-Premises  ^|  No Cloud  ^|  Local AI
echo  ============================================================
echo.
echo  This installer will:
echo    1. Verify Python 3.9+
echo    2. Create a Python virtual environment
echo    3. Install required packages  (~500 MB, needs internet)
echo    4. Build the ISO 27001 knowledge base  (~90 MB, needs internet)
echo    5. Pull the AI models via Ollama  (~3.3 GB, needs internet)
echo.
echo  After first setup the tool runs 100%% offline.
echo  ============================================================
echo.
pause

set "SCRIPT_DIR=%~dp0"
set "VENV=%SCRIPT_DIR%.venv"

:: ─────────────────────────────────────────────────────────────
:: STEP 1 — Check Python 3.9+
:: ─────────────────────────────────────────────────────────────
echo.
echo  [STEP 1/5]  Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python was not found on PATH.
    echo.
    echo  Install Python 3.9 or higher from:
    echo    https://python.org/downloads
    echo.
    echo  During installation, tick "Add Python to PATH".
    echo  Then run install.bat again.
    echo.
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  [OK]  Python %PYVER%

:: ─────────────────────────────────────────────────────────────
:: STEP 2 — Virtual environment
:: ─────────────────────────────────────────────────────────────
echo.
echo  [STEP 2/5]  Setting up virtual environment...
if not exist "%VENV%\Scripts\activate.bat" (
    python -m venv "%VENV%"
    if errorlevel 1 (
        echo.
        echo  ERROR: Could not create virtual environment.
        echo  Make sure the venv module is available: python -m ensurepip
        echo.
        pause & exit /b 1
    )
    echo  [OK]  Virtual environment created
) else (
    echo  [OK]  Virtual environment already exists
)
call "%VENV%\Scripts\activate.bat"

:: ─────────────────────────────────────────────────────────────
:: STEP 3 — Install packages
:: ─────────────────────────────────────────────────────────────
echo.
echo  [STEP 3/5]  Installing Python packages...
echo              (first run: ~500 MB download, 5-10 minutes)
echo.
python -m pip install --upgrade pip --quiet
python -m pip install torch==2.4.1+cpu --index-url https://download.pytorch.org/whl/cpu --quiet
python -m pip install -r "%SCRIPT_DIR%requirements.txt"
if errorlevel 1 (
    echo.
    echo  ERROR: Package installation failed.
    echo  - Check your internet connection
    echo  - Try running install.bat again
    echo  - If the error persists, check requirements.txt for version conflicts
    echo.
    pause & exit /b 1
)
echo.
echo.
echo  [OK]  Packages installed

:: ─────────────────────────────────────────────────────────────
:: STEP 3b — Detect hardware and configure settings
:: ─────────────────────────────────────────────────────────────
echo.
echo  [STEP 3b]  Detecting hardware and configuring settings...
echo.
python "%SCRIPT_DIR%setup_config.py"
if errorlevel 1 (
    echo.
    echo  WARNING: Hardware detection failed. Default settings will be used.
    echo  You can manually adjust settings in Settings ^> AI Engine.
    echo.
)

:: ─────────────────────────────────────────────────────────────
:: STEP 4 — Build knowledge base
:: ─────────────────────────────────────────────────────────────
echo.
echo  [STEP 4/5]  Building ISO 27001 knowledge base...
echo              (downloads embedding model ~90 MB on first run)
echo.
python "%SCRIPT_DIR%rag_setup.py"
if errorlevel 1 (
    echo.
    echo  ERROR: Knowledge base build failed.
    echo  - Make sure rag\ISO27001_Audit_Checklist_V3.xlsx exists
    echo  - Try running:  python rag_setup.py --force
    echo.
    pause & exit /b 1
)
echo.
echo  [OK]  Knowledge base ready

:: ─────────────────────────────────────────────────────────────
:: STEP 5 — Ollama AI engine
:: ─────────────────────────────────────────────────────────────
echo.
echo  [STEP 5/5]  Checking Ollama AI engine...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [!]  Ollama is not installed on this machine.
    echo.
    echo       Download and install Ollama from:
    echo         https://ollama.com/download
    echo.
    echo       After installing, open a new terminal and run:
    echo         ollama pull phi4-mini:3.8b-q4_K_M   (document generator, ~2.4 GB)
    echo         ollama pull qwen2.5:1.5b              (AI reviewer, ~0.9 GB)
    echo.
    echo       Then run launch.bat to start the dashboard.
    echo.
) else (
    for /f "tokens=*" %%v in ('ollama --version 2^>^&1') do echo  [OK]  %%v
    echo.
    echo  Pulling document generator model  (phi4-mini:3.8b-q4_K_M, ~2.4 GB)
    echo  Press Ctrl+C to skip and pull models manually later.
    echo.
    ollama pull phi4-mini:3.8b-q4_K_M
    echo.
    echo  Pulling AI reviewer model  (qwen2.5:1.5b, ~0.9 GB)
    ollama pull qwen2.5:1.5b
    echo.
    echo  [OK]  AI models ready
)

:: ─────────────────────────────────────────────────────────────
:: First-run: create blank organization profile
:: ─────────────────────────────────────────────────────────────
if not exist "%SCRIPT_DIR%inputs\organization_data.json" (
    if exist "%SCRIPT_DIR%inputs\organization_data_default.json" (
        copy /Y "%SCRIPT_DIR%inputs\organization_data_default.json" "%SCRIPT_DIR%inputs\organization_data.json" >nul
    )
)

:: ─────────────────────────────────────────────────────────────
:: Optional: Desktop shortcut
:: ─────────────────────────────────────────────────────────────
echo.
echo  ============================================================
set /p "SHORTCUT=  Create a Desktop shortcut to launch VaultISO27? [Y/N]: "
if /i "!SHORTCUT!"=="Y" (
    powershell -NoProfile -Command ^
        "$s=(New-Object -COM WScript.Shell).CreateShortcut('%USERPROFILE%\Desktop\VaultISO27.lnk');" ^
        "$s.TargetPath='%SCRIPT_DIR%launch.bat';" ^
        "$s.WorkingDirectory='%SCRIPT_DIR%';" ^
        "$s.IconLocation='%SCRIPT_DIR%icon.ico,0';" ^
        "$s.Description='VaultISO27 ISO 27001:2022 Document Generator';" ^
        "$s.Save()"
    echo  [OK]  Desktop shortcut created
)

:: ─────────────────────────────────────────────────────────────
:: Done
:: ─────────────────────────────────────────────────────────────
echo.
echo  ============================================================
echo   Setup complete!
echo.
echo   NEXT STEPS:
echo     1. Double-click  launch.bat  (or the Desktop shortcut)
echo     2. Your browser opens at  http://localhost:8501
echo     3. Go to Settings -- upload your company profile document
echo     4. Generate your ISO 27001 documents
echo.
echo   The tool runs fully offline after this first setup.
echo  ============================================================
echo.
pause
