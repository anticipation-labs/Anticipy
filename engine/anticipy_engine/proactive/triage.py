"""Room 1 — the triage gate (the bouncer; cheap, first, the cost spine).

Drops the bulk of ambient events that aren't actionable BEFORE any smart model runs.
Tuned for HIGH RECALL: a dropped real event is unrecoverable; a passed junk event is
killed cheaply at the harm-line — so when unsure, PASS. Deterministic by default (zero
model calls, CI-safe + free); a cheap-model tiebreak for genuinely ambiguous events is
behind the flag and NEVER fires in stub. General signals only (no site/test-specific
branches). Recipe + sources: notes/proactive_room1.md.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

# Actionable VERBS / task intents — general task language, matched on word boundaries.
_ACTION: Tuple[str, ...] = (
    "send", "book", "schedule", "reschedule", "email", "remind", "call", "text",
    "set up", "draft", "meet", "reply", "wire", "pay", "transfer", "buy", "order",
    "cancel", "delete", "move", "follow up", "forward", "share", "invite", "rsvp",
    "reserve", "sign up", "subscribe", "renew", "submit", "post", "message", "ping",
    "book a", "look up", "research", "compare", "confirm", "register", "purchase",
)
# Commitment / request / imperative patterns — intent even without a listed verb.
_INTENT: Tuple[str, ...] = (
    r"\bi'?ll\b", r"\bi will\b", r"\bi need to\b", r"\bi have to\b", r"\bi should\b",
    r"\bi want to\b", r"\bi'?m going to\b", r"\bremind me\b", r"\bdon'?t forget\b",
    r"\bmake sure\b", r"\bcan you\b", r"\bcould you\b", r"\bwould you\b", r"\blet'?s\b",
    r"\bwe need to\b", r"\bgotta\b", r"\bneed to\b", r"\bhave to\b",
    r"\bby (mon|tue|wed|thu|fri|sat|sun|tomorrow|tonight|next|end of|noon|eod)",
    r"\bdue\b", r"\bdeadline\b", r"\boverdue\b",   # deadlines imply a task (general signal)
)
# Pure-noise: fillers / greetings / acks. Exact-match (whole utterance) -> drop.
_FILLER = {
    "um", "uh", "ok", "okay", "thanks", "thank you", "hey", "hi", "hello", "yeah",
    "yep", "nope", "no", "cool", "nice", "lol", "hmm", "right", "sure", "yo", "sup",
    "mm", "mhm", "ok thanks", "okay thanks", "thanks!", "got it", "sounds good",
}


@dataclass
class TriageConfig:
    action_cues: Tuple[str, ...] = _ACTION
    intent_patterns: Tuple[str, ...] = _INTENT
    min_tokens: int = 2          # 0/1-token utterances are noise


class Triage:
    """The bouncer. `actionable(text)` decides survive-vs-drop with NO smart model in stub."""

    def __init__(self, gateway=None, config: Optional[TriageConfig] = None, mode: Optional[str] = None) -> None:
        self.gateway = gateway
        self.cfg = config or TriageConfig()
        self.mode = mode or os.environ.get("ANTICIPY_MEMORY_MODE", "stub")
        self._intent_re = [re.compile(p) for p in self.cfg.intent_patterns]
        self._action_re = [re.compile(r"\b" + re.escape(c) + r"\b") for c in self.cfg.action_cues]
        self.smart_calls = 0

    def _positive(self, t: str) -> bool:
        return any(r.search(t) for r in self._action_re) or any(r.search(t) for r in self._intent_re)

    def actionable(self, text: str) -> bool:
        """True -> survives to the harm-line; False -> dropped (no smart model touched in stub)."""
        t = (text or "").strip().lower().rstrip(".!?")
        if not t or t in _FILLER:
            return False
        if len(re.findall(r"[a-z0-9']+", t)) < self.cfg.min_tokens:
            return False
        if self._positive(t):
            return True
        # ambiguous: no positive signal, not obvious filler. Stub -> drop (deterministic, free).
        # Live -> a cheap-model tiebreak MAY rescue it (bias: pass when in doubt). Never in CI.
        if self.mode == "live" and self.gateway is not None:
            return self._tiebreak(text)
        return False

    def _tiebreak(self, text: str) -> bool:  # pragma: no cover (live-only; never in the free suite)
        try:
            from ..core.gateway import CHEAP
            import asyncio
            prompt = ("Is the user's utterance an actionable task/request/commitment (something an "
                      "assistant could act on), vs ambient chatter/observation? Answer yes or no only.\n"
                      f"Utterance: {text}")
            raw = (asyncio.get_event_loop().run_until_complete(
                self.gateway.think(prompt, tier=CHEAP, caller="triage")) or "").lower()
            self.smart_calls += 1
            return "yes" in raw and "no" not in raw.split()  # bias handled by the harm-line downstream
        except Exception:
            return True  # fail OPEN (high recall): on any tiebreak error, pass it down
