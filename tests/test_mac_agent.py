import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mac"))
import mac_agent


class Response:
    def __init__(self, payload, status_code=200): self.payload, self.status_code = payload, status_code
    def json(self): return self.payload
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def test_cloud_queues_are_merged_and_priority_copy_wins(monkeypatch):
    monkeypatch.delenv("JOB_MONITOR_QUEUE_FILE", raising=False)
    monkeypatch.setenv("JOB_MONITOR_GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("JOB_MONITOR_GITHUB_TOKEN", "token")
    ordinary = {"key": "same", "title": "STEP Intern"}
    priority = {"key": "same", "title": "STEP Intern", "priority_program": {"name": "Google STEP"}}
    def get(url, **kwargs):
        payload = {"generated_at": "2026-08-29", "jobs": [priority]} if "priority_queue" in url else {"generated_at": "2026-08-28", "jobs": [ordinary]}
        return Response(payload)
    monkeypatch.setattr(mac_agent.requests, "get", get)
    queue = mac_agent.fetch_queue()
    assert queue["generated_at"] == "2026-08-29"
    assert queue["jobs"] == [priority]
