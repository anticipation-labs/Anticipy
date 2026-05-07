"""
Core execution loop for the Anticipy Action Engine.
Uses Browser Use framework for browser automation.
Receives a goal, drives the browser step-by-step, and streams status via callback.
"""

# NOTE: do NOT add `from __future__ import annotations` here. Browser Use's
# Controller registry inspects parameter annotations as live types
# (e.g. `param.annotation == BrowserSession`). PEP 563 turns annotations into
# strings and breaks that check, which silently disables every custom action.

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
import uuid
from typing import Callable, Awaitable
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from browser_use import Agent, BrowserSession, AgentHistoryList
from browser_use import Controller, ActionResult

from app.config import (
    MAX_STEPS,
    MAX_SECONDS,
    PROFILE_ENCRYPTION_KEY,
    BROWSER_PROFILE_BASE,
)
from app.safety import (
    check_blocked,
    block_reason,
    check_needs_confirmation,
    sanitize_input,
)
from app.planner import plan_task
from app.models import CostTracker
from app import messages as msg
from app import supabase_client

from cryptography.fernet import Fernet

logger = logging.getLogger("engine")

# Callback type: async function that sends a message dict to the client
SendFn = Callable[[dict], Awaitable[None]]


# ---------------------------------------------------------------------------
# Generic agent capabilities (no site-specific code).
#
# These are wrapped as Browser Use custom actions so the LLM-driven agent can
# reach for them when the default `input_text`/`click`/etc. don't work — e.g.
# React-controlled inputs that ignore programmatic value changes, canvas-only
# editors (Docs/Sheets) where there's no input element to click, shadow-DOM
# components where querySelector misses everything, and WebGL surfaces that
# only listen to native pointer events.
#
# All of them are intentionally generic. The agent's prompt (in
# _AGENT_SYSTEM_RULES) tells it WHEN to use which.
# ---------------------------------------------------------------------------


_AGENT_SYSTEM_RULES = """\
ADDITIONAL RULES (Anticipy):

1. Field completeness — before calling `done`, list every distinct piece of \
information the user explicitly asked for. If any item is missing, do another \
step to find it. Never silently drop a sub-field.

2. When `input_text` or `input` does not visibly change a field after one try \
(e.g. React-controlled inputs that snap back, autocomplete that swallows the \
value, stale element references), fall back to `force_type` with the same \
index. `force_type` writes via the native value setter and dispatches the \
events React/Vue listen for, then it works.

3. For canvas-only text surfaces (Google Docs/Sheets, Figma text), there is \
no input element to click into. After clicking the canvas to focus, use \
`canvas_type` to send the keystrokes via the keyboard. Do not try `input_text` \
on a `<canvas>` — it will fail.

4. If the page looks empty (no clickable elements extracted) but you can see \
content in the screenshot, the elements are probably inside a shadow root or \
WebGL surface. Use `pierce_query` to find an element by its visible text, or \
`canvas_pointer` to dispatch a real pointer event at a screen coordinate.

5. Never invent values. If a piece of information isn't on the current page \
or in the user's request, search for it.
"""


class _ForceTypeParams(BaseModel):
    """Args for force_type. At module scope so registry sees a real type."""
    index: int = Field(..., description="Element index from the page snapshot")
    text: str = Field(..., description="Text to type into the focused element")


class _CanvasTypeParams(BaseModel):
    text: str = Field(..., description="Text to send to the currently focused canvas/editor")


class _PierceQueryParams(BaseModel):
    visible_text: str = Field(..., description="Visible text inside the target element")
    role: str = Field("", description="Optional ARIA role hint, e.g. 'button', 'textbox'")


class _CanvasPointerParams(BaseModel):
    x: int = Field(..., description="Viewport X coordinate")
    y: int = Field(..., description="Viewport Y coordinate")
    button: str = Field("left", description="left | right | middle")
    click_count: int = Field(1, description="1 for click, 2 for double-click")


# JS that writes a value via the native HTMLInputElement / HTMLTextAreaElement
# setter and dispatches the events React/Vue/Angular listen for.  This bypasses
# the React-controlled-input problem (frameworks override the value setter on
# the instance, so `el.value = "x"` is a no-op as far as their state goes).
_REACT_SAFE_SET_VALUE = r"""
function(v) {
  try { this.focus(); } catch (_) {}
  var proto = (this instanceof HTMLTextAreaElement)
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  var p = Object.getOwnPropertyDescriptor(proto, 'value');
  if (p && p.set) { p.set.call(this, v); } else { this.value = v; }
  this.dispatchEvent(new Event('input',  { bubbles: true }));
  this.dispatchEvent(new Event('change', { bubbles: true }));
  try {
    this.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter' }));
  } catch (_) {}
  return true;
}
""".strip()


