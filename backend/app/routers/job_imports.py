"""User-controlled import for a posting from any job site.

The server deliberately does not fetch the supplied URL here. The user provides the
posting text, which keeps this workflow compatible with sites that require sign-in or
block automated readers while still feeding the normal durable tailoring pipeline.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Job
from app.schemas import JobImport, JobRecord

router = APIRouter(prefix="/api/job-imports", tags=["job-imports"])


def _canonical_job_url(value: str) -> str:
    raw = value.strip()
    initial = urlsplit(raw)
    if initial.scheme and initial.scheme.lower() not in {"http", "https"}:
        raise HTTPException(400, "Job URL must use http or https.")
    if not initial.scheme:
        raw = f"https://{raw}"

    parsed = urlsplit(raw)
    host = parsed.hostname
    if not host or any(character.isspace() for character in host):
        raise HTTPException(400, "Enter a valid job-posting URL.")
    if parsed.username or parsed.password:
        raise HTTPException(400, "Job URLs cannot contain a username or password.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(400, "Enter a valid job-posting URL.") from exc

    normalized_host = host.encode("idna").decode("ascii").lower().rstrip(".")
    if ":" in normalized_host:
        normalized_host = f"[{normalized_host}]"
    netloc = f"{normalized_host}:{port}" if port else normalized_host
    return urlunsplit(
        (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, "")
    )


def _job_id(url: str) -> str:
    return f"manual_import:{hashlib.sha256(url.encode()).hexdigest()[:24]}"


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
def import_job(payload: JobImport, db: Session = Depends(get_db)) -> JobRecord:
    url = _canonical_job_url(payload.url)
    row_id = _job_id(url)
    title = payload.title.strip()
    company = payload.company.strip()
    description = payload.description.strip()
    if not title or not company:
        raise HTTPException(400, "Job title and company are required.")
    if len(description) < 40:
        raise HTTPException(400, "Paste at least 40 characters of the job description.")
    values = {
        "source": "manual_import",
        "title": title,
        "company": company,
        "location": payload.location.strip(),
        "remote": payload.remote,
        "apply_url": url,
        "description": description,
    }

    row = db.get(Job, row_id)
    if row is None:
        row = Job(id=row_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _record(row)
