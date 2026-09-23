from __future__ import annotations
import json, os, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError as ReqConnectionError, Timeout
from urllib3.util.retry import Retry
from notifier import notify as native_notify

ROOT = Path(__file__).resolve().parent.parent
LOCAL = Path(os.environ.get("JOB_MONITOR_LOCAL_DIR", Path.home()/"Library/Application Support/JobMonitor"))
LOCAL.mkdir(parents=True, exist_ok=True)
STATE = LOCAL/"notified.json"
CACHE = LOCAL/"review_queue.json"
HEALTH = LOCAL/"agent_health.json"
# After this many consecutive failed polls (~15 min at a 180s interval) tell the
# user once that notifications are paused, so silence never looks like "no jobs".
STALE_ALERT_AFTER = 5

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=4, connect=4, read=3, backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])))

# Delivery semantics: at-least-once with a hard cap. A job is recorded "pending"
# BEFORE its alert is sent and "sent" after. A crash in the send->receipt window
# therefore re-sends on restart (a missed job alert is worse than a duplicate),
# but never more than MAX_DELIVERY_ATTEMPTS times in total, so a crash loop cannot
# spam. Exactly-once is not achievable against a non-idempotent notifier.
MAX_DELIVERY_ATTEMPTS = 2

DONE_STATUSES = {"applied", "assessment", "interview", "offer", "rejected", "dismissed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, text: str):
    """Write to a temp file in the same directory, fsync, then rename over the
    target — readers never observe a partial file, and a crash leaves the old
    content intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_ledger() -> dict:
    raw = _load(STATE, {})
    if isinstance(raw, list):  # legacy format: a plain list of notified keys
        return {key: {"state": "sent", "attempts": 1} for key in raw}
    return raw


def _load(path: Path, fallback):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def _get(url: str, token: str):
    """GET with the pooled session, then one fresh-connection retry on a
    transient network error (api.github.com occasionally stalls a kept-alive
    socket from this host)."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json"}
    try:
        return SESSION.get(url, headers=headers, timeout=(6, 20))
    except (Timeout, ReqConnectionError):
        time.sleep(2)
        with requests.Session() as fresh:
            fresh.headers["Connection"] = "close"
            return fresh.get(url, headers=headers, timeout=(8, 35))


def fetch_queue():
    local = os.environ.get("JOB_MONITOR_QUEUE_FILE")
    if local:
        return json.loads(Path(local).read_text())
    repo, token = os.environ["JOB_MONITOR_GITHUB_REPO"], os.environ["JOB_MONITOR_GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{repo}/contents/data/review_queue.json"
    r = _get(url, token)
    r.raise_for_status()
    payload = r.json()
    return {"generated_at": payload.get("generated_at") or "", "jobs": payload.get("jobs", [])}


def notify(job):
    title = f"{job['company']} — {job['title']}".replace('"', "'")
    message = f"{job['assessment']['score']}/100 · {job.get('location','')} · ready for review".replace('"', "'")
    app_title = "Job Monitor"
    if os.environ.get("JOB_MONITOR_DRY_RUN") == "1":
        print("NOTIFY", app_title, title, message)
        return
    native_notify(app_title, message, title, job.get("url") or "http://127.0.0.1:8765")


def _write_health(ok: bool, error: str | None):
    health = _load(HEALTH, {})
    fails = 0 if ok else int(health.get("consecutive_failures", 0)) + 1
    health.update({
        "last_attempt": _now(),
        "consecutive_failures": fails,
        "last_error": None if ok else error,
    })
    if ok:
        health["last_success"] = _now()
    if fails == STALE_ALERT_AFTER and os.environ.get("JOB_MONITOR_DRY_RUN") != "1":
        native_notify("Job Monitor", "Can't reach GitHub — new-job notifications are paused.", "Check your network / token")
    _atomic_write(HEALTH, json.dumps(health, indent=2))


def once():
    try:
        queue = fetch_queue()
    except Exception as exc:
        _write_health(False, f"{type(exc).__name__}: {exc}")
        raise
    _atomic_write(CACHE, json.dumps(queue, indent=2))
    _write_health(True, None)

    ledger = _load_ledger()
    statuses = _load(LOCAL / "status.json", {})
    for job in queue.get("jobs", []):
        key = job["key"]
        value = statuses.get(key, {})
        local_status = value.get("status") if isinstance(value, dict) else value
        if local_status in DONE_STATUSES:
            continue
        entry = ledger.get(key, {})
        if entry.get("state") == "sent" or entry.get("attempts", 0) >= MAX_DELIVERY_ATTEMPTS:
            continue
        # Write-ahead: record intent durably, THEN send, THEN record receipt.
        ledger[key] = {"state": "pending", "attempts": entry.get("attempts", 0) + 1, "at": _now()}
        _atomic_write(STATE, json.dumps(ledger, indent=2, sort_keys=True))
        try:
            notify(job)
        except Exception:
            continue  # stays pending; retried next poll until the attempt cap
        ledger[key]["state"] = "sent"
        _atomic_write(STATE, json.dumps(ledger, indent=2, sort_keys=True))


if __name__ == "__main__":
    once()
