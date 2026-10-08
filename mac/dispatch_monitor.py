"""Start the cloud monitor when GitHub's scheduler falls behind.

GitHub delays scheduled workflows on quiet repositories, so a "every two hours"
cron can run only every six to nine hours. This agent checks the private
repository every ten minutes and dispatches the workflow once the latest run is
older than the target interval. The cron schedule stays as the fallback while
the Mac is asleep. Uses the GitHub CLI's own login, which needs the `workflow`
scope; the read-only token used by the notification agent is not involved.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_FILE = Path.home() / "Library/Application Support/JobMonitor/github_repo"
WORKFLOW = os.environ.get("JOB_MONITOR_WORKFLOW", "monitor.yml")
MAX_AGE_MINUTES = float(os.environ.get("JOB_MONITOR_MAX_AGE_MINUTES", "115"))


def should_dispatch(runs: list[dict], now: datetime, max_age_minutes: float = MAX_AGE_MINUTES) -> bool:
    """True when no run is pending and the newest run started too long ago."""
    if any(run.get("status") in {"queued", "in_progress", "waiting", "requested", "pending"} for run in runs):
        return False
    started = [
        datetime.fromisoformat(run["createdAt"].replace("Z", "+00:00"))
        for run in runs
        if run.get("createdAt")
    ]
    if not started:
        return True
    return (now - max(started)).total_seconds() / 60 >= max_age_minutes


def gh(*args: str) -> str:
    binary = shutil.which("gh") or str(Path.home() / ".local/bin/gh")
    return subprocess.run([binary, *args], check=True, capture_output=True, text=True, timeout=60).stdout


def main() -> int:
    repo = os.environ.get("JOB_MONITOR_GITHUB_REPO") or (
        REPO_FILE.read_text().strip() if REPO_FILE.exists() else ""
    )
    if not repo:
        print(f"Missing {REPO_FILE}", file=sys.stderr)
        return 2
    runs = json.loads(gh("run", "list", "-R", repo, "-w", WORKFLOW, "-L", "5", "--json", "createdAt,status"))
    now = datetime.now(timezone.utc)
    if not should_dispatch(runs, now):
        return 0
    gh("workflow", "run", WORKFLOW, "-R", repo)
    print(f"{now.isoformat(timespec='seconds')} dispatched {WORKFLOW} on {repo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
