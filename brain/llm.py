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
from typing import Optional

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Cheap, fast triage model per the product spec (Omar picked these).
DEFAULT_MODEL = os.environ.get("ANTICIPY_MODEL", "deepseek/deepseek-v3.2")


@dataclass
class LLMResult:
    text: str
    used_model: str
    mode: str  # "openrouter" or "heuristic"


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model = model

    @property
    def live(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str, temperature: float = 0.1) -> LLMResult:
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
