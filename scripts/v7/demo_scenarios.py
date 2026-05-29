#!/usr/bin/env python3
"""Real-world demo scenarios for the universal action loop.

NORTH STAR v2: "Donna for everyone across any industry." The product
proof is that the same engine code can drive any web app the user is
logged into. This harness picks 5 (at least) scenarios across non-Google
surfaces, fires each through POST /api/universal/run, captures the
trajectory dir (which contains before/after screenshots), and writes a
result.json with per-scenario verdict.

Constraints honored:
  - Universal action loop only. No per-app code in this script. We pass
    the natural-language intent verbatim into /api/universal/run; the
    LLM picks what to click, where to type, and when the task is done.
  - Real Chrome on :9222 with the user's real logged-in sessions.
    Each scenario picks a surface_hint URL only as a starting point;
    the LLM drives from there.
  - Each scenario produces evidence: the trajectory_dir from the engine
    (PNG before/after of every iteration), the JSON manifest, the run
    transcript, the final URL.
  - SMS pre-confirm and post-action receipt gates live on /api/act.
    The universal loop does not route through /api/act, but where a
    scenario describes a real third-party send the loop will pause on
    the click-Send step and the user can read the proposal on screen.
    The bash wrapper also fires a probe through /api/act in parallel
    for the explicit send scenarios so the SMS gate fires (TWILIO_MOCK
    in env keeps it from spamming the real phone).

Pre-flight account checks: before running each scenario, the harness
opens the surface URL in a probe tab and reads the redirect / body
content. If the redirect lands on a login page or the body shows
"Sign in", the scenario is SKIPPED with reason=not_logged_in rather
than failed.

Aggregate verdict: PASS if at least 4 of the 5 fully-eligible scenarios
end with status=SUCCESS, FAIL otherwise. SKIPPED scenarios do not count
toward either side, but the harness logs them so the next pass knows
which surface to log into.

Exit codes:
  0  aggregate PASS (>= 4 of 5 attempted scenarios SUCCESS)
  1  aggregate FAIL
  2  pre-flight failure (engine or bridge down)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path("/Users/omarebrahim/Developer/Anticipy-V7")
ENV_FILE = Path("/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local")

BRIDGE = "http://127.0.0.1:7777"
ENGINE = "http://127.0.0.1:8731"
CDP_BASE = "http://localhost:9222"

# fcntl lock to keep two demo_scenarios runs from clobbering each
# other's agent window. Held for the whole run. The engine's
# /api/universal/run path itself has no serialization, which is a
# separate engine bug; this lock at least prevents two demo harnesses
# from racing.
_RUN_LOCK_PATH = Path("/tmp/anticipy_demo_scenarios.lock")


# ---------------------------------------------------------------------
# Scenario definitions.
#
# Each entry:
#   id            short kebab-case id, used in the output dir name.
#   surface       human-readable surface name (Notion, Stripe, etc).
#   url           the URL to navigate to as starting_url. The model
#                 takes it from there.
#   intent        natural-language instruction handed to the loop.
#   login_probe   substring (case-insensitive) that, if found in the
#                 body of the probe tab, indicates a logged-out state.
#                 If matched, the scenario is SKIPPED.
#   success_signal substring (case-insensitive) the harness looks for
#                 in the final page text (after the loop returns
#                 SUCCESS) to corroborate the LLM's claim. Optional;
#                 default trust the loop's own vision-confirm verdict.
#   route_via_act if True, the bash wrapper additionally POSTs to
#                 /api/act so the SMS pre-confirm gate fires for that
#                 scenario. Set on the Gmail send-flavor scenarios.
#   deadline_sec  per-scenario wall-clock budget.
#
# Non-Google emphasis: we deliberately pick 4 non-Google surfaces
# (Notion, Stripe, GitHub, Calendly) and 1 Google (Gmail draft reply).
# This satisfies the feedback_test_beyond_google rule of >= 3 non-Google
# surfaces per universal test, while still proving the loop on the
# everyday Gmail compose surface.
# ---------------------------------------------------------------------


SCENARIOS: list[dict[str, Any]] = [
    {
        "id": "stripe_revenue_check",
        "surface": "Stripe Aevoy",
        "url": (
            "https://dashboard.stripe.com/acct_1T3RNiBMF3gCPOse/"
            "payments"
        ),
        "intent": (
            "Read the Stripe Aevoy dashboard page that is currently "
            "open and report the gross volume number visible at the "
            "top of the page. Do not click any payment row. Do not "
            "refund or cancel anything. This is a read-only revenue "
            "check."
        ),
        "login_probe": "sign in to your account",
        "success_signal": "",
        "route_via_act": False,
        "deadline_sec": 300.0,
    },
    {
        "id": "calendly_event_lookup",
        "surface": "Calendly",
        "url": (
            "https://calendly.com/app/scheduling/meeting_types/user/me"
        ),
        "intent": (
            "Read the Calendly event types page that is currently open "
            "and report back the names of the event types listed. Do "
            "not click any event. Do not delete anything. Just read "
            "the page and report what you see."
        ),
        "login_probe": "log in to",
        "success_signal": "",
        "route_via_act": False,
        "deadline_sec": 300.0,
    },
    {
        "id": "notion_workspace_read",
        "surface": "Notion",
        "url": "https://app.notion.com/",
        "intent": (
            "Read the Notion workspace currently open in the agent "
            "window. Report which workspace is signed in and list the "
            "first three sidebar items you can see. Do not click any "
            "page. Do not create anything yet. Just read and report."
        ),
        "login_probe": "log in to notion",
        "success_signal": "",
        "route_via_act": False,
        "deadline_sec": 300.0,
    },
    {
        "id": "github_notifications_read",
        "surface": "GitHub",
        "url": "https://github.com/notifications",
        "intent": (
            "Read the GitHub notifications page that is open in the "
            "agent window. Report the count of unread notifications "
            "visible (the number next to 'Inbox' or 'All'). Do not "
            "click any notification. Just read and report."
        ),
        "login_probe": "sign in to github",
        "success_signal": "",
        "route_via_act": False,
        "deadline_sec": 300.0,
    },
    {
        "id": "gmail_thoughtful_reply_draft",
        "surface": "Gmail",
        "url": "https://mail.google.com/mail/u/0/#inbox",
        "intent": (
            "Draft an email to cam@example.com with subject 'Q3 roadmap "
            "honest update' saying 'Hi Cam, thanks for asking about Q3. "
            "Today we shipped the universal action loop, the stranger "
            "flow, and the dress rehearsal harness. The one bug still "
            "biting us is the trivia engine occasionally returning a "
            "WWI fact when asked about WWII. We have a fix landing this "
            "week. Happy to walk through anything live. Omar.'"
        ),
        "login_probe": "sign in to your google account",
        "success_signal": "",
        # The Gmail compose path takes the /api/act direct-draft branch
        # and lands in real Drafts. SMS pre-confirm gate is bypassed for
        # draft-only (no click-Send), but the receipt path runs.
        "route_via_act": True,
        "deadline_sec": 240.0,
    },
]


# After each scenario, wait this many seconds before the next one so any
# background runner thread from a DEADLINE_EXCEEDED scenario has a chance
# to finish writing its manifest before the next scenario starts. Without
# this cooldown, the next scenario's _prewarm step navigates the agent
# window mid-loop and the prior runner's vision verifier sees garbage.
PER_SCENARIO_COOLDOWN_SEC = 30.0


# ---------------------------------------------------------------------
# .env loader (subset of bash 'set -a; . file; set +a')
# ---------------------------------------------------------------------
def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        elif v.startswith("'") and v.endswith("'"):
            v = v[1:-1]
        out[k] = v
    return out


def _env() -> dict[str, str]:
    e = _load_env_file(ENV_FILE)
    for k, v in os.environ.items():
        if v:
            e[k] = v
    return e


# ---------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------
def _http(url: str, *, method: str = "GET",
          body: bytes | None = None,
          headers: dict[str, str] | None = None,
          timeout: float = 20.0) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, data=body, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), ""
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, exc.read(), ""
        except Exception:
            return exc.code, b"", f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        return 0, b"", f"{type(exc).__name__}: {exc}"


def _json_post(url: str, payload: dict, *,
               headers: dict[str, str] | None = None,
               timeout: float = 600.0) -> tuple[int, dict, str]:
    body = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    status, raw, err = _http(url, method="POST", body=body, headers=h,
                             timeout=timeout)
    if err:
        return status, {}, err
    try:
        return status, json.loads(raw.decode("utf-8") or "{}"), ""
    except Exception as exc:
        return status, {}, f"json decode: {exc}: {raw[:200]!r}"


def _json_get(url: str, *, timeout: float = 15.0,
              headers: dict[str, str] | None = None,
              ) -> tuple[int, Any, str]:
    status, raw, err = _http(url, method="GET", timeout=timeout,
                             headers=headers)
    if err:
        return status, None, err
    try:
        return status, json.loads(raw.decode("utf-8") or "null"), ""
    except Exception as exc:
        return status, None, f"json decode: {exc}: {raw[:200]!r}"


# ---------------------------------------------------------------------
# CDP helpers
# ---------------------------------------------------------------------
def _cdp_list_targets() -> list[dict]:
    s, body, err = _http(f"{CDP_BASE}/json", timeout=5.0)
    if err or s != 200:
        return []
    try:
        return json.loads(body.decode("utf-8") or "[]")
    except Exception:
        return []


def _cdp_close_target(target_id: str) -> bool:
    if not target_id:
        return False
    _s, _b, err = _http(
        f"{CDP_BASE}/json/close/"
        f"{urllib.parse.quote(target_id, safe='')}",
        timeout=5.0,
    )
    return not err


def _cdp_create_new_tab(url: str) -> dict:
    if not url:
        return {"ok": False, "error": "empty url"}
    encoded = urllib.parse.quote(url, safe=":/?&=%#")
    s, body, err = _http(
        f"{CDP_BASE}/json/new?{encoded}", method="PUT", timeout=10.0,
    )
    if err or s >= 400:
        s, body, err = _http(
            f"{CDP_BASE}/json/new?{encoded}", method="GET", timeout=10.0,
        )
    if err:
        return {"ok": False, "error": err}
    try:
        d = json.loads(body.decode("utf-8") or "{}")
    except Exception as exc:
        return {"ok": False, "error": f"decode: {exc}"}
    tid = str(d.get("id") or "")
    if not tid:
        return {"ok": False,
                "error": f"no id in response: {str(d)[:200]}"}
    return {"ok": True, "targetId": tid,
            "url": str(d.get("url") or "")}


def _cdp_eval(target_id: str, expression: str,
              *, timeout: float = 10.0) -> dict:
    if not target_id:
        return {"ok": False, "error": "no target_id"}
    try:
        from websockets.sync.client import connect as ws_connect
    except Exception as exc:
        return {"ok": False, "error": f"websockets missing: {exc}"}
    ws_url = f"ws://localhost:9222/devtools/page/{target_id}"
    try:
        ws = ws_connect(ws_url, max_size=8 * 1024 * 1024,
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
                raw = ws.recv(timeout=max(0.5, deadline - time.time()))
            except Exception as exc:
                return {"ok": False, "error": f"ws recv: {exc}"}
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("id") != 1:
                continue
            result = (msg.get("result") or {}).get("result") or {}
            exc = (msg.get("result") or {}).get("exceptionDetails")
            if exc:
                text = ((exc.get("exception") or {}).get("description")
                        or json.dumps(exc)[:300])
                return {"ok": False, "error": f"js exc: {text}",
                        "value": None}
            return {"ok": True, "value": result.get("value")}
        return {"ok": False, "error": "timeout"}
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _cdp_screenshot(target_id: str, out_path: Path) -> bool:
    """Capture a PNG of a specific target via CDP. Writes to out_path,
    returns True on success."""
    if not target_id:
        return False
    try:
        from websockets.sync.client import connect as ws_connect
    except Exception:
        return False
    ws_url = f"ws://localhost:9222/devtools/page/{target_id}"
    try:
        ws = ws_connect(ws_url, max_size=32 * 1024 * 1024,
                        open_timeout=5.0)
    except Exception:
        return False
    try:
        ws.send(json.dumps({
            "id": 1, "method": "Page.captureScreenshot",
            "params": {"format": "png"}}))
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                raw = ws.recv(timeout=max(0.5, deadline - time.time()))
            except Exception:
                return False
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("id") != 1:
                continue
            data_b64 = (msg.get("result") or {}).get("data") or ""
            if not data_b64:
                return False
            try:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(base64.b64decode(data_b64))
                return True
            except Exception:
                return False
        return False
    finally:
        try:
            ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------
def _bridge_alive() -> dict:
    s, body, err = _http(f"{BRIDGE}/status", timeout=10.0)
    if err or s != 200:
        return {"ok": False, "error": err or f"status {s}"}
    try:
        d = json.loads(body.decode("utf-8") or "{}")
    except Exception as exc:
        return {"ok": False, "error": f"decode: {exc}"}
    return {"ok": bool(d.get("ok")) and bool(d.get("cdp_alive")),
            "raw": d}


def _engine_alive() -> dict:
    s, data, err = _json_get(f"{ENGINE}/api/state", timeout=8.0)
    if err or s != 200:
        return {"ok": False, "error": err or f"status {s}"}
    if not isinstance(data, dict):
        return {"ok": False, "error": "non-dict"}
    return {"ok": True, "key_ok": bool(data.get("key_ok")),
            "cdp_port": data.get("cdp_port")}


def _ts_utc() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False),
                    encoding="utf-8")


# ---------------------------------------------------------------------
# Per-scenario pipeline
# ---------------------------------------------------------------------
def _probe_logged_in(scenario: dict,
                     out_dir: Path,
                     opened_targets: list[str]) -> dict:
    """Open the surface URL in a probe tab and decide whether the user
    is logged in. Captures a 'login_probe.png' screenshot for evidence.

    Returns {"logged_in": bool, "url": "...", "title": "...",
             "body_snippet": "...", "probe_screenshot": "/abs/path"}
    """
    url = scenario.get("url") or ""
    if not url:
        # No URL probe; assume Gmail-style direct compose URL works.
        return {"logged_in": True, "skip_reason": "",
                "url": "", "title": "", "body_snippet": "",
                "probe_screenshot": ""}
    new = _cdp_create_new_tab(url)
    if not new.get("ok"):
        return {"logged_in": False,
                "skip_reason": f"probe nav failed: {new.get('error')}",
                "url": url, "title": "", "body_snippet": "",
                "probe_screenshot": ""}
    tid = str(new.get("targetId") or "")
    if tid:
        opened_targets.append(tid)
    # Wait for the probe tab to settle. Some surfaces (Stripe, Calendly)
    # render lazily; give them a longer settle window. Notion sometimes
    # takes 8+ seconds to hydrate.
    time.sleep(12.0)
    probe_js = (
        "(()=>{const b=document.body;const t=b?b.innerText||'':'';"
        "return JSON.stringify({url:location.href,title:document.title,"
        "bodyLen:t.length,first800:t.slice(0,800).toLowerCase()});})()"
    )
    probe = _cdp_eval(tid, probe_js, timeout=10.0)
    val = str(probe.get("value") or "")
    try:
        data = json.loads(val or "{}")
    except Exception:
        data = {}
    title = str(data.get("title") or "")
    body_low = str(data.get("first800") or "")
    final_url = str(data.get("url") or url)

    shot_path = out_dir / "login_probe.png"
    _cdp_screenshot(tid, shot_path)

    # Heuristic: if the login_probe substring is in the body OR the URL
    # contains a login path AND the page also says "log in"/"sign in",
    # treat as logged-out.
    login_probe = (scenario.get("login_probe") or "").lower().strip()
    looks_login_url = any(s in final_url.lower()
                          for s in ["/login", "/signin", "/sign-in",
                                    "/sign_in", "/auth/login"])
    body_signals_login = any(s in body_low for s in [
        "log in to ", "sign in to ", "continue with google",
        "continue with email", "sign in with", "log in with",
        "create an account", "create one", "log in to your"])
    matched_probe = bool(login_probe and login_probe in body_low)

    logged_in = True
    skip_reason = ""
    if matched_probe or looks_login_url or body_signals_login:
        # If the body says "log in" but is clearly a logged-in app page
        # (e.g. Notion's sidebar with a "Log out" item somewhere), the
        # body length heuristic helps: real app pages have > 1000 chars
        # of varied text, whereas login walls have a short body.
        # 600 chars is the cut-off we use: anything shorter on a
        # supposed app surface is almost certainly a login wall.
        if data.get("bodyLen", 0) < 600 or matched_probe:
            logged_in = False
            skip_reason = (
                f"login wall detected at {final_url!r} "
                f"(bodyLen={data.get('bodyLen')}, "
                f"matched_login_probe={matched_probe})"
            )

    return {"logged_in": logged_in,
            "skip_reason": skip_reason,
            "url": final_url,
            "title": title,
            "body_snippet": body_low[:300],
            "body_chars": int(data.get("bodyLen") or 0),
            "probe_screenshot": str(shot_path) if shot_path.exists() else "",
            "probe_target_id": tid}


_AGENT_WINDOW_STATE = Path(os.path.expanduser(
    "~/.anticipy/v4_agent_window.json"))


def _bridge_navigate(url: str) -> dict:
    """Call /surface-command navigate via the loopback bridge. Returns
    the bridge's full response so callers can read the targetId."""
    env = _env()
    secret = env.get("ANTICIPY_TRIGGER_SECRET", "") or "local-dev"
    payload = {"secret": secret, "command": "navigate", "url": url}
    s, data, err = _json_post(f"{BRIDGE}/surface-command", payload,
                              timeout=60.0)
    if err:
        return {"ok": False, "error": err}
    return data or {}


