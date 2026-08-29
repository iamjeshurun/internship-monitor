#!/bin/zsh
set -euo pipefail
PROJECT_DIR="${0:A:h:h}"
REPO_FILE="$HOME/Library/Application Support/JobMonitor/github_repo"
if [[ ! -f "$REPO_FILE" ]]; then echo "Missing $REPO_FILE" >&2; exit 2; fi
export JOB_MONITOR_GITHUB_REPO="$(<"$REPO_FILE")"
export JOB_MONITOR_GITHUB_TOKEN="$(security find-generic-password -a "$USER" -s job-monitor-github-token -w)"
exec "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/mac/mac_agent.py"
