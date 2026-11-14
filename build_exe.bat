@echo off
setlocal enabledelayedexpansion
title Upstox Bridge - Standalone Windows Executable Builder

echo ==============================================================================
echo          UPSTOX TRADING BRIDGE - STANDALONE BUILD SCRIPT
echo ==============================================================================
echo.

cd /d "%~dp0"

REM 1. Detect Python or Virtual Environment
set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [OK] Using virtual environment Python: !PYTHON_EXE!
) else (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo [ERROR] Python not found. Please run install.bat first!
    pause
    exit /b 1
)

REM 2. Verify PyInstaller installation
echo [*] Checking PyInstaller...
!PYTHON_EXE! -m pip install pyinstaller customtkinter pystray Pillow --quiet

REM 3. Compile Standalone Executable
echo.
echo [*] Compiling Standalone Windows Desktop Software via PyInstaller...
echo     (This may take 1-2 minutes to package all dependencies)
echo.

!PYTHON_EXE! -m PyInstaller upstox_bridge.spec --clean --noconfirm

if errorlevel 1 (
    echo.
    echo ==============================================================================
    echo [ERROR] Build failed! Check the PyInstaller log output above.
    echo ==============================================================================
    pause
    exit /b 1
)

REM 4. Copy auxiliary files into dist\UpstoxBridge
echo.
echo [*] Copying default configuration and template files to output folder...
if not exist "dist\UpstoxBridge" mkdir "dist\UpstoxBridge"

if exist ".env" (
    copy /Y ".env" "dist\UpstoxBridge\.env" >nul
) else if exist ".env.example" (
    copy /Y ".env.example" "dist\UpstoxBridge\.env" >nul
)

if exist "bst.xlsx" copy /Y "bst.xlsx" "dist\UpstoxBridge\bst.xlsx" >nul
if exist "trial.xlsx" copy /Y "trial.xlsx" "dist\UpstoxBridge\trial.xlsx" >nul
if exist "watchlist.txt" copy /Y "watchlist.txt" "dist\UpstoxBridge\watchlist.txt" >nul

echo.
echo ==============================================================================
echo [SUCCESS] Standalone Desktop Application Built Successfully!
echo ==============================================================================
echo  Executable location:
echo    dist\UpstoxBridge\UpstoxBridge.exe
echo.
echo  You can copy or zip the entire 'dist\UpstoxBridge' folder to any Windows
echo  PC and double-click 'UpstoxBridge.exe' to run without installing Python!
echo ==============================================================================
echo.
pause
