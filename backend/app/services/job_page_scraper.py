"""Provider-agnostic extraction of complete job content from an employer page.

Premier job consumers prefer machine-readable, complete descriptions over guessing from
one heading, so extraction is ordered accordingly: schema.org JobPosting JSON-LD,
semantic ``itemprop=description`` markup, then visible section headings. The heading
fallback recognizes role overview, responsibility, and qualification language while
discarding navigation and application-form text.

Fetching is SSRF-hardened because tracker URLs are externally maintained: every request
and redirect must resolve only to public IP addresses, response types must be HTML/text,
and bodies are capped before parsing.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from html.parser import HTMLParser
from io import StringIO
from urllib.parse import urljoin, urlsplit

import httpcore
import httpx

from app.connectors.base import DEFAULT_TIMEOUT, USER_AGENT, html_to_text

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 5 * 1024 * 1024
MIN_DESCRIPTION_CHARS = 180
MAX_DESCRIPTION_CHARS = 30000
_SPACE = re.compile(r"\s+")
_HEADING_PUNCTUATION = re.compile(r"[^a-z0-9' ]+")
_STOP_MARKERS = (
    "equal opportunity employer",
    "equal employment opportunity",
    "equal opportunity at ",
    "reasonable accommodation",
    "privacy notice",
    "applicant privacy",
    "how to apply",
    "application process",
)

# Headings seen across employer career sites. Ordering is conceptual; the earliest match
# in the page wins so an overview is kept when responsibilities and qualifications follow.
_ROLE_HEADINGS = (
    "job description",
    "role description",
    "position description",
    "job overview",
    "overview",
    "about the role",
    "about this role",
    "about the job",
    "the role",
    "role overview",
    "position overview",
    "position summary",
    "job summary",
    "the opportunity",
    "your role",
    "what you'll do",
    "what you will do",
    "what you'll be doing",
    "what you will be doing",
    "what you'll work on",
    "what you will work on",
    "what you'll be responsible for",
    "what you will be responsible for",
    "your impact",
    "how you'll make an impact",
    "how you will make an impact",
    "in this role",
    "in this role you will",
    "responsibilities",
    "key responsibilities",
    "roles and responsibilities",
    "your responsibilities",
    "day to day",
    "a day in the life",
    "duties",
    "key duties",
)
_QUALIFICATION_HEADINGS = (
    "qualifications",
    "required qualifications",
    "minimum qualifications",
    "preferred qualifications",
    "basic qualifications",
    "requirements",
    "job requirements",
    "what we're looking for",
    "what we are looking for",
    "who you are",
    "what you'll bring",
    "what you will bring",
    "skills and experience",
    "experience and skills",
    "what you need",
    "must have",
    "nice to have",
    "preferred skills",
    "required skills",
    "knowledge skills and abilities",
    "what makes you a great fit",
)
_SKIP_TAGS = {
    "script", "style", "nav", "header", "footer", "form", "button", "svg", "noscript",
}
_BLOCK_TAGS = {
    "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "ul", "ol",
    "section", "article", "tr", "td", "blockquote",
}
_VOID_TAGS = {"br", "img", "meta", "link", "input", "hr", "source", "area", "base", "embed", "param", "track", "wbr"}


class JobDescriptionError(RuntimeError):
    """The page could not be fetched safely or did not expose a job description."""


class _StructuredDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.payloads: list[str] = []
        self._capturing = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag != "script":
            return
        attr_map = {key.casefold(): (value or "") for key, value in attrs}
        if "ld+json" in attr_map.get("type", "").casefold():
            self._capturing = True
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capturing:
            self.payloads.append("".join(self._parts))
            self._capturing = False
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)


class _SemanticDescriptionParser(HTMLParser):
    """Collect schema.org microdata descriptions without assuming a page layout."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.descriptions: list[str] = []
        self._depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        attr_map = {key.casefold(): (value or "") for key, value in attrs}
        if self._depth:
            if tag in _BLOCK_TAGS:
                self._parts.append("\n")
            if tag not in _VOID_TAGS:
                self._depth += 1
            return
        itemprops = attr_map.get("itemprop", "").casefold().split()
        if "description" not in itemprops:
            return
        content = attr_map.get("content", "").strip()
        if content:
            self.descriptions.append(content)
        if tag not in _VOID_TAGS:
            self._depth = 1
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")
        self._depth -= 1
        if not self._depth:
            self.descriptions.append("".join(self._parts))
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._depth:
            self._parts.append(data)


