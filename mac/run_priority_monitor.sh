#!/bin/zsh
set -euo pipefail
PROJECT_DIR="${0:A:h:h}"
export PYTHONPATH="$PROJECT_DIR/src"
exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/src/run_priority_monitor.py"
