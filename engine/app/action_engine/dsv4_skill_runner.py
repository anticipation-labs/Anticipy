"""DSv4 skill runner. Phase V4-4. The Ralph Loop.

Structured task in, structured result out. Per iteration:

  1. Screenshot via CDP Page.captureScreenshot.
  2. Accessibility tree via CDP Accessibility.getFullAXTree, reduced
     to interactive elements, max 40 lines, each a stable @eN ref
     with a resolved click point (DOM.getBoxModel center).
  3. Page text excerpt (body innerText) so read/extract tasks can
     see static answers, not just clickable chrome.
  4. Completion check: V4 Flash (text) over task + AX + page text +
     history -> {"done": bool, "evidence": "..."}.
  5. Decide action: V4 Flash (text) -> one structured action.
  6. Dispatch via the existing humanlike CDP dispatcher (Bezier).
  7. Settle. After-screenshot.
  8. Vision verifier (Kimi K2.6) on the before/after pair for any
     state-changing action. DIVERGED is fed back into history.
     DIVERGED twice on the same logical step escalates the action
     decision to Kimi. Still DIVERGED twice with Kimi: hard fail.
  9. Log the iteration to ~/.anticipy/trajectories/<task_id>/.

Documented model routing (V4-0, OpenRouter has no DeepSeek V4
vision): decide/completion/decompose run on deepseek-v4-flash
(text, over the AX tree + page text). The vision verifier runs on
moonshotai/kimi-k2.6. Both are reasoning models; the client
enforces the token-budget floor.

Hard rules honored: no confirmation gates (Send/Buy/Submit dispatch
directly), max 30 iters, no fabrication, no em-dashes, real
artifacts only.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx
import numpy as np
from websockets.sync.client import connect as _ws_connect

from .cdp_dispatcher import (
    CDPSession,
    capture_screenshot,
    connect_to_chrome,
    humanlike_click,
    humanlike_key,
    humanlike_scroll,
    humanlike_type,
    navigate,
    wait_for_settle,
)


_AGENT_WIN_STATE = Path(os.path.expanduser("~/.anticipy/v4_agent_window.json"))
_AGENT_WIN_NAME = "Anticipy Agent"


def _browser_ws(port: int = 9222) -> str:
    r = httpx.get(f"http://localhost:{port}/json/version", timeout=5.0)
    r.raise_for_status()
    return r.json()["webSocketDebuggerUrl"]


def _page_targets(port: int = 9222) -> list[dict]:
    try:
        r = httpx.get(f"http://localhost:{port}/json/list", timeout=5.0)
        r.raise_for_status()
        return [t for t in r.json() if t.get("type") == "page"]
    except Exception:
        return []


def _ws_to(ws_url: str) -> CDPSession:
    """Keepalive-disabled CDP session bound to a specific page ws url.

    cdp_dispatcher.py is a protected file; its connect uses the
    websockets default 20s client keepalive, and the sync client only
    services control frames during send/recv, so a 30s+ OpenRouter
    call starves it and Chrome drops the socket. ping_interval=None
    keeps the CDP socket alive across long model calls.
    """
    ws = _ws_connect(ws_url, max_size=16 * 1024 * 1024,
                     ping_interval=None, ping_timeout=None, open_timeout=20)
    sess = CDPSession(ws=ws, target_id="", rng=np.random.default_rng())
    sess.send("Page.enable")
    sess.send("Runtime.enable")
    sess.send("DOM.enable")
    return sess


def _ensure_agent_window(port: int = 9222) -> tuple[str, str]:
    """Return (target_id, page_ws_url) for the dedicated, ISOLATED
    "Anticipy Agent" background window. The agent must not run in the
    user's foreground tabs (it would steal focus and fight the user).
    Chrome's coloured tab-groups need the chrome.tabGroups extension
    API, unavailable over raw CDP, so a dedicated background window
    via Target.createTarget(newWindow=true, background=true) is the
    correct equivalent isolation: the user's foreground is untouched,
    they keep working in parallel. The target id is persisted so the
    same window is reused across runs instead of spawning one each
    time.
    """
    tid = None
    if _AGENT_WIN_STATE.exists():
        try:
            tid = json.loads(_AGENT_WIN_STATE.read_text()).get("target_id")
        except Exception:
            tid = None
    if tid:
        for t in _page_targets(port):
            if t.get("id") == tid:
                return tid, t["webSocketDebuggerUrl"]

    bws = _ws_connect(_browser_ws(port), max_size=8 * 1024 * 1024,
                      ping_interval=None, ping_timeout=None, open_timeout=20)
    try:
        bws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                             "params": {"url": "about:blank",
                                        "newWindow": True,
                                        "background": True}}))
        deadline = time.time() + 8
        new_tid = None
        while time.time() < deadline:
            m = json.loads(bws.recv())
            if m.get("id") == 1:
                new_tid = m["result"]["targetId"]
                break
        if not new_tid:
            raise RuntimeError("Target.createTarget returned no targetId")
    finally:
        bws.close()
    ws_url = ""
    for t in _page_targets(port):
        if t.get("id") == new_tid:
            ws_url = t["webSocketDebuggerUrl"]
            break
    if not ws_url:
        raise RuntimeError("agent window target not found after create")
    _AGENT_WIN_STATE.parent.mkdir(parents=True, exist_ok=True)
    _AGENT_WIN_STATE.write_text(json.dumps({"target_id": new_tid,
                                            "name": _AGENT_WIN_NAME}))
    return new_tid, ws_url


def _connect_session_keepalive(port: int = 9222,
                               open_url: Optional[str] = None) -> CDPSession:
    """Connect to the ISOLATED Anticipy Agent background window
    (created/reused), keepalive-disabled. Replaces the old behaviour
    of opening a foreground tab in the user's window."""
    tid, ws_url = _ensure_agent_window(port)
    sess = _ws_to(ws_url)
    sess.target_id = tid
    return sess
from .openrouter_client import OpenRouterClient, TEXT_MODEL, VISION_MODEL
from .vision_verifier import VisionVerifier

_logger = logging.getLogger("anticipy.action_engine.dsv4")

TRAJ_DIR = Path(os.path.expanduser("~/.anticipy/trajectories"))