def _prewarm_agent_window(scenario: dict) -> dict:
    """Pre-warm the persisted Anticipy Agent window by navigating it to
    the scenario URL BEFORE the universal loop fires.

    The dsv4 runner's _ensure_agent_window reuses a single persisted
    window across runs. If a prior scenario left it on a different URL,
    the new scenario's vision auditor sees stale content during the
    first iteration and the LLM can wander. By navigating the agent
    window to the scenario URL ourselves and waiting for the SPA to
    hydrate, the runner's first observation is always the right page.

    If no persisted window exists yet, we let the dsv4 runner create
    one on its first call. The starting_url path in the runner will
    then navigate it to the same URL.

    Returns: {"prewarmed": bool, "target_id": "...", "url": "...",
              "settle_seconds": float}.
    """
    url = scenario.get("url") or ""
    out: dict = {"prewarmed": False, "url": url}
    if not url:
        out["skip_reason"] = "no url"
        return out
    if not _AGENT_WINDOW_STATE.exists():
        # Let the dsv4 runner create the window. Its starting_url
        # path will navigate.
        out["skip_reason"] = "no persisted agent window yet"
        return out
    try:
        tid = (json.loads(_AGENT_WINDOW_STATE.read_text())
               .get("target_id") or "")
    except Exception as exc:
        out["error"] = f"read state: {exc}"
        return out
    if not tid:
        out["skip_reason"] = "state file has no target_id"
        return out
    # Make sure the target still exists.
    targets = _cdp_list_targets()
    if not any(t.get("id") == tid for t in targets):
        # Stale state; remove so the runner creates a fresh window.
        try:
            _AGENT_WINDOW_STATE.unlink()
            out["removed_stale_state"] = True
        except Exception:
            pass
        out["skip_reason"] = "persisted target_id no longer exists"
        return out
    # Navigate via raw CDP on the persisted target_id.
    try:
        from websockets.sync.client import connect as ws_connect
    except Exception as exc:
        out["error"] = f"websockets missing: {exc}"
        return out
    ws_url = f"ws://localhost:9222/devtools/page/{tid}"
    try:
        ws = ws_connect(ws_url, max_size=8 * 1024 * 1024,
                        open_timeout=5.0)
    except Exception as exc:
        out["error"] = f"ws connect: {exc}"
        return out
    try:
        ws.send(json.dumps({"id": 1, "method": "Page.enable", "params": {}}))
        # Drain the enable response so it doesn't confuse the next read.
        try:
            ws.recv(timeout=2.0)
        except Exception:
            pass
        ws.send(json.dumps({"id": 2, "method": "Page.navigate",
                            "params": {"url": url}}))
        # Wait briefly for the navigate ack so we know the message landed.
        ack_deadline = time.time() + 8.0
        while time.time() < ack_deadline:
            try:
                raw = ws.recv(timeout=max(0.5, ack_deadline - time.time()))
            except Exception:
                break
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("id") == 2:
                break
    finally:
        try:
            ws.close()
        except Exception:
            pass
    # Settle. Heavy SPAs (Stripe, Notion, GitHub) need ~10-20 seconds
    # of layout + script execution before they look "ready" to the
    # vision model. 18s is the sweet spot in testing.
    settle = 18.0
    time.sleep(settle)
    out["prewarmed"] = True
    out["target_id"] = tid
    out["settle_seconds"] = settle
    return out


