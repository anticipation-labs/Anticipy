"""
Provider clients for the LLM router.

One client per provider, each exposing ``complete(messages, model, **kwargs)``
that returns a ``ProviderResponse``. All clients use ``httpx.AsyncClient``
(project convention) and read API keys from environment variables.

Providers:
  - DeepSeekClient  (direct API, cheapest cache-hit rate, V4 Flash default)
  - GeminiClient    (Google direct, vision-capable, 2.5 Flash and 2.5 Pro)
  - PerplexityClient (Sonar via OpenRouter passthrough for grounded lookups)
  - OpenAIClient    (fallback only, GPT-4.1-nano for cheap text)

The router is responsible for picking a client and handling fallthrough.
Response post-processing (em-dash strip, citation marker cleanup) lives in
``sanitize_text``.

Pricing tables here are USD per 1M tokens; they MUST match
planning/00-handoff/RESEARCH/llm-cost-routing.md. If the research file
changes, update this file too.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


logger = logging.getLogger("engine.llm_router.providers")


# Per-spec pricing (USD per 1M tokens). cache_hit_factor applies on top of
# input price when the provider reports a cache hit. None means caching
# either is automatic, free, or not modelled here.
PRICING: dict[str, dict[str, float]] = {
    # DeepSeek direct API
    "deepseek-v4-flash": {
        "input": 0.14,
        "cached_input": 0.0028,
        "output": 0.28,
    },
    # Gemini 2.5 Flash (Google direct)
    "gemini-2.5-flash": {
        "input": 0.30,
        "cached_input": 0.03,
        "output": 2.50,
    },
    # Gemini 2.5 Pro (Google direct), escalation only
    "gemini-2.5-pro": {
        "input": 1.25,
        "cached_input": 0.125,
        "output": 10.00,
    },
    # Perplexity Sonar via OpenRouter passthrough; we treat the per-request
    # search fee as already amortised into the input/output rates here.
    # Real cost is input + output + (search_fee/1000_requests).
    "perplexity/sonar": {
        "input": 1.00,
        "cached_input": 1.00,
        "output": 1.00,
        "request_fee": 0.005,
    },
    # OpenAI fallback option (cheap nano)
    "gpt-4.1-nano": {
        "input": 0.10,
        "cached_input": 0.025,
        "output": 0.40,
    },
}


# Citation markers Perplexity Sonar puts inline like [1], [2], etc.
_CITATION_RE = re.compile(r"\s*\[\d+\]")
# Em-dash characters we must scrub before returning to user-facing layers.
_EMDASH_CHARS = ("—", "–")


def sanitize_text(text: str) -> str:
    """Strip em-dashes and Perplexity-style citation markers.

    Replaces U+2014 (em dash) and U+2013 (en dash) with a comma + space, then
    strips trailing whitespace. Citation markers like ``[1]`` are removed
    in place. Preserves all other punctuation.
    """
    if not text:
        return text
    cleaned = text
    for ch in _EMDASH_CHARS:
        cleaned = cleaned.replace(ch, ", ")
    cleaned = _CITATION_RE.sub("", cleaned)
    # Collapse runs of double spaces introduced by the replacement.
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned.strip()


@dataclass
class ProviderResponse:
    """Normalized response from any provider."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Raised by a provider client when the upstream call fails."""

    def __init__(self, provider: str, status: int | None, message: str):
        self.provider = provider
        self.status = status
        self.message = message
        super().__init__(f"[{provider}] status={status} {message}")


def _cost_for(model: str, input_tokens: int, output_tokens: int, cached_tokens: int) -> float:
    """Compute USD cost for a single call given token counts.

    Cached tokens are charged at ``cached_input`` rate, fresh input tokens at
    ``input`` rate, and all output tokens at ``output`` rate. Perplexity Sonar
    adds a flat per-request search fee.
    """
    p = PRICING.get(model)
    if not p:
        return 0.0
    fresh = max(0, input_tokens - cached_tokens)
    cost = (
        (fresh / 1_000_000) * p["input"]
        + (cached_tokens / 1_000_000) * p.get("cached_input", p["input"])
        + (output_tokens / 1_000_000) * p["output"]
    )
    cost += float(p.get("request_fee", 0.0))
    return cost


# Module-level injection point for tests. When set, providers use this
# function instead of httpx; signature is async (method, url, headers, json) -> dict.
_TEST_HOOK = None


def set_http_hook(hook):
    """Install a test hook that replaces the httpx call."""
    global _TEST_HOOK
    _TEST_HOOK = hook


def clear_http_hook():
    """Remove the test hook."""
    global _TEST_HOOK
    _TEST_HOOK = None


async def _post_json(
    url: str, headers: dict[str, str], payload: dict, timeout: float = 60.0
) -> dict:
    """POST a JSON request and parse the response.

    Tests can patch the module-level hook to avoid real network calls. On
    HTTP errors (status >= 400) raises ProviderError. Returns the parsed JSON.
    """
    if _TEST_HOOK is not None:
        return await _TEST_HOOK("POST", url, headers, payload)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            body = resp.text[:400] if resp.text else ""
            raise ProviderError("http", resp.status_code, body)
        return resp.json()


# --- DeepSeek direct API client ----------------------------------------------


