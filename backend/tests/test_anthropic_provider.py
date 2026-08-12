"""Contract tests for the Anthropic structured-output adapter."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.llm.base import LLMError
from app.llm.anthropic_provider import AnthropicProvider, _generation_schema
from app.services.parse import parse_resume


class _Answer(BaseModel):
    value: str = ""


def test_installed_sdk_supports_ga_structured_outputs() -> None:
    """Keep the dependency pin aligned with the SDK method used by the adapter."""
    from anthropic import AsyncAnthropic
    import inspect

    client = AsyncAnthropic(api_key="test")
    assert "output_config" in inspect.signature(client.messages.create).parameters


def test_generation_schema_requires_defaulted_fields() -> None:
    output = _generation_schema(_Answer)
    assert output["required"] == ["value"]
    assert output["additionalProperties"] is False
    assert "default" not in output["properties"]["value"]


async def test_complete_structured_returns_validated_output() -> None:
    provider = AnthropicProvider(api_key="test", model="claude-sonnet-4-6")
    calls: list[dict[str, object]] = []

    class _Messages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text='{"value":"ok"}')],
                usage=SimpleNamespace(
                    input_tokens=100,
                    cache_read_input_tokens=20,
                    cache_creation_input_tokens=10,
                    output_tokens=50,
                ),
            )

    provider._client = SimpleNamespace(messages=_Messages())

    result = await provider.complete_structured(
        system="Return a value.",
        user="test",
        schema=_Answer,
        max_tokens=64,
    )

    assert result == _Answer(value="ok")
    output_format = calls[0]["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert output_format["schema"]["required"] == ["value"]
    assert calls[0]["thinking"] == {"type": "adaptive"}
    assert provider.token_usage.total_tokens == 180
    assert provider.token_usage.estimated_cost_usd == pytest.approx(0.0010935)


async def test_complete_structured_can_skip_reasoning() -> None:
    provider = AnthropicProvider(api_key="test", model="claude-sonnet-4-6")
    calls: list[dict[str, object]] = []

    class _Messages:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text='{"value":"ok"}')],
            )

    provider._client = SimpleNamespace(messages=_Messages())
    await provider.complete_structured(
        system="Transcribe.",
        user="test",
        schema=_Answer,
        reasoning=False,
    )

    assert "thinking" not in calls[0]


@pytest.mark.parametrize(
    ("stop_reason", "content", "message"),
    [
        ("refusal", [], "declined"),
        ("max_tokens", [], "output tokens"),
        ("end_turn", [], "no structured output"),
        (
            "end_turn",
            [SimpleNamespace(type="text", text="not json")],
            "invalid structured output",
        ),
    ],
)
async def test_usage_is_recorded_before_response_validation(
    stop_reason, content, message
) -> None:
    provider = AnthropicProvider(api_key="test", model="claude-sonnet-4-6")

    class _Messages:
        async def create(self, **kwargs):
            return SimpleNamespace(
                stop_reason=stop_reason,
                content=content,
                usage=SimpleNamespace(
                    input_tokens=100,
                    cache_read_input_tokens=20,
                    cache_creation_input_tokens=10,
                    output_tokens=50,
                ),
            )

    provider._client = SimpleNamespace(messages=_Messages())

    with pytest.raises(LLMError, match=message):
        await provider.complete_structured(
            system="Return a value.",
            user="test",
            schema=_Answer,
        )

    assert provider.token_usage.requests == 1
    assert provider.token_usage.total_tokens == 180


async def test_resume_parsing_disables_reasoning() -> None:
    calls: list[dict[str, object]] = []

    class _Provider:
        async def complete_structured(self, **kwargs):
            calls.append(kwargs)
            return kwargs["schema"]()

    await parse_resume(_Provider(), "Jane Doe\nSoftware Engineer")
    assert calls[0]["reasoning"] is False