# Recursive querySelector that pierces open shadow roots AND same-origin
# iframes.  Closed shadow roots are made open by the attachShadow patch we
# install at session start (see _SHADOW_OPEN_PATCH below); for the rare site
# that re-freezes attachShadow, fall back to canvas_pointer + vision.
_SHADOW_PIERCE_QUERY = r"""
(visibleText, role) => {
  const target = (visibleText || '').trim().toLowerCase();
  const candidates = [];
  function walk(root) {
    if (!root) return;
    let all;
    try { all = root.querySelectorAll('*'); } catch(_) { return; }
    for (const el of all) {
      const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
      if (txt && (txt === target || (txt.length < 200 && txt.includes(target)))) {
        if (!role || (el.getAttribute('role') || '').toLowerCase() === role.toLowerCase()) {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) {
            candidates.push({
              x: Math.round(r.left + r.width / 2),
              y: Math.round(r.top + r.height / 2),
              tag: el.tagName,
              textLen: txt.length,
            });
          }
        }
      }
      if (el.shadowRoot) walk(el.shadowRoot);
      if (el.tagName === 'IFRAME') {
        try { if (el.contentDocument) walk(el.contentDocument); } catch(_) {}
      }
    }
  }
  walk(document);
  candidates.sort((a, b) => a.textLen - b.textLen);
  return candidates[0] || null;
}
""".strip()


# Force every shadow root to be open. Must be installed via
# Page.addScriptToEvaluateOnNewDocument BEFORE any page script runs, so the
# constructor of every custom element sees our patched attachShadow.
_SHADOW_OPEN_PATCH = r"""
(() => {
  try {
    const orig = Element.prototype.attachShadow;
    Element.prototype.attachShadow = function (init) {
      const opts = Object.assign({}, init || {}, { mode: 'open' });
      return orig.call(this, opts);
    };
  } catch (_) {}
})();
""".strip()


# JS that locates the offscreen text-event-target iframe used by canvas
# editors (Docs / Sheets / Slides) and focuses its inner contenteditable.
# Returns true if a target was found and focused.
_FOCUS_DOCS_EDIT_TARGET = r"""
(() => {
  function findIn(doc) {
    if (!doc) return false;
    let f;
    try { f = doc.querySelector('iframe.docs-texteventtarget-iframe'); } catch(_) {}
    if (f) {
      try {
        const inner = f.contentDocument && f.contentDocument.querySelector('[contenteditable="true"]');
        if (inner) { inner.focus(); return true; }
      } catch(_) {}
    }
    let frames = [];
    try { frames = doc.querySelectorAll('iframe'); } catch(_) {}
    for (const fr of frames) {
      try { if (fr.contentDocument && findIn(fr.contentDocument)) return true; } catch(_) {}
    }
    return false;
  }
  return findIn(document);
})()
""".strip()


async def _canvas_insert_text(session: BrowserSession, text: str) -> str:
    """For canvas-rendered editors (Google Docs/Sheets), focus the offscreen
    text-event-target iframe's contenteditable and use CDP Input.insertText —
    that's the path that triggers Docs' beforeinput/textInput handlers.
    Falls back to per-char dispatchKeyEvent for non-Docs canvases."""
    cdp = await _get_cdp_client(session)
    if cdp is None:
        raise RuntimeError("CDP client unavailable")
    # Try the Docs-style offscreen target first
    try:
        r = await cdp.send("Runtime.evaluate", {
            "expression": _FOCUS_DOCS_EDIT_TARGET,
            "returnByValue": True,
        })
        focused = bool(r.get("result", {}).get("value"))
    except Exception:
        focused = False
    if focused:
        # insertText is one shot for the whole string
        for chunk in text.split("\n"):
            if chunk:
                await cdp.send("Input.insertText", {"text": chunk})
            # Newline → real Enter via dispatchKeyEvent so Docs' line-break handler fires
            if chunk != text.split("\n")[-1] or text.endswith("\n"):
                pass
        return "docs"
    # Non-Docs canvas (Figma, custom editor) — char events are the right path
    for ch in text:
        if ch == "\n":
            for evt in ("keyDown", "keyUp"):
                await cdp.send("Input.dispatchKeyEvent", {
                    "type": evt, "key": "Enter", "code": "Enter",
                    "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13,
                })
            continue
        await cdp.send("Input.dispatchKeyEvent", {
            "type": "char", "text": ch, "unmodifiedText": ch, "key": ch,
        })
    return "char"


async def _get_cdp_client(session: BrowserSession):
    """Best-effort accessor for the active CDP session across browser-use versions."""
    for attr in ("cdp_client", "_cdp_client", "get_cdp_client"):
        v = getattr(session, attr, None)
        if v is None:
            continue
        if callable(v):
            r = v()
            return await r if asyncio.iscoroutine(r) else r
        return v
    # Fallback: dig through the page object
    page = None
    for attr in ("get_current_page", "current_page", "page"):
        v = getattr(session, attr, None)
        if v is None:
            continue
        if callable(v):
            r = v()
            page = await r if asyncio.iscoroutine(r) else r
        else:
            page = v
        if page is not None:
            break
    if page is None:
        return None
    ctx = getattr(page, "context", None)
    if ctx and hasattr(ctx, "new_cdp_session"):
        return await ctx.new_cdp_session(page)
    return None


