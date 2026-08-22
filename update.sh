#!/usr/bin/env bash
set -e

# Change directory to the folder where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if command -v python3 &>/dev/null; then
    python3 update.py
elif command -v python &>/dev/null; then
    python update.py
else
    echo "[ERROR] Python 3 is not installed or not in PATH."
    exit 1
fi
