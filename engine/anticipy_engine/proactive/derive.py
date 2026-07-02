"""TRUE PROACTIVITY, part 1 — derive the UNSPOKEN need (FIX-07, built 2026-07-02).

Everything before this module was reactive-in-origin: the engine only ever reminded the owner
of tasks the owner literally said, at the owner's stated time. This module is the anticipation
brain: it reads the world the engine already knows (memory, open loops, calendar, recent cards)
and DERIVES what's coming that nobody typed — the "kids need pickup at 3" moment.

Pure decision logic, no I/O: ONE smart-model call over a WorldSnapshot, then deterministic
floors that make a derived need structurally safe:
  (a) action-kind whitelist — a derived need can ONLY propose calendar_hold | reminder |
      heads_up_text. Money/send/purchase is impossible by construction; any money signal in
      the need text (harm._MONEY_SIGNAL, the canonical detector) drops the need entirely.
  (b) confidence floor 0.6 — a hunch is not a need.
  (c) max 2 needs per tick — anticipation is a whisper, not a firehose.
Dedup against open loops / recent cards / the fire-once ledger is the CALLER's job
(ControlCore.derive_tick), where _obligation_sig lives.

The derived need does NOT act from here. It is composed into a plain-English action sentence
and submitted through the ONE spine (core/proactive.py on_event: triage → harm-line → budget →
act/ask) — no new decision engine, the same floors as everything else.
"""
from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass, field
from typing import Any, List, Optional

from pydantic import BaseModel, Field, ValidationError

from ..core.gateway import CHEAP, ModelGateway
from .harm import _MONEY_SIGNAL

ALLOWED_KINDS = ("calendar_hold", "reminder", "heads_up_text")
CONFIDENCE_FLOOR = 0.6
MAX_NEEDS_PER_TICK = 2


@dataclass
class WorldSnapshot:
    """Everything the anticipation brain may read, assembled by the caller."""
    now: float
    tz_name: str = ""
    profile_facts: List[str] = field(default_factory=list)
    derived_facts: List[str] = field(default_factory=list)
    open_loops: List[dict] = field(default_factory=list)
    recent_cards: List[dict] = field(default_factory=list)
    calendar_events: List[dict] = field(default_factory=list)

    def render(self) -> str:
        """A compact, human-readable world dump for the one model pass."""
        parts: List[str] = []
        local = _time.strftime("%A %Y-%m-%d %H:%M", _time.localtime(self.now))
        parts.append(f"NOW: {local}" + (f" ({self.tz_name})" if self.tz_name else ""))
        if self.profile_facts:
            parts.append("WHO THE OWNER IS:\n- " + "\n- ".join(self.profile_facts[:20]))
        if self.derived_facts:
            parts.append("LEARNED FACTS:\n- " + "\n- ".join(self.derived_facts[:20]))
        if self.calendar_events:
            parts.append("CALENDAR (today/near):\n- " + "\n- ".join(
                str(e.get("summary") or e.get("title") or e)[:120] for e in self.calendar_events[:12]))
        if self.open_loops:
            parts.append("OPEN LOOPS (already tracked — do NOT re-derive these):\n- " + "\n- ".join(
                str(l.get("text") or l)[:120] for l in self.open_loops[:15]))
        if self.recent_cards:
            parts.append("RECENT CARDS (already surfaced — do NOT re-derive these):\n- " + "\n- ".join(
                str(c.get("title") or c.get("source_text") or c)[:120] for c in self.recent_cards[:12]))
        return "\n\n".join(parts)


class DerivedNeed(BaseModel, extra="forbid"):
    need: str
    why: str = ""
    evidence: List[str] = Field(default_factory=list)
    deadline_ts: Optional[float] = None
    research_questions: List[str] = Field(default_factory=list)
    action_kind: str = "heads_up_text"
    action_args: dict = Field(default_factory=dict)
    confidence: float = 0.0


_PROMPT = """You are the anticipation brain of a proactive assistant ("Donna from Suits").
Below is everything currently known about the owner's world. Your ONE job: derive at most
{max_needs} UNSPOKEN needs — things that are coming that nobody has asked for, that a sharp
human assistant would quietly get ahead of. NOT a restatement of an open loop or recent card
(those are already handled). NOT a guess dressed as a fact: every need must cite the specific
known facts it is derived from, in "evidence".

A good derived need names: what's coming, why it follows from the evidence, the real-world
questions to research first (each phrased as a task a browser assistant could do, e.g.
"Using a maps site in the browser, find the driving time from the office to Lakeview
Elementary leaving at 2:40pm"), and ONE safe proposed action:
- "calendar_hold"  args: {{"title": ..., "start_local": "HH:MM", "duration_min": N}}
- "reminder"       args: {{"text": ..., "when_local": "HH:MM"}}
- "heads_up_text"  args: {{"text": ...}}
NEVER propose sending anything to another person, buying anything, or anything involving
money — those are not yours to derive. If nothing genuinely warrants anticipation, return
an empty list: a quiet day is a correct answer.

Reply as JSON only:
{{"needs": [{{"need": "...", "why": "...", "evidence": ["..."], "deadline_ts": null,
"research_questions": ["..."], "action_kind": "calendar_hold|reminder|heads_up_text",
"action_args": {{}}, "confidence": 0.0}}]}}

THE WORLD:
{world}
"""


async def derive_needs(gateway: ModelGateway, snapshot: WorldSnapshot) -> List[DerivedNeed]:
    """ONE model pass over the world -> a floored, whitelisted list of derived needs.

    Fail-closed: any transport/parse problem returns [] (a quiet tick, never a crash,
    never a fabricated need)."""
    try:
        raw = await gateway.think(
            _PROMPT.format(max_needs=MAX_NEEDS_PER_TICK, world=snapshot.render()),
            tier=CHEAP, caller="derive", json_mode=True, temperature=0,
        )
    except Exception:
        return []
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        data: Any = json.loads(raw[start:end + 1]) if start >= 0 <= end else {}
    except Exception:
        return []
    out: List[DerivedNeed] = []
    for item in (data.get("needs") or [])[: MAX_NEEDS_PER_TICK * 2]:
        try:
            need = DerivedNeed(**{k: item.get(k) for k in DerivedNeed.model_fields if k in item})
        except (ValidationError, TypeError):
            continue
        # Floor (a): kind whitelist + money impossibility (the canonical detector).
        if need.action_kind not in ALLOWED_KINDS:
            continue
        blob = " ".join([need.need, need.why, json.dumps(need.action_args)])
        if _MONEY_SIGNAL.search(blob):
            continue
        # Floor (b): confidence.
        if float(need.confidence or 0.0) < CONFIDENCE_FLOOR:
            continue
        if not (need.need or "").strip():
            continue
        out.append(need)
        if len(out) >= MAX_NEEDS_PER_TICK:
            break
    return out
