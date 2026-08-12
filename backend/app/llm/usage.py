"""Conservative cost estimates for provider/model combinations we explicitly know.

Token counts come from provider responses and are exact. Costs are estimates because
provider pricing can change and optional service tiers can add multipliers. Unknown or
OpenAI-compatible third-party models intentionally return ``None`` rather than a guess.

Published-rate sources, checked 2026-08-12:
https://openai.com/api/pricing/
https://platform.claude.com/docs/en/about-claude/pricing
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def estimate_cost_usd(
    provider: str,
    model: str,
    *,
    input_tokens: int,
    cached_input_tokens: int = 0,
    cache_write_input_tokens: int = 0,
    output_tokens: int,
    as_of: date | None = None,
) -> float | None:
    rates = _rates(provider, model, as_of=as_of)
    if rates is None:
        return None
    input_rate, cached_rate, cache_write_rate, output_rate = rates
    return (
        input_tokens * input_rate
        + cached_input_tokens * cached_rate
        + cache_write_input_tokens * cache_write_rate
        + output_tokens * output_rate
    ) / 1_000_000


def _rates(
    provider: str, model: str, *, as_of: date | None = None
) -> tuple[float, float, float, float] | None:
    key = model.casefold()
    pricing_date = as_of or datetime.now(timezone.utc).date()
    if provider == "anthropic":
        if key.startswith(
            (
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-opus-4-5",
            )
        ):
            return 5.0, 0.5, 6.25, 25.0
        if key.startswith(("claude-sonnet-4-6", "claude-sonnet-4-5")):
            return 3.0, 0.3, 3.75, 15.0
        if key.startswith("claude-sonnet-5"):
            # Anthropic's launch pricing applies through 2026-08-31; standard
            # pricing starts 2026-09-01.
            if pricing_date < date(2026, 9, 1):
                return 2.0, 0.2, 2.5, 10.0
            return 3.0, 0.3, 3.75, 15.0
        if key.startswith("claude-haiku-4-5"):
            return 1.0, 0.1, 1.25, 5.0
    if provider == "openai":
        if key.startswith("gpt-4o-mini"):
            return 0.15, 0.075, 0.15, 0.6
        if key.startswith("gpt-4o"):
            return 2.5, 1.25, 2.5, 10.0
        if key.startswith("gpt-5.6-sol") or key == "gpt-5.6":
            return 5.0, 0.5, 5.0, 30.0
        if key.startswith("gpt-5.6-terra"):
            return 2.0, 0.2, 2.0, 12.0
        if key.startswith("gpt-5.6-luna"):
            return 0.2, 0.02, 0.2, 1.2
    return None
