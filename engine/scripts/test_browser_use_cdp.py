"""Slice 2: cdp_url threads through the browser-use action arm to the bridge runner.

Proves browse_act(cdp_url=...) puts cdp_url into the JSON request the runner receives — so the
PROVEN agent ATTACHES to the user's already-running, logged-in Chrome over CDP instead of a
throwaway browser — WITHOUT launching any browser. The subprocess is faked: we capture the stdin
JSON and return a canned sentinel result. Also proves the default (no cdp_url) stays None and the
read path stays act=False (back-compat).

The CDP-attach branch itself lives in browser_use_runner.py (3.11 bridge): cdp_url set ->
BrowserProfile(cdp_url=...) with NO executable_path (browser-use connects, never launches).
Its LIVE proof against a real Chrome is exercised separately (live-proof pending Omar's Chrome).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_use_cdp.py
"""
import json
import subprocess as _real_subprocess
import types

from anticipy_engine.hands import browser_use_link as bul

CAPTURED = {}


class _FakeProc:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


def _fake_run(cmd, input=None, **kwargs):
    CAPTURED["req"] = json.loads(input)
    payload = {"success": True, "result": "ok", "steps": 1, "url": "https://example.org",
               "urls": [], "actions": [], "elapsed_s": 0.1}
    return _FakeProc(bul._RESULT_SENTINEL + " " + json.dumps(payload) + "\n")


def main():
    # the bridge python + runner exist in this repo, so available() passes
    assert bul.available()["ok"], bul.available()
    # fake the subprocess so NO browser launches; keep TimeoutExpired for the except path
    bul.subprocess = types.SimpleNamespace(run=_fake_run,
                                           TimeoutExpired=_real_subprocess.TimeoutExpired)

    # ACTION task WITH cdp_url -> the runner request must carry cdp_url + act=True
    r = bul.browse_act("add the item to the cart", url="https://example.org",
                       cdp_url="http://localhost:9222")
    assert CAPTURED["req"]["cdp_url"] == "http://localhost:9222", CAPTURED["req"]
    assert CAPTURED["req"]["act"] is True, CAPTURED["req"]
    assert r.success is True and r.result == "ok", r

    # default (no cdp_url) -> None, read path act=False (back-compat unchanged)
    bul.browse_read("read the page title", url="https://example.org")
    assert CAPTURED["req"]["cdp_url"] is None, CAPTURED["req"]
    assert CAPTURED["req"]["act"] is False, CAPTURED["req"]

    # SSRF guard: a NON-loopback cdp_url is REFUSED before the runner is ever invoked
    CAPTURED.clear()
    bad = bul.browse_act("add to cart", url="https://example.org", cdp_url="http://169.254.169.254/")
    assert bad.success is False and "loopback" in (bad.error or ""), bad
    assert "req" not in CAPTURED, "must refuse a non-loopback cdp_url BEFORE invoking the runner"
    # a loopback cdp_url is allowed through (already proven above with http://localhost:9222)
    assert bul._cdp_is_loopback("http://127.0.0.1:9222") and not bul._cdp_is_loopback("http://evil.com")

    print("PASS: cdp_url threads through browse_act -> runner request (CDP-attach plumbing)")
    print("  set -> attaches to the user's logged-in Chrome; unset -> throwaway browser (back-compat)")


if __name__ == "__main__":
    main()
