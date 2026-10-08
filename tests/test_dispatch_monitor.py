import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mac"))
from dispatch_monitor import should_dispatch

NOW = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)


def test_dispatches_when_latest_run_is_older_than_target():
    runs = [{"createdAt": "2026-10-08T17:30:00Z", "status": "completed"}]
    assert should_dispatch(runs, NOW, 115)


def test_waits_while_a_recent_run_exists():
    runs = [
        {"createdAt": "2026-10-08T18:30:00Z", "status": "completed"},
        {"createdAt": "2026-10-08T12:00:00Z", "status": "completed"},
    ]
    assert not should_dispatch(runs, NOW, 115)


def test_never_stacks_a_second_run_behind_a_pending_one():
    runs = [{"createdAt": "2026-10-08T10:00:00Z", "status": "queued"}]
    assert not should_dispatch(runs, NOW, 115)


def test_dispatches_when_no_run_has_happened():
    assert should_dispatch([], NOW, 115)
