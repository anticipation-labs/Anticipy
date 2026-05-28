"""Integration test for the v7 universal surface runtime.

Test 1 (unit, mocked bridge): exercises every primitive without touching Chrome.
Test 2 (live, real Chrome): opens saucedemo.com, types into the username field,
tabs to advance focus, and verifies the URL is the SauceDemo login surface.
SauceDemo is a real e-commerce login page designed for automation, so the test
exercises navigate plus type plus key plus verify against a realistic surface
rather than a bot-shielded search engine. Best-effort; documents pass/fail.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "engine"))

from app.product.action_dispatcher import ActionDispatcher  # noqa: E402
from app.product.action_planner import ActionPlanner, PlannerStep  # noqa: E402
from app.product.universal_surface_runtime import (  # noqa: E402
    PrimitiveResult, UniversalSurfaceRuntime,
)


def _emit(label: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" +
           (f" :: {detail[:200]}" if detail else ""), flush=True)


def _check(rt, label, result, extra_ok=True, detail=""):
    ok = bool(result.ok) and extra_ok
    _emit(label, ok, detail or result.error)
    return ok


class _Proc:
    def __init__(self, stdout="OK", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _fake_post(path, payload):
    if path == "/surface-proof":
        return True, {"ok": True, "url": "https://example.com/",
                      "title": "Example", "dom": "<html><body>Hi</body></html>",
                      "screenshot_path": "/tmp/fake.png"}, ""
    cmd = payload.get("command")
    if path == "/surface-command" and cmd in ("navigate", "type"):
        return True, {"ok": True, "command": cmd,
                      "data": {"navigatedTo": payload.get("url"),
                               "url": payload.get("url"),
                               "title": "Loaded",
                               "typed": payload.get("text")}}, ""
    return True, {"ok": False, "error": "unsupported"}, ""


def test_unit_primitives() -> bool:
    print("\n=== TEST 1: unit primitives (bridge + osascript mocked) ===",
          flush=True)
    passed = True
    rt = UniversalSurfaceRuntime()
    with patch.object(rt, "_post", side_effect=_fake_post), \
         patch.object(rt, "bridge_alive", return_value=True), \
         patch("app.product.universal_surface_runtime._run_osascript",
                return_value=_Proc()), \
         patch("app.product.universal_surface_runtime.subprocess.run",
                return_value=_Proc()):
        r = rt.read()
        passed &= _check(rt, "read returns surface from bridge", r,
                          extra_ok=r.proof.get("url") == "https://example.com/")
        r = rt.open("https://google.com")
        passed &= _check(rt, "open navigates via bridge", r,
                          extra_ok=r.surface.get("navigated_to") == "https://google.com")
        passed &= _check(rt, "open activates native app", rt.open("Finder"))
        passed &= _check(rt, "type with selector via bridge",
                          rt.type("hello", selector="input#q"))
        passed &= _check(rt, "type fallback via system events",
                          rt.type("focused typing"))
        passed &= _check(rt, "key return", rt.key("return"))
        passed &= _check(rt, "key with modifiers",
                          rt.key("a", modifiers=["command"]))
        passed &= _check(rt, "click via set-of-mark label", rt.click("M2"))
        passed &= _check(rt, "verify accepts matching url/title",
                          rt.verify({"url_contains": "example.com",
                                      "title_contains": "Example"}))
        r = rt.verify({"url_contains": "nope"})
        passed &= _check(rt, "verify reports mismatch honestly",
                          PrimitiveResult(ok=(not r.ok and "verify failed" in r.error),
                                          primitive="verify"),
                          detail=r.error)
        passed &= _check(rt, "wait satisfies url contains",
                          rt.wait({"url_contains": "example.com"},
                                   timeout=2.0, interval=0.2))
        passed &= _check(rt, "ask_user emits prompt",
                          rt.ask_user("Continue?", options=["yes", "no"]))
        passed &= _check(rt, "notify_user emits notification",
                          rt.notify_user("hi"))

    # Dispatcher: success path via "done"
    rt_ok = UniversalSurfaceRuntime()
    with patch.object(rt_ok, "read", return_value=PrimitiveResult(
            ok=True, primitive="read",
            proof={"url": "https://x.com/", "title": "x", "dom_text": "ok"})), \
         patch.object(rt_ok, "execute", return_value=PrimitiveResult(
                ok=True, primitive="open")):
        steps = iter([
            PlannerStep(primitive="open", args={"url_or_app": "https://x.com"},
                         model="stub"),
            PlannerStep(primitive="done", args={}, model="stub"),
        ])
        pl = ActionPlanner()
        with patch.object(pl, "plan_next_primitive",
                           side_effect=lambda *a, **k: next(steps)):
            out = ActionDispatcher(runtime=rt_ok, planner=pl).execute("test")
            ok = out.status == "success" and out.steps == 2
            _emit("dispatcher reaches success when planner emits done", ok,
                  f"status={out.status} steps={out.steps}")
            passed &= ok

    # Dispatcher: retry saturation -> ask_user
    rt_fail = UniversalSurfaceRuntime()
    with patch.object(rt_fail, "read", return_value=PrimitiveResult(
            ok=True, primitive="read",
            proof={"url": "https://x.com/", "title": "x"})), \
         patch.object(rt_fail, "execute", return_value=PrimitiveResult(
                ok=False, primitive="click", error="not found")):
        pl = ActionPlanner()
        with patch.object(pl, "plan_next_primitive",
                           return_value=PlannerStep(
                               primitive="click", args={"target": ".btn"},
                               model="stub")):
            out = ActionDispatcher(runtime=rt_fail, planner=pl,
                                    retry_cap=3, max_steps=10).execute("clk")
            ok = out.status == "ask_user" and "tried click" in out.question
            _emit("dispatcher converts retry saturation into ask_user", ok,
                  f"status={out.status}")
            passed &= ok

    return passed


# ------------------------------------------------- Test 2: live Chrome

def test_live_saucedemo() -> bool:
    print("\n=== TEST 2: live Chrome (SauceDemo login surface) ===",
          flush=True)
    rt = UniversalSurfaceRuntime()
    if not rt.bridge_alive():
        _emit("bridge alive on 127.0.0.1:7777", False,
              "bridge not reachable; skipping live test")
        return False

    # SauceDemo is a public e-commerce site purpose-built for automation. It
    # has stable selectors (#user-name, #password, #login-button) and never
    # bot-blocks, so it is a more realistic surface for the runtime than
    # google.com (which serves a consent wall and rotates DOM frequently).
    nav = rt.open("https://www.saucedemo.com/")
    _emit("open saucedemo.com", nav.ok, nav.error)
    if not nav.ok:
        return False
    time.sleep(1.5)  # let the login form render

    typed = rt.type("standard_user", selector="#user-name")
    _emit("type username into #user-name", typed.ok, typed.error)
    if not typed.ok:
        return False
    time.sleep(0.5)

    tab = rt.key("tab")
    _emit("press tab to advance focus", tab.ok, tab.error)
    if not tab.ok:
        return False
    time.sleep(0.5)

    verified = rt.wait({"url_contains": "saucedemo.com"},
                       timeout=8.0, interval=0.5)
    detail = ""
    if isinstance(verified.proof, dict):
        detail = (f"last_url={verified.proof.get('url') or verified.proof.get('last_url', '')}"
                  f" title={verified.proof.get('last_title', '')[:60]}")
    _emit("verify result URL contains 'saucedemo.com'",
          verified.ok, detail)
    return verified.ok


# ------------------------------------------------------------- entrypoint

def main() -> int:
    t0 = time.time()
    unit_ok = test_unit_primitives()
    live_ok = False
    try:
        live_ok = test_live_saucedemo()
    except Exception as exc:
        _emit("live test crashed", False, f"{type(exc).__name__}: {exc}")
    print(f"\nSUMMARY: unit={'PASS' if unit_ok else 'FAIL'} "
          f"live={'PASS' if live_ok else 'FAIL'} "
          f"elapsed={time.time() - t0:.2f}s", flush=True)
    return 0 if unit_ok else 1


if __name__ == "__main__":
    sys.exit(main())
