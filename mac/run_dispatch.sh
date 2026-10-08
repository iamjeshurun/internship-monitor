#!/bin/zsh
set -euo pipefail
PROJECT_DIR="${0:A:h:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/mac/dispatch_monitor.py"
