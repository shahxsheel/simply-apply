"""User-controlled LinkedIn job import.

LinkedIn does not expose a public job-search API and prohibits automated scraping.  This
route therefore accepts only content the user explicitly copied from a posting.  It
normalizes the URL, persists a regular ``Job`` row, and lets the existing durable
tailoring workflow take over from there.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Job
from app.schemas import JobRecord, LinkedInJobImport
from app.services.internship_filter import is_internship

router = APIRouter(prefix="/api/linkedin-jobs", tags=["linkedin-jobs"])

_LINKEDIN_JOB_ID = re.compile(r"(?:^|-)\b(\d{5,})$")


def _canonical_linkedin_url(value: str) -> str:
    raw = value.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        raise HTTPException(400, "Paste a LinkedIn job-posting URL.")
    if not parsed.path.rstrip("/").startswith("/jobs/"):
        raise HTTPException(400, "The LinkedIn URL must point to a job posting.")

    # Tracking parameters are unstable and can contain user-specific identifiers.  The
    # canonical URL is sufficient to reopen the posting and gives repeat imports one ID.
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", "www.linkedin.com", path, "", ""))


def _job_id(url: str) -> str:
    tail = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    match = _LINKEDIN_JOB_ID.search(tail)
    stable = match.group(1) if match else hashlib.sha256(url.encode()).hexdigest()[:20]
    return f"linkedin_manual:{stable}"


def _record(row: Job) -> JobRecord:
    return JobRecord(
        id=row.id,
        source=row.source,
        title=row.title,
        company=row.company,
        location=row.location,
        remote=row.remote,
        apply_url=row.apply_url,
        description=row.description,
    )


@router.post("", response_model=JobRecord)
def import_linkedin_job(
    payload: LinkedInJobImport, db: Session = Depends(get_db)
) -> JobRecord:
    title = payload.title.strip()
    company = payload.company.strip()
    description = payload.description.strip()
    if not is_internship(title, description):
        raise HTTPException(
            400,
            "This does not look like an internship. Include the complete posting "
            "description or check the job title.",
        )

    url = _canonical_linkedin_url(payload.url)
    row_id = _job_id(url)
    row = db.get(Job, row_id)
    values = {
        "source": "linkedin_manual",
        "title": title,
        "company": company,
        "location": payload.location.strip(),
        "remote": payload.remote,
        "apply_url": url,
        "description": description,
    }
    if row is None:
        row = Job(id=row_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _record(row)
