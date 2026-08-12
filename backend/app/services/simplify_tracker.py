"""Scrape direct application links from SimplifyJobs' Summer 2027 tracker.

The repository intentionally publishes its listings as HTML tables inside README.md.
This parser consumes the raw Markdown rather than GitHub's rendered page, which keeps the
contract small. Only direct employer application URLs are retained; Simplify company and
posting URLs are deliberately discarded.

The tracker is cached in memory for 15 minutes. If GitHub is briefly unavailable after a
successful fetch, callers receive the stale snapshot with a warning instead of an empty
board.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from app.connectors.base import DEFAULT_TIMEOUT, USER_AGENT
from app.schemas import SimplifyTrackerJob, SimplifyTrackerResponse

REPOSITORY_URL = "https://github.com/SimplifyJobs/Summer2027-Internships"
RAW_README_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "Summer2027-Internships/dev/README.md"
)
CACHE_TTL = timedelta(minutes=15)

_SECTION = re.compile(r"^##\s+(.+?)\s+Internship Roles\s*$", re.MULTILINE)
_MULTISPACE = re.compile(r"[ \t\r\f\v]+")
_LOCATION_COUNT = re.compile(r"^\d+\s+locations?\s*", re.IGNORECASE)
_cache: tuple[datetime, list[SimplifyTrackerJob]] | None = None
_cache_lock = asyncio.Lock()


@dataclass
class _Cell:
    text_parts: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    def text(self) -> str:
        value = unescape("".join(self.text_parts)).replace("\xa0", " ")
        lines = [_MULTISPACE.sub(" ", line).strip() for line in value.splitlines()]
        return " · ".join(line for line in lines if line)


class _TableParser(HTMLParser):
    """Tiny HTML-table parser tailored to the repository's generated README."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[_Cell]] = []
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = _Cell()
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href")
            if href:
                self._cell.links.append(href)
        elif tag == "br" and self._cell is not None:
            self._cell.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "summary" and self._cell is not None:
            self._cell.text_parts.append("\n")
        elif tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.text_parts.append(data)


def _clean_category(value: str) -> str:
    return re.sub(r"^[^A-Za-z0-9]+", "", value).strip()


def _clean_company(value: str) -> str:
    value = value.replace("🔥", "").replace("🛂", "").replace("🇺🇸", "")
    value = value.replace("🔒", "").replace("🎓", "")
    return _MULTISPACE.sub(" ", value).strip()


def _flags(company_cell: str, role: str) -> list[str]:
    combined = f"{company_cell} {role}"
    flags: list[str] = []
    if "🔥" in combined:
        flags.append("FAANG+")
    if "🛂" in combined:
        flags.append("No sponsorship")
    if "🇺🇸" in combined:
        flags.append("U.S. citizenship")
    if "🎓" in combined:
        flags.append("Advanced degree")
    return flags


def _stable_id(apply_url: str) -> str:
    digest = hashlib.sha256(apply_url.encode("utf-8")).hexdigest()[:20]
    return f"simplify-2027:{digest}"


def _clean_direct_url(url: str) -> str:
    """Remove Simplify attribution without breaking employer-specific parameters."""
    parsed = urlsplit(url)
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered_key = key.casefold()
        lowered_value = value.casefold()
        if lowered_key.startswith("utm_"):
            continue
        if lowered_key in ("ref", "source") and lowered_value == "simplify":
            continue
        query.append((key, value))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), parsed.fragment)
    )


def parse_readme(markdown: str) -> list[SimplifyTrackerJob]:
    """Parse every active category table in repository order."""
    headings = list(_SECTION.finditer(markdown))
    jobs: list[SimplifyTrackerJob] = []

    for index, heading in enumerate(headings):
        category = _clean_category(heading.group(1))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        parser = _TableParser()
        parser.feed(markdown[heading.end() : end])
        parser.close()

        previous_company = ""
        for cells in parser.rows:
            if len(cells) < 5:
                continue
            company_cell, role_cell, location_cell, application_cell, age_cell = cells[:5]
            company_raw = company_cell.text()
            role = role_cell.text().strip()
            if company_raw.casefold() == "company" or not role:
                continue

            if company_raw.strip() == "↳":
                company = previous_company
            else:
                company = _clean_company(company_raw)
                if company:
                    previous_company = company

            links = application_cell.links
            apply_url = next(
                (url for url in links if "simplify.jobs/" not in url),
                None,
            )
            if not company or not apply_url:
                continue
            apply_url = _clean_direct_url(apply_url)

            location = _LOCATION_COUNT.sub("", location_cell.text()).strip(" ·")
            jobs.append(
                SimplifyTrackerJob(
                    id=_stable_id(apply_url),
                    company=company,
                    role=role.replace("🎓", "").strip(),
                    location=location,
                    category=category,
                    age=age_cell.text(),
                    apply_url=apply_url,
                    flags=_flags(company_raw, role),
                    remote="remote" in location.casefold(),
                )
            )

    return jobs


async def _fetch(client: httpx.AsyncClient) -> tuple[datetime, list[SimplifyTrackerJob]]:
    response = await client.get(RAW_README_URL, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    jobs = parse_readme(response.text)
    if not jobs:
        raise ValueError("Simplify tracker returned no parseable internship rows.")
    return datetime.now(timezone.utc), jobs


async def get_tracker(
    *, query: str = "", category: str = "", limit: int = 500
) -> SimplifyTrackerResponse:
    global _cache
    now = datetime.now(timezone.utc)
    stale = False
    warning: str | None = None

    async with _cache_lock:
        if _cache is None or now - _cache[0] >= CACHE_TTL:
            try:
                async with httpx.AsyncClient(
                    headers={"User-Agent": USER_AGENT}, follow_redirects=True
                ) as client:
                    _cache = await _fetch(client)
            except Exception as exc:
                if _cache is None:
                    raise RuntimeError(f"Could not load Simplify Job Tracker: {exc}") from exc
                stale = True
                warning = "GitHub is temporarily unavailable; showing the last snapshot."

        fetched_at, jobs = _cache

    terms = query.casefold().split()
    category_key = category.casefold().strip()
    filtered = [
        job
        for job in jobs
        if (not category_key or job.category.casefold() == category_key)
        and (
            not terms
            or all(
                term
                in f"{job.company} {job.role} {job.location} {job.category}".casefold()
                for term in terms
            )
        )
    ]
    return SimplifyTrackerResponse(
        jobs=filtered[:limit],
        total=len(filtered),
        fetched_at=fetched_at,
        source_url=REPOSITORY_URL,
        stale=stale,
        warning=warning,
    )


def clear_cache() -> None:
    """Test hook; production callers should rely on the TTL."""
    global _cache
    _cache = None
