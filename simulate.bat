@echo off
setlocal
cd /d "%~dp0"
title Upstox Bridge - Simulation Mode

if not exist ".venv\Scripts\python.exe" (
    echo ==============================================================================
    echo [ERROR] Virtual environment not found!
    echo ==============================================================================
    echo It looks like the project has not been installed yet.
    echo Please double-click 'install.bat' to automatically set up the environment.
    echo ==============================================================================
    echo.
    pause
    exit /b 1
)

echo ==============================================================================
echo              UPSTOX BRIDGE - SIMULATION MODE [TESTING]
echo ==============================================================================
echo  - Simulating live market ticks without needing Upstox API keys
echo  - Updating local Excel: data\Upstox_Live_Market.xlsx
echo  - Updating Google Sheets [if GOOGLE_SHEET_WEBHOOK_URL is set in .env]
echo.
echo  Press Ctrl+C in this window at any time to stop simulation.
echo ==============================================================================
echo.

call .venv\Scripts\python.exe main.py simulate %*

if errorlevel 1 (
    echo.
    echo ==============================================================================
    echo Simulation stopped with code %ERRORLEVEL%.
    echo ==============================================================================
    pause
)
