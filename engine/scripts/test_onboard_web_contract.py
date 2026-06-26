"""Static contract gate for the onboarding WEB journey (no browser needed).

The engine onboarding spine is proven by test_onboarding_e2e.py; this asserts the FRONT-END actually
wires the forward-completion path so a real user can always FINISH onboarding — even when no account is
readable (stub model / no debuggable Chrome), the case that used to dead-end the UI. Source-string
assertions, the same approach as factory/bin/check_premium_copy.py.

  test_onboard_web_contract.py            # assert the wiring exists
  test_onboard_web_contract.py --selftest # prove each assertion is load-bearing (planted removals fail)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "web"
HTML = (WEB / "onboard.html").read_text(encoding="utf-8")
JS = (WEB / "onboard.js").read_text(encoding="utf-8")


def _checks(html: str, js: str) -> dict:
    chk = {}
    # 1) the forward-finish button exists in the "nothing readable" block
    chk["finish_button_in_html"] = ("data-onboard-finish" in html)
    # 2) a handler wires that button to a finish function
    chk["finish_handler_wired"] = bool(re.search(r"data-onboard-finish.*addEventListener", js, re.S))
    # 3) finishing PERSISTS completion (so the owner reaches the app + isn't re-trapped)
    chk["finish_posts_complete"] = bool(
        re.search(r"finishOnboarding[\s\S]{0,400}/onboard/complete", js)
        or re.search(r"data-onboard-finish[\s\S]{0,600}/onboard/complete", js))
    # 4) the loop-retry handler must NOT re-run the loop in the same tick (the guaranteed-empty no-op)
    chk["no_synchronous_retry_reload"] = ("openAnticipyBrowser();\n      runLoop();" not in js
                                          and not re.search(r"openAnticipyBrowser\(\);\s*runLoop\(\);", js))
    return chk


def _bad(chk: dict) -> list:
    return [k for k, v in chk.items() if not v]


def _run() -> int:
    chk = _checks(HTML, JS)
    bad = _bad(chk)
    if bad:
        print("FAIL onboard_web_contract — missing wiring:", bad)
        return 1
    print(f"PASS onboard_web_contract: forward-finish path wired ({len(chk)} checks green)")
    return 0


def _selftest() -> int:
    if _bad(_checks(HTML, JS)):
        print("EVAL_BROKEN: live source already fails the contract:", _bad(_checks(HTML, JS)))
        return 2
    # planted removals — each must flip its check to False (proves the assertions are load-bearing)
    planted = [
        ("strip_button", HTML.replace("data-onboard-finish", "data-x-removed"), JS, "finish_button_in_html"),
        ("reintroduce_noop", HTML, JS + "\nopenAnticipyBrowser();\n      runLoop();\n", "no_synchronous_retry_reload"),
    ]
    for name, h, j, must_fail in planted:
        c = _checks(h, j)
        if c.get(must_fail):
            print(f"EVAL_BROKEN: planted '{name}' did not flip '{must_fail}'")
            return 2
        print(f"  planted '{name}' CAUGHT (flipped '{must_fail}')")
    print("PASS onboard_web_contract --selftest: wiring present AND each assertion proven load-bearing")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    return _selftest() if ap.parse_args().selftest else _run()


if __name__ == "__main__":
    sys.exit(main())