def _build_controller() -> "Controller":
    """Construct a Browser Use Controller with our generic capabilities registered."""
    controller = Controller()

    @controller.action(
        "force_type: write text into an input via the native value setter "
        "(works on React/Vue inputs that ignore plain `input_text`).",
        param_model=_ForceTypeParams,
    )
    async def force_type(params: _ForceTypeParams, browser_session: BrowserSession) -> ActionResult:
        try:
            cdp = await _get_cdp_client(browser_session)
            if cdp is None:
                return ActionResult(extracted_content="force_type: no CDP client", error="no_cdp")
            # Resolve the element via its DOM node id from the snapshot
            dom_state = await browser_session.get_state_summary() if hasattr(
                browser_session, "get_state_summary"
            ) else None
            element = None
            if dom_state and hasattr(dom_state, "selector_map"):
                element = dom_state.selector_map.get(params.index)
            if element is None:
                return ActionResult(error=f"force_type: index {params.index} not found")
            object_id = getattr(element, "backend_node_id", None) or getattr(element, "node_id", None)
            # Use Runtime.callFunctionOn against the resolved DOM object
            resolved = await cdp.send("DOM.resolveNode", {"backendNodeId": int(object_id)}) if isinstance(object_id, int) else None
            if not resolved or "object" not in resolved:
                # Try pulling from the element directly
                xpath = getattr(element, "xpath", None)
                if not xpath:
                    return ActionResult(error="force_type: cannot resolve element")
                # Resolve by xpath via Runtime.evaluate
                evald = await cdp.send("Runtime.evaluate", {
                    "expression": (
                        f"document.evaluate({json.dumps(xpath)}, document, null, "
                        "XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue"
                    ),
                    "returnByValue": False,
                })
                obj = evald.get("result", {})
                if not obj.get("objectId"):
                    return ActionResult(error="force_type: xpath resolve failed")
                object_id_str = obj["objectId"]
            else:
                object_id_str = resolved["object"]["objectId"]
            await cdp.send("Runtime.callFunctionOn", {
                "objectId": object_id_str,
                "functionDeclaration": _REACT_SAFE_SET_VALUE,
                "arguments": [{"value": params.text}],
                "awaitPromise": False,
                "returnByValue": True,
            })
            return ActionResult(extracted_content=f"Typed via native setter into element {params.index}")
        except Exception as e:
            return ActionResult(error=f"force_type failed: {e!s}")

    @controller.action(
        "canvas_type: send keystrokes to the currently focused element via CDP "
        "keyboard events. Use this for canvas editors (Google Docs/Sheets/Figma) "
        "after first clicking the canvas to give it focus.",
        param_model=_CanvasTypeParams,
    )
    async def canvas_type(params: _CanvasTypeParams, browser_session: BrowserSession) -> ActionResult:
        try:
            mode = await _canvas_insert_text(browser_session, params.text)
            return ActionResult(extracted_content=f"Typed {len(params.text)} chars into canvas editor ({mode})")
        except Exception as e:
            return ActionResult(error=f"canvas_type failed: {e!s}")

    @controller.action(
        "pierce_query: find an element by its visible text, including inside open "
        "shadow roots. Returns x/y of the element's center so you can click it.",
        param_model=_PierceQueryParams,
    )
    async def pierce_query(params: _PierceQueryParams, browser_session: BrowserSession) -> ActionResult:
        try:
            cdp = await _get_cdp_client(browser_session)
            if cdp is None:
                return ActionResult(error="pierce_query: no CDP client")
            args = [{"value": params.visible_text}, {"value": params.role}]
            r = await cdp.send("Runtime.evaluate", {
                "expression": f"({_SHADOW_PIERCE_QUERY})({json.dumps(params.visible_text)}, {json.dumps(params.role)})",
                "returnByValue": True,
            })
            val = r.get("result", {}).get("value")
            if not val:
                return ActionResult(extracted_content="pierce_query: no match")
            return ActionResult(
                extracted_content=f"Found at x={val['x']}, y={val['y']} ({val.get('tag','?')})"
            )
        except Exception as e:
            return ActionResult(error=f"pierce_query failed: {e!s}")

    @controller.action(
        "canvas_pointer: dispatch a real mouse press+release at viewport coordinates. "
        "Use when DOM is empty (WebGL/canvas) and you've identified the spot from "
        "a screenshot or pierce_query.",
        param_model=_CanvasPointerParams,
    )
    async def canvas_pointer(params: _CanvasPointerParams, browser_session: BrowserSession) -> ActionResult:
        try:
            cdp = await _get_cdp_client(browser_session)
            if cdp is None:
                return ActionResult(error="canvas_pointer: no CDP client")
            # Coordinates from screenshots are in device pixels; CDP wants CSS pixels.
            # Scale by 1/devicePixelRatio so vision-derived clicks land where intended.
            try:
                dpr_r = await cdp.send("Runtime.evaluate", {
                    "expression": "window.devicePixelRatio || 1",
                    "returnByValue": True,
                })
                dpr = float(dpr_r.get("result", {}).get("value") or 1)
                if dpr <= 0:
                    dpr = 1.0
            except Exception:
                dpr = 1.0
            cx, cy = params.x / dpr, params.y / dpr
            base = {"x": cx, "y": cy, "button": params.button, "clickCount": params.click_count, "buttons": 1}
            # mouseMoved first so hover-state listeners (common in WebGL) prime properly
            await cdp.send("Input.dispatchMouseEvent", {**base, "type": "mouseMoved", "buttons": 0})
            await cdp.send("Input.dispatchMouseEvent", {**base, "type": "mousePressed"})
            await cdp.send("Input.dispatchMouseEvent", {**base, "type": "mouseReleased"})
            return ActionResult(extracted_content=f"Pointer at ({int(cx)},{int(cy)}) css px [dpr={dpr:g}]")
        except Exception as e:
            return ActionResult(error=f"canvas_pointer failed: {e!s}")

    return controller

