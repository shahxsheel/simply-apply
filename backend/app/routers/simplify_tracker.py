"""Public Summer 2027 internship tracker backed by SimplifyJobs' repository."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Job
from app.schemas import JobRecord, SimplifyTrackerJob, SimplifyTrackerResponse
from app.services.job_page_scraper import JobDescriptionError, scrape_job_description
from app.services.simplify_tracker import get_tracker

router = APIRouter(prefix="/api", tags=["simplify-tracker"])


@router.get("/simplify-tracker", response_model=SimplifyTrackerResponse)
async def simplify_tracker(
    q: str = Query("", description="Company, role, location, or category"),
    category: str = Query(""),
    limit: int = Query(500, ge=1, le=500),
) -> SimplifyTrackerResponse:
    try:
        return await get_tracker(query=q, category=category, limit=limit)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc


def _posted_at(age: str) -> datetime | None:
    match = re.fullmatch(r"(\d+)(h|d|mo)", age.strip())
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2)
    delta = (
        timedelta(hours=value)
        if unit == "h"
        else timedelta(days=value if unit == "d" else value * 30)
    )
    return datetime.now(timezone.utc) - delta


def _as_record(job: SimplifyTrackerJob, description: str) -> JobRecord:
    return JobRecord(
        id=job.id,
        source="simplify_tracker",
        title=job.role,
        company=job.company,
        location=job.location,
        remote=job.remote,
        posted_at=_posted_at(job.age),
        apply_url=job.apply_url,
        description=description,
    )


def _persist(db: Session, record: JobRecord) -> None:
    row = db.get(Job, record.id)
    values = {
        "source": record.source,
        "title": record.title,
        "company": record.company,
        "location": record.location,
        "remote": record.remote,
        "posted_at": record.posted_at.replace(tzinfo=None) if record.posted_at else None,
        "apply_url": record.apply_url,
        "description": record.description,
        "fetched_at": datetime.now(timezone.utc).replace(tzinfo=None),
    }
    if row is None:
        db.add(Job(id=record.id, **values))
    else:
        for key, value in values.items():
            setattr(row, key, value)
    db.commit()


@router.post("/simplify-tracker/{job_id}/prepare", response_model=JobRecord)
async def prepare_tracker_job(
    job_id: str, db: Session = Depends(get_db)
) -> JobRecord:
    """Scrape and cache a tracker role so the normal /apply pipeline can consume it."""
    cached = db.get(Job, job_id)
    if cached is not None and cached.description:
        return JobRecord(
            id=cached.id,
            source=cached.source,
            title=cached.title,
            company=cached.company,
            location=cached.location,
            remote=cached.remote,
            posted_at=cached.posted_at,
            apply_url=cached.apply_url,
            description=cached.description,
        )

    try:
        tracker = await get_tracker(limit=10000)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    tracker_job = next((job for job in tracker.jobs if job.id == job_id), None)
    if tracker_job is None:
        raise HTTPException(404, "Tracker job is no longer available.")

    try:
        description = await scrape_job_description(tracker_job.apply_url)
    except JobDescriptionError as exc:
        raise HTTPException(422, str(exc)) from exc
    record = _as_record(tracker_job, description)
    _persist(db, record)
    return record
