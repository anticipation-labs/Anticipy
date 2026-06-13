#!/usr/bin/env python3
"""LIVE integration test for the open-source browser arm — Slice 6 step 3.

NOT part of the stub suite (it launches a real browser + makes real model calls
+ hits the live internet). It runs from the 3.10 ENGINE side, calls
`browser_use_link.browse_read` (which shells out to the 3.11 bridge runner), and
ASSERTS a verified read comes back from a real public page.

Run (from the engine 3.10 venv — that's the whole point, it proves the 3.10
engine can drive the open-source arm without importing browser_use):

  PYTHONPATH=engine engine/.venv/bin/python \
      engine/scripts/test_browser_use_link_live.py

Guardrails: READ-ONLY public page (Hacker News / example.com); no login, no
write, no money. The runner uses browser-use's own throwaway browser.
"""
import sys
from pathlib import Path

# Make the engine package importable when run directly.
_ENGINE = Path(__file__).resolve().parents[1]
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

from anticipy_engine.hands import browser_use_link as L  # noqa: E402


def _fail(msg: str) -> None:
    print(f"\nLIVE TEST FAILED: {msg}")
    sys.exit(1)


def main() -> None:
    print(f"engine python: {sys.version.split()[0]} (must be 3.10.x)")
    assert "browser_use" not in sys.modules, "browser_use leaked into engine!"
    print("browser_use NOT imported into the engine process -> separation holds")

    probe = L.available()
    print("bridge available():", probe)
    if not probe["ok"]:
        _fail(f"bridge not available: {probe}")

    # A real, stable, public, read-only page. example.com is tiny + reliable;
    # the verifiable fact is its <h1> heading text "Example Domain".
    url = "https://example.com"
    task = (
        "Read this page and report, verbatim, the exact text of the main "
        "heading (the big H1 title) shown on the page."
    )
    print(f"\nLIVE READ: {url}\n  task: {task}\n  (launching real browser via 3.11 bridge...)")
    res = L.browse_read(task, url=url, structured=False, max_steps=8, timeout_s=240)

    print("\n==== RESULT ====")
    import json as _json
    print(_json.dumps(res.as_dict(), indent=2, default=str))

    if res.error and not res.success:
        _fail(f"bridge returned an error: {res.error}")
    if not res.success:
        _fail("runner did not report success (honest: no faked success)")
    if not res.result:
        _fail("success reported but result text empty")

    # Verify the real fact actually came through the engine boundary.
    expected = "example domain"
    if expected not in (res.result or "").lower():
        _fail(
            f"result did not contain the verifiable fact '{expected}'. "
            f"got: {res.result!r}"
        )

    # Trust marking sanity (Slice-0 read-back insight): a coarse read is flagged
    # for cross-check, never silently treated as ground truth.
    assert res.needs_cross_check is True, "coarse read must be flagged for cross-check"
    assert res.url, "must report the URL actually visited"

    print("\n==== VERIFIED ====")
    print(f"  url visited      : {res.url}")
    print(f"  verifiable fact  : 'Example Domain' present in result")
    print(f"  real fact returned: {res.result!r}")
    print(f"  steps            : {res.steps}   elapsed: {res.elapsed_s}s")
    print(f"  trust            : {res.trust}   needs_cross_check: {res.needs_cross_check}")
    print("\nLIVE TEST PASSED: 3.10 engine drove the open-source browser arm to a verified read.")


if __name__ == "__main__":
    main()
