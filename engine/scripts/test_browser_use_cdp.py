"""browser-use CDP attach + the MONEY hard stop on the logged-in Chrome.

cdp_url lets the proven agent attach to the user's already-running Chrome. But the browser-use action
guard is only a PROMPT instruction (not a code-level pay-click block like WebVoyager's PURCHASE_GUARD),
so running ACTIONS on a logged-in session (saved cards, one-click buy) would have no deterministic money
stop. Policy (money is the hard stop):
  - READS (act=False) MAY attach to the logged-in Chrome (cdp_url threads through to the runner).
  - ACTIONS (browse_act / act=True) with cdp_url are REFUSED before the runner — actions run only on a
    throwaway browser (no saved payment), until a code-level pay-click guard is verified on a real browser.
  - a non-loopback cdp_url is refused (SSRF) for any call.
No browser is launched here: the subprocess is faked (we capture the stdin JSON).

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
    import os as _os
    import sys as _sys
    import tempfile as _tempfile
    # This test FAKES the subprocess (no real browser is ever launched) and exists to prove the
    # cdp/money/SSRF logic, NOT browser readiness. available() is now HONEST: it reports ok=False
    # when the cached Chromium binary is absent (the false-ready fix). So we make the two non-browser
    # prerequisites genuinely satisfiable here — point the bridge python at a real interpreter and the
    # chrome-bin env at a real existing file — so available() is legitimately ok and browse_read does
    # not (correctly) short-circuit on a missing browser before exercising the cdp logic.
    _fake_chrome = _tempfile.NamedTemporaryFile(prefix="anticipy-cdp-test-chrome-", delete=False).name
    _os.environ["ANTICIPY_BU_CHROME_BIN"] = _fake_chrome
    _os.environ["ANTICIPY_BROWSERUSE_PYTHON"] = _sys.executable
    assert bul.available()["ok"], bul.available()
    bul.subprocess = types.SimpleNamespace(run=_fake_run,
                                           TimeoutExpired=_real_subprocess.TimeoutExpired)

    # READ with a loopback cdp_url THREADS THROUGH (attaching for a read is allowed — no actions)
    CAPTURED.clear()
    r = bul.browse_read("read the page title", url="https://example.org", cdp_url="http://127.0.0.1:9222")
    assert CAPTURED["req"]["cdp_url"] == "http://127.0.0.1:9222", CAPTURED["req"]
    assert CAPTURED["req"]["act"] is False, CAPTURED["req"]
    assert r.success is True and r.result == "ok", r

    # ACTION (browse_act) with a loopback cdp_url is REFUSED (money hard stop) — never reaches the runner
    CAPTURED.clear()
    bad = bul.browse_act("add the item to the cart", url="https://example.org", cdp_url="http://127.0.0.1:9222")
    err = (bad.error or "").lower()
    assert bad.success is False and ("money" in err or "logged-in" in err), bad
    assert "req" not in CAPTURED, "an action in the logged-in Chrome must be refused BEFORE the runner"

    # ACTION WITHOUT cdp_url -> runs on the throwaway browser (act threads through; no saved payment)
    CAPTURED.clear()
    ok = bul.browse_act("add the item to the cart", url="https://example.org")
    assert CAPTURED["req"]["act"] is True and CAPTURED["req"]["cdp_url"] is None, CAPTURED["req"]
    assert ok.success is True, ok

    # ENV BACKDOOR closed: an ACTION with NO param cdp_url but ANTICIPY_BROWSERUSE_CDP_URL set must
    # STILL be refused (the runner derives cdp_url from req OR that env, so a param-only guard would
    # let an env-set cdp slip an action into the logged-in Chrome).
    import os as _os
    CAPTURED.clear()
    _os.environ["ANTICIPY_BROWSERUSE_CDP_URL"] = "http://127.0.0.1:9222"
    try:
        env_bad = bul.browse_act("add to cart", url="https://example.org")  # no param cdp_url
        e2 = (env_bad.error or "").lower()
        assert env_bad.success is False and ("money" in e2 or "logged-in" in e2), env_bad
        assert "req" not in CAPTURED, "an env-set cdp must refuse an action BEFORE the runner"
    finally:
        _os.environ.pop("ANTICIPY_BROWSERUSE_CDP_URL", None)

    # a non-loopback cdp_url is refused (SSRF) even for a read
    CAPTURED.clear()
    ssrf = bul.browse_read("x", url="https://example.org", cdp_url="http://169.254.169.254/")
    assert ssrf.success is False and "loopback" in (ssrf.error or ""), ssrf
    assert "req" not in CAPTURED, "a non-loopback cdp_url must be refused before the runner"

    assert bul._cdp_is_loopback("http://127.0.0.1:9222") and not bul._cdp_is_loopback("http://evil.com")

    try:
        _os.unlink(_fake_chrome)
    except OSError:
        pass

    print("PASS: cdp_url attaches for READS; ACTIONS in the logged-in Chrome are REFUSED (money hard stop); "
          "actions run on a throwaway browser; SSRF + loopback guards hold")


if __name__ == "__main__":
    main()
