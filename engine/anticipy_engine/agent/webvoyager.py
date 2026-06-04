"""WebVoyagerAgent — a Task-State Controller around observe -> decide -> act.

General machinery for any site (no site-specific logic):
  PLAN     : the model writes an ordered subgoal checklist from the task.
  STATE    : injected tight each step (plan + current subgoal + last 5 actions
             + filtered marked elements + progress label). Older history summarized.
  PROGRESS : code labels each act PROGRESS / NO_CHANGE / REGRESSION from state deltas.
  ANTI-LOOP: code tracks visited-state signatures + action history; on STUCK it
             forbids the repeated action and nudges; 3 stuck on a subgoal -> fail it.
  COMMIT   : once a target is chosen for a subgoal, don't re-pick (kills re-search).
  AD-SKIP  : de-prioritize Sponsored/Ad elements; the judge rejects a sponsored pick.
  BUDGETS  : per-subgoal step cap + higher overall budget.
  REFLECT  : one brief why-did-that-fail, only after NO_CHANGE / REGRESSION.
  DECIDE   : low temperature + structured JSON, for run-to-run stability.
Never fakes done; genuinely blocked pages hand off; never clicks a purchase control.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import List, Optional

from ..core.browser_link import BrowserLink
from ..core.envelopes import new_id
from ..core.gateway import CHEAP, SMART, ModelGateway
from .handoff import ask_message, classify_wall

PLAN_SYS = """Break the task into 3-6 ordered subgoals a browser agent completes in sequence
(e.g., reach the target page; find the target item; select it; perform the action; verify/stop).
Reply ONLY JSON: {"subgoals":["...","..."]}"""

ACT_SYS = """You control a REAL browser through a numbered set-of-marks overlay (the screenshot shows numbered boxes).
Advance the CURRENT SUBGOAL. Reply ONLY JSON:
{"thought":"one line","action":"click|type|scroll|navigate|answer","index":<int>,"text":"<for type>","enter":<true to submit>,"dir":"down|up","url":"<for navigate>","subgoal_done":<true if the current subgoal is now achieved>,"answer":"<final result, only with action=answer>"}
Rules:
- Pick a NUMBER shown on the screenshot; never invent one.
- To search: action=type on the search box's index, with text and enter=true.
- AVOID elements marked [AD] (sponsored) — prefer organic results.
- If the target isn't visible, action=scroll (dir=down) then look again.
- Obey the PROGRESS label and any STUCK note: NEVER repeat an action that caused no change; do something different.
- VERIFY, don't assume: the LAST STEP label says whether your previous action actually changed the page. If it did not, your approach was wrong — try something else.
- When stuck, change the KIND of action (scroll to reveal new options, press enter to submit, or choose a different element) — not merely a different number.
- Set subgoal_done=true the moment the CURRENT subgoal is achieved. Use action=answer only when the WHOLE task is done."""

# Real purchase-confirm controls only. NOT "submit order" (that's a generic form
# submit, e.g. demo forms) — too broad a match was false-stopping legit tasks.
PURCHASE_GUARD = re.compile(
    r"place\s+(your\s+)?order|buy\s*now|complete\s+(your\s+)?purchase|pay\s+now|confirm\s+(and\s+)?(order|purchase|pay)",
    re.I,
)
BLOCK_MARKERS = ("enter the characters you see", "type the characters", "captcha",
                 "are you a robot", "are you a human", "unusual traffic", "verify you are human",
                 "press & hold", "access denied", "checking your browser")


def _parse_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    s = re.sub(r"```(json)?", "", raw).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except Exception:
                    return None
    return None


def _clean_action(a: dict) -> dict:
    out = {"action": a.get("action")}
    for k in ("index", "text", "url", "dir", "enter"):
        if k in a and a[k] is not None:
            out[k] = a[k]
    return out


def _sig(url, title, els) -> str:
    key = (url or "").split("?")[0] + "|" + (title or "")[:60] + "|" + ",".join((e.get("name") or "")[:18] for e in els[:8])
    return hashlib.sha1(key.encode()).hexdigest()[:12]


class TaskState:
    def __init__(self, subgoals: List[str]) -> None:
        self.subgoals = [{"text": s, "status": "pending"} for s in subgoals]
        self.i = 0

    @property
    def current(self):
        return self.subgoals[self.i] if self.i < len(self.subgoals) else None

    def advance(self):
        if self.current:
            self.current["status"] = "done"
        self.i += 1

    def fail_current(self):
        if self.current:
            self.current["status"] = "failed"
        self.i += 1

    def done(self) -> bool:
        return self.i >= len(self.subgoals)

    def render(self) -> str:
        out = []
        for k, g in enumerate(self.subgoals):
            mark = "x" if g["status"] == "done" else ("!" if g["status"] == "failed" else (">" if k == self.i else " "))
            out.append(f"  [{mark}] {g['text']}")
        return "\n".join(out)


class WebVoyagerAgent:
    def __init__(self, link: BrowserLink, gateway: ModelGateway, max_steps: int = 28,
                 per_subgoal: int = 8, notifier=None) -> None:
        self.link = link
        self.gw = gateway
        self.max_steps = max_steps
        self.per_subgoal = per_subgoal
        self.notifier = notifier  # async callable(str)->None; texts the user on a wall (None = log only)

    async def _observe(self, url: Optional[str] = None):
        r = await self.link.send_browse(new_id(), "observe", {"url": url} if url else {}, timeout=60.0)
        return (r.get("output") or {}), (r.get("proof") or {}).get("screenshot")

    @staticmethod
    def _empty_obs(out) -> bool:
        # An observation we cannot act on: no actionable elements AND no page
        # identity. Heavy sites return this if we look before they're ready.
        o = out or {}
        return not (o.get("elements") or []) and not o.get("url") and not (o.get("text") or "")

    async def _observe_ready(self, url: Optional[str] = None, tries: int = 4):
        # GENERAL fix (no site logic): never decide on a not-ready page, and never
        # let a slow/hung observe crash the run. If the observation is empty (or the
        # observe times out), wait a beat and re-look (same tab, no re-nav).
        async def _try(u=None):
            try:
                return await self._observe(u)
            except Exception:
                return {}, None  # timeout / transport hiccup -> treat as not-ready
        out, shot = await _try(url)
        n = 0
        while self._empty_obs(out) and n < tries:
            await asyncio.sleep(1.2 + 0.6 * n)
            out, shot = await _try()
            n += 1
        return out, shot

    async def _act(self, action: dict):
        # An act that hangs/times out must NOT crash the run. Fail fast (20s); the
        # next observe shows no change and the anti-loop guard recovers or hands off.
        try:
            return await self.link.send_browse(new_id(), "act", action, timeout=20.0)
        except Exception:
            return {"status": "error"}

    async def _plan(self, task: str) -> List[str]:
        raw = await self.gw.think(PLAN_SYS + f"\n\nTASK: {task}", tier=SMART, caller="agent",
                                  json_mode=True, temperature=0.2)
        subs = (_parse_json(raw) or {}).get("subgoals") or [task]
        return [str(s) for s in subs][:6]

    def _done(self, out, step, history, **extra):
        return {"steps": step, "final_url": (out or {}).get("url"), "history": history[-40:],
                "final_shot": getattr(self, "_cur_shot", None), **extra}

    async def _notify(self, msg: str) -> None:
        if not self.notifier:
            return
        try:
            await self.notifier(msg)
        except Exception:
            pass  # a notify failure must never crash the run

    async def _handoff(self, out, step, history, wall_kind: str, detail: str) -> dict:
        # pause -> ask the human (text) -> resume later via /agent/resume. We stop
        # observing here, so we never screenshot what the user types at the wall.
        ask = ask_message(wall_kind, (out or {}).get("url") or "")
        await self._notify(ask)
        return self._done(out, step, history, answer="", needs_human=True, paused=True,
                          wall_kind=wall_kind, ask=ask, resume_token=new_id(), reason=detail)

    async def run(self, task: str, start_url: str) -> dict:
        state = TaskState(await self._plan(task))
        history: List[str] = []
        visited: dict = {}
        committed: Optional[str] = None
        sub_steps = 0
        sub_stuck = 0
        reflection = ""
        last_thought = ""  # carry the model's own reasoning forward one step (scratchpad)
        forbid = None  # (action, index) forbidden this step after a STUCK

        out, shot = await self._observe_ready(start_url)
        self._cur_shot = shot
        prev_sig = _sig(out.get("url"), out.get("title"), out.get("elements") or [])
        visited[prev_sig] = 1
        progress = "START"

        for step in range(self.max_steps):
            text = (out.get("text") or "").lower()
            if any(k in text for k in BLOCK_MARKERS):
                return await self._handoff(out, step + 1, history, classify_wall(text),
                                           "captcha / anti-bot wall — handed back with the page open")

            all_in = [e for e in (out.get("elements") or []) if e.get("inView")]
            organic = [e for e in all_in if not e.get("sponsored")]
            sponsored = [e for e in all_in if e.get("sponsored")]
            els = (organic + sponsored)[:45]  # organic first; ads last (and labelled)

            subgoal_text = state.current["text"] if state.current else "Provide the final answer (action=answer)."
            stuck_note = ""
            if forbid is not None:
                stuck_note = (f"STUCK on this subgoal: you repeated {forbid} with no progress. Pick a DIFFERENT "
                              f"element that advances the subgoal, or scroll for new options. Do NOT repeat {forbid}.")
            el_lines = "\n".join(
                f'[{e["idx"]}]{" [AD]" if e.get("sponsored") else ""} {e.get("role","")} "{(e.get("name") or "")[:80]}"'
                + (f' ({e["state"]})' if e.get("state") else "")
                for e in els
            )
            prompt = (
                ACT_SYS
                + f"\n\nTASK: {task}\nPLAN:\n{state.render()}\nCURRENT SUBGOAL: {subgoal_text}\n"
                + f"URL: {out.get('url')}\nTITLE: {out.get('title')}\nLAST STEP: {progress}\n"
                + (f"COMMITTED TARGET (act on this; don't re-pick): {committed}\n" if committed else "")
                + (f"REFLECTION: {reflection}\n" if reflection else "")
                + (f"YOUR LAST THOUGHT: {last_thought}\n" if last_thought else "")
                + (stuck_note + "\n" if stuck_note else "")
                + "RECENT ACTIONS:\n" + ("\n".join(history[-5:]) or "(none)") + "\n\n"
                + "VISIBLE ELEMENTS:\n" + el_lines + "\n\nNext action JSON:"
            )
            # two-tier ladder: cheap by default; escalate to smart only when stuck
            # (no progress last step, or an action was forbidden by the anti-loop guard)
            escalate = (sub_stuck >= 1) or (forbid is not None)
            tier = SMART if escalate else CHEAP
            raw1 = await self.gw.think(prompt, tier=tier, caller="agent", image=shot,
                                       json_mode=True, temperature=0.1)
            action = _parse_json(raw1)
            raw2 = ""
            if not action or not action.get("action"):
                raw2 = await self.gw.think(  # a non-answer always escalates to smart
                    prompt + "\n\nReturn ONE JSON action now with an \"action\" field.",
                    tier=SMART, caller="agent", image=shot, json_mode=True, temperature=0.1)
                action = _parse_json(raw2)
            if not action or not action.get("action"):
                return self._done(out, step + 1, history, answer="", reason="no parseable action after retry",
                                  last_raw=((raw1 or "<empty>")[:220] + " ||RETRY|| " + (raw2 or "<empty>")[:220]))

            last_thought = (action.get("thought") or "")[:160]  # scratchpad for the next step

            if action.get("action") == "answer":
                return self._done(out, step + 1, history, answer=action.get("answer", ""))

            if action.get("action") == "click":
                el = next((e for e in els if e.get("idx") == action.get("index")), None)
                if el and PURCHASE_GUARD.search(el.get("name", "") or ""):
                    return self._done(out, step + 1, history, stopped_for_safety=True,
                                      answer=f"STOPPED before a purchase control ('{el.get('name')}'). "
                                             "Did NOT place the order — handed back for your confirmation.")
                if el and committed is None:
                    committed = (el.get("name") or "")[:48]  # commit to this target for the subgoal

            sig_here = (action.get("action"), action.get("index"))
            if forbid is not None and sig_here == forbid:
                # the model ignored the STUCK warning; skip this action, force a rethink next step
                history.append(f"{step}: BLOCKED repeat {sig_here}")
                forbid = None
                continue

            prev_url = out.get("url")
            label = next((e.get("name", "") for e in els if e.get("idx") == action.get("index")), action.get("text", ""))
            await self._act(_clean_action(action))
            out, shot = await self._observe_ready()
            self._cur_shot = shot
            sub_steps += 1

            new_sig = _sig(out.get("url"), out.get("title"), out.get("elements") or [])
            if new_sig == prev_sig:
                progress = "NO_CHANGE"
            elif new_sig in visited:
                progress = "REGRESSION"
            else:
                progress = "PROGRESS"
            visited[new_sig] = visited.get(new_sig, 0) + 1
            history.append(f"{step}: {action.get('action')} idx={action.get('index')} "
                           f"'{(label or '')[:26]}' -> {progress} ({(out.get('url') or '')[:48]})")

            # subgoal completion
            if action.get("subgoal_done") and state.current:
                state.advance()
                committed, sub_steps, sub_stuck, forbid, reflection = None, 0, 0, None, ""
                prev_sig = new_sig
                continue

            # anti-loop + reflection on failure
            if progress in ("NO_CHANGE", "REGRESSION"):
                sub_stuck += 1
                forbid = sig_here if action.get("action") == "click" else None
                reflection = await self._reflect(task, subgoal_text, history)
            else:
                sub_stuck = 0
                forbid = None
                reflection = ""

            # per-subgoal budget / stuck escalation -> fail subgoal -> alternative or handoff
            if (sub_stuck >= 3 or sub_steps >= self.per_subgoal) and state.current:
                state.fail_current()
                history.append(f"{step}: subgoal failed ('{subgoal_text[:40]}') -> moving on")
                committed, sub_steps, sub_stuck, forbid, reflection = None, 0, 0, None, ""
                if state.done():
                    return await self._handoff(out, step + 1, history, classify_wall(out.get("text", "")),
                                               "could not complete a subgoal after retries — handed back")
            prev_sig = new_sig

        return self._done(out, self.max_steps, history, answer="", exhausted=True)

    async def _reflect(self, task: str, subgoal: str, history: List[str]) -> str:
        raw = await self.gw.think(
            f"Web agent on subgoal '{subgoal}' for task '{task}'. Last actions:\n" + "\n".join(history[-4:])
            + "\nThe last action did not progress. In ONE sentence: what likely went wrong and what DIFFERENT thing to try.",
            tier=SMART, caller="agent", temperature=0.3)
        return (raw or "").strip()[:200]


async def judge(gw: ModelGateway, task: str, result: dict, image: Optional[str] = None) -> dict:
    prompt = (
        "You are grading a web agent, with the FINAL page screenshot attached. "
        "Reply ONLY JSON {\"success\":true|false,\"reason\":\"...\"}.\n"
        f"TASK: {task}\nAGENT ANSWER: {result.get('answer')!r}\nFINAL URL: {result.get('final_url')}\n"
        "Decide ONLY from substance: does the answer, corroborated by what is visible in the final screenshot, "
        "satisfy what the task asked for? Judge on correctness, not phrasing, and apply the SAME standard to every "
        "site. If the task itself instructed the agent to stop at a particular step, stopping there is success."
    )
    raw = await gw.think(prompt, tier=SMART, caller="agent", image=image, json_mode=True)
    j = _parse_json(raw) or {}
    return {"success": bool(j.get("success")), "reason": j.get("reason", "")}
