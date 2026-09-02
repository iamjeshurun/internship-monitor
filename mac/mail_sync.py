from __future__ import annotations
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/"src"))
from email_history import apple_mail
from tracker import event_key, load_json
from notifier import notify as native_notify

LOCAL = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
HISTORY = LOCAL/"application_history.json"
ACCOUNTS = [x.strip() for x in os.environ.get("JOB_MONITOR_MAIL_ACCOUNTS", "you@example.com,school.account@example.edu").split(",") if x.strip()]

def notify(event):
    title = f"Application update — {event.get('stage','update').title()}"
    message = event.get("subject") or event.get("company_hint") or "New mailbox update"
    native_notify(title, message)

def main():
    LOCAL.mkdir(parents=True, exist_ok=True)
    previous = load_json(HISTORY, {"applications": []}).get("applications", []); known = {event_key(event) for event in previous}; combined = []
    for account in ACCOUNTS:
        try: combined.extend(apple_mail(account, days=45))
        except Exception as exc:
            print(f"Mail scan warning for {account}: {exc}", file=sys.stderr)
            combined.extend(event for event in previous if event.get("mailbox_account") == account)
    unique = {event_key(event): event for event in combined}; new = [event for key, event in unique.items() if key not in known]
    HISTORY.write_text(json.dumps({"applications": sorted(unique.values(), key=lambda item: item.get("date", ""), reverse=True)}, indent=2))
    for event in new: notify(event)
    print(f"Tracker mail sync: {len(unique)} events, {len(new)} new")

if __name__ == "__main__": main()
