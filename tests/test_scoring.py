import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).parent.parent/"src"))
from scoring import assess
PROFILE = yaml.safe_load((Path(__file__).parent.parent/"config/resume_profile.yaml").read_text())
def job(title="Software Engineer Intern - Summer 2027", location="San Francisco, CA", description="Python backend APIs; visa sponsorship available", age_hours=6): return {"title": title, "location": location, "description": description, "age_hours": age_hours}
def test_california_is_preferred_not_excluded():
    r = assess(job(), PROFILE); assert r.eligible and "location: California" in r.reasons
def test_dubai_is_blocked():
    r = assess(job(location="Dubai - United Arab Emirates"), PROFILE); assert not r.eligible and any("non-US" in x for x in r.blockers)
def test_sponsorship_refusal_blocks():
    r = assess(job(description="Python. We are unable to sponsor employment visas."), PROFILE); assert not r.eligible and any("sponsor" in x for x in r.blockers)
def test_priority_changes_score():
    assert assess(job(), PROFILE, {"priority": "Apply first (sophomore program)"}).score > assess(job(), PROFILE, {"priority": "Reach"}).score
def test_missing_description_is_review_flag():
    r = assess(job(description=""), PROFILE); assert r.eligible and "sponsorship unknown" in r.flags
def test_senior_role_rejected(): assert not assess(job(title="Senior Software Engineer Intern - Summer 2027"), PROFILE).eligible
