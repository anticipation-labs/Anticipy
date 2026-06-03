"""WebVoyagerAgent — the observe -> decide -> act loop, driven by a real
vision model through the gateway, acting through the browser hand's primitives.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from ..core.browser_link import BrowserLink
from ..core.envelopes import new_id
from ..core.gateway import SMART, ModelGateway

SYSTEM = """You are a web agent controlling a real browser. Each turn you get a screenshot of
the page plus a numbered list of interactive elements. Choose the SINGLE best next action toward
the TASK. Respond with ONLY a JSON object, no prose:
{"thought":"brief","action":"click|type|scroll|navigate|answer","index":<int>,"text":"<for type>","enter":<true to submit after typing>,"url":"<for navigate>","dir":"down|up","answer":"<final answer text, only with action=answer>"}
Prefer clicking/typing visible elements by their index. Type into a search box then set enter=true to submit.
Use action=answer as soon as you can answer the TASK from what you see. Do not repeat the same action."""


# Hard safety net: the agent must NEVER click a purchase-confirm control, no
# matter what the model decides. Adding to cart / viewing checkout is fine.
PURCHASE_GUARD = re.compile(
    r"place\s+(your\s+)?order|buy\s*now|complete\s+(your\s+)?purchase|pay\s+now|submit\s+order|confirm\s+(and\s+)?(order|purchase|pay)",
    re.I,
)


def _parse_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"^```(json)?", "", s).strip()
    s = re.sub(r"```$", "", s).strip()
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
    def __init__(self, link: BrowserLink, gateway: ModelGateway, max_steps: int = 8) -> None:
        self.link = link
        self.gw = gateway
        self.max_steps = max_steps

    async def _observe(self, url: Optional[str] = None):
        args = {"url": url} if url else {}
        r = await self.link.send_browse(new_id(), "observe", args, timeout=45.0)
        return (r.get("output") or {}), (r.get("proof") or {}).get("screenshot")

    async def _act(self, action: dict):
        return await self.link.send_browse(new_id(), "act", action, timeout=45.0)

    async def run(self, task: str, start_url: str) -> dict:
        transcript = []
        out, shot = await self._observe(start_url)
        for step in range(self.max_steps):
            els = out.get("elements") or []
            el_lines = "\n".join(
                f'[{e["idx"]}] {e["tag"]} {e.get("type","")} "{e.get("text","")}"' for e in els[:60]
            )
            prompt = (
                SYSTEM
                + f"\n\nTASK: {task}\nURL: {out.get('url')}\nTITLE: {out.get('title')}\n"
                + f"PAGE TEXT (truncated):\n{(out.get('text') or '')[:1200]}\n\nELEMENTS:\n{el_lines}\n\nNext action JSON:"
            )
            raw = await self.gw.think(prompt, tier=SMART, caller="agent", image=shot)
            action = _parse_json(raw)
            transcript.append({"step": step, "url": out.get("url"), "raw": (raw or "")[:200], "action": action})
            if not action:
                break
            if action.get("action") == "answer":
                return {"answer": action.get("answer", ""), "steps": step + 1,
                        "final_url": out.get("url"), "transcript": transcript}
            if action.get("action") == "click":
                el = next((e for e in els if e.get("idx") == action.get("index")), None)
                if el and PURCHASE_GUARD.search(el.get("text", "") or ""):
                    return {"answer": f"STOPPED before a purchase control ('{el.get('text')}'). "
                                      "Reached cart/checkout but did NOT place the order — your confirmation required to buy.",
                            "steps": step + 1, "final_url": out.get("url"),
                            "transcript": transcript, "stopped_for_safety": True}
            await self._act(_clean_action(action))
            out, shot = await self._observe()
        return {"answer": "", "steps": self.max_steps, "final_url": out.get("url"),
                "transcript": transcript, "exhausted": True}


async def judge(gw: ModelGateway, task: str, result: dict) -> dict:
    prompt = (
        "Grade a web agent. Reply ONLY JSON {\"success\":true|false,\"reason\":\"...\"}.\n"
        f"TASK: {task}\nAGENT ANSWER: {result.get('answer')!r}\nFINAL URL: {result.get('final_url')}\n"
        "Success = the answer correctly accomplishes the task."
    )
    raw = await gw.think(prompt, tier=SMART, caller="agent")
    j = _parse_json(raw) or {}
    return {"success": bool(j.get("success")), "reason": j.get("reason", "")}
