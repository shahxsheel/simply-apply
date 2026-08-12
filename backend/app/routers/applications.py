"""Local application tracker."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, Job
from app.schemas import ApplicationDetail, ApplicationOut

router = APIRouter(prefix="/api/applications", tags=["applications"])

STATUSES = ("prepared", "applied", "interviewing", "offer", "rejected", "withdrawn")


class ApplicationUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


def _fit_assessment(row: Application) -> tuple[str, str]:
    try:
        tailoring = json.loads(row.tailoring_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return "", ""

    review = tailoring.get("ats_review") if isinstance(tailoring, dict) else None
    if not isinstance(review, dict):
        return "", ""

    return str(review.get("match_level") or ""), str(review.get("summary") or "")


def _to_out(row: Application, job: Job | None) -> ApplicationOut:
    fit_match_level, fit_summary = _fit_assessment(row)
    return ApplicationOut(
        id=row.id,
        job_id=row.job_id,
        resume_id=row.resume_id,
        applied_at=row.applied_at,
        status=row.status,
        notes=row.notes,
        title=job.title if job else "",
        company=job.company if job else "",
        apply_url=job.apply_url if job else "",
        docx_url=f"/api/download/{row.id}/docx" if row.docx_path else None,
        pdf_url=f"/api/download/{row.id}/pdf" if row.pdf_path else None,
        workflow_status=row.workflow_status,
        workflow_step=row.workflow_step,
        workflow_progress=row.workflow_progress,
        workflow_detail=row.workflow_detail,
        workflow_error=row.workflow_error,
        fit_match_level=fit_match_level,
        fit_summary=fit_summary,
        llm_provider=row.llm_provider,
        llm_model=row.llm_model,
        llm_requests=row.llm_requests,
        input_tokens=row.input_tokens,
        cached_input_tokens=row.cached_input_tokens,
        cache_write_input_tokens=row.cache_write_input_tokens,
        output_tokens=row.output_tokens,
        reasoning_tokens=row.reasoning_tokens,
        estimated_cost_usd=row.estimated_cost_usd,
    )


def _to_detail(row: Application, job: Job | None) -> ApplicationDetail:
    data = _to_out(row, job).model_dump()
    try:
        events = json.loads(row.workflow_log or "[]")
    except (TypeError, json.JSONDecodeError):
        events = []
    try:
        tailoring = json.loads(row.tailoring_json) if row.tailoring_json else None
    except (TypeError, json.JSONDecodeError):
        tailoring = None
    return ApplicationDetail(
        **data,
        description=job.description if job else "",
        progress_events=events,
        tailoring=tailoring,
        pdf_error=row.pdf_error,
    )


@router.get("", response_model=list[ApplicationOut])
def list_applications(db: Session = Depends(get_db)) -> list[ApplicationOut]:
    rows = (
        db.execute(select(Application).order_by(Application.applied_at.desc()))
        .scalars()
        .all()
    )
    return [_to_out(row, db.get(Job, row.job_id)) for row in rows]


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(
    application_id: int, db: Session = Depends(get_db)
) -> ApplicationDetail:
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(404, "Application not found.")
    return _to_detail(row, db.get(Job, row.job_id))


@router.patch("/{application_id}", response_model=ApplicationOut)
def update_application(
    application_id: int, payload: ApplicationUpdate, db: Session = Depends(get_db)
) -> ApplicationOut:
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(404, "Application not found.")
    if payload.status is not None:
        if payload.status not in STATUSES:
            raise HTTPException(400, f"Status must be one of: {', '.join(STATUSES)}")
        row.status = payload.status
    if payload.notes is not None:
        row.notes = payload.notes
    db.commit()
    db.refresh(row)
    return _to_out(row, db.get(Job, row.job_id))


@router.delete("/{application_id}")
def delete_application(
    application_id: int, db: Session = Depends(get_db)
) -> dict[str, bool]:
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(404, "Application not found.")
    # Imported lazily to avoid a module cycle during router setup.
    from app.routers.apply import cancel_application_task

    cancel_application_task(application_id)
    db.delete(row)
    db.commit()
    return {"ok": True}
