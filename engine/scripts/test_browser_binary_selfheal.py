"""LOCK: the throwaway-browser binary resolver SELF-HEALS across Playwright version bumps.

Regression for the live Gate-3/Gate-4 bug: the engine pinned `chromium-1161`, but Playwright had
updated the cache to `chromium-1223` (1161 deleted). `chrome_binary()` returned the dead pin, so
`available()` reported "chrome binary missing" and every AUTO_DO_WITH_OPT_OUT web task (e.g. the
Amazon refund) failed in ~0.0s without ever launching a browser. The fix: when the env override is
absent and the pinned path is gone, auto-discover the NEWEST installed chromium-* in the cache.

Deterministic — builds a fake ms-playwright cache in a temp dir (no real browser, no network):
a dead 1161 dir (no binary) + a live 1223 dir (with the CFT binary) + a headless_shell decoy that
must be ignored. Asserts the resolver picks the highest-numbered build with a real binary.
"""
import os
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anticipy_engine.hands.browser_use_link import _discover_cached_chromium  # noqa: E402


def _make_cft(base: Path, ver: int) -> Path:
    """Create a fake CFT layout under chromium-<ver> and return the binary path."""
    rel = "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    p = base / f"chromium-{ver}" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#!/bin/sh\nexit 0\n")
    return p


def main():
    fails = []
    cache = Path(tempfile.mkdtemp())

    # dead pin: chromium-1161 dir exists but has NO binary (the rot)
    (cache / "chromium-1161" / "chrome-mac" / "Chromium.app" / "Contents" / "MacOS").mkdir(parents=True)
    # a headless_shell decoy that MUST be ignored (hyphen-glob excludes the underscore name)
    (cache / "chromium_headless_shell-1223" / "chrome-mac-arm64").mkdir(parents=True)
    # two live builds; the resolver must pick the NEWEST by number, not lexical order
    _make_cft(cache, 1207)
    newest = _make_cft(cache, 1223)

    got = _discover_cached_chromium(cache_dir=str(cache))
    if got != str(newest):
        fails.append(f"expected newest build {newest}, got {got}")

    # empty cache -> None (so available()/runner still report an honest 'missing')
    empty = Path(tempfile.mkdtemp())
    if _discover_cached_chromium(cache_dir=str(empty)) is not None:
        fails.append("empty cache must return None (honest 'missing'), not a fabricated path")

    if fails:
        for f in fails:
            print("FAIL:", f)
        raise SystemExit(1)
    print("PASS browser_binary_selfheal: resolver picks newest installed chromium; empty cache -> None")


if __name__ == "__main__":
    main()
