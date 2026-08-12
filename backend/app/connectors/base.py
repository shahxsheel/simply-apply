"""Shared HTTP and HTML helpers for employer internship boards."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from io import StringIO

import httpx

USER_AGENT = "SimplyApply/0.1 (+https://github.com/jadghazi/simplyapply)"
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class _TextExtractor(HTMLParser):
    """Minimal HTML -> readable text.

    Job descriptions arrive as HTML from every source. We only need clean text for the
    LLM and for display, so a full markdown converter would be a dependency we don't
    need. Block-level tags become newlines; list items get a bullet.
    """

    BLOCK = {
        "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6",
        "ul", "ol", "tr", "section", "article",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out = StringIO()
        self._skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "li":
            self._out.write("\n- ")
        elif tag in self.BLOCK:
            self._out.write("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        elif tag in self.BLOCK:
            self._out.write("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._out.write(data)

    def text(self) -> str:
        raw = self._out.getvalue().replace("\xa0", " ")
        lines = [line.strip() for line in raw.splitlines()]
        cleaned: list[str] = []
        for line in lines:
            if line or (cleaned and cleaned[-1]):
                cleaned.append(line)
        return "\n".join(cleaned).strip()


#: Matches an *escaped* opening tag — `&lt;p&gt;`, `&lt;/div&gt;`, `&lt;h4 class=…`.
#: The `(?:amp;)*` handles doubly-escaped payloads (`&amp;lt;p&amp;gt;`), where the
#: literal `&lt;` never appears until the first unescape pass has run.
#: Requiring a letter or slash after the `<` keeps prose like "latency &lt; 200ms"
#: from being mistaken for markup.
_ESCAPED_MARKUP = re.compile(r"&(?:amp;)*lt;/?[a-zA-Z]")


def html_to_text(markup: str) -> str:
    """HTML -> readable text, tolerating sources that HTML-escape their markup.

    Greenhouse returns `content` with the tags themselves escaped (`&lt;div&gt;…`).
    Feeding that straight to HTMLParser is a silent trap: `convert_charrefs` turns the
    entities into literal `<div>` *text*, so the parser sees no tags at all and the
    "cleaned" description is the raw markup verbatim. That noise then goes into the
    tailoring prompt, wasting tokens and burying the actual requirements.

    So: unescape first when the payload looks like escaped markup, and loop, because a
    doubly-escaped source (`&amp;lt;p&amp;gt;`) needs more than one pass. Bounded to
    keep a pathological input from spinning.
    """
    if not markup:
        return ""

    for _ in range(3):
        if not _ESCAPED_MARKUP.search(markup):
            break
        unescaped = unescape(markup)
        if unescaped == markup:
            break
        markup = unescaped

    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:
        return markup
    return parser.text()
