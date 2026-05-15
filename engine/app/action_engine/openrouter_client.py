"""OpenRouter client for the Anticipy action engine. Phase V4-2.

Thin wrapper over OpenRouter's OpenAI-compatible chat completions
endpoint with: vision support, primary->fallback model routing,
429/5xx/timeout retry with exponential backoff, and structured
per-call logging for real cost accounting.

Hard architecture facts (verified against the live catalog in V4-0,
2026-05-15):

  deepseek/deepseek-v4-flash : text only.   TEXT steps.
  moonshotai/kimi-k2.6       : text+image.  VISION steps + fallback.

BOTH are reasoning models on OpenRouter. Every response carries a
`reasoning` field and a `content` field. If max_tokens is small the
reasoning consumes the whole budget and `content` comes back null
with finish_reason="length". So:

  - MIN_TOKENS floor of 256 is enforced on every call.
  - The client returns `content`; if `content` is null/empty but
    `reasoning` is present, that signals a starved budget and the
    call is retried once with a doubled token budget.

No em-dashes. No fabrication. The call log is the real cost ledger.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

ENV_PATH = os.path.expanduser("~/.anticipy/.env")
load_dotenv(ENV_PATH)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
CALL_LOG = Path(os.path.expanduser("~/.anticipy/openrouter_calls.jsonl"))

TEXT_MODEL = "deepseek/deepseek-v4-flash"
VISION_MODEL = "moonshotai/kimi-k2.6"

# Reasoning-model floor. Below this, `content` is reliably starved.
MIN_TOKENS = 256

# OpenRouter pricing per million tokens (USD), for the call ledger.
# Updated from the live catalog if it drifts; these are the V4-0 values.
PRICING = {
    "deepseek/deepseek-v4-flash": {"in": 0.30, "out": 0.50},
    "deepseek/deepseek-v4-pro": {"in": 0.435, "out": 0.87},
    "moonshotai/kimi-k2.6": {"in": 0.60, "out": 2.50},
}


@dataclass
class ORResponse:
    content: str
    model: str
    latency_s: float
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning: str = ""
    finish_reason: str = ""
    cost_usd: float = 0.0
    raw: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.content)


def screenshot_to_image_block(png_bytes: bytes) -> dict:
    """OpenRouter vision content block from raw PNG bytes."""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}


def _estimate_cost(model: str, p_tok: int, c_tok: int) -> float:
    rate = PRICING.get(model)
    if not rate:
        return 0.0
    return (p_tok / 1_000_000.0) * rate["in"] + (c_tok / 1_000_000.0) * rate["out"]


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None, timeout_s: float = 90.0):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key.startswith("sk-or-"):
            raise RuntimeError(
                f"OPENROUTER_API_KEY missing/malformed (looked in {ENV_PATH})"
            )
        self.timeout_s = timeout_s

    # ── core call ─────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict],
        model: str = TEXT_MODEL,
        max_tokens: int = 512,
        temperature: float = 0.0,
        image_b64: Optional[str] = None,
        response_format: Optional[dict] = None,
        _retry_on_starve: bool = True,
    ) -> ORResponse:
        """One chat completion. If image_b64 is given it is appended as
        a vision block to the LAST user message (model must be vision
        capable; use VISION_MODEL). 429/5xx/timeout retried with
        exponential backoff up to ~30s total."""
        max_tokens = max(max_tokens, MIN_TOKENS)
        msgs = [dict(m) for m in messages]
        if image_b64:
            # Attach the image to the last user turn.
            for m in reversed(msgs):
                if m.get("role") == "user":
                    block = [{"type": "text", "text": m["content"]}] if isinstance(m["content"], str) else list(m["content"])
                    block.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    })
                    m["content"] = block
                    break

        payload: dict[str, Any] = {
            "model": model,
            "messages": msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

        backoffs = [1.0, 2.0, 4.0, 8.0, 15.0]
        attempt = 0
        t0 = time.monotonic()
        last_err = "unknown"
        while attempt <= len(backoffs):
            try:
                r = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://anticipy.ai",
                        "X-Title": "Anticipy Action Engine",
                    },
                    json=payload,
                    timeout=self.timeout_s,
                )
            except (requests.Timeout, requests.ConnectionError) as e:
                last_err = f"transport: {e}"
                if attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                    attempt += 1
                    continue
                return self._log_and_return(ORResponse(
                    content="", model=model, latency_s=time.monotonic() - t0,
                    error=last_err), payload)

            if r.status_code == 429 or r.status_code >= 500:
                last_err = f"http {r.status_code}: {r.text[:160]}"
                if attempt < len(backoffs):
                    time.sleep(backoffs[attempt])
                    attempt += 1
                    continue
                return self._log_and_return(ORResponse(
                    content="", model=model, latency_s=time.monotonic() - t0,
                    error=last_err), payload)

            if r.status_code != 200:
                return self._log_and_return(ORResponse(
                    content="", model=model, latency_s=time.monotonic() - t0,
                    error=f"http {r.status_code}: {r.text[:200]}"), payload)

            j = r.json()
            if "choices" not in j or not j["choices"]:
                return self._log_and_return(ORResponse(
                    content="", model=model, latency_s=time.monotonic() - t0,
                    error=f"no choices: {json.dumps(j)[:200]}", raw=j), payload)

            choice = j["choices"][0]
            msg = choice.get("message", {})
            content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning") or "")
            finish = choice.get("finish_reason", "")
            usage = j.get("usage", {})
            p_tok = usage.get("prompt_tokens", 0)
            c_tok = usage.get("completion_tokens", 0)
            resp = ORResponse(
                content=content,
                model=j.get("model", model),
                latency_s=time.monotonic() - t0,
                prompt_tokens=p_tok,
                completion_tokens=c_tok,
                reasoning=reasoning if isinstance(reasoning, str) else "",
                finish_reason=finish,
                cost_usd=_estimate_cost(model, p_tok, c_tok),
                raw=j,
            )

            # Reasoning model starved the answer: retry once, 2x budget.
            if (not content and reasoning and finish == "length"
                    and _retry_on_starve):
                self._log(resp, payload)
                return self.chat(
                    messages, model=model, max_tokens=max_tokens * 2,
                    temperature=temperature, image_b64=image_b64,
                    response_format=response_format, _retry_on_starve=False,
                )
            return self._log_and_return(resp, payload)

        return self._log_and_return(ORResponse(
            content="", model=model, latency_s=time.monotonic() - t0,
            error=last_err), payload)

    # ── fallback routing ──────────────────────────────────────────────

    def chat_with_fallback(
        self,
        messages: list[dict],
        primary: str = TEXT_MODEL,
        fallback: str = VISION_MODEL,
        max_tokens: int = 512,
        temperature: float = 0.0,
        image_b64: Optional[str] = None,
        response_format: Optional[dict] = None,
    ) -> ORResponse:
        """Call primary. On error or empty content, retry on fallback.
        If a response_format json is requested and the primary returns
        unparseable JSON, that also triggers the fallback."""
        resp = self.chat(messages, model=primary, max_tokens=max_tokens,
                          temperature=temperature, image_b64=image_b64,
                          response_format=response_format)
        bad = (not resp.ok)
        if not bad and response_format and response_format.get("type") == "json_object":
            try:
                json.loads(resp.content)
            except Exception:
                bad = True
        if bad:
            fb = self.chat(messages, model=fallback, max_tokens=max_tokens,
                           temperature=temperature, image_b64=image_b64,
                           response_format=response_format)
            fb.raw["_fellback_from"] = primary
            return fb
        return resp

    # ── logging ───────────────────────────────────────────────────────

    def _log(self, resp: ORResponse, payload: dict) -> None:
        try:
            CALL_LOG.parent.mkdir(parents=True, exist_ok=True)
            row = {
                "ts": time.time(),
                "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
                "model": resp.model,
                "requested_model": payload.get("model"),
                "latency_s": round(resp.latency_s, 3),
                "prompt_tokens": resp.prompt_tokens,
                "completion_tokens": resp.completion_tokens,
                "cost_usd": round(resp.cost_usd, 6),
                "finish_reason": resp.finish_reason,
                "had_image": any(
                    isinstance(m.get("content"), list)
                    and any(b.get("type") == "image_url" for b in m["content"])
                    for m in payload.get("messages", [])
                ),
                "content_len": len(resp.content),
                "error": resp.error,
            }
            with CALL_LOG.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        except Exception:
            pass  # logging must never break the call path

    def _log_and_return(self, resp: ORResponse, payload: dict) -> ORResponse:
        self._log(resp, payload)
        return resp


if __name__ == "__main__":
    import sys
    c = OpenRouterClient()
    r = c.chat([{"role": "user", "content": "Reply with the single word READY."}],
               model=TEXT_MODEL, max_tokens=256)
    print(json.dumps({
        "ok": r.ok, "content": r.content[:80], "model": r.model,
        "latency_s": round(r.latency_s, 2), "cost_usd": r.cost_usd,
        "p_tok": r.prompt_tokens, "c_tok": r.completion_tokens,
        "error": r.error,
    }, indent=2))
    sys.exit(0 if r.ok else 1)
