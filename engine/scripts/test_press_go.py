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

import datetime as dt  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.live_memory.press_go import (  # noqa: E402
    WHITELIST, _ground_datetime, map_inferred_to_step)
from anticipy_engine.owner_onboarding import OwnerOnboardingIn  # noqa: E402
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
# Apollo wave 2 breach line: a laugh-hedged JOKE in a "remind me to ..." shape. Before the
# fix, review_infer's narrower guard let infer_line().task be non-empty, so the mapper's
# _NOTE_RAW path built a write_memory step and press-go AUTO-EXECUTED a joke as a task (the
# cardinal sin). is_vent() is now the single source of truth -> EMPTY task -> handback.
LAUGH_VENT = "remind me to never agree to a 7am meeting again, lol"


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
        laugh_id = await _seed_inert(core, LAUGH_VENT)

        vent = await core.approve_remembered(vent_id)
        if vent.get("approved") is not False:
            fails.append(f"VENT was not denied: {vent}")
        if vent.get("goal_id"):
            fails.append(f"VENT created a goal: {vent}")
        if "vent" not in (vent.get("reason") or "").lower() and \
                "no confident" not in (vent.get("reason") or "").lower():
            fails.append(f"VENT reason not a vent stop: {vent}")

        # CARDINAL-SIN REGRESSION PIN (Apollo wave 2): the laugh-hedged "remind me to ..."
        # joke must hand back — denied, NO goal, NO execution — even though it carries the
        # _NOTE_RAW "remind me to" shape the mapper would otherwise turn into a write_memory.
        laugh = await core.approve_remembered(laugh_id)
        if laugh.get("approved") is not False:
            fails.append(f"LAUGH-HEDGED JOKE was not denied (cardinal sin): {laugh}")
        if laugh.get("goal_id") or laugh.get("executed"):
            fails.append(f"LAUGH-HEDGED JOKE executed/created a goal (cardinal sin): {laugh}")

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


def check_malformed_clock_no_crash(fails):
    """REGRESSION PIN (Apollo wave-2 A): an out-of-range minute in a remembered line
    ('meet at 2:99') must NOT crash _ground_datetime / map_inferred_to_step — it hands back
    gracefully (None / no step), exactly like a missing time. Mirrors duetime._hm bounds."""
    # _ground_datetime must return None (not raise) on a bad minute AND a bad hour.
    for raw in ("meet the vendor tomorrow at 2:99", "meet tomorrow at 99:00",
                "lunch tomorrow at 13:75"):
        try:
            out = _ground_datetime(raw)
        except Exception as e:  # noqa: BLE001 — any crash is the bug
            fails.append(f"_ground_datetime CRASHED on {raw!r}: {type(e).__name__}: {e}")
            continue
        if out is not None:
            fails.append(f"_ground_datetime accepted a malformed clock {raw!r} -> {out}")
    # a VALID minute still grounds (we did not over-reject).
    ok = _ground_datetime("meet the vendor tomorrow at 2:30pm")
    if ok is None:
        fails.append("_ground_datetime rejected a VALID 2:30pm clock (over-correction)")
    # the mapper must hand back (no step), never raise.
    try:
        m = map_inferred_to_step({"task": "meeting with the vendor", "people": [],
                                  "due_phrase": None},
                                 raw_text="I need to meet the vendor tomorrow at 2:99.")
    except Exception as e:  # noqa: BLE001
        fails.append(f"map_inferred_to_step CRASHED on 2:99: {type(e).__name__}: {e}")
        return
    if m.get("step") is not None or m.get("intent") in WHITELIST:
        fails.append(f"map_inferred_to_step grounded a malformed 2:99 clock: {m}")


