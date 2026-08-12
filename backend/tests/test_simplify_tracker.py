"""Parser and filtering tests for the public Simplify Summer 2027 tracker."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas import SimplifyTrackerJob
from app.services import simplify_tracker
from app.services.simplify_tracker import get_tracker, parse_readme

SAMPLE = """
## 💻 Software Engineering Internship Roles
<table>
<thead><tr><th>Company</th><th>Role</th><th>Location</th><th>Application</th><th>Age</th></tr></thead>
<tbody>
<tr>
  <td>🔥 <strong><a href="https://simplify.jobs/c/Acme">Acme</a></strong></td>
  <td>Software Engineer Intern</td>
  <td><details><summary><strong>2 locations</strong></summary>Seattle, WA<br>Remote</details></td>
  <td><a href="https://jobs.example.com/acme-1?embed=true&amp;utm_source=Simplify&amp;ref=Simplify"><img alt="Apply"></a>
      <a href="https://simplify.jobs/p/acme-1"><img alt="Simplify"></a></td>
  <td>0d</td>
</tr>
<tr>
  <td>↳</td>
  <td>Backend Engineer Intern 🎓</td>
  <td>Austin, TX</td>
  <td><a href="https://jobs.example.com/acme-2"><img alt="Apply"></a></td>
  <td>2d</td>
</tr>
</tbody>
</table>

## 📱 Product Management Internship Roles
<table><tbody>
<tr>
  <td><strong><a href="https://simplify.jobs/c/Beta">Beta</a></strong></td>
  <td>Product Manager Intern</td><td>NYC</td>
  <td><a href="https://careers.example.com/beta-1"><img alt="Apply"></a>
      <a href="https://simplify.jobs/p/beta-1"><img alt="Simplify"></a></td>
  <td>1d</td>
</tr>
</tbody></table>
"""


def test_parse_readme_keeps_only_direct_employer_links() -> None:
    jobs = parse_readme(SAMPLE)

    assert len(jobs) == 3
    assert jobs[0].company == "Acme"
    assert jobs[0].apply_url == "https://jobs.example.com/acme-1?embed=true"
    assert "simplify_url" not in jobs[0].model_dump()
    assert "company_url" not in jobs[0].model_dump()
    assert jobs[0].location == "Seattle, WA · Remote"
    assert jobs[0].remote is True
    assert jobs[0].flags == ["FAANG+"]
    assert "Simplify" not in jobs[0].apply_url


def test_continuation_row_inherits_company_and_flags_degree() -> None:
    jobs = parse_readme(SAMPLE)

    assert jobs[1].company == "Acme"
    assert jobs[1].role == "Backend Engineer Intern"
    assert jobs[1].flags == ["Advanced degree"]


def test_secondary_simplify_link_is_discarded() -> None:
    job = parse_readme(SAMPLE)[2]
    assert job.apply_url == "https://careers.example.com/beta-1"
    assert "simplify.jobs" not in job.model_dump_json()
    assert job.category == "Product Management"


def test_listing_without_direct_employer_link_is_omitted() -> None:
    sample = SAMPLE.replace(
        '<a href="https://careers.example.com/beta-1"><img alt="Apply"></a>', ""
    )
    jobs = parse_readme(sample)
    assert all(job.company != "Beta" for job in jobs)


async def test_tracker_filters_cached_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    jobs = [
        SimplifyTrackerJob(
            id="one",
            company="Acme",
            role="Software Engineer Intern",
            location="Seattle, WA",
            category="Software Engineering",
            apply_url="https://example.com/one",
        ),
        SimplifyTrackerJob(
            id="two",
            company="Beta",
            role="Product Manager Intern",
            location="NYC",
            category="Product Management",
            apply_url="https://example.com/two",
        ),
    ]
    monkeypatch.setattr(
        simplify_tracker,
        "_cache",
        (datetime.now(timezone.utc), jobs),
    )

    result = await get_tracker(query="acme seattle", category="Software Engineering")

    assert result.total == 1
    assert result.jobs[0].id == "one"
