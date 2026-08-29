from __future__ import annotations
import re
from dataclasses import asdict, dataclass, field

@dataclass
class Assessment:
    score: int
    eligible: bool
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    notify_threshold: int = 45
    def as_dict(self): return asdict(self)

def hits(text: str, terms: list[str]) -> list[str]:
    out = []
    for term in terms:
        term = str(term).strip()
        if term and re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text.lower()): out.append(term)
    return out

def assess(job: dict, profile: dict, company_meta: dict | None = None) -> Assessment:
    company_meta = company_meta or {}
    title, location, description = job.get("title", ""), job.get("location", ""), job.get("description", "")
    text, reasons, blockers, flags, score = f"{title} {description}", [], [], [], 0
    threshold = profile["scoring"]["min_score_to_notify"]
    if hits(title, profile["role_titles"]["reject_titles"]["terms"]): blockers.append("senior/advanced role title")
    if not hits(title, profile["role_titles"]["must_match_any"]): blockers.append("not identified as an internship or co-op")
    advanced_degree = (
        re.search(r"\b(?:pursuing|enrolled\s+in|working\s+toward)\b[^.\n]{0,60}\b(?:master'?s|masters|ph\.?\s*d\.?|doctorate)\b", description, re.I)
        or re.search(r"\b(?:master'?s|masters|ph\.?\s*d\.?|doctorate)\b[^.\n]{0,80}\b(?:required|candidate|candidates|student|students|program|degree)\b", description, re.I)
    )
    if advanced_degree: blockers.append("advanced degree required")
    foreign = hits(location, profile["locations"].get("foreign_markers", []))
    us = hits(location, profile["locations"].get("us_markers", []))
    if foreign and not us: blockers.append(f"non-US location: {foreign[0]}")
    if not location: flags.append("location missing; verify US eligibility")
    term = hits(text, profile["terms"]["accept"])
    wrong = hits(text, profile["terms"].get("reject", []))
    if wrong and not term: blockers.append(f"wrong internship term: {wrong[0]}")
    if term: score += 15; reasons.append(f"target term: {term[0]}")
    else: flags.append("term not explicit")
    role = hits(title, profile["role_titles"]["strong_titles"]["terms"])
    score += min(24, 8 * len(set(role)))
    if role: reasons.append("role match: " + ", ".join(role[:3]))
    skills = []
    for group in profile["skills"].values(): skills.extend(hits(text, group["terms"]))
    score += min(24, 3 * len(set(skills)))
    if skills: reasons.append("skills: " + ", ".join(skills[:6]))
    elif not description: flags.append("description unavailable; skill score incomplete")
    for group in profile["locations"]["preference_groups"]:
        if hits(location, group["terms"]): score += group["weight"]; reasons.append(f"location: {group['name']}"); break
    priority = company_meta.get("priority", "")
    pw = profile["scoring"].get("company_priority_weights", {}).get(priority, 0)
    score += pw
    if pw: reasons.append(f"company priority: {priority}")
    no_sponsor = hits(description, profile["sponsorship"]["red_flags"])
    if no_sponsor: blockers.append("posting appears to refuse current/future sponsorship")
    elif not description: flags.append("sponsorship unknown")
    grad = hits(description, profile.get("graduation", {}).get("reject_phrases", []))
    if grad: blockers.append(f"graduation requirement may conflict: {grad[0]}")
    age = job.get("age_hours")
    if isinstance(age, (int, float)):
        if age <= 24: score += 8; reasons.append("posted within 24 hours")
        elif age <= 168: score += 4; reasons.append("posted within 7 days")
    return Assessment(max(0, min(100, score)), not blockers, reasons, blockers, flags, threshold)

def score_job(job: dict, profile: dict):
    result = assess({**job, "description": job.get("content", "")}, profile)
    class Compat:
        score = result.score
        reasons = result.reasons + result.blockers
        rejected = not result.eligible
        strong_match = result.score >= profile["scoring"].get("strong_match_threshold", 70)
        sponsorship_flag = any("sponsor" in x for x in result.blockers)
    return Compat()
