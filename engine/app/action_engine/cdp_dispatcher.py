"""CDP dispatcher with humanlike motion. Phase fara-3.

Talks to Chrome on localhost:9222 (the LaunchAgent-managed real-clone
profile). Translates a Fara action into CDP Input.dispatchMouseEvent /
Input.dispatchKeyEvent calls with Bezier curves and Gaussian timing.

Architecture:

    fara_action_dict          our_dispatcher                 chrome
   {action: left_click,   ->  bezier_path + sleeps      ->   actual mouse
    coordinate: [x,y]}        + dispatchMouseEvent           and clicks

Coordinate cache keyed on per-skill landmark fingerprints lets repeat
runs of the same skill skip the Fara round trip when the visual
landmarks haven't changed. See engine/app/action_engine/coord_cache.py.

Refusal detection: Fara's training data includes safety refusals at
critical points. When Fara's output flags refusal, this dispatcher
short-circuits with RefusalSignal so upstream skill logic can decide
what to do.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import httpx
import numpy as np
from websockets.sync.client import connect as ws_connect  # type: ignore

from .humanlike import (
    MotionPoint,
    bezier_path,
    gaussian_delay,
    typing_inter_char_delays,
)

_logger = logging.getLogger("anticipy.action_engine.cdp")


@dataclass
class RefusalSignal:
    reason: str
    raw: str = ""


@dataclass
class CDPSession:
    """A bound CDP session for one tab. Tracks cursor + msg id."""

    ws: Any  # websockets sync connection
    target_id: str
    msg_id: int = 0
    cursor_x: float = 714.0
    cursor_y: float = 448.0
    rng: np.random.Generator = field(default_factory=lambda: np.random.default_rng())
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _next_id(self) -> int:
        with self._lock:
            self.msg_id += 1
            return self.msg_id

    def send(self, method: str, params: Optional[dict] = None, timeout_s: float = 10.0) -> dict:
        msg_id = self._next_id()
        msg = {"id": msg_id, "method": method, "params": params or {}}
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                raw = self.ws.recv(timeout=max(0.1, deadline - time.time()))
            except TimeoutError:
                continue
            try:
                resp = json.loads(raw)
            except Exception:
                continue
            if resp.get("id") == msg_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error on {method}: {resp['error']}")
                return resp.get("result", {})
        raise TimeoutError(f"CDP {method} timed out after {timeout_s}s")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def _list_targets(host: str = "localhost", port: int = 9222) -> list[dict]:
    r = httpx.get(f"http://{host}:{port}/json/list", timeout=5.0)
    r.raise_for_status()
    return r.json()


def _new_target(url: str, host: str = "localhost", port: int = 9222) -> dict:
    r = httpx.put(f"http://{host}:{port}/json/new?{url}", timeout=10.0)
    r.raise_for_status()
    return r.json()


def connect_to_chrome(
    host: str = "localhost",
    port: int = 9222,
    target_url_substr: Optional[str] = None,
    open_url: Optional[str] = None,
    seed: Optional[int] = None,
) -> CDPSession:
    """Open a CDP session against the matching tab.

    If `target_url_substr` is given, attach to the first existing tab whose
    URL contains that substring. Else if `open_url` is given, open a new
    tab with that URL and attach to it. Else attach to the first http(s)
    tab (or the first tab if none have http URLs).
    """
    targets = _list_targets(host, port)
    target = None
    if target_url_substr:
        for t in targets:
            if target_url_substr in (t.get("url") or ""):
                target = t
                break
    if target is None and open_url:
        target = _new_target(open_url, host, port)
    if target is None:
        # First http(s) target
        for t in targets:
            if (t.get("url") or "").startswith(("http://", "https://")):
                target = t
                break
        if target is None and targets:
            target = targets[0]
    if target is None:
        raise RuntimeError("no CDP target available on :9222")

    ws_url = target["webSocketDebuggerUrl"]
    ws = ws_connect(ws_url, max_size=8 * 1024 * 1024)
    rng = np.random.default_rng(seed) if seed is not None else np.random.default_rng()
    sess = CDPSession(ws=ws, target_id=target["id"], rng=rng)
    sess.send("Page.enable")
    sess.send("Runtime.enable")
    return sess


# ─── Action primitives ───────────────────────────────────────────────


def humanlike_click(
    sess: CDPSession,
    x: int,
    y: int,
    click_count: int = 1,
    n_points: int = 30,
) -> None:
    """Move cursor along a Bezier path then click."""
    path = bezier_path(sess.cursor_x, sess.cursor_y, float(x), float(y), n_points=n_points, rng=sess.rng)
    for pt in path:
        time.sleep(pt.delay_ms / 1000.0)
        sess.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": pt.x,
            "y": pt.y,
            "button": "none",
        }, timeout_s=8.0)
    sess.cursor_x = path[-1].x
    sess.cursor_y = path[-1].y
    # Settle before press
    time.sleep(gaussian_delay(80.0, 30.0, 30.0, 200.0, rng=sess.rng) / 1000.0)
    sess.send("Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": float(x),
        "y": float(y),
        "button": "left",
        "clickCount": click_count,
    }, timeout_s=8.0)
    time.sleep(gaussian_delay(60.0, 20.0, 30.0, 150.0, rng=sess.rng) / 1000.0)
    sess.send("Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": float(x),
        "y": float(y),
        "button": "left",
        "clickCount": click_count,
    }, timeout_s=8.0)


def humanlike_type(sess: CDPSession, text: str) -> None:
    """Type text with per-char Gaussian delays and occasional pauses."""
    delays = typing_inter_char_delays(text, rng=sess.rng)
    for ch, d in zip(text, delays):
        time.sleep(d / 1000.0)
        sess.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            "text": ch,
            "key": ch,
            "unmodifiedText": ch,
        }, timeout_s=8.0)
        sess.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": ch}, timeout_s=8.0)


def humanlike_key(sess: CDPSession, keys: list[str]) -> None:
    """Press keys in order, release in reverse (combo key support)."""
    for k in keys:
        sess.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": k, "code": k}, timeout_s=8.0)
        time.sleep(gaussian_delay(20.0, 8.0, 5.0, 60.0, rng=sess.rng) / 1000.0)
    for k in reversed(keys):
        sess.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": k, "code": k}, timeout_s=8.0)


def humanlike_scroll(sess: CDPSession, pixels: int) -> None:
    """Scroll by pixels in chunks of 100-300 with 20-50ms gaps."""
    remaining = abs(pixels)
    direction = -1 if pixels < 0 else 1
    while remaining > 0:
        chunk = min(remaining, int(sess.rng.integers(100, 301)))
        sess.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": sess.cursor_x,
            "y": sess.cursor_y,
            "deltaX": 0,
            "deltaY": chunk * direction,
        }, timeout_s=8.0)
        time.sleep(gaussian_delay(35.0, 10.0, 20.0, 80.0, rng=sess.rng) / 1000.0)
        remaining -= chunk


def navigate(sess: CDPSession, url: str, wait_for_load_s: float = 15.0) -> None:
    """Navigate to URL and wait for Page.loadEventFired."""
    sess.send("Page.navigate", {"url": url}, timeout_s=10.0)
    deadline = time.time() + wait_for_load_s
    while time.time() < deadline:
        try:
            raw = sess.ws.recv(timeout=max(0.1, deadline - time.time()))
        except TimeoutError:
            continue
        try:
            resp = json.loads(raw)
        except Exception:
            continue
        if resp.get("method") == "Page.loadEventFired":
            return
    raise TimeoutError(f"navigate({url}) did not fire load within {wait_for_load_s}s")


def capture_screenshot(sess: CDPSession, format: str = "png") -> bytes:
    r = sess.send("Page.captureScreenshot", {"format": format, "fromSurface": True, "captureBeyondViewport": False}, timeout_s=10.0)
    return base64.b64decode(r["data"])


def wait_for_settle(sess: CDPSession, timeout_s: float = 2.0, stable_window_s: float = 0.4, sample_interval_s: float = 0.2) -> bool:
    """Sample screenshots until visible region stable for stable_window_s.

    Returns True on settle, False on timeout. Cheap perceptual hash compare
    via byte-equality of compressed PNGs (good enough; real phash is heavier).
    """
    start = time.time()
    last_hash = None
    last_change = time.time()
    while time.time() - start < timeout_s:
        try:
            shot = capture_screenshot(sess, format="jpeg")
        except Exception:
            return False
        h = hash(shot)
        if h != last_hash:
            last_hash = h
            last_change = time.time()
        elif time.time() - last_change >= stable_window_s:
            return True
        time.sleep(sample_interval_s)
    return False


# ─── Top-level dispatch from Fara action ──────────────────────────────


def dispatch_fara_action(sess: CDPSession, fara_response: dict) -> dict:
    """Take a parsed Fara response (the dict returned by /infer) and
    execute it against the bound CDP session. Returns a dict with the
    outcome.
    """
    if fara_response.get("refusal"):
        return {
            "ok": False,
            "refusal": True,
            "reason": fara_response.get("refusal_reason"),
            "action": None,
        }

    action = fara_response.get("action")
    if not action:
        return {"ok": False, "reason": "no_action_in_fara_response", "action": None}

    try:
        if action == "left_click":
            x, y = fara_response["coordinate"]
            humanlike_click(sess, x, y)
        elif action == "type":
            txt = fara_response.get("text", "")
            if "coordinate" in fara_response and fara_response["coordinate"]:
                x, y = fara_response["coordinate"]
                humanlike_click(sess, x, y)
            humanlike_type(sess, txt)
        elif action == "key":
            humanlike_key(sess, fara_response.get("keys", []))
        elif action == "mouse_move":
            x, y = fara_response["coordinate"]
            humanlike_click(sess, x, y, click_count=0)  # move via path, no click
        elif action == "scroll":
            humanlike_scroll(sess, int(fara_response.get("pixels", 0)))
        elif action == "visit_url":
            navigate(sess, fara_response["url"])
        elif action == "web_search":
            # Fara emits this as "go to a search engine and search". We
            # default to Google search.
            from urllib.parse import quote
            q = quote(str(fara_response.get("query", "")))
            navigate(sess, f"https://www.google.com/search?q={q}")
        elif action == "history_back":
            sess.send("Page.navigateToHistoryEntry", {"entryId": -1}, timeout_s=5.0)
        elif action == "wait":
            time.sleep(float(fara_response.get("time", 1.0)))
        elif action == "pause_and_memorize_fact":
            # No browser side-effect; caller's history tracker stores the fact.
            pass
        elif action == "terminate":
            return {"ok": True, "terminated": True, "status": fara_response.get("status", "success"), "action": action}
        else:
            return {"ok": False, "reason": f"unknown_action:{action}", "action": action}
    except Exception as e:
        return {"ok": False, "reason": f"dispatch_threw:{e}", "action": action}

    wait_for_settle(sess, timeout_s=2.0)
    return {"ok": True, "action": action}
