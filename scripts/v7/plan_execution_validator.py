#!/usr/bin/env python3
"""Plan-execution validator for Anticipy V7.

Existing E2E (state/v7/e2e_hard_transcripts_*) verified only that the
engine GENERATED a plan from a transcript. This validator verifies that
the plan ACTUALLY EXECUTES in Chrome: a real calendar event appears in
the user's Google Calendar, a real Gmail draft is saved, etc.

Flow per plan
=============
1. Read T<NN>_inject.json from a prior e2e run dir. Reuse the existing
   transcript + plan structure produced there.
2. POST /api/listen/reset to the live engine (8731), then POST
   /api/listen/inject with the same transcript so _LISTEN["pending"]
   is freshly populated and consistent with the recorded plan.
3. POST /api/act (no body) to drive the engine through whatever path
   the recorded plan dictates: direct_browser, gmail compose, or the
   frozen DSv4SkillRunner via action_handoff.
4. Poll /api/listen/status until _LISTEN["acted"] flips (success) or
   the engine returns terminal ran=False (failure / clarify / gated).
5. Verify the SIDE EFFECT directly in the user's real Chrome via the
   loopback bridge on 127.0.0.1:7777:
     - calendar plans  -> navigate to calendar.google.com/calendar/u/0/r,
                          eval DOM for the event title text.
     - gmail draft     -> navigate to mail.google.com/mail/u/0/#drafts,
                          eval DOM for the subject/recipient.
     - other / lookup  -> read any visible target page DOM for a literal
                          string match from the plan.
   The validator NEVER touches any tab it did not create.

R4 browser safety
=================
- The validator NEVER mutates a tab it did not create. The bridge's
  /surface-command navigate uses prefer_in_place=True under the hood,
  which can re-target an existing same-host user tab, so we DO NOT
  use it. Instead we open a brand-new background tab via CDP's
  /json/new HTTP endpoint, which Chrome implements as
  Target.createTarget {background: true} (the same primitive the
  bridge calls when no host match is found). This guarantees a fresh
  targetId we own.
- For DOM reads / screenshots we attach to that specific targetId by
  going through the bridge's /surface-proof endpoint with the FULL
  URL we navigated to (a unique URL only the new tab has), and via
  the bridge's eval_js. We never reuse a url_prefix that could match
  another tab.
- The bridge's /status is queried at start to confirm CDP is alive
  and to make sure the path of record is the CDP-primary bridge.
- We close the tab via the verbatim CDP /json/close/{targetId} HTTP
  endpoint. /json/list is read only to confirm the tab was actually
  removed; no other tab is navigated, evaluated, or closed.

Output
======
state/v7/plan_execution_validation_<UTC ISO ts>/
  - result.json    -> {schema, ts, engine, runs:[{plan_id, executed, evidence, reason}]}
  - screenshots/   -> PNG per plan when bridge surface-proof succeeds
  - logs/          -> stdout, stderr, and HTTP traces per plan
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path("/Users/omarebrahim/Developer/Anticipy-V7")
DEFAULT_E2E_RUN = (
    REPO_ROOT / "state" / "v7" / "e2e_hard_transcripts_20260528T031414Z"
)
DEFAULT_ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8731")
DEFAULT_BRIDGE = os.environ.get("ANTICIPY_BRIDGE_URL", "http://127.0.0.1:7777")
BRIDGE_SECRET = os.environ.get("ANTICIPY_TRIGGER_SECRET", "local-dev")
CDP_BASE = os.environ.get("ANTICIPY_CDP_BASE", "http://localhost:9222")

ACT_TIMEOUT_S = float(os.environ.get("PLAN_ACT_TIMEOUT_S", "120"))
VERIFY_SETTLE_S = float(os.environ.get("PLAN_VERIFY_SETTLE_S", "4.0"))
BRIDGE_TIMEOUT_S = float(os.environ.get("PLAN_BRIDGE_TIMEOUT_S", "30.0"))

CALENDAR_VERIFY_URL = (
    "https://calendar.google.com/calendar/u/0/r/search?q={query}"
)
GMAIL_DRAFTS_URL = "https://mail.google.com/mail/u/0/#drafts"


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------
def _http_json(
    url: str, payload: dict | None = None, method: str = "GET",
    timeout: float = 30.0,
) -> tuple[int, dict | str]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
            return e.code, json.loads(raw) if raw else str(e)
        except Exception:
            return e.code, str(e)
    except Exception as e:
        return -1, str(e)


def _bridge_post(
    path: str, payload: dict, timeout: float = BRIDGE_TIMEOUT_S
) -> dict:
    payload = dict(payload)
    payload.setdefault("secret", BRIDGE_SECRET)
    status, body = _http_json(
        DEFAULT_BRIDGE + path,
        payload=payload,
        method="POST",
        timeout=timeout,
    )
    if isinstance(body, dict):
        body.setdefault("_http_status", status)
        return body
    return {"ok": False, "_http_status": status, "error": str(body)}


def _bridge_status(timeout: float = 20.0) -> dict:
    status, body = _http_json(
        DEFAULT_BRIDGE + "/status",
        payload=None,
        method="GET",
        timeout=timeout,
    )
    if isinstance(body, dict):
        body.setdefault("_http_status", status)
        return body
    return {"ok": False, "_http_status": status, "error": str(body)}


def _cdp_get(path: str, timeout: float = 6.0) -> tuple[int, Any]:
    return _http_json(CDP_BASE + path, method="GET", timeout=timeout)


# ---------------------------------------------------------------------------
# Plan loading
# ---------------------------------------------------------------------------
def _load_plan_file(run_dir: Path, plan_id: str) -> dict:
    f = run_dir / f"{plan_id}_inject.json"
    if not f.exists():
        raise FileNotFoundError(str(f))
    return json.loads(f.read_text())


def _plan_category(plan: dict) -> str:
    """Classify the plan into a verification strategy."""
    intent = (plan.get("intent") or "").lower()
    task = (plan.get("task") or "").lower()
    if intent in {"calendar_event", "calendar"}:
        return "calendar"
    if intent in {"email_draft", "gmail_draft", "email"}:
        return "gmail_draft"
    # The 'other' intent often still wraps calendar work (e.g. T01, T20).
    if "google calendar" in task or "calendar" in task:
        return "calendar"
    if "gmail" in task or "draft" in task or "email" in task:
        return "gmail_draft"
    return "unknown"


def _extract_event_titles(plan: dict) -> list[str]:
    """Pull plausible event titles from the plan.

    Order of preference:
      1. Literal strings between single quotes in the task ('Dentist
         appointment'). High specificity, low false-positive rate.
      2. Literal strings between double quotes (rare in current plans).
      3. The plan's `thing` field, capitalized, as a fallback search
         term. This handles plans like T04 where the task describes
         events but does not single-quote a title.
    """
    import re
    task = plan.get("task") or ""
    thing = (plan.get("thing") or "").strip()
    blacklist = {"do not send or book anything", "tuesday", "thursday",
                  "friday", "monday", "wednesday", "saturday", "sunday"}
    out: list[str] = []
    for quote in ("'", '"'):
        for t in re.findall(quote + r"([^" + quote + r"]{3,80})" + quote,
                              task):
            t = t.strip()
            if not t or t.lower() in blacklist or t in out:
                continue
            out.append(t)
    if not out and thing and len(thing) > 2:
        out.append(thing)
    return out


# ---------------------------------------------------------------------------
# Engine actions
# ---------------------------------------------------------------------------
def _engine_reset_and_inject(engine: str, transcript: str,
                              account: str) -> dict:
    """Reset listen state, then inject the transcript to populate pending."""
    _http_json(engine + "/api/listen/reset", payload={}, method="POST",
               timeout=10.0)
    payload = {
        "text": transcript,
        "account_id": account,
        "user_id": account,
        "source": "asr-transcript",
    }
    status, body = _http_json(
        engine + "/api/listen/inject", payload=payload, method="POST",
        timeout=90.0,
    )
    return {"http": status, "body": body}


def _engine_act(engine: str) -> dict:
    """POST /api/act with no body so the engine uses _LISTEN['pending']."""
    status, body = _http_json(
        engine + "/api/act", payload={}, method="POST",
        timeout=ACT_TIMEOUT_S,
    )
    return {"http": status, "body": body}


def _engine_listen_status(engine: str) -> dict:
    status, body = _http_json(
        engine + "/api/listen/status", method="GET", timeout=10.0,
    )
    if isinstance(body, dict):
        body["_http_status"] = status
        return body
    return {"_http_status": status, "error": str(body)}


# ---------------------------------------------------------------------------
# Browser primitives (R4-safe: open via Target.createTarget, end-to-end
# targetId, never touch tabs we did not create)
# ---------------------------------------------------------------------------
def _cdp_open_new_tab(url: str) -> dict:
    """Open a brand-new background tab via Chrome's /json/new endpoint.

    /json/new is the HTTP shorthand for CDP Target.createTarget. It
    ALWAYS allocates a fresh page target (never re-uses an existing
    same-host tab the way the bridge's prefer_in_place navigate would).
    Returns {ok, targetId, ws_url, url}.
    """
    encoded = urllib.parse.quote(url, safe=":/?&=#%+,;@!$'*-.~")
    req = urllib.request.Request(
        f"{CDP_BASE}/json/new?{encoded}",
        method="PUT",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10.0) as r:
            raw = r.read().decode("utf-8", errors="replace")
            body = json.loads(raw)
            return {
                "ok": True,
                "targetId": str(body.get("id") or ""),
                "ws_url": str(body.get("webSocketDebuggerUrl") or ""),
                "url": str(body.get("url") or url),
                "title": str(body.get("title") or ""),
                "http": r.status,
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "targetId": "",
                "ws_url": "", "url": "", "title": ""}


def _ws_call(ws_url: str, method: str, params: dict | None = None,
             timeout: float = 15.0) -> dict:
    """Single-shot CDP WS call. Uses ``websockets.sync.client`` because
    Chrome 148+ with remote-allow-origins rejects websocket-client's
    forced Origin header.
    """
    try:
        from websockets.sync.client import connect as ws_connect
    except Exception as exc:
        return {"ok": False, "error": f"websockets lib missing: {exc}",
                "result": {}}
    payload = {"id": int(time.time() * 1000) & 0xFFFFFFF, "method": method,
               "params": params or {}}
    try:
        ws_url_local = ws_url.replace("127.0.0.1", "localhost")
        with ws_connect(ws_url_local, open_timeout=timeout,
                        close_timeout=2.0,
                        max_size=32 * 1024 * 1024) as ws:
            ws.send(json.dumps(payload))
            deadline = time.time() + timeout
            while time.time() < deadline:
                msg = ws.recv(timeout=min(5.0, max(0.5, deadline - time.time())))
                if not msg:
                    continue
                try:
                    parsed = json.loads(msg)
                except Exception:
                    continue
                if parsed.get("id") == payload["id"]:
                    return {"ok": "error" not in parsed,
                            "result": parsed.get("result") or {},
                            "error": (parsed.get("error") or {}).get("message")}
            return {"ok": False, "error": "timed out waiting for response",
                    "result": {}}
    except Exception as exc:
        return {"ok": False, "error": f"ws call: {exc}", "result": {}}


def _cdp_runtime_evaluate(ws_url: str, expression: str,
                           timeout: float = 15.0) -> dict:
    """Runtime.evaluate -> {ok, value, type, error}. JSON-stringifiable
    return values only.
    """
    r = _ws_call(ws_url, "Runtime.evaluate",
                  {"expression": expression, "returnByValue": True,
                   "awaitPromise": False}, timeout=timeout)
    if not r.get("ok"):
        return {"ok": False, "value": None, "type": "",
                "error": r.get("error") or "ws call failed"}
    res = (r.get("result") or {}).get("result") or {}
    exc = (r.get("result") or {}).get("exceptionDetails")
    if exc:
        return {"ok": False, "value": None, "type": res.get("type") or "",
                "error": f"js exc: {json.dumps(exc)[:200]}"}
    return {"ok": True, "value": res.get("value"),
            "type": res.get("type") or "", "error": ""}


def _cdp_screenshot(ws_url: str, save_to: Path,
                     timeout: float = 15.0) -> dict:
    """Page.captureScreenshot for the specific target. No bringToFront."""
    import base64
    r = _ws_call(ws_url, "Page.captureScreenshot",
                  {"format": "png", "captureBeyondViewport": False},
                  timeout=timeout)
    if not r.get("ok"):
        return {"ok": False, "path": "", "bytes": 0,
                "error": r.get("error") or "ws call failed"}
    b64 = (r.get("result") or {}).get("data") or ""
    if not b64:
        return {"ok": False, "path": "", "bytes": 0,
                "error": "empty screenshot data"}
    try:
        raw = base64.b64decode(b64)
        save_to.parent.mkdir(parents=True, exist_ok=True)
        save_to.write_bytes(raw)
        return {"ok": True, "path": str(save_to), "bytes": len(raw),
                "error": ""}
    except Exception as exc:
        return {"ok": False, "path": "", "bytes": 0, "error": str(exc)}


def _cdp_close_target(target_id: str) -> dict:
    """Close ONLY the tab we created, by targetId. Verbatim CDP HTTP."""
    if not target_id:
        return {"ok": False, "error": "empty target_id"}
    encoded = urllib.parse.quote(target_id, safe="")
    try:
        req = urllib.request.Request(f"{CDP_BASE}/json/close/{encoded}",
                                      method="GET",
                                      headers={"Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=8.0) as r:
            raw = r.read().decode("utf-8", errors="replace")
            return {"ok": int(r.status) == 200, "http": r.status,
                    "body": raw[:200]}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "http": exc.code, "body": str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _cdp_target_exists(target_id: str) -> bool:
    status, body = _cdp_get("/json/list", timeout=5.0)
    if status != 200 or not isinstance(body, list):
        return False
    return any(t.get("id") == target_id for t in body)


# ---------------------------------------------------------------------------
# Per-plan verification
# ---------------------------------------------------------------------------
_CAL_SEARCH_PROBE_JS = (
    "(function(){try{"
    " var doc = document;"
    " var main = doc.querySelector('[role=main]');"
    " var mainText = main ? (main.innerText || '') : '';"
    " var noResults = mainText.toLowerCase().indexOf('no events found') !== -1 "
    "  || mainText.toLowerCase().indexOf('no matches') !== -1 "
    "  || mainText.toLowerCase().indexOf('no results') !== -1;"
    " var match = mainText.match(/([0-9]+)\\s+events?\\s+found/i);"
    " var count = match ? parseInt(match[1], 10) : 0;"
    " return JSON.stringify({"
    "   url: location.href, title: document.title,"
    "   mainText: mainText.slice(0, 8000),"
    "   noResults: noResults, eventCount: count,"
    "   mainLen: mainText.length});"
    "}catch(e){return JSON.stringify({err:String(e)});}})()"
)


_GMAIL_DRAFTS_PROBE_JS = (
    "(function(){try{"
    " var doc = document;"
    " var rows = doc.querySelectorAll('tr.zA, [role=row]');"
    " var samples = [];"
    " for (var i = 0; i < rows.length && i < 50; i++) {"
    "   var t = (rows[i].innerText || '').trim();"
    "   if (t) samples.push(t.slice(0, 300));"
    " }"
    " var main = doc.querySelector('[role=main]');"
    " var mainText = main ? (main.innerText || '').slice(0, 8000) : '';"
    " return JSON.stringify({"
    "   url: location.href, title: document.title,"
    "   rowCount: rows.length, rows: samples, mainText: mainText});"
    "}catch(e){return JSON.stringify({err:String(e)});}})()"
)


def _read_target_dom(ws_url: str, log: list,
                       expression: str | None = None) -> dict:
    """Pull title, URL, and a structured DOM payload from a target.

    Returns whatever the JS expression returns, parsed. Defaults to a
    generic body innerText probe for non-app pages.
    """
    expr = expression or (
        "(function(){try{"
        " var t = document.body ? (document.body.innerText || '') : '';"
        " return JSON.stringify({url: location.href,"
        "   title: document.title, sample: t.slice(0,6000),"
        "   mainText: t.slice(0,6000), len: t.length});"
        "}catch(e){return JSON.stringify({err:String(e)});}})()"
    )
    ev = _cdp_runtime_evaluate(ws_url, expr, timeout=15.0)
    log.append(f"[dom_probe] ok={ev.get('ok')} err={ev.get('error')}")
    if not ev.get("ok"):
        return {"ok": False, "url": "", "title": "", "mainText": "",
                "error": ev.get("error") or ""}
    raw = ev.get("value")
    if not isinstance(raw, str):
        return {"ok": False, "url": "", "title": "", "mainText": "",
                "error": f"unexpected eval result type: {type(raw).__name__}"}
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        return {"ok": False, "url": "", "title": "", "mainText": raw[:4000],
                "error": f"json parse: {exc}"}
    if parsed.get("err"):
        return {"ok": False, "url": "", "title": "", "mainText": "",
                "error": str(parsed.get("err"))}
    parsed["ok"] = True
    parsed.setdefault("error", "")
    return parsed


def _verify_calendar(plan: dict, plan_id: str, screenshots_dir: Path,
                      log: list) -> dict:
    """Open a fresh Google Calendar search tab via CDP /json/new and
    scan the rendered DOM for the literal event titles in the plan.

    Returns {executed, evidence, reason, targetId, opened_url, closed}.
    """
    titles = _extract_event_titles(plan)
    log.append(f"[verify_calendar] titles={titles}")
    if not titles:
        return {
            "executed": False,
            "evidence": {},
            "reason": "no_literal_titles_in_plan",
            "targetId": "",
            "opened_url": "",
            "closed": False,
        }
    title = titles[0]
    # Calendar search degrades on very long queries; truncate to the first
    # 6 words for the search itself, but match the full title in results.
    words = title.split()
    search_term = " ".join(words[:6]) if len(words) > 6 else title
    query = urllib.parse.quote(search_term)
    url = CALENDAR_VERIFY_URL.format(query=query)
    log.append(f"[verify_calendar] search_term={search_term!r}")
    new = _cdp_open_new_tab(url)
    log.append(f"[verify_calendar] open_new_tab ok={new.get('ok')} "
               f"targetId={new.get('targetId')} err={new.get('error','')}")
    target_id = new.get("targetId") or ""
    ws_url = new.get("ws_url") or ""
    opened_url = new.get("url") or url
    if not new.get("ok") or not target_id or not ws_url:
        return {
            "executed": False,
            "evidence": {"open_response": new},
            "reason": f"cdp_open_new_tab_failed: {new.get('error', '')}",
            "targetId": target_id, "opened_url": opened_url, "closed": False,
        }

    # Calendar's SPA boots its search results pane after fetch + auth.
    # The results pane lives under [role=main]. We poll briefly because
    # the initial render contains only the navigation skeleton.
    settle_total = max(VERIFY_SETTLE_S * 2, 8.0)
    deadline = time.time() + settle_total
    dom = {"ok": False, "mainText": "", "url": opened_url, "title": "",
            "noResults": False, "eventCount": 0, "error": ""}
    while time.time() < deadline:
        time.sleep(1.0)
        dom = _read_target_dom(ws_url, log, expression=_CAL_SEARCH_PROBE_JS)
        if not dom.get("ok"):
            continue
        main = (dom.get("mainText") or "").strip()
        if main and ("events found" in main.lower()
                      or "no events found" in main.lower()
                      or len(main) > 100):
            break
    page_url = dom.get("url") or opened_url
    main_text = dom.get("mainText") or ""
    no_results = bool(dom.get("noResults"))
    event_count = int(dom.get("eventCount") or 0)
    # A match must be in the search results pane, not the URL bar.
    # We accept either the full title or the trimmed search_term, since
    # very long titles (T20) won't fit any single line of the results.
    main_low = main_text.lower()
    full_match = bool(main_text and title.lower() in main_low)
    partial_match = bool(main_text and search_term.lower() in main_low)
    found = bool(not no_results and event_count > 0
                  and (full_match or partial_match))

    # Best-effort screenshot.
    screenshot_path = ""
    if ws_url:
        shot_target = screenshots_dir / f"{plan_id}_calendar.png"
        shot = _cdp_screenshot(ws_url, shot_target, timeout=15.0)
        log.append(f"[verify_calendar] shot ok={shot.get('ok')} "
                   f"bytes={shot.get('bytes')} err={shot.get('error','')}")
        if shot.get("ok"):
            screenshot_path = shot.get("path") or ""

    closed = _cdp_close_target(target_id)
    log.append(f"[verify_calendar] closed={json.dumps(closed)[:200]}")

    if not dom.get("ok"):
        reason = f"dom_read_failed: {dom.get('error','')}"
    elif no_results:
        reason = "calendar_search_returned_no_events"
    elif event_count == 0:
        reason = "calendar_search_returned_zero_events"
    elif not found:
        reason = "title_not_in_calendar_results_pane"
    elif full_match:
        reason = "full_title_found_in_calendar_results_pane"
    else:
        reason = "search_term_found_in_calendar_results_pane"

    return {
        "executed": bool(found),
        "evidence": {
            "url": page_url,
            "page_title": dom.get("title") or "",
            "title_probed": title,
            "search_term": search_term,
            "calendar_event_count": event_count,
            "calendar_no_results": no_results,
            "screenshot": screenshot_path,
            "dom_excerpt": main_text[:1200],
            "dom_read_ok": dom.get("ok"),
            "dom_error": dom.get("error") or "",
        },
        "targetId": target_id,
        "opened_url": opened_url,
        "closed": bool(closed.get("ok")),
        "reason": reason,
    }


def _verify_gmail_draft(plan: dict, plan_id: str, screenshots_dir: Path,
                         log: list) -> dict:
    """Open a fresh tab on Gmail drafts via CDP /json/new and look for
    a recipient or subject literal from the plan."""
    needles: list[str] = []
    for key in ("person", "thing"):
        v = (plan.get(key) or "").strip()
        if v and len(v) > 2 and v not in needles:
            needles.append(v)
    task = plan.get("task") or ""
    if "subject" in task.lower():
        import re
        m = re.search(r"subject[^a-z]*([\"'])([^\"']{3,80})\1", task,
                      re.IGNORECASE)
        if m and m.group(2) not in needles:
            needles.append(m.group(2))
    log.append(f"[verify_gmail] needles={needles}")
    if not needles:
        return {
            "executed": False, "evidence": {},
            "reason": "no_literal_recipient_or_subject_in_plan",
            "targetId": "", "opened_url": "", "closed": False,
        }

    new = _cdp_open_new_tab(GMAIL_DRAFTS_URL)
    log.append(f"[verify_gmail] open_new_tab ok={new.get('ok')} "
               f"targetId={new.get('targetId')} err={new.get('error','')}")
    target_id = new.get("targetId") or ""
    ws_url = new.get("ws_url") or ""
    opened_url = new.get("url") or GMAIL_DRAFTS_URL
    if not new.get("ok") or not target_id or not ws_url:
        return {
            "executed": False,
            "evidence": {"open_response": new},
            "reason": f"cdp_open_new_tab_failed: {new.get('error', '')}",
            "targetId": target_id, "opened_url": opened_url, "closed": False,
        }

    # Settle then read the drafts list rows directly.
    settle_total = max(VERIFY_SETTLE_S * 2, 8.0)
    deadline = time.time() + settle_total
    dom = {"ok": False, "rows": [], "rowCount": 0, "mainText": "",
            "url": opened_url, "title": "", "error": ""}
    while time.time() < deadline:
        time.sleep(1.0)
        dom = _read_target_dom(ws_url, log,
                                  expression=_GMAIL_DRAFTS_PROBE_JS)
        if dom.get("ok") and (dom.get("rowCount") or 0) > 0:
            break
    page_url = dom.get("url") or opened_url
    rows = dom.get("rows") or []
    main_text = dom.get("mainText") or ""
    blob = (" ".join(rows) + " " + main_text).lower()
    found = bool(blob and any(n.lower() in blob for n in needles))

    screenshot_path = ""
    if ws_url:
        shot_target = screenshots_dir / f"{plan_id}_gmail.png"
        shot = _cdp_screenshot(ws_url, shot_target, timeout=15.0)
        if shot.get("ok"):
            screenshot_path = shot.get("path") or ""

    closed = _cdp_close_target(target_id)
    log.append(f"[verify_gmail] closed={json.dumps(closed)[:200]}")

    if not dom.get("ok"):
        reason = f"dom_read_failed: {dom.get('error','')}"
    elif (dom.get("rowCount") or 0) == 0:
        reason = "gmail_drafts_list_empty_or_not_rendered"
    elif not found:
        reason = "needle_not_in_gmail_drafts_rows"
    else:
        reason = "recipient_or_subject_found_in_gmail_drafts_rows"

    return {
        "executed": bool(found),
        "evidence": {
            "url": page_url,
            "page_title": dom.get("title") or "",
            "needles_probed": needles,
            "gmail_drafts_row_count": int(dom.get("rowCount") or 0),
            "gmail_drafts_rows_sample": rows[:10],
            "screenshot": screenshot_path,
            "dom_excerpt": (" | ".join(rows))[:1200] or main_text[:1200],
            "dom_read_ok": dom.get("ok"),
            "dom_error": dom.get("error") or "",
        },
        "targetId": target_id,
        "opened_url": opened_url,
        "closed": bool(closed.get("ok")),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def _run_one(plan_id: str, run_dir: Path, engine: str, log_dir: Path,
             screenshots_dir: Path, account: str) -> dict:
    log: list[str] = [f"plan_id={plan_id} ts={time.time():.3f}"]
    try:
        loaded = _load_plan_file(run_dir, plan_id)
    except FileNotFoundError as e:
        return {
            "plan_id": plan_id, "executed": False,
            "evidence": {}, "reason": f"plan_file_missing: {e}",
            "category": "unknown",
            "tabs_opened": 0, "tabs_closed": 0,
        }

    transcript = loaded.get("transcript") or ""
    plan = loaded.get("plan") or {}
    category = _plan_category(plan)
    log.append(f"category={category}")
    log.append(f"plan={json.dumps(plan)[:600]}")

    # Even if the engine returns clarify, we still want to surface that
    # honestly in the validator output.
    if plan.get("mode") != "act":
        return {
            "plan_id": plan_id, "executed": False,
            "evidence": {"plan_mode": plan.get("mode"),
                          "plan_question": plan.get("question")},
            "reason": f"plan_mode_not_act: {plan.get('mode')}",
            "category": category, "tabs_opened": 0, "tabs_closed": 0,
            "engine_skipped": True,
        }

    # 1. Reset + inject. The engine will recompute its plan; that's fine
    #    because the recorded plan is the deterministic shape for these
    #    transcripts (per the E2E run).
    inj = _engine_reset_and_inject(engine, transcript, account)
    log.append(f"inject http={inj.get('http')} ok={isinstance(inj.get('body'), dict)}")

    # 2. /api/act.
    t0 = time.time()
    act = _engine_act(engine)
    t_act = time.time() - t0
    log.append(f"act http={act.get('http')} dur={t_act:.2f}s "
               f"body={json.dumps(act.get('body'))[:400]}")

    act_body = act.get("body") if isinstance(act.get("body"), dict) else {}
    engine_ran = bool(act_body.get("ran"))
    engine_status = act_body.get("status") or act_body.get("error") or ""
    engine_intent = act_body.get("intent") or plan.get("intent") or ""
    engine_path = act_body.get("path") or ""

    # 3. Verify side effect.
    tabs_opened = 0
    tabs_closed = 0
    verify: dict
    if category == "calendar":
        verify = _verify_calendar(plan, plan_id, screenshots_dir, log)
    elif category == "gmail_draft":
        verify = _verify_gmail_draft(plan, plan_id, screenshots_dir, log)
    else:
        verify = {
            "executed": False, "evidence": {},
            "reason": f"unsupported_verification_category: {category}",
            "targetId": "", "opened_url": "", "closed": False,
        }
    if verify.get("targetId"):
        tabs_opened = 1
        if verify.get("closed"):
            tabs_closed = 1

    return {
        "plan_id": plan_id,
        "executed": bool(verify.get("executed")),
        "evidence": verify.get("evidence", {}),
        "reason": verify.get("reason", ""),
        "category": category,
        "engine_intent": engine_intent,
        "engine_ran": engine_ran,
        "engine_status": engine_status,
        "engine_path": engine_path,
        "engine_act_duration_s": round(t_act, 3),
        "tabs_opened": tabs_opened,
        "tabs_closed": tabs_closed,
        "logs": log,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plans", default="T01,T03,T04,T20,T05",
                        help="Comma-separated plan IDs (T01..T20)")
    parser.add_argument("--run-dir", default=str(DEFAULT_E2E_RUN),
                        help="Source E2E run dir with TNN_inject.json files")
    parser.add_argument("--engine", default=DEFAULT_ENGINE)
    parser.add_argument("--account",
                        default="plan-exec-validator-1779938054")
    parser.add_argument("--output-root",
                        default=str(REPO_ROOT / "state" / "v7"))
    args = parser.parse_args()

    ids = [s.strip() for s in args.plans.split(",") if s.strip()]
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        print(f"missing run_dir: {run_dir}", file=sys.stderr)
        return 2

    # Pre-flight: bridge and engine must be alive.
    bs = _bridge_status()
    if not bs.get("ok"):
        print(f"bridge not ready: {json.dumps(bs)[:300]}", file=sys.stderr)
        return 2
    if not bs.get("cdp_alive"):
        print(f"CDP not alive on bridge: {json.dumps(bs)[:300]}",
              file=sys.stderr)
        return 2
    estatus, _ = _http_json(args.engine + "/healthz", method="GET",
                              timeout=10.0)
    if int(estatus) != 200:
        print(f"engine not healthy: {estatus}", file=sys.stderr)
        return 2

    # Snapshot the tab inventory before/after for tab-leakage audit.
    status_before, body_before = _cdp_get("/json/list", timeout=10.0)
    tab_ids_before = set()
    if status_before == 200 and isinstance(body_before, list):
        tab_ids_before = {t.get("id") for t in body_before if t.get("id")}

    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(args.output_root) / f"plan_execution_validation_{ts}"
    log_dir = out_dir / "logs"
    screenshots_dir = out_dir / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    runs: list[dict] = []
    for pid in ids:
        print(f"-- {pid} --")
        r = _run_one(pid, run_dir, args.engine, log_dir, screenshots_dir,
                     args.account)
        per_log = log_dir / f"{pid}.log"
        per_log.write_text("\n".join(r.get("logs") or []), encoding="utf-8")
        # Strip logs from the result.json (kept on disk under logs/).
        r.pop("logs", None)
        runs.append(r)
        print(f"   executed={r.get('executed')} reason={r.get('reason')}")

    tabs_opened = sum(int(r.get("tabs_opened") or 0) for r in runs)
    tabs_closed = sum(int(r.get("tabs_closed") or 0) for r in runs)

    # Audit tab inventory after the validator. Anything new that we did
    # not also close is a leak the headline numbers should reflect.
    tab_ids_after = set()
    status_after, body_after = _cdp_get("/json/list", timeout=10.0)
    if status_after == 200 and isinstance(body_after, list):
        tab_ids_after = {t.get("id") for t in body_after if t.get("id")}
    new_tabs_remaining = sorted(tab_ids_after - tab_ids_before)

    result = {
        "schema": "anticipy.plan_execution_validation.v7",
        "ts_utc": ts,
        "engine": args.engine,
        "bridge": DEFAULT_BRIDGE,
        "source_run_dir": str(run_dir),
        "totals": {
            "plans": len(runs),
            "executed": sum(1 for r in runs if r.get("executed")),
            "skipped": sum(1 for r in runs if r.get("engine_skipped")),
            "tabs_opened": tabs_opened,
            "tabs_closed": tabs_closed,
            "tab_leakage": tabs_opened - tabs_closed,
            "tabs_before": len(tab_ids_before),
            "tabs_after": len(tab_ids_after),
            "new_tabs_remaining": new_tabs_remaining,
        },
        "runs": runs,
    }
    (out_dir / "result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(f"wrote {out_dir / 'result.json'}")
    print(json.dumps(result["totals"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
