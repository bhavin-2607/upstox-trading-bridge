@echo off
setlocal
title Upstox Trading Bridge - Windows Installer

echo ==============================================================================
echo           UPSTOX TRADING BRIDGE - ONE-CLICK WINDOWS INSTALLER
echo ==============================================================================
echo.

cd /d "%~dp0"

REM 1. Detect Python command
set "PYTHON_CMD="

python --version >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
    py --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD (
    echo ==============================================================================
    echo [ERROR] Python is not installed or not in your system PATH!
    echo ==============================================================================
    echo.
    echo Please download and install Python 3.10, 3.11, or 3.12 from:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANT: Make sure to check the box:
    echo   [X] Add python.exe to PATH
    echo at the bottom of the Python installer setup window before clicking Install.
    echo.
    pause
    exit /b 1
)

echo [OK] Python detected:
%PYTHON_CMD% --version
echo.

REM 2. Create Virtual Environment
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating isolated virtual environment in .venv folder...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment!
        echo Please ensure you have write permissions in this folder.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created successfully.
) else (
    echo [OK] Virtual environment already exists in .venv folder.
)
echo.

REM 3. Upgrade pip and install dependencies
echo [*] Installing required Python packages...
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to install required packages from requirements.txt!
    echo Please check your internet connection and try running install.bat again.
    pause
    exit /b 1
)
echo [OK] All dependencies installed successfully.
echo.

REM 4. Setup .env file
if not exist ".env" (
    echo [*] Creating .env file from .env.example...
    copy .env.example .env >nul
    echo [OK] .env file created.
    echo [NOTE] Remember to open .env in Notepad and paste your UPSTOX_ACCESS_TOKEN.
) else (
    echo [OK] .env file already exists.
)
echo.

REM 5. Generate Excel Template
echo [*] Initializing Excel template workbook...
call .venv\Scripts\python.exe main.py create-template
echo.

echo ==============================================================================
echo                           INSTALLATION COMPLETE!
echo ==============================================================================
echo.
echo WHAT TO DO NEXT:
echo.
echo 1. Open .env in Notepad:
echo    - Paste your UPSTOX_ACCESS_TOKEN [from developer.upstox.com]
echo    - Optional: Paste GOOGLE_SHEET_WEBHOOK_URL if streaming to Google Sheets
echo.
echo 2. Open watchlist.txt in Notepad:
echo    - Add or remove symbols [one symbol per line, e.g. NIFTY 50, GOLD DEC FUT]
echo.
echo 3. Double-click run.bat to start the live market data bridge!
echo.
echo    Tip: You can also double-click simulate.bat anytime to test Excel and
echo         Google Sheets updates outside market hours.
echo ==============================================================================
echo.
pause
