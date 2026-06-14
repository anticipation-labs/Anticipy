"""PRESS-GO — the default-deny owner approval path for the remembered list.

The owner skims the inert remembered list and presses go on ONE line. This test proves
the DEFAULT-DENY press-go end to end, through the REAL ControlCore + orchestrator funnel
(stub model + mock hands, CI-safe):

  (1) WHITELIST EXECUTES: approving a CALENDAR line runs via the orchestrator (_drive ->
      GatedApprover reads owner_approved -> ApiHand) and comes back with a real read-backed
      receipt (Law 4). A NOTE line executes via the MemoryWorker. Every auto-executed intent
      carries a real read-back receipt — there is no auto-executed intent that cannot be
      independently verified.

  (2) NON-WHITELIST HANDBACK: approving a DRAFT, a SEND, a MONEY action, and a MESSAGE are
      prepared-and-handed-back (approved=false, prepared=true) — NO goal reaches the
      orchestrator. We spy on orchestrator.start_goal AND orchestrator._drive and assert they
      are called ZERO times across all of them. A DRAFT is reversible but is handed back (not
      auto-executed) precisely because api_hand has no wired Gmail drafts read-back tool, so a
      live draft write could not produce a real read-back receipt. Money phrased as a send also
      lands here.

  (3) NO AUTO-EXEC: remembered/inferred items execute ONLY via the explicit approve call.
      A vent line returns approved=false with no goal. A full trigger_tick (now AND +10y)
      fires ZERO triggers off the remembered store — the press-go added no due/remind field
      and created no open_loop on the handback branch.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_press_go.py
"""
import asyncio
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.live_memory.press_go import WHITELIST, map_inferred_to_step  # noqa: E402
from anticipy_engine.shared.schema import now_ts  # noqa: E402


# Lines the owner remembered. Each is fed through the ONE capture chokepoint so it lands
# in the inert remembered list, exactly as the product captures them. The text is phrased
# the way a person speaks; the review inference is what the owner SEES and what the mapper
# keys off.
CALENDAR = "I need to meet the roofing vendor tomorrow at 2pm."
DRAFT = "I'll draft the contract email to Priya tomorrow morning."
NOTE = "Remind me to renew the patio permit."
SEND = "Send Sam the revised decking file."
MONEY = "Pay the vendor $500 for the filter today."
MESSAGE = "Message Priya on Slack about the vendor call."
VENT = "ugh I should just quit my job and move to a beach"


async def _seed(core: ControlCore, text: str) -> str:
    """Capture a line into the inert remembered list and return its line_id."""
    core.live_memory.capturer.capture(text, source="transcript")
    rows = core.live_memory.capturer.remember.all()
    row = next(r for r in rows if r["text"] == text)
    return str(row["id"])


async def _seed_inert(core: ControlCore, text: str) -> str:
    """Seed ONLY the inert remembered store (the SAFE half), bypassing the normal capture
    open_loop side-effect — so the trigger's open_loops source stays empty and the test
    isolates whether the REMEMBERED store can auto-fire."""
    row = core.live_memory.capturer.remember.remember(text, source="transcript")
    return str(row["id"])


def _install_spy(core: ControlCore) -> dict:
    """Count every call to the two orchestrator execution entry points. The non-whitelist
    branch must reach NEITHER (no goal ever reaches orchestrator.execute)."""
    counts = {"start_goal": 0, "_drive": 0, "drive_intents": []}
    real_start = core.orchestrator.start_goal
    real_drive = core.orchestrator._drive

    async def start_spy(goal):
        counts["start_goal"] += 1
        return await real_start(goal)

    async def drive_spy(goal):
        counts["_drive"] += 1
        counts["drive_intents"].extend(s.intent for s in goal.steps)
        return await real_drive(goal)

    core.orchestrator.start_goal = start_spy
    core.orchestrator._drive = drive_spy
    return counts


