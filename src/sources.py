from __future__ import annotations

import json
import re
import time
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from models import Job
from parse_simplify_readme import age_to_hours, parse_readme


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "internship-job-monitor/2.0 (+personal job search)"})


RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
BACKOFF_BASE = 1.0        # seconds; doubles each attempt
MAX_RETRY_WAIT = 20.0     # never sleep longer than this, even if Retry-After says so


def _retry_wait(response, attempt: int) -> float:
    """Honor Retry-After (seconds or HTTP date), else exponential backoff; capped."""
    header = (getattr(response, "headers", None) or {}).get("Retry-After")
    wait = None
    if header:
        try:
            wait = float(header)
        except ValueError:
            try:
                wait = max(0.0, parsedate_to_datetime(header).timestamp() - time.time())
            except (TypeError, ValueError):
                wait = None
    if wait is None:
        wait = BACKOFF_BASE * (2 ** attempt)
    return min(wait, MAX_RETRY_WAIT)


def _get(url: str, timeout: int = 25, attempts: int = MAX_ATTEMPTS, **kwargs):
    """GET with bounded retry on transient failures (timeouts, connection errors,
    429/5xx). A source that still fails after MAX_ATTEMPTS raises, and collect()
    isolates that failure to the one source."""
    last_exc = None
    for attempt in range(attempts):
        try:
            response = SESSION.get(url, timeout=timeout, **kwargs)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(min(BACKOFF_BASE * (2 ** attempt), MAX_RETRY_WAIT))
                continue
            raise
        if response.status_code in RETRY_STATUSES and attempt < attempts - 1:
            time.sleep(_retry_wait(response, attempt))
            continue
        response.raise_for_status()
        return response
    raise last_exc  # pragma: no cover


def _get_json(url: str, timeout: int = 25, attempts: int = MAX_ATTEMPTS):
    return _get(url, timeout=timeout, attempts=attempts).json()


def greenhouse(company: str, token: str) -> list[Job]:
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    return [Job("greenhouse", str(j["id"]), company, j.get("title", ""), (j.get("location") or {}).get("name", ""), j.get("absolute_url", ""), unescape(j.get("content", "")), j.get("updated_at")) for j in data.get("jobs", [])]


def lever(company: str, site: str) -> list[Job]:
    data = _get_json(f"https://api.lever.co/v0/postings/{site}?mode=json")
    return [Job("lever", str(j.get("id", "")), company, j.get("text", ""), (j.get("categories") or {}).get("location", ""), j.get("hostedUrl") or j.get("applyUrl", ""), BeautifulSoup(j.get("descriptionPlain", "") or "", "html.parser").get_text(" ")) for j in data]


def ashby(company: str, board: str) -> list[Job]:
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true")
    return [Job("ashby", str(j.get("jobUrl") or j.get("applyUrl")), company, j.get("title", ""), j.get("location", ""), j.get("jobUrl") or j.get("applyUrl", ""), BeautifulSoup(j.get("descriptionHtml", ""), "html.parser").get_text(" "), j.get("publishedAt"), metadata={"compensation": j.get("compensation")}) for j in data.get("jobs", []) if j.get("isListed", True)]


def simplify(config: dict) -> list[Job]:
    repo, branch = config["repo"], config.get("branch", "dev")
    response = _get(f"https://raw.githubusercontent.com/{repo}/{branch}/README.md", timeout=30)
    categories = [x.lower() for x in config.get("categories", [])]
    jobs = []
    for row in parse_readme(response.text):
        if categories and not any(x in row.category.lower() for x in categories):
            continue
        jobs.append(Job("simplify", row.url, row.company.lstrip("🔥").strip(), row.role, row.location, row.url, age_hours=age_to_hours(row.age_raw)))
    return jobs


def x_recent(config: dict, bearer_token: str) -> list[Job]:
    query = config.get("query", "")
    accounts = [f"from:{a}" for a in config.get("watched_accounts", [])]
    if accounts:
        query = f"({query}) OR ({' OR '.join(accounts)})"
    response = _get("https://api.x.com/2/tweets/search/recent", timeout=30, headers={"Authorization": f"Bearer {bearer_token}"}, params={"query": query, "max_results": 100, "tweet.fields": "created_at,author_id,entities"})
    jobs = []
    for post in response.json().get("data", []):
        text = post.get("text", "")
        urls = [u.get("expanded_url") for u in (post.get("entities") or {}).get("urls", []) if u.get("expanded_url")]
        url = urls[0] if urls else f"https://x.com/i/web/status/{post['id']}"
        jobs.append(Job("x", post["id"], "Social lead", text[:140], "", url, text, post.get("created_at"), metadata={"author_id": post.get("author_id")}))
    return jobs


_ATS_JOB_URL = re.compile(
    r"boards\.greenhouse\.io/(?:embed/job_app\?for=)?([^/?&]+).*?(?:gh_jid=|/jobs/)(\d+)"
    r"|job-boards\.greenhouse\.io/([^/?]+)/jobs/(\d+)"
    r"|jobs\.lever\.co/([^/]+)/([0-9a-f-]{36})"
    r"|jobs\.ashbyhq\.com/([^/]+)/([0-9a-f-]{36})",
    re.I,
)


def _fetch_description(url: str) -> str:
    """Best-effort JD text for an aggregator listing that points at a known ATS."""
    m = _ATS_JOB_URL.search(url or "")
    if not m:
        return ""
    try:
        if "greenhouse.io" in url:
            token = m.group(1) or m.group(3)
            job_id = m.group(2) or m.group(4)
            data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{job_id}", timeout=12, attempts=1)
            return unescape(data.get("content", ""))
        if "lever.co" in url:
            data = _get_json(f"https://api.lever.co/v0/postings/{m.group(5)}/{m.group(6)}", timeout=12, attempts=1)
            return BeautifulSoup(data.get("descriptionPlain") or data.get("description", ""), "html.parser").get_text(" ")
        if "ashbyhq.com" in url:
            board = m.group(7)
            data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true", timeout=12, attempts=1)
            for posting in data.get("jobs", []):
                if m.group(8) in (posting.get("jobUrl", "") + posting.get("applyUrl", "")):
                    return BeautifulSoup(posting.get("descriptionHtml", ""), "html.parser").get_text(" ")
    except Exception:
        return ""
    return ""


def enrich_descriptions(jobs: list[Job], should_fetch, limit: int = 40) -> None:
    """Fill in descriptions for description-less listings the caller cares about."""
    fetched = 0
    for job in jobs:
        if fetched >= limit:
            break
        if job.description or not should_fetch(job):
            continue
        text = _fetch_description(job.url)
        if text:
            job.description = text
            fetched += 1


def custom_jsonld(company: str, page_url: str) -> list[Job]:
    response = _get(page_url, timeout=30)
    soup = BeautifulSoup(response.text, "lxml")
    jobs = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            objects = json.loads(script.string or "null")
        except json.JSONDecodeError:
            continue
        objects = objects if isinstance(objects, list) else [objects]
        for obj in objects:
            if not isinstance(obj, dict) or obj.get("@type") != "JobPosting":
                continue
            loc = obj.get("jobLocation", "")
            if isinstance(loc, list):
                loc = ", ".join(str(x) for x in loc)
            jobs.append(Job("custom_jsonld", str(obj.get("identifier") or obj.get("url")), company, obj.get("title", ""), str(loc), urljoin(page_url, obj.get("url", page_url)), BeautifulSoup(obj.get("description", ""), "html.parser").get_text(" "), obj.get("datePosted")))
    return jobs
