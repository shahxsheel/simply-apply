"""tailor() control-flow tests.

The guardrail tests prove we can *detect* fabrication. These prove we *act* on it
correctly — retry once, then fail closed to the untruthful-but-safe option (the user's
own resume), never shipping flagged content.

A stub provider stands in for the LLM so the control flow is deterministic and testable
without a key or a network call.
"""

from __future__ import annotations

import pytest

from app.llm.base import LLMError, LLMProvider
from app.schemas import Basics, JobRecord, Project, Skill, StructuredResume, Work
from app.services.tailor import tailor


class StubProvider(LLMProvider):
    """Returns a scripted resume per call so we can drive each branch."""

    name = "stub"

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []
        self.systems: list[str] = []
        self.ats_calls: list[str] = []

    async def complete_structured(self, *, system, user, schema, max_tokens=16000):
        if schema.__name__ == "ATSReview":
            self.ats_calls.append(user)
            return schema(
                match_level="Moderate",
                summary="Relevant evidence is clear but could be more specific.",
                strengths=["Python experience is prominent."],
                suggested_changes=["Clarify the impact of the caching work."],
                keyword_gaps=["Kubernetes"],
            )
        self.calls.append(user)
        self.systems.append(system)
        if not self._responses:
            raise AssertionError("StubProvider called more times than scripted")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    async def health(self):
        return True, "stub"


@pytest.fixture
def base() -> StructuredResume:
    return StructuredResume(
        basics=Basics(name="Jane Doe", summary="Backend engineer."),
        work=[
            Work(
                name="Acme Corp",
                position="Software Engineer",
                startDate="2022-01",
                endDate="2024-06",
                highlights=["Reduced latency by 15%."],
            )
        ],
        skills=[Skill(name="Languages", keywords=["Python"])],
    )


@pytest.fixture
def job() -> JobRecord:
    return JobRecord(
        id="greenhouse:acme:1",
        source="greenhouse",
        title="Senior Backend Engineer",
        company="Globex",
        apply_url="https://example.com/apply",
        description="We need Python and Kubernetes experience.",
    )


