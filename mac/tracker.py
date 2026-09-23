from __future__ import annotations
import hashlib, json, os, re, tempfile
from datetime import datetime, timezone
from pathlib import Path

STAGE_ORDER = {"ready": 0, "reviewing": 1, "applied": 2, "assessment": 3, "interview": 4, "offer": 5, "rejected": 5, "dismissed": 6}
STOP = {"job", "application", "intern", "internship", "the", "and", "for", "at", "you", "your", "from", "team"}
GENERIC_ROLE = {"thank", "thanks", "interest", "received", "submitted", "invitation", "assessment", "assessments", "process", "prepare", "track", "important", "information", "successfully", "applied", "update", "reminder", "action", "required", "complete", "completed", "completing", "next", "step", "steps", "take", "status"}
GENERIC_COMPANY = {"capital", "company", "corp", "corporation", "group", "holdings", "inc", "llc", "careers", "recruiting", "talent", "trading", "assessments", "assessment", "hiring", "jobs", "team", "global", "technologies", "labs", "no", "reply", "noreply"}
# ATS / assessment vendors that mask the real employer in the sender line.
ATS_VENDORS = {"greenhouse", "workday", "myworkday", "ashby", "ashbyhq", "lever", "icims", "smartrecruiters", "jobvite", "successfactors", "shl", "hackerrank", "codesignal", "criteria", "hirevue", "modernhire"}

def load_json(path: Path, fallback):
    try: return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError): return fallback

def tokens(value: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(x) > 2 and x not in STOP}

def event_key(event: dict) -> str:
    raw = "\x1f".join(str(event.get(k, "")) for k in ("mailbox_account", "date", "subject"))
    return "email-" + hashlib.sha256(raw.encode()).hexdigest()[:20]

def company_tokens(value: str) -> set[str]:
    """Tokens that identify an employer, minus ATS vendors and generic suffixes.

    Also keeps 2-letter names (GE, EY, HP, 3M) that ``tokens`` would drop.
    """
    raw = {x for x in re.findall(r"[a-z0-9&]+", (value or "").lower()) if x not in STOP}
    return {x for x in raw if len(x) > 1 and x not in GENERIC_COMPANY and x not in ATS_VENDORS}


def _event_day(event: dict) -> str:
    return (str(event.get("date_iso") or event.get("date") or "")[:10]) or "?"


def _company_slug(event: dict) -> str:
    ctoks = company_tokens(event.get("company_hint", ""))
    return "-".join(sorted(ctoks)) or re.sub(r"[^a-z0-9]+", "-", event.get("company_hint", "").lower()).strip("-")


def application_key(event: dict) -> str:
    req = str(event.get("requisition_id") or "").strip().lower()
    if req:
        return "application-req-" + hashlib.sha256(req.encode()).hexdigest()[:20]
    ctoks = company_tokens(event.get("company_hint", ""))
    company = _company_slug(event)
    role_tokens = tokens(event.get("role_hint", "")) - ctoks - GENERIC_ROLE
    role = "-".join(sorted(role_tokens))
    if company and company not in ATS_VENDORS:
        # No distinguishing role/req: two applications to the same employer are
        # only separable by submission day. Same-day duplicate receipts still
        # collapse; different days stay as distinct rows so nothing is hidden.
        raw = f"{company}|{role}" if role else f"{company}|day|{_event_day(event)}"
        return "application-" + hashlib.sha256(raw.encode()).hexdigest()[:20]
    return event_key(event)

def match_event(event: dict, jobs: list[dict]) -> dict | None:
    req = str(event.get("requisition_id") or "").lower()
    if req:
        exact = next((j for j in jobs if req in " ".join(str(j.get(k, "")).lower() for k in ("external_id", "url", "title"))), None)
        if exact:
            return exact
    event_company = company_tokens(event.get("company_hint", ""))
    event_tokens = tokens(f"{event.get('subject','')} {event.get('company_hint','')}")
    ranked = []
    for job in jobs:
        company = company_tokens(job.get("company", ""))
        title = tokens(job.get("title", ""))
        company_overlap = len(event_company & company)
        # Require the smaller company-token set to be fully covered, so
        # "Akuna Capital" never matches "Anthelion Capital" on a shared word.
        strong_company = bool(event_company) and (event_company <= company or company <= event_company)
        title_overlap = len(event_tokens & title)
        # Never attach a generic ATS message to a job merely because both titles
        # contain words such as "software engineering intern".
        if company_overlap:
            ranked.append((strong_company * 8 + company_overlap * 4 + title_overlap, job))
    if not ranked:
        return None
    ranked.sort(key=lambda row: row[0], reverse=True)
    best_score, best_job = ranked[0]
    tied = [job for score, job in ranked if score == best_score]
    best_title_overlap = len(event_tokens & tokens(best_job.get("title", "")))
    # Multiple same-company openings and nothing in the email points at one of
    # them: do NOT guess — let the event stand as its own row.
    if len(tied) > 1 and best_title_overlap == 0:
        return None
    # A weak, company-word-only overlap that isn't uniquely best is ambiguous.
    if best_score < 8 and len(tied) > 1:
        return None
    return best_job

