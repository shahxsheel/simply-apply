"""Ashby public job boards, restricted to internship postings.

Ashby exposes one unauthenticated endpoint per employer board.  Like Greenhouse, it has
no global company search, so the configured board slugs define the employers queried.

Official endpoint:
    https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from app.connectors.base import DEFAULT_TIMEOUT, html_to_text
from app.schemas import JobRecord
from app.services.internship_filter import is_internship

BOARD_URL = (
    "https://api.ashbyhq.com/posting-api/job-board/"
    "{board}?includeCompensation=true"
)


class AshbyConnector:
    source = "ashby"

    def __init__(self, boards: list[str] | None = None, max_concurrent: int = 6) -> None:
        self.boards = boards or []
        self._sem = asyncio.Semaphore(max_concurrent)

    async def fetch(self, client: httpx.AsyncClient) -> list[JobRecord]:
        if not self.boards:
            return []

        results = await asyncio.gather(
            *(self._fetch_board(client, board) for board in self.boards),
            return_exceptions=True,
        )
        jobs: list[JobRecord] = []
        failures = 0
        for item in results:
            if isinstance(item, BaseException):
                failures += 1
            else:
                jobs.extend(item)

        if failures == len(self.boards):
            raise RuntimeError(f"all {failures} Ashby boards failed")
        return jobs

    async def _fetch_board(
        self, client: httpx.AsyncClient, board: str
    ) -> list[JobRecord]:
        async with self._sem:
            response = await client.get(
                BOARD_URL.format(board=board), timeout=DEFAULT_TIMEOUT
            )
            response.raise_for_status()
            payload = response.json()

        out: list[JobRecord] = []
        for raw in payload.get("jobs") or []:
            record = self._normalize(raw, board)
            if record is None or not is_internship(record.title, record.description):
                continue
            out.append(record)
        return out

    def _normalize(self, raw: dict, board: str) -> JobRecord | None:
        job_id = raw.get("id")
        title = (raw.get("title") or "").strip()
        apply_url = raw.get("jobUrl") or raw.get("applyUrl")
        if not job_id or not title or not apply_url or raw.get("isListed") is False:
            return None

        description = (raw.get("descriptionPlain") or "").strip()
        if not description:
            description = html_to_text(raw.get("descriptionHtml") or "")

        workplace = (raw.get("workplaceType") or "").lower()
        return JobRecord(
            id=f"ashby:{board}:{job_id}",
            source=self.source,
            title=title,
            company=board.replace("-", " ").title(),
            location=(raw.get("location") or "").strip(),
            remote=bool(raw.get("isRemote")) or workplace == "remote",
            posted_at=_parse_timestamp(raw.get("publishedAt")),
            apply_url=apply_url,
            description=description,
        )


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
