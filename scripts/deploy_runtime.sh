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
for f in sources.yaml resume_profile.yaml companies.yaml; do
  cp "$PROJECT_DIR/config/$f" "$RUNTIME/config/$f"
done
rm -rf "$RUNTIME"/src/__pycache__ "$RUNTIME"/mac/__pycache__

# The poll and mail-sync agents run the scripts fresh on every
# StartInterval fire, so they pick up the synced code on their next run with no
# reload. Only the long-lived dashboard (KeepAlive Flask) must be restarted.
echo "Restarting dashboard"
uid="$(id -u)"
launchctl kickstart -k "gui/$uid/com.jobmonitor.dashboard" 2>/dev/null \
  || { launchctl bootout "gui/$uid/com.jobmonitor.dashboard" 2>/dev/null || true
       launchctl bootstrap "gui/$uid" "$HOME/Library/LaunchAgents/com.jobmonitor.dashboard.plist" 2>/dev/null || true; }

# Optional: force an immediate run of the interval agents instead of waiting.
for label in poll mail-sync; do
  launchctl kickstart "gui/$uid/com.jobmonitor.$label" 2>/dev/null || true
done

echo "Done. Watch logs:"
echo "  tail -f ~/Library/Logs/job-monitor-mail.log ~/Library/Logs/job-monitor-error.log"
