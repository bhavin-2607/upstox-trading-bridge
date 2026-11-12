@echo off
setlocal
cd /d "%~dp0"
title Upstox Live Market Data Bridge

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
echo                 UPSTOX LIVE MARKET DATA BRIDGE
echo ==============================================================================
echo  - Streaming active symbols from: watchlist.txt
echo  - Updating local Excel: data\Upstox_Live_Market.xlsx
echo  - Local HTTP Feed: http://127.0.0.1:8080/live.csv
echo.
echo  Press Ctrl+C in this window at any time to safely stop.
echo ==============================================================================
echo.

call .venv\Scripts\python.exe main.py run %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo ==============================================================================
    echo Bridge stopped with error code %ERRORLEVEL%.
    echo Check the error message above or verify your UPSTOX_ACCESS_TOKEN in .env.
    echo ==============================================================================
    pause
)
