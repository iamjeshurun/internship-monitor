#!/bin/zsh
set -euo pipefail
RUNTIME="${0:A:h:h}"
exec "$RUNTIME/.venv/bin/python" "$RUNTIME/mac/mail_sync.py"
