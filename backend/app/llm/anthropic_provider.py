"""Anthropic adapter.

Uses GA JSON structured outputs, then validates the result with the caller's Pydantic
model. The generation schema marks every property as required: the resume models use
empty strings/lists for absent values, and making that explicit keeps the schema below
Anthropic's optional-property complexity limit without weakening constrained decoding.

Model notes (Claude Opus 4.8):
  * `thinking={"type": "adaptive"}` — the model decides how much to reason per request.
    Tailoring against a long JD genuinely benefits from it; there is no token budget to tune.
  * `temperature` / `top_p` / `top_k` are *removed* on this model and return a 400 if sent.
    Output variation is steered by the prompt instead. Do not reintroduce them.
"""

from __future__ import annotations

from typing import Any
from typing import TypeVar

from pydantic import BaseModel

from app.llm.base import LLMError, LLMProvider
from app.llm.usage import estimate_cost_usd

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-opus-4-8"


def _generation_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return an Anthropic-compatible strict schema for a default-heavy app model.

    Pydantic omits fields with defaults from JSON Schema's ``required`` arrays. That is
    convenient for the HTTP API, but StructuredResume has enough such fields to exceed
    Anthropic's limit of 24 optional properties. For generation, an absent string/list is
    already represented by an empty value, so requiring every key preserves the model's
    semantics and makes the grammar substantially simpler.
    """

    output = model.model_json_schema()

    def make_strict(node: Any) -> None:
        if isinstance(node, dict):
            node.pop("default", None)
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            for value in node.values():
                make_strict(value)
        elif isinstance(node, list):
            for value in node:
                make_strict(value)

    make_strict(output)
    return output


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    requires_key = True

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        if not api_key:
            raise LLMError(
                "No Anthropic API key configured. Add one in Settings, or switch provider."
            )
        self.model = model or DEFAULT_MODEL
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise LLMError("The `anthropic` package is not installed.") from exc
        self._client = AsyncAnthropic(api_key=api_key)

    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 16000,
        reasoning: bool = True,
    ) -> T:
        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": _generation_schema(schema),
                }
            },
        }
        if reasoning:
            request["thinking"] = {"type": "adaptive"}

        try:
            response = await self._client.messages.create(**request)
        except Exception as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc

        # Provider responses can consume billable tokens even when the model refuses,
        # truncates, or emits invalid JSON. Record usage before validating the payload.
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            cached_tokens = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            cache_write_tokens = int(
                getattr(usage, "cache_creation_input_tokens", 0) or 0
            )
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            self.record_usage(
                input_tokens=input_tokens,
                cached_input_tokens=cached_tokens,
                cache_write_input_tokens=cache_write_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=estimate_cost_usd(
                    "anthropic",
                    self.model,
                    input_tokens=input_tokens,
                    cached_input_tokens=cached_tokens,
                    cache_write_input_tokens=cache_write_tokens,
                    output_tokens=output_tokens,
                ),
            )

        if response.stop_reason == "refusal":
            raise LLMError(
                "The model declined this request. If the resume or job description "
                "contains unusual content, try editing it and retrying."
            )
        if response.stop_reason == "max_tokens":
            raise LLMError(
                "Model ran out of output tokens before completing the structured response."
            )

        text = next(
            (
                block.text
                for block in response.content
                if getattr(block, "type", None) == "text"
            ),
            None,
        )
        if not text:
            raise LLMError(
                f"Model returned no structured output (stop_reason={response.stop_reason})."
            )
        try:
            return schema.model_validate_json(text)
        except Exception as exc:
            raise LLMError(f"Anthropic returned invalid structured output: {exc}") from exc

    async def health(self) -> tuple[bool, str]:
        try:
            model = await self._client.models.retrieve(self.model)
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
        return True, f"Reachable — {model.display_name}"
