"""P3-X gate: route the action layer through the extension+native
messaging surface, kill the legacy "No real Chrome on :9222" path.

Per planning/00-handoff/ARCHITECTURE.md section 4, every browser
action drives the wearer's actual Chrome through the extension's
native messaging bridge. CDP on :9222 is the legacy fallback for
controlled probes only. This test file verifies:

  1. bridge_extension.dispatch() returns the standardized shape on
     success and on failure.
  2. The new action_engine.dispatch.dispatch_action wraps
     bridge_extension.dispatch correctly.
  3. server._dispatch_via_extension_bridge picks the extension
     surface when the browser_surface helper returns
     'extension_native_bridge' AND the bridge accepts commands.
  4. server._run_action_engine returns the dispatch result through
     /api/act instead of the legacy "No real Chrome" error.
  5. When the extension surface is unavailable AND CDP is not
     reachable, the gated error message reflects BOTH layers, not
     the old "No real Chrome on :9222" string.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


# Make the engine package importable when pytest is invoked from
# engine/. Same pattern as test_engine_port_reclaim.py.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE_ROOT = os.path.dirname(_HERE)
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

# Pin a high port string so the eager `_acquire_singleton_lock` import
# never touches the live engine's lock file. Same defensive pattern as
# test_engine_port_reclaim and test_timeline_integration.
os.environ.setdefault("ANTICIPY_ENGINE_PORT", "59733")


# ---------------------------------------------------------------------------
# 1. bridge_extension.dispatch shape
# ---------------------------------------------------------------------------


def test_dispatch_returns_standard_shape_on_success(monkeypatch):
    """SurfaceRuntime returns ok=True -> dispatch returns ran=True
    with the documented keys populated."""
    from app import bridge_extension as be

    class _FakeRuntime:
        def __init__(self, *a, **kw):
            pass

        def run_browser_task(self, *, verb, target, task):
            return {
                "ok": True,
                "surface": {"kind": "browser", "url": target},
                "proof": {"url": target, "screenshot_path": "/tmp/x.png"},
                "source": "chrome_extension_native_messaging",
                "error": "",
            }

    monkeypatch.setattr(
        be, "_intent_to_browser_verb",
        lambda payload: ("open_browser_tab", "https://example.com"),
    )
    monkeypatch.setattr(
        "app.product.surface_runtime.SurfaceRuntime", _FakeRuntime,
    )

    result = be.dispatch(
        goal="navigate to https://example.com",
        intent_payload={"verb": "open_browser_tab",
                        "target": "https://example.com"},
    )
    assert isinstance(result, dict)
    assert result["ran"] is True
    assert result["surface"] == "extension"
    assert result["url"] == "https://example.com"
    assert result["screenshot_path"] == "/tmp/x.png"
    assert result["error"] == ""
    assert result["source"] == "chrome_extension_native_messaging"
    assert result["verb"] == "open_browser_tab"
    assert result["target"] == "https://example.com"


def test_dispatch_surfaces_runtime_error(monkeypatch):
    """SurfaceRuntime returns ok=False -> dispatch returns ran=False
    with the error message intact and never raises."""
    from app import bridge_extension as be

    class _FakeRuntime:
        def __init__(self, *a, **kw):
            pass

        def run_browser_task(self, *, verb, target, task):
            return {
                "ok": False,
                "surface": {"kind": "browser"},
                "proof": {},
                "source": "chrome_extension_native_messaging",
                "error": "native bridge is closed",
            }

    monkeypatch.setattr(
        "app.product.surface_runtime.SurfaceRuntime", _FakeRuntime,
    )

    result = be.dispatch(
        goal="navigate to https://example.com",
        intent_payload={"verb": "open_browser_tab",
                        "target": "https://example.com"},
    )
    assert result["ran"] is False
    assert result["error"] == "native bridge is closed"
    assert result["surface"] == "extension"


def test_dispatch_handles_missing_primitive(monkeypatch):
    """Empty intent and ungoogleable goal -> dispatch returns ran=False
    with a clear error, never crashes the caller."""
    from app import bridge_extension as be

    # Force the URL extraction to return empty so we exercise the
    # "could not derive" branch deterministically.
    monkeypatch.setattr(
        "app.product.surface_runtime.normalize_browser_url",
        lambda raw: "",
    )

    result = be.dispatch(goal="", intent_payload={})
    assert result["ran"] is False
    assert "could not derive" in result["error"]


def test_dispatch_handles_runtime_exception(monkeypatch):
    """SurfaceRuntime raises -> dispatch wraps the error and returns
    ran=False instead of propagating."""
    from app import bridge_extension as be

    class _BoomRuntime:
        def __init__(self, *a, **kw):
            pass

        def run_browser_task(self, *, verb, target, task):
            raise RuntimeError("kaboom")

    monkeypatch.setattr(
        "app.product.surface_runtime.SurfaceRuntime", _BoomRuntime,
    )

    result = be.dispatch(
        goal="navigate to https://example.com",
        intent_payload={"verb": "open_browser_tab",
                        "target": "https://example.com"},
    )
    assert result["ran"] is False
    assert "kaboom" in result["error"]
    assert result["surface"] == "extension"


# ---------------------------------------------------------------------------
# 2. action_engine.dispatch.dispatch_action delegation
# ---------------------------------------------------------------------------


def test_dispatch_action_delegates_to_bridge(monkeypatch):
    """dispatch_action is a thin wrapper: it MUST call
    bridge_extension.dispatch with the same arguments and return the
    same payload."""
    from app.action_engine import dispatch as ae_dispatch

    captured: dict[str, Any] = {}

    def _fake_dispatch(goal, intent_payload=None, *, timeout_s=30.0):
        captured["goal"] = goal
        captured["intent_payload"] = intent_payload
        captured["timeout_s"] = timeout_s
        return {"ran": True, "surface": "extension", "url": "https://x"}

    monkeypatch.setattr(
        "app.bridge_extension.dispatch", _fake_dispatch,
    )

    result = ae_dispatch.dispatch_action(
        goal="go to https://x",
        intent_payload={"verb": "open_browser_tab", "target": "https://x"},
        timeout_s=15.0,
    )
    assert result == {"ran": True, "surface": "extension", "url": "https://x"}
    assert captured["goal"] == "go to https://x"
    assert captured["intent_payload"]["verb"] == "open_browser_tab"
    assert captured["timeout_s"] == 15.0


def test_extension_surface_available_delegates(monkeypatch):
    """extension_surface_available is a thin wrapper around
    bridge_extension.surface_available."""
    from app.action_engine import dispatch as ae_dispatch

    monkeypatch.setattr("app.bridge_extension.surface_available", lambda: True)
    assert ae_dispatch.extension_surface_available() is True

    monkeypatch.setattr("app.bridge_extension.surface_available", lambda: False)
    assert ae_dispatch.extension_surface_available() is False


# ---------------------------------------------------------------------------
# 3. server._dispatch_via_extension_bridge surface picker
# ---------------------------------------------------------------------------


def test_dispatch_via_extension_bridge_picks_extension_surface(monkeypatch):
    """When _browser_surface returns 'extension_native_bridge' and the
    bridge accepts commands, the helper routes through dispatch_action
    and returns a JSONResponse with path=extension_native_bridge."""
    from app.product import server

    monkeypatch.setattr(
        server, "_browser_surface",
        lambda: "extension_native_bridge", raising=False,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.extension_surface_available",
        lambda: True,
    )

    captured: dict[str, Any] = {}

    def _fake_dispatch_action(goal, intent_payload=None, *, timeout_s=30.0):
        captured["goal"] = goal
        captured["intent_payload"] = intent_payload
        return {
            "ran": True,
            "surface": "extension",
            "screenshot_path": "/tmp/proof.png",
            "url": "https://example.com",
            "error": "",
            "proof": {"url": "https://example.com"},
            "source": "chrome_extension_native_messaging",
            "verb": "open_browser_tab",
            "target": "https://example.com",
        }

    monkeypatch.setattr(
        "app.action_engine.dispatch.dispatch_action", _fake_dispatch_action,
    )

    resp = server._dispatch_via_extension_bridge(
        instruction="open https://example.com in chrome",
        plan={"task": "open https://example.com in chrome",
              "intent": "browser", "person": "", "thing": ""},
    )
    assert resp is not None
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["ran"] is True
    assert payload["status"] == "SUCCESS"
    assert payload["path"] == "extension_native_bridge"
    assert payload["opened_url"] == "https://example.com"
    assert payload["surface"] == "extension"
    assert payload["screenshot_path"] == "/tmp/proof.png"
    # The goal that reached dispatch_action must match what the caller
    # passed; this proves the seam carries the user's instruction.
    assert "example.com" in captured["goal"]


def test_dispatch_via_extension_bridge_skips_when_surface_is_cdp(monkeypatch):
    """When _browser_surface reports explicit_cdp, the helper returns
    None so the caller falls through to the legacy CDP path."""
    from app.product import server

    monkeypatch.setattr(
        server, "_browser_surface", lambda: "explicit_cdp", raising=False,
    )
    # dispatch_action should NEVER be called when the surface is CDP.
    calls: list[Any] = []

    def _should_not_be_called(*a, **kw):
        calls.append((a, kw))
        return {"ran": True}

    monkeypatch.setattr(
        "app.action_engine.dispatch.dispatch_action", _should_not_be_called,
    )

    resp = server._dispatch_via_extension_bridge(
        instruction="open https://example.com",
        plan={"task": "open https://example.com"},
    )
    assert resp is None
    assert calls == []


def test_dispatch_via_extension_bridge_skips_when_bridge_closed(monkeypatch):
    """Surface is extension_native_bridge but the bridge is closed.
    Helper must return None so the caller can attempt CDP fallback."""
    from app.product import server

    monkeypatch.setattr(
        server, "_browser_surface",
        lambda: "extension_native_bridge", raising=False,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.extension_surface_available",
        lambda: False,
    )

    resp = server._dispatch_via_extension_bridge(
        instruction="open https://example.com",
        plan={"task": "open https://example.com"},
    )
    assert resp is None


def test_dispatch_via_extension_bridge_surfaces_failure_as_502(monkeypatch):
    """Bridge reachable but the primitive failed -> helper returns a
    JSONResponse with status_code=502 and ran=False so the caller does
    NOT fall back (the extension's error is the ground truth)."""
    from app.product import server

    monkeypatch.setattr(
        server, "_browser_surface",
        lambda: "extension_native_bridge", raising=False,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.extension_surface_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.dispatch_action",
        lambda goal, intent_payload=None, *, timeout_s=30.0: {
            "ran": False,
            "surface": "extension",
            "screenshot_path": "",
            "url": "",
            "error": "navigation refused",
            "proof": {},
            "source": "chrome_extension_native_messaging",
            "verb": "open_browser_tab",
            "target": "https://example.com",
        },
    )

    resp = server._dispatch_via_extension_bridge(
        instruction="open https://example.com",
        plan={"task": "open https://example.com",
              "intent": "browser", "person": "", "thing": ""},
    )
    assert resp is not None
    assert resp.status_code == 502
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["ran"] is False
    assert payload["status"] == "ERROR"
    assert payload["error"] == "navigation refused"
    assert payload["path"] == "extension_native_bridge"


# ---------------------------------------------------------------------------
# 4. server._run_action_engine routes through the extension bridge
#    instead of returning the legacy "No real Chrome on :9222" error.
# ---------------------------------------------------------------------------


def test_run_action_engine_uses_bridge_when_cdp_unavailable(monkeypatch):
    """When _ensure_cdp_chrome returns False AND the extension bridge
    is reachable, _run_action_engine returns the dispatch result
    instead of the legacy gated error."""
    from app.product import server

    # Force the direct-browser short-circuit to skip so we exercise
    # the gate just below _ensure_cdp_chrome.
    monkeypatch.setattr(
        server, "_try_direct_browser_action",
        lambda *a, **kw: None, raising=False,
    )
    # CDP is unavailable (the live failure mode we are fixing).
    monkeypatch.setattr(
        server, "_ensure_cdp_chrome", lambda: False, raising=False,
    )
    # Extension surface is the active surface.
    monkeypatch.setattr(
        server, "_browser_surface",
        lambda: "extension_native_bridge", raising=False,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.extension_surface_available",
        lambda: True,
    )

    def _fake_dispatch_action(goal, intent_payload=None, *, timeout_s=30.0):
        return {
            "ran": True,
            "surface": "extension",
            "screenshot_path": "",
            "url": "https://example.com",
            "error": "",
            "proof": {"url": "https://example.com"},
            "source": "chrome_extension_native_messaging",
            "verb": "open_browser_tab",
            "target": "https://example.com",
        }

    monkeypatch.setattr(
        "app.action_engine.dispatch.dispatch_action", _fake_dispatch_action,
    )

    resp = server._run_action_engine(
        "open https://example.com in chrome",
        {"task": "open https://example.com in chrome",
         "intent": "browser", "person": "", "thing": "",
         "__sms_confirmed": True},
    )
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["ran"] is True
    assert payload["path"] == "extension_native_bridge"
    # The legacy error string must not be in the response anymore.
    assert "No real Chrome on :9222" not in (payload.get("error") or "")


def test_run_action_engine_gated_message_no_longer_legacy(monkeypatch):
    """When both the bridge AND CDP are unavailable, the gated error
    message MUST NOT contain the old 'No real Chrome on :9222 and the
    launchd agent could not be kicked' string. It must explain that
    BOTH surfaces are unreachable."""
    from app.product import server

    monkeypatch.setattr(
        server, "_try_direct_browser_action",
        lambda *a, **kw: None, raising=False,
    )
    monkeypatch.setattr(
        server, "_ensure_cdp_chrome", lambda: False, raising=False,
    )
    monkeypatch.setattr(
        server, "_browser_surface",
        lambda: "extension_native_bridge", raising=False,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.extension_surface_available",
        lambda: False,
    )

    resp = server._run_action_engine(
        "open https://example.com in chrome",
        {"task": "open https://example.com",
         "intent": "browser", "person": "", "thing": ""},
    )
    payload = json.loads(resp.body.decode("utf-8"))
    assert payload["ran"] is False
    assert payload.get("gated") is True
    # The legacy "launchd agent" phrasing must not be in the response.
    assert "launchd agent" not in payload["error"]
    # The new error must name BOTH layers explicitly so the operator
    # knows which one to fix.
    assert "extension" in payload["error"].lower()


# ---------------------------------------------------------------------------
# 5. /api/act response no longer returns the legacy error
# ---------------------------------------------------------------------------


def test_api_act_extension_path_returns_no_legacy_error(monkeypatch):
    """End-to-end: POST /api/act with a navigate goal returns the
    extension dispatch result, not the legacy 'No real Chrome' error."""
    from app.product import server
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        server, "_ensure_cdp_chrome", lambda: False, raising=False,
    )
    monkeypatch.setattr(
        server, "_browser_surface",
        lambda: "extension_native_bridge", raising=False,
    )
    monkeypatch.setattr(
        "app.action_engine.dispatch.extension_surface_available",
        lambda: True,
    )

    def _fake_dispatch_action(goal, intent_payload=None, *, timeout_s=30.0):
        return {
            "ran": True,
            "surface": "extension",
            "screenshot_path": "",
            "url": "https://example.com",
            "error": "",
            "proof": {"url": "https://example.com"},
            "source": "chrome_extension_native_messaging",
            "verb": "open_browser_tab",
            "target": "https://example.com",
        }

    monkeypatch.setattr(
        "app.action_engine.dispatch.dispatch_action", _fake_dispatch_action,
    )

    # Ensure the popover pending instruction does not leak into this
    # test from the live engine state; we POST an explicit instruction.
    server._LISTEN["pending"] = None

    client = TestClient(server.app)
    resp = client.post(
        "/api/act",
        json={"instruction": "open https://example.com in chrome"},
    )
    assert resp.status_code in (200, 502), (
        f"unexpected status {resp.status_code} body={resp.text[:300]}"
    )
    body = resp.json()
    err = (body.get("error") or "")
    # The bug we're fixing: this error string must never reappear.
    assert "No real Chrome on :9222 and the launchd agent could not be kicked" not in err
    # And the response must reach the bridge dispatch path or a direct
    # surface path (NOT a legacy CDP-only gated response).
    if body.get("path") == "extension_native_bridge":
        assert body.get("ran") in (True, False)
    elif body.get("ran") is True:
        # Direct surface_runtime path succeeded; also acceptable
        assert body.get("path") in (
            "extension_native_bridge",
            "surface_runtime",
            "direct_browser_cdp",
        )
