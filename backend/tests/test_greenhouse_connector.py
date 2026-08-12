from __future__ import annotations

import httpx
import pytest

from app.connectors.greenhouse import GreenhouseConnector


@pytest.mark.asyncio
async def test_greenhouse_returns_internships_and_nothing_else() -> None:
    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "Software Engineering Intern — Summer 2027",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Seattle, WA"},
                "content": "<p>This software engineering internship is for students.</p>",
                "company_name": "Acme",
            },
            {
                "id": 2,
                "title": "Senior Software Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
                "location": {"name": "Seattle, WA"},
                "content": "<p>Seven years of experience, excluding internships.</p>",
                "company_name": "Acme",
            },
            {
                "id": 3,
                "title": "International Tax Manager",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/3",
                "location": {"name": "Remote"},
                "content": "<p>Manage global tax operations.</p>",
                "company_name": "Acme",
            },
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/boards/acme/jobs")
        assert request.url.params["content"] == "true"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        jobs = await GreenhouseConnector(["acme"]).fetch(client)

    assert [job.id for job in jobs] == ["greenhouse:acme:1"]
    assert jobs[0].title == "Software Engineering Intern — Summer 2027"


@pytest.mark.asyncio
async def test_greenhouse_accepts_explicit_internship_description() -> None:
    payload = {
        "jobs": [
            {
                "id": 4,
                "title": "Summer 2027 Software Engineer",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/4",
                "location": {"name": "New York, NY"},
                "content": "<p>This software engineering internship lasts twelve weeks.</p>",
                "company_name": "Acme",
            }
        ]
    }

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        jobs = await GreenhouseConnector(["acme"]).fetch(client)

    assert len(jobs) == 1