async def check_malformed_clock_endpoints_no_crash(fails):
    """Through the REAL endpoints: approving AND dry-running a '2:99' line returns a graceful
    handback (approved/would_execute False), never a 500/crash."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pressgo-badclock-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        bad = "I need to meet the roofing vendor tomorrow at 2:99."
        lid = await _seed(core, bad)
        try:
            a = await core.approve_remembered(lid)
        except Exception as e:  # noqa: BLE001
            fails.append(f"approve_remembered CRASHED on 2:99: {type(e).__name__}: {e}")
            return
        if a.get("approved") is not False or not a.get("prepared"):
            fails.append(f"2:99 approve was not a graceful handback: {a}")
        try:
            d = core.dryrun_remembered(lid)
        except Exception as e:  # noqa: BLE001
            fails.append(f"dryrun_remembered CRASHED on 2:99: {type(e).__name__}: {e}")
            return
        if d.get("would_execute") is not False:
            fails.append(f"2:99 dryrun was not a graceful handback: {d}")
        return a, d
    finally:
        await core.stop()


async def check_owner_timezone_offset(fails):
    """REGRESSION PIN (Apollo wave-2 B): a press-go calendar hold is grounded in the OWNER's
    onboarded timezone (profile drawer), so start/end ISO carry the owner's UTC offset — not
    the server's. We onboard an explicit IANA zone whose offset differs from the server's and
    assert both approve AND dryrun produce that owner offset on the grounded event."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pressgo-tz-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        # pick a zone whose current offset is NOT the server's, so a server-tz regression
        # would visibly differ. America/New_York and Asia/Kolkata can't both equal local.
        server_off = dt.datetime.now().astimezone().utcoffset()
        zones = ["America/New_York", "Asia/Kolkata", "Pacific/Kiritimati"]
        zone = next(z for z in zones
                    if dt.datetime.now(ZoneInfo(z)).utcoffset() != server_off)
        owner_off = dt.datetime.now(ZoneInfo(zone)).utcoffset()

        await core.owner_onboard(OwnerOnboardingIn(owner_name="Omar", timezone=zone))
        tz, name = core._owner_timezone()
        if name != zone:
            fails.append(f"owner timezone not read from profile drawer: {name} != {zone}")

        cal_id = await _seed(core, CALENDAR)
        cal = await core.approve_remembered(cal_id)
        goal = core.store.load(cal.get("goal_id"))
        if goal is None or not goal.steps:
            fails.append(f"calendar approve produced no goal/step: {cal}")
            return
        start_iso = goal.steps[0].args.get("start_datetime")
        start_off = dt.datetime.fromisoformat(start_iso).utcoffset()
        if start_off != owner_off:
            fails.append(f"calendar start carries the WRONG offset: got {start_off} "
                         f"(server={server_off}) expected owner {owner_off} ({zone}); "
                         f"iso={start_iso}")
        # dryrun must show the SAME owner offset (the preview must match the real action).
        d = core.dryrun_remembered(cal_id)
        d_iso = (d.get("args") or {}).get("start_datetime")
        if d_iso and dt.datetime.fromisoformat(d_iso).utcoffset() != owner_off:
            fails.append(f"dryrun preview offset != owner offset: {d_iso}")
        return zone, start_iso, d_iso
    finally:
        await core.stop()


async def check_content_idempotency(fails):
    """REGRESSION PIN (Apollo wave-2 C): the SAME task captured TWICE arrives as two DIFFERENT
    remembered lines (different line_ids). Idempotency must key on action CONTENT (intent +
    normalized summary + grounded start), so approving BOTH lines yields EXACTLY ONE real
    calendar hold — the second press short-circuits to the first's receipt."""
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-pressgo-content-idem-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    try:
        # count REAL write executions at the hand (the actual mutation site).
        hand = core.api_hand
        writes = {"n": 0}
        real_execute = hand._execute

        async def counting_execute(job, tool, ikey, *, is_write):
            if is_write:
                writes["n"] += 1
            return await real_execute(job, tool, ikey, is_write=is_write)

        hand._execute = counting_execute

        # SAME utterance captured twice -> two distinct inert lines.
        line_a = await _seed(core, CALENDAR)
        # capture the identical text again; _seed returns the FIRST match, so grab the 2nd id.
        core.live_memory.capturer.capture(CALENDAR, source="transcript")
        ids = [str(r["id"]) for r in core.live_memory.capturer.remember.all()
               if r["text"] == CALENDAR]
        line_b = next(i for i in ids if i != line_a)
        if line_a == line_b:
            fails.append("the two captured lines share a line_id (test setup wrong)")

        ra = await core.approve_remembered(line_a)
        rb = await core.approve_remembered(line_b)
        if writes["n"] != 1:
            fails.append(f"same-content double-approve fired {writes['n']} real calendar "
                         f"holds (must be exactly 1): ra={ra} rb={rb}")
        if not (ra.get("approved") and rb.get("approved")):
            fails.append(f"both same-content approves should be approved: {ra} | {rb}")
        if not rb.get("idempotent"):
            fails.append(f"second same-content approve must be idempotent: {rb}")
        if ra.get("goal_id") != rb.get("goal_id"):
            fails.append(f"same-content approves produced DIFFERENT goals (double-create): "
                         f"{ra.get('goal_id')} vs {rb.get('goal_id')}")
        if not rb.get("receipt"):
            fails.append(f"idempotent re-press did not return the original receipt: {rb}")
        # and the goal store holds exactly ONE remembered-approval goal for this action.
        rmb_goals = [g for g in core.store.all() if g.id.startswith("rmb-")]
        if len(rmb_goals) != 1:
            fails.append(f"expected exactly ONE goal for the duplicated action, found "
                         f"{[g.id for g in rmb_goals]}")
        return writes["n"], ra, rb
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


