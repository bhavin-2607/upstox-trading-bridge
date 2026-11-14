@echo off
setlocal
cd /d "%~dp0"
title Upstox Bridge - Desktop Dashboard

if not exist ".venv\Scripts\python.exe" (
    echo ==============================================================================
    echo [ERROR] Virtual environment not found!
    echo ==============================================================================
    echo Please double-click 'install.bat' first to set up the environment.
    echo ==============================================================================
    pause
    exit /b 1
)

start "" .venv\Scripts\python.exe main.py gui
