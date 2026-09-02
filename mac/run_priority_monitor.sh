#!/bin/zsh
set -euo pipefail
PROJECT_DIR="${0:A:h:h}"
export PYTHONPATH="$PROJECT_DIR/src"
"$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/src/run_priority_monitor.py"
cp "$PROJECT_DIR/data/priority_queue.json" "$HOME/Library/Application Support/JobMonitor/priority_queue.local.json"
