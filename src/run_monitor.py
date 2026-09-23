from __future__ import annotations
import os, sys
from datetime import datetime, timezone
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from notifications import send_digest
from dedupe import deduplicate
from scoring import assess
from scoring import hits
from sources import ashby, custom_jsonld, enrich_descriptions, greenhouse, lever, simplify
from state import StateStore

def load_yaml(name): return yaml.safe_load((ROOT / "config" / name).read_text())

def _age_days(value) -> float | None:
    if isinstance(value, (int, float)):
        return value / 24
    if not value:
        return None
    try:
        posted = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - posted).total_seconds() / 86400)
    except ValueError:
        return None

def prepare_jobs(jobs):
    prepared = []
    for job in jobs:
        value = job.as_dict()
        age = _age_days(value.get("age_hours")) or _age_days(value.get("posted_at"))
        if age is not None:
            value["age_days"] = round(age, 2)
        prepared.append(value)
    return deduplicate(prepared)

def collect(cfg):
    jobs, errors = [], []
    providers = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "custom_pages": custom_jsonld}
    for provider, fn in providers.items():
        for company, identifier in cfg.get("boards", {}).get(provider, {}).items():
            try: jobs.extend(fn(company, identifier))
            except Exception as exc: errors.append(f"{provider}:{company}: {exc}")
    scfg = cfg.get("sources", {}).get("simplify", {})
    if scfg.get("enabled"):
        try: jobs.extend(simplify(scfg))
        except Exception as exc: errors.append(f"simplify: {exc}")
    return jobs, errors

def main():
    profile, cfg = load_yaml("resume_profile.yaml"), load_yaml("sources.yaml")
    if cfg.get("freshness_days"):
        profile.setdefault("scoring", {})["max_age_days"] = cfg["freshness_days"]
    companies = load_yaml("companies.yaml").get("companies", {})
    store = StateStore(ROOT / "data" / "state.json")
    jobs, errors = collect(cfg)

    # Aggregator listings carry no JD text. Pull it for the ones that look
    # relevant enough to score properly (skills / sponsorship / grad-year).
    must = profile["role_titles"]["must_match_any"]
    strong = profile["role_titles"]["strong_titles"]["terms"]
    reject = profile["role_titles"]["reject_titles"]["terms"]
    def _worth_fetching(job):
        return (hits(job.title, must) and hits(job.title, strong) and not hits(job.title, reject))
    try:
        enrich_descriptions(jobs, _worth_fetching, limit=int(cfg.get("enrich_limit", 40)))
    except Exception as exc:
        errors.append(f"enrich: {exc}")

    jobs = prepare_jobs(jobs)
    ready = []
    for job in jobs:
        assessment = assess(job, profile, companies.get(job["company"])).as_dict()
        record, new = store.upsert(job, assessment)
        # Notify whenever a job *enters* the ready queue this run — including a
        # previously screened-out job that now qualifies (description arrived,
        # scoring changed), not only brand-new discoveries.
        if record.get("became_ready"): ready.append(record)
    store.add_run({"checked": len(jobs), "new_ready": len(ready), "errors": errors})
    store.save(); store.save_queue(ROOT / "data" / "review_queue.json")
    delivered = send_digest(ready, errors)
    print(f"Checked {len(jobs)} jobs; {len(ready)} new review items; notification_delivered={delivered}")
    for error in errors: print("WARNING", error)
    return 0 if jobs or not cfg.get("sources", {}).get("simplify", {}).get("enabled") else 2

if __name__ == "__main__": raise SystemExit(main())
