#!/usr/bin/env bash
# macOS Build script for Upstox Bridge Standalone Application
set -e

cd "$(dirname "$0")"

echo "=================================================================="
echo "    UPSTOX TRADING BRIDGE - STANDALONE MACOS BUILD SCRIPT"
echo "=================================================================="

PYTHON_BIN=".venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

echo "[*] Using Python: $($PYTHON_BIN --version)"
echo "[*] Compiling Standalone Executable via PyInstaller..."

$PYTHON_BIN -m PyInstaller upstox_bridge.spec --clean --noconfirm

# Remove intermediate build folder
if [ -d "build" ]; then
    rm -rf build
fi

echo "[*] Copying configuration assets to dist..."
mkdir -p dist
if [ -f ".env" ]; then
    cp -f ".env" "dist/.env"
elif [ -f ".env.example" ]; then
    cp -f ".env.example" "dist/.env"
fi
if [ -f "bst.xlsx" ]; then
    cp -f "bst.xlsx" "dist/bst.xlsx"
fi
if [ -f "trial.xlsx" ]; then
    cp -f "trial.xlsx" "dist/trial.xlsx"
fi
if [ -f "watchlist.txt" ]; then
    cp -f "watchlist.txt" "dist/watchlist.txt"
fi

if [ -f "dist/UpstoxBridge" ]; then
    chmod +x dist/UpstoxBridge || true
fi

echo "=================================================================="
echo "[SUCCESS] Standalone Executable compiled at: dist/UpstoxBridge"
echo "  Run it in Terminal with: ./dist/UpstoxBridge"
echo "=================================================================="
