"""Pydantic contracts shared by the API, the LLM layer, and the renderers.

The resume shape is a subset of the JSON Resume standard (https://jsonresume.org) rather
than a bespoke schema. That buys interop with existing themes/tooling and means a
contributor already knows the field names.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- jobs


class JobRecord(BaseModel):
    """Normalized posting. Every connector returns these, whatever the upstream shape."""

    id: str
    source: str
    title: str
    company: str
    location: str = ""
    remote: bool = False
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    posted_at: datetime | None = None
    apply_url: str
    description: str = ""


class InternshipBoardResponse(BaseModel):
    """Internship-only snapshot from one employer ATS provider."""

    board: str
    jobs: list[JobRecord]
    warning: str | None = None


class SimplifyTrackerJob(BaseModel):
    """One open role scraped from Simplify's public Summer 2027 repository."""

    id: str
    company: str
    role: str
    location: str = ""
    category: str
    age: str = ""
    apply_url: str
    flags: list[str] = Field(default_factory=list)
    remote: bool = False


class SimplifyTrackerResponse(BaseModel):
    jobs: list[SimplifyTrackerJob]
    total: int
    fetched_at: datetime
    source_url: str
    stale: bool = False
    warning: str | None = None


class LinkedInJobImport(BaseModel):
    """A LinkedIn posting copied by the user; the server never fetches LinkedIn."""

    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=400)
    company: str = Field(min_length=1, max_length=300)
    location: str = Field(default="", max_length=300)
    remote: bool = False
    description: str = Field(min_length=40, max_length=100_000)


class JobImport(BaseModel):
    """A posting copied by the user from any HTTP(S) job site."""

    url: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=400)
    company: str = Field(min_length=1, max_length=300)
    location: str = Field(default="", max_length=300)
    remote: bool = False
    description: str = Field(min_length=40, max_length=100_000)


# ------------------------------------------------------------------------ resume


class Location(BaseModel):
    city: str = ""
    region: str = ""
    countryCode: str = ""


class Profile(BaseModel):
    network: str = ""
    username: str = ""
    url: str = ""


class Basics(BaseModel):
    name: str = ""
    label: str = ""
    email: str = ""
    phone: str = ""
    url: str = ""
    summary: str = ""
    location: Location = Field(default_factory=Location)
    profiles: list[Profile] = Field(default_factory=list)


class Work(BaseModel):
    name: str = ""  # employer — JSON Resume calls this `name`
    position: str = ""
    url: str = ""
    startDate: str = ""
    endDate: str = ""
    location: str = ""
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str = ""
    area: str = ""
    studyType: str = ""
    startDate: str = ""
    endDate: str = ""
    score: str = ""
    courses: list[str] = Field(default_factory=list)


class Skill(BaseModel):
    name: str = ""
    level: str = ""
    keywords: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    description: str = ""
    url: str = ""
    startDate: str = ""
    endDate: str = ""
    highlights: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class StructuredResume(BaseModel):
    basics: Basics = Field(default_factory=Basics)
    work: list[Work] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)


class ResumeOut(BaseModel):
    id: int
    name: str
    is_base: bool
    created_at: datetime
    tailored_for_job_id: str | None = None
    data: StructuredResume


# ----------------------------------------------------------------------- tailoring


class GuardrailViolation(BaseModel):
    kind: str  # employer | title | date | metric | skill
    value: str
    where: str
    detail: str


class ATSReview(BaseModel):
    """Advisory review of the exact resume that was rendered for the job."""

    match_level: str = ""
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    suggested_changes: list[str] = Field(default_factory=list)
    keyword_gaps: list[str] = Field(default_factory=list)


class TailorResult(BaseModel):
    resume: StructuredResume
    changed: bool
    fell_back: bool = False
    violations: list[GuardrailViolation] = Field(default_factory=list)
    warning: str | None = None
    notes: list[str] = Field(default_factory=list)
    ats_review: ATSReview | None = None


class ApplyResponse(BaseModel):
    application_id: int
    resume_id: int
    job: JobRecord
    docx_url: str | None = None
    pdf_url: str | None = None
    pdf_error: str | None = None
    tailoring: TailorResult


class TailorStartRequest(BaseModel):
    """Enough listing data to create a tracker entry before scraping begins."""

    job_id: str
    source: str = ""
    title: str = ""
    company: str = ""
    location: str = ""
    remote: bool = False
    apply_url: str = ""


class ApplicationProgressEvent(BaseModel):
    step: str
    detail: str
    progress: int
    at: datetime


# ------------------------------------------------------------------------ settings


class SettingsOut(BaseModel):
    llm_provider: str
    model: str
    has_key: bool
    ollama_host: str
    openai_base_url: str


class SettingsIn(BaseModel):
    llm_provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    ollama_host: str | None = None
    openai_base_url: str | None = None
    greenhouse_companies: list[str] | None = None
    ashby_boards: list[str] | None = None


class ApplicationOut(BaseModel):
    id: int
    job_id: str
    resume_id: int
    applied_at: datetime
    status: str
    notes: str
    title: str = ""
    company: str = ""
    apply_url: str = ""
    docx_url: str | None = None
    pdf_url: str | None = None
    workflow_status: str = "completed"
    workflow_step: str = "completed"
    workflow_progress: int = 100
    workflow_detail: str = "Resume ready."
    workflow_error: str | None = None
    fit_match_level: str = ""
    fit_summary: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    llm_requests: int = 0
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    estimated_cost_usd: float | None = None


class ApplicationDetail(ApplicationOut):
    description: str = ""
    progress_events: list[ApplicationProgressEvent] = Field(default_factory=list)
    tailoring: TailorResult | None = None
    pdf_error: str | None = None
