"""OpenAI structured response token accounting."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.llm.base import LLMError
from app.llm.openai_provider import OpenAIProvider


class _Answer(BaseModel):
    value: str


async def test_completion_usage_is_normalized_and_costed() -> None:
    provider = OpenAIProvider(api_key="test", model="gpt-4o")

    async def fake_parse(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        refusal=None,
                        parsed=_Answer(value="ok"),
                    )
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=50,
                prompt_tokens_details=SimpleNamespace(cached_tokens=20),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=10),
            ),
        )

    provider._parse = fake_parse
    result = await provider.complete_structured(
        system="Return a value.",
        user="test",
        schema=_Answer,
    )

    assert result.value == "ok"
    assert provider.token_usage.input_tokens == 80
    assert provider.token_usage.cached_input_tokens == 20
    assert provider.token_usage.output_tokens == 50
    assert provider.token_usage.reasoning_tokens == 10
    assert provider.token_usage.total_tokens == 150
    assert provider.token_usage.estimated_cost_usd == pytest.approx(0.000725)


@pytest.mark.parametrize(
    ("refusal", "parsed", "message"),
    [
        ("policy refusal", None, "declined"),
        (None, None, "no structured output"),
    ],
)
async def test_usage_is_recorded_before_response_validation(
    refusal, parsed, message
) -> None:
    provider = OpenAIProvider(api_key="test", model="gpt-4o")

    async def fake_parse(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(refusal=refusal, parsed=parsed)
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=50,
                prompt_tokens_details=SimpleNamespace(cached_tokens=20),
                completion_tokens_details=SimpleNamespace(reasoning_tokens=10),
            ),
        )

    provider._parse = fake_parse

    with pytest.raises(LLMError, match=message):
        await provider.complete_structured(
            system="Return a value.",
            user="test",
            schema=_Answer,
        )

    assert provider.token_usage.requests == 1
    assert provider.token_usage.total_tokens == 150
