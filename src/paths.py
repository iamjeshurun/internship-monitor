"""Where configuration and runtime data live.

Defaults to this repository's config/ and data/ folders. A private instance sets
JOB_MONITOR_CONFIG_DIR and JOB_MONITOR_DATA_DIR to its own folders, so personal
configuration and job history never need to live in this repository.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("JOB_MONITOR_CONFIG_DIR") or ROOT / "config")
DATA_DIR = Path(os.environ.get("JOB_MONITOR_DATA_DIR") or ROOT / "data")
