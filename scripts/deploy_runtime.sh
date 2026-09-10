#!/bin/zsh
# Sync the current checkout's code into the live macOS runtime and reload the
# four Job Monitor background agents. Does NOT touch config, state, secrets, or
# the venv — run mac/install.sh if dependencies or plists changed.
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
RUNTIME="$HOME/Library/Application Support/JobMonitor/runtime"

if [[ ! -d "$RUNTIME" ]]; then
  echo "Runtime not found at $RUNTIME — run mac/install.sh first." >&2
  exit 1
fi

echo "Syncing code into $RUNTIME"
rsync -a --delete "$PROJECT_DIR/src/" "$RUNTIME/src/"
for f in mac_agent.py dashboard.py tracker.py mail_sync.py notifier.py; do
  cp "$PROJECT_DIR/mac/$f" "$RUNTIME/mac/$f"
done
# Behaviour config tracked with the code. Account routing and private answers
# are never overwritten.
for f in sources.yaml priority_programs.yaml resume_profile.yaml companies.yaml; do
  cp "$PROJECT_DIR/config/$f" "$RUNTIME/config/$f"
done
rm -rf "$RUNTIME"/src/__pycache__ "$RUNTIME"/mac/__pycache__

echo "Reloading agents"
for label in poll dashboard mail-sync priority; do
  plist="$HOME/Library/LaunchAgents/com.jobmonitor.$label.plist"
  launchctl bootout "gui/$(id -u)/com.jobmonitor.$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
done

echo "Done. Watch logs:"
echo "  tail -f ~/Library/Logs/job-monitor-mail.log ~/Library/Logs/job-monitor-error.log"
