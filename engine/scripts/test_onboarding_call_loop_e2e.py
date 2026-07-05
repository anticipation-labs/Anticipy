"""Onboarding SCRAPE<->CALL LOOP proof — the outbound CALL arm, end to end, in mock.

The inhale/dossier/first-cards halves were already real; this proves the arm that was ORPHANED: after
the four-layer inhale synthesizes a dossier that still carries GAPS, does the loop actually (1) hand
those DOSSIER gaps to clarify, (2) INITIATE an outbound call (CallChannel.send — a mock send in mock
channels, a real Twilio dial when live), (3) run OnboardingCallBrain over the ranked gap-questions,
(4) write the answers BACK so the dossier + first cards are re-aimed?

Un-gameable by construction (same discipline as test_onboarding_firstcards_e2e.py):
  * A THROWAWAY engine on its OWN ephemeral port + fresh ANTICIPY_DATA_DIR, mock hands/channels.
  * The "smart model" is a deterministic stand-in: it returns a fixed dossier whose identity has NO
    role/location (only name+email) but DOES list gaps -> the call arm can only ask what the inhale
    genuinely left open, and can only re-aim identity from the (mock) owner's answers.
  * The payoff asserts the profile drawer, after the call, carries the CALL-EXCLUSIVE answer tokens
    ("Austin, Texas", "founder and product lead") that appear NOWHERE in the inhaled bytes or the
    typed setup — they could ONLY have come from the outbound call's written-back answers.

Negative controls (the honesty law):
  * flag OFF  -> the loop never dials (onboarding_call is None); default behavior is untouched.
  * gaps EMPTY -> a complete inhale needs no call (onboarding_call is None); we never invent a call.
  * supplied real answers -> written back UN-simulated (simulated_answers False).

  test_onboarding_call_loop_e2e.py            # PASS/FAIL
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import socket
import tempfile
import threading
import time

# Env BEFORE importing anticipy_engine.main — free/deterministic/mock, schedulers off, call arm ON.
_TMP0 = tempfile.mkdtemp(prefix="anticipy-callloop-import-")
os.environ["ANTICIPY_DATA_DIR"] = _TMP0
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_HANDS_MODE"] = "mock"
os.environ["ANTICIPY_CHANNELS_MODE"] = "mock"
os.environ["ANTICIPY_NATIVE_BRIDGE_FALLBACK"] = "0"
os.environ["ANTICIPY_TICK_SECONDS"] = "0"
os.environ["ANTICIPY_DERIVE_SECONDS"] = "0"
os.environ["ANTICIPY_INBOUND_POLL_SECONDS"] = "0"
os.environ["ANTICIPY_ONBOARD_CALL"] = "1"   # turn the (gated) call arm ON for this probe
os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
os.environ.pop("OPENROUTER_API_KEY", None)

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from anticipy_engine import main as engmain  # noqa: E402
from anticipy_engine.core import registry  # noqa: E402
from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.core.gateway import PROVIDER_OPENROUTER  # noqa: E402
from anticipy_engine.onboarding import loop as onb_loop  # noqa: E402
from anticipy_engine.onboarding import owner_scrape as onb_scrape  # noqa: E402
from anticipy_engine.onboarding.clarify import (  # noqa: E402
    clarify_dossier_payload,
    clarifying_questions_from_dossier,
)

# ---- fixtures -------------------------------------------------------------------------------------
# The dossier the (faked) smart model returns from the inhale: identity has a name+email but NO
# role/location, and lists two gaps. So clarify must produce a role gap and a location gap, and the
# (mock) owner's answers are the ONLY source of role/location on the board.
DOSSIER = {
    "identity": {"name": "Dana Rivera", "role": "", "location": "", "email": "dana@lumenlabs.example"},
    "work": "", "people": [], "family": [], "tools": [], "act_on_sites": [],
    "gaps": ["your role or title", "where you're based"], "confidence": 0.85,
}
# What the (faked) inhale reads — deliberately carries NONE of the answer tokens below.
INHALED_TEXT = "You are signed in as Dana Rivera <dana@lumenlabs.example>.\nInbox synced.\n"
# Tokens that can ONLY come from the outbound call's mock answers (absent from the inhale + typed setup).
CALL_TOKENS = ("Austin, Texas", "founder and product lead")


def _fake_scrape(cdp_url=None, surfaces=None, max_chars=0, scroll_steps=0, dwell=0, settle=0):
    return {"ok": True, "logged_in": ["gmail_inbox"], "needs_login": [],
            "surfaces": [{"key": "gmail_inbox", "label": "Gmail - inbox", "status": "ok",
                          "needs_login": False, "text": INHALED_TEXT, "chars": len(INHALED_TEXT)}]}


async def _fake_think(prompt, *a, **k):
    # dossier synthesis vs. the warm OnboardingCallBrain turn — same gateway, branch on the prompt.
    if "RAW ACCOUNT TEXT" in prompt:
        return json.dumps(DOSSIER)
    return "That's really helpful — thank you, noted."


# ---- throwaway engine on its OWN ephemeral port ---------------------------------------------------
_SERVER = None
_BASE_URL = ""


def _boot_engine() -> str:
    global _SERVER, _BASE_URL
    if _SERVER is not None:
        return _BASE_URL
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    config = uvicorn.Config(engmain.app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    t0 = time.time()
    while not server.started and time.time() - t0 < 25:
        time.sleep(0.03)
    if not server.started:
        raise RuntimeError("throwaway engine did not start")
    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            if httpx.get(base + "/health", timeout=2).status_code == 200:
                break
        except Exception:
            time.sleep(0.03)
    _SERVER, _BASE_URL = server, base

    @atexit.register
    def _stop() -> None:
        server.should_exit = True

    return base


def _install_core(*, dossier=None) -> ControlCore:
    tmp = tempfile.mkdtemp(prefix="anticipy-callloop-run-")
    os.environ["ANTICIPY_DATA_DIR"] = tmp
    core = ControlCore(data_dir=tmp)
    registry.register_default(core)
    onb_loop.scrape_owner = _fake_scrape
    onb_scrape.scrape_owner = _fake_scrape

    async def _think(prompt, *a, **k):
        if "RAW ACCOUNT TEXT" in prompt:
            return json.dumps(dossier if dossier is not None else DOSSIER)
        return "That's really helpful — thank you, noted."

    core.gateway.provider = PROVIDER_OPENROUTER   # flips dossier.py into the synthesis branch
    core.gateway.think = _think
    return core


def _run(coro):
    """Drive one coroutine on a fresh loop (the uvicorn engine owns its own loop in another thread)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _texts(drawer: dict) -> list:
    return [i.get("text", "") for i in (drawer.get("recent") or [])]