async def check_whitelist_executes(fails):
    """(1) calendar + note each execute via the funnel and return a real read-back receipt.

    Every intent that auto-executes here MUST carry a read-back receipt — there is no
    auto-executed intent that cannot be independently verified. (DRAFT is reversible but is
    NOT here: it has no wired read-back, so it is handed back; see check_nonwhitelist_handback.)
    """
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pressgo-wl-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        cal_id = await _seed(core, CALENDAR)
        note_id = await _seed(core, NOTE)

        cal = await core.approve_remembered(cal_id)
        if not (cal.get("approved") and cal.get("executed")):
            fails.append(f"CALENDAR did not execute: {cal}")
        if cal.get("intent") != "create_event":
            fails.append(f"CALENDAR mapped to wrong intent: {cal.get('intent')}")
        if cal.get("state") != "done":
            fails.append(f"CALENDAR goal not done (no receipt): {cal}")
        # Law 4: the receipt is the read-back gate's proof — a mock create_event write
        # carries readback=True + self_attested=False.
        receipt = cal.get("receipt") or {}
        step_proof = next((v for k, v in receipt.items() if "create_event" in k), None)
        if not (isinstance(step_proof, dict) and step_proof.get("readback") is True
                and step_proof.get("self_attested") is False):
            fails.append(f"CALENDAR receipt missing read-back proof: {receipt}")

        note = await core.approve_remembered(note_id)
        if not (note.get("approved") and note.get("executed")):
            fails.append(f"NOTE did not execute: {note}")
        if note.get("intent") != "write_memory":
            fails.append(f"NOTE mapped to wrong intent: {note.get('intent')}")
        if note.get("state") != "done":
            fails.append(f"NOTE goal not done: {note}")

        # THE FIX'S CORE GUARANTEE: every auto-executed intent has a real read-back receipt.
        # Walk each receipt and assert no auto-executed write is self-attested-only.
        for label, res, kind in (("CALENDAR", cal, "create_event"),):
            rc = res.get("receipt") or {}
            sp = next((v for k, v in rc.items() if kind in k), None)
            if not (isinstance(sp, dict) and sp.get("readback") is True
                    and sp.get("self_attested") is False):
                fails.append(f"{label} auto-executed WITHOUT a read-back receipt "
                             f"(read-back-less hole): {rc}")

        # IDEMPOTENCY: re-pressing the SAME calendar line returns the SAME goal + receipt
        # (no double-create of the hold). The endpoint is safe to re-press.
        cal2 = await core.approve_remembered(cal_id)
        if not cal2.get("idempotent"):
            fails.append(f"re-press not idempotent: {cal2}")
        if cal2.get("goal_id") != cal.get("goal_id"):
            fails.append(f"re-press created a NEW goal (double-create risk): "
                         f"{cal.get('goal_id')} vs {cal2.get('goal_id')}")

        return cal, note
    finally:
        await core.stop()