def _run_universal(scenario: dict) -> dict:
    """POST to /api/universal/run, return the engine JSON verbatim."""
    payload = {
        "intent": scenario["intent"],
        "surface_hint": scenario.get("url") or "",
        "deadline_sec": float(scenario.get("deadline_sec") or 120.0),
    }
    deadline = float(payload["deadline_sec"]) + 60.0
    s, data, err = _json_post(f"{ENGINE}/api/universal/run", payload,
                              timeout=deadline)
    if err:
        return {"ok": False, "status": "HTTP_ERROR", "error": err}
    if s != 200:
        return {"ok": False, "status": f"HTTP_{s}", "error": str(data)[:600]}
    return data


def _probe_act_for_sms_gate(scenario: dict) -> dict:
    """Fire one /api/act call for scenarios marked route_via_act=True.

    The point is to exercise the SMS pre-confirm gate for the
    send-flavor scenarios (the universal loop itself doesn't go through
    /api/act). TWILIO_MOCK=true in env keeps real SMS suppressed; the
    pending record + receipt logic still runs.

    Returns the engine response or an error wrapper.
    """
    if not scenario.get("route_via_act"):
        return {"ok": True, "skipped": True,
                "reason": "scenario not routed via /api/act"}
    s, data, err = _json_post(f"{ENGINE}/api/act",
                              {"instruction": scenario["intent"]},
                              timeout=180.0)
    if err:
        return {"ok": False, "error": err}
    if s != 200:
        return {"ok": False, "status": s, "error": str(data)[:400]}
    return {
        "ok": True,
        "ran": bool(data.get("ran")),
        "pre_confirm_required": bool(data.get("pre_confirm_required")),
        "gate_kind": data.get("gate_kind"),
        "task_id": data.get("task_id"),
        "intent": data.get("intent"),
        "status": data.get("status"),
        "receipt": data.get("receipt"),
        "compose_url": data.get("compose_url"),
        "resolved_person": data.get("resolved_person"),
    }