def _has(texts, tok) -> bool:
    return any(tok.lower() in (x or "").lower() for x in texts)


# ---- direct unit: clarify reads dossier gaps; run_onboarding_call closes the loop -----------------
def test_clarify_reads_dossier_gaps():
    fails = []
    qs = clarifying_questions_from_dossier(DOSSIER, max_questions=5)
    fields = [q.field for q in qs]
    if fields != ["role", "location"]:
        fails.append(f"clarify must read the dossier's role/location gaps, got {fields}")
    if not all(q.reason == "gap" for q in qs):
        fails.append(f"dossier gaps are gap-reason questions: {[q.reason for q in qs]}")
    # the question text is derived from the dossier's OWN gap strings (not a public-web profile)
    if not any("role or title" in q.question_text for q in qs):
        fails.append(f"role question must follow the dossier gap wording: {[q.question_text for q in qs]}")
    pay = clarify_dossier_payload(DOSSIER)
    if pay["summary"]["source"] != "owner_inhale_dossier":
        fails.append(f"payload must declare its source is the inhale dossier: {pay['summary']}")
    if fails:
        raise AssertionError("clarify_reads_dossier_gaps:\n  - " + "\n  - ".join(fails))


def test_run_onboarding_call_direct():
    """Directly drive the orchestrator (mock): initiate -> talk -> write back -> re-aim."""
    fails = []
    core = _install_core()
    res = _run(core.run_onboarding_call(dict(DOSSIER)))
    if not res.get("initiated"):
        fails.append(f"call must be INITIATED: {res}")
    call = res.get("call") or {}
    if not (call.get("sent") and call.get("mock") is True):
        fails.append(f"mock channels -> a recorded MOCK call send: {call}")
    if len(core.call_channel.sent) != 1:
        fails.append(f"exactly one call placed on the channel audit trail: {core.call_channel.sent}")
    if [q["field"] for q in res.get("questions", [])] != ["role", "location"]:
        fails.append(f"the call asks the dossier's ranked gap-questions: {res.get('questions')}")
    if res.get("simulated_answers") is not True:
        fails.append("no real answers supplied -> answers are simulated (tagged)")
    # answers written back -> profile drawer reflects them (first cards + re-aimed identity)
    ptexts = [i.text for i in core.memory.profile.all()]
    if not any(t.startswith("From setup call") for t in ptexts):
        fails.append(f"each answer must be written back as a profile fact: {ptexts}")
    if not (_has(ptexts, "Austin, Texas") and _has(ptexts, "founder and product lead")):
        fails.append(f"re-aimed identity must carry the call answers: {ptexts}")
    if fails:
        raise AssertionError("run_onboarding_call_direct:\n  - " + "\n  - ".join(fails))


