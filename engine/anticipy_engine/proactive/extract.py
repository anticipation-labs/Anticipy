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

_PROMPT = '''You read ONE line of someone's messy spoken day and extract the ACTIONABLE tasks, judging each.
RULES (critical — getting these wrong is the worst failure):
- A VENT / sarcasm / hyperbole / despair is NOT a task. "I should quit and move to the woods", "burn it all down", "I could scream" -> list NOTHING actionable and set vent true.
- A real obligation IS a task even when buried in speech to someone else ("I still have to get Mom's prescription before Friday").
- ONE line can hold SEVERAL tasks: "call the dentist at 3, book dinner Friday, and email Sarah" = 3 separate tasks.
- If the WHOLE breath carries real emotion/anger/despair, set "vent": true EVEN IF it also names an action ("so over this, book the room" -> vent true). When vent is true, every task's kind must be "hold" — never act on something said in the heat.
- kind: "act" (clean reversible task: a reminder, a calendar hold), "ask" (touches another person / money / hard to reverse), "hold" (real action voiced inside emotion — surface later, cold, never now).
Return STRICT JSON ONLY, no prose:
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
        """Tasks safe to surface as candidates: only when the line is NOT a vent. A vented line
        yields nothing to act on here (the cardinal-sin guard at the model layer)."""
        if self.vent:
            return []
        return [t for t in self.tasks if t.get("kind") in ("act", "ask")]


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