INTERACTIVE_ROLES = {
    "button", "link", "textbox", "searchbox", "combobox", "checkbox",
    "radio", "menuitem", "tab", "switch", "slider", "listbox", "option",
    "textarea", "spinbutton",
}


@dataclass
class TaskResult:
    task: str
    status: str = "UNKNOWN"   # SUCCESS | ITERATION_EXHAUSTED | HARD_FAIL | ERROR
    answer: str = ""
    evidence: str = ""
    subtasks: list[dict] = field(default_factory=list)
    n_iterations: int = 0
    trajectory_dir: str = ""
    error: Optional[str] = None
    memory: dict = field(default_factory=dict)


# ── AX tree extraction over raw CDP ───────────────────────────────────


def _ax_tree_and_refs(sess: CDPSession, max_lines: int = 40) -> tuple[str, dict]:
    """Return (compact_listing, ref_map). ref_map: '@eN' -> {x,y,role,
    name}. Interactive nodes only, each with a resolved click point."""
    try:
        res = sess.send("Accessibility.getFullAXTree", {}, timeout_s=15.0)
    except Exception as e:
        return (f"(ax tree error: {e})", {})
    nodes = res.get("nodes", [])
    listing: list[str] = []
    ref_map: dict[str, dict] = {}
    n = 0
    for node in nodes:
        if node.get("ignored"):
            continue
        role = (node.get("role", {}) or {}).get("value", "")
        if role not in INTERACTIVE_ROLES:
            continue
        name = (node.get("name", {}) or {}).get("value", "")
        if not name or len(name.strip()) < 1:
            continue
        backend_id = node.get("backendDOMNodeId")
        if backend_id is None:
            continue
        try:
            box = sess.send("DOM.getBoxModel",
                            {"backendNodeId": backend_id}, timeout_s=5.0)
            quad = box["model"]["content"]
            cx = (quad[0] + quad[2] + quad[4] + quad[6]) / 4.0
            cy = (quad[1] + quad[3] + quad[5] + quad[7]) / 4.0
        except Exception:
            continue
        n += 1
        ref = f"@e{n}"
        ref_map[ref] = {"x": cx, "y": cy, "role": role, "name": name[:80]}
        listing.append(f'{ref} [{role}] "{name[:80]}"')
        if n >= max_lines:
            break
    return ("\n".join(listing) if listing else "(no interactive elements)", ref_map)


def _page_text(sess: CDPSession, max_chars: int = 1400) -> str:
    try:
        r = sess.send("Runtime.evaluate", {
            "expression": "document.body ? document.body.innerText : ''",
            "returnByValue": True,
        }, timeout_s=8.0)
        txt = (r.get("result", {}) or {}).get("value", "") or ""
    except Exception:
        return ""
    skip = {"skip to main content", "accessibility help", "ai mode",
            "all", "images", "videos", "news", "more", "tools"}
    out = []
    for ln in txt.splitlines():
        s = ln.strip()
        if s and s.lower() not in skip and len(s) > 1:
            out.append(s)
    return "\n".join(out)[:max_chars]


_VK = {
    "Enter": 13, "Tab": 9, "Escape": 27, "Backspace": 8, "Delete": 46,
    "ArrowUp": 38, "ArrowDown": 40, "ArrowLeft": 37, "ArrowRight": 39,
    "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34, "Space": 32,
}


