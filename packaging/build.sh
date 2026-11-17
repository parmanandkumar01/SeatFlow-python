#!/usr/bin/env bash
# One-click compiler script for SeatFlow Standalone Executable
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_EXEC="$ROOT_DIR/.venv/bin/python"
else
    PYTHON_EXEC="$(command -v python3)"
fi

echo "=========================================="
echo "SeatFlow Standalone Binary Compiler"
echo "Python: $PYTHON_EXEC"
echo "=========================================="

# Check if PyInstaller is installed
if ! "$PYTHON_EXEC" -c "import PyInstaller" &>/dev/null; then
    echo "Installing PyInstaller..."
    "$PYTHON_EXEC" -m pip install "pyinstaller>=6.0.0"
fi

# Run build script
"$PYTHON_EXEC" packaging/build_binary.py "$@"
