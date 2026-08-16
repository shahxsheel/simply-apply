"""End-to-end test of the apply loop through the real FastAPI app.

Covers everything except the network hop to the LLM: resume storage, job lookup, tailor,
guardrail, DOCX render, application logging, and the download endpoint. The provider is
stubbed so the test is deterministic and needs no API key — but every other layer is the
real one, including SQLite and python-docx.
"""

from __future__ import annotations

from types import SimpleNamespace

import docx
import pytest
from fastapi.testclient import TestClient

BASE_RESUME = {
    "basics": {"name": "Jane Doe", "email": "jane@example.com", "summary": "Engineer."},
    "work": [
        {
            "name": "Acme Corp",
            "position": "Software Engineer",
            "startDate": "2022-01",
            "endDate": "2024-06",
            "highlights": ["Reduced p95 latency by 15% with a Redis cache."],
        }
    ],
    "education": [],
    "skills": [{"name": "Languages", "level": "", "keywords": ["Python"]}],
    "projects": [],
}

JOB = {
    "id": "greenhouse:acme:999",
    "source": "greenhouse",
    "title": "Senior Backend Engineer",
    "company": "Globex",
    "location": "Remote",
    "remote": True,
    "apply_url": "https://example.com/apply/999",
    "description": "Python, Redis, and Kubernetes.",
}


