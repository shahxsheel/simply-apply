"""The apply loop: tailor → guardrail → render → log → hand off.

Deliberately does not submit anything. The user downloads their files and clicks Submit
on the employer's own form. That's a product decision from the PRD, not a limitation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.llm.base import LLMError
from app.llm.registry import build_provider
from app.models import Application, Job, Resume
from app.schemas import (
    ApplicationOut,
    ApplyResponse,
    JobRecord,
    StructuredResume,
    TailorStartRequest,
)
from app.services.job_page_scraper import JobDescriptionError, scrape_job_description
from app.services.render_docx import render_docx
from app.services.render_pdf import PDFRenderError, render_pdf
from app.services.tailor import tailor

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["apply"])

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_running_tasks: dict[int, asyncio.Task[None]] = {}


def _slug(value: str, fallback: str = "resume") -> str:
    cleaned = _UNSAFE.sub("-", (value or "").strip()).strip("-")
    return (cleaned or fallback)[:60]


def _job_record(row: Job) -> JobRecord:
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


def _application_out(application: Application, job: Job) -> ApplicationOut:
    return ApplicationOut(
        id=application.id,
        job_id=application.job_id,
        resume_id=application.resume_id,
        applied_at=application.applied_at,
        status=application.status,
        notes=application.notes,
        title=job.title,
        company=job.company,
        apply_url=job.apply_url,
        docx_url=(
            f"/api/download/{application.id}/docx" if application.docx_path else None
        ),
        pdf_url=f"/api/download/{application.id}/pdf" if application.pdf_path else None,
        workflow_status=application.workflow_status,
        workflow_step=application.workflow_step,
        workflow_progress=application.workflow_progress,
        workflow_detail=application.workflow_detail,
        workflow_error=application.workflow_error,
        llm_provider=application.llm_provider,
        llm_model=application.llm_model,
        llm_requests=application.llm_requests,
        input_tokens=application.input_tokens,
        cached_input_tokens=application.cached_input_tokens,
        cache_write_input_tokens=application.cache_write_input_tokens,
        output_tokens=application.output_tokens,
        reasoning_tokens=application.reasoning_tokens,
        estimated_cost_usd=application.estimated_cost_usd,
    )


def _set_progress(
    db: Session,
    application: Application,
    step: str,
    detail: str,
    progress: int,
    *,
    status: str = "running",
) -> None:
    try:
        events = json.loads(application.workflow_log or "[]")
    except (TypeError, json.JSONDecodeError):
        events = []
    events.append(
        {
            "step": step,
            "detail": detail,
            "progress": progress,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    application.workflow_status = status
    application.workflow_step = step
    application.workflow_progress = progress
    application.workflow_detail = detail
    application.workflow_log = json.dumps(events)
    db.commit()


def _mark_failure(db: Session, application_id: int, message: str) -> None:
    db.rollback()
    application = db.get(Application, application_id)
    if application is None:  # the user removed the tracker row while it was running
        return
    application.workflow_error = message
    _set_progress(
        db,
        application,
        "failed",
        message,
        application.workflow_progress,
        status="failed",
    )


def _save_provider_usage(application: Application, provider: object) -> None:
    application.llm_provider = str(getattr(provider, "name", "") or "")
    application.llm_model = str(getattr(provider, "model", "") or "")
    usage = getattr(provider, "token_usage", None)
    if usage is None:
        return
    # A queued/running application may be resumed after a process restart. Preserve the
    # tokens already spent by the interrupted attempt and add the new provider session.
    application.llm_requests = (application.llm_requests or 0) + usage.requests
    application.input_tokens = (application.input_tokens or 0) + usage.input_tokens
    application.cached_input_tokens = (
        application.cached_input_tokens or 0
    ) + usage.cached_input_tokens
    application.cache_write_input_tokens = (
        application.cache_write_input_tokens or 0
    ) + usage.cache_write_input_tokens
    application.output_tokens = (application.output_tokens or 0) + usage.output_tokens
    application.reasoning_tokens = (
        application.reasoning_tokens or 0
    ) + usage.reasoning_tokens
    if usage.estimated_cost_usd is not None:
        application.estimated_cost_usd = (
            application.estimated_cost_usd or 0
        ) + usage.estimated_cost_usd


async def _process_application(application_id: int) -> None:
    """Run the expensive pipeline independently of the browser request."""
    with SessionLocal() as db:
        application = db.get(Application, application_id)
        if application is None:
            return
        job_row = db.get(Job, application.job_id)
        tailored_row = db.get(Resume, application.resume_id)
        base_row = (
            db.get(Resume, tailored_row.base_resume_id)
            if tailored_row and tailored_row.base_resume_id
            else None
        )
        if job_row is None or tailored_row is None or base_row is None:
            _set_progress(
                db,
                application,
                "failed",
                "The saved job or base resume could not be found.",
                application.workflow_progress,
                status="failed",
            )
            application.workflow_error = application.workflow_detail
            db.commit()
            return

        provider: object | None = None
        provider_usage_saved = False
        try:
            if not job_row.description.strip():
                _set_progress(
                    db,
                    application,
                    "scraping",
                    "Reading the employer page and locating the job description.",
                    10,
                )
                job_row.description = await scrape_job_description(job_row.apply_url)
                job_row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.commit()
                _set_progress(
                    db,
                    application,
                    "description_ready",
                    "Job description extracted and saved.",
                    25,
                )
            else:
                _set_progress(
                    db,
                    application,
                    "description_ready",
                    "Using the job description already saved from this posting.",
                    25,
                )

            base_resume = StructuredResume.model_validate_json(base_row.structured_json)
            provider = build_provider(db)
            result = await tailor(
                provider,
                base_resume,
                _job_record(job_row),
                progress=lambda step, detail, value: _set_progress(
                    db, application, step, detail, value
                ),
            )

            _save_provider_usage(application, provider)
            provider_usage_saved = True
            tailored_row.structured_json = result.resume.model_dump_json()
            db.commit()
            _set_progress(
                db,
                application,
                "rendering",
                "Rendering the one-page Jake resume as DOCX and PDF.",
                85,
            )

            settings = get_settings()
            stem = (
                f"{_slug(result.resume.basics.name, 'resume')}-"
                f"{_slug(job_row.company, 'company')}-{tailored_row.id}"
            )
            docx_path = settings.artifacts_dir / f"{stem}.docx"
            pdf_path = settings.artifacts_dir / f"{stem}.pdf"
            render_docx(result.resume, docx_path)

            pdf_error: str | None = None
            try:
                render_pdf(result.resume, pdf_path)
            except PDFRenderError as exc:
                pdf_error = str(exc)
                pdf_path = None  # type: ignore[assignment]
                log.warning("background apply: PDF render failed — %s", exc)

            application.docx_path = str(docx_path)
            application.pdf_path = str(pdf_path) if pdf_path else None
            application.pdf_error = pdf_error
            application.tailoring_json = result.model_dump_json()
            application.workflow_error = None
            db.commit()
            _set_progress(
                db,
                application,
                "completed",
                "Tailored resume, ATS review, and downloads are ready.",
                100,
                status="completed",
            )
        except (JobDescriptionError, LLMError) as exc:
            log.warning("background apply %s failed: %s", application_id, exc)
            if provider is not None:
                _save_provider_usage(application, provider)
                db.commit()
            _mark_failure(db, application_id, str(exc))
        except asyncio.CancelledError:
            db.rollback()
            if provider is not None and not provider_usage_saved:
                # Preserve any completed provider calls from this attempt before the
                # durable queued/running row is resumed by the next process.
                application = db.get(Application, application_id)
                if application is not None:
                    _save_provider_usage(application, provider)
                    db.commit()
            return
        except Exception as exc:  # rendering/storage failures still need a durable state
            log.exception("background apply %s failed unexpectedly", application_id)
            message = f"Tailoring failed: {exc}"
            _mark_failure(db, application_id, message)


def _launch_application_task(application_id: int) -> bool:
    existing = _running_tasks.get(application_id)
    if existing is not None and not existing.done():
        return False

    task = asyncio.get_running_loop().create_task(_process_application(application_id))
    _running_tasks[application_id] = task

    def forget(completed: asyncio.Task[None]) -> None:
        if _running_tasks.get(application_id) is completed:
            _running_tasks.pop(application_id, None)

    task.add_done_callback(forget)
    return True


def recover_incomplete_application_tasks() -> int:
    """Resume durable work that was queued or running when the process stopped."""
    with SessionLocal() as db:
        application_ids = [
            application_id
            for (application_id,) in (
                db.query(Application.id)
                .filter(Application.workflow_status.in_(("queued", "running")))
                .order_by(Application.id)
                .all()
            )
        ]

    return sum(
        _launch_application_task(application_id)
        for application_id in application_ids
    )


async def shutdown_application_tasks() -> None:
    """Cancel in-memory workers while leaving their durable progress resumable."""
    tasks = [task for task in _running_tasks.values() if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def cancel_application_task(application_id: int) -> None:
    task = _running_tasks.get(application_id)
    if task is not None and not task.done():
        task.cancel()


@router.post("/applications/tailor", response_model=ApplicationOut, status_code=202)
async def start_tailoring(
    payload: TailorStartRequest, db: Session = Depends(get_db)
) -> ApplicationOut:
    """Create a visible tracker row immediately, then tailor it in the background."""
    base_row = (
        db.query(Resume)
        .filter(Resume.is_base.is_(True))
        .order_by(Resume.created_at.desc())
        .first()
    )
    if base_row is None:
        raise HTTPException(
            400, "No base resume yet. Upload and confirm one on the Resume page first."
        )

    existing_application = (
        db.query(Application)
        .filter(Application.job_id == payload.job_id)
        .order_by(Application.id.desc())
        .first()
    )
    if existing_application is not None:
        existing_job = db.get(Job, payload.job_id)
        if existing_job is not None:
            return _application_out(existing_application, existing_job)

    job_row = db.get(Job, payload.job_id)
    if job_row is None:
        if not all((payload.title, payload.company, payload.apply_url)):
            raise HTTPException(404, "Job not found and listing details were incomplete.")
        job_row = Job(
            id=payload.job_id,
            source=payload.source or "tracker",
            title=payload.title,
            company=payload.company,
            location=payload.location,
            remote=payload.remote,
            apply_url=payload.apply_url,
            description="",
        )
        db.add(job_row)
    else:
        for name in ("source", "title", "company", "location", "apply_url"):
            value = getattr(payload, name)
            if value:
                setattr(job_row, name, value)
        job_row.remote = payload.remote or job_row.remote

    tailored_row = Resume(
        name=f"{job_row.company} — {job_row.title}",
        structured_json=base_row.structured_json,
        is_base=False,
        base_resume_id=base_row.id,
        tailored_for_job_id=job_row.id,
    )
    db.add(tailored_row)
    db.flush()

    now = datetime.now(timezone.utc)
    queued_detail = "Queued. The job description will be prepared next."
    application = Application(
        job_id=job_row.id,
        resume_id=tailored_row.id,
        applied_at=now.replace(tzinfo=None),
        status="prepared",
        workflow_status="queued",
        workflow_step="queued",
        workflow_progress=0,
        workflow_detail=queued_detail,
        workflow_log=json.dumps(
            [
                {
                    "step": "queued",
                    "detail": queued_detail,
                    "progress": 0,
                    "at": now.isoformat(),
                }
            ]
        ),
    )
    db.add(application)
    db.commit()
    db.refresh(application)

    response = _application_out(application, job_row)
    _launch_application_task(application.id)
    return response


@router.post("/apply/{job_id:path}", response_model=ApplyResponse)
async def apply(job_id: str, db: Session = Depends(get_db)) -> ApplyResponse:
    settings = get_settings()

    job_row = db.get(Job, job_id)
    if job_row is None:
        raise HTTPException(404, "Job not found. Open its internship board first.")

    base_row = (
        db.query(Resume)
        .filter(Resume.is_base.is_(True))
        .order_by(Resume.created_at.desc())
        .first()
    )
    if base_row is None:
        raise HTTPException(
            400, "No base resume yet. Upload and confirm one on the Resume page first."
        )

    base_resume = StructuredResume.model_validate_json(base_row.structured_json)
    job = _job_record(job_row)

    try:
        provider = build_provider(db)
        result = await tailor(provider, base_resume, job)
    except LLMError as exc:
        raise HTTPException(400, str(exc)) from exc

    # Persist the exact document that gets rendered — including the fallback case, so the
    # application log always points at what was actually sent.
    tailored_row = Resume(
        name=f"{job.company} — {job.title}",
        structured_json=result.resume.model_dump_json(),
        is_base=False,
        base_resume_id=base_row.id,
        tailored_for_job_id=job.id,
    )
    db.add(tailored_row)
    db.commit()
    db.refresh(tailored_row)

    stem = f"{_slug(result.resume.basics.name, 'resume')}-{_slug(job.company, 'company')}-{tailored_row.id}"
    docx_path = settings.artifacts_dir / f"{stem}.docx"
    pdf_path = settings.artifacts_dir / f"{stem}.pdf"

    render_docx(result.resume, docx_path)

    # The PDF is a pure-Python render now, so it works on every install. We still guard
    # it: a rendering bug should degrade to "DOCX only" for this one apply rather than
    # 500 the whole request and lose the tailored document the user already generated.
    pdf_error: str | None = None
    try:
        render_pdf(result.resume, pdf_path)
    except PDFRenderError as exc:
        pdf_error = str(exc)
        pdf_path = None  # type: ignore[assignment]
        log.warning("apply: PDF render failed — %s", exc)

    application = Application(
        job_id=job.id,
        resume_id=tailored_row.id,
        applied_at=datetime.now(timezone.utc).replace(tzinfo=None),
        status="prepared",
        docx_path=str(docx_path),
        pdf_path=str(pdf_path) if pdf_path else None,
        workflow_status="completed",
        workflow_step="completed",
        workflow_progress=100,
        workflow_detail="Tailored resume, ATS review, and downloads are ready.",
        workflow_log=json.dumps(
            [
                {
                    "step": "completed",
                    "detail": "Tailored resume, ATS review, and downloads are ready.",
                    "progress": 100,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        ),
        tailoring_json=result.model_dump_json(),
        pdf_error=pdf_error,
    )
    _save_provider_usage(application, provider)
    db.add(application)
    db.commit()
    db.refresh(application)

    return ApplyResponse(
        application_id=application.id,
        resume_id=tailored_row.id,
        job=job,
        docx_url=f"/api/download/{application.id}/docx",
        pdf_url=f"/api/download/{application.id}/pdf" if pdf_path else None,
        pdf_error=pdf_error,
        tailoring=result,
    )


@router.get("/download/{application_id}/{fmt}")
def download(
    application_id: int, fmt: str, db: Session = Depends(get_db)
) -> FileResponse:
    if fmt not in ("docx", "pdf"):
        raise HTTPException(400, "Format must be 'docx' or 'pdf'.")

    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(404, "Application not found.")

    raw_path = application.docx_path if fmt == "docx" else application.pdf_path
    if not raw_path:
        raise HTTPException(404, f"No {fmt.upper()} was generated for this application.")

    path = Path(raw_path).resolve()

    # The path came from our own DB, but resolve-and-contain anyway: this endpoint returns
    # file bytes, and a containment check is cheap insurance against a future code path
    # that lets a value in here from somewhere less trustworthy.
    artifacts_dir = get_settings().artifacts_dir.resolve()
    if not path.is_relative_to(artifacts_dir):
        raise HTTPException(400, "Refusing to serve a file outside the artifacts directory.")
    if not path.exists():
        raise HTTPException(404, "The generated file is missing. Re-run Apply.")

    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if fmt == "docx"
        else "application/pdf"
    )
    return FileResponse(path, media_type=media_type, filename=path.name)