# Fernet cipher for cookie encryption
_fernet = Fernet(
    PROFILE_ENCRYPTION_KEY.encode()
    if isinstance(PROFILE_ENCRYPTION_KEY, str)
    else PROFILE_ENCRYPTION_KEY
)

# --- Status message mapping ---
# Maps Browser Use action types to user-friendly messages
_ACTION_STATUS_MAP = {
    "go_to_url": msg.TASK_NAVIGATING,
    "navigate": msg.TASK_NAVIGATING,
    "search": msg.TASK_NAVIGATING,
    "click": msg.TASK_PERFORMING_ACTION,
    "input": msg.TASK_TYPING,
    "input_text": msg.TASK_TYPING,
    "type": msg.TASK_TYPING,
    "scroll": msg.TASK_SCROLLING,
    "scroll_down": msg.TASK_SCROLLING,
    "scroll_up": msg.TASK_SCROLLING,
    "select": msg.TASK_SELECTING,
    "select_option": msg.TASK_SELECTING,
    "wait": msg.TASK_WAITING,
    "extract_page_content": msg.TASK_READING_PAGE,
    "done": msg.TASK_COMPLETE,
}


def _get_llm():
    """Return the best available LLM using browser-use's native wrappers."""
    from browser_use import ChatGoogle, ChatGroq

    google_key = os.environ.get("GOOGLE_API_KEY")
    if google_key:
        return ChatGoogle(
            model="gemini-2.5-flash",
            api_key=google_key,
            temperature=0.0,
            thinking_budget=0,
        )

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        return ChatGroq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            api_key=groq_key,
            temperature=0.0,
        )

    raise RuntimeError("No LLM API key found. Set GOOGLE_API_KEY or GROQ_API_KEY.")


def _sanitize_status(text: str) -> str:
    """
    Strip technical terms from LLM-generated step descriptions before showing to users.
    next_goal can contain words like 'JavaScript', 'JSON', model names, etc.
    """
    import re
    replacements = [
        ("javascript", "a script"),
        ("xpath", "the element"),
        ("css selector", "the element"),
        ("dom element", "the element"),
        ("iframe", "the page section"),
        ("accessibility tree", "the page"),
        ("playwright", "the browser"),
        ("patchright", "the browser"),
        ("chromium", "the browser"),
        ("webdriver", "the browser"),
        ("api call", "a request"),
        ("http request", "a request"),
        ("json response", "the data"),
        ("json", "data"),
        ("groq", "the AI"),
        ("gemini", "the AI"),
        ("llama", "the AI"),
        ("deepseek", "the AI"),
        ("fastapi", "the server"),
        ("supabase", "the database"),
        ("python", "the system"),
        ("async", ""),
        ("await", ""),
    ]
    text_lower = text.lower()
    for term, replacement in replacements:
        if term in text_lower:
            if replacement:
                text = re.sub(re.escape(term), replacement, text, flags=re.IGNORECASE)
            else:
                text = re.sub(r'\b' + re.escape(term) + r'\b', "", text, flags=re.IGNORECASE)
            text_lower = text.lower()
    # Clean up double spaces
    text = re.sub(r"  +", " ", text).strip()
    return text


def _get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


# URL path fragments that almost always indicate a login/auth wall.
_LOGIN_URL_PATTERNS = (
    "/login", "/signin", "/sign-in", "/sign_in", "/log-in", "/log_in",
    "/auth/", "/account/login", "/users/sign_in", "/accounts/login",
    "/oauth", "/sso", "/checkpoint", "/identifier", "/identifiersignin",
    "/authenticate",
)