def check_pressgo_defers_to_harmline(fails):
    """REGRESSION PIN (Apollo wave 4): press-go's denial belt must DEFER TO the harm-line —
    it can never be NARROWER than harm.py's money/send vocabulary. The pre-fix bug let a
    money-idiom, a soft-send line, and a send GERUND slip past the narrower _BINDING_SEND
    belt into the WHITELIST (write_memory / create_event = EXECUTES). The fix runs the
    deterministic harm-line (+ is_vent) on the RAW line BEFORE returning any whitelisted Step
    and refuses the mapping when the harm category is detrimental/binding or the line is a
    vent. We drive the FULL review-inference path (infer_line) exactly as the product does,
    and assert: every harmful line HANDS BACK (no whitelisted intent, no step), and every
    genuine-safe line still EXECUTES."""
    from anticipy_engine.live_memory.review_infer import infer_line

    def _maps_to_execute(raw, people=None):
        inferred = infer_line(raw, people_hint=people)
        m = map_inferred_to_step(inferred, raw_text=raw,
                                 now=dt.datetime(2026, 6, 15, 9, 0).astimezone())
        return (m.get("intent") in WHITELIST and m.get("step") is not None), m

    # MUST HAND BACK — the 3 reproduced lines + the money-idiom / soft-send / gerund set.
    # Each of these would, pre-fix, have mapped into write_memory or create_event.
    handback = [
        "Don't forget to square up the dinner tab",                      # money idiom -> harm money
        "Schedule sending the deck to the investor tomorrow at 10am",    # send gerund -> harm binding_send
        "Remind me to email the resignation to HR",                      # soft-send (email) -> belt + note deny
        "Remind me to cover the rent",                                   # money idiom (cover the rent)
        "Note to self: settle the invoice with the contractor",          # money idiom (settle the invoice)
        "Don't forget to chip in for the gift",                          # money idiom (chip in)
        "Schedule wiring the deposit tomorrow at 2pm",                   # gerund (wiring) + money
        "Schedule emailing the report tomorrow at 9am",                  # gerund (emailing) soft-send
        "Remind me to send the resignation to HR",                       # send verb in a note frame
        "Remind me to text Priya about the call",                        # soft-send (text) in a note frame
        "Schedule paying the vendor tomorrow at 11am",                   # gerund (paying) + money
    ]
    for raw in handback:
        executes, m = _maps_to_execute(raw, people=["HR"])
        if executes:
            fails.append(f"HARM-LINE DEFERRAL HOLE: {raw!r} mapped INTO the whitelist "
                         f"(executes) instead of handing back: {m}")

    # MUST STILL EXECUTE — genuine-safe reversibles the harm-line does NOT stop as
    # money/send/destroy/etc. The harm-line may read the bare calendar line as 'unclassified'
    # (a fail-safe ask), which is NOT in the refuse set, so the press-go shape mapper still
    # grounds it — the gate keys off the harm CATEGORY, never the broad detrimental flag.
    safe_exec = [
        ("I need to meet the roofing vendor tomorrow at 2pm.", None, "create_event"),
        ("Remind me to renew the patio permit.", None, "write_memory"),
        ("Schedule a sync with Sarah tomorrow at 10am", None, "create_event"),
        ("Remind me to call the dentist", None, "write_memory"),
    ]
    for raw, people, want_intent in safe_exec:
        executes, m = _maps_to_execute(raw, people=people)
        if not executes:
            fails.append(f"HARM-LINE DEFERRAL OVER-BLOCK: genuine-safe {raw!r} no longer "
                         f"executes (should map to {want_intent}): {m}")
        elif m.get("intent") != want_intent:
            fails.append(f"safe line {raw!r} mapped to {m.get('intent')} not {want_intent}")


async def main():
    fails = []
    check_mapper_units(fails)
    check_pressgo_defers_to_harmline(fails)
    check_malformed_clock_no_crash(fails)
    await check_malformed_clock_endpoints_no_crash(fails)
    cal, note = await check_whitelist_executes(fails)
    hb, counts = await check_nonwhitelist_handback(fails)
    vent, fired_now, fired_future = await check_vent_and_no_autofire(fails)
    race_writes, race_r1, race_r2 = await check_concurrent_double_approve(fails)
    tz_zone, tz_start, tz_dry = await check_owner_timezone_offset(fails)
    idem_writes, idem_a, idem_b = await check_content_idempotency(fails)

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
    print(f"  (5) MALFORMED CLOCK '2:99' -> graceful handback (no crash) on approve + dryrun")
    print(f"  (6) OWNER TIMEZONE {tz_zone}: calendar grounded with owner offset "
          f"approve={tz_start} dryrun={tz_dry}")
    print(f"  (7) CONTENT IDEMPOTENCY: same task captured twice -> {idem_writes} real "
          f"hold(s) (must be 1); 2nd press idempotent={idem_b.get('idempotent')} "
          f"goal={idem_b.get('goal_id')}")

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS: only read-back-verifiable intents auto-execute with a real receipt; "
          "draft/send/money/message are handed back (orchestrator never called); vent denied; "
          "no auto-fire; malformed clock handed back; owner-tz offset on calendar; "
          "same-content captured twice -> ONE hold ====")


if __name__ == "__main__":
    asyncio.run(main())
