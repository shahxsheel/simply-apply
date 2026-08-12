"""Provider-agnostic job-description extraction and URL-safety tests."""

from __future__ import annotations

import json
from typing import Any

import httpcore
import httpx
import pytest

from app.services import job_page_scraper
from app.services.job_page_scraper import (
    JobDescriptionError,
    _PinnedIPTransport,
    _validate_public_url,
    extract_job_description,
)


def test_visible_job_description_section_is_extracted() -> None:
    markup = """
    <html><nav>Careers Home</nav><main>
      <h2>Job Description</h2>
      <p>Build reliable distributed systems used by thousands of customers.</p>
      <h3>Responsibilities</h3>
      <ul><li>Develop Python APIs and review production metrics.</li>
          <li>Collaborate with engineering and product teams.</li></ul>
      <h3>Qualifications</h3>
      <p>Experience with Python, SQL, testing, and cloud infrastructure is preferred.</p>
      <h3>Equal Opportunity Employer</h3><p>Long legal boilerplate.</p>
    </main></html>
    """

    description = extract_job_description(markup)

    assert description.startswith("Job Description")
    assert "Qualifications" in description
    assert "Long legal boilerplate" not in description


def test_jobposting_json_is_preferred_for_javascript_shell() -> None:
    payload = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "description": (
            "<p>Join the platform team to build reliable APIs and data services.</p>"
            "<p>You will write Python, SQL, tests, documentation, and production tooling "
            "while collaborating with engineers across the organization.</p>"
            "<p>Successful candidates communicate clearly and learn quickly.</p>"
        ),
    }
    markup = f'<html><script type="application/ld+json">{json.dumps(payload)}</script></html>'

    description = extract_job_description(markup)

    assert "platform team" in description
    assert "Python" in description


def test_structured_description_beats_partial_visible_section() -> None:
    payload = {
        "@type": "JobPosting",
        "description": (
            "<p>Complete role overview with engineering responsibilities, Python services, "
            "SQL data systems, testing expectations, collaboration, education requirements, "
            "and preferred production experience.</p>"
            "<p>This second paragraph makes the complete structured description long enough "
            "and includes all material qualifications for applicants.</p>"
        ),
    }
    markup = (
        f'<script type="application/ld+json">{json.dumps(payload)}</script>'
        "<h2>Qualifications</h2><p>Partial visible qualifications only. "
        + "Short content. " * 20
        + "</p>"
    )

    description = extract_job_description(markup)

    assert description.startswith("Complete role overview")
    assert "Partial visible" not in description


@pytest.mark.parametrize(
    "heading",
    [
        "About the role",
        "In this role you will",
        "What you'll do",
        "Key Responsibilities",
        "Qualifications",
        "What we're looking for",
        "Role Overview",
        "Your Impact",
        "Must Have",
    ],
)
def test_common_role_heading_families_are_recognized(heading: str) -> None:
    markup = f"""
    <nav><a>Qualifications</a><a>Apply</a></nav>
    <main><h2>{heading}</h2>
      <p>Build and operate reliable Python services serving customer-facing products.</p>
      <ul><li>Own implementation, tests, monitoring, and production support.</li>
          <li>Collaborate with product, design, data, and platform engineering.</li></ul>
      <h3>Preferred Qualifications</h3>
      <p>Experience with SQL, APIs, distributed systems, and clear technical writing.</p>
    </main>
    """

    description = extract_job_description(markup)

    assert description.startswith(heading)
    assert "Python services" in description
    assert "Preferred Qualifications" in description


def test_itemprop_description_is_semantic_fallback() -> None:
    markup = """
    <main itemscope itemtype="https://schema.org/JobPosting">
      <section itemprop="description">
        <p>Join the infrastructure group to build reliable developer tooling.</p>
        <p>You will own Python services, SQL pipelines, automated testing, operational
        metrics, documentation, and cross-functional delivery with experienced mentors.</p>
        <p>Candidates should have software engineering fundamentals and strong communication.</p>
      </section>
    </main>
    """

    description = extract_job_description(markup)

    assert "infrastructure group" in description
    assert "automated testing" in description


def test_missing_description_is_actionable() -> None:
    with pytest.raises(JobDescriptionError, match="responsibilities"):
        extract_job_description("<html><p>Apply now.</p></html>")


async def test_private_destination_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_page_scraper,
        "_resolved_addresses",
        lambda hostname, port: ["127.0.0.1"],
    )
    with pytest.raises(JobDescriptionError, match="private address"):
        await _validate_public_url("https://careers.example.com/job/1")


async def test_public_destination_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        job_page_scraper,
        "_resolved_addresses",
        lambda hostname, port: ["93.184.216.34"],
    )
    assert await _validate_public_url("https://careers.example.com/job/1") == [
        "93.184.216.34"
    ]


async def test_mixed_public_and_private_dns_answers_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        job_page_scraper,
        "_resolved_addresses",
        lambda hostname, port: ["93.184.216.34", "10.0.0.5"],
    )
    with pytest.raises(JobDescriptionError, match="private address"):
        await _validate_public_url("https://careers.example.com/job/1")


async def test_invalid_url_port_is_actionable() -> None:
    with pytest.raises(JobDescriptionError, match="invalid port"):
        await _validate_public_url("https://careers.example.com:99999/job/1")


class _FakeStream(httpcore.AsyncNetworkStream):
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.server_hostname: bytes | str | None = None
        self._response = bytearray(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nok"
        )

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        chunk = bytes(self._response[:max_bytes])
        del self._response[:max_bytes]
        return chunk

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.writes.append(buffer)

    async def aclose(self) -> None:
        return None

    async def start_tls(
        self,
        ssl_context,
        server_hostname: bytes | str | None = None,
        timeout: float | None = None,
    ) -> httpcore.AsyncNetworkStream:
        self.server_hostname = server_hostname
        return self

    def get_extra_info(self, info: str) -> Any:
        return None


class _FakeBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.connected_host: str | None = None
        self.stream = _FakeStream()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        self.connected_host = host
        return self.stream

    async def connect_unix_socket(self, *args, **kwargs):
        raise AssertionError("Unix sockets are not used for employer pages")

    async def sleep(self, seconds: float) -> None:
        return None


async def test_pinned_transport_keeps_hostname_for_tls_and_http() -> None:
    backend = _FakeBackend()
    transport = _PinnedIPTransport("93.184.216.34", backend)

    async with httpx.AsyncClient(transport=transport) as client:
        response = await client.get("https://careers.example.com/job/1")

    assert response.text == "ok"
    assert backend.connected_host == "93.184.216.34"
    assert backend.stream.server_hostname in (
        "careers.example.com",
        b"careers.example.com",
    )
    request_bytes = b"".join(backend.stream.writes).lower()
    assert b"host: careers.example.com" in request_bytes
