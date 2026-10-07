from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from notifications import send_digest
from paths import DATA_DIR
from run_monitor import collect, load_yaml, prepare_jobs
from scoring import assess
from sources import _fetch_description
from state import StateStore


def main():
    profile = load_yaml("resume_profile.yaml")
    source_config = load_yaml("sources.yaml")
    priority_config = load_yaml("priority_programs.yaml")
    programs = priority_config.get("programs", {})
    companies = load_yaml("companies.yaml").get("companies", {})

    # The fast watcher uses the shared aggregator plus only explicitly configured
    # priority boards, keeping each ten-minute run small.
    focused = {
        "sources": {"simplify": source_config.get("sources", {}).get("simplify", {})},
        "boards": priority_config.get("boards", {}),
    }
    collected, errors = collect(focused)
    jobs = [job for job in prepare_jobs(collected, programs) if job.get("priority_program")]
    # Priority matches are few, so fetch each one's real JD (sponsorship / grad-year
    # screening is otherwise blind for aggregator listings).
    for job in jobs:
        if not job.get("description"):
            job["description"] = _fetch_description(job.get("url", ""))
    store = StateStore(DATA_DIR / "priority_state.json")
    ready = []
    for job in jobs:
        assessment = assess(job, profile, companies.get(job["company"])).as_dict()
        record, new = store.upsert(job, assessment)
        if record.get("became_ready"):
            ready.append(record)
    store.add_run(
        {"checked": len(collected), "priority_matches": len(jobs), "new_ready": len(ready), "errors": errors}
    )
    store.save()
    store.save_queue(DATA_DIR / "priority_queue.json")
    delivered = send_digest(ready, errors)
    print(
        f"Checked {len(collected)} listings; {len(jobs)} priority matches; {len(ready)} new; notification_delivered={delivered}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
