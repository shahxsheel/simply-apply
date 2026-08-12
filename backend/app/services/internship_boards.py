"""Load internship-only snapshots from the two supported employer ATS providers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.ashby import AshbyConnector
from app.connectors.base import USER_AGENT
from app.connectors.greenhouse import GreenhouseConnector
from app.models import Job
from app.schemas import InternshipBoardResponse, JobRecord
from app.services import settings_store
from app.services.internship_filter import is_internship

InternshipBoard = Literal["ashby", "greenhouse"]


def _record(row: Job) -> JobRecord:
    return JobRecord(
        id=row.id,
        source=row.source,
        title=row.title,
        company=row.company,
        location=row.location,
        remote=row.remote,
        salary_min=row.salary_min,
        salary_max=row.salary_max,
        currency=row.currency,
        posted_at=row.posted_at,
        apply_url=row.apply_url,
        description=row.description,
    )


def _saved_internships(db: Session, board: InternshipBoard) -> list[JobRecord]:
    rows = db.execute(select(Job).where(Job.source == board)).scalars().all()
    return [
        _record(row)
        for row in rows
        if is_internship(row.title, row.description)
    ]


def _persist(db: Session, jobs: list[JobRecord]) -> None:
    fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    for job in jobs:
        row = db.get(Job, job.id)
        values = {
            "source": job.source,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "remote": job.remote,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "currency": job.currency,
            "posted_at": job.posted_at.replace(tzinfo=None) if job.posted_at else None,
            "apply_url": job.apply_url,
            "description": job.description,
            "fetched_at": fetched_at,
        }
        if row is None:
            db.add(Job(id=job.id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
    db.commit()


async def load_internship_board(
    db: Session, board: InternshipBoard
) -> InternshipBoardResponse:
    if board == "ashby":
        connector = AshbyConnector(settings_store.ashby_boards(db))
    else:
        connector = GreenhouseConnector(settings_store.greenhouse_companies(db))

    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True
        ) as client:
            jobs = await connector.fetch(client)
        # A second boundary check protects the product contract if a connector changes.
        internships = [
            job for job in jobs if is_internship(job.title, job.description)
        ]
        _persist(db, internships)
        internships.sort(
            key=lambda job: job.posted_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return InternshipBoardResponse(board=board, jobs=internships)
    except Exception as exc:
        saved = _saved_internships(db, board)
        if not saved:
            raise
        return InternshipBoardResponse(
            board=board,
            jobs=saved,
            warning=f"The live {board.title()} board could not be refreshed: {exc}",
        )
