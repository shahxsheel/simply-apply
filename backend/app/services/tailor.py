"""tailor() — rewrite a structured resume against a job description.

Control flow is deliberate:

    generate → guardrail → (violations?) → regenerate with violations fed back
                                        → still bad? → return the BASE resume + warning

The fallback matters. A tailoring tool that silently ships a fabricated resume when its
safety check fails is worse than one that doesn't tailor at all, because the user never
learns it happened. Failing closed to the untailored resume means the worst case is a
generic application, not a rescinded offer.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.llm.base import LLMError, LLMProvider
from app.schemas import ATSReview, JobRecord, StructuredResume, TailorResult
from app.services import guardrail

log = logging.getLogger(__name__)

MAX_JD_CHARS = 12000
TARGET_WORK_ENTRIES = 2
MAX_HIGHLIGHTS_PER_JOB = 3
TARGET_PROJECTS = 3
MAX_PROJECT_HIGHLIGHTS = 2
MAX_EDUCATION_ENTRIES = 2
MAX_SKILL_GROUPS = 6
MAX_KEYWORDS_PER_GROUP = 12

SYSTEM_PROMPT = """You tailor an existing resume to a specific job description.

You are editing a resume that belongs to a real person applying for a real job. Anything \
you invent, they will have to answer for in an interview.

ALLOWED:
- Reorder work entries, bullets, skills, and projects so the most relevant appear first.
- Rewrite bullet phrasing to use the job description's vocabulary for the SAME work.
- Rewrite the summary to target this role.
- Surface skills that already appear anywhere in the resume, including ones currently \
buried inside a bullet or project description.
- Drop bullets or entries that are irrelevant to this role.

RELEVANCE AND ONE-PAGE REQUIREMENTS:
- This is a targeted one-page resume, not a complete employment history.
- Treat one page as both a hard maximum and a content-density target. The finished resume
  must fill the usable page from the top margin through the bottom margin, with no large
  blank area at the end. Use the full truthful detail available in the base resume so the
  final section ends at the bottom margin. Do not underfill the page.
- Always select exactly 2 work experiences and exactly 3 projects from the base resume.
  Pick the entries that provide the strongest evidence for this specific job description,
  and order each section by relevance, strongest first. If the base resume contains fewer
  than 2 work experiences or fewer than 3 projects, include every available entry; never
  invent an entry to reach the target.
- Give each selected work experience at most 3 concise, high-value bullets and each
  selected project at most 2 substantial bullets.
- Keep the summary to 2 focused lines and keep only job-relevant skills.
- Prefer specific, substantial bullets that retain the truthful action, technical detail,
  scope, and outcome from the base resume; do not over-compress them into fragments merely
  to save space. Aim for substantial two-line bullets when the base resume supports that
  detail, and avoid terse one-line fragments that leave the page visibly underfilled.
- If the strongest evidence alone would leave the lower portion of the page blank, add
  the next-most-relevant truthful bullets, projects, and skills from the base resume until
  the page is substantially full, while staying within the limits above.
- Omit irrelevant work, projects, bullets, and skills. Never replace omitted facts with
  invented ones.

RECRUITER EYE-SCAN AND REVISION PASS:
- Before returning the resume, silently review the complete draft in display order as a
  human recruiter making a quick first pass. This is a human-readability review, not
  another keyword count. Do not output the review; revise the resume and return only the
  improved final version.
- First-glance test: can the recruiter immediately identify the candidate's target role
  and strongest job-relevant qualifications from the summary and leading evidence,
  without having to infer connections? If not, make those connections explicit using
  only facts and vocabulary supported by the base resume.
- Evidence scan: lead each section, selected entry, and bullet list with the strongest
  evidence for the job's most important requirements. Replace generic or repetitive
  wording with specific supported actions, tools, scope, and outcomes. Never invent a
  result or metric when the base resume does not provide one.
- Readability scan: make every bullet easy to skim, start with a strong action verb, and
  communicate what the candidate did, how they did it, and the result or purpose when the
  base resume supports those details. Remove first-person pronouns, filler, unexplained
  jargon, spelling errors, tense errors, and inconsistent phrasing.
- Visual-density scan: avoid both walls of text and weak fragments. Keep bullets concise
  enough to scan in the fixed one-page template, generally one or two rendered lines,
  while retaining the substantial truthful detail needed to fill the page.
- After this scan, revise the draft once to fix every issue found, then return the revised
  complete resume. Do not return critique, alternatives, scores, or editing notes.

STYLE REQUIREMENTS:
- Never use the Unicode em dash character (U+2014) anywhere in the output. Rewrite the
  sentence using commas, colons, semicolons, parentheses, or periods instead.

