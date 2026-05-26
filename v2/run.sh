#!/usr/bin/env bash
# Run the app using the local virtual environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

exec "$VENV/bin/python" "$SCRIPT_DIR/main.py" "$@"