def _verify_success(scenario: dict, universal_result: dict,
                    out_dir: Path,
                    opened_targets: list[str]) -> dict:
    """Mechanical check: open the surface again (the loop landed on a
    target page) and look for the success_signal substring. Captures
    an after_check.png screenshot. If success_signal is empty, trust
    the loop's vision-confirmed SUCCESS as authoritative.
    """
    answer = str(universal_result.get("answer") or "")
    evidence = str(universal_result.get("evidence") or "")
    status = str(universal_result.get("status") or "")

    out: dict[str, Any] = {
        "engine_status": status,
        "engine_answer": answer[:400],
        "engine_evidence": evidence[:400],
        "trajectory_dir": str(universal_result.get("trajectory_dir") or ""),
        "elapsed_sec": universal_result.get("elapsed_sec"),
        "deadline_hit": bool(universal_result.get("deadline_hit")),
        "n_iterations": int(universal_result.get("n_iterations") or 0),
        "after_screenshot": "",
        "agent_window_screenshot": "",
        "success_signal_present": None,
    }

    # Capture a fresh "after" screenshot of the agent's owned window
    # (the dsv4 runner persists target_id in ~/.anticipy/v4_agent_window.json).
    agent_win_state = Path(os.path.expanduser(
        "~/.anticipy/v4_agent_window.json"))
    agent_target_id = ""
    if agent_win_state.exists():
        try:
            agent_target_id = str(json.loads(
                agent_win_state.read_text()).get("target_id") or "")
        except Exception:
            agent_target_id = ""
    if agent_target_id:
        shot = out_dir / "agent_window_after.png"
        if _cdp_screenshot(agent_target_id, shot):
            out["agent_window_screenshot"] = str(shot)

    # If a success_signal was provided, also probe the surface for the
    # signal substring (case-insensitive).
    signal = (scenario.get("success_signal") or "").lower().strip()
    if signal and agent_target_id:
        body_js = (
            "(()=>{const t=(document.body&&document.body.innerText)||'';"
            "return JSON.stringify({url:location.href,title:document.title,"
            "found:t.toLowerCase().indexOf(" + json.dumps(signal)
            + ")>=0,bodyLen:t.length,first600:t.slice(0,600)});})()"
        )
        probe = _cdp_eval(agent_target_id, body_js, timeout=10.0)
        try:
            data = json.loads(str(probe.get("value") or "{}"))
        except Exception:
            data = {}
        out["success_signal_present"] = bool(data.get("found"))
        out["after_url"] = str(data.get("url") or "")
        out["after_title"] = str(data.get("title") or "")
        out["after_body_chars"] = int(data.get("bodyLen") or 0)
        out["after_body_snippet"] = str(data.get("first600") or "")[:600]

    # Copy the trajectory dir into the output dir so it travels with
    # the rest of the evidence. The engine writes to a global location
    # by default; copying makes the result self-contained.
    traj = out.get("trajectory_dir") or ""
    if traj and Path(traj).is_dir():
        try:
            dst = out_dir / "trajectory"
            if dst.exists():
                shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(traj, dst,
                            ignore=shutil.ignore_patterns("*.iso"))
            out["trajectory_copy"] = str(dst)
            # Build screenshot index for quick eyeballing.
            shots = sorted(dst.glob("*.png"))
            out["screenshot_count"] = len(shots)
            out["screenshot_paths"] = [str(p) for p in shots[:20]]
        except Exception as exc:
            out["trajectory_copy_error"] = (
                f"{type(exc).__name__}: {exc}")

    return out


