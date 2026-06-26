"""CREATE+PRINT routing gate — a physical-sign task reaches the print path; a DIGITAL request does not.

The create+print chokepoint turns "make a sign for the broken door" into a real PDF + an "okay to print?"
card. It must NOT fire for digital requests ("post a warning in the slack channel", "create a label in
gmail") — those would manufacture a spurious physical PDF (overnight bug-hunt #1) — while still firing for
a physical sign that merely MENTIONS a medium ("put up a sign with my email on it"). Hermetic: stub model,
mock hands, temp data dir; drives core.owner_ingest directly (the bus-safe pattern from owner_test_run.py)
so it never resolves the ask / prints / touches a real account.

  test_create_print_routing.py            # assert routing
  test_create_print_routing.py --selftest # + prove the digital-exclusion is load-bearing
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_HANDS_MODE"] = "mock"
os.environ["ANTICIPY_CHANNELS_MODE"] = "mock"
os.environ["ANTICIPY_NATIVE_BRIDGE_FALLBACK"] = "0"
os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
# Force NO network: make_sign uses the smart tier (commit 9a265a1), so a non-keyword sign
# ("...with my email on it") would dispatch a REAL model call. Pop the key so the deriver/stub path
# resolves instantly — this test asserts ROUTING (reaches print?), not the headline wording.
os.environ.pop("OPENROUTER_API_KEY", None)

from anticipy_engine.core.control_core import ControlCore  # noqa: E402

# (utterance, should_reach_print)
PHYSICAL = [
    "make a sign for the broken door",
    "put up a sign with my email on it",            # mentions a medium but is a physical sign
    "print an out-of-order sign for the elevator",
    "make a no-parking sign for the driveway",
]
DIGITAL = [
    "post a warning in the slack channel about the deploy freeze",
    "create a label in gmail for invoices",
    "put a notice on the website about downtime",
    "send a teams message reminding the team",
]


async def _reaches_print(core, text: str) -> bool:
    res = await core.owner_ingest("transcript", text, execute_actions=True)
    cards = (res or {}).get("cards", [])
    return any(c.get("action") == "create_and_print" for c in cards)


async def _check_all() -> list:
    """Return the list of failures (empty = all correct). One fresh core per utterance (clean state)."""
    bad = []
    for t, want in [(x, True) for x in PHYSICAL] + [(x, False) for x in DIGITAL]:
        with tempfile.TemporaryDirectory(prefix="anticipy-cpr-") as d:
            core = ControlCore(data_dir=Path(d))
            await core.start()
            try:
                got = await _reaches_print(core, t)
            finally:
                await core.stop()
        if got != want:
            kind = "PHYSICAL sign did NOT reach print" if want else "DIGITAL request WRONGLY reached print"
            bad.append(f"{kind}: {t!r}")
    return bad


def _run() -> int:
    bad = asyncio.run(_check_all())
    if bad:
        print("FAIL create_print_routing:")
        for b in bad:
            print("  -", b)
        return 1
    print(f"PASS create_print_routing: {len(PHYSICAL)} physical signs print, "
          f"{len(DIGITAL)} digital requests excluded (incl. email-on-sign false-exclusion guard)")
    return 0


async def _selftest_async() -> int:
    bad = await _check_all()
    if bad:
        print("EVAL_BROKEN: live routing already fails:", bad)
        return 2
    # prove the digital-exclusion is load-bearing: the canonical leak excluded AND the door sign prints
    async def one(text):
        with tempfile.TemporaryDirectory(prefix="anticipy-cpr-") as d:
            core = ControlCore(data_dir=Path(d))
            await core.start()
            try:
                return await _reaches_print(core, text)
            finally:
                await core.stop()
    leak = await one("post a warning in the slack channel about the deploy freeze")
    door = await one("make a sign for the broken door")
    if leak:
        print("EVAL_BROKEN: slack-channel request reached the physical print path")
        return 2
    if not door:
        print("EVAL_BROKEN: the door-sign happy path no longer prints")
        return 2
    print("PASS create_print_routing --selftest: digital leak excluded AND door-sign happy path intact")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        return asyncio.run(_selftest_async())
    return _run()


if __name__ == "__main__":
    sys.exit(main())