def test_run_onboarding_call_supplied_answers():
    """Supplied REAL answers are used verbatim and written back UN-simulated."""
    fails = []
    core = _install_core()
    res = _run(
        core.run_onboarding_call(dict(DOSSIER), answers={"role": "VP Engineering", "location": "Toronto"}))
    if res.get("simulated_answers") is not False:
        fails.append(f"supplied answers must not be flagged simulated: {res.get('simulated_answers')}")
    ptexts = [i.text for i in core.memory.profile.all()]
    if not (_has(ptexts, "VP Engineering") and _has(ptexts, "Toronto")):
        fails.append(f"supplied answers must be written back: {ptexts}")
    if fails:
        raise AssertionError("run_onboarding_call_supplied_answers:\n  - " + "\n  - ".join(fails))


def test_no_gaps_no_call():
    """A complete inhale (no gaps, full identity) needs no call — nothing is invented."""
    fails = []
    core = _install_core()
    complete = {"identity": {"name": "Dana", "role": "CEO", "location": "Austin"}, "gaps": [], "confidence": 0.9}
    res = _run(core.run_onboarding_call(complete))
    if res.get("initiated") is not False:
        fails.append(f"no gaps -> no call initiated: {res}")
    if core.call_channel.sent:
        fails.append(f"no gaps -> nothing dialed: {core.call_channel.sent}")
    if fails:
        raise AssertionError("no_gaps_no_call:\n  - " + "\n  - ".join(fails))


# ---- full loop over real HTTP: /onboard/loop fires the call step and closes the loop --------------
def test_loop_fires_call_over_http():
    fails = []
    base = _boot_engine()
    core = _install_core()
    http = httpx.Client(base_url=base, timeout=30)

    # consent for a readable service, then the inhale loop (which now dials the gap-filling call).
    http.post("/onboard/permissions", json={"service": "gmail", "allowed": True})
    lp = http.post("/onboard/loop", json={"max_layers": 2}).json()

    if lp.get("done") is not True:
        fails.append(f"inhale should complete (readable, no needs_login): done={lp.get('done')}")
    oc = lp.get("onboarding_call")
    if not oc:
        fails.append(f"the loop must attach an onboarding_call result: {lp.get('onboarding_call')}")
    else:
        if oc.get("initiated") is not True:
            fails.append(f"loop step must INITIATE the outbound call: {oc}")
        if oc.get("mode") != "mock":
            fails.append(f"mock channels -> mock call mode: {oc.get('mode')}")
        if not ((oc.get("call") or {}).get("mock") is True):
            fails.append(f"a recorded MOCK call: {oc.get('call')}")
        if [q.get("field") for q in oc.get("questions", [])] != ["role", "location"]:
            fails.append(f"the call carries clarify's dossier gap-questions: {oc.get('questions')}")
        if (oc.get("written") or {}).get("profile", 0) < 2:
            fails.append(f"answers must be written back: {oc.get('written')}")

    # first cards: the board (profile drawer) now reflects the call answers (re-aimed identity).
    drawers = http.get("/memory/drawers").json().get("drawers", {})
    ptext = _texts(drawers.get("profile", {}))
    if not any(t.startswith("From setup call") for t in ptext):
        fails.append(f"the board must show the call's written-back facts: {ptext}")
    for tok in CALL_TOKENS:
        if not _has(ptext, tok):
            fails.append(f"call-exclusive answer token missing from the board: {tok!r}")

    # negative control: flag OFF -> the loop does NOT dial (default behavior untouched).
    os.environ["ANTICIPY_ONBOARD_CALL"] = "0"
    try:
        core2 = _install_core()
        http.post("/onboard/permissions", json={"service": "gmail", "allowed": True})
        lp_off = http.post("/onboard/loop", json={"max_layers": 2}).json()
        if lp_off.get("onboarding_call") is not None:
            fails.append(f"flag OFF must not fire the call: {lp_off.get('onboarding_call')}")
        if not core2.call_channel.sent == []:
            fails.append(f"flag OFF -> nothing dialed: {core2.call_channel.sent}")
    finally:
        os.environ["ANTICIPY_ONBOARD_CALL"] = "1"

    http.close()
    if fails:
        raise AssertionError("loop_fires_call_over_http:\n  - " + "\n  - ".join(fails))


def main() -> int:
    test_clarify_reads_dossier_gaps()
    test_run_onboarding_call_direct()
    test_run_onboarding_call_supplied_answers()
    test_no_gaps_no_call()
    test_loop_fires_call_over_http()
    print("PASS onboarding_call_loop_e2e: the inhale dossier's gaps -> clarify's ranked questions -> an "
          "INITIATED (mock) outbound call via CallChannel.send -> OnboardingCallBrain over those questions "
          "-> answers written back + identity re-aimed (Austin, Texas / founder and product lead) -> first "
          "cards on the board; gated OFF by default, no call when gaps are empty, supplied answers un-mocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