class DeepSeekClient:
    """Calls DeepSeek's direct API (NOT OpenRouter).

    Cache-hit input is 1/50 the cache-miss price. Caching is automatic on
    DeepSeek's side; we just report the ``prompt_cache_hit_tokens`` field they
    return.
    """

    BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    DEFAULT_MODEL = "deepseek-v4-flash"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        # Empty key is tolerated at construction time (tests inject the hook).
        # Real calls without a key will raise ProviderError at request time.

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        **kwargs,
    ) -> ProviderResponse:
        model_to_use = model or self.DEFAULT_MODEL
        if not self.api_key and _TEST_HOOK is None:
            raise ProviderError("deepseek", None, "DEEPSEEK_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # DeepSeek model id format: deepseek-chat (V4 Flash default route)
        deepseek_model = "deepseek-chat" if model_to_use == "deepseek-v4-flash" else model_to_use
        payload = {
            "model": deepseek_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        data = await _post_json(self.BASE_URL, headers, payload)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("deepseek", None, "no choices in response")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens", 0) or 0)
        out_tok = int(usage.get("completion_tokens", 0) or 0)
        cached_tok = int(usage.get("prompt_cache_hit_tokens", 0) or 0)

        cost = _cost_for(model_to_use, in_tok, out_tok, cached_tok)
        return ProviderResponse(
            content=sanitize_text(content),
            model=model_to_use,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=cached_tok,
            cost_usd=cost,
            raw=data,
        )


# --- Gemini direct API client ------------------------------------------------


class GeminiClient:
    """Calls Google Gemini direct API for vision and escalation."""

    BASE_URL_FMT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    DEFAULT_MODEL = "gemini-2.5-flash"

    # Map our friendly names to Gemini API model IDs.
    MODEL_ID_MAP = {
        "gemini-2.5-flash": "gemini-2.5-flash",
        "gemini-2.5-pro": "gemini-2.5-pro",
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        **kwargs,
    ) -> ProviderResponse:
        model_to_use = model or self.DEFAULT_MODEL
        if not self.api_key and _TEST_HOOK is None:
            raise ProviderError("gemini", None, "GOOGLE_API_KEY not set")

        api_model_id = self.MODEL_ID_MAP.get(model_to_use, model_to_use)
        url = self.BASE_URL_FMT.format(model=api_model_id) + f"?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        # Convert OpenAI-style messages to Gemini's contents array.
        contents = []
        for m in messages:
            role = "user" if m.get("role") in ("user", "system") else "model"
            contents.append({
                "role": role,
                "parts": [{"text": str(m.get("content", ""))}],
            })
        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }

        data = await _post_json(url, headers, payload)
        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderError("gemini", None, "no candidates in response")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        content = "".join(str(p.get("text", "")) for p in parts)
        usage = data.get("usageMetadata") or {}
        in_tok = int(usage.get("promptTokenCount", 0) or 0)
        out_tok = int(usage.get("candidatesTokenCount", 0) or 0)
        cached_tok = int(usage.get("cachedContentTokenCount", 0) or 0)

        cost = _cost_for(model_to_use, in_tok, out_tok, cached_tok)
        return ProviderResponse(
            content=sanitize_text(content),
            model=model_to_use,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=cached_tok,
            cost_usd=cost,
            raw=data,
        )


# --- Perplexity via OpenRouter ----------------------------------------------


class PerplexityClient:
    """Calls Perplexity Sonar through OpenRouter for grounded web lookups.

    Going through OpenRouter avoids managing a separate Perplexity API key for
    now. Cost includes a per-request search fee (~$0.005). See spec.
    """

    BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_MODEL = "perplexity/sonar"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        **kwargs,
    ) -> ProviderResponse:
        model_to_use = model or self.DEFAULT_MODEL
        if not self.api_key and _TEST_HOOK is None:
            raise ProviderError("perplexity", None, "OPENROUTER_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        data = await _post_json(self.BASE_URL, headers, payload)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("perplexity", None, "no choices in response")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens", 0) or 0)
        out_tok = int(usage.get("completion_tokens", 0) or 0)

        cost = _cost_for(model_to_use, in_tok, out_tok, 0)
        return ProviderResponse(
            content=sanitize_text(content),
            model=model_to_use,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=0,
            cost_usd=cost,
            raw=data,
        )


# --- OpenAI fallback client --------------------------------------------------


class OpenAIClient:
    """OpenAI fallback. Only used when the primary provider errors out."""

    BASE_URL = "https://api.openai.com/v1/chat/completions"
    DEFAULT_MODEL = "gpt-4.1-nano"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.4,
        **kwargs,
    ) -> ProviderResponse:
        model_to_use = model or self.DEFAULT_MODEL
        if not self.api_key and _TEST_HOOK is None:
            raise ProviderError("openai", None, "OPENAI_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_to_use,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        data = await _post_json(self.BASE_URL, headers, payload)
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("openai", None, "no choices in response")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens", 0) or 0)
        out_tok = int(usage.get("completion_tokens", 0) or 0)
        cached_tok = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0)

        cost = _cost_for(model_to_use, in_tok, out_tok, cached_tok)
        return ProviderResponse(
            content=sanitize_text(content),
            model=model_to_use,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cached_tokens=cached_tok,
            cost_usd=cost,
            raw=data,
        )


# --- Factory -----------------------------------------------------------------

# Static map from canonical model name to a fresh client instance creator.
# The router uses this for dispatch and for fallthrough swaps.
def get_client_for_model(model: str):
    """Return the right client class instance for ``model``.

    Raises ValueError if the model is unknown.
    """
    if model.startswith("deepseek"):
        return DeepSeekClient()
    if model.startswith("gemini"):
        return GeminiClient()
    if model.startswith("perplexity"):
        return PerplexityClient()
    if model.startswith("gpt-"):
        return OpenAIClient()
    raise ValueError(f"unknown model: {model}")


__all__ = [
    "ProviderResponse",
    "ProviderError",
    "DeepSeekClient",
    "GeminiClient",
    "PerplexityClient",
    "OpenAIClient",
    "get_client_for_model",
    "sanitize_text",
    "set_http_hook",
    "clear_http_hook",
    "PRICING",
]
