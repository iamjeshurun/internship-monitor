from __future__ import annotations
import os, sys
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from notifications import send_digest
from scoring import assess
from sources import ashby, custom_jsonld, greenhouse, lever, simplify, x_recent
from state import StateStore

def load_yaml(name): return yaml.safe_load((ROOT / "config" / name).read_text())

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
    xcfg = cfg.get("sources", {}).get("x", {})
    if xcfg.get("enabled"):
        token = os.environ.get("X_BEARER_TOKEN")
        if not token: errors.append("x: enabled but X_BEARER_TOKEN is missing")
        else:
            try: jobs.extend(x_recent(xcfg, token))
            except Exception as exc: errors.append(f"x: {exc}")
    return jobs, errors

def main():
    profile, cfg = load_yaml("resume_profile.yaml"), load_yaml("sources.yaml")
    companies = load_yaml("companies.yaml").get("companies", {})
    store = StateStore(ROOT / "data" / "state.json")
    jobs, errors = collect(cfg)
    ready = []
    for job in jobs:
        assessment = assess(job.as_dict(), profile, companies.get(job.company)).as_dict()
        record, new = store.upsert(job.as_dict(), assessment)
        if new and record["status"] == "ready_for_review": ready.append(record)
    store.add_run({"checked": len(jobs), "new_ready": len(ready), "errors": errors})
    store.save(); store.save_queue(ROOT / "data" / "review_queue.json")
    delivered = send_digest(ready, errors)
    print(f"Checked {len(jobs)} jobs; {len(ready)} new review items; notification_delivered={delivered}")
    for error in errors: print("WARNING", error)
    return 0 if jobs or not cfg.get("sources", {}).get("simplify", {}).get("enabled") else 2

if __name__ == "__main__": raise SystemExit(main())
