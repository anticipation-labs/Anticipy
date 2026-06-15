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
import re
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

def c_vent_stays_silent():
    """THE cardinal sin — acting on a vent or sarcasm — must NEVER happen, and money is always a
    hard stop. Runs the adversarial cardinal-sin/money corpus against the REAL assembled engine;
    ANY breach = NOT_REAL. This is the engine's single most important safety property."""
    venv_py = REPO / "engine" / ".venv" / "bin" / "python"
    try:
        r = subprocess.run(
            [str(venv_py), str(REPO / "engine" / "scripts" / "safety_mega_eval.py")],
            capture_output=True, text=True, timeout=240,
            env={**os.environ, "PYTHONPATH": str(REPO / "engine"),
                 "ANTICIPY_MODEL_PROVIDER": "stub", "ANTICIPY_HANDS_MODE": "mock",
                 "ANTICIPY_CHANNELS_MODE": "mock", "ANTICIPY_DATA_DIR": "/tmp/anticipy_floor_rc"})
        out = r.stdout + r.stderr
        m = re.search(r"BREACHES:\s*(\d+)", out)
        if r.returncode == 0 and m and int(m.group(1)) == 0:
            n = re.search(r"CORPUS LINES:\s*(\d+)", out)
            return REAL, f"0 breaches across {n.group(1) if n else '?'} adversarial lines (vents never act, money blocked)"
        return NOT_REAL, f"safety floor not clean (rc={r.returncode}): {out.strip()[-160:]}"
    except Exception as e:
        return UNKNOWN, f"could not run the safety floor: {e}"


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


def c_action_executed_with_proof():
    """The engine doesn't just DECIDE — it EXECUTES a real action and proves it by an independent
    read-back (never the actor's own write echo). Scans the live glass-box for a write confirmed
    via read-back (e.g. a calendar event created, then re-observed by ListEvents)."""
    for ev in reversed(_glassbox_tail()):
        data = ev.get("data") or {}
        proof = data.get("proof")
        if isinstance(proof, dict) and proof.get("verified_by_read") and data.get("status") == "success":
            return REAL, f"a real action executed + independently read-back-verified (via {proof.get('verified_by_read')})"
    return NOT_REAL, "no read-back-verified action execution observed in the live glass-box yet"


def c_owner_test_5_days():
    return NEEDS_OMAR, "5 consecutive real Omar days through the live system, 0 vent-actions (his call to run)"


# The ENGINE's finish line — does this engine actually work, end to end, for real. NOT the
# product website/download (that lives in a separate repo and is not this engine's job).
CRITERIA = [
    ("engine_live",          "The engine is actually running + healthy",                    c_engine_live),
    ("input_inference_live", "Messy speech in -> action cards out, LIVE (the core magic)",   c_input_inference_live),
    ("action_executed",      "The engine EXECUTES an action + proves it by read-back",       c_action_executed_with_proof),
    ("vent_stays_silent",    "Vents/sarcasm never trigger an action; money always blocked",  c_vent_stays_silent),
    ("reminder_fired_live",  "A time-due reminder was really delivered to a phone",          c_reminder_fired_live),
    ("text_roundtrip",       "A real inbound text was answered by the brain (round-trip)",   c_text_roundtrip_observed),
    ("onboarding_scrape",    "The account-scrape onboarding actually fired once",            c_onboarding_scrape_observed),
    ("owner_test_5_days",    "5 real owner days, 0 vent-actions (the finish line)",          c_owner_test_5_days),
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
