from __future__ import annotations

import re
from urllib.parse import urlsplit


DIRECT_SOURCES = {"greenhouse", "lever", "ashby", "custom_jsonld"}

# Coarse location buckets so the same role from an aggregator ("NYC") and an
# official board ("New York, NY") collapse, while genuinely different cities stay
# apart. First match wins; order roughly by specificity.
_LOCATION_BUCKETS = [
    ("remote", r"\bremote\b"),
    ("new-york", r"\bnew york\b|\bnyc\b|\bmanhattan\b|\bbrooklyn\b"),
    ("bay-area", r"\bsan francisco\b|\bsf\b|\bpalo alto\b|\bmenlo park\b|\bmountain view\b|\bsunnyvale\b|\bsanta clara\b|\bsan jose\b|\bcupertino\b|\bredwood city\b|\bbay area\b"),
    ("seattle", r"\bseattle\b|\bredmond\b|\bbellevue\b"),
    ("chicago", r"\bchicago\b"),
    ("los-angeles", r"\blos angeles\b|\bsanta monica\b|\bpasadena\b|\bculver city\b"),
    ("san-diego", r"\bsan diego\b"),
    ("boston", r"\bboston\b|\bcambridge, ma\b|\bcambridge ma\b"),
    ("austin", r"\baustin\b"),
    ("dallas", r"\bdallas\b|\bplano\b|\birving\b|\bfort worth\b"),
    ("houston", r"\bhouston\b"),
    ("dc", r"\bwashington, ?d\.?c\.?\b|\barlington, va\b|\bmclean\b|\breston\b"),
    ("denver", r"\bdenver\b|\bboulder\b"),
    ("atlanta", r"\batlanta\b"),
]


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def location_bucket(value: str) -> str:
    text = (value or "").lower()
    for name, pattern in _LOCATION_BUCKETS:
        if re.search(pattern, text):
            return name
    # Two-letter state codes as a fallback bucket.
    state = re.search(r"\b([a-z]{2})\b\s*$", _normalized(value))
    if state and state.group(1) in {"ny", "ca", "wa", "il", "tx", "ma", "co", "ga", "va", "nc", "nj", "pa", "fl", "az", "or"}:
        return f"state-{state.group(1)}"
    return _normalized(value) or "unspecified"


def normalized_title(value: str) -> str:
    text = _normalized(value)
    text = re.sub(r"\b(summer|spring|fall|winter|autumn)\s*(20\d\d)?\b", "", text)
    text = re.sub(r"\b20\d\d\b", "", text)
    text = re.sub(r"\b(intern|internship|co op|coop|program|opportunity|req\s*\d+|id\s*\d+)\b", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _company_matches(company: str, configured: list[str]) -> bool:
    actual = _normalized(company)
    return any(_normalized(name) in actual or actual in _normalized(name) for name in configured)


def _official(job: dict, domains: list[str]) -> bool:
    host = (urlsplit(job.get("url", "")).hostname or "").lower()
    domain_match = any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in domains)
    return domain_match or job.get("source") in DIRECT_SOURCES


def classify_priority(job: dict, programs: dict) -> dict | None:
    text = f"{job.get('title', '')} {job.get('description', '')}"
    for program_id, config in programs.items():
        if not _company_matches(job.get("company", ""), config.get("companies", [])):
            continue
        alias = next((pattern for pattern in config.get("aliases", []) if re.search(pattern, text, re.I)), None)
        if alias:
            return {
                "id": program_id,
                "name": config["name"],
                "matched_alias": alias,
                "official_source": _official(job, config.get("official_domains", [])),
            }
    return None


def dedupe_key(job: dict) -> str:
    priority = job.get("priority_program") or {}
    if priority:
        return "priority|" + "|".join((priority.get("id", ""), location_bucket(job.get("location", ""))))
    return "role|" + "|".join((
        _normalized(job.get("company", "")),
        normalized_title(job.get("title", "")),
        location_bucket(job.get("location", "")),
    ))


def deduplicate(jobs: list[dict]) -> list[dict]:
    chosen: dict[str, dict] = {}
    for job in jobs:
        key = dedupe_key(job)
        current = chosen.get(key)
        rank = (bool((job.get("priority_program") or {}).get("official_source")), job.get("source") in DIRECT_SOURCES, bool(job.get("description")))
        current_rank = (bool(((current or {}).get("priority_program") or {}).get("official_source")), (current or {}).get("source") in DIRECT_SOURCES, bool((current or {}).get("description")))
        if current is None or rank > current_rank:
            chosen[key] = job
    return list(chosen.values())