def _scenario_verdict(scenario: dict, ver: dict,
                      universal: dict) -> str:
    """Decide PASS / PARTIAL / FAIL for one scenario.

    Rules:
      - status=SUCCESS from the loop is the primary signal.
        That status only fires when the vision auditor confirms the
        objective on the real after-screenshot.
      - If success_signal is set and the mechanical re-read also finds
        it, that's PASS.
      - If status=SUCCESS but success_signal is set and missing,
        downgrade to PARTIAL (the LLM thought it was done, but the
        mechanical check disagrees).
      - If status=SUCCESS and no success_signal is set, trust the
        LLM verdict: PASS.
      - DEADLINE_EXCEEDED, ERROR, HARD_FAIL, ITERATION_EXHAUSTED -> FAIL.
    """
    s = str(universal.get("status") or "").upper()
    if s != "SUCCESS":
        return "FAIL"
    signal = (scenario.get("success_signal") or "").strip()
    if not signal:
        return "PASS"
    present = ver.get("success_signal_present")
    if present is True:
        return "PASS"
    if present is False:
        return "PARTIAL"
    # success_signal_present is None => couldn't probe; trust the loop
    return "PASS"


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root",
                    default=str(REPO_ROOT / "state" / "v7"
                                / "demo_scenarios_runs"))
    ap.add_argument("--only",
                    default="",
                    help="comma-separated scenario ids to run; default = all")
    args = ap.parse_args(argv)

    # Acquire the run lock so two demo harnesses cannot race. The lock
    # is held for the lifetime of this process; the OS releases it on
    # exit. If we cannot acquire within 5 seconds we abort with a clear
    # message rather than competing for the agent window.
    import fcntl
    try:
        _lock_fh = open(_RUN_LOCK_PATH, "w")
        fcntl.flock(_lock_fh.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"[demo] FAIL: another demo_scenarios run holds "
              f"{_RUN_LOCK_PATH}; refusing to compete for the agent "
              "window.", flush=True)
        return 2

    if not _bridge_alive().get("ok"):
        print("[demo] FAIL: bridge not alive on 127.0.0.1:7777",
              flush=True)
        return 2
    if not _engine_alive().get("ok"):
        print("[demo] FAIL: engine not alive on 127.0.0.1:8731",
              flush=True)
        return 2

    only = {s.strip() for s in args.only.split(",") if s.strip()}
    scenarios = [s for s in SCENARIOS if not only or s["id"] in only]
    if not scenarios:
        print(f"[demo] FAIL: no scenarios match --only={args.only!r}",
              flush=True)
        return 2

    run_id = _ts_utc()
    run_root = Path(args.out_root) / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    print(f"[demo] run dir = {run_root}", flush=True)
    print(f"[demo] scenarios = {[s['id'] for s in scenarios]}",
          flush=True)

    aggregate: dict[str, Any] = {
        "run_id": run_id,
        "started_at": _ts_utc(),
        "engine_url": ENGINE,
        "bridge_url": BRIDGE,
        "cdp_base": CDP_BASE,
        "scenarios": [],
    }
    opened_targets: list[str] = []

    try:
        for scenario_idx, scenario in enumerate(scenarios):
            sid = scenario["id"]
            print("", flush=True)
            print(f"=== {sid} ({scenario['surface']}) ===", flush=True)
            if scenario_idx > 0:
                print(f"[demo] cooldown {PER_SCENARIO_COOLDOWN_SEC}s before "
                      "next scenario...", flush=True)
                time.sleep(PER_SCENARIO_COOLDOWN_SEC)
            scen_dir = run_root / sid
            scen_dir.mkdir(parents=True, exist_ok=True)
            scen_record: dict[str, Any] = {
                "id": sid,
                "surface": scenario["surface"],
                "url": scenario.get("url") or "",
                "intent": scenario["intent"],
                "started_at": _ts_utc(),
                "verdict": "UNKNOWN",
                "skip_reason": "",
            }

            # Step 1: probe login state in a SEPARATE probe tab. We do
            # not touch the agent window here; the prewarm step below
            # handles the agent window.
            probe = _probe_logged_in(scenario, scen_dir, opened_targets)
            scen_record["probe"] = probe
            if not probe.get("logged_in"):
                scen_record["verdict"] = "SKIPPED"
                scen_record["skip_reason"] = probe.get("skip_reason") or "?"
                scen_record["finished_at"] = _ts_utc()
                aggregate["scenarios"].append(scen_record)
                _write_json(scen_dir / "result.json", scen_record)
                _write_json(run_root / "aggregate.json", aggregate)
                print(f"[demo] {sid}: SKIPPED ({scen_record['skip_reason']})",
                      flush=True)
                continue

            # Step 2: route through /api/act for SMS gate probe
            # (Gmail draft scenario only).
            act_resp = _probe_act_for_sms_gate(scenario)
            scen_record["act_probe"] = act_resp

            # Step 2.5: pre-warm the agent window by navigating it to
            # the scenario URL ourselves. The dsv4 runner's
            # _ensure_agent_window reuses a persisted target across
            # runs, so without prewarming the first iteration sees
            # stale content from the previous scenario. By navigating
            # to the right URL up front and letting the SPA hydrate,
            # we cut wall-clock by 30-60s per scenario.
            prewarm = _prewarm_agent_window(scenario)
            scen_record["agent_window_prewarm"] = prewarm

            # Step 3: fire the universal loop.
            print(f"[demo] {sid}: POST /api/universal/run "
                  f"(deadline {scenario['deadline_sec']}s)...",
                  flush=True)
            t0 = time.monotonic()
            universal = _run_universal(scenario)
            t1 = time.monotonic()
            scen_record["universal_result"] = universal
            scen_record["universal_elapsed_sec"] = round(t1 - t0, 3)

            # Step 4: verify success on the agent window.
            ver = _verify_success(scenario, universal, scen_dir,
                                  opened_targets)
            scen_record["verify"] = ver

            verdict = _scenario_verdict(scenario, ver, universal)
            scen_record["verdict"] = verdict
            scen_record["finished_at"] = _ts_utc()
            aggregate["scenarios"].append(scen_record)
            _write_json(scen_dir / "result.json", scen_record)
            _write_json(run_root / "aggregate.json", aggregate)
            print(f"[demo] {sid}: verdict={verdict} "
                  f"(engine={universal.get('status','?')}, "
                  f"iters={universal.get('n_iterations','?')}, "
                  f"elapsed={scen_record['universal_elapsed_sec']}s, "
                  f"signal={ver.get('success_signal_present')})",
                  flush=True)

    finally:
        # Best-effort close all probe tabs we opened. Agent windows are
        # left alone; the dsv4 runner reuses them across runs.
        for tid in opened_targets:
            _cdp_close_target(tid)

    # Aggregate verdict.
    eligible = [s for s in aggregate["scenarios"]
                if s["verdict"] != "SKIPPED"]
    pass_count = sum(1 for s in eligible
                     if s["verdict"] in {"PASS"})
    partial_count = sum(1 for s in eligible
                        if s["verdict"] == "PARTIAL")
    fail_count = sum(1 for s in eligible
                     if s["verdict"] == "FAIL")
    skip_count = len(aggregate["scenarios"]) - len(eligible)

    # PASS threshold: at least 4 of 5 (or, more generally, 80% of the
    # attempted scenarios end in PASS). PARTIAL does not count as PASS.
    threshold = max(4, int(round(len(scenarios) * 0.8)))
    aggregate_verdict = "PASS" if pass_count >= threshold else "FAIL"

    aggregate["finished_at"] = _ts_utc()
    aggregate["pass_count"] = pass_count
    aggregate["partial_count"] = partial_count
    aggregate["fail_count"] = fail_count
    aggregate["skipped_count"] = skip_count
    aggregate["threshold"] = threshold
    aggregate["aggregate_verdict"] = aggregate_verdict
    _write_json(run_root / "aggregate.json", aggregate)

    print("", flush=True)
    print(f"=== AGGREGATE: {aggregate_verdict} "
          f"(pass={pass_count}, partial={partial_count}, "
          f"fail={fail_count}, skip={skip_count}, "
          f"threshold>={threshold}) ===", flush=True)
    print(f"=== evidence: {run_root}/aggregate.json ===", flush=True)
    return 0 if aggregate_verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
