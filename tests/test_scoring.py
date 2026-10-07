import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from scoring import assess

PROFILE = yaml.safe_load((Path(__file__).parent.parent / "config/resume_profile.yaml").read_text())


def job(
    title="Software Engineer Intern - Summer 2027",
    location="San Francisco, CA",
    description="Python backend APIs; visa sponsorship available",
    age_hours=6,
):
    return {"title": title, "location": location, "description": description, "age_hours": age_hours}


def test_california_is_preferred_not_excluded():
    r = assess(job(), PROFILE)
    assert r.eligible and "location: California" in r.reasons


def test_dubai_is_blocked():
    r = assess(job(location="Dubai - United Arab Emirates"), PROFILE)
    assert not r.eligible and any("non-US" in x for x in r.blockers)


def test_sponsorship_refusal_blocks():
    r = assess(job(description="Python. We are unable to sponsor employment visas."), PROFILE)
    assert not r.eligible and any("sponsor" in x for x in r.blockers)


def test_priority_changes_score():
    assert (
        assess(job(), PROFILE, {"priority": "Apply first (sophomore program)"}).score
        > assess(job(), PROFILE, {"priority": "Reach"}).score
    )


def test_missing_description_is_review_flag():
    r = assess(job(description=""), PROFILE)
    assert r.eligible and "sponsorship unknown" in r.flags


def test_senior_role_rejected():
    assert not assess(job(title="Senior Software Engineer Intern - Summer 2027"), PROFILE).eligible


def test_masters_or_phd_only_role_rejected():
    r = assess(job(description="We are looking for Masters or PhD candidates in computer science."), PROFILE)
    assert not r.eligible and "advanced degree required" in r.blockers


def test_bachelors_role_not_rejected_as_advanced_degree():
    r = assess(job(description="Python internship for candidates pursuing a bachelor's degree."), PROFILE)
    assert r.eligible


def test_stale_posting_is_blocked_when_max_age_configured():
    profile = {**PROFILE, "scoring": {**PROFILE["scoring"], "max_age_days": 30}}
    fresh = assess({**job(age_hours=None), "age_days": 5}, profile)
    stale = assess({**job(age_hours=None), "age_days": 60}, profile)
    assert fresh.eligible and not stale.eligible
    assert any("older than 30 days" in b for b in stale.blockers)
