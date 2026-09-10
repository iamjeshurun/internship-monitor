from __future__ import annotations
import hashlib, json, re
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


def application_key(event: dict) -> str:
    req = str(event.get("requisition_id") or "").strip().lower()
    if req:
        return "application-req-" + hashlib.sha256(req.encode()).hexdigest()[:20]
    ctoks = company_tokens(event.get("company_hint", ""))
    company = "-".join(sorted(ctoks)) or re.sub(r"[^a-z0-9]+", "-", event.get("company_hint", "").lower()).strip("-")
    role_tokens = tokens(event.get("role_hint", "")) - ctoks - GENERIC_ROLE
    role = "-".join(sorted(role_tokens)) or "general"
    if company and company not in ATS_VENDORS:
        raw = f"{company}|{role}"
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
    best_score, best_job = max(ranked, key=lambda row: row[0])
    # A weak, company-word-only overlap with several candidates is ambiguous.
    if best_score < 8 and sum(1 for score, _ in ranked if score == best_score) > 1:
        return None
    return best_job

def merge_tracker(queue: dict, history: dict, statuses: dict) -> list[dict]:
    jobs = [dict(job) for job in queue.get("jobs", [])]
    items = {job["key"]: {**job, "status": statuses.get(job["key"], {}).get("status", statuses.get(job["key"], "ready")) if isinstance(statuses.get(job["key"], {}), dict) else statuses[job["key"]], "status_source": "manual" if job["key"] in statuses else "queue"} for job in jobs}
    for event in history.get("applications", []):
        matched = match_event(event, jobs); key = matched["key"] if matched else application_key(event)
        if key not in items:
            items[key] = {"key": key, "company": event.get("company_hint") or "Email-detected application", "title": event.get("role_hint") or event.get("subject") or "Application update", "location": "", "url": "", "assessment": {"score": "—", "reasons": [], "flags": []}, "status": "applied", "status_source": "email"}
        item, manual, stage = items[key], statuses.get(key), event.get("stage", "applied")
        manual_status = manual.get("status") if isinstance(manual, dict) else manual
        email_can_update = not manual or manual_status in {"ready", "reviewing"}
        if email_can_update and STAGE_ORDER.get(stage, 0) >= STAGE_ORDER.get(item.get("status", "ready"), 0): item["status"], item["status_source"] = stage, "email"
        item.setdefault("events", []).append(event); item["last_update"] = event.get("date", "")
    return sorted(items.values(), key=lambda item: (STAGE_ORDER.get(item.get("status", "ready"), 0), item.get("last_update", "")), reverse=True)

def save_status(path: Path, key: str, status: str, source: str = "manual"):
    state = load_json(path, {}); state[key] = {"status": status, "source": source, "updated_at": datetime.now(timezone.utc).isoformat()}; path.write_text(json.dumps(state, indent=2))
