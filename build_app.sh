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
echo "[*] Compiling Standalone Application via PyInstaller..."

$PYTHON_BIN -m PyInstaller upstox_bridge.spec --clean --noconfirm

echo "[*] Copying configuration assets to dist/UpstoxBridge..."
if [ -f ".env" ]; then
    cp -f ".env" "dist/UpstoxBridge/.env"
fi
if [ -f "bst.xlsx" ]; then
    cp -f "bst.xlsx" "dist/UpstoxBridge/bst.xlsx"
fi
if [ -f "watchlist.txt" ]; then
    cp -f "watchlist.txt" "dist/UpstoxBridge/watchlist.txt"
fi

echo "=================================================================="
echo "[SUCCESS] Standalone Application compiled at: dist/UpstoxBridge/UpstoxBridge"
echo "=================================================================="
