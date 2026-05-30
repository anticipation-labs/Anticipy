#!/usr/bin/env python3
"""Smoke test for the cold-start inhale source registry.

Covers:
  - Defaults written on missing file (first call to load_all materializes
    ``~/.anticipy/inhale_sources.json`` with the shipped 3 sources +
    ``_comment``).
  - Edit persists (mutate one source, save, re-load, see the mutation).
  - GET endpoint returns the same doc as the on-disk file.
  - POST endpoint round-trips a valid config and writes atomically.
  - Invalid POST bodies return HTTP 400 with errors.

Sandboxed via ANTICIPY_INHALE_SOURCES_DIR so the smoke does not stomp
the real user config.

Run from repo root:
    python3 engine/scripts/coldstart_sources_smoke.py
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import time
import urllib.request


# Sandbox the inhale config dir BEFORE any imports that might cache it.
SANDBOX = tempfile.mkdtemp(prefix="inhale_sources_smoke_")
os.environ["ANTICIPY_INHALE_SOURCES_DIR"] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.coldstart import sources as inhale_sources  # noqa: E402


def banner(s: str) -> None:
    print(f"\n=== {s} ===", flush=True)


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", flush=True)
    sys.exit(1)


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        fail(f"{label}: expected {expected!r}, got {actual!r}")


def assert_true(cond: bool, label: str) -> None:
    if not cond:
        fail(label)


# ---------------------------------------------------------------------------
# Test 1: first load materializes defaults
# ---------------------------------------------------------------------------
def test_defaults_written_on_missing() -> None:
    banner("test 1: defaults written when file is missing")
    path = inhale_sources.config_path()
    if path.exists():
        path.unlink()
    assert_true(not path.exists(), "precondition: file should not exist")
    doc = inhale_sources.load_all()
    assert_true(path.exists(), "file should have been materialized")
    assert_eq(doc.get("version"), inhale_sources.CONFIG_VERSION,
              "default version")
    assert_eq(len(doc.get("sources") or []), 3,
              "default sources should contain 3 entries")
    ids = sorted(str(s.get("id")) for s in doc["sources"])
    assert_eq(ids, ["gmail", "google_calendar", "google_drive"],
              "default source ids")
    assert_true("_comment" in doc and isinstance(doc["_comment"], str)
                and len(doc["_comment"]) > 20,
                "default comment block")
    # Permissions: 0644 (owner rw, group/world r).
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert_eq(mode, 0o644, "file permissions 0644")
    # load_enabled returns the 3 sorted by priority.
    enabled = inhale_sources.load_enabled()
    assert_eq(len(enabled), 3, "all defaults enabled")
    prios = [int(s.get("priority")) for s in enabled]
    assert_eq(prios, sorted(prios),
              "enabled list sorted by priority ascending")
    print(f"  ok: file at {path}, defaults written, mode 0o{mode:o}")


# ---------------------------------------------------------------------------
# Test 2: edit persists across reads
# ---------------------------------------------------------------------------
def test_edit_persists() -> None:
    banner("test 2: edit + save round-trips")
    doc = inhale_sources.load_all()
    # Disable drive, change calendar URL.
    new_sources = []
    for s in doc["sources"]:
        new_s = dict(s)
        if new_s.get("id") == "google_drive":
            new_s["enabled"] = False
        if new_s.get("id") == "google_calendar":
            new_s["url"] = "https://calendar.google.com/calendar/r/day"
        new_sources.append(new_s)
    new_sources.append({
        "id": "outlook",
        "label": "Outlook web mail",
        "url": "https://outlook.live.com/mail/0/inbox",
        "scrape_selector": "[role='row']",
        "max_pages": 4,
        "enabled": True,
        "priority": 4,
    })
    new_doc = {
        "version": inhale_sources.CONFIG_VERSION,
        "sources": new_sources,
        "_comment": doc["_comment"],
    }
    ok, errors, normalized = inhale_sources.validate_payload(new_doc)
    assert_true(ok, f"validation should pass: {errors}")
    inhale_sources.save(normalized)
    # Re-load and confirm.
    reloaded = inhale_sources.load_all()
    by_id = {s["id"]: s for s in reloaded["sources"]}
    assert_eq(by_id["google_drive"]["enabled"], False,
              "drive should be disabled")
    assert_eq(by_id["google_calendar"]["url"],
              "https://calendar.google.com/calendar/r/day",
              "calendar url updated")
    assert_true("outlook" in by_id, "outlook entry added")
    enabled = inhale_sources.load_enabled()
    enabled_ids = sorted(s["id"] for s in enabled)
    assert_eq(enabled_ids, ["gmail", "google_calendar", "outlook"],
              "load_enabled skips disabled entry")
    print("  ok: edits persisted, disabled entry excluded from enabled list")


# ---------------------------------------------------------------------------
# Test 3 + 4: GET and POST endpoints (in-process FastAPI)
# ---------------------------------------------------------------------------
def _start_server() -> tuple[str, threading.Thread]:
    """Boot the engine FastAPI app on an ephemeral port in a thread."""
    # Prevent the server from spawning side processes during import.
    os.environ.setdefault("ANTICIPY_QUIET", "1")
    os.environ.setdefault("ANTICIPY_NO_BACKGROUND", "1")
    os.environ.setdefault("ANTICIPY_ENGINE_PORT", "0")

    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    import uvicorn
    from app.product.server import app

    config = uvicorn.Config(
        app, host="127.0.0.1", port=port,
        log_level="warning", access_log=False, lifespan="off")
    server = uvicorn.Server(config)

    thread = threading.Thread(
        target=server.run, name="inhale_sources_smoke.uvicorn",
        daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    # Poll for readiness on a known route.
    deadline = time.time() + 12.0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                    f"{base}/healthz", timeout=1.5) as resp:
                if resp.status == 200:
                    return base, thread
        except Exception:
            time.sleep(0.15)
    fail("uvicorn never became ready")
    raise SystemExit(1)  # unreachable; satisfies type checker


def _http_get(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def _http_post(url: str, body: object) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def test_endpoints() -> None:
    banner("test 3+4: GET and POST /api/coldstart/sources")
    base, _ = _start_server()
    # GET returns the on-disk file.
    status, body = _http_get(f"{base}/api/coldstart/sources")
    assert_eq(status, 200, "GET status")
    assert_eq(body.get("ok"), True, "GET ok")
    on_disk = inhale_sources.load_all()
    assert_eq(body.get("config"), on_disk,
              "GET body.config matches on-disk doc")

    # POST round-trips a valid config.
    new_doc = {
        "version": inhale_sources.CONFIG_VERSION,
        "sources": [
            {
                "id": "notion",
                "label": "Notion home",
                "url": "https://www.notion.so",
                "scrape_selector": "[data-block-id]",
                "max_pages": 2,
                "enabled": True,
                "priority": 1,
            },
        ],
        "_comment": "smoke override",
    }
    status, body = _http_post(
        f"{base}/api/coldstart/sources", new_doc)
    assert_eq(status, 200, "POST status")
    assert_eq(body.get("ok"), True, f"POST ok: {body}")
    assert_eq(body["config"]["sources"][0]["id"], "notion",
              "POST persisted single notion entry")
    # The file on disk now reflects the POST.
    after = inhale_sources.load_all()
    assert_eq(len(after["sources"]), 1, "on-disk has 1 source after POST")
    assert_eq(after["sources"][0]["id"], "notion",
              "on-disk source is the POSTed entry")
    # GET sees the same.
    status, body = _http_get(f"{base}/api/coldstart/sources")
    assert_eq(body["config"], after, "GET after POST matches on-disk")

    # Invalid POST: missing required fields, bad url scheme.
    bad = {"sources": [{"id": "x", "label": "y",
                         "url": "ftp://no", "enabled": True}]}
    status, body = _http_post(f"{base}/api/coldstart/sources", bad)
    assert_eq(status, 400, "invalid POST returns 400")
    assert_eq(body.get("ok"), False, "invalid POST not ok")
    assert_true(isinstance(body.get("errors"), list) and body["errors"],
                "invalid POST returns errors list")

    # Invalid POST: sources is not a list.
    status, body = _http_post(
        f"{base}/api/coldstart/sources",
        {"sources": "not a list"})
    assert_eq(status, 400, "non-list sources returns 400")
    print("  ok: GET, POST, and 400-on-invalid all behave")


def main() -> int:
    print(f"sandbox: {SANDBOX}", flush=True)
    test_defaults_written_on_missing()
    test_edit_persists()
    test_endpoints()
    print("\nALL COLDSTART SOURCES SMOKE TESTS PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
