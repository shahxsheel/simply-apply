"""Provider-agnostic LLM interface.

One method: given a system prompt, a user prompt, and a Pydantic model, return a
validated instance of that model. Everything the app asks an LLM to do — parsing a
resume, tailoring one — is structured extraction, so a single structured-output method
covers the whole surface.

Pushing schema validation into the interface (rather than returning a string and parsing
downstream) means each provider can use its *native* structured-output mechanism:
Anthropic's JSON schema output, OpenAI's `chat.completions.parse`, Ollama's `format`
JSON-schema parameter. That is strictly more reliable than asking for JSON in the prompt
and hoping — the model is constrained at decode time rather than corrected after the fact.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised for any provider failure — missing key, transport, or schema violation.

    The routers turn this into a 400 with the message intact, so the user sees
    "no API key configured for anthropic" rather than an opaque 500.
    """


@dataclass
class TokenUsage:
    """Provider-normalized token counts accumulated for one workflow."""

    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    requests: int = 0
    estimated_cost_usd: float | None = None

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.cached_input_tokens
            + self.cache_write_input_tokens
            + self.output_tokens
        )


class LLMProvider(ABC):
    name: str = ""
    #: False for local providers (Ollama) — the settings UI hides the key field.
    requires_key: bool = True

    @property
    def token_usage(self) -> TokenUsage:
        if not hasattr(self, "_token_usage"):
            self._token_usage = TokenUsage()
        return self._token_usage

    def record_usage(
        self,
        *,
        input_tokens: int = 0,
        cached_input_tokens: int = 0,
        cache_write_input_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        estimated_cost_usd: float | None = None,
    ) -> None:
        usage = self.token_usage
        usage.input_tokens += max(0, input_tokens)
        usage.cached_input_tokens += max(0, cached_input_tokens)
        usage.cache_write_input_tokens += max(0, cache_write_input_tokens)
        usage.output_tokens += max(0, output_tokens)
        usage.reasoning_tokens += max(0, reasoning_tokens)
        usage.requests += 1
        if estimated_cost_usd is not None:
            usage.estimated_cost_usd = (usage.estimated_cost_usd or 0) + estimated_cost_usd

    @abstractmethod
    async def complete_structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 16000,
        reasoning: bool = True,
    ) -> T:
        """Return an instance of `schema`, or raise LLMError.

        ``reasoning=False`` is for transcription-style work where extended reasoning
        adds latency without improving the result.
        """

    @abstractmethod
    async def health(self) -> tuple[bool, str]:
        """(reachable, detail) — powers the "Test connection" button in Settings."""
