"""Deterministic internship classification shared by discovery sources and imports.

The product is intentionally internship-only.  Matching on the word ``intern`` without
boundaries is a common bug: it also accepts "internal" and "international".  These
patterns cover the usual internship/co-op naming conventions while keeping that failure
mode out of every connector.
"""

from __future__ import annotations

import re

_INTERNSHIP_TITLE_SIGNAL = re.compile(
    r"\b(?:intern(?:ship)?|co[\s-]?op|student[\s-]+trainee|"
    r"summer[\s-]+(?:analyst|associate|fellow))s?\b",
    re.IGNORECASE,
)

# Description matching is deliberately narrower than title matching.  Senior roles often
# say "7+ years excluding internships" or accept internships as prior experience; those
# are not internship openings.  These phrases identify the posting itself as one.
_INTERNSHIP_DESCRIPTION_SIGNAL = re.compile(
    r"\b(?:this|the|a|an)\s+(?:[a-z0-9+#.-]+\s+){0,3}internship\b|"
    r"\binternship\s+(?:position|opportunity|opening|role)\b|"
    r"\bjoin\s+us\s+as\s+an?\s+intern\b",
    re.IGNORECASE,
)


def is_internship(title: str, description: str = "") -> bool:
    """Return whether the posting explicitly identifies itself as an internship."""
    return bool(
        _INTERNSHIP_TITLE_SIGNAL.search(title)
        or _INTERNSHIP_DESCRIPTION_SIGNAL.search(description)
    )
