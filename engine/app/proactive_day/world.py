"""The simulated wearer life. Deterministic, in-process, seeded.
Nothing real is sent: the phone/SMS/call/email sink RECORDS every
outbound attempt (channel, ts, content) and delivers nothing.

This is the world the resolution/timing/completion layers read and
the comms layer writes to. It is NOT the frozen reasoning engine's
memory; it is the wearer's life state for the simulated day.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Outbound:
    ts: float
    channel: str          # silent_queue | text | email | call | call2
    to: str
    body: str
    pending_ids: list = field(default_factory=list)  # items this batch covers


@dataclass
class SimWorld:
    """A populated life. Everything is local and recorded."""
    now_s: float = 0.0
    contacts: dict = field(default_factory=dict)        # name -> {email,phone}
    calendar: list = field(default_factory=list)        # [{title,start,end}]
    files: dict = field(default_factory=dict)           # label -> path/desc
    inbox: list = field(default_factory=list)           # received mail
    sent_mail: list = field(default_factory=list)       # mail the world shows sent
    conversation: list = field(default_factory=list)    # day memory: [{ts,speaker,text,place}]
    facts: dict = field(default_factory=dict)           # learned shorthand etc.
    outbound: list = field(default_factory=list)        # the recording sink
    world_actions: list = field(default_factory=list)   # things done by other means

    # --- clock ---
    def tick(self, to_s: float) -> None:
        self.now_s = max(self.now_s, float(to_s))

    # --- conversation memory (the day accumulates) ---
    def hear(self, speaker: str, text: str, place: str = "home") -> None:
        self.conversation.append({"ts": self.now_s, "speaker": speaker,
                                  "text": text, "place": place})

    def recent(self, n: int = 12) -> list:
        return self.conversation[-n:]

    # --- the world doing things by OTHER means (completion/double-act) ---
    def world_did(self, kind: str, detail: dict) -> None:
        """The wearer sent it from their phone, or it got done another
        way. Completion detection must notice this and kill the
        pending action so the system never double-acts.
        """
        rec = {"ts": self.now_s, "kind": kind, **detail}
        self.world_actions.append(rec)
        if kind == "email_sent":
            self.sent_mail.append(rec)
        elif kind == "calendar_changed":
            self.calendar.append(detail)

    def already_satisfied(self, action: dict) -> bool:
        """True if the world already shows this action's outcome by any
        means (so the pending action must be killed: zero double-act).
        """
        a = (action or {})
        kind = a.get("kind")
        tgt = str(a.get("target", "")).lower()
        obj = str(a.get("object", "")).lower()
        for w in self.world_actions:
            if kind == "send_email" and w["kind"] == "email_sent":
                # SAME task only if BOTH recipient and subject
                # correspond. A shared recipient alone (an unrelated
                # promise to the same person) or a shared topic alone
                # (a different promise about the same file) is a
                # DIFFERENT task and must NOT be silently killed. A
                # genuine already-done always carries both the same
                # recipient and the same subject, so every real
                # double-send is still killed: zero double-action is
                # preserved while distinct real promises survive.
                to_l = str(w.get("to", "")).lower()
                sub_l = str(w.get("subject", "")).lower()
                if (tgt and tgt in to_l) and (obj and obj in sub_l):
                    return True
            if kind == "calendar" and w["kind"] == "calendar_changed":
                if obj and obj in str(w.get("title", "")).lower():
                    return True
            if kind and w["kind"] == "generic_done" and \
                    obj and obj in str(w.get("what", "")).lower():
                return True
        return False

    # --- the recording comms sink (sends NOTHING) ---
    def emit(self, ob: Outbound) -> None:
        self.outbound.append(ob)

    def outbound_for(self, pid: str) -> list:
        return [o for o in self.outbound if pid in (o.pending_ids or [])]


def populated(seed: int = 20260516) -> SimWorld:
    """A realistic, fixed populated life for the scripted day."""
    import random

    rng = random.Random(seed)
    w = SimWorld()
    w.contacts = {
        "dana": {"email": "dana@investor.example", "phone": "+15550101",
                 "rel": "lead investor"},
        "priya": {"email": "priya@home.example", "phone": "+15550102",
                  "rel": "wife"},
        "sean": {"email": "sean@team.example", "phone": "+15550103",
                 "rel": "engineer"},
        "the contractor": {"email": "build@vendor.example",
                           "phone": "+15550104", "rel": "contractor"},
        "marcus": {"email": "marcus@client.example", "phone": "+15550105",
                   "rel": "client"},
    }
    w.calendar = [
        {"title": "standup", "start": 9.0, "end": 9.25},
        {"title": "investor sync with Dana", "start": 14.0, "end": 15.0},
        {"title": "dinner with Priya", "start": 19.5, "end": 21.0},
    ]
    w.files = {
        "the q3 deck": "~/decks/Q3.pdf",
        "the signed contract": "~/legal/contract_signed.pdf",
        "the budget": "~/finance/budget_2026.xlsx",
    }
    w.facts = {}
    w.now_s = 0.0
    rng.random()  # keep seed consumed deterministically
    return w
