import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mac"))
import mac_agent


class Response:
    def __init__(self, payload, status_code=200): self.payload, self.status_code = payload, status_code
    def json(self): return self.payload
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError(self.status_code)


def test_fetch_queue_reads_the_private_review_queue(monkeypatch):
    monkeypatch.delenv("JOB_MONITOR_QUEUE_FILE", raising=False)
    monkeypatch.setenv("JOB_MONITOR_GITHUB_REPO", "owner/repo")
    monkeypatch.setenv("JOB_MONITOR_GITHUB_TOKEN", "token")
    seen = []
    def get(url, **kwargs):
        seen.append(url)
        return Response({"generated_at": "2026-08-28", "jobs": [{"key": "a", "title": "SWE Intern"}]})
    monkeypatch.setattr(mac_agent.SESSION, "get", get)
    queue = mac_agent.fetch_queue()
    assert seen == ["https://api.github.com/repos/owner/repo/contents/data/review_queue.json"]
    assert queue == {"generated_at": "2026-08-28", "jobs": [{"key": "a", "title": "SWE Intern"}]}
