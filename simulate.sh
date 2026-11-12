#!/usr/bin/env bash
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "[ERROR] Virtual environment not found. Please run ./install.sh first."
    exit 1
fi

.venv/bin/python main.py simulate "$@"