# Phrases that strongly suggest a login wall when seen in visible page text.
_LOGIN_PAGE_PHRASES = (
    "sign in to continue",
    "log in to continue",
    "please sign in",
    "please log in",
    "create an account or sign in",
    "you must be logged in",
    "you need to be signed in",
    "enter your password",
    "forgot password",
)


def _looks_like_login(url: str, page_text: str) -> bool:
    """Heuristic: does this look like a login/auth wall?"""
    if not url and not page_text:
        return False
    url_l = (url or "").lower()
    for pat in _LOGIN_URL_PATTERNS:
        if pat in url_l:
            return True
    text_l = (page_text or "").lower()
    for phrase in _LOGIN_PAGE_PHRASES:
        if phrase in text_l:
            return True
    return False


async def _load_cookies(user_id: str, domain: str) -> list[dict] | None:
    """Load saved cookies from Supabase, decrypt."""
    try:
        rows = await supabase_client.select_rows(
            "browser_profiles",
            filters={"user_id": user_id, "site_domain": domain},
            limit=1,
        )
        if rows:
            encrypted = rows[0].get("cookies_json", "")
            if not encrypted:
                return None
            try:
                cookies_json = _fernet.decrypt(encrypted.encode("utf-8")).decode("utf-8")
            except Exception:
                cookies_json = encrypted
            cookies = json.loads(cookies_json)
            if cookies:
                return cookies
    except Exception:
        pass
    return None


async def _save_cookies(user_id: str, domain: str, cookies: list[dict]) -> None:
    """Encrypt and save cookies to Supabase."""
    try:
        # Sanitize cookies — never store passwords or sensitive form data
        safe_cookies = []
        for c in cookies:
            cookie = dict(c)
            # Strip any cookie that looks like it contains credentials
            name_lower = cookie.get("name", "").lower()
            if any(kw in name_lower for kw in ("password", "passwd", "secret", "credit", "card")):
                continue
            safe_cookies.append(cookie)

        cookies_json = json.dumps(safe_cookies)
        encrypted = _fernet.encrypt(cookies_json.encode("utf-8")).decode("utf-8")
        await supabase_client.upsert_row(
            "browser_profiles",
            {
                "user_id": user_id,
                "site_domain": domain,
                "cookies_json": encrypted,
                "updated_at": "now()",
            },
        )
    except Exception:
        pass


async def _send_status(send: SendFn, message: str) -> None:
    await send({"type": "status", "message": message})


async def _send_confirm(send: SendFn, message: str, action: str) -> None:
    await send({"type": "confirm", "message": message, "action": action})


async def _send_login(send: SendFn) -> None:
    await send({"type": "login_needed", "message": msg.LOGIN_NEEDED})


async def _send_complete(send: SendFn, message: str) -> None:
    await send({"type": "complete", "message": message})


async def _send_error(send: SendFn, message: str) -> None:
    await send({"type": "error", "message": message})


