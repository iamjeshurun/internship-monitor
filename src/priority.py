"""Flag postings that belong to named early-career programs (e.g. Google STEP)."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from dedupe import DIRECT_SOURCES, normalized


def _company_matches(company: str, configured: list[str]) -> bool:
    actual = normalized(company)
    return any(normalized(name) in actual or actual in normalized(name) for name in configured)


def _official(job: dict, domains: list[str]) -> bool:
    host = (urlsplit(job.get("url", "")).hostname or "").lower()
    domain_match = any(host == domain.lower() or host.endswith("." + domain.lower()) for domain in domains)
    return domain_match or job.get("source") in DIRECT_SOURCES


def classify_priority(job: dict, programs: dict) -> dict | None:
    text = f"{job.get('title', '')} {job.get('description', '')}"
    for program_id, config in programs.items():
        if not _company_matches(job.get("company", ""), config.get("companies", [])):
            continue
        alias = next(
            (pattern for pattern in config.get("aliases", []) if re.search(pattern, text, re.I)), None
        )
        if alias:
            return {
                "id": program_id,
                "name": config["name"],
                "matched_alias": alias,
                "official_source": _official(job, config.get("official_domains", [])),
            }
    return None