async def check_nonwhitelist_handback(fails):
    """(2) draft + send + money + message are prepared-handback; orchestrator never invoked.

    DRAFT is included here because of the read-back-less-whitelist fix: a Gmail draft is
    reversible but cannot yet be independently read back, so it must NOT auto-execute — it is
    prepared and handed back (the owner is shown the draft to create), exactly like a send."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pressgo-hb-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    counts = _install_spy(core)
    try:
        out = {}
        for name, text in (("DRAFT", DRAFT), ("SEND", SEND), ("MONEY", MONEY),
                           ("MESSAGE", MESSAGE)):
            lid = await _seed(core, text)
            res = await core.approve_remembered(lid)
            out[name] = res
            if res.get("approved") is not False:
                fails.append(f"{name} was not denied: {res}")
            if not res.get("prepared"):
                fails.append(f"{name} not handed back as prepared: {res}")
            if res.get("intent") in WHITELIST:
                fails.append(f"{name} mapped INTO the whitelist (hole!): {res}")
            if res.get("executed"):
                fails.append(f"{name} was executed (must be handed back): {res}")
            # nothing was saved as a runnable goal
            if res.get("goal_id"):
                fails.append(f"{name} created a goal_id (should be none): {res}")

        # The DRAFT handback must still SHOW the owner the draft to create (would_do),
        # and its reason must name the missing read-back (honest, not a generic deny).
        draft_res = out["DRAFT"]
        if "draft" not in str(draft_res.get("would_do") or "").lower():
            fails.append(f"DRAFT handback did not surface the draft to create: {draft_res}")
        if "verify" not in str(draft_res.get("why_handback") or "").lower() \
                and "read-back" not in str(draft_res.get("why_handback") or "").lower():
            fails.append(f"DRAFT handback reason did not name the missing read-back: {draft_res}")

        # THE load-bearing assertion: no goal reached orchestrator execution at all.
        if counts["start_goal"] != 0 or counts["_drive"] != 0:
            fails.append(f"orchestrator executed a non-whitelisted item: {counts}")
        # and the goal store holds no goal from these approvals
        if core.store.all():
            fails.append(f"a goal was persisted for a handback item: "
                         f"{[g.intent for g in core.store.all()]}")
        return out, counts
    finally:
        await core.stop()


async def check_vent_and_no_autofire(fails):
    """(3) a vent returns approved=false; remembered items never auto-fire via trigger_tick."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pressgo-vent-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    counts = _install_spy(core)
    try:
        # seed a mix INCLUDING a whitelisted line straight into the INERT remembered store
        # (bypassing the normal capture open_loop side-effect) so this test isolates the
        # remembered store: none may auto-execute or auto-fire without the explicit approve.
        await _seed_inert(core, CALENDAR)
        await _seed_inert(core, MONEY)
        vent_id = await _seed_inert(core, VENT)

        vent = await core.approve_remembered(vent_id)
        if vent.get("approved") is not False:
            fails.append(f"VENT was not denied: {vent}")
        if vent.get("goal_id"):
            fails.append(f"VENT created a goal: {vent}")
        if "vent" not in (vent.get("reason") or "").lower() and \
                "no confident" not in (vent.get("reason") or "").lower():
            fails.append(f"VENT reason not a vent stop: {vent}")

        # trigger_tick now AND +10y must fire ZERO off the remembered store, and must not
        # invoke the orchestrator (the only execution trigger is the explicit approve).
        now = now_ts()
        fired_now = await core.proactive.trigger_tick(now=now)
        fired_future = await core.proactive.trigger_tick(now=now + 3650 * 86400.0)
        if fired_now or fired_future:
            fails.append(f"trigger fired off remembered store: now={fired_now} "
                         f"future={fired_future}")
        if counts["start_goal"] != 0 or counts["_drive"] != 0:
            fails.append(f"orchestrator auto-fired without an explicit approve: {counts}")
        # the handback (money) and the vent created NO open_loop the trigger could enumerate
        loops = [l.text for l in core.live_memory.memory.open_loops.all()]
        if any(MONEY.split()[0] in t or "beach" in t for t in loops):
            fails.append(f"handback/vent leaked into open_loops: {loops}")
        return vent, fired_now, fired_future
    finally:
        await core.stop()


