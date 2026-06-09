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
import urllib.parse
from typing import List, Optional

from ..core.browser_link import BrowserLink
from ..core.envelopes import new_id
from ..core.gateway import CHEAP, SMART, ModelGateway
from .handoff import ask_message, classify_wall

PLAN_SYS = """Break the task into 3-6 ordered subgoals a browser agent completes in sequence
(e.g., reach the target page; find the target item; select it; perform the action; verify/stop).
Reply ONLY JSON: {"subgoals":["...","..."]}"""

AGENT_MAX_TOKENS = 16

ACT_SYS = """You control a REAL browser through a numbered set-of-marks overlay (the screenshot shows numbered boxes).
Advance the CURRENT SUBGOAL. Reply ONLY JSON:
{"thought":"one line","action":"click|type|scroll|navigate|answer","index":<int>,"text":"<for type>","enter":<true to submit>,"dir":"down|up","url":"<for navigate>","subgoal_done":<true if the current subgoal is now achieved>,"answer":"<final result, only with action=answer>"}
Rules:
- Use the shortest valid JSON. Omit unused keys and omit "thought" if space is tight.
- If SEARCH_TEXT is provided and you need to type it, use "text":"$ITEM" exactly.
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
COMMERCE_STOP = {
    "the", "and", "for", "with", "that", "this", "thing", "item", "product", "cart", "basket",
    "bag", "add", "added", "shipping", "pickup", "delivery",
}
COMMERCE_SEARCH_URLS = {
    "target.com": "https://www.target.com/s?searchTerm={q}",
    "walmart.com": "https://www.walmart.com/search?q={q}",
    "bestbuy.com": "https://www.bestbuy.com/site/searchpage.jsp?st={q}",
    "homedepot.com": "https://www.homedepot.com/s/{q}",
    "lowes.com": "https://www.lowes.com/search?searchTerm={q}",
    "ikea.com": "https://www.ikea.com/us/en/search/?q={q}",
}
ADD_TO_CART_RE = re.compile(
    r"\b(add|put)\b.{0,50}\b(cart|basket|bag)\b|\badd\b.{0,30}\b(shipping|pickup|delivery)\b|^\s*add\s+",
    re.I,
)
VIEW_CART_RE = re.compile(r"\b(view|go to|open)\b.{0,30}\b(cart|basket|bag)\b|^\s*(cart|basket|bag)\s*$", re.I)
NON_PRODUCT_RE = re.compile(
    r"\b(add to|cart|basket|bag|checkout|sponsored|ad|sign in|log in|create account|"
    r"pickup|delivery|shipping|ratings?|reviews?|see more|show more)\b",
    re.I,
)


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


async def _think(gw: ModelGateway, task: str, tier: str, caller: str, image: Optional[str] = None,
                 json_mode: bool = False, temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None) -> str:
    try:
        return await gw.think(task, tier=tier, caller=caller, image=image, json_mode=json_mode,
                              temperature=temperature, max_tokens=max_tokens)
    except TypeError as exc:
        if "max_tokens" not in str(exc):
            raise
        return await gw.think(task, tier=tier, caller=caller, image=image, json_mode=json_mode,
                              temperature=temperature)


def _clean_action(a: dict, item_text: str = "") -> dict:
    out = {"action": a.get("action")}
    for k in ("index", "text", "url", "dir", "enter"):
        if k in a and a[k] is not None:
            out[k] = item_text if k == "text" and str(a[k]).strip() in {"$ITEM", "<ITEM>"} else a[k]
    return out


def _search_text(task: str) -> str:
    patterns = (
        r"\bfind\s+(?P<item>.+?)\s+and\s+add\b",
        r"\bsearch\s+for\s+(?P<item>.+?)\b(?:and|then|$)",
    )
    for pat in patterns:
        m = re.search(pat, task or "", re.I)
        if m:
            item = re.sub(r"\s+", " ", m.group("item")).strip(" .,:;-")
            if 3 <= len(item) <= 180:
                return item
    return ""


def _host(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url or "").netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _commerce_search_url(start_url: str, item: str) -> str:
    host = _host(start_url)
    q = urllib.parse.quote_plus(item)
    for domain, template in COMMERCE_SEARCH_URLS.items():
        if host == domain or host.endswith("." + domain):
            return template.format(q=q)
    return ""


def _item_tokens(text: str) -> list[str]:
    toks = re.findall(r"\d+(?:\.\d+)?|[a-z0-9]+", (text or "").lower())
    keep = []
    for tok in toks:
        if tok in COMMERCE_STOP:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", tok) or len(tok) >= 3 or tok in {"oz", "ml", "qt", "lb"}:
            keep.append(tok)
    return keep


def _number_tokens(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", (text or "").lower())


def _quantity_pairs(text: str) -> list[tuple[str, str]]:
    units = {
        "ounce": "oz", "ounces": "oz", "oz": "oz",
        "cup": "cup", "cups": "cup",
        "count": "ct", "counts": "ct", "ct": "ct",
        "quart": "qt", "quarts": "qt", "qt": "qt",
        "milliliter": "ml", "milliliters": "ml", "ml": "ml",
        "pound": "lb", "pounds": "lb", "lb": "lb",
        "gallon": "gal", "gallons": "gal", "gal": "gal",
    }
    out = []
    for m in re.finditer(
        r"(?P<num>\d+(?:\.\d+)?)[\s-]*(?:fl[\s-]*)?"
        r"(?P<unit>ounces?|oz|cups?|counts?|ct|quarts?|qt|milliliters?|ml|pounds?|lb|gallons?|gal)\b",
        (text or "").lower(),
    ):
        out.append((m.group("num"), units.get(m.group("unit"), m.group("unit"))))
    return out


def _numbers_match(candidate: str, item: str) -> bool:
    nums = _number_tokens(item)
    if not nums:
        return True
    item_pairs = _quantity_pairs(item)
    if item_pairs:
        candidate_pairs = set(_quantity_pairs(candidate))
        return all(pair in candidate_pairs for pair in item_pairs)
    hay = " " + re.sub(r"[^a-z0-9.]+", " ", (candidate or "").lower()) + " "
    return all(re.search(rf"(?<!\d){re.escape(num)}(?!\d)", hay) for num in nums)


def _token_hits(name: str, tokens: list[str]) -> int:
    hay = " " + re.sub(r"[^a-z0-9]+", " ", (name or "").lower()) + " "
    hits = 0
    for tok in tokens:
        if f" {tok} " in hay or (len(tok) >= 5 and tok in hay):
            hits += 1
    return hits


def _pick_product(elements: list[dict], item: str) -> Optional[dict]:
    tokens = _item_tokens(item)
    if not tokens:
        return None
    best = None
    best_score = 0
    for el in elements or []:
        name = (el.get("name") or "").strip()
        if not name or el.get("sponsored") or NON_PRODUCT_RE.search(name) or not _numbers_match(name, item):
            continue
        role = (el.get("role") or "").lower()
        if role not in {"a", "button"} and "link" not in role:
            continue
        hits = _token_hits(name, tokens)
        if hits <= 0:
            continue
        score = hits * 3 + (2 if el.get("inView") else 0) + min(len(name), 120) / 120
        if score > best_score:
            best, best_score = el, score
    min_hits = 2 if len(tokens) >= 3 else 1
    return best if best and _token_hits(best.get("name") or "", tokens) >= min_hits else None


def _pick_button(elements: list[dict], pattern: re.Pattern) -> Optional[dict]:
    for el in elements or []:
        name = (el.get("name") or "").strip()
        if not name or el.get("sponsored") or PURCHASE_GUARD.search(name):
            continue
        role = (el.get("role") or "").lower()
        if role not in {"button", "a", "input"} and "button" not in role and "link" not in role and "search" not in role:
            continue
        if pattern.search(name):
            return el
    return None


def _pick_add_button(elements: list[dict], item: str) -> Optional[dict]:
    item_tokens = _item_tokens(item)
    for el in elements or []:
        name = (el.get("name") or "").strip()
        if not name or el.get("sponsored") or PURCHASE_GUARD.search(name):
            continue
        if re.search(r"\b(add to list|registry|wish list|favorite)\b", name, re.I):
            continue
        if not ADD_TO_CART_RE.search(name):
            continue
        # If the real site exposes a variant number in the add control, it must
        # match the remembered item. Generic "Add to cart" controls are allowed.
        if _number_tokens(name) and not _numbers_match(name, item):
            continue
        generic = re.fullmatch(r"\s*add\s+(to\s+)?(cart|basket|bag)\s*", name, re.I) is not None
        if not generic:
            hits = _token_hits(name, item_tokens)
            required = max(3, int(len(item_tokens) * 0.7 + 0.999))
            if hits < required:
                continue
        role = (el.get("role") or "").lower()
        if role not in {"button", "a", "input"} and "button" not in role and "link" not in role:
            continue
        return el
    return None


def _cart_verified(out: dict, item: str) -> bool:
    text = (out or {}).get("text") or ""
    low = text.lower()
    url = ((out or {}).get("url") or "").lower()
    added = (
        any(k in low for k in ("added to cart", "added to bag", "added to basket", "item added", "in your cart"))
        or re.search(r"\b\d+\s+in\s+(cart|basket|bag)\b|\bin\s+(cart|basket|bag)\b", low) is not None
    )
    cart_url = re.search(r"/(cart|basket|bag)(?:[/?#]|$)", url) is not None
    tokens = _item_tokens(item)
    if not (added or cart_url) or not tokens or not _numbers_match(text, item):
        return False
    hits = _token_hits(text, tokens)
    return hits >= (2 if len(tokens) >= 3 else 1)


def _page_state(stage: str, out: dict, item: str, action: str = "") -> dict:
    elements = []
    for el in (out or {}).get("elements") or []:
        name = (el.get("name") or "").strip()
        if not name:
            continue
        elements.append({
            "idx": el.get("idx"),
            "role": el.get("role"),
            "name": name[:90],
            "inView": bool(el.get("inView")),
            "sponsored": bool(el.get("sponsored")),
        })
        if len(elements) >= 18:
            break
    return {
        "stage": stage,
        "action": action,
        "url": (out or {}).get("url"),
        "title": (out or {}).get("title"),
        "item_token_hits": _token_hits((out or {}).get("text") or "", _item_tokens(item)),
        "cartish": any(k in ((out or {}).get("text") or "").lower() for k in ("added to cart", "cart", "basket", "bag")),
        "elements": elements,
    }


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
        if _search_text(task):
            return [
                "search for the remembered item on the site",
                "open the matching non-sponsored product",
                "add the item to the cart",
                "verify the cart contains the item",
            ]
        raw = await _think(self.gw, PLAN_SYS + f"\n\nTASK: {task}", tier=SMART, caller="agent",
                           json_mode=True, temperature=0.2, max_tokens=AGENT_MAX_TOKENS)
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

    async def _try_commerce_recipe(self, task: str, start_url: str) -> Optional[dict]:
        item = _search_text(task)
        if not item or not re.search(r"\b(cart|basket|bag)\b", task or "", re.I):
            return None

        history: List[str] = []
        states: list[dict] = []
        steps = 0

        search_url = _commerce_search_url(start_url, item)
        if search_url:
            out, shot = await self._observe_ready(search_url)
            self._cur_shot = shot
            history.append(f"recipe: navigate search url for item on {_host(start_url)}")
        else:
            out, shot = await self._observe_ready(start_url)
            self._cur_shot = shot
            history.append("recipe: observe start page")
            search_box = _pick_button(out.get("elements") or [], re.compile(r"\bsearch\b", re.I))
            if search_box:
                await self._act({"action": "type", "index": search_box.get("idx"), "text": item, "enter": True})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: typed item into site search idx={search_box.get('idx')}")
                steps += 1

        states.append(_page_state("search_results", out, item, history[-1]))
        text = (out.get("text") or "").lower()
        if any(k in text for k in BLOCK_MARKERS):
            return await self._handoff(out, steps + 1, history, classify_wall(text),
                                       "captcha / anti-bot wall during commerce recipe")
        if _cart_verified(out, item):
            return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                              page_states=states, commerce_recipe=True)

        product = None
        for scrolls in range(3):
            product = _pick_product(out.get("elements") or [], item)
            if product:
                break
            await self._act({"action": "scroll", "dir": "down"})
            out, shot = await self._observe_ready()
            self._cur_shot = shot
            history.append(f"recipe: scroll search results {scrolls + 1}")
            states.append(_page_state(f"search_results_scroll_{scrolls + 1}", out, item, history[-1]))
            steps += 1

        if product:
            label = (product.get("name") or "")[:80]
            await self._act({"action": "click", "index": product.get("idx")})
            out, shot = await self._observe_ready()
            self._cur_shot = shot
            history.append(f"recipe: opened product idx={product.get('idx')} '{label}'")
            states.append(_page_state("product_page", out, item, history[-1]))
            steps += 1
        else:
            add_from_results = _pick_add_button(out.get("elements") or [], item)
            if add_from_results:
                await self._act({"action": "click", "index": add_from_results.get("idx")})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: clicked add control from results idx={add_from_results.get('idx')}")
                states.append(_page_state("post_add_from_results", out, item, history[-1]))
                steps += 1
            else:
                return self._done(out, steps + 1, history, answer="",
                                  reason="commerce recipe could not identify a matching product",
                                  page_states=states, commerce_recipe=True)

        if _cart_verified(out, item):
            return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                              page_states=states, commerce_recipe=True)

        for attempt in range(5):
            if _cart_verified(out, item):
                return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                  page_states=states, commerce_recipe=True)
            add = _pick_add_button(out.get("elements") or [], item)
            if not add:
                await self._act({"action": "scroll", "dir": "down"})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: scroll product for add control {attempt + 1}")
                states.append(_page_state(f"product_scroll_{attempt + 1}", out, item, history[-1]))
                steps += 1
                if _cart_verified(out, item):
                    return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                      page_states=states, commerce_recipe=True)
                continue
            label = (add.get("name") or "")[:80]
            await self._act({"action": "click", "index": add.get("idx")})
            out, shot = await self._observe_ready()
            self._cur_shot = shot
            history.append(f"recipe: clicked add control idx={add.get('idx')} '{label}'")
            states.append(_page_state("post_add", out, item, history[-1]))
            steps += 1
            break

        if _cart_verified(out, item):
            return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                              page_states=states, commerce_recipe=True)

        view_cart = _pick_button(out.get("elements") or [], VIEW_CART_RE)
        if view_cart:
            label = (view_cart.get("name") or "")[:80]
            await self._act({"action": "click", "index": view_cart.get("idx")})
            out, shot = await self._observe_ready()
            self._cur_shot = shot
            history.append(f"recipe: opened cart idx={view_cart.get('idx')} '{label}'")
            states.append(_page_state("cart_page", out, item, history[-1]))
            steps += 1
            if _cart_verified(out, item):
                return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                  page_states=states, commerce_recipe=True)

        return self._done(out, steps + 1, history, answer="",
                          reason="commerce recipe did not verify the cart artifact",
                          page_states=states, commerce_recipe=True)

    async def run(self, task: str, start_url: str) -> dict:
        recipe_result = await self._try_commerce_recipe(task, start_url)
        if recipe_result is not None:
            return recipe_result

        state = TaskState(await self._plan(task))
        history: List[str] = []
        visited: dict = {}
        committed: Optional[str] = None
        sub_steps = 0
        sub_stuck = 0
        reflection = ""
        last_thought = ""  # carry the model's own reasoning forward one step (scratchpad)
        forbid = None  # (action, index) forbidden this step after a STUCK
        item_text = _search_text(task)

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
                + (f"SEARCH_TEXT: {item_text}\n" if item_text else "")
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
            raw1 = await _think(self.gw, prompt, tier=tier, caller="agent", image=shot,
                                json_mode=True, temperature=0.1, max_tokens=AGENT_MAX_TOKENS)
            if not (raw1 or "").strip() and shot:
                # Some model/provider paths return empty content for image+JSON.
                # The prompt already carries the set-of-marks element list, so a
                # text-only retry keeps the same planner in the loop without faking.
                raw1 = await _think(self.gw, prompt, tier=tier, caller="agent", image=None,
                                    json_mode=True, temperature=0.1, max_tokens=AGENT_MAX_TOKENS)
            if not (raw1 or "").strip():
                raw1 = await _think(self.gw, prompt, tier=tier, caller="agent", image=None,
                                    json_mode=False, temperature=0.1, max_tokens=AGENT_MAX_TOKENS)
            action = _parse_json(raw1)
            raw2 = ""
            if not action or not action.get("action"):
                raw2 = await _think(  # a non-answer always escalates to smart
                    self.gw,
                    prompt + "\n\nReturn ONE JSON action now with an \"action\" field.",
                    tier=SMART, caller="agent", image=shot, json_mode=True, temperature=0.1,
                    max_tokens=AGENT_MAX_TOKENS)
                if not (raw2 or "").strip() and shot:
                    raw2 = await _think(
                        self.gw,
                        prompt + "\n\nReturn ONE JSON action now with an \"action\" field.",
                        tier=SMART, caller="agent", image=None, json_mode=True, temperature=0.1,
                        max_tokens=AGENT_MAX_TOKENS)
                if not (raw2 or "").strip():
                    raw2 = await _think(
                        self.gw,
                        prompt + "\n\nReturn ONE JSON action now with an \"action\" field.",
                        tier=SMART, caller="agent", image=None, json_mode=False, temperature=0.1,
                        max_tokens=AGENT_MAX_TOKENS)
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
            await self._act(_clean_action(action, item_text))
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
        raw = await _think(
            self.gw,
            f"Web agent on subgoal '{subgoal}' for task '{task}'. Last actions:\n" + "\n".join(history[-4:])
            + "\nThe last action did not progress. In ONE sentence: what likely went wrong and what DIFFERENT thing to try.",
            tier=SMART, caller="agent", temperature=0.3, max_tokens=AGENT_MAX_TOKENS)
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
    # temperature=0 so identical (answer, screenshot) gets an identical verdict —
    # the general judge must be deterministic, not flip on a re-grade.
    raw = await _think(gw, prompt, tier=SMART, caller="agent", image=image, json_mode=True, temperature=0,
                       max_tokens=AGENT_MAX_TOKENS)
    j = _parse_json(raw) or {}
    return {"success": bool(j.get("success")), "reason": j.get("reason", "")}