class EngineAgent:
    """
    Wraps Browser Use Agent with Anticipy's safety, streaming, and cookie management.
    """

    def __init__(
        self,
        goal: str,
        send: SendFn,
        receive_confirmation: Callable[[], Awaitable[str]],
        user_id: str | None = None,
    ) -> None:
        self.goal = sanitize_input(goal)
        self.send = send
        self.receive_confirmation = receive_confirmation
        self.user_id = user_id
        self.tracker = CostTracker()
        self._session: BrowserSession | None = None
        self._last_status_time: float = 0.0
        self._step_count: int = 0
        self._start_time: float = 0.0
        self._stopped: bool = False
        self._login_notified: bool = False
        self._closed: bool = False
        # Profile dir created per-task for anonymous users so cookies don't leak
        # across distinct anonymous callers; cleaned up in _close().
        self._ephemeral_profile_dir: str | None = None

    async def _on_step(self, browser_state, agent_output, step_num) -> None:
        """Callback fired after each Browser Use step. Streams status to user."""
        self._step_count = step_num
        now = time.time()

        # Budget check — time
        elapsed = now - self._start_time
        if elapsed > MAX_SECONDS:
            self._stopped = True
            return

        # --- Login wall detection (one-shot per task) ---
        if not self._login_notified:
            current_url = ""
            page_text = ""
            try:
                current_url = getattr(browser_state, "url", "") or ""
            except Exception:
                pass
            try:
                # Browser Use exposes page snapshot under different attrs across versions —
                # try common ones, fall through quietly if not present
                snap = getattr(browser_state, "elements_text", "") or ""
                if not snap:
                    snap = getattr(browser_state, "page_text", "") or ""
                page_text = (snap or "")[:1500].lower()
            except Exception:
                pass

            if _looks_like_login(current_url, page_text):
                self._login_notified = True
                await _send_login(self.send)
                # Don't stop — the agent may still be able to complete via guest checkout,
                # or the user may sign in inside the browser window and we keep going.

        # Throttle status updates to every 2 seconds
        if now - self._last_status_time < 2.0:
            return
        self._last_status_time = now

        # Determine status message from the agent's actions
        status_msg = msg.TASK_PERFORMING_ACTION
        if agent_output and agent_output.action:
            for action in agent_output.action:
                try:
                    # ActionModel is dynamic — dump to dict to inspect
                    action_dict = action.model_dump(exclude_none=True)
                    for action_name in action_dict.keys():
                        action_lower = action_name.lower()
                        for key, val in _ACTION_STATUS_MAP.items():
                            if key in action_lower:
                                status_msg = val
                                break
                except Exception:
                    pass

        # Use next_goal for more descriptive status if available
        description = status_msg.rstrip(".")
        if agent_output and agent_output.next_goal:
            # Use a simplified version of next_goal, sanitized to remove technical terms
            goal_text = agent_output.next_goal[:80]
            if len(agent_output.next_goal) > 80:
                goal_text += "..."
            description = _sanitize_status(goal_text)

        progress = msg.STEP_PROGRESS.format(current=step_num, description=description)
        await _send_status(self.send, progress)

    async def _should_stop(self) -> bool:
        """Check if agent should stop (budget exceeded)."""
        if self._stopped:
            return True
        elapsed = time.time() - self._start_time
        if elapsed > MAX_SECONDS:
            self._stopped = True
            return True
        return False

    async def run(self) -> None:
        """Execute the full agent loop using Browser Use."""
        self._start_time = time.time()
        self._last_status_time = self._start_time

        try:
            # --- Safety check (with category-aware messaging) ---
            reason = block_reason(self.goal)
            if reason:
                if reason == "password":
                    await _send_error(self.send, msg.PASSWORD_REQUEST_BLOCKED)
                elif reason == "financial":
                    await _send_error(self.send, msg.FINANCIAL_TRANSACTION_BLOCKED)
                else:
                    await _send_error(self.send, msg.BLOCKED_ACTION)
                return

            # --- Plan (get starting URL) ---
            await _send_status(self.send, msg.TASK_STARTING)
            try:
                plan = await asyncio.wait_for(plan_task(self.goal, self.tracker), timeout=15)
            except (asyncio.TimeoutError, Exception):
                logger.exception("plan_task error")
                plan = {"url": "https://www.google.com", "sub_goals": [self.goal], "success": ""}
            start_url = plan.get("url") or "https://www.google.com"

            # --- Configure browser session ---
            # Authenticated users get a stable profile under BROWSER_PROFILE_BASE.
            # Anonymous users get a fresh ephemeral dir per task so they never
            # share cookies / sessions with each other.
            if self.user_id:
                profile_dir = os.path.join(BROWSER_PROFILE_BASE, self.user_id)
                os.makedirs(profile_dir, exist_ok=True)
            else:
                self._ephemeral_profile_dir = tempfile.mkdtemp(
                    prefix=f"engine_anon_{uuid.uuid4().hex[:8]}_"
                )
                profile_dir = self._ephemeral_profile_dir

            # Build chrome args for stealth and stability
            chrome_args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--window-size=1920,1080",
                # Software WebGL fallback to prevent crashes on GPU-intensive pages
                "--use-gl=swiftshader",
                "--no-first-run",
                "--no-default-browser-check",
            ]

            # NopeCHA extension for CAPTCHA solving
            nopecha_dir = os.path.join(os.path.dirname(__file__), "..", "nopecha")
            if os.path.isdir(nopecha_dir):
                chrome_args.extend([
                    f"--disable-extensions-except={nopecha_dir}",
                    f"--load-extension={nopecha_dir}",
                ])

            self._session = BrowserSession(
                headless=False,
                user_data_dir=profile_dir,
                args=chrome_args,
                no_viewport=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                wait_between_actions=0.5,
                minimum_wait_page_load_time=0.5,
                wait_for_network_idle_page_load_time=3.0,
            )

            # --- Load saved cookies ---
            domain = _get_domain(start_url)
            cookies = None
            if self.user_id and domain:
                cookies = await _load_cookies(self.user_id, domain)

            # Start session and inject cookies before agent runs.
            # We try several Browser Use accessor names to stay version-tolerant
            # rather than reaching for a private attribute.
            # Cold-start the browser. Chromium's first launch on a fresh profile
            # can exceed Browser Use's 30s start-event timeout under load. Retry
            # once after a stop/teardown so the second attempt re-uses the warm
            # binary cache and succeeds.
            start_attempts = 0
            while True:
                start_attempts += 1
                try:
                    await self._session.start()
                    break
                except Exception:
                    logger.warning(
                        "browser session start attempt %d failed", start_attempts,
                        exc_info=True,
                    )
                    if start_attempts >= 2:
                        await _send_error(self.send, msg.BROWSER_ERROR)
                        return
                    # Tear down whatever partial state we have and retry
                    try:
                        await self._session.stop()
                    except Exception:
                        pass
                    await asyncio.sleep(2)

            # Force every shadow root open BEFORE any page script runs, so the
            # agent can find elements inside e.g. Salesforce LWC, Polymer, etc.
            try:
                cdp = await _get_cdp_client(self._session)
                if cdp is not None:
                    await cdp.send("Page.addScriptToEvaluateOnNewDocument", {
                        "source": _SHADOW_OPEN_PATCH,
                    })
            except Exception:
                logger.debug("shadow-open patch install failed", exc_info=True)

            if cookies:
                try:
                    add_cookies = getattr(self._session, "add_cookies", None)
                    if callable(add_cookies):
                        await add_cookies(cookies)
                    else:
                        ctx = (
                            getattr(self._session, "browser_context", None)
                            or getattr(self._session, "context", None)
                            or getattr(self._session, "_browser_context", None)
                        )
                        if ctx is not None and hasattr(ctx, "add_cookies"):
                            await ctx.add_cookies(cookies)
                except Exception:
                    logger.debug("cookie injection failed", exc_info=True)

            # --- Get LLM ---
            llm = _get_llm()

            # --- Build task with starting URL hint ---
            task = self.goal
            if start_url and not start_url.startswith("https://www.google.com/search"):
                task = f"Go to {start_url} and {self.goal}"

            # --- Create Browser Use agent ---
            await _send_status(self.send, msg.TASK_NAVIGATING)

            controller = _build_controller()

            agent = Agent(
                task=task,
                llm=llm,
                browser_session=self._session,
                controller=controller,
                max_actions_per_step=3,
                max_failures=5,
                use_vision=True,
                register_new_step_callback=self._on_step,
                register_should_stop_callback=self._should_stop,
                generate_gif=False,
                enable_planning=True,
                loop_detection_enabled=True,
                extend_system_message=_AGENT_SYSTEM_RULES,
            )

            # --- Run with hard timeout ---
            try:
                history: AgentHistoryList = await asyncio.wait_for(
                    agent.run(max_steps=MAX_STEPS),
                    timeout=MAX_SECONDS + 30,
                )
            except asyncio.TimeoutError:
                await _send_error(self.send, msg.BUDGET_TIME_EXCEEDED)
                await self._save_session_cookies(start_url)
                return

            # --- Process result ---
            await self._save_session_cookies(start_url)

            if history.is_done():
                result_text = history.final_result()
                if result_text and len(result_text.strip()) > 2:
                    # Clean any technical leakage from the result
                    clean_result = _sanitize_output(result_text)
                    await _send_complete(self.send, clean_result)
                else:
                    await _send_complete(
                        self.send,
                        "I completed the task but couldn't get a clear answer. Can you check?"
                    )
            elif self._stopped:
                await _send_error(self.send, msg.BUDGET_TIME_EXCEEDED)
            else:
                # Try to extract any partial result
                result_text = history.final_result()
                if result_text:
                    clean_result = _sanitize_output(result_text)
                    await _send_complete(self.send, clean_result)
                else:
                    await _send_complete(self.send, msg.TASK_STUCK)

        except asyncio.CancelledError:
            await _send_error(self.send, msg.TASK_INTERRUPTED)
            raise
        except Exception:
            logger.exception("Agent execution error")
            # If we hit a login wall *and* errored, surface that instead of the
            # generic connection error — it's far more actionable for the user.
            if self._login_notified:
                await _send_error(
                    self.send,
                    "I couldn't get past the sign-in screen. Try signing in to "
                    "the site in your browser first, then ask me again.",
                )
            else:
                await _send_error(self.send, msg.CONNECTION_ERROR)
        finally:
            await self._close()

    async def _save_session_cookies(self, start_url: str) -> None:
        """Save cookies from the current browser session for an authenticated user."""
        if not self.user_id or not self._session:
            return
        try:
            domain = _get_domain(start_url)

            # Get current URL via best-effort accessor probing
            current_url = ""
            for attr in ("get_current_page_url", "current_url", "url"):
                try:
                    val = getattr(self._session, attr, None)
                    if callable(val):
                        v = val()
                        current_url = await v if asyncio.iscoroutine(v) else (v or "")
                    elif val is not None:
                        current_url = val if isinstance(val, str) else str(val)
                    if current_url:
                        break
                except Exception:
                    continue
            current_domain = _get_domain(current_url) if current_url else ""

            cookies_fn = getattr(self._session, "cookies", None)
            cookies: list[dict] = []
            try:
                if callable(cookies_fn):
                    result = cookies_fn()
                    cookies = await result if asyncio.iscoroutine(result) else (result or [])
            except Exception:
                cookies = []

            if not cookies:
                return

            if domain:
                domain_cookies = [
                    c for c in cookies
                    if domain in (c.get("domain", "") or "")
                ]
                if domain_cookies:
                    await _save_cookies(self.user_id, domain, domain_cookies)

            if current_domain and current_domain != domain:
                current_cookies = [
                    c for c in cookies
                    if current_domain in (c.get("domain", "") or "")
                ]
                if current_cookies:
                    await _save_cookies(self.user_id, current_domain, current_cookies)
        except Exception:
            logger.debug("save cookies failed", exc_info=True)

    async def _close(self) -> None:
        """Close browser session and clean up any ephemeral profile dir.  Idempotent."""
        if self._closed:
            return
        self._closed = True

        try:
            if self._session:
                await self._session.stop()
        except Exception:
            logger.debug("session.stop() raised", exc_info=True)
        self._session = None

        # Clean up ephemeral anonymous profile so /tmp doesn't fill up.
        if self._ephemeral_profile_dir:
            try:
                shutil.rmtree(self._ephemeral_profile_dir, ignore_errors=True)
            except Exception:
                pass
            self._ephemeral_profile_dir = None