FORBIDDEN: every one of these is fabrication:
- Adding an employer, job title, school, degree, or project that is not already present.
- Changing any date, including "extending" one to close a gap.
- Changing, adding, or inflating any number, percentage, or metric. If the resume says \
15%, it says 15% in your output.
- Adding a skill or technology the resume never mentions, even if the job asks for it.

The reader has both documents. Rephrasing is invisible; inventing is not.

Return a complete, targeted resume with contact information and education preserved.
Other sections should appear only when they contain relevant evidence."""

RETRY_PREFIX = """Your previous attempt introduced facts that are not in the base resume.

Violations found:
{violations}

Produce the tailored resume again. Every employer, job title, school, degree, date, \
number, and skill must appear in the base resume below. When in doubt, copy the base \
resume's value exactly."""

ATS_SYSTEM_PROMPT = """You are a strict Applicant Tracking System reviewer.

Review the exact targeted resume against the supplied job description. Evaluate section
clarity, keyword alignment, evidence, readability, and likely ATS parsing. Be concise and
specific. Suggestions are advisory only and must remain truthful:
- Never recommend adding a skill, credential, employer, title, metric, or experience the
  resume does not support.
- You may identify a missing job keyword, but say to add it only if the candidate genuinely
  has that experience and can support it.
- Prefer suggestions that improve wording, prioritization, measurable evidence, or clarity.
- Do not critique the Jake-style visual template; it is fixed and ATS-oriented.

Use match_level values Strong, Moderate, or Weak. Return no more than 4 strengths, 5
suggested changes, and 8 keyword gaps."""


def _build_user_prompt(resume: StructuredResume, job: JobRecord) -> str:
    description = job.description[:MAX_JD_CHARS]
    truncated = " (truncated)" if len(job.description) > MAX_JD_CHARS else ""
    return f"""JOB
Title: {job.title}
Company: {job.company}
Location: {job.location or "Not specified"}

JOB DESCRIPTION{truncated}
{description}

BASE RESUME (the only source of truth — JSON Resume format)
{resume.model_dump_json(indent=2)}"""


def _apply_one_page_budget(
    resume: StructuredResume, base: StructuredResume
) -> tuple[StructuredResume, list[str]]:
    """Keep the model's relevance order while enforcing a deterministic page envelope.

    Identity, contact, education, and employment metadata are copied from the base
    resume. The model chooses which evidence to keep and how to phrase it; it never gets
    the final say over facts an employer is likely to verify.
    """
    fitted = resume.model_copy(deep=True)
    omitted_roles = max(0, len(fitted.work) - TARGET_WORK_ENTRIES)
    omitted_projects = max(0, len(fitted.projects) - TARGET_PROJECTS)

    fitted.work = fitted.work[:TARGET_WORK_ENTRIES]
    selected_work = {
        (item.name.casefold().strip(), item.position.casefold().strip())
        for item in fitted.work
    }
    for source in base.work:
        key = (source.name.casefold().strip(), source.position.casefold().strip())
        if len(fitted.work) >= min(TARGET_WORK_ENTRIES, len(base.work)):
            break
        if key not in selected_work:
            fitted.work.append(source.model_copy(deep=True))
            selected_work.add(key)
    for job in fitted.work:
        job.highlights = job.highlights[:MAX_HIGHLIGHTS_PER_JOB]
        source = next(
            (
                item
                for item in base.work
                if item.name.casefold().strip() == job.name.casefold().strip()
                and item.position.casefold().strip() == job.position.casefold().strip()
            ),
            None,
        )
        if source is not None:
            job.name = source.name
            job.position = source.position
            job.url = source.url
            job.startDate = source.startDate
            job.endDate = source.endDate
            job.location = source.location

    fitted.projects = fitted.projects[:TARGET_PROJECTS]
    selected_projects = {
        item.name.casefold().strip() for item in fitted.projects
    }
    for source in base.projects:
        key = source.name.casefold().strip()
        if len(fitted.projects) >= min(TARGET_PROJECTS, len(base.projects)):
            break
        if key not in selected_projects:
            fitted.projects.append(source.model_copy(deep=True))
            selected_projects.add(key)
    for project in fitted.projects:
        project.highlights = project.highlights[:MAX_PROJECT_HIGHLIGHTS]
        source = next(
            (
                item
                for item in base.projects
                if item.name.casefold().strip() == project.name.casefold().strip()
            ),
            None,
        )
        if source is not None:
            project.name = source.name
            project.url = source.url
            project.startDate = source.startDate
            project.endDate = source.endDate

    fitted.basics.name = base.basics.name
    fitted.basics.label = base.basics.label
    fitted.basics.email = base.basics.email
    fitted.basics.phone = base.basics.phone
    fitted.basics.url = base.basics.url
    fitted.basics.location = base.basics.location.model_copy(deep=True)
    fitted.basics.profiles = [item.model_copy(deep=True) for item in base.basics.profiles]
    fitted.education = [
        item.model_copy(deep=True) for item in base.education[:MAX_EDUCATION_ENTRIES]
    ]
    fitted.skills = fitted.skills[:MAX_SKILL_GROUPS]
    for skill in fitted.skills:
        skill.keywords = skill.keywords[:MAX_KEYWORDS_PER_GROUP]

    notes: list[str] = []
    if omitted_roles:
        notes.append(
            f"One-page budget omitted {omitted_roles} lower-priority work "
            f"entr{'y' if omitted_roles == 1 else 'ies'}."
        )
    if omitted_projects:
        notes.append(
            f"One-page budget omitted {omitted_projects} lower-priority "
            f"project{'s' if omitted_projects != 1 else ''}."
        )
    return fitted, notes


