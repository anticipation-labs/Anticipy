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

from ..shared.note_task import match_note_task
from ..shared.schedule_change import match_schedule_change_hold

CHEAP = "cheap"
SMART = "smart"
COST = {CHEAP: 0.0005, SMART: 0.02}

PROVIDER_STUB = "stub"
PROVIDER_OPENROUTER = "openrouter"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# 429 retry-hint honoring (ledger F7 residual). The live brain is Gemini free tier,
# whose 429s state the server's own wait: google.rpc.RetryInfo retryDelay in the error
# body (a proto3 Duration string like "21s" / "15.002899939s"; the OpenAI-compat
# endpoint sometimes wraps the error in a one-element array, and sometimes the only
# surviving signal is a "Please retry in Ns" phrase in the message). OpenRouter
# documents a Retry-After delta-seconds header. A hint at or under the cap is honored
# inline (plus a small margin so an exact-boundary retry doesn't re-hit the window);
# a longer hint means the quota window outlasts the request path — return the empty
# non-read immediately so the caller's UNAVAILABLE -> defer path owns the wait,
# instead of burning more blind retries that count against the same quota.
RETRY_HINT_INLINE_CAP_S = 8.0
RETRY_HINT_MARGIN_S = 0.25
_RETRY_IN_MSG_RE = re.compile(r"retry in\s+([0-9]+(?:\.[0-9]+)?)\s*s", re.IGNORECASE)


def _retry_hint_seconds(resp) -> Optional[float]:
    """The server-stated wait (seconds) before retrying a 429, or None if it gave none.

    Sources, most authoritative first: the Retry-After header (delta-seconds only;
    the rare HTTP-date form is treated as no hint), RetryInfo retryDelay in the error
    body (string Duration, with a defensive {seconds, nanos} object fallback), then a
    "retry in Ns" phrase in the error message. Never raises — a malformed hint is
    just no hint, and the caller keeps its blind backoff.
    """
    try:
        ra = (resp.headers.get("retry-after") or "").strip()
        if ra:
            try:
                return max(0.0, float(ra))
            except ValueError:
                pass
        data = resp.json()
        if isinstance(data, list):  # Gemini OpenAI-compat: [{"error": {...}}]
            data = next((d for d in data if isinstance(d, dict)), {})
        err = data.get("error") if isinstance(data, dict) else None
        if not isinstance(err, dict):
            return None
        for detail in err.get("details") or []:
            if not isinstance(detail, dict) or \
                    not str(detail.get("@type", "")).endswith("RetryInfo"):
                continue
            delay = detail.get("retryDelay")
            if isinstance(delay, str) and delay.strip().endswith("s"):
                try:
                    return max(0.0, float(delay.strip()[:-1]))
                except ValueError:
                    pass
            if isinstance(delay, dict):
                try:
                    return max(0.0, float(delay.get("seconds", 0))
                               + float(delay.get("nanos", 0)) / 1e9)
                except (TypeError, ValueError):
                    pass
        m = _RETRY_IN_MSG_RE.search(str(err.get("message", "")))
        if m:
            return max(0.0, float(m.group(1)))
    except Exception:
        return None
    return None


