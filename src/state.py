from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.data = json.loads(path.read_text())
        else:
            self.data = {"schema_version": 2, "scoring_version": "2.0", "jobs": {}, "runs": []}
        self.data.setdefault("jobs", {})
        self.data.setdefault("runs", [])

    def upsert(self, job: dict, assessment: dict) -> tuple[dict, bool]:
        now = utc_now()
        current = self.data["jobs"].get(job["key"])
        is_new = current is None
        if current is None:
            current = {**job, "first_seen": now, "status": "discovered", "notification_state": "pending"}
        current.update(job)
        current.update({"last_seen": now, "assessment": assessment, "scoring_version": self.data["scoring_version"]})
        if assessment["eligible"] and assessment["score"] >= assessment["notify_threshold"]:
            if current["status"] in {"discovered", "screened_out"}:
                current["status"] = "ready_for_review"
        elif current["status"] in {"discovered", "screened_out", "ready_for_review"}:
            current["status"] = "screened_out"
        if current["status"] == "screened_out":
            # Git is the durable dedup/index layer, not a description warehouse.
            # Current boards are refetched each run; retain full content only for
            # jobs that a person may review.
            current = {
                "key": job["key"],
                "first_seen": current["first_seen"],
                "status": "screened_out",
            }
        self.data["jobs"][job["key"]] = current
        return current, is_new

    def add_run(self, record: dict):
        self.data["runs"].append({"at": utc_now(), **record})
        self.data["runs"] = self.data["runs"][-100:]

    def ready_queue(self) -> list[dict]:
        jobs = [j for j in self.data["jobs"].values() if j.get("status") == "ready_for_review"]
        return sorted(jobs, key=lambda j: (-j["assessment"]["score"], j.get("first_seen", "")))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        os.replace(tmp, self.path)

    def save_queue(self, path: Path):
        payload = {"generated_at": utc_now(), "jobs": self.ready_queue()}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        os.replace(tmp, path)
