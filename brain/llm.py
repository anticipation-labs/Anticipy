"""LLM client for Anticipy's brain.

Uses OpenRouter (OpenAI-compatible) when OPENROUTER_API_KEY is set.
Falls back to a deterministic heuristic engine when no key is present, so the
whole pipeline is provable end-to-end without secrets. The real key only
swaps the reasoning core; the plumbing is identical.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Cheap, fast triage model per the product spec (Omar picked these).
DEFAULT_MODEL = os.environ.get("ANTICIPY_MODEL", "deepseek/deepseek-v3.2")

# The FALLBACK timezone. Per-owner now, because this used to be the only one.
#
# It was a server-wide constant, so every prompt was grounded in Vancouver's
# time of day no matter who was speaking. With one user that is invisible; the
# second person to onboard, from anywhere else, would be told the wrong hour
# and have her quiet hours land in the middle of their afternoon.
TZ = ZoneInfo(os.environ.get("ANTICIPY_TZ", "America/Vancouver"))


def owner_tz(name: Optional[str] = None) -> ZoneInfo:
    """The owner's own zone, falling back to the server default.

    Never raises: a junk or unknown identifier from an old or odd client must
    not stop her thinking, it just means she uses the fallback.
    """
    if name and isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except Exception:
            pass
    return TZ


def where_line(tz_name: Optional[str] = None) -> str:
    """Where the owner is, in one sentence — or nothing at all.

    now_line() has always carried the TIME and never the PLACE, which is how
    "book dinner" became a reservation in Seattle for somebody who lives in
    Vancouver. An IANA identifier already holds the city, so this costs the
    user no permission prompt and no typing.

    Returns "" when the zone is unknown, so a prompt gains a sentence only when
    there is something true to put in it.
    """
    raw = (tz_name or "").strip()
    if not raw or "/" not in raw:
        return ""
    city = raw.rsplit("/", 1)[-1].replace("_", " ").strip()
    if not city:
        return ""
    return (f"They are in {city} — anything local (a restaurant, a shop, a "
            f"clinic) means {city} unless they say otherwise.")


def now_line(tz_name: Optional[str] = None) -> str:
    """The one sentence that stops date hallucination. A model with no clock
    guessed 'this coming Sunday, July 28th' — a date in the PAST — in a live
    scheduling thread. Humans know what day it is; so does every prompt.

    Takes the owner's zone when known. Called with nothing, it behaves exactly
    as it did before.
    """
    return datetime.now(owner_tz(tz_name)).strftime(
        "Right now it is %A, %B %-d, %Y, %-I:%M %p %Z.")


@dataclass
class LLMResult:
    text: str
    used_model: str
    mode: str  # "openrouter" or "heuristic"


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 owner_zone: Optional[str] = None):
        # The owner's IANA zone, e.g. "America/Vancouver". None means fall back
        # to the server default and say nothing about place — exactly the
        # behaviour that existed before this was per-owner.
        self.owner_zone = owner_zone
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model = model

    @property
    def live(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, temperature: float = 0.1) -> LLMResult:
        # Grounded at the client so EVERY caller — triage, replies, voice,
        # briefings, the clock — knows the current local date and time, and
        # WHERE the owner is. One place to set it means no caller can forget.
        #
        # `owner_zone` is set from the owner's own profile, reported by their
        # phone. Unset, this behaves exactly as it did before: the server
        # default zone and no place sentence at all.
        where = where_line(self.owner_zone)
        system = f"{now_line(self.owner_zone)}\n\n{system}"
        if where:
            system = f"{where}\n{system}"
        if self.live:
            return self._openrouter(system, user, temperature)
        return LLMResult(text=self._heuristic(system, user), used_model="heuristic", mode="heuristic")

    def _openrouter(self, system: str, user: str, temperature: float) -> LLMResult:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=60) as c:
            r = c.post(OPENROUTER_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        return LLMResult(text=data["choices"][0]["message"]["content"], used_model=self.model, mode="openrouter")

    # ---- deterministic fallback so we can prove the pipeline with no key ----
    def _heuristic(self, system: str, user: str) -> str:
        """A tiny rules engine that mimics the JSON the real model returns for triage."""
        text = user.lower()
        # commitments / promises -> ACT
        act_patterns = [
            (r"(send|share) (you |him |her |them |it )?(the |over the |with them )?(deck|pitch|contract|portfolio|file|proposal|link|document)", "draft_and_send_document"),
            (r"(grab|get|book|reserve) .*(dinner|lunch|table|reservation|restaurant)", "find_and_book_restaurant"),
            (r"(schedule|set up|book|put).*(meeting|call|time|thursday|monday|tomorrow|calendar)", "create_calendar_event"),
            (r"(remind me|i should|need to) (to )?(email|message|text|call|follow up)", "create_reminder_or_draft"),
            (r"(cancel|unsubscribe).*(gym|subscription|membership|plan)", "start_cancellation_flow"),
            (r"(reorder|order more|out of|running low)", "reorder_item"),
            (r"(check|find|look up|compare) .*(pric|flight|hotel|availabilit|cost)", "research_and_report"),
            (r"(reschedule|move|change) .*(appointment|clinic|doctor)", "reschedule_appointment"),
            (r"running (late|behind)|tell them i", "notify_contact"),
        ]
        for pat, goal in act_patterns:
            if re.search(pat, text):
                return json.dumps({"decision": "act", "goal": goal, "reason": f"matched intent: {goal}"})
        # questions to the user / ambiguity -> ASK
        if re.search(r"\b(should i|do you think|not sure|maybe we|what about)\b", text):
            return json.dumps({"decision": "ask", "goal": None, "reason": "ambiguous intent, confirm first"})
        # small talk / jokes -> IGNORE
        return json.dumps({"decision": "ignore", "goal": None, "reason": "no actionable commitment detected"})
