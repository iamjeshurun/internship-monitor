import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent/"src"))
from models import Job, canonical_url
from state import StateStore
def test_tracking_parameters_do_not_break_dedup(): assert canonical_url("https://jobs.example/a?utm_source=x&ref=Simplify") == canonical_url("https://jobs.example/a")
def test_screened_job_can_be_rescored(tmp_path):
    store = StateStore(tmp_path/"state.json"); job = Job("test", "1", "Acme", "SWE Intern", "NYC", "https://example/a").as_dict()
    first, _ = store.upsert(job, {"eligible": False, "score": 0, "notify_threshold": 45}); assert first["status"] == "screened_out"
    second, _ = store.upsert(job, {"eligible": True, "score": 70, "notify_threshold": 45}); assert second["status"] == "ready_for_review"
def test_queue_contains_only_review_items(tmp_path):
    store = StateStore(tmp_path/"state.json")
    store.upsert(Job("test", "1", "A", "SWE Intern", "NYC", "https://example/a").as_dict(), {"eligible": True, "score": 70, "notify_threshold": 45})
    store.upsert(Job("test", "2", "B", "Marketing Intern", "NYC", "https://example/b").as_dict(), {"eligible": True, "score": 10, "notify_threshold": 45})
    assert [x["company"] for x in store.ready_queue()] == ["A"]