class ModelGateway:
    # gate + plan (proactive brain) and agent (the web-agent loop) may use smart
    SMART_CALLERS = frozenset({"gate", "plan", "agent"})

    def __init__(self, provider: Optional[str] = None, endpoint: Optional[str] = None,
                 stub=None, timeout: float = 60.0,
                 cheap_model: Optional[str] = None, smart_model: Optional[str] = None,
                 transport=None) -> None:
        self.provider = provider or os.environ.get("ANTICIPY_MODEL_PROVIDER", PROVIDER_STUB)
        self.endpoint = endpoint  # optional custom OpenAI-compatible endpoint
        self.timeout = timeout
        self.cheap_model = cheap_model or os.environ.get("ANTICIPY_MODEL_CHEAP", "openai/gpt-4o-mini")
        self.smart_model = smart_model or os.environ.get("ANTICIPY_MODEL_SMART", "openai/gpt-4o")
        self.calls: List[dict] = []
        self._stub = stub or default_stub
        # The "openrouter" path speaks plain OpenAI chat-completions. Any compatible
        # provider (Gemini, Groq, Cerebras, ...) can serve it via these overrides —
        # this is how the engine survives an unfunded OpenRouter account.
        self._url = os.environ.get("ANTICIPY_OPENAI_BASE_URL", OPENROUTER_URL)
        self._key = (os.environ.get("ANTICIPY_MODEL_API_KEY")
                     or os.environ.get("OPENROUTER_API_KEY"))
        self._transport = transport  # test injection (httpx.MockTransport); None in prod

    async def think(self, task: str, tier: str, caller: str, image: Optional[str] = None,
                    json_mode: bool = False, temperature: Optional[float] = None,
                    max_tokens: Optional[int] = None) -> str:
        if tier == SMART and caller not in self.SMART_CALLERS:
            raise PermissionError(f"smart tier not allowed from caller '{caller}'")
        self.calls.append({"tier": tier, "caller": caller, "cost": COST.get(tier, 0.0)})

        if self.provider == PROVIDER_OPENROUTER:
            return await self._openrouter(task, tier, image, json_mode, temperature, max_tokens)
        if self.endpoint:
            return await self._custom_endpoint(task, tier)
        return self._stub(task, tier, caller)

    @property
    def smart_calls(self) -> List[dict]:
        return [c for c in self.calls if c["tier"] == SMART]

    def total_cost(self) -> float:
        return round(sum(c["cost"] for c in self.calls), 6)

    # ---- real provider: OpenRouter (OpenAI-compatible, vision-capable) ----
    async def _openrouter(self, task: str, tier: str, image: Optional[str], json_mode: bool = False,
                          temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> str:
        if not self._key:
            raise RuntimeError("no model API key: set ANTICIPY_MODEL_API_KEY (or OPENROUTER_API_KEY)")
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
        body = {"model": model, "messages": [{"role": "user", "content": content}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}  # force a parseable JSON object
        if temperature is not None:
            body["temperature"] = temperature  # low temp for stable, run-to-run decisions
        token_cap = max_tokens or os.environ.get("ANTICIPY_MODEL_MAX_TOKENS")
        if token_cap:
            body["max_tokens"] = int(token_cap)

        # Retry transient empties / 429 / 5xx — the provider intermittently returns
        # empty content under load, which would otherwise read as a spurious failure.
        # On 429 the server's own retry hint is honored (see _retry_hint_seconds):
        # short hints sleep inline, long hints fail fast into the caller's
        # UNAVAILABLE -> defer path (ledger F7) instead of hammering a closed window.
        last = ""
        for attempt in range(4):
            try:
                async with httpx.AsyncClient(timeout=self.timeout,
                                             transport=self._transport) as client:
                    resp = await client.post(self._url, headers=headers, json=body)
                if resp.status_code == 429:
                    hint = _retry_hint_seconds(resp)
                    if hint is not None:
                        self.calls[-1]["retry_hint_s"] = hint  # visible in postmortems
                        if hint > RETRY_HINT_INLINE_CAP_S:
                            return ""  # window outlasts us -> the defer path owns the wait
                        await asyncio.sleep(hint + RETRY_HINT_MARGIN_S)
                        continue
                    await asyncio.sleep(1.5 * (attempt + 1))  # no guidance -> blind backoff
                    continue
                if resp.status_code in (500, 502, 503, 504):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                resp.raise_for_status()
                content_out = (resp.json()["choices"][0].get("message") or {}).get("content")
                if content_out:
                    return content_out
                last = content_out or ""
                await asyncio.sleep(1.0 * (attempt + 1))  # empty -> brief backoff, retry
            except (httpx.TransportError, httpx.HTTPStatusError):
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
# "post" must be the WORD post (post/posts/posted/posting), not a hyphenated
# compound ("post-shift dinner") or a prefix ("postpone"): the bare substring
# planned a junk post_to_x step that parked otherwise-complete goals at
# needs_human. This stub is also the planner for keyless default boots.
_POST_WORD_RE = re.compile(r"\bpost(?:ed|ing|s)?\b(?!-)")
# A SELF-reminder line's honest plan IS the open-loop write: the drawer grounds
# remind_ts from the spoken time and Room 3 re-gates the embedded action when the
# reminder fires. No side steps may ride a reminder (the F24 junk-step family — a
# "remind me ... to send X" line must hold, not send now), and the loop text is the
# GOAL line itself, never the whole plan prompt (no prompt dumping).
_SELF_REMINDER_RE = re.compile(r"\b(?:remind me|set (?:a |an )?reminder|reminder to|don'?t forget)\b", re.I)
_FORGET_HOLD_RE = re.compile(
    r"\b(?:before|so)\s+(?:i|we)\s+(?:don'?t\s+)?forget\b",
    re.I,
)
_FORGET_HOLD_TIME_RE = re.compile(
    r"\b(?:today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"noon|midnight|morning|afternoon|evening|night|"
    r"in \d+ (?:minutes?|hours?|days?))\b"
    r"|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b",
    re.I,
)
_GOAL_LINE_RE = re.compile(r"\bGOAL: (?P<goal>[^\n]+)")
# Grounded calendar shapes (decided act upstream by the harm-line's calendar_hold /
# slot-choice rules): the honest plan is ONE create_event whose args come from the
# SPOKEN line — never the canned Lunch-with-Sarah placeholders (LESSONS 2026-06-07:
# a real artifact is still fake if it is semantically wrong) and never a junk
# browse step planted by a bare keyword ("on site" -> browse_task parked the
# cabinet-delivery block on a screenshot instead of a calendar block; ledger F27).
# At the LIVE tier the real planner grounds ISO datetimes itself and ApiHand keeps
# refusing ungrounded calendar writes; this branch is the stub/keyless tier only.
_OWNER_TASK_PREFIX_RE = re.compile(r"^\s*owner task:\s*", re.I)
_TIME_TOKEN = r"(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)"
_BLOCK_RANGE_RE = re.compile(
    r"\bblock\b[^.;!?]{0,40}?(?P<window>(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day\s+)?"
    + _TIME_TOKEN + r"\s*(?:to|until|till|through|-|–)\s*" + _TIME_TOKEN + r")\b",
    re.I,
)
_BLOCK_PURPOSE_RE = re.compile(
    r"\bfor\s+(?:the\s+|a\s+|an\s+)?(?P<purpose>[^.;!?,]{3,60}?)"
    r"(?=\s+(?:so|because|since|before|after)\b|[.;!?,]|$)",
    re.I,
)


def _grounded_calendar_step(goal_line: str) -> Optional[dict]:
    from ..shared.slotbooking import appointment_title, match_slot_choice_booking

    line = _OWNER_TASK_PREFIX_RE.sub("", goal_line or "").strip()
    slot = match_slot_choice_booking(line)
    if slot:
        title = appointment_title(line) or line[:80]
        return {"intent": "create_event", "args": {"title": title, "when": slot}, "risk": "low"}
    hold = match_schedule_change_hold(line)
    if hold:
        return {"intent": "create_event", "args": {"title": hold.title, "when": hold.when}, "risk": "low"}
    m = _BLOCK_RANGE_RE.search(line)
    if m:
        window = re.sub(r"\s+", " ", m.group("window")).strip()
        pm = _BLOCK_PURPOSE_RE.search(line, m.end())
        title = re.sub(r"\s+", " ", pm.group("purpose")).strip() if pm else line[:80]
        return {"intent": "create_event", "args": {"title": title, "when": window}, "risk": "low"}
    return None


def default_stub(task: str, tier: str, caller: str) -> str:
    t = task.lower()
    if caller == "gate":
        risky = any(k in t for k in ("wire money", "delete", "pay ", "transfer"))
        actionable = any(k in t for k in ("send", "book", "schedule", "email", "remind", "call", "set up"))
        decision = "ask_first" if risky else ("do_and_notify" if actionable else "ignore")
        return json.dumps({"decision": decision, "reason": f"stub gate read of: {task[:80]}"})

    if caller == "plan":
        goal_m = _GOAL_LINE_RE.search(task)
        goal_line = (goal_m.group("goal") if goal_m else task).strip()
        if _SELF_REMINDER_RE.search(task):
            return json.dumps({"steps": [{"intent": "write_memory",
                                          "args": {"kind": "open_loop", "text": goal_line},
                                          "risk": "low"}]})
        if _FORGET_HOLD_RE.search(goal_line) and _FORGET_HOLD_TIME_RE.search(goal_line):
            return json.dumps({"steps": [{"intent": "write_memory",
                                          "args": {"kind": "open_loop", "text": goal_line},
                                          "risk": "low"}]})
        if match_note_task(goal_line) is not None:
            return json.dumps({"steps": [{"intent": "write_memory",
                                          "args": {"kind": "open_loop", "text": goal_line},
                                          "risk": "low"}]})
        # grounded calendar shapes plan EXACTLY the one event — no keyword steps ride
        grounded = _grounded_calendar_step(goal_line)
        if grounded is not None:
            return json.dumps({"steps": [grounded]})
        steps = []
        # an explicit draft request plans the DRAFT (Gmail.WriteDraftEmail — never
        # sends); only undrafted email/send requests plan the gated send
        if "draft" in t:
            steps.append({"intent": "send_email_draft",
                          "args": {"to": "Sarah", "subject": "Q3 deck", "body": "Attached."},
                          "risk": "low"})
        elif any(k in t for k in ("email", "send", "deck")):
            steps.append({"intent": "send_email",
                          "args": {"to": "Sarah", "subject": "Q3 deck", "body": "Attached."},
                          "risk": "needs_confirm"})
        # "set up" is already a gate-trigger word; a time-anchored "set up X" is a
        # calendar write (it used to reach create_event only via memory-noise steps)
        if any(k in t for k in ("lunch", "book", "calendar", "meet", "schedule", "set up")):
            steps.append({"intent": "create_event",
                          "args": {"title": "Lunch with Sarah", "when": "Friday 12:00"}, "risk": "low"})
        if any(k in t for k in ("remind", "friday", "follow", "later")):
            steps.append({"intent": "write_memory",
                          "args": {"kind": "open_loop", "text": "Send Sarah the Q3 deck Friday"}, "risk": "low"})
        if _POST_WORD_RE.search(t) or any(k in t for k in ("tweet", "launch", " x ", " x.", "on x")):
            steps.append({"intent": "post_to_x", "args": {"text": "We just launched. "}, "risk": "low"})
        if any(k in t for k in ("browse", "open ", "website", "site", "check the")):
            steps.append({"intent": "browse_task", "args": {"task": "open the page"}, "risk": "low"})
        if not steps:
            steps.append({"intent": "browse_task", "args": {"task": task}, "risk": "low"})
        return json.dumps({"steps": steps})

    return f"[stub:{tier}:{caller}] {task[:120]}"