def _clean(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.basics.summary = "Backend engineer with a focus on Python services."
    return out


def _fabricated(base: StructuredResume) -> StructuredResume:
    out = base.model_copy(deep=True)
    out.skills.append(Skill(name="Infra", keywords=["Kubernetes"]))
    return out


async def test_clean_first_attempt_is_returned(base, job) -> None:
    provider = StubProvider([_clean(base)])
    result = await tailor(provider, base, job)

    assert result.changed is True
    assert result.fell_back is False
    assert result.violations == []
    assert len(provider.calls) == 1, "a clean result must not trigger a retry"
    assert result.ats_review is not None
    assert result.ats_review.match_level == "Moderate"
    assert len(provider.ats_calls) == 1


async def test_violation_triggers_retry_with_feedback(base, job) -> None:
    provider = StubProvider([_fabricated(base), _clean(base)])
    result = await tailor(provider, base, job)

    assert result.changed is True
    assert result.fell_back is False
    assert len(provider.calls) == 2

    # The retry must name the specific invented value — a generic "try again" doesn't work.
    assert "Kubernetes" in provider.calls[1]
    assert "violation" in provider.calls[1].lower()


async def test_persistent_violation_falls_back_to_base(base, job) -> None:
    """The critical path: two bad attempts must ship the user's own resume, not the fake."""
    provider = StubProvider([_fabricated(base), _fabricated(base)])
    result = await tailor(provider, base, job)

    assert result.fell_back is True
    assert result.changed is False
    assert result.resume == base, "fallback must be the untouched base resume"
    assert result.warning and "original" in result.warning.lower()
    assert any(v.value == "Kubernetes" for v in result.violations)


async def test_retry_error_falls_back_rather_than_raising(base, job) -> None:
    """A provider failure mid-retry must not surface flagged content or a 500."""
    provider = StubProvider([_fabricated(base), LLMError("rate limited")])
    result = await tailor(provider, base, job)

    assert result.fell_back is True
    assert result.resume == base


async def test_first_attempt_error_propagates(base, job) -> None:
    """If we never got a result at all, that's a real error the user should see."""
    provider = StubProvider([LLMError("no API key configured")])
    with pytest.raises(LLMError):
        await tailor(provider, base, job)


async def test_prompt_contains_job_and_resume(base, job) -> None:
    provider = StubProvider([_clean(base)])
    await tailor(provider, base, job)

    prompt = provider.calls[0]
    assert "Senior Backend Engineer" in prompt
    assert "Globex" in prompt
    assert "Acme Corp" in prompt
    assert "Kubernetes" in prompt, "the JD text must reach the model"
    assert "exactly 2 work experiences and exactly 3 projects" in provider.systems[0]
    assert "not a complete employment history" in provider.systems[0]
    assert "blank area at the end" in provider.systems[0]
    assert "Do not underfill the page" in provider.systems[0]
    assert "next-most-relevant truthful bullets" in provider.systems[0]
    assert "Never use the Unicode em dash character (U+2014)" in provider.systems[0]


async def test_prompt_requires_recruiter_eye_scan_and_revision(base, job) -> None:
    provider = StubProvider([_clean(base)])
    await tailor(provider, base, job)

    system = provider.systems[0]
    assert "RECRUITER EYE-SCAN AND REVISION PASS" in system
    assert "human recruiter making a quick first pass" in system
    assert "without having to infer connections" in system
    assert "what the candidate did, how they did it" in system
    assert "generally one or two rendered lines" in system
    assert "revise the draft once" in system
    assert "Do not return critique" in system


async def test_custom_system_prompt_is_used_for_initial_attempt_and_retry(base, job) -> None:
    provider = StubProvider([_fabricated(base), _clean(base)])
    custom_prompt = "Use the user's saved tailoring instructions."

    await tailor(provider, base, job, system_prompt=custom_prompt)

    assert provider.systems == [custom_prompt, custom_prompt]


async def test_long_job_description_is_truncated(base) -> None:
    """Guards against blowing the context window on a pathological posting."""
    huge = JobRecord(
        id="x:1",
        source="x",
        title="Engineer",
        company="Corp",
        apply_url="https://example.com",
        description="word " * 20000,
    )
    provider = StubProvider([_clean(base)])
    await tailor(provider, base, huge)
    assert "(truncated)" in provider.calls[0]


async def test_one_page_budget_keeps_two_work_entries_and_three_projects(base, job) -> None:
    expanded = base.model_copy(deep=True)
    expanded.work = [
        Work(name=f"Employer {i}", position=f"Role {i}", highlights=[f"Evidence {j}" for j in range(5)])
        for i in range(5)
    ]
    expanded.projects = [
        Project(name=f"Project {i}", highlights=[f"Project evidence {j}" for j in range(4)])
        for i in range(5)
    ]
    candidate = expanded.model_copy(deep=True)
    provider = StubProvider([candidate])

    result = await tailor(provider, expanded, job)

    assert [item.name for item in result.resume.work] == [
        "Employer 0",
        "Employer 1",
    ]
    assert all(len(item.highlights) == 3 for item in result.resume.work)
    assert [item.name for item in result.resume.projects] == [
        "Project 0",
        "Project 1",
        "Project 2",
    ]
    assert all(len(item.highlights) == 2 for item in result.resume.projects)
    assert any("omitted 3 lower-priority work" in note for note in result.notes)
    assert any("omitted 2 lower-priority projects" in note for note in result.notes)


async def test_budget_fills_missing_model_sections_from_truthful_base(base, job) -> None:
    expanded = base.model_copy(deep=True)
    expanded.work.append(
        Work(name="Beta Corp", position="Backend Intern", highlights=["Built APIs."])
    )
    expanded.projects = [
        Project(name=f"Project {i}", highlights=[f"Evidence {i}."])
        for i in range(3)
    ]
    candidate = _clean(expanded)
    candidate.work = candidate.work[:1]
    candidate.projects = candidate.projects[:1]
    provider = StubProvider([candidate])

    result = await tailor(provider, expanded, job)

    assert len(result.resume.work) == 2
    assert len(result.resume.projects) == 3
    assert [item.name for item in result.resume.projects] == [
        "Project 0",
        "Project 1",
        "Project 2",
    ]


async def test_verified_identity_and_education_are_restored(base, job) -> None:
    base.basics.email = "jane@example.com"
    candidate = _clean(base)
    candidate.basics.name = "Jane Q. Doe"
    candidate.basics.email = "invented@example.com"
    provider = StubProvider([candidate])

    result = await tailor(provider, base, job)

    assert result.resume.basics.name == "Jane Doe"
    assert result.resume.basics.email == "jane@example.com"
