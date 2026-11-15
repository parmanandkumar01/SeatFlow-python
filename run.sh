#!/usr/bin/env bash
# Runner script for SeatFlow Desktop Application

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON_EXEC="$(command -v python3)"
fi

export PYTHONPATH="$SCRIPT_DIR/src:${PYTHONPATH:-}"

echo "Starting SeatFlow..."
exec "$PYTHON_EXEC" -m seatflow.main "$@"
