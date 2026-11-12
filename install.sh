#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=============================================================================="
echo "          UPSTOX TRADING BRIDGE - ONE-CLICK INSTALLER (macOS / Linux)"
echo "=============================================================================="
echo ""

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in PATH."
    echo "Please install Python 3.10+ from https://www.python.org/downloads/"
    exit 1
fi

echo "[OK] Python detected: $(python3 --version)"

if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "[OK] Virtual environment already exists."
fi

echo "[*] Installing dependencies..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if [ ! -f ".env" ]; then
    echo "[*] Creating .env file from .env.example..."
    cp .env.example .env
    echo "[!] Please configure your UPSTOX_ACCESS_TOKEN in .env"
fi

echo "[*] Generating Excel template..."
.venv/bin/python main.py create-template

chmod +x run.sh simulate.sh 2>/dev/null || true

echo ""
echo "=============================================================================="
echo "INSTALLATION COMPLETE!"
echo "1. Edit .env with your UPSTOX_ACCESS_TOKEN"
echo "2. Edit watchlist.txt with your symbols"
echo "3. Run './run.sh' or 'python3 main.py run' to start!"
echo "=============================================================================="
