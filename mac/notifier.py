from __future__ import annotations

import os
import subprocess
from pathlib import Path

LOCAL = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home() / "Library/Application Support/JobMonitor"))
NOTIFIER = LOCAL / "tools/terminal-notifier.app/Contents/MacOS/terminal-notifier"
DASHBOARD = "http://127.0.0.1:8765"


def notify(title: str, message: str, subtitle: str = "", url: str = DASHBOARD):
    if NOTIFIER.exists():
        command = [str(NOTIFIER), "-title", title, "-message", message, "-sound", "Glass", "-open", url]
        if subtitle:
            command += ["-subtitle", subtitle]
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            return result
    safe_title, safe_message, safe_subtitle = (
        value.replace('"', "'") for value in (title, message, subtitle)
    )
    suffix = f' subtitle "{safe_subtitle}"' if safe_subtitle else ""
    return subprocess.run(
        [
            "osascript",
            "-e",
            f'display notification "{safe_message}" with title "{safe_title}"{suffix} sound name "Glass"',
        ],
        check=False,
    )
