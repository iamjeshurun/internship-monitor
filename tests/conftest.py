"""Make ``src`` and ``mac`` importable regardless of which tests run."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for sub in ("src", "mac"):
    path = str(ROOT / sub)
    if path not in sys.path:
        sys.path.insert(0, path)
