"""Owner Action Engine intake.

This is the shared front door for the owner operating path: typed transcript,
MP3 transcript, live listening, and pay-to-try all become the same ugly stream of
observed lines. The job here is not to obey clean commands. It is to pull the
small number of actionable needles out of normal daily speech, create durable
task cards, and leave the rest as memory/noise.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from .core.envelopes import new_id

OwnerSource = Literal["pay_to_try", "start_listening", "mp3", "transcript", "typed", "app", "mac_mic", "pendant_phone"]
OwnerDisposition = Literal["do", "ask", "remember", "blocked"]
OwnerRoute = Literal["api", "browser", "voice_text", "memory"]


class OwnerObservedLine(BaseModel):
    line_no: int
    text: str


class OwnerTaskCard(BaseModel):
    id: str = Field(default_factory=new_id)
    source: str
    line_no: int
    source_text: str
    title: str
    disposition: OwnerDisposition
    route: OwnerRoute
    action: str
    args: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.75
    reason: str = ""
    status: str = "open"
    proof: list[dict[str, Any]] = Field(default_factory=list)


class OwnerIngestResult(BaseModel):
    source: str
    observed_lines: list[OwnerObservedLine]
    cards: list[OwnerTaskCard]
    ignored_line_count: int


_TIMEISH = re.compile(
    r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"this afternoon|this morning|this evening|next week|before \w+|by \w+|"
    r"at\s+\d{1,2}(:\d\d)?\s*(am|pm)?|\d{1,2}(:\d\d)?\s*(am|pm))\b",
    re.I,
)
_PICKUP = re.compile(r"\b(pick\s*up|pickup|drop\s*off|school|kids?|children|child|daycare)\b", re.I)
_REMEMBER = re.compile(
    r"\b(remind me|don't let me forget|dont let me forget|remember to|make sure i|make sure to|"
    r"i need to|need to|gotta|i have to|i should|i told .* i'?d)\b",
    re.I,
)
# C22: routing tokens must stay generic verbs/nouns — never vocabulary tuned to the
# persona bank or the directive's sample transcript (pre-games Stage B scoring).
_SEND = re.compile(r"\b(send|email|text|tell|reply|follow up|circle back|draft)\b", re.I)
_BROWSER = re.compile(r"\b(grab|buy|order|purchase|checkout|cart|find|look up|research)\b", re.I)
_MONEY = re.compile(r"\b(pay|buy|order|purchase|checkout|wire|venmo|zelle|cashapp|credit card|payment)\b", re.I)
_NO_BUY = re.compile(r"\b(don'?t buy|do not buy|don'?t checkout|do not checkout|cart only|just.*cart)\b", re.I)
_PROFILE = re.compile(
    r"\b(my name is|i am a|i'm a|i work at|i work as|i live in|i prefer|i like|i hate|"
    r"my wife|my husband|my partner|my kid|my daughter|my son|my boss|my contractor)\b",
    re.I,
)
_VENT_OR_JOKE = re.compile(
    r"\b(kill me|this is stupid|whatever|ugh|i swear|i hate this|"
    r"can'?t believe|sarcasm|lol|haha)\b",
    re.I,
)
_FILLER = {
    "yeah",
    "yep",
    "ok",
    "okay",
    "uh",
    "um",
    "mhm",
    "right",
    "cool",
    "sure",
    "anyway",
    "whatever",
    "fine",
}


def _clean_line(raw: str) -> str:
    text = raw.strip()
    text = re.sub(r"^\[?\d{1,2}:\d\d(:\d\d)?\]?\s*", "", text)
    text = re.sub(r"^[A-Z][A-Za-z0-9 _-]{0,24}:\s+", "", text)
    return re.sub(r"\s+", " ", text).strip(" -\t")


def _split_transcript(text: str) -> list[OwnerObservedLine]:
    raw_parts: list[str] = []
    for raw_line in (text or "").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        if len(raw_line) > 220:
            raw_parts.extend(p for p in re.split(r"(?<=[.!?])\s+", raw_line) if p.strip())
        else:
            raw_parts.append(raw_line)
    if not raw_parts and text.strip():
        raw_parts = [p for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]
    observed: list[OwnerObservedLine] = []
    for i, raw in enumerate(raw_parts, start=1):
        cleaned = _clean_line(raw)
        if cleaned:
            observed.append(OwnerObservedLine(line_no=i, text=cleaned))
    return observed


def _is_filler(text: str) -> bool:
    words = [w.strip(".,!?;:'\"").lower() for w in text.split()]
    return len(words) <= 5 and all(w in _FILLER or not w for w in words)


def _person_hint(text: str) -> str | None:
    m = re.search(r"\b(?:send|email|text|tell|reply to|follow up with)\s+([A-Z][a-z]+)\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b([A-Z][a-z]+)\s+(?:needs|asked|is waiting|wanted)\b", text)
    return m.group(1) if m else None


class OwnerMode:
    """Deterministic first pass for messy owner transcript -> task cards."""

    def ingest(self, text: str, source: str = "transcript", meta: dict[str, Any] | None = None) -> OwnerIngestResult:
        del meta  # reserved for clock/device context; kept out of rules for determinism.
        observed = _split_transcript(text)
        cards: list[OwnerTaskCard] = []
        ignored = 0
        for line in observed:
            card = self._card_for_line(line, source)
            if card is None:
                ignored += 1
            else:
                cards.append(card)
        return OwnerIngestResult(source=source, observed_lines=observed, cards=cards, ignored_line_count=ignored)

    def _card_for_line(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard | None:
        text = line.text
        lowered = text.lower()
        if _is_filler(text):
            return None

        if _PROFILE.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title=f"Remember: {text}",
                disposition="remember",
                route="memory",
                action="write_profile_memory",
                args={"memory_text": text},
                confidence=0.82,
                reason="stated preference, identity, or relationship fact",
            )

        if _PICKUP.search(text) and (_TIMEISH.search(text) or _REMEMBER.search(text)):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Protect pickup or drop-off timing",
                disposition="do",
                route="api",
                action="create_calendar_or_reminder",
                args={"task_text": text, "kind": "pickup_or_dropoff"},
                confidence=0.86,
                reason="care obligation plus time/reminder signal",
            )

        person = _person_hint(text)
        if person and _SEND.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title=f"Prepare message for {person}",
                disposition="ask",
                route="voice_text",
                action="draft_or_confirm_message",
                args={"person": person, "task_text": text},
                confidence=0.81,
                reason="third-party communication should be confirmed before sending",
            )

        if _BROWSER.search(text):
            if _NO_BUY.search(text):
                disposition: OwnerDisposition = "do"
                action = "find_or_cart_without_purchase"
                reason = "shopping/research request explicitly blocks purchase"
            elif _MONEY.search(text):
                disposition = "blocked"
                action = "prepare_purchase_path_without_payment"
                reason = "money or checkout is a hard stop; prepare but do not pay"
            else:
                disposition = "do"
                action = "research_or_find_item"
                reason = "browser-resolvable life-admin task"
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Resolve browser task",
                disposition=disposition,
                route="browser",
                action=action,
                args={"task_text": text, "payment_allowed": False},
                confidence=0.76,
                reason=reason,
            )

        if _REMEMBER.search(text) and not _VENT_OR_JOKE.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Capture reminder or open loop",
                disposition="do",
                route="api",
                action="create_reminder_or_open_loop",
                args={"task_text": text},
                confidence=0.73,
                reason="explicit remember/commitment signal",
            )

        if "?" in text and ("can you" in lowered or "could you" in lowered) and not _VENT_OR_JOKE.search(text):
            return OwnerTaskCard(
                source=source,
                line_no=line.line_no,
                source_text=text,
                title="Clarify possible request",
                disposition="ask",
                route="voice_text",
                action="ask_clarifying_question",
                args={"task_text": text},
                confidence=0.58,
                reason="possible request but not enough structure to act",
            )

        return None