async def _attach_ats_review(
    provider: LLMProvider,
    result: TailorResult,
    job: JobRecord,
    progress: Callable[[str, str, int], None] | None = None,
) -> TailorResult:
    if progress:
        progress("ats_review", "Reviewing the final resume as an ATS.", 70)
    description = job.description[:MAX_JD_CHARS]
    prompt = f"""JOB
Title: {job.title}
Company: {job.company}

JOB DESCRIPTION
{description}

FINAL RESUME TO REVIEW
{result.resume.model_dump_json(indent=2)}"""
    try:
        result.ats_review = await provider.complete_structured(
            system=ATS_SYSTEM_PROMPT,
            user=prompt,
            schema=ATSReview,
            max_tokens=2500,
        )
    except LLMError as exc:
        log.warning("ATS review failed without blocking resume generation: %s", exc)
        result.notes.append("ATS review was unavailable; resume generation still completed.")
    return result


async def tailor(
    provider: LLMProvider,
    resume: StructuredResume,
    job: JobRecord,
    progress: Callable[[str, str, int], None] | None = None,
    *,
    system_prompt: str | None = None,
) -> TailorResult:
    base_prompt = _build_user_prompt(resume, job)
    effective_system_prompt = system_prompt or SYSTEM_PROMPT
    notes: list[str] = []

    if progress:
        progress("tailoring", "Selecting and rewriting the strongest job-relevant evidence.", 35)
    try:
        candidate = await provider.complete_structured(
            system=effective_system_prompt, user=base_prompt, schema=StructuredResume
        )
    except LLMError:
        raise

    candidate, budget_notes = _apply_one_page_budget(candidate, resume)
    notes.extend(budget_notes)
    if progress:
        progress("verifying", "Checking every claim against the saved resume.", 55)
    violations = guardrail.check(resume, candidate)
    if not violations:
        return await _attach_ats_review(
            provider,
            TailorResult(resume=candidate, changed=True, notes=notes),
            job,
            progress,
        )

    # One retry, with the specific violations named. Generic "try again" prompts don't
    # help; pointing at the exact invented value usually does.
    log.warning("tailor: %d guardrail violation(s) on first attempt", len(violations))
    notes.append(f"First attempt had {len(violations)} guardrail violation(s); retried.")

    retry_prompt = (
        RETRY_PREFIX.format(violations=guardrail.summarize(violations))
        + "\n\n"
        + base_prompt
    )

    try:
        candidate = await provider.complete_structured(
            system=effective_system_prompt, user=retry_prompt, schema=StructuredResume
        )
    except LLMError as exc:
        log.warning("tailor: retry failed (%s); falling back to base resume", exc)
        return await _attach_ats_review(
            provider,
            TailorResult(
                resume=resume,
                changed=False,
                fell_back=True,
                violations=violations,
                warning=(
                    "Tailoring was rejected by the no-fabrication check and the retry "
                    "failed. Your original, unmodified resume was used instead."
                ),
                notes=notes,
            ),
            job,
            progress,
        )

    candidate, budget_notes = _apply_one_page_budget(candidate, resume)
    notes.extend(budget_notes)
    if progress:
        progress("verifying", "Checking the revised resume against the saved facts.", 60)
    violations = guardrail.check(resume, candidate)
    if not violations:
        notes.append("Retry passed the no-fabrication check.")
        return await _attach_ats_review(
            provider,
            TailorResult(resume=candidate, changed=True, notes=notes),
            job,
            progress,
        )

    # Fail closed. The user gets a truthful resume and an explicit heads-up.
    log.warning(
        "tailor: %d violation(s) persisted after retry; falling back to base resume",
        len(violations),
    )
    return await _attach_ats_review(
        provider,
        TailorResult(
            resume=resume,
            changed=False,
            fell_back=True,
            violations=violations,
            warning=(
                "Tailoring introduced details that aren't in your resume, twice. Your "
                "original, unmodified resume was used instead. The flagged items are "
                "listed below — a more capable model usually fixes this."
            ),
            notes=notes,
        ),
        job,
        progress,
    )