# --- Technical leakage sanitization ---


def _sanitize_output(text: str) -> str:
    """
    Remove technical terms from agent output that users should never see.
    Strip markdown code blocks and JSON formatting.
    """
    if not text:
        return text

    import re

    # Strip markdown code blocks (```json ... ```)
    had_code_blocks = '```' in text
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```\s*', '', text)

    # Convert JSON array/object formatting to plain text
    # Replace {"name": "X", "price": "Y"} patterns with readable format
    def _json_to_plain(match):
        try:
            import json as _json
            data = _json.loads(match.group(0))
            if isinstance(data, list):
                lines = []
                for i, item in enumerate(data, 1):
                    if isinstance(item, dict):
                        parts = []
                        for k, v in item.items():
                            parts.append(str(v))
                        lines.append(f"{i}. {' — '.join(parts)}")
                    else:
                        lines.append(f"{i}. {item}")
                return '\n'.join(lines)
            elif isinstance(data, dict):
                return ', '.join(f"{k}: {v}" for k, v in data.items())
        except Exception:
            pass
        return match.group(0)

    # Only convert JSON if markdown code blocks were present
    if had_code_blocks:
        text = re.sub(r'\[\s*\{[^]]+\}\s*\]', _json_to_plain, text, flags=re.DOTALL)

    # Technical terms that should never appear in user-facing output
    tech_terms_to_strip = [
        "javascript", "xpath", "css selector", "dom element", "iframe",
        "accessibility tree", "playwright", "patchright", "chromium", "webdriver",
        "api call", "http request", "json response",
        "groq", "gemini", "llama", "deepseek",
        "supabase", "fastapi", "httpx",
    ]

    text_lower = text.lower()

    # Replace technical terms with user-friendly alternatives
    for term in tech_terms_to_strip:
        if term in text_lower:
            text = re.sub(re.escape(term), "a different method", text, flags=re.IGNORECASE)
            text_lower = text.lower()

    # These are only problematic when they appear in error-like contexts
    error_indicators = [
        "traceback", "exception", "stack trace", "status code",
        "api error", "http error", "500 internal", "429 too many",
        "null pointer", "undefined is not",
    ]

    for indicator in error_indicators:
        if indicator in text_lower:
            return "I ran into a problem completing that. Want to try again?"

    return text.strip()


# --- Public entry point ---

async def execute_task(
    goal: str,
    send: SendFn,
    receive_confirmation: Callable[[], Awaitable[str]],
    user_id: str | None = None,
) -> None:
    """
    Top-level entry point. Creates an EngineAgent and runs it
    with a hard timeout. Called by main.py WebSocket handler.

    All exceptions are caught and reported to the user as a friendly message —
    no stack traces or technical detail leak through.
    """
    agent = EngineAgent(goal, send, receive_confirmation, user_id)
    try:
        await asyncio.wait_for(agent.run(), timeout=MAX_SECONDS + 60)
    except asyncio.TimeoutError:
        await _send_error(send, msg.BUDGET_TIME_EXCEEDED)
    except asyncio.CancelledError:
        # Already surfaced inside run(); rethrow so callers can clean up.
        raise
    except Exception:
        logger.exception("execute_task error")
        await _send_error(send, msg.CONNECTION_ERROR)
    finally:
        # _close() is idempotent so calling it here on top of the run() finally
        # is safe — it covers the wait_for-TimeoutError path too.
        try:
            await agent._close()
        except Exception:
            logger.debug("agent close raised", exc_info=True)


# PHASE 2: User device fallback
# If datacenter IP is blocked, offer to run the browser on the user's device instead.
# Architecture: Browser Use connects to a remote Chrome instance on user's machine
# via Chrome DevTools Protocol. The user installs a lightweight bridge app that
# exposes their local Chrome to the cloud agent. This gives residential IP + real
# browser fingerprint. Implementation deferred to post-raise.
