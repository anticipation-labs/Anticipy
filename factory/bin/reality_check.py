#!/usr/bin/env python3
"""THE REALITY GATE — the anti-fake-done forcing function.

Omar's standing complaint: "done" keeps meaning "the code exists / a mock test passed,"
never "a real person used it and it worked." This script makes that impossible to fake.

It defines the finish line as a list of ATOMIC criteria, each with a check that hits the
REAL, LIVE system (the public site, the running engine, the Twilio log, the glass-box) and
reads the answer BACK independently — never a mock, never the actor's own claim. It then
WRITES logs/factory/FINISH_LINE.md *from those live results*, so the ledger can only ever say
REAL when reality says REAL. The loop advances only when this gate flips an item to REAL.

Verdicts:  REAL (verified live)  ·  NOT_REAL (built or not, but does not work live)
           NEEDS_OMAR (only Omar can finish: Apple notarization, OAuth, his 5 real days)
           UNKNOWN (couldn't check — network/engine down; NEVER counted as done)

Exit code: 0 only when every me-verifiable criterion is REAL (i.e. nothing left that I can
finish alone). Non-zero otherwise — so a loop/CI can use it as the literal "are we done yet?".

Run: factory/bin/reality_check.py        (or with --quiet for just the scoreboard)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LEDGER = REPO / "logs" / "factory" / "FINISH_LINE.md"
GLASSBOX = Path(os.environ.get("ANTICIPY_DATA_DIR", "/tmp/anticipy_demo_data")) / "glassbox.jsonl"
ENGINE = os.environ.get("ANTICIPY_ENGINE_URL", "http://127.0.0.1:8787")
PUBLIC = "https://anticipy.ai"

REAL, NOT_REAL, NEEDS_OMAR, UNKNOWN = "REAL", "NOT_REAL", "NEEDS_OMAR", "UNKNOWN"


def _http(url, *, data=None, headers=None, timeout=12):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (trusted hosts)
        return r.getcode(), r.read().decode("utf-8", "replace")


def _owner_token():
    env = REPO / ".env.local"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ANTICIPY_OWNER_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("ANTICIPY_OWNER_API_TOKEN", "")


def _glassbox_tail(n=4000):
    if not GLASSBOX.exists():
        return []
    try:
        lines = GLASSBOX.read_text(errors="replace").splitlines()[-n:]
    except Exception:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


# ---- the criteria. each returns (verdict, evidence). ground EVERY answer in a live read. ----

def c_front_door_leads_to_product():
    """A stranger landing on anticipy.ai can find a path to the WORKING SOFTWARE — not only a
    $149.99 pendant pre-order."""
    try:
        code, html = _http(PUBLIC, timeout=12)
    except Exception as e:
        return UNKNOWN, f"could not fetch {PUBLIC}: {e}"
    low = html.lower()
    leads = any(t in low for t in ('href="/app"', 'href="/download"', ">download<", "get the app", "start listening"))
    pendant = "pre-order" in low or "preorder" in low or "$149" in low or "waitlist" in low
    if leads:
        return REAL, "homepage has a discoverable link/CTA into the software"
    if pendant:
        return NOT_REAL, "homepage offers only the pendant pre-order / waitlist; no discoverable app download"
    return NOT_REAL, "homepage has no discoverable path to the product"


def c_install_no_terminal():
    """The recommended install does NOT require Terminal (curl|bash) or a Gatekeeper override."""
    for path in ("/app", "/download", "/install.sh"):
        try:
            code, body = _http(PUBLIC + path, timeout=12)
        except Exception:
            continue
        low = body.lower()
        if "curl " in low and "| bash" in low.replace("|bash", "| bash"):
            return NOT_REAL, f"{path} tells the user to paste a Terminal command (curl | bash)"
        if "not yet apple-notarized" in low or "is damaged" in low or "quarantine" in low:
            return NOT_REAL, f"{path} admits the app is not notarized (Gatekeeper will block a stranger)"
    return UNKNOWN, "could not confirm a clean, no-terminal install path"


def c_download_notarized():
    """The Mac app opens on a stranger's machine without the 'damaged / unidentified' block."""
    # we cannot notarize without Omar's Apple Developer account
    dmgs = list((REPO).glob("**/*.dmg")) + list(Path.home().glob("Downloads/Anticipy*.dmg"))
    for dmg in dmgs[:3]:
        try:
            r = subprocess.run(["xcrun", "stapler", "validate", str(dmg)],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and "validated" in (r.stdout + r.stderr).lower():
                return REAL, f"{dmg.name} is notarized + stapled (Gatekeeper will open it)"
        except Exception:
            pass
    return NEEDS_OMAR, "Apple notarization requires Omar's Developer ID/password; no notarized local DMG found"


def c_engine_live():
    """The engine is actually running and healthy."""
    try:
        code, body = _http(ENGINE + "/status", timeout=8)
        d = json.loads(body)
        if d.get("engine") == "ok":
            return REAL, f"engine up; channels={d.get('channels',{}).get('mode')}"
        return NOT_REAL, f"engine returned: {body[:120]}"
    except Exception as e:
        return UNKNOWN, f"engine not reachable at {ENGINE}: {e}"


def c_input_inference_live():
    """A real day's words go IN and the inference produces action cards OUT — live, not mock.
    Uses a crisp, unambiguously-actionable line (the live model is non-deterministic, so a vent-y
    probe can legitimately yield 0 cards); retries twice before calling it NOT_REAL."""
    tok = _owner_token()
    headers = {"Content-Type": "application/json"}
    if tok:
        headers["X-Owner-Token"] = tok
    probe = "Remind me to call the dentist at 3 tomorrow to book a cleaning."
    last = ""
    for _ in range(3):
        try:
            body = json.dumps({"source": "reality_check", "text": probe, "execute_actions": False}).encode()
            code, resp = _http(ENGINE + "/owner/ingest", data=body, headers=headers, timeout=25)
            d = json.loads(resp)
            cards = d.get("cards") or []
            if cards:
                return REAL, f"live ingest -> {len(cards)} action card(s): \"{cards[0].get('title','')[:60]}\""
            last = str(d)[:140]
        except Exception as e:
            last = f"error: {e}"
    return (NOT_REAL if "error" not in last else UNKNOWN), f"live ingest produced no card after 3 tries: {last}"


def c_reminder_fired_live():
    """A time-due reminder was actually DELIVERED to a phone (read back from the glass-box)."""
    for ev in reversed(_glassbox_tail()):
        if ev.get("kind") == "notify" and ev.get("data", {}).get("sent"):
            return REAL, "a reminder NOTIFY was delivered (glass-box sent=true)"
    return NOT_REAL, "no delivered reminder observed in the live glass-box yet"


def c_text_roundtrip_observed():
    """A real inbound text was answered by the brain — the round-trip actually happened."""
    for ev in reversed(_glassbox_tail()):
        if ev.get("kind") == "inbound_agent_reply" and ev.get("data", {}).get("sent"):
            return REAL, "a real inbound text got a real reply (glass-box inbound_agent_reply sent=true)"
    return NOT_REAL, "never observed: an inbound text from the owner answered by the brain"


def c_onboarding_scrape_observed():
    """The 'it scrapes your logged-in accounts' step actually FIRED for someone, once."""
    for ev in reversed(_glassbox_tail()):
        if ev.get("kind") == "onboard_discover":
            return REAL, "an onboarding account-scrape actually fired (glass-box onboard_discover)"
    return NOT_REAL, "never observed: a real first-run account scrape feeding the per-person mesh"


def c_owner_test_5_days():
    return NEEDS_OMAR, "5 consecutive real Omar days through the live system, 0 vent-actions (his call to run)"


CRITERIA = [
    ("engine_live",            "The engine is actually running + healthy",                    c_engine_live),
    ("input_inference_live",   "Messy speech in -> action cards out, LIVE (the core magic)",  c_input_inference_live),
    ("reminder_fired_live",    "A time-due reminder was really delivered to a phone",         c_reminder_fired_live),
    ("front_door_product",     "anticipy.ai leads a stranger to the SOFTWARE (not a pendant)",c_front_door_leads_to_product),
    ("install_no_terminal",    "Install needs no Terminal and no Gatekeeper override",        c_install_no_terminal),
    ("download_notarized",     "The Mac app opens clean on a stranger's machine (notarized)", c_download_notarized),
    ("text_roundtrip",         "A real inbound text was answered by the brain (round-trip)",   c_text_roundtrip_observed),
    ("onboarding_scrape",      "The account-scrape onboarding actually fired once",            c_onboarding_scrape_observed),
    ("owner_test_5_days",      "5 real Omar days, 0 vent-actions (the finish line)",           c_owner_test_5_days),
]


def run():
    rows = []
    for cid, title, fn in CRITERIA:
        try:
            verdict, evidence = fn()
        except Exception as e:
            verdict, evidence = UNKNOWN, f"check crashed: {e}"
        rows.append((cid, title, verdict, evidence))
    return rows


_ICON = {REAL: "✅", NOT_REAL: "❌", NEEDS_OMAR: "🙋", UNKNOWN: "❓"}


def write_ledger(rows):
    real = sum(1 for *_, v, _ in [(r[0], r[1], r[2], r[3]) for r in rows] if v == REAL)
    me_items = [r for r in rows if r[2] != NEEDS_OMAR]
    me_real = sum(1 for r in me_items if r[2] == REAL)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime())
    lines = [
        "# THE FINISH LINE — generated from REALITY, not claims",
        "",
        "> This file is WRITTEN by `factory/bin/reality_check.py`. Do not hand-edit it to say done.",
        "> An item is ✅ REAL only because a live check confirmed it this run. \"Done\" = every",
        "> me-verifiable item ✅, then the 🙋 owner items finished with Omar.",
        "",
        f"_Last reality check: {stamp}_",
        "",
        f"**Real, verified-live: {real}/{len(rows)}**  ·  me-verifiable done: {me_real}/{len(me_items)}",
        "",
        "| | criterion | verdict | evidence (live read-back) |",
        "|---|---|---|---|",
    ]
    for cid, title, verdict, evidence in rows:
        lines.append(f"| {_ICON.get(verdict,'?')} | {title} | **{verdict}** | {evidence} |")
    lines.append("")
    LEDGER.write_text("\n".join(lines))
    return real, len(rows), me_real, len(me_items)


def main():
    quiet = "--quiet" in sys.argv
    rows = run()
    real, total, me_real, me_total = write_ledger(rows)
    print(f"\n=== REALITY CHECK — {real}/{total} verified-live  (me-verifiable: {me_real}/{me_total}) ===")
    for cid, title, verdict, evidence in rows:
        print(f"  {_ICON.get(verdict,'?')} {verdict:10} {title}")
        if not quiet:
            print(f"        └ {evidence}")
    print(f"\nLedger written: {LEDGER.relative_to(REPO)}")
    # exit 0 ONLY when nothing me-verifiable is left undone
    undone = [r for r in rows if r[2] in (NOT_REAL, UNKNOWN)]
    if undone:
        print(f"NOT DONE: {len(undone)} item(s) still not real -> the loop keeps going.")
        return 1
    print("All me-verifiable criteria are REAL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