class _Stub:
    """Returns whatever resume it was given — honest or fabricated, per the test.

    Deliberately does NOT subclass LLMProvider or import app.schemas at module scope.
    The `client` fixture purges `app.*` from sys.modules to get a clean instance per
    test, which means any class imported up here would be a *stale* copy that pydantic
    rejects as a different type. Building the model inside the call keeps us on whatever
    module generation the app is currently running.
    """

    name = "stub"
    model = "stub-model"

    def __init__(self, fabricate: bool = False) -> None:
        self.fabricate = fabricate
        self.systems: list[str] = []
        self.token_usage = SimpleNamespace(
            requests=0,
            input_tokens=0,
            cached_input_tokens=0,
            cache_write_input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            estimated_cost_usd=None,
        )

    async def complete_structured(self, *, system, user, schema, max_tokens=16000):
        self.systems.append(system)
        self.token_usage.requests += 1
        self.token_usage.input_tokens += 100
        self.token_usage.output_tokens += 20
        if schema.__name__ == "ATSReview":
            return schema(
                match_level="Moderate",
                summary="The resume has relevant backend evidence.",
                strengths=["Python and Redis are supported."],
                suggested_changes=["Make impact clearer where possible."],
                keyword_gaps=["Kubernetes"],
            )
        resume = schema.model_validate(BASE_RESUME)
        resume.basics.summary = "Backend engineer specializing in Python and Redis."
        if self.fabricate:
            resume.skills.append(
                type(resume.skills[0])(name="Infra", keywords=["Kubernetes"])
            )
        return resume

    async def health(self):
        return True, "stub"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A fully isolated app instance with its own SQLite file and artifacts dir."""
    monkeypatch.setenv("SIMPLYAPPLY_DATA_DIR", str(tmp_path / "data"))

    # The engine, the settings cache, and the artifacts path are all module-level
    # singletons bound at import time. Dropping every `app.*` module forces them to be
    # rebuilt against this test's temp data dir, so tests can't leak state into each other.
    import sys

    for module in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[module]

    from app.db import init_db
    from app.main import app as fresh_app

    init_db()

    with TestClient(fresh_app) as c:
        yield c


def _seed(client, monkeypatch, fabricate: bool = False) -> _Stub:
    """Store a base resume, cache the job, and pin the LLM to the stub."""
    assert client.post(
        "/api/resumes", json={"name": "Base", "data": BASE_RESUME}
    ).status_code == 200

    from app.db import SessionLocal
    from app.models import Job

    with SessionLocal() as db:
        db.add(
            Job(
                id=JOB["id"],
                source=JOB["source"],
                title=JOB["title"],
                company=JOB["company"],
                location=JOB["location"],
                remote=JOB["remote"],
                apply_url=JOB["apply_url"],
                description=JOB["description"],
            )
        )
        db.commit()

    import app.routers.apply as apply_module

    provider = _Stub(fabricate)
    monkeypatch.setattr(apply_module, "build_provider", lambda db: provider)
    return provider


def test_health(client) -> None:
    assert client.get("/api/health").json()["status"] == "ok"


def test_dedicated_internship_board_endpoint_replaces_search(client, monkeypatch) -> None:
    import app.routers.internship_boards as board_module
    from app.schemas import InternshipBoardResponse

    async def fake_board(db, board):
        assert board == "greenhouse"
        return InternshipBoardResponse(board=board, jobs=[])

    monkeypatch.setattr(board_module, "load_internship_board", fake_board)
    response = client.get("/api/internship-boards/greenhouse")
    assert response.status_code == 200
    assert response.json()["board"] == "greenhouse"
    assert client.get("/api/search").status_code == 404


def test_linkedin_internship_import_is_saved_as_a_normal_job(client) -> None:
    response = client.post(
        "/api/linkedin-jobs",
        json={
            "url": (
                "https://www.linkedin.com/jobs/view/software-engineering-intern-"
                "at-acme-1234567890?trackingId=private"
            ),
            "title": "Software Engineering Intern — Summer 2027",
            "company": "Acme",
            "location": "Seattle, WA",
            "remote": False,
            "description": (
                "This software engineering internship is for currently enrolled "
                "students. You will build and test production Python services."
            ),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == "linkedin_manual:1234567890"
    assert body["source"] == "linkedin_manual"
    assert body["apply_url"] == (
        "https://www.linkedin.com/jobs/view/"
        "software-engineering-intern-at-acme-1234567890"
    )
    assert "trackingId" not in body["apply_url"]
    assert "currently enrolled" in body["description"]


def test_linkedin_import_rejects_non_linkedin_and_non_internship_jobs(client) -> None:
    common = {
        "title": "Software Engineer",
        "company": "Acme",
        "description": "A permanent software engineering role for experienced candidates.",
    }
    wrong_host = client.post(
        "/api/linkedin-jobs",
        json={**common, "url": "https://example.com/jobs/123"},
    )
    # Internship classification happens before URL normalization, and both inputs are
    # intentionally invalid.  Check each condition independently below.
    assert wrong_host.status_code == 400

    non_internship = client.post(
        "/api/linkedin-jobs",
        json={**common, "url": "https://www.linkedin.com/jobs/view/123456"},
    )
    assert non_internship.status_code == 400
    assert "internship" in non_internship.json()["detail"].lower()

    wrong_host_internship = client.post(
        "/api/linkedin-jobs",
        json={
            **common,
            "title": "Software Engineer Intern",
            "description": "A software engineering internship for currently enrolled students.",
            "url": "https://example.com/jobs/123",
        },
    )
    assert wrong_host_internship.status_code == 400
    assert "linkedin" in wrong_host_internship.json()["detail"].lower()


def test_generic_job_import_accepts_any_http_job_site_and_role(client) -> None:
    response = client.post(
        "/api/job-imports",
        json={
            "url": "jobs.example.com/openings/staff-engineer?ref=board#details",
            "title": "Staff Software Engineer",
            "company": "Example Labs",
            "location": "New York, NY",
            "remote": True,
            "description": (
                "Lead the design and delivery of reliable distributed systems while "
                "mentoring engineers and partnering with product teams."
            ),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"].startswith("manual_import:")
    assert body["source"] == "manual_import"
    assert body["title"] == "Staff Software Engineer"
    assert body["remote"] is True
    assert body["apply_url"] == (
        "https://jobs.example.com/openings/staff-engineer?ref=board"
    )


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///tmp/posting.html",
        "https://user:secret@example.com/jobs/123",
        "not a valid url",
    ],
)
def test_generic_job_import_rejects_unsafe_or_invalid_urls(client, url) -> None:
    response = client.post(
        "/api/job-imports",
        json={
            "url": url,
            "title": "Software Engineer",
            "company": "Example Labs",
            "description": (
                "Build and maintain production systems with a collaborative "
                "engineering team using modern software practices."
            ),
        },
    )

    assert response.status_code == 400


def test_generic_job_import_rejects_blank_required_copy(client) -> None:
    response = client.post(
        "/api/job-imports",
        json={
            "url": "https://jobs.example.com/roles/123",
            "title": "   ",
            "company": "Example Labs",
            "description": " " * 40,
        },
    )

    assert response.status_code == 400


def test_generic_job_reimport_updates_one_stable_record(client) -> None:
    payload = {
        "url": "https://careers.example.com/jobs/42#overview",
        "title": "Platform Engineer",
        "company": "Example",
        "description": "Build and operate a reliable platform for product engineering teams.",
    }
    first = client.post("/api/job-imports", json=payload)
    second = client.post(
        "/api/job-imports",
        json={
            **payload,
            "title": "Senior Platform Engineer",
            "description": (
                "Build and operate a reliable platform for product engineering teams "
                "and lead cross-functional infrastructure projects."
            ),
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert second.json()["title"] == "Senior Platform Engineer"


def test_apply_without_resume_is_a_clear_error(client, monkeypatch) -> None:
    from app.db import SessionLocal
    from app.models import Job

    with SessionLocal() as db:
        db.add(Job(id=JOB["id"], source="x", title="T", company="C", apply_url="u"))
        db.commit()

    import app.routers.apply as apply_module

    monkeypatch.setattr(apply_module, "build_provider", lambda db: _Stub())
    res = client.post(f"/api/apply/{JOB['id']}")
    assert res.status_code == 400
    assert "base resume" in res.json()["detail"].lower()


def test_apply_produces_a_downloadable_docx(client, monkeypatch, tmp_path) -> None:
    _seed(client, monkeypatch)

    res = client.post(f"/api/apply/{JOB['id']}")
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["tailoring"]["fell_back"] is False
    assert body["tailoring"]["violations"] == []
    assert body["tailoring"]["ats_review"]["match_level"] == "Moderate"
    assert body["docx_url"]

    download = client.get(body["docx_url"])
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats"
    )

    # Read the real file back the way an ATS would.
    out = tmp_path / "downloaded.docx"
    out.write_bytes(download.content)
    text = "\n".join(p.text for p in docx.Document(str(out)).paragraphs)
    assert "Jane Doe" in text
    assert "Acme Corp" in text
    assert "15%" in text


def test_apply_logs_the_application(client, monkeypatch) -> None:
    _seed(client, monkeypatch)
    client.post(f"/api/apply/{JOB['id']}")

    rows = client.get("/api/applications").json()
    assert len(rows) == 1
    assert rows[0]["company"] == "Globex"
    assert rows[0]["status"] == "prepared"
    assert rows[0]["apply_url"] == JOB["apply_url"]
    assert rows[0]["fit_match_level"] == "Moderate"
    assert rows[0]["fit_summary"] == "The resume has relevant backend evidence."


async def test_background_tailoring_is_visible_before_and_after_completion(
    client, monkeypatch
) -> None:
    """Refreshing the UI must find the durable row while tailoring continues."""
    _seed(client, monkeypatch)

    import app.routers.apply as apply_module

    launched: list[int] = []
    monkeypatch.setattr(
        apply_module,
        "_launch_application_task",
        lambda application_id: launched.append(application_id),
    )

    started = client.post(
        "/api/applications/tailor",
        json={"job_id": JOB["id"]},
    )
    assert started.status_code == 202, started.text
    application_id = started.json()["id"]
    assert launched == [application_id]
    assert started.json()["workflow_status"] == "queued"
    assert client.get("/api/applications").json()[0]["workflow_step"] == "queued"

    # Simulate a prior interrupted attempt. Recovery must add the next provider
    # session instead of erasing already-spent tokens.
    from app.db import SessionLocal
    from app.models import Application

    with SessionLocal() as db:
        application = db.get(Application, application_id)
        application.llm_requests = 1
        application.input_tokens = 50
        application.output_tokens = 10
        application.estimated_cost_usd = 0.01
        db.commit()

    await apply_module._process_application(application_id)

    detail = client.get(f"/api/applications/{application_id}").json()
    assert detail["workflow_status"] == "completed"
    assert detail["workflow_progress"] == 100
    assert detail["fit_match_level"] == "Moderate"
    assert detail["fit_summary"] == "The resume has relevant backend evidence."
    assert detail["description"] == JOB["description"]
    assert detail["docx_url"]
    assert detail["pdf_url"]
    assert detail["llm_provider"] == "stub"
    assert detail["llm_model"] == "stub-model"
    assert detail["llm_requests"] == 3
    assert detail["input_tokens"] == 250
    assert detail["output_tokens"] == 50
    assert detail["estimated_cost_usd"] == pytest.approx(0.01)
    steps = [event["step"] for event in detail["progress_events"]]
    assert steps == [
        "queued",
        "description_ready",
        "tailoring",
        "verifying",
        "ats_review",
        "rendering",
        "completed",
    ]


async def test_task_launch_is_idempotent_and_shutdown_cancels_workers(
    client, monkeypatch
) -> None:
    import asyncio
    import app.routers.apply as apply_module

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def wait_forever(application_id: int) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(apply_module, "_process_application", wait_forever)

    assert apply_module._launch_application_task(42) is True
    assert apply_module._launch_application_task(42) is False
    await started.wait()
    assert list(apply_module._running_tasks) == [42]

    await apply_module.shutdown_application_tasks()
    assert cancelled.is_set()
    await asyncio.sleep(0)
    assert apply_module._running_tasks == {}


def test_startup_recovers_only_queued_and_running_rows_once(client, monkeypatch) -> None:
    _seed(client, monkeypatch)

    from app.db import SessionLocal
    from app.models import Application, Resume
    import app.routers.apply as apply_module

    with SessionLocal() as db:
        base = db.query(Resume).filter(Resume.is_base.is_(True)).one()
        applications = []
        for status in ("queued", "running", "failed", "completed"):
            resume = Resume(
                name=f"Recovered {status}",
                structured_json=base.structured_json,
                is_base=False,
                base_resume_id=base.id,
                tailored_for_job_id=JOB["id"],
            )
            db.add(resume)
            db.flush()
            application = Application(
                job_id=JOB["id"],
                resume_id=resume.id,
                workflow_status=status,
                workflow_step=status,
                workflow_progress=25,
            )
            db.add(application)
            db.flush()
            applications.append(application.id)
        db.commit()

    launched: list[int] = []

    def launch(application_id: int) -> bool:
        launched.append(application_id)
        return True

    monkeypatch.setattr(apply_module, "_launch_application_task", launch)

    # A second app lifespan simulates a backend restart against the same durable DB.
    with TestClient(client.app):
        pass

    assert launched == applications[:2]


def test_fabricating_model_falls_back_and_warns(client, monkeypatch, tmp_path) -> None:
    """The whole point of the system: a bad model must not produce a bad resume."""
    _seed(client, monkeypatch, fabricate=True)

    body = client.post(f"/api/apply/{JOB['id']}").json()

    assert body["tailoring"]["fell_back"] is True
    assert body["tailoring"]["warning"]
    assert any(v["value"] == "Kubernetes" for v in body["tailoring"]["violations"])

    # And the rendered file must be the honest one — no Kubernetes in the DOCX.
    out = tmp_path / "fallback.docx"
    out.write_bytes(client.get(body["docx_url"]).content)
    text = "\n".join(p.text for p in docx.Document(str(out)).paragraphs)
    assert "Kubernetes" not in text
    assert "Python" in text


def test_apply_produces_a_single_page_pdf(client, monkeypatch, tmp_path) -> None:
    """PDF now works on every install and must be exactly one page — the guarantee."""
    import pypdfium2 as pdfium

    _seed(client, monkeypatch)

    body = client.post(f"/api/apply/{JOB['id']}").json()
    assert body["pdf_url"]
    assert body["pdf_error"] is None

    download = client.get(body["pdf_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"

    out = tmp_path / "downloaded.pdf"
    out.write_bytes(download.content)
    assert download.content[:5] == b"%PDF-"  # real PDF header, not an error page

    pdf = pdfium.PdfDocument(str(out))
    try:
        assert len(pdf) == 1, f"PDF must be a single page, got {len(pdf)}"
    finally:
        pdf.close()


def test_tracker_job_is_scraped_then_uses_normal_apply_pipeline(client, monkeypatch) -> None:
    """Tracker roles become normal cached jobs before tailoring starts."""
    _seed(client, monkeypatch)

    import app.routers.simplify_tracker as tracker_module
    from app.schemas import SimplifyTrackerJob, SimplifyTrackerResponse
    from datetime import datetime, timezone

    tracker_job = SimplifyTrackerJob(
        id="simplify-2027:direct-test",
        company="Direct Corp",
        role="Software Engineer Intern",
        location="Seattle, WA",
        category="Software Engineering",
        age="0d",
        apply_url="https://careers.example.com/jobs/1",
    )

    async def fake_tracker(**kwargs):
        return SimplifyTrackerResponse(
            jobs=[tracker_job],
            total=1,
            fetched_at=datetime.now(timezone.utc),
            source_url="https://github.com/example/tracker",
        )

    async def fake_scrape(url: str) -> str:
        assert url == tracker_job.apply_url
        return "Job Description\nBuild Python and Redis services with the backend team."

    monkeypatch.setattr(tracker_module, "get_tracker", fake_tracker)
    monkeypatch.setattr(tracker_module, "scrape_job_description", fake_scrape)

    prepared = client.post(
        f"/api/simplify-tracker/{tracker_job.id}/prepare"
    )
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["description"].startswith("Job Description")
    assert prepared.json()["source"] == "simplify_tracker"

    applied = client.post(f"/api/apply/{tracker_job.id}")
    assert applied.status_code == 200, applied.text
    assert applied.json()["job"]["company"] == "Direct Corp"


def test_pdf_render_failure_is_reported_not_fatal(client, monkeypatch) -> None:
    """A render bug must degrade to DOCX-only for that apply, not 500 the request."""
    import app.services.render_pdf as pdf_module
    import app.routers.apply as apply_module

    _seed(client, monkeypatch)
    monkeypatch.setattr(
        apply_module,
        "render_pdf",
        lambda resume, path: (_ for _ in ()).throw(
            pdf_module.PDFRenderError("simulated render failure")
        ),
    )

    res = client.post(f"/api/apply/{JOB['id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["docx_url"]
    assert body["pdf_url"] is None
    assert "simulated render failure" in body["pdf_error"]


def test_download_rejects_unknown_format(client, monkeypatch) -> None:
    _seed(client, monkeypatch)
    app_id = client.post(f"/api/apply/{JOB['id']}").json()["application_id"]
    assert client.get(f"/api/download/{app_id}/exe").status_code == 400


def test_settings_never_returns_the_api_key(client) -> None:
    client.put("/api/settings", json={"llm_provider": "openai", "api_key": "sk-secret"})
    body = client.get("/api/settings").json()
    assert body["has_key"] is True
    assert "sk-secret" not in str(body)


def test_settings_exposes_updates_and_resets_tailoring_prompt(client) -> None:
    default = client.get("/api/settings").json()
    assert "RECRUITER EYE-SCAN AND REVISION PASS" in default["tailor_system_prompt"]
    assert default["tailor_system_prompt_is_custom"] is False

    custom_prompt = "Prioritize concise evidence supported by the base resume."
    updated = client.put(
        "/api/settings", json={"tailor_system_prompt": custom_prompt}
    )
    assert updated.status_code == 200
    assert updated.json()["tailor_system_prompt"] == custom_prompt
    assert updated.json()["tailor_system_prompt_is_custom"] is True

    reset = client.put("/api/settings", json={"tailor_system_prompt": ""})
    assert reset.status_code == 200
    assert "RECRUITER EYE-SCAN AND REVISION PASS" in reset.json()[
        "tailor_system_prompt"
    ]
    assert reset.json()["tailor_system_prompt_is_custom"] is False


def test_apply_uses_saved_tailoring_system_prompt(client, monkeypatch) -> None:
    provider = _seed(client, monkeypatch)
    custom_prompt = "Use this exact custom resume tailoring instruction."
    assert client.put(
        "/api/settings", json={"tailor_system_prompt": custom_prompt}
    ).status_code == 200

    response = client.post(f"/api/apply/{JOB['id']}")

    assert response.status_code == 200, response.text
    assert provider.systems[0] == custom_prompt
