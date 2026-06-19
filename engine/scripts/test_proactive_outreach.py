"""PROACTIVE OUTREACH — live, self-firing proof (deterministic, stub model, MOCK channels).

The product claim Omar challenged ("what happened to the proactive side?"): Anticipy is not a
reactive agent — it ANTICIPATES. A due reminder fires ON ITS OWN CLOCK, with NO user input in
the moment and NO manual tick, and the signature "call me at 2:45" reminder RINGS the voice
line instead of texting. And it can never go dark in silence.

This proves the whole thing on the REAL assembled engine (the actual FastAPI app + its real
lifespan, the same object uvicorn serves), end to end:

  (1) CAN'T-GO-DARK GUARD: _arm_proactive_health reports armed/dark + live/mock honestly.
        - ANTICIPY_TICK_SECONDS=0  -> armed=False, reason names the disabled self-firing.
        - a real interval         -> armed=True.
  (2) SELF-FIRING (no manual tick): booting the real app (lifespan -> asyncio scheduler at 1s)
      and seeding two DUE reminders, the background clock fires BOTH within a couple seconds
      with zero calls to /trigger/tick. /status honestly shows armed=True, outreach=mock.
  (3) VOICE ESCALATION: the loop the user asked to be CALLED about (channel_pref='call')
      rings the CALL channel; the plain reminder texts. Same anti-spam either way.
  (4) FIRE-ONCE: after firing, counts do not grow, and each loop carries a durable fired_at.

MOCK channels throughout: nothing texts or calls a real phone — CallChannel/TextChannel in mock
just record to .sent. Safe to run anywhere.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_proactive_outreach.py
It MUST print PASS and exit 0.
"""
import os
import tempfile
import time
from pathlib import Path

# Isolated data dir + safe modes BEFORE importing the app (the module builds the core singleton
# at import, reading these). MOCK channels => no real send ever leaves the box.
_TMP = Path(tempfile.mkdtemp(prefix="anticipy-proactive-proof-"))
os.environ["ANTICIPY_DATA_DIR"] = str(_TMP)
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_HANDS_MODE"] = "mock"
os.environ["ANTICIPY_CHANNELS_MODE"] = "mock"      # never a real text/call
os.environ["ANTICIPY_INBOUND_POLL_SECONDS"] = "0"  # no Twilio inbound poller
os.environ["ANTICIPY_NATIVE_BRIDGE_FALLBACK"] = "0"
os.environ["ANTICIPY_TICK_SECONDS"] = "1"          # anticipate every 1s for a fast proof
os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)   # local: /status is open

from fastapi.testclient import TestClient  # noqa: E402

import anticipy_engine.main as m  # noqa: E402

CALL_LINE = "remind me to call me back about the dentist at 2:45"   # -> channel_pref via fire path
TEXT_LINE = "take my meds at 9pm"


def _seed(core, loop_id: str, text: str, remind_ts: float, channel_pref: str | None) -> None:
    fields = {"task": text, "remind_ts": remind_ts}
    if channel_pref:
        fields["channel_pref"] = channel_pref
    core.memory.open_loops.write_text(text, id=loop_id, fields=fields,
                                      provenance="proof_seed", importance=0.6, status="open")