class _VisibleContentParser(HTMLParser):
    """Visible body text with menus, forms, scripts, and decorative SVG removed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out = StringIO()
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip += 1
        elif not self._skip and tag == "li":
            self._out.write("\n- ")
        elif not self._skip and tag in _BLOCK_TAGS:
            self._out.write("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        elif not self._skip and tag in _BLOCK_TAGS:
            self._out.write("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._out.write(data)

    def lines(self) -> list[str]:
        lines = [_SPACE.sub(" ", line).strip() for line in self._out.getvalue().splitlines()]
        return [line for line in lines if line]


def _trim_boilerplate(text: str) -> str:
    lowered = text.casefold()
    cut = len(text)
    for marker in _STOP_MARKERS:
        index = lowered.find(marker, MIN_DESCRIPTION_CHARS)
        if index >= 0:
            cut = min(cut, index)
    return text[:cut].strip()[:MAX_DESCRIPTION_CHARS]


def _heading_key(line: str) -> str:
    line = line.casefold().replace("’", "'").replace("&", " and ")
    return _SPACE.sub(" ", _HEADING_PUNCTUATION.sub(" ", line)).strip()


def _matches_heading(line: str, headings: tuple[str, ...]) -> bool:
    if len(line) > 120:
        return False
    key = _heading_key(line)
    return any(key == heading or key.startswith(f"{heading} ") for heading in headings)


def _visible_role_content(markup: str) -> str | None:
    parser = _VisibleContentParser()
    parser.feed(markup)
    parser.close()
    lines = parser.lines()
    all_headings = _ROLE_HEADINGS + _QUALIFICATION_HEADINGS
    start = next((i for i, line in enumerate(lines) if _matches_heading(line, all_headings)), None)
    if start is None:
        return None
    candidate = _trim_boilerplate("\n".join(lines[start:]))
    return candidate if len(candidate) >= MIN_DESCRIPTION_CHARS else None


def _walk_json(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _structured_job_description(markup: str) -> str | None:
    parser = _StructuredDataParser()
    parser.feed(markup)
    parser.close()
    for payload in parser.payloads:
        try:
            value = json.loads(payload)
        except (TypeError, ValueError):
            continue
        for node in _walk_json(value):
            kind = node.get("@type", "")
            kinds = kind if isinstance(kind, list) else [kind]
            if not any(str(item).casefold() == "jobposting" for item in kinds):
                continue
            description = node.get("description")
            if not isinstance(description, str):
                continue
            candidate = _trim_boilerplate(html_to_text(description))
            if len(candidate) >= MIN_DESCRIPTION_CHARS:
                return candidate
    return None


def _semantic_job_description(markup: str) -> str | None:
    parser = _SemanticDescriptionParser()
    parser.feed(markup)
    parser.close()
    for description in parser.descriptions:
        candidate = _trim_boilerplate(html_to_text(description))
        if len(candidate) >= MIN_DESCRIPTION_CHARS:
            return candidate
    return None


def extract_job_description(markup: str) -> str:
    """Extract a useful description without knowing which ATS hosts the page."""
    description = (
        _structured_job_description(markup)
        or _semantic_job_description(markup)
        or _visible_role_content(markup)
    )
    if description:
        return description
    raise JobDescriptionError(
        "Could not find JobPosting metadata or a recognizable role, responsibilities, "
        "or qualifications section on the employer page. Open the posting directly to "
        "review it."
    )


class _PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Connect to one validated address while preserving the request hostname.

    HTTP Core still receives the original URL, so it uses the employer hostname for the
    Host header, TLS SNI, and certificate verification. Only the TCP destination is
    replaced, closing the validation/request DNS-rebinding window.
    """

    def __init__(
        self,
        address: str,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        self.address = address
        self._backend = backend or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_tcp(
            self.address,
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options=None,
    ) -> httpcore.AsyncNetworkStream:
        return await self._backend.connect_unix_socket(
            path, timeout=timeout, socket_options=socket_options
        )

    async def sleep(self, seconds: float) -> None:
        await self._backend.sleep(seconds)


class _PinnedIPTransport(httpx.AsyncHTTPTransport):
    """HTTPX transport whose connection pool cannot perform a second DNS lookup."""

    def __init__(
        self,
        address: str,
        backend: httpcore.AsyncNetworkBackend | None = None,
    ) -> None:
        super().__init__(trust_env=False)
        # HTTPX 0.28 does not expose HTTP Core's network backend in its public
        # constructor. Both packages are pinned, and replacing this one pool dependency
        # lets HTTPX retain its normal TLS and response handling.
        self._pool._network_backend = _PinnedNetworkBackend(  # type: ignore[attr-defined]
            address, backend
        )


def _resolved_addresses(hostname: str, port: int) -> list[str]:
    rows = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return sorted({row[4][0] for row in rows})


async def _validate_public_url(url: str) -> list[str]:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise JobDescriptionError("Job URL must be a valid HTTP or HTTPS address.")
    if parsed.username or parsed.password:
        raise JobDescriptionError("Job URL must not contain embedded credentials.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise JobDescriptionError("Job URL contains an invalid port.") from exc
    try:
        addresses = await asyncio.to_thread(_resolved_addresses, parsed.hostname, port)
    except (OSError, socket.gaierror) as exc:
        raise JobDescriptionError("Could not resolve the employer's job page.") from exc
    if not addresses:
        raise JobDescriptionError("Could not resolve the employer's job page.")
    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                raise JobDescriptionError(
                    "Refusing to fetch a job page that resolves to a private address."
                )
        except ValueError as exc:
            raise JobDescriptionError("Employer page resolved to an invalid address.") from exc
    return addresses


async def _download_html(url: str) -> str:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        addresses = await _validate_public_url(current)
        # A fresh pool per hop prevents a redirect from reusing a connection validated
        # for a different origin. All DNS answers were checked above; selecting one is
        # safe and avoids a second lookup inside the socket backend.
        transport = _PinnedIPTransport(addresses[0])
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
            transport=transport,
        ) as client:
            async with client.stream("GET", current, timeout=DEFAULT_TIMEOUT) as response:
                if response.is_redirect:
                    target = response.headers.get("location")
                    if not target:
                        raise JobDescriptionError("Employer page returned an invalid redirect.")
                    current = urljoin(current, target)
                    continue
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise JobDescriptionError(
                        f"Employer page returned HTTP {response.status_code}."
                    ) from exc
                content_type = response.headers.get("content-type", "").casefold()
                if content_type and not any(
                    allowed in content_type
                    for allowed in ("text/html", "application/xhtml", "text/plain")
                ):
                    raise JobDescriptionError("Employer link did not return an HTML page.")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BODY_BYTES:
                        raise JobDescriptionError(
                            "Employer job page was too large to parse safely."
                        )
                encoding = response.encoding or "utf-8"
                return bytes(body).decode(encoding, errors="replace")
    raise JobDescriptionError("Employer page redirected too many times.")


async def scrape_job_description(url: str) -> str:
    try:
        markup = await _download_html(url)
    except JobDescriptionError:
        raise
    except httpx.RequestError as exc:
        raise JobDescriptionError(
            "Could not reach the employer's job page. Use View Posting and try again later."
        ) from exc
    return extract_job_description(markup)
