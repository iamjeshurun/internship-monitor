#!/bin/zsh
# Sync the current checkout's code into the live macOS runtime and reload the
# four Job Monitor background agents. Does NOT touch config, state, secrets, or
# the venv — run mac/install.sh if dependencies or plists changed.
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
# A private instance keeps its config in a separate repository; point at it with
# JOB_MONITOR_CONFIG_SOURCE=/path/to/private-repo/config.
CONFIG_SOURCE="${JOB_MONITOR_CONFIG_SOURCE:-$PROJECT_DIR/config}"
RUNTIME="$HOME/Library/Application Support/JobMonitor/runtime"

if [[ ! -d "$RUNTIME" ]]; then
  echo "Runtime not found at $RUNTIME — run mac/install.sh first." >&2
  exit 1
fi

echo "Syncing code into $RUNTIME"
rsync -a --delete "$PROJECT_DIR/src/" "$RUNTIME/src/"
# Shared dashboard assets (same UI as the fictional public demo).
rsync -a --delete "$PROJECT_DIR/web/" "$RUNTIME/web/"
for f in mac_agent.py dashboard.py tracker.py mail_sync.py notifier.py run_priority_monitor.sh; do
  cp "$PROJECT_DIR/mac/$f" "$RUNTIME/mac/$f"
done
# Behaviour config. Account routing and private answers are only copied from a
# private config source, never from this repository's examples.
files=(sources.yaml priority_programs.yaml resume_profile.yaml companies.yaml)
[[ -n "${JOB_MONITOR_CONFIG_SOURCE:-}" ]] && files+=(accounts.yaml)
for f in $files; do
  [[ -f "$CONFIG_SOURCE/$f" ]] && cp "$CONFIG_SOURCE/$f" "$RUNTIME/config/$f"
done
rm -rf "$RUNTIME"/src/__pycache__ "$RUNTIME"/mac/__pycache__

# The poll, mail-sync, and priority agents run the scripts fresh on every
# StartInterval fire, so they pick up the synced code on their next run with no
# reload. Only the long-lived dashboard (KeepAlive Flask) must be restarted.
echo "Restarting dashboard"
uid="$(id -u)"
launchctl kickstart -k "gui/$uid/com.jobmonitor.dashboard" 2>/dev/null \
  || { launchctl bootout "gui/$uid/com.jobmonitor.dashboard" 2>/dev/null || true
       launchctl bootstrap "gui/$uid" "$HOME/Library/LaunchAgents/com.jobmonitor.dashboard.plist" 2>/dev/null || true; }

# Optional: force an immediate run of the interval agents instead of waiting.
for label in poll mail-sync priority; do
  launchctl kickstart "gui/$uid/com.jobmonitor.$label" 2>/dev/null || true
done

echo "Done. Watch logs:"
echo "  tail -f ~/Library/Logs/job-monitor-mail.log ~/Library/Logs/job-monitor-error.log"