def _sort_ts(event: dict) -> str:
    return str(event.get("date_iso") or event.get("date") or "")


def _manual_status(value):
    return value.get("status") if isinstance(value, dict) else value


def _apply_event(item: dict, event: dict, statuses: dict):
    """Advance an item's status from an email event, independent of iteration
    order: the event with the latest timestamp wins; ties break toward the
    stronger stage. A manual status (other than ready/reviewing) is never
    overwritten. ``last_update`` tracks the newest event.
    """
    stage = event.get("stage", "applied")
    ts = _sort_ts(event)
    manual = _manual_status(statuses.get(item["key"]))
    if not manual or manual in {"ready", "reviewing"}:
        cur = item.get("_status_ts")
        if cur is None or ts > cur or (ts == cur and STAGE_ORDER.get(stage, 0) > STAGE_ORDER.get(item["status"], 0)):
            item["status"], item["status_source"], item["_status_ts"] = stage, "email", ts
    item.setdefault("events", []).append(event)
    if ts > item.get("last_update", ""):
        item["last_update"] = ts
        item["last_update_display"] = event.get("date", "")


def merge_tracker(queue: dict, history: dict, statuses: dict) -> list[dict]:
    jobs = [dict(job) for job in queue.get("jobs", [])]
    items = {}
    for job in jobs:
        raw = statuses.get(job["key"])
        status = _manual_status(raw) or "ready"
        items[job["key"]] = {**job, "status": status, "status_source": "manual" if raw else "queue"}

    # Oldest-first so an application row exists before its later status updates
    # arrive; _apply_event itself is order-independent for the status decision.
    events = sorted(history.get("applications", []), key=_sort_ts)
    for event in events:
        matched = match_event(event, jobs)
        if matched:
            key = matched["key"]
        elif event.get("requisition_id") or (tokens(event.get("role_hint", "")) - company_tokens(event.get("company_hint", "")) - GENERIC_ROLE):
            key = application_key(event)  # has a distinguishing role or req id
        elif event.get("stage", "applied") != "applied":
            # Role-less status update (rejection / assessment / interview): route
            # it to this company's most recent application at or before its date,
            # rather than guessing a job or forking a bare row.
            key = _route_status_event(event, items)
        else:
            key = application_key(event)  # role-less receipt -> day-bucketed row

        if key not in items:
            items[key] = {"key": key, "company": event.get("company_hint") or "Email-detected application",
                          "title": event.get("role_hint") or event.get("subject") or "Application update",
                          "location": "", "url": "", "assessment": {"score": "—", "reasons": [], "flags": []},
                          "status": "applied", "status_source": "email"}
        _apply_event(items[key], event, statuses)

    ordered = sorted(items.values(),
                     key=lambda i: (STAGE_ORDER.get(i.get("status", "ready"), 0), i.get("last_update", "")),
                     reverse=True)
    for item in ordered:
        item.pop("_status_ts", None)
        display = item.pop("last_update_display", None)
        if display:
            item["last_update"] = display
    return ordered


def _route_status_event(event: dict, items: dict) -> str:
    slug = _company_slug(event)
    ts = _sort_ts(event)
    candidates = [
        (i.get("last_update", ""), key) for key, i in items.items()
        if slug and slug == "-".join(sorted(company_tokens(i.get("company", ""))))
        and i.get("status_source") in {"email", "queue", "manual"}
    ]
    earlier = [c for c in candidates if c[0] <= ts] or candidates
    if earlier:
        return max(earlier)[1]
    return application_key(event)

def save_status(path: Path, key: str, status: str, source: str = "manual"):
    """Persist a manual status atomically. load_json() treats an unreadable file
    as empty, so a torn write here would silently wipe every manual status."""
    state = load_json(path, {})
    state[key] = {"status": status, "source": source, "updated_at": datetime.now(timezone.utc).isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(state, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
