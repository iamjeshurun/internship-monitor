from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {"ref", "source", "gh_src"}


def canonical_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), "")
    )


@dataclass
class Job:
    source: str
    source_id: str
    company: str
    title: str
    location: str
    url: str
    description: str = ""
    posted_at: str | None = None
    age_hours: float | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def canonical_url(self) -> str:
        return canonical_url(self.url)

    @property
    def key(self) -> str:
        basis = self.canonical_url or f"{self.source}|{self.source_id}|{self.company}|{self.title}"
        return sha256(basis.encode("utf-8")).hexdigest()[:24]

    def as_dict(self) -> dict:
        value = asdict(self)
        value["canonical_url"] = self.canonical_url
        value["key"] = self.key
        return value
