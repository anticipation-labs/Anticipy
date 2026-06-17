"""GATE F — available() must be HONEST about a missing chrome binary.

The false-ready bug: browser_use_link.available() returned ok=True by checking
only the bridge python + runner — it NEVER probed the chrome binary the runner
must LAUNCH. So it reported "ready" even though the chromium-1161 cache was
absent and the runner fails at "chrome binary missing". This test pins the fix:
  - binary ABSENT, no CDP url   -> ok=False with a clear "chrome binary missing" reason
  - binary PRESENT              -> ok=True (when bridge python + runner also exist)
  - binary ABSENT but CDP url   -> ok=True (attach mode needs no local binary)
  - browse_read short-circuits with an honest error when ok=False (no faked success)

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_available_probe.py
"""
import os
import tempfile

from anticipy_engine.hands import browser_use_link as link


def _clear_cdp():
    os.environ.pop("ANTICIPY_BROWSERUSE_CDP_URL", None)


def main():
    _clear_cdp()
    # Point the bridge python at something that exists so it's never the failing
    # prerequisite — we want to isolate the CHROME probe. The current interpreter
    # is a real, existing python.
    import sys
    os.environ["ANTICIPY_BROWSERUSE_PYTHON"] = sys.executable
    assert os.path.exists(link._RUNNER_PATH), "runner must exist for this test to isolate the chrome probe"

    # 1) chrome binary ABSENT, no CDP -> ok MUST be False, with an honest reason.
    os.environ["ANTICIPY_BU_CHROME_BIN"] = "/nonexistent/anticipy/chromium/does/not/exist"
    probe = link.available()
    assert probe["ok"] is False, ("false-ready bug: available() said ok=True with no chrome binary", probe)
    assert probe["chrome_bin_exists"] is False, probe
    assert probe["browser_ready"] is False, probe
    assert "chrome binary missing" in probe["reason"], probe
    # bridge python + runner are present, so the ONLY reason must be the binary.
    assert probe["bridge_python_exists"] is True and probe["runner_exists"] is True, probe
    print("PASS available(): chrome ABSENT + no CDP -> ok=False, reason names the missing binary")

    # 2) browse_read must short-circuit honestly (no faked success) when ok=False.
    res = link.browse_read("read the page", url="https://example.com")
    assert res.success is False, res
    assert "browser bridge unavailable" in (res.error or ""), res
    assert "chrome binary missing" in (res.error or ""), res
    print("PASS browse_read: missing-binary -> honest failure, never a faked success")

    # 3) chrome binary PRESENT -> ok=True (use a real temp file as the 'binary').
    with tempfile.NamedTemporaryFile(prefix="anticipy-fake-chromium-", delete=False) as f:
        fake_bin = f.name
    try:
        os.environ["ANTICIPY_BU_CHROME_BIN"] = fake_bin
        probe = link.available()
        assert probe["ok"] is True, ("present binary should be ready", probe)
        assert probe["chrome_bin_exists"] is True and probe["browser_ready"] is True, probe
        print("PASS available(): chrome PRESENT -> ok=True (browser reachable)")
    finally:
        os.unlink(fake_bin)

    # 4) chrome binary ABSENT but a loopback CDP url configured -> ok=True
    #    (attach mode needs no local binary, mirroring the runner).
    os.environ["ANTICIPY_BU_CHROME_BIN"] = "/nonexistent/anticipy/chromium/does/not/exist"
    os.environ["ANTICIPY_BROWSERUSE_CDP_URL"] = "http://127.0.0.1:9222"
    try:
        probe = link.available()
        assert probe["ok"] is True, ("CDP-attach should not require a local binary", probe)
        assert probe["chrome_bin_exists"] is False and probe["cdp_attach"] is True, probe
        assert probe["browser_ready"] is True, probe
        print("PASS available(): chrome ABSENT + CDP url -> ok=True (attach needs no local binary)")
    finally:
        _clear_cdp()

    print("ALL available()-probe TESTS PASSED")


if __name__ == "__main__":
    main()