def main() -> None:
    fails: list[str] = []
    core = m.core

    # ---- (1) can't-go-dark guard, both states (pure function, no network) ----
    m._arm_proactive_health(0.0, False)
    if m._proactive_health.get("armed") is not False:
        fails.append(f"TICK=0 must report armed=False, got {m._proactive_health}")
    if "manual" not in m._proactive_health.get("reason", "").lower():
        fails.append(f"dark health reason should name the manual-only fallback: {m._proactive_health}")
    m._arm_proactive_health(30.0, True)
    if m._proactive_health.get("armed") is not True:
        fails.append(f"armed interval must report armed=True, got {m._proactive_health}")

    # ---- (1b) capture-side: "call me" sets channel_pref='call'; "call <someone>" does NOT ----
    from anticipy_engine.live_memory.capture import _WANTS_CALL  # noqa: E402
    for yes in ("call me back at 2:45", "give me a call at 3", "ring me at noon", "phone me later"):
        if not _WANTS_CALL.search(yes):
            fails.append(f"capture should flag a call-me ask: {yes!r}")
    for no in ("call the dentist at 3pm", "remind me to call mom", "take my meds at 9pm"):
        if _WANTS_CALL.search(no):
            fails.append(f"capture must NOT escalate a call-someone-else line to a phone call: {no!r}")

    # ---- seed two DUE reminders (remind_ts in the past) BEFORE the scheduler exists ----
    now = time.time()
    _seed(core, "proof-call-loop", CALL_LINE, now - 120, channel_pref="call")
    _seed(core, "proof-text-loop", TEXT_LINE, now - 120, channel_pref=None)
    call0, text0 = len(core.call_channel.sent), len(core.text_channel.sent)

    # ---- (2)+(3) boot the REAL app; its lifespan starts the asyncio scheduler. We NEVER call
    #            /trigger/tick — the background clock must fire on its own. ----
    with TestClient(m.app) as client:
        st = client.get("/status").json().get("proactive", {})
        if st.get("armed") is not True:
            fails.append(f"/status proactive.armed should be True under TICK=1: {st}")
        if st.get("outreach") != "mock":
            fails.append(f"/status proactive.outreach should be 'mock' here: {st}")

        deadline = time.time() + 8.0
        while time.time() < deadline:
            if (len(core.call_channel.sent) > call0) and (len(core.text_channel.sent) > text0):
                break
            time.sleep(0.25)

        new_calls = core.call_channel.sent[call0:]
        new_texts = core.text_channel.sent[text0:]
        if not new_calls:
            fails.append("the 'call me' reminder did NOT ring the call channel on the self-clock "
                         f"(call sends unchanged at {len(core.call_channel.sent)})")
        else:
            rec = new_calls[-1]
            if rec.get("channel") != "call":
                fails.append(f"call-pref reminder used wrong channel: {rec}")
        if not new_texts:
            fails.append("the plain reminder did NOT text on the self-clock "
                         f"(text sends unchanged at {len(core.text_channel.sent)})")
        else:
            rec = new_texts[-1]
            if rec.get("channel") != "text":
                fails.append(f"plain reminder used wrong channel: {rec}")

        # ---- (4) fire-once: give the clock more ticks; counts must not grow ----
        steady_calls, steady_texts = len(core.call_channel.sent), len(core.text_channel.sent)
        time.sleep(2.5)
        if len(core.call_channel.sent) != steady_calls:
            fails.append(f"call reminder fired more than once: {steady_calls} -> {len(core.call_channel.sent)}")
        if len(core.text_channel.sent) != steady_texts:
            fails.append(f"text reminder fired more than once: {steady_texts} -> {len(core.text_channel.sent)}")

    # durable fire-once stamp on each loop (survives a restart)
    for lid in ("proof-call-loop", "proof-text-loop"):
        loop = core.memory.open_loops.get(lid)
        if loop is None or loop.fields.get("fired_at") is None:
            fails.append(f"loop {lid} carries no durable fired_at stamp after firing")

    print("==== PROACTIVE OUTREACH (live self-firing, stub model, MOCK channels) ====")
    print("  (1) can't-go-dark health reports armed/dark + live/mock honestly")
    print("  (2) the background clock fired two DUE reminders with NO manual tick")
    print("  (3) the 'call me' reminder RANG the call channel; the plain one texted")
    print("  (4) fire-once held (no duplicate sends) + durable fired_at stamp")
    if fails:
        print("==== FAIL ====")
        for x in fails:
            print("   -", x)
        raise SystemExit(1)
    print("PASS prove_proactive_outreach")


if __name__ == "__main__":
    main()
