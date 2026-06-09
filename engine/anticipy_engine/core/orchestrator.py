"""The orchestrator — the boss.

Control loop over a Goal: plan (one smart call), then for each step build a Job,
gate irreversible/external steps through the human path, dispatch on the bus,
verify the Result's proof, retry on failure, reroute to an alternate intent, and
persist after every step so a restart can resume. NEVER marks a goal done
without proof for every step; never silently drops a step.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from typing import Dict, Optional
from zoneinfo import ZoneInfo

from .bus import Bus
from .envelopes import Goal, GoalState, Job, JobStatus, Result, Risk, Step, StepState
from .gateway import SMART, ModelGateway
from .store import GoalStore


class Approver:
    async def approve(self, goal: Goal, step: Step) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class AutoApprover(Approver):
    """Human-path stub: a test can auto-approve or auto-deny."""

    def __init__(self, approve: bool = True) -> None:
        self._approve = approve

    async def approve(self, goal: Goal, step: Step) -> bool:
        return self._approve


def _robust_json(raw):
    """Resilient extraction of a JSON object/array from a model reply that may be fenced,
    prose-wrapped, or slightly off (the browser-agent pattern, reused): strip fences, try the
    whole string, then a balanced-brace/bracket scan. Returns the parsed value or None."""
    if not raw:
        return None
    s = re.sub(r"```(json)?", "", raw).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    for op, cl in (("{", "}"), ("[", "]")):
        start = s.find(op)
        if start < 0:
            continue
        depth = 0
        for i in range(start, len(s)):
            if s[i] == op:
                depth += 1
            elif s[i] == cl:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start:i + 1])
                    except Exception:
                        break
    return None


_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_CALENDAR_EVENT_RE = re.compile(
    r"\b(calendar event|calendar entry|event (on|in) (my |the )?calendar)\b",
    re.I,
)
_TITLE_RE = re.compile(r"\b(?:titled|called|named)\s+(?P<title>.+?)\s+\bon\b", re.I | re.S)
_DATE_RE = re.compile(
    rf"\b(?P<month>{_MONTH_RE})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?\b",
    re.I,
)
_TIME_RANGE_RE = re.compile(
    r"\bfrom\s+(?P<start>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+"
    r"(?:to|until|-)\s+(?P<end>\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b",
    re.I,
)
_CLOCK_RE = re.compile(r"^\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm)?\s*$", re.I)
_TZ_RE = re.compile(r"\b(?P<tz>[A-Z][A-Za-z_]+/[A-Z][A-Za-z_]+)\b")
_BROWSER_ACTION_RE = re.compile(
    r"https?://"
    r"|\b(?:on|at|from|using|via)\s+(?:[a-z0-9-]+\.)+[a-z]{2,}\b"
    r"|\b(?:add|put)\b[\w' ,.-]{0,120}\b(?:cart|basket|bag)\b"
    r"|\b(?:get|grab)\b[\w' ,.-]{0,80}\b(?:that|the)\s+(?:thing|one|item|product)\b",
    re.I,
)
_VAGUE_BROWSER_RE = re.compile(
    r"\b(that|the)\s+(thing|one|item|product)\b"
    r"|\b(earlier|last time|before|was looking at|looked at)\b",
    re.I,
)
_URL_IN_TEXT_RE = re.compile(r"https?://[^\s<>\]})\"']+", re.I)
_DOMAIN_IN_TEXT_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+[a-z]{2,})(/[^\s<>\]})\"']*)?", re.I)
_PRODUCT_HINT_RE = re.compile(
    r"\b(?:looked at|looking at|viewed|found|considered|considering|wanted|shopping for|"
    r"product|item|thing|cart|kitchen)\b",
    re.I,
)


def _parse_clock(raw: str, fallback_ampm: str | None = None) -> tuple[int, int] | None:
    m = _CLOCK_RE.match(raw or "")
    if not m:
        return None
    hour = int(m.group("hour"))
    minute = int(m.group("minute") or "0")
    if hour > 23 or minute > 59:
        return None
    ampm = (m.group("ampm") or fallback_ampm or "").lower()
    if ampm:
        if hour < 1 or hour > 12:
            return None
        if ampm == "am":
            hour = 0 if hour == 12 else hour
        elif ampm == "pm":
            hour = 12 if hour == 12 else hour + 12
    return hour, minute


def _zone_from_text(text: str):
    m = _TZ_RE.search(text or "")
    if m:
        try:
            return ZoneInfo(m.group("tz")), m.group("tz")
        except Exception:
            pass
    local = dt.datetime.now().astimezone().tzinfo
    return local, str(local)


def _calendar_event_step(text: str) -> Optional[Step]:
    """Deterministic plan for explicit, fully grounded Calendar-event requests."""
    if not _CALENDAR_EVENT_RE.search(text or ""):
        return None
    date_m = _DATE_RE.search(text)
    range_m = _TIME_RANGE_RE.search(text)
    if not date_m or not range_m:
        return None

    end_ampm_m = re.search(r"(am|pm)\s*$", range_m.group("end"), re.I)
    start_ampm_m = re.search(r"(am|pm)\s*$", range_m.group("start"), re.I)
    fallback_ampm = end_ampm_m.group(1).lower() if end_ampm_m and not start_ampm_m else None
    start_clock = _parse_clock(range_m.group("start"), fallback_ampm=fallback_ampm)
    end_clock = _parse_clock(range_m.group("end"))
    if not start_clock or not end_clock:
        return None

    now = dt.datetime.now().astimezone()
    month = _MONTHS[date_m.group("month").lower()]
    day = int(date_m.group("day"))
    year = int(date_m.group("year") or now.year)
    zone, zone_name = _zone_from_text(text)
    try:
        start = dt.datetime(year, month, day, start_clock[0], start_clock[1], tzinfo=zone)
        end = dt.datetime(year, month, day, end_clock[0], end_clock[1], tzinfo=zone)
    except ValueError:
        return None
    if end <= start:
        return None

    title_m = _TITLE_RE.search(text)
    summary = title_m.group("title") if title_m else "Calendar event"
    summary = re.sub(r"\s+", " ", summary).strip(" \"'“”.,")
    if not summary:
        summary = "Calendar event"

    return Step(
        intent="create_event",
        args={
            "summary": summary,
            "start_datetime": start.isoformat(timespec="seconds"),
            "end_datetime": end.isoformat(timespec="seconds"),
            "timezone": zone_name,
        },
        risk=Risk.low,
    )


def _clean_link(raw: str) -> str:
    return (raw or "").strip().rstrip(".,;:!?)\"]}'")


def _context_lines(context) -> list[str]:
    if not isinstance(context, dict):
        return []
    lines: list[str] = []
    seen: set[str] = set()
    for key in ("notes", "open_loops", "history", "profile", "derived"):
        val = context.get(key)
        if isinstance(val, str):
            raw_lines = [line.strip() for line in val.splitlines() if line.strip()]
        elif isinstance(val, list):
            raw_lines = [str(line).strip() for line in val if str(line).strip()]
        else:
            raw_lines = []
        for line in raw_lines:
            key_line = re.sub(r"\s+", " ", line).strip().lower()
            if key_line and key_line not in seen:
                seen.add(key_line)
                lines.append(line)
    return lines


def _line_site(line: str) -> str:
    url_m = _URL_IN_TEXT_RE.search(line)
    if url_m:
        return _clean_link(url_m.group(0))
    for m in _DOMAIN_IN_TEXT_RE.finditer(line):
        domain = (m.group(1) or "").lower()
        if m.start(1) > 0 and line[m.start(1) - 1] == "@":
            continue
        if domain and domain not in {"example.com", "localhost"} and "." in domain:
            return "https://" + _clean_link((m.group(1) or "") + (m.group(2) or ""))
    return ""


def _source_ref(line: str) -> str:
    digest = hashlib.sha1((line or "").encode("utf-8", "ignore")).hexdigest()[:12]
    return f"memory:{digest}"


def _sanitize_item(raw: str) -> str:
    item = re.split(
        r"\s+\b(?:on|at|from|via|using)\s+(?:https?://)?(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?",
        raw or "",
        maxsplit=1,
        flags=re.I,
    )[0]
    item = _URL_IN_TEXT_RE.sub(" ", item)
    item = re.sub(r"\b(?:product|item|thing)\s*[:=-]\s*", " ", item, flags=re.I)
    item = re.sub(r"\s+", " ", item).strip(" \"'“”.,:;-")
    item = re.sub(r"^(?:a|an|the)\s+", "", item, flags=re.I)
    return item


def _line_item(line: str) -> str:
    quoted = re.findall(r"['\"“”]([^'\"“”]{3,140})['\"“”]", line)
    if quoted:
        item = _sanitize_item(quoted[-1])
        return item if 3 <= len(item) <= 160 else ""
    patterns = (
        r"\b(?:looked at|looking at|viewed|found|considered|considering|wanted|shopping for)\s+(?P<item>[^.;\n]+)",
        r"\b(?:product|item|thing)\s*[:=-]\s*(?P<item>[^.;\n]+)",
    )
    for pat in patterns:
        m = re.search(pat, line, re.I)
        if m:
            item = _sanitize_item(m.group("item"))
            if 3 <= len(item) <= 160:
                return item
    return ""


def _memory_resolved_browser_step(text: str, context) -> Optional[Step]:
    if not _VAGUE_BROWSER_RE.search(text or ""):
        return None
    candidates = []
    for line in _context_lines(context):
        if not _PRODUCT_HINT_RE.search(line):
            continue
        site = _line_site(line)
        item = _line_item(line)
        if site and item:
            candidates.append({"site": site, "item": item, "source_ref": _source_ref(line)})
    if not candidates:
        return None
    resolved = candidates[0]
    task = (
        f"On {resolved['site']}, find {resolved['item']} and add it to the cart. "
        "Stop after the cart visibly contains the item. Do not checkout, pay, or place an order."
    )
    return Step(
        intent="browse_task",
        args={
            "task": task,
            "url": resolved["site"],
            "original_task": text,
            "resolved_from_memory": True,
            "memory_resolution": resolved,
        },
        risk=Risk.low,
    )


def _browser_action_step(text: str, context=None) -> Optional[Step]:
    """Route web-action goals; vague target resolution must come from memory."""
    clean = (text or "").strip()
    if not clean or not _BROWSER_ACTION_RE.search(clean):
        return None
    resolved = _memory_resolved_browser_step(clean, context)
    if resolved is not None:
        return resolved
    if _VAGUE_BROWSER_RE.search(clean):
        return None
    return Step(intent="browse_task", args={"task": clean}, risk=Risk.low)


class Orchestrator:
    def __init__(
        self,
        bus: Bus,
        gateway: ModelGateway,
        store: GoalStore,
        glassbox=None,
        scorecard=None,
        approver: Optional[Approver] = None,
        max_retries: int = 2,
        alternates: Optional[Dict[str, str]] = None,
        memory_context=None,
    ) -> None:
        self.bus = bus
        # INJECT seam: optional callable(about)->dict; pulled BEFORE the plan smart-call.
        # None (default) -> no memory, prompt unchanged (existing tests unaffected).
        self.memory_context = memory_context
        self.gateway = gateway
        self.store = store
        self.glassbox = glassbox
        self.scorecard = scorecard
        self.approver = approver or AutoApprover(True)
        self.max_retries = max_retries
        # reroute map: if an intent's worker keeps failing, try the alternate.
        self.alternates = alternates if alternates is not None else {"create_event": "browse_task"}
        self._cost_start: Dict[str, float] = {}

    # ---- entry points ----
    async def start_goal(self, goal: Goal) -> Goal:
        self._cost_start[goal.id] = self.gateway.total_cost()
        goal.state = GoalState.planning
        self.store.save(goal)
        self._log("goal_planning", {"goal_id": goal.id})

        context = self.memory_context(goal.description or goal.intent) if self.memory_context else {}
        goal.steps = self._deterministic_plan(goal, context)
        plan_source = "deterministic" if goal.steps else "model"
        if not goal.steps:
            plan_raw = await self.gateway.think(self._plan_prompt(goal, context), tier=SMART, caller="plan", json_mode=True)
            goal.steps = self._parse_plan(plan_raw)
            if not goal.steps:   # ONE bounded re-ask for clean JSON (real models drift; the stub never needs it)
                strict = (self._plan_prompt(goal, context)
                          + '\n\nYour previous reply could not be parsed. Reply with ONLY valid minified JSON '
                            '{"steps":[{"intent":"...","args":{},"risk":"low"}]} and nothing else.')
                plan_raw = await self.gateway.think(strict, tier=SMART, caller="plan", json_mode=True)
                goal.steps = self._parse_plan(plan_raw)
            plan_source = "model"
        if not goal.steps:
            goal.state = GoalState.failed
            self.store.save(goal)
            self._log("goal_failed", {"goal_id": goal.id, "reason": "empty_plan"})
            if self.scorecard is not None:
                self.scorecard.record_goal(goal.id, "failed", self._goal_cost(goal))
            return goal
        goal.state = GoalState.running
        self.store.save(goal)
        self._log("goal_planned", {"goal_id": goal.id, "steps": [s.intent for s in goal.steps],
                                   "source": plan_source})
        return await self._drive(goal)

    async def resume_waiting(self) -> list:
        resumed = []
        for goal in self.store.waiting():
            self._log("goal_resumed", {"goal_id": goal.id})
            resumed.append(await self._drive(goal))
        return resumed

    # ---- core loop ----
    async def _drive(self, goal: Goal) -> Goal:
        goal.state = GoalState.running
        self.store.save(goal)
        for step in goal.steps:
            if step.state == StepState.done:
                continue  # resume-friendly: already-done steps are skipped
            await self._run_step(goal, step)
            self.store.save(goal)  # persist after EVERY step
            if step.state in (StepState.needs_human, StepState.failed):
                goal.state = GoalState.waiting if step.state == StepState.needs_human else GoalState.failed
                self.store.save(goal)
                self._log(f"goal_{goal.state.value}", {"goal_id": goal.id, "stuck_on": step.intent})
                return goal

        # every step verified done -> collect proof, finish
        goal.proof = {f"{i}:{s.intent}": s.result.proof for i, s in enumerate(goal.steps) if s.result}
        goal.state = GoalState.done
        self.store.save(goal)
        self._log("goal_done", {"goal_id": goal.id, "proof": goal.proof})
        if self.scorecard is not None:
            self.scorecard.record_goal(goal.id, "success", self._goal_cost(goal))
        return goal

    async def _run_step(self, goal: Goal, step: Step) -> None:
        # human path: never run an irreversible/external step without approval
        if step.risk in (Risk.needs_confirm, Risk.ask_human):
            approved = await self.approver.approve(goal, step)
            self._log("approval", {"goal_id": goal.id, "intent": step.intent, "approved": approved})
            if not approved:
                step.state = StepState.needs_human
                return

        if await self._dispatch_with_retry(goal, step, step.intent):
            return
        # exhausted retries -> reroute to an alternate worker/intent if one exists
        alt = self.alternates.get(step.intent)
        if alt:
            self._log("reroute", {"goal_id": goal.id, "from": step.intent, "to": alt})
            if await self._dispatch_with_retry(goal, step, alt):
                return
        step.state = StepState.needs_human  # surface; never silently drop

    async def _dispatch_with_retry(self, goal: Goal, step: Step, intent: str) -> bool:
        attempts = 0
        while attempts <= self.max_retries:
            attempts += 1
            step.attempts += 1
            job = Job(intent=intent, args=step.args, risk=step.risk, goal_id=goal.id)
            result = await self.bus.submit_job(job)
            if result.status == JobStatus.success and self._verify(result):
                step.result = result
                step.state = StepState.done
                return True
            if result.status == JobStatus.needs_human:
                step.result = result
                step.state = StepState.needs_human
                return True  # resolved (surfaced); rerouting wouldn't help
            # failed OR success-without-proof -> retry
            step.result = result
        return False

    @staticmethod
    def _verify(result: Result) -> bool:
        """No proof, not done."""
        return result.proof is not None and bool(result.proof)

    # ---- helpers ----
    @staticmethod
    def _deterministic_plan(goal: Goal, context=None) -> list:
        text = goal.description or goal.intent
        calendar = _calendar_event_step(text)
        if calendar is not None:
            return [calendar]
        browser = _browser_action_step(text, context)
        return [browser] if browser is not None else []

    def _plan_prompt(self, goal: Goal, context=None) -> str:
        base = ('Plan the goal into ordered steps. Respond with ONLY a JSON object '
                '{"steps":[{"intent":"...","args":{...},"risk":"low|needs_confirm|ask_human"}]} '
                '- no prose, no markdown fences.\nGOAL: ' + (goal.description or goal.intent))
        # Give a REAL model the available tool/intent vocabulary (general, not per-task; the model still
        # chooses). The stub gateway greps the prompt for keywords, so this is gated to a real provider —
        # the deterministic tier's prompt (and plans) stay byte-identical.
        if getattr(self.gateway, "provider", None) == "openrouter":
            base += "\nUse ONLY these intents (pick the closest fit): " + ", ".join(sorted(self.bus._workers)) + "."
            base += "\nCURRENT_LOCAL_TIME: " + dt.datetime.now().astimezone().isoformat(timespec="seconds") + "."
            base += ('\nArg shapes - browse_task{"task":<plain-English what to do/find on the web>}, '
                     'read_page{"task":<what to read>}, send_email{"recipient","subject","body"}, '
                     'send_text{"recipient","body"}, '
                     'create_event{"summary","start_datetime","end_datetime"}, create_doc{"title","body"}, '
                     'write_memory{"text"}. For any web search / lookup / shopping / browsing step, use '
                     'browse_task with a "task" string. For vague web tasks such as "that thing" or "earlier", '
                     'use browse_task only if RELEVANT MEMORY identifies a real site and item; otherwise ask. '
                     'Never plan by typing the whole instruction into search. For Calendar writes, only use create_event when '
                     'the user supplied a concrete date and clock time, or a relative day plus clock time '
                     'that can be grounded from CURRENT_LOCAL_TIME. Never use capture time as the event time '
                     'unless the user explicitly asked for now.')
        return base + (f"\nRELEVANT MEMORY: {context}" if context else "")

    @staticmethod
    def _parse_plan(raw: str) -> list:
        """Robust: tolerate fenced / prose-wrapped / {steps:[...]} or bare-list output; skip a
        malformed step rather than dropping the whole plan (the Wave-0 PLAN_BAD @ live killer)."""
        data = _robust_json(raw)
        steps_raw = data.get("steps") if isinstance(data, dict) else (data if isinstance(data, list) else None)
        if not isinstance(steps_raw, list):
            return []
        out = []
        for s in steps_raw:
            if not isinstance(s, dict) or not s.get("intent"):
                continue
            risk = s.get("risk", "low")
            risk = Risk(risk) if risk in ("low", "needs_confirm", "ask_human") else Risk.low
            args = s.get("args") if isinstance(s.get("args"), dict) else {}
            out.append(Step(intent=str(s["intent"]), args=args, risk=risk))
        return out

    def _goal_cost(self, goal: Goal) -> float:
        start = self._cost_start.get(goal.id, self.gateway.total_cost())
        return round(self.gateway.total_cost() - start, 6)

    def _log(self, kind: str, payload) -> None:
        if self.glassbox is None:
            return
        data = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
        self.glassbox.log(kind, data)
