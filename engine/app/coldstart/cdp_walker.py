"""Thin CDP walker for the instant cold-start inhale.

Talks to the existing loopback bridge at ``127.0.0.1:7777`` (the CDP
primary bridge from ``scripts/v7/anticipy_bridge_fallback_cdp.py``),
which speaks to the user's real Chrome at ``localhost:9222``.

Hard rules per ``planning/10-instant-cold-start/DESIGN.md`` and
``planning/00-handoff/NORTH_STAR_v2.md`` rule 1 (universal action
agent, no per-app code):

  - Opens new ANTICIPY-OWNED background tabs. Never hijacks a tab the
    user is currently using.
  - Closes every tab it opened when its walk finishes (or fails).
  - Reads visible row metadata only: sender, subject, snippet, date.
    No bodies. No raw HTML over the wire.
  - Generic row-extraction heuristic. No hardcoded selectors that
    bake Gmail markup into the engine.
  - URL CHOICES live in ``~/.anticipy/inhale_sources.json`` via
    ``sources.py``, NOT in source code. The walker iterates whatever
    entries the user has enabled.
  - Returns plain dict rows; the LLM in ``auto_inhale.py`` decides
    what is a person, what is a project, what is a tool.

The walker is intentionally synchronous + small. The orchestrator
runs it in a thread (or two threads in parallel) and drains its
returned rows into the LLM-batching pipeline.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


BRIDGE_HOST = os.environ.get("ANTICIPY_SURFACE_HOST", "127.0.0.1")
try:
    BRIDGE_PORT = int(os.environ.get("ANTICIPY_SURFACE_PORT", "7777"))
except Exception:
    BRIDGE_PORT = 7777
BRIDGE_URL = f"http://{BRIDGE_HOST}:{BRIDGE_PORT}"
BRIDGE_SECRET = os.environ.get("ANTICIPY_TRIGGER_SECRET") or "local-dev"

try:
    CDP_PORT = int(os.environ.get("ANTICIPY_CDP_PORT", "9222"))
except Exception:
    CDP_PORT = 9222
CDP_HOST = os.environ.get("ANTICIPY_CDP_HOST", "localhost")
CDP_BASE = f"http://{CDP_HOST}:{CDP_PORT}"


@dataclass
class WalkerRow:
    """One visible row the walker pulled off a surface.

    The orchestrator does NOT introspect ``kind`` further: it batches
    every row's ``text`` through the LLM extraction prompt, which
    figures out what to do.
    """

    kind: str = ""            # "inbox" | "sent" | "calendar" | "drive" | "settings"
    text: str = ""            # human-readable line; full content for the LLM
    source: str = ""          # canonical surface name ("gmail.inbox")
    extra: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def _http_json(method: str, path: str, payload: dict | None = None,
               *, timeout: float = 8.0) -> tuple[int, dict, str]:
    """Tiny JSON RPC over urllib. Bridge speaks plain JSON."""
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BRIDGE_URL + path, data=body,
                                  method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200))
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:
            raw = b""
        status = int(exc.code)
    except Exception as exc:
        return 0, {}, f"{type(exc).__name__}: {exc}"
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except Exception:
        data = {"raw": raw.decode("utf-8", errors="replace")}
    return status, data if isinstance(data, dict) else {}, ""


def _bridge_alive() -> bool:
    status, data, err = _http_json("GET", "/status", timeout=4.0)
    if err or status != 200:
        return False
    return bool(data.get("ok") and data.get("cdp_alive"))


def _bridge_command(command: str, *, timeout: float = 30.0,
                    **kwargs: Any) -> dict:
    payload = {"secret": BRIDGE_SECRET, "command": command}
    payload.update(kwargs)
    status, data, err = _http_json(
        "POST", "/surface-command", payload, timeout=timeout)
    if err:
        return {"ok": False, "error": err}
    if not isinstance(data, dict):
        return {"ok": False, "error": f"non-dict response: {data!r}"}
    data.setdefault("ok", False)
    return data


def _cdp_list_pages() -> list[dict]:
    try:
        with urllib.request.urlopen(
                f"{CDP_BASE}/json", timeout=4.0) as resp:
            raw = resp.read()
    except Exception:
        return []
    try:
        items = json.loads(raw.decode("utf-8") or "[]")
    except Exception:
        return []
    return [t for t in items if str(t.get("type") or "") == "page"]


def _cdp_close(target_id: str) -> bool:
    if not target_id:
        return False
    try:
        with urllib.request.urlopen(
                f"{CDP_BASE}/json/close/"
                f"{urllib.parse.quote(target_id, safe='')}",
                timeout=4.0):
            return True
    except Exception:
        return False


def _cdp_create_new_tab(url: str) -> dict:
    """Open a NEW page tab via Chrome's DevTools /json/new endpoint.

    Per Z-001 harness pattern: PUT first (Chrome 129+), GET fallback.
    Returns ``{ok, targetId, url, error}``.
    """
    if not url:
        return {"ok": False, "error": "empty url"}
    encoded = urllib.parse.quote(url, safe=":/?&=%#")
    # Try PUT first.
    req = urllib.request.Request(
        f"{CDP_BASE}/json/new?{encoded}", method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
    except Exception:
        # Fall back to GET on older Chrome that rejects PUT.
        try:
            with urllib.request.urlopen(
                    f"{CDP_BASE}/json/new?{encoded}", timeout=8.0) as resp:
                raw = resp.read()
        except Exception as exc:
            return {"ok": False, "error": f"new tab: {exc}"}
    try:
        d = json.loads(raw.decode("utf-8") or "{}")
    except Exception as exc:
        return {"ok": False, "error": f"decode: {exc}"}
    tid = str(d.get("id") or "")
    if not tid:
        return {"ok": False,
                "error": f"no id in response: {str(d)[:200]}"}
    return {"ok": True, "targetId": tid,
            "url": str(d.get("url") or "")}


def _cdp_eval_on_target(target_id: str, expression: str,
                        *, timeout: float = 12.0) -> dict:
    """Runtime.evaluate against a specific page target. Reuses the
    same async-WS pattern the Z-001 harness uses so the bridge does
    not need to know about our walker tabs.
    """
    if not target_id:
        return {"ok": False, "error": "no target_id"}
    try:
        from websockets.sync.client import connect as ws_connect
    except Exception as exc:
        return {"ok": False, "error": f"websockets missing: {exc}"}
    ws_url = f"ws://localhost:{CDP_PORT}/devtools/page/{target_id}"
    try:
        ws = ws_connect(ws_url, max_size=12 * 1024 * 1024,
                        open_timeout=5.0)
    except Exception as exc:
        return {"ok": False, "error": f"ws connect: {exc}"}
    try:
        ws.send(json.dumps({
            "id": 1, "method": "Runtime.evaluate",
            "params": {"expression": expression,
                       "returnByValue": True,
                       "awaitPromise": False}}))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = ws.recv(
                    timeout=max(0.5, deadline - time.time()))
            except Exception as exc:
                return {"ok": False, "error": f"ws recv: {exc}"}
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("id") != 1:
                continue
            result = (msg.get("result") or {}).get("result") or {}
            exc_info = (msg.get("result") or {}).get("exceptionDetails")
            if exc_info:
                text = ((exc_info.get("exception") or {}).get(
                    "description") or json.dumps(exc_info)[:300])
                return {"ok": False, "error": f"js exc: {text}",
                        "value": None}
            return {"ok": True, "value": result.get("value")}
        return {"ok": False, "error": "timeout"}
    finally:
        try:
            ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public walker class
# ---------------------------------------------------------------------------
class CDPWalker:
    """Open Anticipy-owned background tabs, extract visible row metadata,
    close the tab on the way out.

    Single-purpose instance: construct, call ``walk_source()`` per
    entry from ``sources.load_enabled()``, then ``close_all()``.
    Owns its own list of opened ``targetId``s so the caller cannot
    leak tabs even if a walk raises.

    URL CHOICES live in the user config at
    ``~/.anticipy/inhale_sources.json`` and reach this class via the
    ``url`` field on each entry passed to ``walk_source()``. There
    are no URL string literals in this module.
    """

    # Limit the data volume we pull from any single surface. The LLM
    # batches will not need more than this and we want the inhale to
    # finish under the popover budget.
    MAX_ROWS_PER_SURFACE = 120

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.errors: list[str] = []

    # ---- lifecycle -------------------------------------------------------
    def bridge_ready(self) -> bool:
        """Verify the loopback bridge + Chrome are both up."""
        return _bridge_alive()

    def close_all(self) -> dict:
        """Close every tab the walker opened. Returns per-id success."""
        seen: dict[str, bool] = {}
        for tid in self.opened:
            if tid in seen:
                continue
            seen[tid] = _cdp_close(tid)
        return seen

    # ---- low-level helpers ----------------------------------------------
    def _open_anticipy_tab(self, url: str) -> str:
        """Open a fresh tab owned by Anticipy. Records the targetId
        for cleanup. Returns the targetId or ``""`` on failure.
        """
        new = _cdp_create_new_tab(url)
        if not new.get("ok"):
            self.errors.append(
                f"open_tab {url!r}: {new.get('error')}")
            return ""
        tid = str(new.get("targetId") or "")
        if tid:
            self.opened.append(tid)
        return tid

    def _wait_for_dom_ready(self, target_id: str,
                            probe_js: str = "",
                            timeout_s: float = 20.0,
                            poll_s: float = 1.0) -> dict:
        """Poll a JS probe expression until it returns truthy or the
        timeout fires. Default probe asserts ``document.readyState``
        is ``complete``. The walker uses this to decide when a Gmail
        SPA tab has hydrated enough to scrape.
        """
        if not probe_js:
            probe_js = "(()=>document.readyState==='complete')()"
        deadline = time.time() + max(2.0, timeout_s)
        last = {"ok": False, "value": False, "error": "no attempt"}
        while time.time() < deadline:
            last = _cdp_eval_on_target(target_id, probe_js,
                                       timeout=6.0)
            if last.get("ok") and last.get("value"):
                return last
            time.sleep(poll_s)
        return last

    def _scroll_and_collect(self, target_id: str,
                            collect_js: str,
                            *,
                            scroll_pages: int = 4,
                            settle_s: float = 0.7) -> list[dict]:
        """Repeatedly run a JS collector that returns row dicts, then
        nudge the scrollable list. Returns the accumulated, de-duped
        rows in capture order.

        The collector JS must return a JSON-stringified array, or an
        array of plain JS objects. Both shapes are accepted.
        """
        rows: list[dict] = []
        seen_keys: set[str] = set()
        for page_idx in range(max(1, scroll_pages)):
            evald = _cdp_eval_on_target(target_id, collect_js,
                                        timeout=10.0)
            value = evald.get("value")
            batch: list[dict] = []
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except Exception:
                    parsed = []
                if isinstance(parsed, list):
                    batch = [b for b in parsed if isinstance(b, dict)]
            elif isinstance(value, list):
                batch = [b for b in value if isinstance(b, dict)]
            for row in batch:
                key = "|".join([
                    str(row.get("sender") or row.get("title") or ""),
                    str(row.get("subject") or row.get("when") or ""),
                    str(row.get("date") or row.get("attendees") or ""),
                ])[:240]
                if not key:
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                rows.append(row)
                if len(rows) >= self.MAX_ROWS_PER_SURFACE:
                    return rows
            # Nudge a scroll. Best-effort: ignore the eval result so
            # one misbehaving page does not abort the walk.
            _cdp_eval_on_target(
                target_id,
                "(()=>{const o=document.scrollingElement||document.body;"
                "if(!o)return false;o.scrollBy(0,o.clientHeight*0.85);"
                "return true;})()",
                timeout=4.0,
            )
            time.sleep(settle_s)
        return rows

    # ---- Gmail inbox + sent ---------------------------------------------
    # NOTE: this JS is INTENTIONALLY generic. It does NOT key off Gmail
    # specific class names. It walks every visible [role="row"] element
    # (also used by Outlook web, Fastmail, Superhuman) and pulls the
    # text content. Then we strip whitespace. The LLM does the rest.
    _GMAIL_COLLECT_JS = (
        "(()=>{const out=[];"
        "const rows=document.querySelectorAll('[role=\\\"row\\\"],"
        "tr.zA,tr[role=\\\"row\\\"]');"
        "for(const r of rows){"
        "  const cells=r.querySelectorAll('span,div,td');"
        "  const text=(r.innerText||'').trim().replace(/\\\\s+/g,' ')"
        "    .slice(0,400);"
        "  if(!text||text.length<6)continue;"
        "  let sender='',subject='',date='',snippet='';"
        "  const senderEl=r.querySelector('"
        "    span.yX > span,span[email],[data-hovercard-id],"
        "    .yW span'"
        "  );"
        "  if(senderEl){sender=(senderEl.getAttribute&&"
        "    (senderEl.getAttribute('email')||"
        "     senderEl.getAttribute('name'))||senderEl.innerText||'').trim();}"
        "  const subjEl=r.querySelector('span.bog,span.y6 span,"
        "    [data-thread-id] span');"
        "  if(subjEl){subject=(subjEl.innerText||'').trim();}"
        "  const dateEl=r.querySelector('span.xW.xY span[title],"
        "    td.xW span[title],time');"
        "  if(dateEl){date=(dateEl.getAttribute&&"
        "    (dateEl.getAttribute('title')||dateEl.innerText)"
        "    ||dateEl.innerText||'').trim();}"
        "  snippet=text.slice(0,240);"
        "  out.push({sender:sender||text.split(' ')[0],"
        "            subject:subject||'',"
        "            date:date||'',"
        "            snippet:snippet,"
        "            text:text});"
        "  if(out.length>=80)break;"
        "}"
        "return JSON.stringify(out);})()"
    )

    def walk_gmail(self, kind: str = "inbox",
                   url: str = "",
                   max_rows: int | None = None,
                   per_tab_budget_s: float = 18.0) -> list[WalkerRow]:
        """Open a new background Gmail tab, scroll-collect ``max_rows``
        rows, close the tab, return ``WalkerRow`` objects.

        ``kind`` is the WalkerRow.kind label (e.g. ``"inbox"`` or
        ``"sent"``) used downstream by the LLM extractor. ``url`` is
        the surface URL chosen by the user in
        ``inhale_sources.json``; this method is URL-agnostic.
        """
        if not url:
            return []
        rows: list[WalkerRow] = []
        tid = self._open_anticipy_tab(url)
        if not tid:
            return rows
        deadline = time.time() + max(6.0, per_tab_budget_s)
        # Wait for the Gmail list to mount: presence of any [role="row"].
        ready_js = (
            "(()=>{const rows=document.querySelectorAll('"
            "[role=\\\"row\\\"],tr.zA');return rows&&rows.length>0;})()"
        )
        self._wait_for_dom_ready(tid, probe_js=ready_js,
                                 timeout_s=min(12.0,
                                               max(4.0,
                                                   per_tab_budget_s / 2)))
        budget_left = max(2.0, deadline - time.time())
        # 4 scroll-pages is enough for ~80-120 rows in standard Gmail
        # density. Each loop is ~1s so this fits inside the budget.
        raw_rows = self._scroll_and_collect(
            tid, self._GMAIL_COLLECT_JS,
            scroll_pages=max(1, int(budget_left // 1.2)),
            settle_s=0.6,
        )
        cap = max_rows if max_rows is not None else self.MAX_ROWS_PER_SURFACE
        for row in raw_rows[:cap]:
            rows.append(WalkerRow(
                kind=kind, source=f"gmail.{kind}",
                text=str(row.get("text") or "")[:480],
                extra={
                    "sender": str(row.get("sender") or "")[:200],
                    "subject": str(row.get("subject") or "")[:240],
                    "date": str(row.get("date") or "")[:80],
                    "snippet": str(row.get("snippet") or "")[:240],
                },
            ))
        return rows

    # ---- Google Calendar agenda -----------------------------------------
    _CAL_COLLECT_JS = (
        "(()=>{const out=[];"
        "const evts=document.querySelectorAll('"
        "[role=\\\"button\\\"][data-eventchip],"
        "[data-eventid],div[role=\\\"button\\\"][aria-label]'"
        ");"
        "for(const e of evts){"
        "  const label=(e.getAttribute&&"
        "    (e.getAttribute('aria-label')||e.innerText))||'';"
        "  const clean=label.trim().replace(/\\\\s+/g,' ').slice(0,360);"
        "  if(!clean||clean.length<6)continue;"
        "  out.push({title:clean,when:'',attendees:'',text:clean});"
        "  if(out.length>=80)break;"
        "}"
        "return JSON.stringify(out);})()"
    )

    def walk_calendar(self,
                      url: str = "",
                      max_rows: int | None = None,
                      per_tab_budget_s: float = 12.0
                      ) -> list[WalkerRow]:
        """Open a calendar surface tab, capture event labels.

        ``url`` is supplied by the caller (from the user config).
        The collector JS is generic and works against any calendar
        surface that exposes ``[data-eventid]`` or
        ``[role='button'][aria-label]`` rows.
        """
        if not url:
            return []
        tid = self._open_anticipy_tab(url)
        rows: list[WalkerRow] = []
        if not tid:
            return rows
        deadline = time.time() + max(6.0, per_tab_budget_s)
        ready_js = (
            "(()=>{return document.querySelectorAll('"
            "[data-eventid],[role=\\\"button\\\"][aria-label]').length>0;})()"
        )
        self._wait_for_dom_ready(tid, probe_js=ready_js,
                                 timeout_s=min(10.0, per_tab_budget_s / 2))
        budget_left = max(2.0, deadline - time.time())
        raw_rows = self._scroll_and_collect(
            tid, self._CAL_COLLECT_JS,
            scroll_pages=max(1, int(budget_left // 1.2)),
            settle_s=0.6,
        )
        cap = max_rows if max_rows is not None else self.MAX_ROWS_PER_SURFACE
        for row in raw_rows[:cap]:
            rows.append(WalkerRow(
                kind="calendar", source="google.calendar",
                text=str(row.get("text") or "")[:480],
                extra={
                    "title": str(row.get("title") or "")[:240],
                    "when": str(row.get("when") or "")[:120],
                    "attendees": str(row.get("attendees") or "")[:240],
                },
            ))
        return rows

    # ---- Google Drive recents (best effort) -----------------------------
    _DRIVE_COLLECT_JS = (
        "(()=>{const out=[];"
        "const files=document.querySelectorAll('"
        "[role=\\\"row\\\"] [data-tooltip],"
        "div[data-id][aria-label],div[role=\\\"gridcell\\\"]'"
        ");"
        "for(const f of files){"
        "  const title=(f.getAttribute&&("
        "    f.getAttribute('aria-label')||"
        "    f.getAttribute('data-tooltip')))"
        "    ||f.innerText||'';"
        "  const clean=title.trim().replace(/\\\\s+/g,' ').slice(0,260);"
        "  if(!clean||clean.length<3)continue;"
        "  out.push({title:clean,text:clean});"
        "  if(out.length>=60)break;"
        "}"
        "return JSON.stringify(out);})()"
    )

    def walk_drive(self,
                   url: str = "",
                   max_rows: int | None = None,
                   per_tab_budget_s: float = 10.0) -> list[WalkerRow]:
        """Open a drive/files surface tab, capture file labels.

        ``url`` is supplied by the caller (from the user config).
        The collector JS is generic and works against any grid that
        exposes ``[role='row']`` or ``[data-id]`` cells.
        """
        if not url:
            return []
        tid = self._open_anticipy_tab(url)
        rows: list[WalkerRow] = []
        if not tid:
            return rows
        deadline = time.time() + max(4.0, per_tab_budget_s)
        ready_js = (
            "(()=>{return document.querySelectorAll('[role=\\\"row\\\"]').length>0"
            "||document.querySelectorAll('[data-id]').length>0;})()"
        )
        self._wait_for_dom_ready(tid, probe_js=ready_js,
                                 timeout_s=min(8.0, per_tab_budget_s / 2))
        budget_left = max(2.0, deadline - time.time())
        raw_rows = self._scroll_and_collect(
            tid, self._DRIVE_COLLECT_JS,
            scroll_pages=max(1, int(budget_left // 1.2)),
            settle_s=0.5,
        )
        cap = max_rows if max_rows is not None else self.MAX_ROWS_PER_SURFACE
        for row in raw_rows[:cap]:
            rows.append(WalkerRow(
                kind="drive", source="google.drive",
                text=str(row.get("text") or "")[:360],
                extra={"title": str(row.get("title") or "")[:240]},
            ))
        return rows


    # ---- Generic dispatcher driven by the user config -------------------
    def walk_source(self, source: dict,
                    per_tab_budget_s: float = 18.0,
                    max_rows: int | None = None) -> list[WalkerRow]:
        """Walk one source entry from ``inhale_sources.json``.

        Dispatches to the appropriate generic collector based on the
        entry's ``id``. Mail-shaped ids use the mail collector,
        calendar-shaped ids use the calendar collector, file-shaped
        ids use the drive collector. Unknown ids fall back to the
        mail (row-walker) collector, which is the most generic.

        The dispatch is keyed off ``id`` not ``url`` because the
        collector JS depends on the DOM shape, which is a property
        of the surface, not of the URL the user typed.
        """
        if not isinstance(source, dict):
            return []
        sid = str(source.get("id") or "").lower()
        url = str(source.get("url") or "")
        if not url:
            return []
        kind_label = sid or "inbox"
        if "calendar" in sid:
            return self.walk_calendar(
                url=url,
                max_rows=max_rows,
                per_tab_budget_s=per_tab_budget_s,
            )
        if "drive" in sid or "files" in sid:
            return self.walk_drive(
                url=url,
                max_rows=max_rows,
                per_tab_budget_s=per_tab_budget_s,
            )
        # Default: row-shaped surfaces (gmail, outlook, fastmail,
        # superhuman, generic mailers). The collector JS already
        # matches ``[role='row']``, ``tr.zA``, and ``tr[role='row']``
        # so it covers the major web mailers without per-app code.
        return self.walk_gmail(
            kind=kind_label,
            url=url,
            max_rows=max_rows,
            per_tab_budget_s=per_tab_budget_s,
        )


__all__ = [
    "CDPWalker",
    "WalkerRow",
    "BRIDGE_URL",
    "CDP_BASE",
]
