"""Token accounting and conservative cost-estimation tests."""

from __future__ import annotations

from datetime import date

import pytest

from app.llm.usage import estimate_cost_usd


def test_gpt_4o_cost_uses_current_input_and_output_rates() -> None:
    value = estimate_cost_usd(
        "openai",
        "gpt-4o",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert value == pytest.approx(12.5)


def test_claude_opus_48_cost_includes_cache_categories() -> None:
    value = estimate_cost_usd(
        "anthropic",
        "claude-opus-4-8",
        input_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        cache_write_input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert value == pytest.approx(36.75)


def test_claude_sonnet_5_uses_launch_pricing_through_august_2026() -> None:
    value = estimate_cost_usd(
        "anthropic",
        "claude-sonnet-5",
        input_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        cache_write_input_tokens=1_000_000,
        output_tokens=1_000_000,
        as_of=date(2026, 8, 31),
    )
    assert value == pytest.approx(14.7)


def test_claude_sonnet_5_uses_standard_pricing_from_september_2026() -> None:
    value = estimate_cost_usd(
        "anthropic",
        "claude-sonnet-5",
        input_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        cache_write_input_tokens=1_000_000,
        output_tokens=1_000_000,
        as_of=date(2026, 9, 1),
    )
    assert value == pytest.approx(22.05)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gpt-5.6-sol", 35.5),
        ("gpt-5.6-terra", 14.2),
        ("gpt-5.6-luna", 1.42),
    ],
)
def test_gpt_56_model_family_uses_published_rates(model, expected) -> None:
    value = estimate_cost_usd(
        "openai",
        model,
        input_tokens=1_000_000,
        cached_input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert value == pytest.approx(expected)


def test_unknown_model_cost_is_not_guessed() -> None:
    assert (
        estimate_cost_usd(
            "openai",
            "third-party-model",
            input_tokens=100,
            output_tokens=100,
        )
        is None
    )
