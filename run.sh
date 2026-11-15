#!/usr/bin/env bash
# Runner script for Bingo Linux Desktop Application

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON_EXEC="$(command -v python3)"
fi

export PYTHONPATH="$SCRIPT_DIR/src:${PYTHONPATH:-}"

echo "Starting Bingo Linux..."
exec "$PYTHON_EXEC" -m bingo_linux.main "$@"
