"""GENUINE owner self-scrape over CDP — and it TAKES ITS TIME.

Reads the owner's OWN logged-in surfaces (Gmail inbox/sent, Calendar, Contacts, LinkedIn) READ-ONLY.
It does not glance: per surface it lets the page settle, then SCROLLS through it in steps, dwelling so
more content loads (more emails, more events, more contacts, more posts), accumulating the UNIQUE lines
it sees — a real cataloguing crawl, not a 3-second snapshot. No faking by construction:
  - a surface that bounces to a sign-in wall is reported `needs_login` (never invented content);
  - money / credential / banking domains are refused by the SAME nav wall the browser arm uses;
  - it only ever READS — it never clicks an action, types, sends, or buys.

The dossier synthesizer (dossier.py) turns the catalogued text into a graded profile. The four-layer
loop calls this once per APPROVED surface, going DEEPER (more scroll steps) each layer.
"""
from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request

from ..core.navwall import nav_block_reason

# each surface declares the HOST it should land on when you're logged in — a redirect AWAY from that
# host (Gmail bouncing to accounts.google.com / workspace.google.com) is the reliable login-wall signal.
DEFAULT_SURFACES = [
    {"key": "gmail_inbox", "label": "Gmail — inbox", "url": "https://mail.google.com/mail/u/0/#inbox", "host": "mail.google.com"},
    {"key": "gmail_sent", "label": "Gmail — sent mail", "url": "https://mail.google.com/mail/u/0/#sent", "host": "mail.google.com"},
    {"key": "calendar", "label": "Google Calendar", "url": "https://calendar.google.com/calendar/u/0/r", "host": "calendar.google.com"},
    {"key": "contacts", "label": "Google Contacts", "url": "https://contacts.google.com/", "host": "contacts.google.com"},
    {"key": "linkedin", "label": "LinkedIn", "url": "https://www.linkedin.com/feed/", "host": "linkedin.com"},
]

# STRICT login-page phrases only (not generic "log in"/"sign in" links every site's header has).
_STRONG_LOGIN_MARKERS = (
    "use your google account", "enter your password", "to continue to",
    "couldn't find your google account", "forgot email",
    "sign in to linkedin", "new to linkedin",
)
# login PATHS (LinkedIn's login is the same host as its feed, so the path catches it).
_LOGIN_URL_HINTS = ("accounts.google.com", "workspace.google.com", "/signin", "/login",
                    "/uas/login", "/checkpoint", "servicelogin")


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).netloc or "").lower()
    except Exception:
        return ""

# JS: read the page's full visible text
_TEXT_JS = "(document.body ? document.body.innerText : '')"
# JS: find the LARGEST scrollable element (Gmail/LinkedIn scroll their own container, not the window),
# scroll it ~85% of a screen, and report its position so we can tell when we've hit the bottom.
_SCROLL_JS = (
    "(()=>{const els=[document.scrollingElement].concat(Array.from(document.querySelectorAll('*')))"
    ".filter(e=>e&&e.scrollHeight>e.clientHeight+60);"
    "const el=els.sort((a,b)=>b.scrollHeight-a.scrollHeight)[0]||document.scrollingElement;"
    "if(!el)return JSON.stringify({top:0,max:0});"
    "el.scrollBy(0,Math.round(el.clientHeight*0.85));"
    "return JSON.stringify({top:el.scrollTop,max:el.scrollHeight-el.clientHeight});})()"
)


def _page_ws_url(cdp_url: str) -> str | None:
    base = (cdp_url or "http://127.0.0.1:9222").rstrip("/")
    try:
        with urllib.request.urlopen(base + "/json/list", timeout=3) as resp:
            pages = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    items = [p for p in pages if isinstance(p, dict) and p.get("type") == "page"]
    if not items:
        return None
    normal = [p for p in items if not str(p.get("url") or "").startswith("devtools://")]
    chosen = (normal or items)[-1]
    return str(chosen.get("webSocketDebuggerUrl") or "").replace("127.0.0.1", "localhost")


async def _eval(call, expr: str, timeout: float = 20.0):
    ev = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, timeout=timeout)
    return (((ev.get("result") or {}).get("result") or {}).get("value"))


