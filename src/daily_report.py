from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from notifications import send_email, send_github_alert
ROOT = Path(__file__).resolve().parent.parent


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main():
    data = json.loads((ROOT/"data/state.json").read_text())
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    ready = [j for j in data.get("jobs", {}).values() if j.get("status") == "ready_for_review"]
    # "New" = entered the ready queue in the last 24h. This is what the report
    # leads with; the rest is an at-a-glance count, not a re-listing every day.
    recent = sorted(
        (j for j in ready if _dt(j.get("ready_since", j["first_seen"])) >= cutoff),
        key=lambda j: -j["assessment"]["score"],
    )
    older = [j for j in ready if j not in recent]
    runs = [r for r in data.get("runs", []) if _dt(r["at"]) >= cutoff]
    errors = [e for r in runs for e in r.get("errors", [])]
    lines = [
        "Job Monitor — last 24 hours", "",
        f"Runs: {len(runs)}    Source warnings: {len(errors)}",
        f"New review-ready matches: {len(recent)}",
        f"Still awaiting your review (older): {len(older)} — open the Mac dashboard",
        "",
    ]
    if recent:
        lines += ["New since yesterday:"]
        lines += [f"- {j['company']} — {j['title']} ({j['assessment']['score']}/100)\n  {j.get('url','')}" for j in recent]
    else:
        lines += ["No new review-ready matches in the last 24 hours."]
    if errors:
        lines += ["", "Source warnings:", *[f"- {e}" for e in errors[:10]]]
    body = "\n".join(lines)
    if send_github_alert("Daily job monitor report", body):
        return
    if not send_email("Daily job monitor report", body):
        raise SystemExit("No notification backend is configured")


if __name__ == "__main__":
    main()