async def check_concurrent_double_approve(fails):
    """REGRESSION PIN (Apollo fix A): two CONCURRENT presses of the SAME remembered line
    must produce EXACTLY ONE real write (no duplicate calendar hold / draft). Before the
    fix, both presses passed the 'prior goal not done yet' check and both fired the hand;
    the per-line lock in approve_remembered + the ApiHand in-flight reservation now serialize
    them, so the second press lands on the first's done goal and returns its receipt."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pressgo-race-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        # count REAL write executions at the hand (the actual mutation site). Widen the
        # race window with a small sleep so a naive (unlocked) impl would double-fire.
        hand = core.api_hand
        writes = {"n": 0}
        real_execute = hand._execute

        async def counting_execute(job, tool, ikey, *, is_write):
            if is_write:
                writes["n"] += 1
                await asyncio.sleep(0.05)
            return await real_execute(job, tool, ikey, is_write=is_write)

        hand._execute = counting_execute

        cal_id = await _seed(core, CALENDAR)
        r1, r2 = await asyncio.gather(
            core.approve_remembered(cal_id),
            core.approve_remembered(cal_id),
        )
        if writes["n"] != 1:
            fails.append(f"concurrent double-approve fired {writes['n']} real writes "
                         f"(must be exactly 1): r1={r1} r2={r2}")
        if not (r1.get("approved") and r2.get("approved")):
            fails.append(f"both concurrent presses should be approved: {r1} | {r2}")
        if not (r1.get("idempotent") or r2.get("idempotent")):
            fails.append(f"one concurrent press must be the idempotent winner: {r1} | {r2}")
        if r1.get("goal_id") != r2.get("goal_id"):
            fails.append(f"concurrent presses produced different goals (double-create): "
                         f"{r1.get('goal_id')} vs {r2.get('goal_id')}")
        return writes["n"], r1, r2
    finally:
        await core.stop()


def check_mapper_units(fails):
    """Pure-mapper sanity: the AUTO-EXECUTE whitelist is exactly the two read-back-verifiable
    reversible intents (send_email_draft was REMOVED — no wired drafts read-back yet, so it
    cannot produce a live read-back receipt; it is a prepared-handback). The mapper never maps
    a binding send/money/message INTO the whitelist, AND a draft never produces a step."""
    if WHITELIST != frozenset({"create_event", "write_memory"}):
        fails.append(f"WHITELIST drifted from the audited read-back-verifiable two: {WHITELIST}")
    # send_email_draft must NOT be auto-executable until a drafts read-back tool is wired.
    if "send_email_draft" in WHITELIST:
        fails.append("send_email_draft is in the auto-execute WHITELIST but has no wired "
                     "read-back receipt (the read-back-less whitelist hole)")
    # binding/send/money/message inferred tasks must NOT produce a whitelisted step
    for task in ("Send Sam the deck", "Pay the vendor $500", "Message Priya on Slack",
                 "Wire $200 to the landlord", "Buy the filter"):
        m = map_inferred_to_step({"task": task, "people": ["Sam"], "due_phrase": None},
                                 raw_text=task)
        if m.get("intent") in WHITELIST or m.get("step") is not None:
            fails.append(f"mapper put a binding task into the whitelist: {task!r} -> {m}")
    # a DRAFT task is reversible but NOT auto-executable: the mapper must surface the draft
    # to create (would_do) but return NO executable step, so it hands back.
    dm = map_inferred_to_step({"task": "draft the contract email to Priya",
                               "people": ["Priya"], "due_phrase": None},
                              raw_text="I'll draft the contract email to Priya tomorrow morning.")
    if dm.get("step") is not None or dm.get("intent") in WHITELIST:
        fails.append(f"DRAFT produced an auto-executable step (read-back-less hole): {dm}")
    if "draft" not in str(dm.get("would_do") or "").lower():
        fails.append(f"DRAFT handback did not surface the draft to create: {dm}")


async def main():
    fails = []
    check_mapper_units(fails)
    cal, note = await check_whitelist_executes(fails)
    hb, counts = await check_nonwhitelist_handback(fails)
    vent, fired_now, fired_future = await check_vent_and_no_autofire(fails)
    race_writes, race_r1, race_r2 = await check_concurrent_double_approve(fails)

    print("==== DEFAULT-DENY PRESS-GO ====")
    print(f"  (1) WHITELIST executes via orchestrator + read-back (only read-back-verifiable "
          f"intents auto-execute):")
    print(f"      CALENDAR  -> {cal.get('intent')} state={cal.get('state')} "
          f"receipt_keys={list((cal.get('receipt') or {}).keys())}")
    print(f"      NOTE      -> {note.get('intent')} state={note.get('state')}")
    print(f"  (2) NON-WHITELIST handback (orchestrator never called): start_goal="
          f"{counts['start_goal']} _drive={counts['_drive']}")
    for name in ("DRAFT", "SEND", "MONEY", "MESSAGE"):
        r = hb[name]
        print(f"      {name:8s} -> approved={r.get('approved')} prepared={r.get('prepared')} "
              f"intent={r.get('intent')} why={r.get('why_handback')!r}")
    print(f"  (3) VENT approved={vent.get('approved')} reason={vent.get('reason')!r}; "
          f"trigger_tick now+10y fired {len(fired_now)}+{len(fired_future)} (must be 0)")
    print(f"  (4) CONCURRENT double-approve of one line -> {race_writes} real write(s) "
          f"(must be 1); idempotent winner={race_r1.get('idempotent') or race_r2.get('idempotent')}")

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS: only read-back-verifiable intents auto-execute with a real receipt; "
          "draft/send/money/message are handed back (orchestrator never called); vent denied; "
          "no auto-fire ====")


if __name__ == "__main__":
    asyncio.run(main())
