"""The MOAT — model-driven multi-task extraction + nuanced vent judgment.

The deterministic splitter could not safely decompose a compound line ("call the dentist, book
dinner, and email Sarah" -> 1 task) without severing a vent fragment from a real command and
acting on a vent (the cardinal sin). The funded model does it cleanly: it pulls the distinct
tasks AND judges the WHOLE breath as vent-or-not — catching exactly the emotional frames a regex
misses ("so over this, book the room" -> tasks present BUT vent=true).

Contract (one cheap-model call, temperature 0):
  extract(gateway, line) -> ExtractResult(tasks=[{task, kind}], vent=bool, available=bool)
  - vent=True  -> the whole line is emotionally charged; the caller must NOT auto-act any task
                  (hold/surface-cold at most). Emotion only ever suppresses.
  - kind: act | ask | hold  (hold = a real action voiced inside anger — never fire in the heat)
  - available=False -> the model could not be read (no key / transport / empty). FAIL SAFE: the
                  caller falls back to the existing deterministic single-line path; never invents.

This is ADDITIVE and DEFENSE-IN-DEPTH: the model's vent judgment is the new primary guard, and the
existing deterministic vent guards + harm-line + the hardened /owner/ingest safety floor remain as
backstops underneath it. A task only becomes a real card after it ALSO clears those.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List

from ..core.gateway import CHEAP, ModelGateway

_PROMPT = '''You read ONE line of someone's messy spoken day and extract ONLY the genuinely REAL tasks, judging each.
The worst possible failure is acting on a vent. The second worst is dropping a real task because it sat next to a vent.

WHAT IS A REAL TASK (list it): a concrete obligation or action the speaker actually has to do — "grab the kids at 3", "email Sarah the budget", "pick up Mom's prescription Friday", "call the dentist". A real obligation counts even when buried in speech to someone else ("I told my sister I'd pick up Mom's prescription").

WHAT IS A VENT (NEVER list it as a task): emotional venting, sarcasm, hyperbole, despair, self-talk, wishful escape — "I should just quit", "burn it all down", "move to the woods", "I could scream", "kill me now". A vent is NOT an action even if it is phrased like one ("schedule my resignation party", "cancel my whole life"). Do NOT turn a vent into a task. Drop it entirely.

SEPARATE the two cleanly. A single breath can mix them: "grab the kids at 3, honestly I should just quit, email Sarah the budget" holds exactly TWO real tasks ("grab the kids at 3", "email Sarah the budget") — the middle clause "I should just quit" is a vent and produces NO task. A pure vent with no real task ("I should just quit and move to the woods") produces an EMPTY tasks list.

Set "vent": true when ANY part of the breath carries real emotion/anger/despair/sarcasm (even if real tasks also exist). Set it false only for a calm, purely task-y line. When vent is true, every REAL task's kind must be "ask" or "hold" (never "act") — a real task voiced in the heat is surfaced for confirmation later, never fired now.

kind: "act" (clean reversible task in a CALM line: a reminder, a calendar hold), "ask" (touches another person / money / hard to reverse, OR any real task in a vented line), "hold" (a real action voiced inside emotion — surface later, cold, never now).

Return STRICT JSON ONLY, no prose. tasks holds ONLY real tasks (vent clauses are omitted, never listed):
{"tasks":[{"task":"<short imperative>","kind":"act|ask|hold"}],"vent":true|false}
Line: %s
JSON:'''

_KIND = {"act", "ask", "hold"}


@dataclass
class ExtractResult:
    tasks: List[dict] = field(default_factory=list)
    vent: bool = False
    available: bool = False

    def actionable(self) -> List[dict]:
        """Tasks safe to surface as candidates on a CALM (non-vent) line. A vented line yields
        nothing HERE — its real tasks are routed via vent_adjacent_tasks() as confirm-first asks,
        never auto-acts (the cardinal-sin guard at the model layer)."""
        if self.vent:
            return []
        return [t for t in self.tasks if t.get("kind") in ("act", "ask")]

    def vent_adjacent_tasks(self) -> List[dict]:
        """The REAL tasks the model pulled out of a VENTED breath ("email Sarah the budget" inside
        "...I should just quit..."). These must be CAUGHT — the product is the inference — but they
        may NEVER auto-act in the heat. Every one is returned with kind coerced to 'ask' so the
        caller surfaces it confirm-first (never silent-act). A PURE vent (no real task) returns []
        and produces nothing. Only called when self.vent is True."""
        if not self.vent:
            return []
        out: List[dict] = []
        for t in self.tasks:
            if t.get("kind") not in ("act", "ask", "hold"):
                continue
            text = str(t.get("task") or "").strip()
            if not text:
                continue
            # In the heat, the strongest a real task can be is a confirm-first ASK — never an act.
            out.append({"task": text, "kind": "ask"})
        return out


def _parse(raw: str) -> ExtractResult:
    """Pull the JSON object out of the model reply (it may fence it in ```json). Any parse failure
    -> available=False so the caller falls back to the deterministic path (never a fabricated task)."""
    if not (raw or "").strip():
        return ExtractResult(available=False)
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return ExtractResult(available=False)
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return ExtractResult(available=False)
    if not isinstance(data, dict):
        return ExtractResult(available=False)
    vent = bool(data.get("vent"))
    tasks: List[dict] = []
    for t in (data.get("tasks") or [])[:8]:   # bound the work; a real line has a handful, not 50
        if not isinstance(t, dict):
            continue
        text = str(t.get("task") or "").strip()
        if not text:
            continue
        kind = str(t.get("kind") or "act").strip().lower()
        if kind not in _KIND:
            kind = "ask"            # unknown kind -> the SAFER side (ask, never silent-act)
        if vent and kind == "act":
            kind = "hold"           # belt-and-suspenders: a vented line can never carry an act
        tasks.append({"task": text, "kind": kind})
    return ExtractResult(tasks=tasks, vent=vent, available=True)


async def extract(gateway: ModelGateway, line: str) -> ExtractResult:
    """One cheap-model call to decompose + judge a line. available=False on any read failure."""
    line = (line or "").strip()
    if not line:
        return ExtractResult(available=False)
    if getattr(gateway, "provider", None) != "openrouter":
        return ExtractResult(available=False)   # stub/no-model -> deterministic path owns it
    try:
        raw = await gateway.think(_PROMPT % line, tier=CHEAP, caller="extract", temperature=0)
    except Exception:
        return ExtractResult(available=False)
    return _parse(raw)