async def _read_surface(call, surface: dict, max_chars: int, scroll_steps: int,
                        dwell: float, settle: float) -> dict:
    url = surface["url"]
    reason = nav_block_reason(url)
    if reason:
        return {**surface, "status": "blocked", "reason": reason, "needs_login": False,
                "text": "", "chars": 0, "final_url": "", "scrolls": 0}
    try:
        await call("Page.navigate", {"url": url}, timeout=25)
        await asyncio.sleep(settle)  # let the SPA hydrate before we judge or read
        meta = json.loads(await _eval(call, "JSON.stringify({u:location.href,t:document.title})") or "{}")
        final_url, title = (meta.get("u") or ""), (meta.get("t") or "")
        first = (await _eval(call, _TEXT_JS) or "")
        probe = (first[:900] + " | " + title).lower()
        expected = surface.get("host") or ""
        fhost = _host(final_url)
        redirected = bool(expected) and (expected not in fhost) and (fhost not in expected)
        needs_login = (redirected
                       or any(h in final_url.lower() for h in _LOGIN_URL_HINTS)
                       or any(m in probe for m in _STRONG_LOGIN_MARKERS))
        if needs_login:  # honest — don't crawl or invent a logged-out surface
            return {**surface, "status": "needs_login", "needs_login": True, "title": title,
                    "final_url": final_url, "text": "", "chars": 0, "scrolls": 0}

        # THOROUGH PASS: scroll through, dwelling so more loads, cataloguing UNIQUE lines.
        seen: set = set()
        catalogued: list = []

        def _ingest(blob: str):
            for ln in (blob or "").splitlines():
                ln = ln.strip()
                if ln and ln not in seen:
                    seen.add(ln)
                    catalogued.append(ln)

        _ingest(first)
        last_top = -1.0
        for _ in range(max(1, scroll_steps)):
            pos = json.loads(await _eval(call, _SCROLL_JS) or "{}")
            await asyncio.sleep(dwell)  # let lazily-loaded rows render
            _ingest(await _eval(call, _TEXT_JS) or "")
            top = float(pos.get("top") or 0)
            if top <= last_top + 2 and top >= float(pos.get("max") or 0) - 2:
                break  # reached the bottom — nothing more to catalogue
            last_top = top
            if sum(len(x) + 1 for x in catalogued) > max_chars:
                break
    except Exception as e:
        return {**surface, "status": "error", "reason": str(e)[:160], "needs_login": False,
                "text": "", "chars": 0, "final_url": "", "scrolls": 0}

    text = "\n".join(catalogued)[:max_chars]
    return {**surface, "status": "ok", "needs_login": False, "title": title, "final_url": final_url,
            "text": text, "chars": len(text), "scrolls": scroll_steps, "lines": len(catalogued)}


async def _scrape_async(ws_url: str, surfaces: list, max_chars: int, scroll_steps: int,
                        dwell: float, settle: float) -> list:
    import websockets

    counter = 0
    results: list = []
    async with websockets.connect(ws_url, max_size=16 * 1024 * 1024, open_timeout=8) as ws:
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
            results.append(await _read_surface(call, s, max_chars, scroll_steps, dwell, settle))
    return results


def scrape_owner(cdp_url: str | None = None, surfaces: list | None = None, max_chars: int = 6000,
                 scroll_steps: int = 6, dwell: float = 1.8, settle: float = 3.5) -> dict:
    """Genuine, THOROUGH read of the owner's logged-in surfaces over CDP — scrolls + dwells + catalogues
    per surface (it takes its time). Returns {ok, surfaces:[{key,status,needs_login,text,chars,lines,
    scrolls,...}], logged_in:[keys], needs_login:[keys]}. A sign-in wall -> needs_login (no invention)."""
    cdp_url = cdp_url or "http://127.0.0.1:9222"
    surfaces = surfaces if surfaces is not None else DEFAULT_SURFACES
    ws_url = _page_ws_url(cdp_url)
    if not ws_url:
        return {"ok": False, "error": f"no debuggable Chrome page at {cdp_url}", "surfaces": []}
    args = (ws_url, surfaces, max_chars, scroll_steps, dwell, settle)
    try:
        signals = asyncio.run(_scrape_async(*args))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            signals = loop.run_until_complete(_scrape_async(*args))
        finally:
            loop.close()
    return {
        "ok": True,
        "surfaces": signals,
        "logged_in": [s["key"] for s in signals if s.get("status") == "ok"],
        "needs_login": [s["key"] for s in signals if s.get("needs_login")],
    }
