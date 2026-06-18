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

WHAT IS A REAL TASK (list it): a concrete obligation or action the speaker actually has to do — "grab the kids at 3", "email Sarah the budget", "pick up Mom's prescription Friday", "call the dentist". It counts as the speaker's task in exactly three shapes: (1) a DIRECT action of the speaker's ("call the dentist", "send the deck"); (2) a SELF-COMMITMENT ("I told my sister I'd pick up Mom's prescription", "I need to renew the lease"); (3) a RELAYED REQUEST or IMPERATIVE explicitly aimed AT the speaker — "Maya said can you pick up Leila at 3:15" -> "pick up Leila at 3:15"; "my wife says pick up the kids at 3" -> "pick up the kids at 3"; "the boss wants the report redone by Friday" -> "redo the report by Friday". The test: is the SPEAKER explicitly asked, told, or self-committed to DO a concrete action?

CASUAL / VAGUE / FILLER-WRAPPED TASK-INTENT IS STILL A REAL TASK (list it). People almost NEVER speak in clean imperatives like "email Sarah the budget". They say it loosely, hedged, with filler and fuzzy references — and it is STILL a real task you must catch: "oh yeah I gotta do that email of the thing next weekend" -> {"task":"do the email (the thing) next weekend","kind":"ask"}; "I owe my mom a call" -> {"task":"call mom","kind":"ask"}; "I should really book that trip soon" -> {"task":"book the trip","kind":"ask"}; "I keep meaning to deal with that situation with the car" -> {"task":"deal with the car situation","kind":"ask"}; "ugh I really should sort out the whatsit before it's too late" -> {"task":"sort out the whatsit","kind":"ask"}. First-person intent markers — "I gotta", "I need to", "I should/really should", "I owe", "I keep meaning to", "don't let me forget", "remind me", "I've been meaning to", "gotta remember to" — signal a REAL task EVEN WHEN the object ("the thing", "the whatsit", "that situation") or the time ("soon", "at some point", "next weekend") is FUZZY. Do NOT drop a task just because it is vaguely worded — keep the speaker's own words for the fuzzy part ("the thing"), and it gets resolved later by asking the owner or from memory. Missing one of these is the SECOND-worst failure. The ONLY things to drop are true emotional VENTS and AMBIENT reports about other people (below).

WHO PERFORMS THE ACTION decides everything. List a task ONLY when the SPEAKER is the one who must act (or is reminded/helped). If the LISTENER or a THIRD PARTY is the one asked to act, it is NOT the speaker's task — drop it. The grammar looks identical; the DIRECTION is opposite:
 - "Maya said can you pick up Leila" / "my wife says pick up the kids" -> someone asks the SPEAKER -> the speaker acts -> TASK (list it).
 - "babe can you grab milk on the way home?" / "hon could you call the plumber?" -> the SPEAKER asks the LISTENER -> the listener acts -> NOT the speaker's task -> DROP.
 - "can you remind me to call mom?" -> asking to remind the SPEAKER -> TASK (the speaker is the one reminded).
 - "did you ever grab the dry cleaning?" / "did you email Sarah back?" / "hey did you remind Jenny to send the slides at 4 like I asked?" -> the speaker CHECKS whether the listener/3rd party did something -> NOT the speaker's task -> DROP, list nothing (even if it contains "remind" and a time — that time is the OTHER person's, not a reminder the speaker wants set).

WHAT IS NOT A TASK — a QUESTION, or an AMBIENT REPORT of someone else's state/need (NEVER list it, even though it names an action): (a) a question/request where the LISTENER or a THIRD PARTY is the actor (see WHO PERFORMS THE ACTION above) -> drop. (b) a report that a THIRD PARTY has a need, or that something is in some STATE, with NO request or instruction aimed at the speaker, is ambient context, NOT the speaker's task — "Casey told me grandma needs her prescription", "the dishwasher is leaking", "the vendor wants the contract back", "Sarah said she'd handle the catering", "Mom keeps reminding me to call grandma" -> drop, list nothing. When unsure whether the SPEAKER is the actor, prefer DROP: surfacing someone else's action or ambient context as the speaker's task is a nag.

WHAT IS A VENT (NEVER list it as a task): emotional venting, sarcasm, hyperbole, despair, self-talk, wishful escape — "I should just quit", "burn it all down", "move to the woods", "I could scream", "kill me now". A vent is NOT an action even if it is phrased like one ("schedule my resignation party", "cancel my whole life"). Do NOT turn a vent into a task. Drop it entirely.

