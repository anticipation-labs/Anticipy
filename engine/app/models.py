"""
LLM API wrapper with automatic retry, fallback chain, 5-strategy JSON extraction,
and cumulative cost tracking. Uses raw httpx — no SDK imports.

Per-provider throttling and slot serialization live here so that fan-out
(asyncio.gather) over the same provider does not exceed its rate limit and
different providers run independently.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

import httpx

from app.config import (
    MODEL_CHAIN,
    MAX_COST_USD,
    ROLE_CHAINS,
    COST_MONTHLY_CAP_USD,
)
from app.cost_watch import (
    CostCapExceeded,
    assert_under_cap,
    log_paid_call,
)


logger = logging.getLogger("engine")


def _chain_for_role(role: str | None) -> list[dict]:
    """Return the model chain to try for ``role``.

    ``role=None`` (default) ⇒ the legacy MODEL_CHAIN. Known role names use
    their dedicated chain. An empty role chain (e.g. critic with neither
    Mistral nor Gemini configured) gracefully falls back to MODEL_CHAIN so
    the system stays responsive. Unknown role names are treated as None.
    """
    if not role:
        return MODEL_CHAIN
    chain = ROLE_CHAINS.get(role)
    if chain is None:
        return MODEL_CHAIN
    if not chain:
        # Role known but no providers configured for it ⇒ degrade rather
        # than fail. The role-diversity invariant is best-effort.
        logger.warning(
            "role chain for %r is empty; falling back to MODEL_CHAIN", role,
        )
        return MODEL_CHAIN
    return chain


class DegradedResponse:
    """
    Sentinel returned by the LLM cascade when every provider in MODEL_CHAIN
    failed (network / 4xx / unparseable). Falsy and not a dict, so existing
    callers using `if result and isinstance(result, dict)` keep working —
    new callers can `isinstance(x, DegradedResponse)` to fail closed.
    """

    __slots__ = ()

    def __bool__(self) -> bool:  # noqa: D401
        return False

    def __repr__(self) -> str:
        return "<DegradedResponse>"


@dataclass
class CostTracker:
    """Tracks cumulative cost for a single task."""
    total_usd: float = 0.0
    calls: int = 0

    def add(self, input_tokens: int, output_tokens: int, cost_in: float, cost_out: float) -> None:
        self.total_usd += (input_tokens / 1000) * cost_in + (output_tokens / 1000) * cost_out
        self.calls += 1

    @property
    def exceeded(self) -> bool:
        return self.total_usd >= MAX_COST_USD


# ─────────────────────────────────────────────────────────────────────────────
# Per-provider throttle + slot
#
# Many free / low-tier providers cap ~1 request per ~1.2s. Without spacing,
# 3-way asyncio.gather → 429s; with spacing the slowest queue still finishes
# inside the layer timeout if `effective_layer_timeout_seconds` pads.
#
# State is *module-global* on purpose: every component that calls a provider
# shares the same lock so cross-feature fan-out (proactive + intent extract
# in the same task) cooperates.
# ─────────────────────────────────────────────────────────────────────────────

_throttle_locks: dict[str, asyncio.Lock] = {}
_throttle_last_call: dict[str, float] = {}
_provider_semaphores: dict[str, asyncio.Semaphore] = {}

# ─────────────────────────────────────────────────────────────────────────────
# Per-provider quota tracking. When a provider returns 429 the cascade marks
# it blocked-until-X and skips it on subsequent calls until the cooldown
# expires. Cooldown grows exponentially on repeat 429s (5s, 10s, 20s, …, 60s
# cap). On a successful call the failure count resets.
#
# This kills the "all providers throttled simultaneously" failure mode that
# corrupted the previous hostile-suite run — instead of hammering each
# provider's retry budget linearly, the cascade routes around the blocked
# ones and sleeps only when EVERY provider in MODEL_CHAIN is in cooldown.
# Cop-out #18: provider exhaustion is not an excuse.
# ─────────────────────────────────────────────────────────────────────────────

_provider_quota_until: dict[str, float] = {}
_provider_failure_count: dict[str, int] = {}

_QUOTA_BASE_COOLDOWN_S = 5.0
_QUOTA_MAX_COOLDOWN_S = 60.0


def _is_provider_quota_blocked(provider: str) -> tuple[bool, float]:
    """Returns (blocked, unblock_at_ts).
    blocked=True means callers should skip this provider for now."""
    until = _provider_quota_until.get(provider, 0.0)
    return (time.monotonic() < until, until)


def _mark_provider_429(provider: str) -> None:
    """Mark a provider as quota-blocked with exponential backoff cooldown.
    First 429 → 5s, then 10s, 20s, 40s, capped at 60s."""
    failures = _provider_failure_count.get(provider, 0) + 1
    _provider_failure_count[provider] = failures
    cooldown = min(
        _QUOTA_BASE_COOLDOWN_S * (2 ** (failures - 1)),
        _QUOTA_MAX_COOLDOWN_S,
    )
    _provider_quota_until[provider] = time.monotonic() + cooldown
    logger.warning(
        "provider quota-blocked: %s for %.1fs (consecutive 429 #%d)",
        provider, cooldown, failures,
    )


def _mark_provider_ok(provider: str) -> None:
    """Clear quota state on a successful call."""
    if _provider_failure_count.get(provider, 0) > 0:
        _provider_failure_count[provider] = 0
    _provider_quota_until.pop(provider, None)


def _earliest_unblock_time() -> float | None:
    """Returns the earliest monotonic timestamp at which any currently-blocked
    provider will unblock, or None if no provider is blocked."""
    if not _provider_quota_until:
        return None
    now = time.monotonic()
    upcoming = [t for t in _provider_quota_until.values() if t > now]
    return min(upcoming) if upcoming else None


def _reset_provider_quotas() -> None:
    """Test helper. Production code should not call this."""
    _provider_quota_until.clear()
    _provider_failure_count.clear()


def _get_lock(provider: str) -> asyncio.Lock:
    lock = _throttle_locks.get(provider)
    if lock is None:
        lock = asyncio.Lock()
        _throttle_locks[provider] = lock
    return lock


def _get_semaphore(provider: str) -> asyncio.Semaphore:
    sem = _provider_semaphores.get(provider)
    if sem is None:
        sem = asyncio.Semaphore(1)
        _provider_semaphores[provider] = sem
    return sem


async def _await_throttle(provider: str, min_interval: float) -> None:
    """
    Block until at least `min_interval` seconds have passed since the last
    call to `provider`. min_interval <= 0 is a no-op. Safe to call from
    many concurrent coroutines on the same provider — they serialize.
    """
    if min_interval <= 0:
        return
    lock = _get_lock(provider)
    async with lock:
        last = _throttle_last_call.get(provider, 0.0)
        now = time.monotonic()
        wait = (last + min_interval) - now
        if wait > 0:
            await asyncio.sleep(wait)
            now = time.monotonic()
        _throttle_last_call[provider] = now


@contextlib.asynccontextmanager
async def provider_slot(
    provider: str, min_interval: float
) -> AsyncIterator[None]:
    """
    Async context manager that combines a per-provider Semaphore(1) with the
    throttle so that:
      - only one coroutine is *inside* the call to `provider` at a time
      - the throttle still applies on entry
      - different providers run in parallel (independent semaphores)
    """
    sem = _get_semaphore(provider)
    async with sem:
        await _await_throttle(provider, min_interval)
        yield


def effective_layer_timeout_seconds(
    base: float, expected_concurrent_calls: int = 1
) -> float:
    """
    Pad a layer's `asyncio.wait_for` budget so that fan-out across
    `expected_concurrent_calls` coroutines on the *same* provider has time to
    drain through the throttle.

    Formula: base + (N - 1) * MODEL_CHAIN[0].min_interval_seconds. If the
    primary provider has no throttle (or MODEL_CHAIN is empty), returns base.
    """
    if expected_concurrent_calls <= 1:
        return base
    if not MODEL_CHAIN:
        return base
    primary = MODEL_CHAIN[0]
    interval = float(primary.get("min_interval_seconds", 0.0) or 0.0)
    if interval <= 0:
        return base
    return base + (expected_concurrent_calls - 1) * interval


def _strip_json(text: str) -> str:
    """Strategy 1: Extract the first JSON object from potentially wrapped text."""
    # Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text)
    text = text.strip()

    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]

    # If no closing }, the response was truncated — try to close it
    if start != -1 and end == -1:
        partial = text[start:]
        # Try adding a closing quote + }
        for suffix in ['"}', '"}', 'null}', '}']:
            attempt = partial + suffix
            try:
                json.loads(attempt)
                return attempt
            except (json.JSONDecodeError, ValueError):
                continue
    return text


def _fix_json_string(text: str) -> str:
    """Strategy 2: Fix common JSON issues (single quotes, trailing commas, unquoted keys)."""
    # Replace single quotes with double quotes (naive but handles most cases)
    fixed = text.replace("'", '"')
    # Remove trailing commas before closing braces
    fixed = re.sub(r",\s*}", "}", fixed)
    fixed = re.sub(r",\s*]", "]", fixed)
    return fixed


def _extract_key_value_pairs(text: str) -> dict | None:
    """Strategy 3: Extract key-value pairs using regex when JSON parsing fails."""
    # Look for action, target, value patterns
    action_match = re.search(r'"?action"?\s*[=:]\s*"?(\w+)"?', text, re.IGNORECASE)
    target_match = re.search(r'"?target"?\s*[=:]\s*"?([A-O]|null)"?', text, re.IGNORECASE)
    value_match = re.search(r'"?value"?\s*[=:]\s*"([^"]*)"', text, re.IGNORECASE)

    if action_match:
        result = {"action": action_match.group(1).lower()}
        if target_match:
            t = target_match.group(1)
            result["target"] = None if t.lower() == "null" else t.upper()
        else:
            result["target"] = None
        if value_match:
            result["value"] = value_match.group(1)
        else:
            result["value"] = None
        return result
    return None


def _keyword_extraction(text: str) -> dict | None:
    """Strategy 4: Last-resort keyword extraction from freeform text."""
    text_lower = text.lower().strip()

    # Check for done/stuck/need_info first
    if any(kw in text_lower for kw in ["done", "complete", "finished", "task completed"]):
        # Try to extract an answer value
        for pattern in [r'answer[:\s]+"([^"]+)"', r"answer[:\s]+(.+?)(?:\.|$)"]:
            m = re.search(pattern, text_lower)
            if m:
                return {"action": "done", "target": None, "value": m.group(1).strip()}
        return {"action": "done", "target": None, "value": None}

    if "stuck" in text_lower:
        return {"action": "stuck", "target": None, "value": None}

    if any(kw in text_lower for kw in ["need info", "need more info", "need information"]):
        return {"action": "need_info", "target": None, "value": text[:100]}

    # Check for click/type actions with letter labels
    click_match = re.search(r"click\s+(?:on\s+)?(?:\[)?([A-O])(?:\])?", text, re.IGNORECASE)
    if click_match:
        return {"action": "click", "target": click_match.group(1).upper(), "value": None}

    type_match = re.search(r"type\s+['\"]?(.+?)['\"]?\s+(?:in(?:to)?)\s+(?:\[)?([A-O])(?:\])?", text, re.IGNORECASE)
    if type_match:
        return {"action": "type", "target": type_match.group(2).upper(), "value": type_match.group(1)}

    scroll_match = re.search(r"scroll\s+(up|down)", text, re.IGNORECASE)
    if scroll_match:
        return {"action": "scroll", "target": None, "value": scroll_match.group(1).lower()}

    navigate_match = re.search(r"navigate\s+(?:to\s+)?(https?://\S+)", text, re.IGNORECASE)
    if navigate_match:
        return {"action": "navigate", "target": None, "value": navigate_match.group(1)}

    return None


def _validate_json(text: str) -> dict | None:
    """Try to parse as JSON dict. Return None on failure."""
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def _parse_json_5_strategies(text: str) -> dict | None:
    """
    5-strategy JSON parsing (V42):
    1. Direct extraction and parse
    2. Fix common JSON syntax issues
    3. Regex key-value extraction
    4. Keyword extraction from freeform text
    5. Give up (return None)
    """
    # Strategy 1: Standard extraction
    cleaned = _strip_json(text)
    result = _validate_json(cleaned)
    if result:
        return result

    # Strategy 2: Fix common issues
    fixed = _fix_json_string(cleaned)
    result = _validate_json(fixed)
    if result:
        return result

    # Strategy 3: Regex extraction of key-value pairs
    result = _extract_key_value_pairs(text)
    if result:
        return result

    # Strategy 4: Keyword extraction
    result = _keyword_extraction(text)
    if result:
        return result

    # Strategy 5: Give up
    return None


async def _call_openai_compatible(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 256,
    json_mode: bool = False,
) -> tuple[str, int, int]:
    """Call an OpenAI-compatible chat completions endpoint. Returns (text, input_tokens, output_tokens)."""
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return "", 0, 0
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        if not isinstance(text, str):
            text = str(text)
        usage = data.get("usage") or {}
        return text, int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0)


async def _call_gemini(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 256,
    json_mode: bool = False,
) -> tuple[str, int, int]:
    """Call Google Gemini REST API. Returns (text, input_tokens, output_tokens)."""
    # The API key is passed via header rather than the URL so it doesn't leak
    # into proxy logs.  (Gemini accepts both forms.)
    url = f"{base_url}/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    # Convert OpenAI-style messages to Gemini contents format
    contents = []
    system_text = ""
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "user")
        text = m.get("content", "")
        if not isinstance(text, str):
            text = str(text)
        if role == "system":
            system_text = text
            continue
        gemini_role = "user" if role == "user" else "model"
        contents.append({"role": gemini_role, "parts": [{"text": text}]})

    # Prepend system text to first user message if present
    if system_text and contents:
        first = contents[0]
        first["parts"][0]["text"] = system_text + "\n\n" + first["parts"][0]["text"]

    gen_cfg: dict = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
        "thinkingConfig": {"thinkingBudget": 0},
    }
    if json_mode:
        gen_cfg["responseMimeType"] = "application/json"
    body = {
        "contents": contents,
        "generationConfig": gen_cfg,
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return "", 0, 0
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = parts[0].get("text", "") if parts else ""
        if not isinstance(text, str):
            text = str(text)
        usage = data.get("usageMetadata") or {}
        return (
            text,
            int(usage.get("promptTokenCount", 0) or 0),
            int(usage.get("candidatesTokenCount", 0) or 0),
        )


async def _call_model(
    model_cfg: dict,
    messages: list[dict],
    temperature: float = 0.0,
    max_tokens: int = 256,
    json_mode: bool = False,
) -> tuple[str, int, int]:
    """Dispatch to the correct backend based on model name. Honors the
    per-provider throttle via `provider_slot`. When `json_mode=True`,
    asks the provider for native JSON output (Gemini responseMimeType,
    OpenAI-compat response_format)."""
    interval = float(model_cfg.get("min_interval_seconds", 0.0) or 0.0)
    async with provider_slot(model_cfg["name"], interval):
        if model_cfg["name"] == "gemini":
            return await _call_gemini(
                model_cfg["base_url"],
                model_cfg["api_key"],
                model_cfg["model"],
                messages,
                temperature,
                max_tokens,
                json_mode=json_mode,
            )
        return await _call_openai_compatible(
            model_cfg["base_url"],
            model_cfg["api_key"],
            model_cfg["model"],
            messages,
            temperature,
            max_tokens,
            json_mode=json_mode,
        )


async def llm_call(
    messages: list[dict],
    tracker: CostTracker,
    temperature: float = 0.0,
    max_tokens: int = 256,
    require_json: bool = False,
    retries_per_model: int = 2,
    json_mode: bool = False,
    role: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
) -> str | dict | DegradedResponse:
    """
    Call LLMs with retry and fallback. Returns:
      - dict, when require_json=True and parsing succeeds on any provider
      - str, when require_json=False and any provider returns text
      - DegradedResponse(), when every provider in the role chain failed
        (or the chain is empty / the cost cap is exceeded). The sentinel is
        falsy so existing `if result and ...` callers work unchanged.

    role: "planner" | "critic" | "reflector" | "executor" | None.
      Selects a role-specific provider order from config.ROLE_CHAINS so
      different roles use different models (multi-agent diversity).
      None ⇒ legacy MODEL_CHAIN order (existing callers untouched).
    task_id / user_id: forwarded to ``cost_watch.log_paid_call`` so the
      audit log can be filtered. Both optional.

    Errors never propagate — they're logged at debug level and we move to the
    next model so callers don't see backend-specific stack traces.
    """
    if tracker.exceeded:
        return DegradedResponse()

    # Hard month-to-date cap (cop-out #15). Failure to query ⇒ proceed; we'd
    # rather log misses than block legitimate calls on an audit outage.
    try:
        await assert_under_cap(COST_MONTHLY_CAP_USD)
    except CostCapExceeded as e:
        logger.error("cost cap exceeded: %s", e)
        return DegradedResponse()
    except Exception:
        logger.debug("cost cap check raised; proceeding", exc_info=True)

    chain = _chain_for_role(role)
    if not chain:
        return DegradedResponse()

    # Two passes: first pass skips quota-blocked providers entirely. If every
    # provider was blocked, we sleep until the earliest unblock and try once
    # more. This prevents hammering rate-limited providers with retry budget
    # we know will fail (cop-out #18).
    for outer_pass in range(2):
        any_provider_attempted = False

        for model_cfg in chain:
            provider_name = model_cfg.get("name", "unknown")

            blocked, _ = _is_provider_quota_blocked(provider_name)
            if blocked:
                logger.debug("skipping quota-blocked provider %s", provider_name)
                continue

            any_provider_attempted = True

            for attempt in range(retries_per_model):
                if tracker.exceeded:
                    return DegradedResponse()
                try:
                    text, in_tok, out_tok = await _call_model(
                        model_cfg, messages, temperature, max_tokens,
                        json_mode=json_mode or require_json,
                    )
                    tracker.add(
                        in_tok,
                        out_tok,
                        model_cfg["cost_input"],
                        model_cfg["cost_output"],
                    )
                    _mark_provider_ok(provider_name)

                    # Audit trail — every successful paid call. Free providers
                    # log cost=0 (cop-out #14: don't filter, just record).
                    cost_in = float(model_cfg.get("cost_input", 0.0) or 0.0)
                    cost_out = float(model_cfg.get("cost_output", 0.0) or 0.0)
                    cost_usd = (in_tok / 1000.0) * cost_in + (out_tok / 1000.0) * cost_out
                    try:
                        await log_paid_call(
                            provider=provider_name,
                            model=str(model_cfg.get("model", "")),
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            cost_usd=cost_usd,
                            role=role,
                            task_id=task_id,
                            user_id=user_id,
                        )
                    except Exception:
                        logger.debug("cost_watch log raised; ignoring", exc_info=True)

                    if require_json:
                        parsed = _parse_json_5_strategies(text)
                        if parsed is not None:
                            return parsed
                        # JSON parse failed — retry on same model
                        if attempt < retries_per_model - 1:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        # Last attempt on this model — try next model
                        break
                    else:
                        return text.strip() if text else ""

                except httpx.HTTPStatusError as e:
                    status = e.response.status_code if e.response is not None else 0
                    logger.debug("LLM %s HTTP %s", provider_name, status)
                    if status == 429:
                        # Mark provider blocked; skip remaining attempts on this provider.
                        _mark_provider_429(provider_name)
                        break
                    if status == 402:
                        # Payment required (e.g. DeepSeek out of credit) — block
                        # for the maximum cooldown so we stop trying it within
                        # this session.
                        _provider_quota_until[provider_name] = (
                            time.monotonic() + _QUOTA_MAX_COOLDOWN_S
                        )
                        break
                    # Other 4xx — no retry on this model
                    break
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt < retries_per_model - 1:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    break
                except Exception:
                    logger.debug("LLM %s call failed", provider_name, exc_info=True)
                    if attempt < retries_per_model - 1:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    break

        # If at least one provider was attempted on this pass and we're here,
        # then either we returned a result already (we wouldn't be here) or
        # every attempted provider failed for non-quota reasons. No point in
        # a second pass.
        if any_provider_attempted:
            break

        # First pass had no providers to attempt — every one is quota-blocked.
        # Sleep until the earliest unblock, then try again. Cap the wait so we
        # don't hang the request indefinitely.
        unblock_at = _earliest_unblock_time()
        if unblock_at is None:
            break
        wait = min(max(0.0, unblock_at - time.monotonic()), _QUOTA_MAX_COOLDOWN_S)
        if wait <= 0.05:
            break
        logger.info(
            "all providers quota-blocked; sleeping %.1fs for first unblock", wait,
        )
        await asyncio.sleep(wait)

    return DegradedResponse()


async def llm_call_text(
    messages: list[dict],
    tracker: CostTracker,
    temperature: float = 0.0,
    max_tokens: int = 256,
    role: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
) -> str | DegradedResponse:
    """Call LLM and return text. Returns DegradedResponse() on full cascade
    failure so callers can `isinstance(x, DegradedResponse)` to fail closed.

    ``role`` selects a role-specific provider chain (see ROLE_CHAINS).
    """
    result = await llm_call(
        messages, tracker, temperature, max_tokens,
        require_json=False,
        role=role, task_id=task_id, user_id=user_id,
    )
    if isinstance(result, DegradedResponse):
        return result
    return str(result) if result is not None else ""


async def llm_call_json(
    messages: list[dict],
    tracker: CostTracker,
    temperature: float = 0.0,
    max_tokens: int = 256,
    role: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
) -> dict | DegradedResponse:
    """Call LLM and return parsed JSON dict, or DegradedResponse on full
    cascade failure. Callers should `isinstance(x, dict)` before consuming.

    ``role`` selects a role-specific provider chain (see ROLE_CHAINS).
    """
    result = await llm_call(
        messages, tracker, temperature, max_tokens,
        require_json=True,
        role=role, task_id=task_id, user_id=user_id,
    )
    if isinstance(result, dict):
        return result
    return DegradedResponse()


async def llm_call_json_str(
    messages: list[dict],
    tracker: CostTracker,
    temperature: float = 0.0,
    max_tokens: int = 256,
    role: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """Provider-native JSON mode. Returns a clean JSON *string* (parseable
    by `json.loads` with no fence stripping or regex recovery), or "" when
    every provider failed. Used by the proactive cascade adapter.

    ``role`` selects a role-specific provider chain (see ROLE_CHAINS).
    """
    if tracker.exceeded:
        return ""

    chain = _chain_for_role(role)
    if not chain:
        return ""

    for model_cfg in chain:
        for attempt in range(2):
            if tracker.exceeded:
                return ""
            try:
                text, in_tok, out_tok = await _call_model(
                    model_cfg, messages, temperature, max_tokens, json_mode=True,
                )
                tracker.add(
                    in_tok, out_tok,
                    model_cfg["cost_input"], model_cfg["cost_output"],
                )

                # Audit trail (cop-out #14).
                cost_in = float(model_cfg.get("cost_input", 0.0) or 0.0)
                cost_out = float(model_cfg.get("cost_output", 0.0) or 0.0)
                cost_usd = (in_tok / 1000.0) * cost_in + (out_tok / 1000.0) * cost_out
                try:
                    await log_paid_call(
                        provider=str(model_cfg.get("name", "unknown")),
                        model=str(model_cfg.get("model", "")),
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        cost_usd=cost_usd,
                        role=role,
                        task_id=task_id,
                        user_id=user_id,
                    )
                except Exception:
                    logger.debug("cost_watch log raised; ignoring", exc_info=True)

                if not text:
                    continue
                stripped = _strip_json(text)
                # Validate it parses; otherwise treat as a soft failure.
                try:
                    json.loads(stripped)
                    return stripped
                except (json.JSONDecodeError, ValueError):
                    if attempt < 1:
                        await asyncio.sleep(0.5)
                        continue
                    break
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else 0
                logger.debug("LLM %s HTTP %s (json_str)", model_cfg.get("name"), status)
                if status == 429 and attempt < 1:
                    await asyncio.sleep(2.0)
                    continue
                break
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt < 1:
                    await asyncio.sleep(1.0)
                    continue
                break
            except Exception:
                logger.debug("LLM %s json_str call failed", model_cfg.get("name"), exc_info=True)
                break

    return ""
