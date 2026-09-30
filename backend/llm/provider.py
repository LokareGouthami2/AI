"""LLM providers.

``AnthropicProvider`` calls Claude with structured outputs (JSON schema derived
from the Pydantic output model). ``ExtractiveProvider`` is a deterministic,
offline engine built from classical NLP — it lets every feature work without an
API key and is what the test-suite uses. Both return *unvalidated* Pydantic
objects; semantic validation happens in ``service.py``.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from backend.config import get_settings

log = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class LLMRefusal(LLMError):
    pass


@dataclass
class LLMResult:
    output: BaseModel | None
    raw: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    error: str | None = None


@dataclass
class TaskRequest:
    task: str  # clean | smart | assignment | exam | simple | flashcards | quiz | rag
    system: str
    user: str
    output_model: type[BaseModel]
    context: dict[str, Any] = field(default_factory=dict)  # used by the offline provider
    max_tokens: int = 16000


class LLMProvider:
    name = "base"
    model = ""

    def generate(self, req: TaskRequest) -> LLMResult:  # pragma: no cover - interface
        raise NotImplementedError


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, effort: str, fallbacks: bool, timeout: float):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=2)
        self.model = model
        self.effort = effort
        self.fallbacks = fallbacks

    def generate(self, req: TaskRequest, repair_messages: list[dict] | None = None) -> LLMResult:
        a = self._anthropic
        messages = [{"role": "user", "content": req.user}] + (repair_messages or [])
        kwargs = dict(
            model=self.model,
            max_tokens=req.max_tokens,
            system=req.system,
            messages=messages,
            output_format=req.output_model,
            output_config={"effort": self.effort},
        )
        try:
            if self.fallbacks:
                resp = self.client.beta.messages.parse(
                    **kwargs, betas=["server-side-fallback-2026-07-01"], fallbacks="default"
                )
            else:
                resp = self.client.messages.parse(**kwargs)
        except a.RateLimitError as exc:
            raise LLMError("The AI service is rate limited; try again shortly.") from exc
        except a.AuthenticationError as exc:
            raise LLMError("The AI service rejected the server's API key.") from exc
        except a.APIStatusError as exc:
            raise LLMError(f"AI service error ({exc.status_code}).") from exc
        except a.APIConnectionError as exc:
            raise LLMError("Could not reach the AI service.") from exc
        except Exception as exc:  # parse/validation failure inside the SDK helper
            return LLMResult(output=None, error=f"{type(exc).__name__}: {exc}", model=self.model)

        if resp.stop_reason == "refusal":
            raise LLMRefusal("The AI model declined this request.")
        raw = "".join(getattr(b, "text", "") for b in resp.content)
        usage = resp.usage
        return LLMResult(
            output=resp.parsed_output,
            raw=raw,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            model=getattr(resp, "model", self.model),
            error=None if resp.parsed_output is not None else f"unparseable output (stop_reason={resp.stop_reason})",
        )


class ExtractiveProvider(LLMProvider):
    """Offline, deterministic generator (no network, no API key)."""

    name = "offline"
    model = "extractive-v1"

    def generate(self, req: TaskRequest) -> LLMResult:
        from backend.llm import extractive

        fn = getattr(extractive, f"task_{req.task}")
        out = fn(**req.context)
        return LLMResult(output=out, raw=out.model_dump_json(), model=self.model)


@functools.lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    s = get_settings()
    key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None
    if s.llm_provider == "anthropic" or (s.llm_provider == "auto" and key):
        if not key:
            raise LLMError("WRITEAI_LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        log.info("LLM provider: anthropic (%s)", s.anthropic_model)
        return AnthropicProvider(key, s.anthropic_model, s.anthropic_effort, s.anthropic_fallbacks, s.llm_timeout_s)
    log.info("LLM provider: offline extractive engine")
    return ExtractiveProvider()
