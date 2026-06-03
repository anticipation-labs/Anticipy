"""WebVoyagerAgent — the rebuilt browser loop to the frontier recipe.

observe (set-of-marks: numbered boxes + a11y role/name/state + screenshot)
-> decide (strong vision model, fed the running HISTORY each step)
-> act (TRUSTED clicks/keys via the extension's CDP layer)
-> verify (did the page change?) with loop detection + recovery.

Never fakes done. Genuinely blocked pages (captcha/anti-bot) hand off to the
user with the page open. Refuses to click any purchase-confirm control.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from ..core.browser_link import BrowserLink
from ..core.envelopes import new_id
from ..core.gateway import SMART, ModelGateway

SYSTEM = """You control a REAL browser. Each turn you receive:
- a SCREENSHOT with numbered colored boxes drawn on the interactive elements,
- a list of those same numbered elements with role / name / state,
- the GOAL and a short HISTORY of what you already tried and what happened.
Choose the SINGLE best next action toward the GOAL. The index you pick MUST be a number shown on the screenshot.
Reply with ONLY a JSON object (no prose):
{"thought":"one line","action":"click|type|scroll|navigate|answer","index":<int>,"text":"<for type>","enter":<true to submit after typing>,"dir":"down|up","url":"<for navigate>","answer":"<final answer, only with action=answer>"}
Rules:
- Pick from the numbered boxes; never invent an index that isn't listed.
- To search: use action=type on the search box's index, set text, and enter=true.
- If what you need isn't visible, action=scroll (dir=down) then look again.
- HISTORY shows your past actions. If an action caused 'no change', do something DIFFERENT — a different element, scroll, or navigate. Never repeat a no-op.
- Use action=answer ONLY when the GOAL is achieved; put the result in "answer"."""

PURCHASE_GUARD = re.compile(
    r"place\s+(your\s+)?order|buy\s*now|complete\s+(your\s+)?purchase|pay\s+now|submit\s+order|confirm\s+(and\s+)?(order|purchase|pay)",
    re.I,
)
BLOCK_MARKERS = ("enter the characters you see", "type the characters", "captcha",
                 "are you a robot", "are you a human", "unusual traffic", "verify you are human",
                 "press & hold", "access denied", "checking your browser")


def _parse_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    s = re.sub(r"```(json)?", "", raw).strip()
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _clean_action(a: dict) -> dict:
    out = {"action": a.get("action")}
    for k in ("index", "text", "url", "dir", "enter"):
        if k in a and a[k] is not None:
            out[k] = a[k]
    return out


class WebVoyagerAgent:
    def __init__(self, link: BrowserLink, gateway: ModelGateway, max_steps: int = 14) -> None:
        self.link = link
        self.gw = gateway
        self.max_steps = max_steps

    async def _observe(self, url: Optional[str] = None):
        args = {"url": url} if url else {}
        r = await self.link.send_browse(new_id(), "observe", args, timeout=60.0)
        return (r.get("output") or {}), (r.get("proof") or {}).get("screenshot")

    async def _act(self, action: dict):
        return await self.link.send_browse(new_id(), "act", action, timeout=60.0)

    def _done(self, out, step, history, **extra):
        return {"steps": step, "final_url": (out or {}).get("url"), "history": history[-12:], **extra}

    async def run(self, task: str, start_url: str) -> dict:
        history = []
        out, shot = await self._observe(start_url)
        last_sig = None
        stuck = 0
        for step in range(self.max_steps):
            text = (out.get("text") or "").lower()
            if any(k in text for k in BLOCK_MARKERS):
                return self._done(out, step + 1, history, answer="", needs_human=True,
                                  reason="captcha / anti-bot wall — handed back with the page open")

            els = [e for e in (out.get("elements") or []) if e.get("inView")]
            el_lines = "\n".join(
                f'[{e["idx"]}] {e.get("role","")} "{(e.get("name") or "")[:80]}"'
                + (f' ({e["state"]})' if e.get("state") else "")
                for e in els[:50]
            )
            hist = "\n".join(f"- {h}" for h in history[-6:]) or "(nothing yet)"
            nudge = ("\nNOTE: your last action did NOT change the page. Do something different "
                     "(another element / scroll / navigate).") if stuck >= 1 else ""
            prompt = (SYSTEM + f"\n\nGOAL: {task}\nURL: {out.get('url')}\nTITLE: {out.get('title')}\n"
                      f"HISTORY:\n{hist}{nudge}\n\nVISIBLE ELEMENTS:\n{el_lines}\n\nNext action JSON:")
            raw = await self.gw.think(prompt, tier=SMART, caller="agent", image=shot)
            action = _parse_json(raw)
            if not action:
                history.append(f"{step}: model returned no valid action")
                return self._done(out, step + 1, history, answer="", reason="model gave no parseable action")

            if action.get("action") == "answer":
                return self._done(out, step + 1, history, answer=action.get("answer", ""))

            # hard safety: never click a purchase-confirm control
            if action.get("action") == "click":
                el = next((e for e in els if e.get("idx") == action.get("index")), None)
                if el and PURCHASE_GUARD.search(el.get("name", "") or ""):
                    return self._done(out, step + 1, history, stopped_for_safety=True,
                                      answer=f"STOPPED before a purchase control ('{el.get('name')}'). "
                                             "Reached cart/checkout but did NOT place the order — your call to buy.")

            prev_url = out.get("url")
            label = next((e.get("name", "") for e in els if e.get("idx") == action.get("index")), action.get("text", ""))
            await self._act(_clean_action(action))
            out, shot = await self._observe()
            changed = out.get("url") != prev_url
            history.append(f"{step}: {action.get('action')} idx={action.get('index')} "
                           f"'{(label or '')[:28]}' -> {'now ' + (out.get('url') or '')[:55] if changed else 'no change'}")

            sig = (action.get("action"), action.get("index"), prev_url)
            if not changed and action.get("action") in ("click", "navigate"):
                stuck = stuck + 1 if sig == last_sig else 1
                last_sig = sig
            else:
                stuck = 0
                last_sig = None
            if stuck >= 3:
                return self._done(out, step + 1, history, answer="", stuck=True,
                                  reason="loop detected: repeated an action with no progress")

        return self._done(out, self.max_steps, history, answer="", exhausted=True)


async def judge(gw: ModelGateway, task: str, result: dict) -> dict:
    prompt = (
        "Grade a web agent. Reply ONLY JSON {\"success\":true|false,\"reason\":\"...\"}.\n"
        f"TASK: {task}\nAGENT ANSWER: {result.get('answer')!r}\nFINAL URL: {result.get('final_url')}\n"
        "Success = the answer correctly accomplishes the task. A safety stop at checkout (no purchase) counts as success "
        "if the task was to reach checkout. A clean hand-off on a captcha/login wall is NOT success."
    )
    raw = await gw.think(prompt, tier=SMART, caller="agent")
    j = _parse_json(raw) or {}
    return {"success": bool(j.get("success")), "reason": j.get("reason", "")}
