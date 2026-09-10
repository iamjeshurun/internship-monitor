from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/"src"))
from email_history import apple_mail, parse_mail_date
from tracker import event_key, load_json
from notifier import notify as native_notify

LOCAL = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
HISTORY = LOCAL/"application_history.json"
HEALTH = LOCAL/"mail_health.json"
ACCOUNTS = [x.strip() for x in os.environ.get("JOB_MONITOR_MAIL_ACCOUNTS", "you@example.com,second.account@example.com,school.account@example.edu").split(",") if x.strip()]
# Each run scans a short window (fast); prior events are merged forward and only
# retired once they age out, so history is not lost when a window is small.
SCAN_DAYS = int(os.environ.get("JOB_MONITOR_MAIL_DAYS", "21"))
RETAIN_DAYS = int(os.environ.get("JOB_MONITOR_MAIL_RETAIN_DAYS", "365"))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_ts(event: dict) -> str:
    return event.get("date_iso") or parse_mail_date(event.get("date")) or ""


def event_age_days(event: dict) -> float:
    iso = event_ts(event)
    if not iso:
        return 0.0  # unknown age -> keep
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 86400


def notify(event):
    title = f"Application update — {event.get('stage','update').title()}"
    message = event.get("subject") or event.get("company_hint") or "New mailbox update"
    native_notify(title, message)


def main():
    LOCAL.mkdir(parents=True, exist_ok=True)
    previous = load_json(HISTORY, {"applications": []}).get("applications", [])
    known = {event_key(event) for event in previous}
    prior_health = load_json(HEALTH, {}).get("accounts", {})

    # Start from prior events that are still within the retention window; the
    # fresh scan then overwrites any it re-observes and adds new ones. Backfill
    # date_iso on older records written before it existed.
    merged = {}
    for e in previous:
        if event_age_days(e) <= RETAIN_DAYS:
            e.setdefault("date_iso", parse_mail_date(e.get("date")))
            merged[event_key(e)] = e
    health = {}
    for account in ACCOUNTS:
        try:
            events = apple_mail(account, days=SCAN_DAYS)
            for event in events:
                merged[event_key(event)] = event
            health[account] = {"ok": True, "events": len(events), "scanned_at": now(),
                               "error": None, "last_ok": now()}
        except Exception as exc:
            health[account] = {"ok": False, "events": 0, "scanned_at": now(), "error": str(exc),
                               "last_ok": prior_health.get(account, {}).get("last_ok")}
            print(f"Mail scan warning for {account}: {exc}", file=sys.stderr)

    new = [event for key, event in merged.items() if key not in known]
    HISTORY.write_text(json.dumps(
        {"applications": sorted(merged.values(), key=event_ts, reverse=True)}, indent=2))
    HEALTH.write_text(json.dumps({
        "updated_at": now(),
        "accounts": health,
        "configured_accounts": ACCOUNTS,
        "scan_days": SCAN_DAYS,
        "any_failure": any(not h["ok"] for h in health.values()),
    }, indent=2))
    for event in new:
        notify(event)
    print(f"Tracker mail sync: {len(merged)} events, {len(new)} new, "
          f"{sum(1 for h in health.values() if not h['ok'])} account error(s)")


if __name__ == "__main__":
    main()
