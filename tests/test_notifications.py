import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import notifications


class Response:
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload
    def raise_for_status(self): return None


def test_github_alert_comments_on_existing_thread(monkeypatch):
    sent = {}
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_ALERT_MENTION", "owner")
    monkeypatch.setattr(notifications.requests, "get", lambda *a, **k: Response([{"number": 7, "title": "Job Monitor Alerts"}]))
    def post(url, **kwargs):
        sent.update(url=url, body=kwargs["json"]["body"]); return Response({})
    monkeypatch.setattr(notifications.requests, "post", post)
    assert notifications.send_github_alert("Ready", "One match")
    assert sent["url"].endswith("/issues/7/comments")
    assert "@owner" in sent["body"]