SEPARATE the two cleanly. A single breath can mix them: "grab the kids at 3, honestly I should just quit, email Sarah the budget" holds exactly TWO real tasks ("grab the kids at 3", "email Sarah the budget") — the middle clause "I should just quit" is a vent and produces NO task. A pure vent with no real task ("I should just quit and move to the woods") produces an EMPTY tasks list.

Set "vent": true when ANY part of the breath carries real emotion — anger, despair, sarcasm, OR overwhelm/exhaustion/frustration. Overwhelm markers absolutely count and people use them constantly next to real tasks: "my brain is fried", "I'm fried", "I'm so done", "I'm exhausted", "I'm running on empty/fumes", "I'm losing it", "I can't even", "I'm drowning", "I'm overwhelmed", "ugh I'm spent". When such a marker sits in the breath, set vent=true for the WHOLE breath even if clean tasks also exist ("my brain is fried, call the dentist and book Friday at 3" -> vent=true, tasks ["call the dentist","book Friday at 3"] each kind "hold"). Set vent=false ONLY for a calm, purely task-y line with no emotional marker at all. When vent is true, every REAL task's kind must be "ask" or "hold" (never "act") — a real task voiced in the heat is surfaced for confirmation later, never fired now.

kind: "act" (clean reversible task in a CALM line: a reminder, a calendar hold), "ask" (touches another person / money / hard to reverse, OR any real task in a vented line), "hold" (a real action voiced inside emotion — surface later, cold, never now).

RESOLVE VAGUE REFERENCES FROM CONTEXT. Earlier lines of the SAME person's day are given as CONTEXT. When THIS line refers to something vaguely — "that thing", "it", "that", "the whole thing", "that situation", "her", "him", "them" — look back through the CONTEXT and rewrite the task with the CONCRETE referent. Example — CONTEXT: "the Henderson contract came in this morning"; LINE: "I need to get that thing reviewed before Friday" -> {"task":"review the Henderson contract before Friday","kind":"ask"}; then LINE: "send it back to legal once I'm done" -> {"task":"send the Henderson contract back to legal","kind":"ask"}. If the context does NOT name the referent, keep the speaker's own words ("that thing") rather than inventing one — never fabricate a referent that was not said.

Return STRICT JSON ONLY, no prose. tasks holds ONLY real tasks (vent clauses are omitted, never listed):
{"tasks":[{"task":"<short imperative, with vague references resolved from context>","kind":"act|ask|hold"}],"vent":true|false}
CONTEXT (earlier in their day; for resolving references only — do NOT extract tasks from it):
%s
LINE (extract tasks from THIS line only): %s
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


