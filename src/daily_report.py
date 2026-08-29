from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from notifications import send_email
ROOT = Path(__file__).resolve().parent.parent

def main():
    data = json.loads((ROOT/"data/state.json").read_text())
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent = [j for j in data.get("jobs", {}).values() if datetime.fromisoformat(j["first_seen"]) >= cutoff]
    ready = [j for j in data.get("jobs", {}).values() if j.get("status") == "ready_for_review"]
    runs = [r for r in data.get("runs", []) if datetime.fromisoformat(r["at"]) >= cutoff]
    errors = [e for r in runs for e in r.get("errors", [])]
    body = "\n".join(["Job Monitor — last 24 hours", "", f"Runs: {len(runs)}", f"New jobs discovered: {len(recent)}", f"Waiting for review: {len(ready)}", f"Source warnings: {len(errors)}", "", *[f"- {j['company']} — {j['title']} ({j['assessment']['score']}/100)" for j in ready[:20]]])
    if not send_email("Daily job monitor report", body): raise SystemExit("Daily email is not configured")
if __name__ == "__main__": main()
