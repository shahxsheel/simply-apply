from __future__ import annotations

import httpx
import pytest

from app.connectors.ashby import AshbyConnector
from app.services.internship_filter import is_internship


def test_internship_filter_does_not_confuse_intern_with_internal() -> None:
    assert is_internship("Software Engineering Internship")
    assert is_internship("Summer Analyst")
    assert is_internship("Backend Co-op")
    assert not is_internship("Internal Applications Engineer")
    assert not is_internship("International Tax Manager")
    assert not is_internship(
        "Senior Software Engineer",
        "Requires seven years of professional experience, excluding internships.",
    )
    assert not is_internship(
        "Early Career Recruiter", "Build and run recruiting and internship programs."
    )
    assert is_internship(
        "Summer 2027 Software Engineer",
        "This software engineering internship is for currently enrolled students.",
    )


@pytest.mark.asyncio
async def test_ashby_returns_only_matching_internships() -> None:
    payload = {
        "jobs": [
            {
                "id": "intern-1",
                "title": "Software Engineer Intern, Summer 2027",
                "location": "New York, NY",
                "isRemote": False,
                "isListed": True,
                "publishedAt": "2026-08-01T12:00:00Z",
                "jobUrl": "https://jobs.ashbyhq.com/acme/intern-1",
                "descriptionPlain": "Build Python services during this internship.",
            },
            {
                "id": "fulltime-1",
                "title": "Software Engineer, Internal Applications",
                "location": "New York, NY",
                "isRemote": False,
                "isListed": True,
                "jobUrl": "https://jobs.ashbyhq.com/acme/fulltime-1",
                "descriptionPlain": "Build Python services full time.",
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/job-board/acme")
        assert request.url.params["includeCompensation"] == "true"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await AshbyConnector(["acme"]).fetch(client)

    assert len(jobs) == 1
    assert jobs[0].id == "ashby:acme:intern-1"
    assert jobs[0].company == "Acme"
    assert jobs[0].description.startswith("Build Python")


@pytest.mark.asyncio
async def test_ashby_isolates_a_dead_board() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/job-board/dead"):
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "1",
                        "title": "Product Intern",
                        "jobUrl": "https://jobs.ashbyhq.com/live/1",
                        "descriptionPlain": "A product internship for current students.",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await AshbyConnector(["dead", "live"]).fetch(client)

    assert [job.id for job in jobs] == ["ashby:live:1"]
