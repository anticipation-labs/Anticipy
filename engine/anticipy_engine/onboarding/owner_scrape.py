"""GENUINE owner self-scrape over CDP.

Reads the owner's OWN logged-in surfaces (Gmail inbox/sent, Calendar, Contacts, LinkedIn) READ-ONLY
and returns the raw text signals. No faking by construction:
  - a surface that bounces to a sign-in wall is reported `needs_login` (never invented content);
  - money / credential / banking domains are refused by the SAME nav wall the browser arm uses;
  - it only ever READS page text — it never clicks, types, sends, or buys.

The dossier synthesizer (dossier.py) turns these raw signals into a graded profile. The four-layer
onboarding loop calls this once per APPROVED surface (the per-service permission gate lives in the loop,
not here — this reads exactly the surfaces it is handed).
"""
from __future__ import annotations

import asyncio
import json
import urllib.request

from ..core.navwall import nav_block_reason

# Layer-1 surfaces: the core accounts most people have. The loop gates each with the owner's
# per-service approval BEFORE this is ever pointed at it.
DEFAULT_SURFACES = [
    {"key": "gmail_inbox", "label": "Gmail — inbox", "url": "https://mail.google.com/mail/u/0/#inbox"},
    {"key": "gmail_sent", "label": "Gmail — sent mail", "url": "https://mail.google.com/mail/u/0/#sent"},
    {"key": "calendar", "label": "Google Calendar", "url": "https://calendar.google.com/calendar/u/0/r"},
    {"key": "contacts", "label": "Google Contacts", "url": "https://contacts.google.com/"},
    {"key": "linkedin", "label": "LinkedIn", "url": "https://www.linkedin.com/feed/"},
]

_LOGIN_TEXT_MARKERS = (
    "sign in", "sign-in", "log in", "use your google account", "enter your password",
    "couldn't find your google account", "forgot email", "to continue to", "create account",
    "new to linkedin", "join now", "sign in to linkedin",
)
_LOGIN_URL_HINTS = ("accounts.google.com", "/signin", "/login", "/uas/login", "/checkpoint",
                    "servicelogin", "authuser")


def _page_ws_url(cdp_url: str) -> str | None:
    """Pick a real page target on the debuggable Chrome to drive."""
    base = (cdp_url or "http://127.0.0.1:9222").rstrip("/")
    try:
        with urllib.request.urlopen(base + "/json/list", timeout=3) as resp:
            pages = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    items = [p for p in pages if isinstance(p, dict) and p.get("type") == "page"]
    if not items:
        return None
    # prefer a non-devtools normal tab; take the last (most-recently-focused)
    normal = [p for p in items if not str(p.get("url") or "").startswith("devtools://")]
    chosen = (normal or items)[-1]
    return str(chosen.get("webSocketDebuggerUrl") or "").replace("127.0.0.1", "localhost")


async def _read_surface(call, surface: dict, max_chars: int) -> dict:
    url = surface["url"]
    reason = nav_block_reason(url)
    if reason:
        return {**surface, "status": "blocked", "reason": reason, "needs_login": False,
                "text": "", "chars": 0, "final_url": ""}
    try:
        await call("Page.navigate", {"url": url}, timeout=25)
        await asyncio.sleep(3.2)  # let the SPA hydrate
        ev = await call("Runtime.evaluate", {
            "expression": ("JSON.stringify({u:location.href,t:document.title,"
                           "x:(document.body?document.body.innerText:'')})"),
            "returnByValue": True}, timeout=25)
        raw = (((ev.get("result") or {}).get("result") or {}).get("value")) or "{}"
        val = json.loads(raw)
    except Exception as e:  # a tool failure on this surface — honest, not a fake success
        return {**surface, "status": "error", "reason": str(e)[:140], "needs_login": False,
                "text": "", "chars": 0, "final_url": ""}
    final_url = (val.get("u") or "")
    title = val.get("t") or ""
    text = (val.get("x") or "")
    probe = (text[:800] + " | " + final_url + " | " + title).lower()
    needs_login = (any(h in final_url.lower() for h in _LOGIN_URL_HINTS)
                   or any(m in probe for m in _LOGIN_TEXT_MARKERS))
    clipped = "" if needs_login else text[:max_chars]
    return {**surface, "status": "needs_login" if needs_login else "ok", "needs_login": needs_login,
            "title": title, "final_url": final_url, "text": clipped, "chars": len(clipped)}


async def _scrape_async(ws_url: str, surfaces: list, max_chars: int) -> list:
    import websockets

    counter = 0
    results: list = []
    async with websockets.connect(ws_url, max_size=12 * 1024 * 1024, open_timeout=8) as ws:
        async def call(method: str, params: dict, timeout: float = 20.0) -> dict:
            nonlocal counter
            counter += 1
            await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                if int(msg.get("id") or 0) == counter:
                    return msg

        await call("Page.enable", {})
        await call("Runtime.enable", {})
        for s in surfaces:
            results.append(await _read_surface(call, s, max_chars))
    return results


def scrape_owner(cdp_url: str | None = None, surfaces: list | None = None, max_chars: int = 6000) -> dict:
    """Genuine read of the owner's logged-in surfaces over CDP. Returns:
       {ok, surfaces:[{key,label,status,needs_login,text,chars,final_url,...}], logged_in:[keys],
        needs_login:[keys]}.  A sign-in wall -> needs_login (no invented content)."""
    cdp_url = cdp_url or "http://127.0.0.1:9222"
    surfaces = surfaces if surfaces is not None else DEFAULT_SURFACES
    ws_url = _page_ws_url(cdp_url)
    if not ws_url:
        return {"ok": False, "error": f"no debuggable Chrome page at {cdp_url}", "surfaces": []}
    try:
        signals = asyncio.run(_scrape_async(ws_url, surfaces, max_chars))
    except RuntimeError:  # already in an event loop
        loop = asyncio.new_event_loop()
        try:
            signals = loop.run_until_complete(_scrape_async(ws_url, surfaces, max_chars))
        finally:
            loop.close()
    return {
        "ok": True,
        "surfaces": signals,
        "logged_in": [s["key"] for s in signals if s.get("status") == "ok"],
        "needs_login": [s["key"] for s in signals if s.get("needs_login")],
    }