_DAY_PROMPT = '''You read a person's WHOLE messy spoken day (many lines at once) and extract EVERY genuinely REAL task they need handled. You see the entire day together, so a vague reference in one line is resolved from another line, and NOTHING is dropped just because it sat next to a vent.

WHAT IS A REAL TASK (list every one): a concrete obligation/action the SPEAKER must do or be reminded of — reminders ("remind me to X", "don't let me forget X"), calendar holds ("block 2pm for X", "lock the trial date on my calendar", "hold the 9:40am flight"), look-ups ("pull up / look up / find out / check X"), drafts ("draft an email/note to X, don't send"), cart-prep ("start/set up a cart for X, don't check out"), calls/emails/errands/follow-ups ("nudge my advisor", "follow up on the Delgado filing"), and money moves ("pay the $14,200 taxes", "wire $400 to her", "refund X to my card"). Casual/fuzzy/filler phrasing is STILL a real task: "I gotta deal with that thing", "I owe my mom a call", "I keep meaning to sort the car out". Keep the speaker's own words for fuzzy parts. Missing a real task is the worst failure here.

ONE TASK PER OBLIGATION. Emit each real obligation EXACTLY ONCE. Do NOT split a reminder into two —
"remind me to call the title company at 9" is ONE task ("call the title company at 9"), never both
"remind me to call..." AND "call...". "set a reminder to read the data room" -> one task ("read the
data room"). Combine a means-clause with its goal ("renew the cert by signing up for the course" -> one).

WHO PERFORMS IT decides everything. List a task ONLY when the SPEAKER must act / is reminded:
 - "Maya said pick up Leila at 3" / "the boss wants the report by Friday" -> the speaker acts -> TASK.
 - An imperative to SEND / TEXT / EMAIL / CALL a named person is the SPEAKER's OWN task (THEY do the
   sending) -> LIST IT: "send Theo a reminder text that the flight lands Sunday" -> {"task":"text Theo
   that the flight lands Sunday"}; "shoot Mara the address" -> list it; "call my mom back" -> list it.
 - Only a QUESTION/REQUEST aimed AT the person is dropped: "Sam, can you take the handoff?" / "babe can
   you grab milk?" -> a request AT ANOTHER NAMED PERSON to do something -> their task -> DROP.
 - "did you ever email Sarah back?" -> a check on someone else -> DROP.
AMBIENT reports of others' state/needs with no instruction to the speaker ("the dishwasher is leaking", "the vendor wants the contract") -> DROP.

VENTS (drop, or mark vent): emotional venting / sarcasm / hyperbole / despair / wishful escape / overwhelm — "I should just quit", "move to the woods", "send help and gas-station coffee", "I'm so done", "I'm fried". A vent is never a task even if phrased like one. If a real task is voiced inside an emotional breath, KEEP the task but set its "vent":true (so it is surfaced confirm-first, never auto-fired).

For each REAL task return {"task":"<short, vague refs resolved from the whole day>","kind":"act|ask|hold","vent":true|false}.
 - kind: "act" = a clean reversible task in a calm line (a reminder, a calendar hold, a lookup); "ask" = touches another person / money / hard-to-reverse, OR any task in a vented breath; "hold" = a real action voiced inside emotion.
 - vent:true forces kind to ask/hold (never act).
Return STRICT JSON ONLY, no prose: {"tasks":[{"task":"...","kind":"...","vent":true|false}]}. Empty list if the whole day is pure vents/ambient.

DAY (extract every real task the SPEAKER must do):
%s
JSON:'''


async def extract_day(gateway: ModelGateway, text: str) -> List[dict]:
    """WHOLE-DAY extraction — ONE pass over the entire transcript so dense multi-line days stop dropping
    tasks to per-line rolling-context contamination (the 20-life catch-rate ceiling). Returns a list of
    {task, kind, vent}; [] on any read failure (caller keeps the deterministic backstops). GENEROUS by
    design — recall first; every emitted task still clears the downstream floors (vent guard, money
    hard-stop, third-party silence), so generosity here can only ADD catches, never weaken safety."""
    text = (text or "").strip()
    if not text or getattr(gateway, "provider", None) != "openrouter":
        return []
    try:
        raw = await gateway.think(_DAY_PROMPT % text, tier="smart", caller="gate", temperature=0)
    except Exception:
        return []
    if not (raw or "").strip():
        return []
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    if not isinstance(data, dict):
        return []
    out: List[dict] = []
    for t in (data.get("tasks") or [])[:40]:   # a whole day has more than one line, but still bounded
        if not isinstance(t, dict):
            continue
        task = str(t.get("task") or "").strip()
        if not task:
            continue
        vent = bool(t.get("vent"))
        kind = str(t.get("kind") or "ask").strip().lower()
        if kind not in _KIND:
            kind = "ask"
        if vent and kind == "act":
            kind = "hold"
        out.append({"task": task, "kind": kind, "vent": vent})
    return out


async def extract(gateway: ModelGateway, line: str, context: str = "") -> ExtractResult:
    """One cheap-model call to decompose + judge a line. available=False on any read failure.

    `context` is the EARLIER lines of the same person's day (most recent last). It is used ONLY
    to resolve vague references in THIS line ("that thing" -> "the Henderson contract"); tasks are
    NEVER extracted from the context (the caller already processed those lines). Empty context (a
    single line / the proactive path / the safety eval) leaves behavior identical to before."""
    line = (line or "").strip()
    if not line:
        return ExtractResult(available=False)
    if getattr(gateway, "provider", None) != "openrouter":
        return ExtractResult(available=False)   # stub/no-model -> deterministic path owns it
    ctx = (context or "").strip() or "(none)"
    try:
        raw = await gateway.think(_PROMPT % (ctx, line), tier=CHEAP, caller="extract", temperature=0)
    except Exception:
        return ExtractResult(available=False)
    return _parse(raw)
