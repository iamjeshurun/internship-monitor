from __future__ import annotations

import re
from urllib.parse import urlsplit


DIRECT_SOURCES = {"greenhouse", "lever", "ashby", "custom_jsonld"}


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


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
        return "priority|" + "|".join((priority.get("id", ""), _normalized(job.get("location", ""))))
    return "role|" + "|".join((_normalized(job.get("company", "")), _normalized(job.get("title", "")), _normalized(job.get("location", ""))))


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