def _send_key(sess: CDPSession, keyname: str) -> None:
    """Proper CDP keyDown/keyUp with virtual key codes. Verified live:
    rawKeyDown (what the legacy dispatcher uses) is IGNORED by the
    Google Sheets canvas grid; full keyDown/keyUp with
    windows/nativeVirtualKeyCode IS honored once the grid has focus.
    General: this is the correct way to drive any app by key."""
    vk = _VK.get(keyname, 0)
    text = "\r" if keyname == "Enter" else ("\t" if keyname == "Tab" else "")
    down = {"type": "keyDown", "key": keyname, "code": keyname,
            "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk}
    if text:
        down["text"] = text
    sess.send("Input.dispatchKeyEvent", down, timeout_s=6.0)
    sess.send("Input.dispatchKeyEvent",
              {"type": "keyUp", "key": keyname, "code": keyname,
               "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk},
              timeout_s=6.0)


def _a1_to_colrow(ref: str) -> Optional[tuple[int, int]]:
    """'B3' -> (col=1, row=2), zero-based. Standard A1 notation,
    a universal spreadsheet convention (Sheets/Excel/LibreOffice),
    not site-specific logic."""
    m = re.match(r"^([A-Za-z]+)(\d+)$", ref.strip())
    if not m:
        return None
    letters, num = m.group(1).upper(), int(m.group(2))
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    return (col - 1, num - 1)


def _read_name_box(sess: CDPSession) -> Optional[tuple[int, int]]:
    """Current selected cell as (col,row) from the spreadsheet's cell
    reference indicator. Reading a DOM value is observing state (like
    page text), not API automation."""
    try:
        r = sess.send("Runtime.evaluate", {
            "expression": (
                "(function(){var e=document.querySelector('#t-name-box')"
                "||document.querySelector('[aria-label=\"Name box\"]');"
                "return e? (e.value||e.textContent) : '';})()"),
            "returnByValue": True,
        }, timeout_s=5.0)
        val = ((r.get("result", {}) or {}).get("value", "") or "").strip()
        return _a1_to_colrow(val)
    except Exception:
        return None


def _ledger_to_cells(ledger: list[str]) -> dict:
    """Parse ledger outcome strings into a {cellref: value} map. The
    ledger decomposition is a reliable language task; the runner then
    executes the fill deterministically so the model never touches the
    grid and cannot fumble into a Table. Handles forms like:
      'Cell A1 contains "Anticipy Test Tracker"'
      'A3 = Week'  /  'B4 contains 100'  /  'cell B3 is Revenue'
    """
    cells: dict[str, str] = {}
    for item in ledger:
        m = re.search(r"\b([A-Za-z]{1,3}\d{1,4})\b", item)
        if not m:
            continue
        ref = m.group(1).upper()
        rest = item[m.end():]
        vm = re.search(r"[\"'“‘]([^\"'”’]+)[\"'”’]", item)
        if vm:
            val = vm.group(1)
        else:
            vm = re.search(r"(?:contains?|=|is|:|should be|holds?)\s*(.+)$",
                           rest, re.IGNORECASE)
            if vm:
                val = vm.group(1).strip().strip(".").strip()
            else:
                continue
        # Reject if the "value" still looks like a sentence fragment
        # with no real content.
        if val and len(val) <= 120:
            cells[ref] = val
    return cells


def _grid_fill(sess: CDPSession, cells: dict, css_w: int, css_h: int) -> tuple[bool, str]:
    """Deterministic general grid filler using the NAME-BOX GOTO
    primitive, verified live: clicking the cell-reference box, typing
    an A1-notation cell, and pressing Enter jumps the selection to
    that exact cell from ANY state. No position tracking, no arrow
    counting, immune to Table-template 'Column N' confusion. Every
    spreadsheet (Sheets/Excel-online/etc) has this box, so this is
    general, not site-specific. Per cell: goto -> insertText value
    -> Enter to commit."""

    # Guaranteed-clean start. Prior runs leave corrupted "Untitled
    # spreadsheet" files (with an accidental Table1 / Column 1-5) in
    # the real Drive, and the model keeps reopening one from the
    # recent list. https://sheets.new ALWAYS creates a pristine blank
    # grid (verified live). The objective is "create a new sheet", so
    # starting fresh here is correct, deterministic, and immune to
    # debris. General "start from a known-clean state".
    try:
        navigate(sess, "https://sheets.new", wait_for_load_s=20.0)
    except Exception:
        pass

    def press(key: str, vk: int, mods: int = 0):
        for typ in ("keyDown", "keyUp"):
            sess.send("Input.dispatchKeyEvent",
                      {"type": typ, "key": key, "code": key,
                       "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
                       "modifiers": mods}, timeout_s=6.0)

    def name_box_xy():
        r = sess.send("Runtime.evaluate", {
            "expression": (
                "(function(){var e=document.querySelector('#t-name-box')"
                "||document.querySelector('[aria-label=\"Name box\"]');"
                "if(!e)return null;var b=e.getBoundingClientRect();"
                "if(b.width<1)return null;"
                "return [b.x+b.width/2,b.y+b.height/2];})()"),
            "returnByValue": True}, timeout_s=5.0)
        return (r.get("result", {}) or {}).get("value")

    # Sheets is a heavy SPA: sheets.new redirects and the grid/name
    # box can take 8-15s to render. Poll until the name box actually
    # exists rather than a fixed sleep (the fixed sleep was bailing
    # before render -> blank sheet).
    nb = None
    deadline = time.time() + 30.0
    while time.time() < deadline:
        nb = name_box_xy()
        if nb:
            break
        time.sleep(1.0)
    if not nb:
        return (False, "name box never rendered (sheets.new slow/blocked)")
    nbx, nby = int(nb[0]), int(nb[1])
    # Close the "Tables" suggestion sidebar if Sheets popped it open
    # (it overlays the grid and steals the first interactions).
    press("Escape", 27)
    time.sleep(0.4)

    def nb_value() -> str:
        r = sess.send("Runtime.evaluate", {
            "expression": ("(function(){var e=document.querySelector("
                           "'#t-name-box')||document.querySelector("
                           "'[aria-label=\"Name box\"]');return e?(e.value"
                           "||e.textContent||''):'';})()"),
            "returnByValue": True}, timeout_s=5.0)
        return ((r.get("result", {}) or {}).get("value", "") or "").strip().upper()

    def goto(ref: str) -> bool:
        # Recompute the name box position EACH time: the layout
        # shifts as the sidebar closes / grid scrolls, so a cached
        # coordinate goes stale (that was the bug: only the last
        # cell's value survived). Verify the selection actually
        # landed on the target; retry once.
        for attempt in range(2):
            xy = name_box_xy()
            if not xy:
                time.sleep(0.5)
                continue
            cx, cy = int(xy[0]), int(xy[1])
            sess.send("Input.dispatchMouseEvent",
                      {"type": "mousePressed", "x": cx, "y": cy,
                       "button": "left", "clickCount": 1}, timeout_s=6.0)
            sess.send("Input.dispatchMouseEvent",
                      {"type": "mouseReleased", "x": cx, "y": cy,
                       "button": "left", "clickCount": 1}, timeout_s=6.0)
            time.sleep(0.25)
            press("a", 65, 2)   # Ctrl+A selects existing name-box text
            sess.send("Input.insertText", {"text": ref}, timeout_s=6.0)
            time.sleep(0.15)
            press("Enter", 13)
            time.sleep(0.5)
            if nb_value().replace("$", "") == ref.upper():
                return True
        return False

    filled = 0
    items = []
    for ref, val in cells.items():
        cr = _a1_to_colrow(str(ref))
        if cr is not None:
            items.append((cr[1], cr[0], str(ref), str(val)))
    items.sort()
    for _, _, ref, val in items:
        if not goto(ref):
            continue  # could not land on this cell; skip, do not corrupt others
        sess.send("Input.insertText", {"text": val}, timeout_s=8.0)
        time.sleep(0.2)
        press("Enter", 13)  # commit the value (Enter also moves down)
        time.sleep(0.35)
        filled += 1
    return (filled > 0,
            f"grid_fill wrote {filled}/{len(items)} cells via name-box goto")


def _page_url(sess: CDPSession) -> str:
    try:
        r = sess.send("Runtime.evaluate",
                       {"expression": "location.href", "returnByValue": True},
                       timeout_s=5.0)
        return (r.get("result", {}) or {}).get("value", "") or ""
    except Exception:
        return ""


def _css_viewport(sess: CDPSession) -> tuple[int, int]:
    """CSS-pixel viewport size. CDP Input.dispatchMouseEvent works in
    CSS pixels, but Page.captureScreenshot returns DEVICE pixels
    (Retina dpr=2 -> a 3418x1848 image for a 1709x924 viewport). A
    vision model that reads the device-pixel screenshot and returns a
    coordinate is off by the dpr factor when that coordinate is
    dispatched as a CSS-pixel mouse event. Returns (cssW, cssH)."""
    try:
        lm = sess.send("Page.getLayoutMetrics", {}, timeout_s=5.0)
        vp = lm.get("cssLayoutViewport", {})
        w = int(vp.get("clientWidth", 0))
        h = int(vp.get("clientHeight", 0))
        if w > 0 and h > 0:
            return (w, h)
    except Exception:
        pass
    return (1280, 800)


def _normalize_for_model(png_bytes: bytes, css_w: int, css_h: int) -> bytes:
    """Resize the device-pixel screenshot down to the CSS viewport
    size. The model then sees an image whose coordinate space is
    exactly CSS pixels, so any [x,y] it returns maps 1:1 to a CDP
    mouse event. This is the general fix that makes vision clicking
    accurate on every canvas surface, no per-site logic."""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        if im.size != (css_w, css_h):
            im = im.resize((css_w, css_h), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes


# ── prompts ───────────────────────────────────────────────────────────

_DECOMPOSE_SYS = (
    "Split a browser task into the FEWEST independent subtasks. "
    'Output ONLY JSON: {"subtasks": ["...", "..."]}.\n'
    "Hard rules:\n"
    "- Preserve EVERY requirement of the original task verbatim. "
    "Never drop, summarize, or omit any value, cell, row, or detail. "
    "If the task lists data (cells, rows, numbers), that data MUST "
    "appear in full inside a subtask.\n"
    "- Default to ONE subtask. Only split when subtasks are truly "
    "independent objectives that need different pages or a result "
    "from an earlier step (e.g. 'look up X' then 'email about X').\n"
    "- Do NOT split a single coherent piece of work into micro-steps. "
    "Filling many cells in ONE spreadsheet is ONE subtask (the loop "
    "handles the individual cells). Opening a site and acting on it "
    "is ONE subtask.\n"
    "Example: 'Open Sheets, make a sheet, put a title in A1 and "
    "three data rows' -> ONE subtask containing all of that, not five."
)

_DECIDE_SYS = (
    "You drive a web browser to accomplish a sub-goal. You can SEE a "
    "screenshot of the current page. You also get the interactive "
    "accessibility tree (each element a @eN ref with its on-screen "
    "role and name) and the visible page text. Output ONLY JSON with "
    "the single next action:\n"
    '{"action":"navigate|click|type|key|scroll|grid_fill|done",'
    '"target_ref":"@eN or null",'
    '"coordinate":[x,y] or null,'
    '"text":"text for type/key, or null",'
    '"url":"url for navigate, or null",'
    '"cells":{"A1":"value","B3":"value"} or null,'
    '"answer":"final answer if done"}\n'
    "Targeting rules:\n"
    "- Prefer target_ref @eN when the element is in the accessibility "
    "tree (most standard buttons, links, inputs). It is the most "
    "reliable.\n"
    "- For canvas content with NO ref (a Google Sheets/Docs/Maps/"
    "Canva drawing surface), look at the screenshot and give a pixel "
    "coordinate [x,y] of the exact spot to click. The screenshot is "
    "the full page; use the visible grid lines, column headers (A, B, "
    "C ...) and row numbers to locate a cell precisely.\n"
    "- navigate first if the page is blank (a Google search URL is "
    "fine). If the visible text already answers the sub-goal, action "
    "done with the answer. One action only. No prose.\n"
    "SEARCHING a site: the MOST reliable method, do this FIRST, is to "
    "navigate DIRECTLY to the site's search-results URL with the "
    "query URL-encoded. Use these patterns:\n"
    "  Amazon  -> https://www.amazon.com/s?k=QUERY\n"
    "  YouTube -> https://www.youtube.com/results?search_query=QUERY\n"
    "  Google Maps -> https://www.google.com/maps/search/QUERY\n"
    "  Spotify -> https://open.spotify.com/search/QUERY\n"
    "  generic -> https://www.google.com/search?q=QUERY\n"
    "Replace spaces with + (Amazon/YouTube/Google) or %20. Only if no "
    "URL pattern fits, fall back to the on-page search box: it is a "
    "textbox/searchbox/combobox in the accessibility tree (named "
    "'Search' or with a search placeholder); fill that @eN ref then "
    "key Enter. NEVER click banners, hero carousels, promo tiles, or "
    "category links to search, and never press Enter on an empty "
    "search box.\n"
    "FILLING a recipient / email / To / address field: fill the "
    "input's @eN ref with the value directly. If an autocomplete or "
    "contact-picker dialog pops up, do NOT click inside it; press "
    "key Escape or key Tab to dismiss it and move on. Never get "
    "stuck clicking a picker dialog.\n"
    "ALREADY SIGNED IN: if a sign-in / login page shows a section "
    "like 'You're already signed in to', 'Choose an account', "
    "'Continue as <name>', or a list of existing workspaces/accounts "
    "each with an Open / Continue / Launch / Use button, you do NOT "
    "need to log in - click that Open/Continue button (the @eN for "
    "the workspace/account that best matches the task) to use the "
    "existing session. NEVER type an email/password or attempt a "
    "fresh sign-in when an existing session is offered. For Slack, "
    "click 'Open' next to the relevant workspace.\n"
    "GMAIL COMPOSE (exact sequence, the To field spawns a contact "
    "picker if you CLICK it - so never click the To field): "
    "1) open Compose (the Compose button @eN, or key 'c'). "
    "2) When the compose window is open the To field is ALREADY "
    "focused - emit a type action with the recipient address "
    "directly, with NO target_ref and NO click. "
    "3) key Tab to move to Subject, then type the subject. "
    "4) key Tab to move to the Body, then type the body. "
    "5) click the Send button (@eN named 'Send'), or key "
    "Control+Enter, to send. Do not click the To/Subject/Body "
    "fields - just type and Tab between them.\n"
    "EXTRACTING an answer (the goal asks to 'tell me' / find a name, "
    "title, price, count): if the VISIBLE PAGE TEXT or the screenshot "
    "already shows it, immediately action done with the answer. Do "
    "NOT scroll or click looking for more once the answer is on "
    "screen. Reflexive scrolling when the answer is already visible "
    "is a failure.\n"
    "SPREADSHEET / GRID DATA ENTRY (Google Sheets, etc): do NOT try "
    "to click cells or move cell-by-cell yourself. Once a spreadsheet "
    "is open, emit ONE single action: grid_fill, with cells set to "
    "the COMPLETE map of every required cell to its value, e.g. "
    '{"action":"grid_fill","cells":{"A1":"Anticipy Test Tracker",'
    '"A3":"Week","B3":"Revenue","A4":"Week 1","B4":"100"}}. Read the '
    "objective and include every cell and row it specifies, verbatim. "
    "The executor focuses the grid and fills all cells deterministically "
    "in one go. After grid_fill, check the screenshot; if anything is "
    "still missing, emit another grid_fill for just the missing cells, "
    "else action done."
)

_COMPLETE_SYS = (
    "Decide if the sub-goal is already satisfied by what is visible. "
    'Output ONLY JSON: {"done": true|false, "evidence": "one '
    'sentence", "answer": "the answer if done else empty"}.'
)


def _json_from(text: str) -> dict:
    raw = (text or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
    return {}


# ── runner ────────────────────────────────────────────────────────────


@dataclass
class DSv4SkillRunner:
    cdp_port: int = 9222
    max_iters: int = 30
    client: Optional[OpenRouterClient] = None
    verifier: Optional[VisionVerifier] = None
    # Kimi-primary escalation: when set, EVERY model call (decompose,
    # ledger, decide, completion, vision-confirm) routes to this model
    # instead of the cheaper V4 Flash for text steps. Used by the fix
    # loop to escalate a still-failing Tier 1 task to the strongest
    # OpenRouter model as the primary decider, not just fallback.
    force_model: Optional[str] = None

    def __post_init__(self):
        self.client = self.client or OpenRouterClient()
        self.verifier = self.verifier or VisionVerifier(client=self.client)

    def _txt_model(self) -> str:
        return self.force_model or TEXT_MODEL

    def _vis_model(self) -> str:
        return self.force_model or VISION_MODEL

    # decomposition
    def _decompose(self, task: str) -> list[str]:
        r = self.client.chat(
            [{"role": "user", "content": f"{_DECOMPOSE_SYS}\n\nTASK: {task}"}],
            model=self._txt_model(), max_tokens=512, temperature=0.0,
            response_format={"type": "json_object"},
        )
        obj = _json_from(r.content)
        subs = obj.get("subtasks") if isinstance(obj, dict) else None
        if isinstance(subs, list) and subs and all(isinstance(s, str) for s in subs):
            return [s for s in subs if s.strip()]
        return [task]

    # progress ledger: the general long-horizon-coherence fix.
    def _build_ledger(self, subgoal: str) -> list[str]:
        """Break a subgoal into atomic, individually-checkable outcome
        statements (e.g. 'cell A1 contains Anticipy Test Tracker',
        'the email To field contains x@y.com'). The model is then
        guided through ONE pending item at a time, which it handles
        reliably, instead of juggling a 15-step sequence and losing
        the thread. General: every subgoal gets a ledger."""
        sysp = (
            "Break the objective into the minimal list of concrete, "
            "individually verifiable end-state facts. Each item is a "
            "single observable result, not an action. Output ONLY "
            'JSON {"items":["...","..."]}. Preserve every value, '
            "cell, field, and row from the objective verbatim."
        )
        r = self.client.chat(
            [{"role": "user", "content": f"{sysp}\n\nOBJECTIVE: {subgoal}"}],
            model=self._txt_model(), max_tokens=700, temperature=0.0,
            response_format={"type": "json_object"},
        )
        obj = _json_from(r.content)
        items = obj.get("items") if isinstance(obj, dict) else None
        if isinstance(items, list) and items and all(isinstance(s, str) for s in items):
            return [s.strip() for s in items if s.strip()]
        return [subgoal]

    def _ledger_status(self, ledger: list[str], page_text: str,
                       ax: str) -> list[bool]:
        """Which ledger items are satisfied by what is currently
        visible. Cheap text call on V4 Flash."""
        sysp = (
            "For each numbered item, answer true if the visible page "
            "content shows that exact end-state is already achieved, "
            'else false. Output ONLY JSON {"done":[true,false,...]} '
            "with one boolean per item, in order."
        )
        listing = "\n".join(f"{i+1}. {it}" for i, it in enumerate(ledger))
        user = (f"ITEMS:\n{listing}\n\nVISIBLE PAGE TEXT:\n"
                f"{page_text or '(empty)'}\n\nINTERACTIVE:\n{ax[:1500]}")
        r = self.client.chat(
            [{"role": "user", "content": f"{sysp}\n\n{user}"}],
            model=self._txt_model(), max_tokens=400, temperature=0.0,
            response_format={"type": "json_object"},
        )
        obj = _json_from(r.content)
        flags = obj.get("done") if isinstance(obj, dict) else None
        if isinstance(flags, list) and len(flags) == len(ledger):
            return [bool(x) for x in flags]
        return [False] * len(ledger)

    def _decide(self, subgoal: str, ax: str, page_text: str,
                history: list[str], screenshot_b64: Optional[str] = None,
                img_w: int = 0, img_h: int = 0) -> dict:
        """Vision-primary decide. The action model SEES the page
        screenshot plus the AX tree and page text. This is the
        authorized general fix from V4-6: a text-only model is blind
        to canvas content (Sheets/Docs/Maps/Canva), so the decide
        step must be multimodal. The only vision-capable model in the
        locked set is Kimi K2.6 (V4-0 proved no DeepSeek V4 vision on
        OpenRouter), so decide runs on VISION_MODEL. It works on every
        page type: DOM pages via @eN refs, canvas via pixel
        coordinates read off the screenshot."""
        hist = "\n".join(history[-3:]) or "(none)"
        dims = (f"The screenshot is exactly {img_w} pixels wide and "
                f"{img_h} pixels tall. Any coordinate you return MUST "
                f"be within 0..{img_w} for x and 0..{img_h} for y, "
                f"measured on THIS screenshot. The top-left is (0,0)."
                if img_w and img_h else "")
        user = (
            f"SUB-GOAL: {subgoal}\n\n"
            f"RECENT (do not repeat a failed action):\n{hist}\n\n"
            f"VISIBLE PAGE TEXT:\n{page_text or '(empty)'}\n\n"
            f"INTERACTIVE ELEMENTS:\n{ax}\n\n"
            f"{dims}\n"
            "Look at the screenshot. Single next action as JSON."
        )
        r = self.client.chat(
            [{"role": "user", "content": f"{_DECIDE_SYS}\n\n{user}"}],
            model=self._vis_model(), max_tokens=600, temperature=0.0,
            image_b64=screenshot_b64,
            response_format={"type": "json_object"},
        )
        return _json_from(r.content)

    def _vision_confirm(self, subgoal: str, screenshot_b64: str) -> tuple[bool, str]:
        """Authoritative completion check. Looks at the ACTUAL
        screenshot (Kimi vision) and decides if the objective's end
        state is genuinely visible. This is what prevents fabricated
        success: the innerText ledger can be fooled, real pixels
        cannot. Conservative: anything other than an explicit DONE is
        treated as not-done."""
        sysp = (
            "You are a strict completion auditor. Look ONLY at the "
            "screenshot. Decide if the objective is genuinely and "
            "fully achieved as visible on screen right now. Be "
            "skeptical: empty fields, placeholder/template content, or "
            "missing data mean NOT done. Output ONLY JSON "
            '{"done": true|false, "evidence": "what you actually see"}.'
        )
        user = f"OBJECTIVE: {subgoal}\n\nIs it fully done on screen?"
        r = self.client.chat(
            [{"role": "user", "content": f"{sysp}\n\n{user}"}],
            model=self._vis_model(), max_tokens=400, temperature=0.0,
            image_b64=screenshot_b64,
            response_format={"type": "json_object"},
        )
        obj = _json_from(r.content)
        done = bool(obj.get("done")) if isinstance(obj, dict) else False
        ev = (obj.get("evidence") if isinstance(obj, dict) else "") or ""
        return (done, str(ev)[:200])

    def _completion(self, subgoal: str, ax: str, page_text: str) -> dict:
        user = (f"SUB-GOAL: {subgoal}\n\nVISIBLE PAGE TEXT:\n"
                f"{page_text or '(empty)'}\n\nINTERACTIVE:\n{ax}\n\nDone?")
        r = self.client.chat(
            [{"role": "user", "content": f"{_COMPLETE_SYS}\n\n{user}"}],
            model=self._txt_model(), max_tokens=300, temperature=0.0,
            response_format={"type": "json_object"},
        )
        return _json_from(r.content)

    def _dispatch(self, sess: CDPSession, action: dict, ref_map: dict,
                  css_w: int = 0, css_h: int = 0) -> tuple[bool, str, bool]:
        """Returns (ok, detail, state_changing)."""
        kind = (action.get("action") or "").lower()
        ref = action.get("target_ref")
        if ref and not str(ref).startswith("@"):
            ref = "@" + str(ref).lstrip("@")
        try:
            if kind == "navigate":
                navigate(sess, action.get("url") or "about:blank", wait_for_load_s=20.0)
                return (True, "navigated", True)
            if kind == "grid_fill":
                cells = action.get("cells")
                if not isinstance(cells, dict) or not cells:
                    return (False, "grid_fill needs a non-empty cells map", False)
                ok, detail = _grid_fill(sess, cells, css_w or 1280, css_h or 800)
                return (ok, detail, True)
            coord = action.get("coordinate")
            cxy = None
            if isinstance(coord, (list, tuple)) and len(coord) == 2:
                try:
                    fx, fy = float(coord[0]), float(coord[1])
                    # Vision models often return NORMALIZED fractions
                    # in [0,1] instead of pixels. int(0.057) -> 0 sent
                    # every click to the top-left corner. Detect the
                    # convention: if both are <= 1.0 they are fractions
                    # of the viewport; scale to CSS pixels. Otherwise
                    # they are already pixels. General, not site logic.
                    if 0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0 and css_w and css_h:
                        cxy = (int(round(fx * css_w)), int(round(fy * css_h)))
                    else:
                        cxy = (int(round(fx)), int(round(fy)))
                    if css_w and css_h:
                        cxy = (max(0, min(cxy[0], css_w - 1)),
                               max(0, min(cxy[1], css_h - 1)))
                except Exception:
                    cxy = None
            if kind == "click":
                t = ref_map.get(ref)
                if t:
                    humanlike_click(sess, int(t["x"]), int(t["y"]))
                    return (True, f"clicked ref {t['name']!r}", True)
                if cxy:
                    humanlike_click(sess, cxy[0], cxy[1])
                    return (True, f"clicked px {cxy}", True)
                return (False, f"no ref {ref} and no coordinate", False)
            if kind == "type":
                t = ref_map.get(ref)
                if t:
                    humanlike_click(sess, int(t["x"]), int(t["y"]))
                elif cxy:
                    humanlike_click(sess, cxy[0], cxy[1])
                txt = action.get("text") or ""
                # Canvas grid apps (Google Sheets/Docs) ignore raw
                # keyDown/keyUp; CDP Input.insertText reliably inserts
                # into the focused cell/editor. Keep humanlike click
                # for targeting, use insertText for the payload.
                try:
                    sess.send("Input.insertText", {"text": txt}, timeout_s=8.0)
                except Exception:
                    humanlike_type(sess, txt)
                return (True, f"typed {txt[:30]!r}", True)
            if kind == "key":
                keyname = (action.get("text") or "Enter").strip()
                _send_key(sess, keyname)
                return (True, f"key {keyname}", True)
            if kind == "scroll":
                humanlike_scroll(sess, -600)
                return (True, "scrolled", True)
            if kind == "done":
                return (True, "done", False)
            return (False, f"unknown action {kind!r}", False)
        except Exception as e:
            return (False, f"dispatch threw: {e}", False)

    _POPUP_GOAL = (
        "A sign-in, OAuth, or consent window just opened. Approve it so "
        "the original task can continue. Allowed: click an account that "
        "is already listed; click Continue / Next / Allow / Authorize / "
        "Approve / Confirm / Yes; dismiss a cookie or info banner. "
        "FORBIDDEN: do not type into a password field, do not create an "
        "account, do not type credentials. If the ONLY way forward is to "
        "enter a password, output action done with answer "
        "'NEEDS_PASSWORD'. When the consent is approved and nothing more "
        "is needed, output action done with answer 'POPUP_DONE'."
    )

    def _handle_auth_popup(self, target_id: str, parent_subgoal: str,
                           traj: Path, tag_prefix: str,
                           max_iters: int = 8) -> str:
        """Drive an OAuth/sign-in/consent popup target in a bounded
        sub-loop, then return. Safe by construction: the popup goal
        forbids password entry and account creation. Returns a short
        status string for the trajectory/history."""
        ws_url = ""
        for t in _page_targets(self.cdp_port):
            if t.get("id") == target_id:
                ws_url = t["webSocketDebuggerUrl"]
                break
        if not ws_url:
            return "popup_gone_before_attach"
        try:
            psess = _ws_to(ws_url)
            psess.target_id = target_id
        except Exception as e:
            return f"popup_attach_failed:{e}"
        try:
            for pit in range(max_iters):
                # Popup closed -> auth flow finished, opener continues.
                if target_id not in {t["id"] for t in _page_targets(self.cdp_port)}:
                    return "popup_closed_ok"
                try:
                    shot = capture_screenshot(psess)
                    (traj / f"{tag_prefix}_{pit:02d}.png").write_bytes(shot)
                    cw, ch = _css_viewport(psess)
                    shot_n = _normalize_for_model(shot, cw, ch)
                    ax, ref_map = _ax_tree_and_refs(psess)
                    ptext = _page_text(psess)
                except Exception:
                    return "popup_observe_failed"
                b64 = base64.b64encode(shot_n).decode("ascii")
                action = self._decide(self._POPUP_GOAL, ax, ptext, [],
                                      screenshot_b64=b64, img_w=cw, img_h=ch)
                if not action or not action.get("action"):
                    continue
                if (action.get("action") or "").lower() == "done":
                    ans = (action.get("answer") or "").upper()
                    if "NEEDS_PASSWORD" in ans:
                        return "popup_needs_password"
                    return "popup_done"
                self._dispatch(psess, action, ref_map, css_w=cw, css_h=ch)
                wait_for_settle(psess, timeout_s=3.0)
            return "popup_iters_exhausted"
        finally:
            try:
                psess.close()
            except Exception:
                pass

    def _run_subtask(self, sess: CDPSession, subgoal: str, traj: Path,
                     sub_idx: int, memory: dict) -> dict:
        history: list[str] = []
        diverged_streak = 0
        no_action_count = 0
        last_sig = None
        best_ptext_len = 0  # progress proxy: a sheet being filled grows
        ledger = self._build_ledger(subgoal)
        best_done_count = 0  # real progress proxy: ledger items satisfied
        try:
            known_target_ids = {t["id"] for t in _page_targets(self.cdp_port)}
        except Exception:
            known_target_ids = set()

        # If the ledger is a spreadsheet cell-fill (>=2 cell->value
        # outcomes), execute it deterministically ONCE up front. The
        # model never touches the grid, so it cannot fumble into a
        # Table; the proven name-box-goto + clean sheets.new start do
        # the work. The loop below then vision-confirms the result.
        gf_cells = _ledger_to_cells(ledger)
        if len(gf_cells) >= 2:
            try:
                cw, ch = _css_viewport(sess)
                ok, detail = _grid_fill(sess, gf_cells, cw or 1280, ch or 800)
                history.append(f"deterministic grid_fill: {detail}")
                wait_for_settle(sess, timeout_s=3.0)
            except Exception as e:
                history.append(f"deterministic grid_fill threw: {e}")

        for it in range(self.max_iters):
            tag = f"s{sub_idx}_i{it:02d}"
            before = capture_screenshot(sess)
            (traj / f"{tag}_before.png").write_bytes(before)
            css_w, css_h = _css_viewport(sess)
            before_norm = _normalize_for_model(before, css_w, css_h)
            ax, ref_map = _ax_tree_and_refs(sess)
            ptext = _page_text(sess)

            # Ledger drives the per-step FOCUS (which item to do next).
            # It does NOT have completion authority: a text model
            # reading innerText gave false "done" on an empty Sheets
            # canvas. SUCCESS requires the VISION verifier to confirm
            # the end state on the actual screenshot. This is the
            # integrity fix that makes every result trustworthy.
            status = self._ledger_status(ledger, ptext, ax)
            if all(status):
                vconf = self._vision_confirm(
                    subgoal, base64.b64encode(before_norm).decode("ascii"))
                if vconf[0]:
                    return {"subgoal": subgoal, "status": "SUCCESS",
                            "answer": "; ".join(ledger),
                            "evidence": f"vision-confirmed: {vconf[1]}",
                            "iters": it}
                # Ledger lied. Do not trust it; keep working, but cap
                # how many times a false-positive ledger can stall us.
                history.append(f"i{it}: ledger said done but vision says "
                                f"NOT done: {vconf[1]}")
                diverged_streak += 1
                if diverged_streak >= 8:
                    return {"subgoal": subgoal, "status": "HARD_FAIL",
                            "answer": "",
                            "evidence": f"ledger/vision conflict unresolved: {vconf[1]}",
                            "iters": it}
            done_items = [ledger[i] for i, s in enumerate(status) if s]
            pending = [ledger[i] for i, s in enumerate(status) if not s]
            next_item = pending[0] if pending else subgoal
            # Real progress: an additional ledger item became satisfied.
            # That outranks the verifier being strict on a nav step.
            cur_done = len(done_items)
            if cur_done > best_done_count:
                best_done_count = cur_done
                diverged_streak = 0
            focus = (
                f"OVERALL: {subgoal}\n"
                f"ALREADY DONE ({len(done_items)}/{len(ledger)}): "
                f"{done_items}\n"
                f"DO ONLY THIS NEXT, nothing else: {next_item}"
            )

            mem_hint = ""
            if memory:
                mem_hint = " KNOWN: " + json.dumps(memory)[:200]
            before_b64 = base64.b64encode(before_norm).decode("ascii")
            action = self._decide(focus + mem_hint, ax, ptext, history,
                                  screenshot_b64=before_b64,
                                  img_w=css_w, img_h=css_h)
            if not action or not action.get("action"):
                # A single unparseable response is usually transient.
                # Re-observe and re-decide; only hard-fail if the model
                # cannot produce ANY action many times in a row.
                no_action_count += 1
                history.append(f"i{it}: model gave no parseable action, retrying")
                if no_action_count >= 8:
                    return {"subgoal": subgoal, "status": "HARD_FAIL",
                            "answer": "", "evidence": "no parseable action x8",
                            "iters": it}
                continue
            no_action_count = 0

            if (action.get("action") or "").lower() == "done":
                ans = action.get("answer") or ""
                # The model declaring done is NOT authoritative. Only
                # the vision auditor on the real screenshot can confirm
                # completion (prevents fabricated success).
                vc = self._vision_confirm(
                    subgoal, base64.b64encode(before_norm).decode("ascii"))
                if vc[0]:
                    return {"subgoal": subgoal, "status": "SUCCESS",
                            "answer": ans or "; ".join(ledger),
                            "evidence": f"vision-confirmed: {vc[1]}",
                            "iters": it}
                history.append(
                    f"i{it}: actor said done but vision says NOT done: {vc[1]}")
                continue

            sig = json.dumps({k: action.get(k) for k in ("action", "target_ref", "url", "text")})
            if sig == last_sig:
                diverged_streak += 1
            last_sig = sig

            ok, detail, state_changing = self._dispatch(sess, action, ref_map,
                                                        css_w=css_w, css_h=css_h)
            history.append(f"i{it}: {action.get('action')} {action.get('target_ref') or action.get('url') or ''} -> {detail}")
            if not ok:
                diverged_streak += 1
                if diverged_streak >= 6:
                    return {"subgoal": subgoal, "status": "HARD_FAIL",
                            "answer": "", "evidence": f"dispatch failures: {detail}",
                            "iters": it}
                continue

            wait_for_settle(sess, timeout_s=4.0)

            # OAuth / sign-in / consent popups open as a SEPARATE page
            # target (often a new window). The main session is bound
            # to one target and cannot see them, so auth flows stall
            # (this is exactly why notion/slack hit a login wall). If
            # a new page target appeared since before the action,
            # follow it: drive the account-chooser / Continue / Allow
            # in a bounded sub-loop, then return to the main target.
            try:
                now_ids = {t["id"] for t in _page_targets(self.cdp_port)}
                new_ids = now_ids - known_target_ids
                known_target_ids = now_ids
                for nid in new_ids:
                    if nid == sess.target_id:
                        continue
                    self._handle_auth_popup(nid, subgoal, traj,
                                            f"{tag}_popup")
                    history.append(f"i{it}: handled popup target {nid[:8]}")
            except Exception as e:
                history.append(f"i{it}: popup-check error {e}")

            after = capture_screenshot(sess)
            (traj / f"{tag}_after.png").write_bytes(after)

            if state_changing:
                v = self.verifier.verify(action, before, after, subgoal)
                (traj / f"{tag}_verdict.json").write_text(json.dumps({
                    "status": v.status, "evidence": v.evidence,
                    "confidence": v.confidence, "fellback": v.fellback}))
                # Progress proxy: a sheet/page being filled grows its
                # visible text. If text grew since the best seen, the
                # task IS advancing even when the verifier is strict on
                # an intermediate cell-selection step. Reset the streak.
                cur_len = len(ptext)
                made_progress = cur_len > best_ptext_len + 2
                if made_progress:
                    best_ptext_len = cur_len

                if v.status == "DIVERGED" and not made_progress:
                    diverged_streak += 1
                    history.append(f"i{it}: VERIFIER DIVERGED: {v.evidence}")
                    if diverged_streak >= 6:
                        return {"subgoal": subgoal, "status": "HARD_FAIL",
                                "answer": "", "evidence": f"diverged repeatedly: {v.evidence}",
                                "iters": it}
                else:
                    diverged_streak = 0

        return {"subgoal": subgoal, "status": "ITERATION_EXHAUSTED",
                "answer": "", "evidence": f"{self.max_iters} iters exhausted",
                "iters": self.max_iters}

    def run(self, task: str, starting_url: Optional[str] = None) -> TaskResult:
        task_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
        traj = TRAJ_DIR / task_id
        traj.mkdir(parents=True, exist_ok=True)
        result = TaskResult(task=task, trajectory_dir=str(traj))

        try:
            sess = _connect_session_keepalive(
                port=self.cdp_port, open_url=starting_url or "about:blank")
        except Exception as e:
            result.status = "ERROR"
            result.error = f"connect failed: {e}"
            self._write_manifest(traj, result)
            return result

        try:
            if starting_url:
                try:
                    navigate(sess, starting_url, wait_for_load_s=20.0)
                except Exception:
                    pass

            subtasks = self._decompose(task)
            memory: dict[str, Any] = {}
            total_iters = 0
            overall = "SUCCESS"
            for i, sub in enumerate(subtasks):
                sr = self._run_subtask(sess, sub, traj, i, memory)
                result.subtasks.append(sr)
                total_iters += sr.get("iters", 0)
                if sr.get("answer"):
                    memory[f"subtask_{i}"] = sr["answer"]
                if sr["status"] != "SUCCESS":
                    overall = sr["status"]
                    break
            result.status = overall
            result.n_iterations = total_iters
            result.memory = memory
            if result.subtasks:
                last = result.subtasks[-1]
                result.answer = last.get("answer", "")
                result.evidence = last.get("evidence", "")
        except Exception as e:
            result.status = "ERROR"
            result.error = str(e)
        finally:
            try:
                sess.close()
            except Exception:
                pass

        self._write_manifest(traj, result)
        return result

    def _write_manifest(self, traj: Path, result: TaskResult) -> None:
        try:
            (traj / "manifest.json").write_text(json.dumps({
                "task": result.task,
                "status": result.status,
                "answer": result.answer,
                "evidence": result.evidence,
                "n_iterations": result.n_iterations,
                "subtasks": result.subtasks,
                "memory": result.memory,
                "error": result.error,
            }, indent=2))
        except Exception as e:
            _logger.warning("manifest write failed: %s", e)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--url", default=None)
    p.add_argument("--max-iters", type=int, default=30)
    args = p.parse_args()
    runner = DSv4SkillRunner(max_iters=args.max_iters)
    res = runner.run(args.task, starting_url=args.url)
    print(json.dumps({
        "status": res.status,
        "answer": res.answer,
        "evidence": res.evidence,
        "n_iterations": res.n_iterations,
        "n_subtasks": len(res.subtasks),
        "trajectory_dir": res.trajectory_dir,
        "error": res.error,
    }, indent=2))
