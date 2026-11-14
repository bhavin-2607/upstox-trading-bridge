@echo off
setlocal enabledelayedexpansion
title Upstox Bridge - Standalone Windows Single-File Builder

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

REM 3. Compile Standalone Single-File Executable
echo.
echo [*] Compiling Standalone Windows Single-File Executable via PyInstaller...
echo     (Embedding Python runtime, python3XX.dll, and all dependencies into one file)
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

REM 4. Clean up intermediate build scratch folder so users never open it by mistake
if exist "build" (
    echo [*] Removing intermediate build cache folder...
    rmdir /s /q "build"
)

REM 5. Copy auxiliary configuration files alongside dist\UpstoxBridge.exe
echo.
echo [*] Copying configuration and workbook files to dist folder...
if not exist "dist" mkdir "dist"

if exist ".env" (
    copy /Y ".env" "dist\.env" >nul
) else if exist ".env.example" (
    copy /Y ".env.example" "dist\.env" >nul
)

if exist "bst.xlsx" copy /Y "bst.xlsx" "dist\bst.xlsx" >nul
if exist "trial.xlsx" copy /Y "trial.xlsx" "dist\trial.xlsx" >nul
if exist "watchlist.txt" copy /Y "watchlist.txt" "dist\watchlist.txt" >nul

echo.
echo ==============================================================================
echo [SUCCESS] Standalone Single-File Executable Built Successfully!
echo ==============================================================================
echo  Executable location:
echo    dist\UpstoxBridge.exe
echo.
echo  This is a 100%% self-contained single executable. All Python DLLs and
echo  libraries are embedded inside. You can copy 'dist\UpstoxBridge.exe'
echo  and 'dist\.env' to any Windows PC and double-click to run!
echo ==============================================================================
echo.
pause
