"""The model gateway — one swappable entry point, cost-disciplined, now with a
real provider (OpenRouter) and vision.

`think(task, tier, caller, image=None)` routes through OUR gateway. Tiers map to
a cheap and a smart model (cost ladder). Provider precedence:
  explicit arg > ANTICIPY_MODEL_PROVIDER env > "stub" (default).
The default stays the deterministic stub so existing brain/hands tests are free
and reproducible; the web agent constructs a gateway with provider="openrouter".
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import List, Optional

CHEAP = "cheap"
SMART = "smart"
COST = {CHEAP: 0.0005, SMART: 0.02}

PROVIDER_STUB = "stub"
PROVIDER_OPENROUTER = "openrouter"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class ModelGateway:
    # gate + plan (proactive brain) and agent (the web-agent loop) may use smart
    SMART_CALLERS = frozenset({"gate", "plan", "agent"})

    def __init__(self, provider: Optional[str] = None, endpoint: Optional[str] = None,
                 stub=None, timeout: float = 60.0,
                 cheap_model: Optional[str] = None, smart_model: Optional[str] = None) -> None:
        self.provider = provider or os.environ.get("ANTICIPY_MODEL_PROVIDER", PROVIDER_STUB)
        self.endpoint = endpoint  # optional custom OpenAI-compatible endpoint
        self.timeout = timeout
        self.cheap_model = cheap_model or os.environ.get("ANTICIPY_MODEL_CHEAP", "openai/gpt-4o-mini")
        self.smart_model = smart_model or os.environ.get("ANTICIPY_MODEL_SMART", "openai/gpt-4o")
        self.calls: List[dict] = []
        self._stub = stub or default_stub
        self._key = os.environ.get("OPENROUTER_API_KEY")

    async def think(self, task: str, tier: str, caller: str, image: Optional[str] = None,
                    json_mode: bool = False, temperature: Optional[float] = None) -> str:
        if tier == SMART and caller not in self.SMART_CALLERS:
            raise PermissionError(f"smart tier not allowed from caller '{caller}'")
        self.calls.append({"tier": tier, "caller": caller, "cost": COST.get(tier, 0.0)})

        if self.provider == PROVIDER_OPENROUTER:
            return await self._openrouter(task, tier, caller, image, json_mode, temperature)
        if self.endpoint:
            return await self._custom_endpoint(task, tier)
        return self._stub(task, tier, caller)

    @property
    def smart_calls(self) -> List[dict]:
        return [c for c in self.calls if c["tier"] == SMART]

    def total_cost(self) -> float:
        return round(sum(c["cost"] for c in self.calls), 6)

    # ---- real provider: OpenRouter (OpenAI-compatible, vision-capable) ----
    async def _openrouter(self, task: str, tier: str, caller: str, image: Optional[str], json_mode: bool = False,
                          temperature: Optional[float] = None) -> str:
        if not self._key:
            raise RuntimeError("OPENROUTER_API_KEY NOT SET / NOT FUNDED")
        import httpx

        model = self.smart_model if tier == SMART else self.cheap_model
        content = task if image is None else [
            {"type": "text", "text": task},
            {"type": "image_url", "image_url": {"url": image}},
        ]
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy",
        }
        max_tokens_env = os.environ.get("ANTICIPY_MODEL_MAX_TOKENS")
        default_max_tokens = 2048 if caller == "agent" else 128
        try:
            max_tokens = int(max_tokens_env) if max_tokens_env else default_max_tokens
        except ValueError:
            max_tokens = default_max_tokens
        body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}  # force a parseable JSON object
        if temperature is not None:
            body["temperature"] = temperature  # low temp for stable, run-to-run decisions

        # Retry transient empties / 429 / 5xx — the provider intermittently returns
        # empty content under load, which would otherwise read as a spurious failure.
        last = ""
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
                if resp.status_code in (429, 500, 502, 503, 504):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                if 400 <= resp.status_code < 500:
                    try:
                        detail = resp.json().get("error") or resp.text
                    except Exception:
                        detail = resp.text
                    affordable = _affordable_tokens(detail)
                    if resp.status_code == 402 and affordable and 64 <= affordable < int(body["max_tokens"]):
                        body["max_tokens"] = affordable
                        await asyncio.sleep(0.2)
                        continue
                    raise RuntimeError(f"OpenRouter non-retryable error {resp.status_code}: {str(detail)[:300]}")
                resp.raise_for_status()
                content_out = (resp.json()["choices"][0].get("message") or {}).get("content")
                if content_out:
                    return content_out
                last = content_out or ""
                await asyncio.sleep(1.0 * (attempt + 1))  # empty -> brief backoff, retry
            except httpx.TransportError:
                await asyncio.sleep(1.5 * (attempt + 1))
        return last or ""

    async def _custom_endpoint(self, task: str, tier: str) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.endpoint, json={"tier": tier, "task": task})
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Deterministic stub "model" — reproducible, free, drives the brain tests.
# ---------------------------------------------------------------------------
def default_stub(task: str, tier: str, caller: str) -> str:
    t = task.lower()
    if caller == "gate":
        risky = any(k in t for k in ("wire money", "delete", "pay ", "transfer"))
        actionable = any(k in t for k in ("send", "book", "schedule", "email", "remind", "call", "set up"))
        decision = "ask_first" if risky else ("do_and_notify" if actionable else "ignore")
        return json.dumps({"decision": decision, "reason": f"stub gate read of: {task[:80]}"})

    if caller == "plan":
        steps = []
        if any(k in t for k in ("email", "send", "deck", "draft")):
            steps.append({"intent": "send_email",
                          "args": {"to": "Sarah", "subject": "Q3 deck", "body": "Attached."},
                          "risk": "needs_confirm"})
        if any(k in t for k in ("lunch", "book", "calendar", "meet", "schedule")):
            steps.append({"intent": "create_event",
                          "args": {"title": "Lunch with Sarah", "when": "Friday 12:00"}, "risk": "low"})
        if any(k in t for k in ("remind", "friday", "follow", "later")):
            steps.append({"intent": "write_memory",
                          "args": {"kind": "open_loop", "text": "Send Sarah the Q3 deck Friday"}, "risk": "low"})
        if any(k in t for k in ("post", "tweet", "launch", " x ", " x.", "on x")):
            steps.append({"intent": "post_to_x", "args": {"text": "We just launched. "}, "risk": "low"})
        if any(k in t for k in ("browse", "open ", "website", "site", "check the")):
            steps.append({"intent": "browse_task", "args": {"task": "open the page"}, "risk": "low"})
        if not steps:
            steps.append({"intent": "browse_task", "args": {"task": task}, "risk": "low"})
        return json.dumps({"steps": steps})

    return f"[stub:{tier}:{caller}] {task[:120]}"


def _affordable_tokens(detail) -> Optional[int]:
    message = detail.get("message") if isinstance(detail, dict) else str(detail)
    match = re.search(r"can only afford\s+(\d+)", message or "")
    return int(match.group(1)) if match else None
