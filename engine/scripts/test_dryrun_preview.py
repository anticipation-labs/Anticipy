"""LIVE DRY-RUN PREVIEW — show EXACTLY what press-go WOULD do, WITHOUT doing it.

Trust-before-connect: before the owner connects any account, he can preview his whole day's
planned real actions. This test proves the dry-run through the REAL ControlCore (stub model
+ mock hands, CI-safe):

  (0) EXECUTES NOTHING — the load-bearing claim. We spy on orchestrator.start_goal AND
      orchestrator._drive and assert they are called ZERO times across EVERY dry-run
      (whitelisted, handback, AND vent). The goal store stays EMPTY, no memory note is
      written, and the remembered enrichment never becomes an open_loop. A dry-run plans
      and shows; it never acts.

  (1) WHITELIST PREVIEW: dry-running a CALENDAR / DRAFT / NOTE line returns the CONCRETE
      planned action — would_execute=true, the right intent, the tool it WOULD call
      (GoogleCalendar.CreateEvent / Gmail.WriteDraftEmail / local memory), the EXACT args
      press-go would send, and the connect-first note. The previewed args MATCH the args
      approve_remembered would actually drive (same mapper).

  (2) NON-WHITELIST PREVIEW: dry-running a SEND / MONEY / MESSAGE returns
      would_execute=false with a handback + why, and intent never lands in the WHITELIST.

  (3) VENT PREVIEW: a vent returns would_execute=false with a vent-stop reason and no intent.

  (4) DAY MODE: /dryrun-day previews EVERY line at once with a would_execute_count, and STILL
      executes nothing (spy stays at zero).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_dryrun_preview.py
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
from anticipy_engine.live_memory.review_infer import infer_line  # noqa: E402
from anticipy_engine.shared.schema import now_ts  # noqa: E402


# Same lines a person speaks as in the press-go test, so the dry-run keys off the SAME
# review inference the owner sees.
CALENDAR = "I need to meet the roofing vendor tomorrow at 2pm."
DRAFT = "I'll draft the contract email to Priya tomorrow morning."
NOTE = "Remind me to renew the patio permit."
SEND = "Send Sam the revised decking file."
MONEY = "Pay the vendor $500 for the filter today."
MESSAGE = "Message Priya on Slack about the vendor call."
VENT = "ugh I should just quit my job and move to a beach"


async def _seed_inert(core: ControlCore, text: str) -> str:
    """Seed ONLY the inert remembered store (the SAFE half), bypassing the normal capture
    open_loop side-effect — so the trigger's open_loops source stays empty and the test
    isolates the DRY-RUN's effect (zero) rather than capture's normal side-effects. This is
    the same isolation press-go uses for its no-auto-fire check."""
    row = core.live_memory.capturer.remember.remember(text, source="transcript")
    return str(row["id"])


def _install_spy(core: ControlCore) -> dict:
    """Count every call to the two orchestrator execution entry points. A dry-run must
    reach NEITHER — it plans and shows; it never executes."""
    counts = {"start_goal": 0, "_drive": 0}
    real_start = core.orchestrator.start_goal
    real_drive = core.orchestrator._drive

    async def start_spy(goal):
        counts["start_goal"] += 1
        return await real_start(goal)

    async def drive_spy(goal):
        counts["_drive"] += 1
        return await real_drive(goal)

    core.orchestrator.start_goal = start_spy
    core.orchestrator._drive = drive_spy
    return counts


async def run(fails):
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-dryrun-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    counts = _install_spy(core)
    out = {}
    try:
        # Seed straight into the INERT remembered store so the ONLY thing that could
        # execute / auto-fire is the dry-run itself (which must do neither). Normal capture
        # has its own open_loop side-effects that would mask the dry-run's true (zero) effect.
        ids = {}
        for name, text in (("CALENDAR", CALENDAR), ("DRAFT", DRAFT), ("NOTE", NOTE),
                           ("SEND", SEND), ("MONEY", MONEY), ("MESSAGE", MESSAGE),
                           ("VENT", VENT)):
            ids[name] = await _seed_inert(core, text)

        for name in ids:
            out[name] = core.dryrun_remembered(ids[name])

        # ---- (1) WHITELIST PREVIEW: concrete planned intent + tool + args ----
        expect = {
            "CALENDAR": ("create_event", "GoogleCalendar.CreateEvent"),
            "DRAFT":    ("send_email_draft", "Gmail.WriteDraftEmail"),
            "NOTE":     ("write_memory", None),  # local tool label, just assert prefix
        }
        for name, (intent, tool) in expect.items():
            p = out[name]
            if p.get("would_execute") is not True:
                fails.append(f"{name} dry-run did not preview would_execute=true: {p}")
            if p.get("intent") != intent:
                fails.append(f"{name} previewed wrong intent: {p.get('intent')} != {intent}")
            if p.get("intent") not in WHITELIST:
                fails.append(f"{name} previewed intent not in WHITELIST: {p}")
            if not isinstance(p.get("args"), dict) or not p["args"]:
                fails.append(f"{name} preview missing concrete args: {p}")
            if not p.get("would_do"):
                fails.append(f"{name} preview missing would_do description: {p}")
            if tool is not None and p.get("tool") != tool:
                fails.append(f"{name} previewed wrong tool: {p.get('tool')} != {tool}")
            if tool is None and not str(p.get("tool", "")).startswith("Anticipy.Memory"):
                fails.append(f"{name} previewed wrong local tool: {p.get('tool')}")
            if not p.get("note"):
                fails.append(f"{name} preview missing connect-first note: {p}")

        # the connect-first note for Google-backed intents says exactly what it'll do live
        cal_note = str(out["CALENDAR"].get("note", "")).lower()
        if "connect google" not in cal_note:
            fails.append(f"CALENDAR note missing 'connect Google' promise: {cal_note!r}")

        # the previewed args are the SAME args approve_remembered would drive (same mapper):
        # dry-run promises EXACTLY what execution would send.
        for name, intent in (("CALENDAR", "create_event"), ("DRAFT", "send_email_draft"),
                             ("NOTE", "write_memory")):
            raw = next(r for r in core.live_memory.capturer.remember.all()
                       if r["id"] == ids[name])["text"]
            mapped = map_inferred_to_step(infer_line(raw), raw_text=raw)
            real_args = dict(mapped["step"].args)
            if out[name].get("args") != real_args:
                fails.append(f"{name} previewed args differ from press-go args: "
                             f"{out[name].get('args')} != {real_args}")

        # ---- (2) NON-WHITELIST PREVIEW: would_execute=false + handback + why ----
        for name in ("SEND", "MONEY", "MESSAGE"):
            p = out[name]
            if p.get("would_execute") is not False:
                fails.append(f"{name} dry-run did not deny would_execute: {p}")
            if p.get("intent") in WHITELIST:
                fails.append(f"{name} previewed INTO the whitelist (hole!): {p}")
            if not p.get("handback"):
                fails.append(f"{name} preview missing handback: {p}")
            if not p.get("why"):
                fails.append(f"{name} preview missing why: {p}")

        # ---- (3) VENT PREVIEW: would_execute=false, vent stop, no intent ----
        v = out["VENT"]
        if v.get("would_execute") is not False:
            fails.append(f"VENT dry-run did not deny: {v}")
        if v.get("intent") is not None:
            fails.append(f"VENT previewed an intent: {v}")
        if "vent" not in (v.get("why") or "").lower() \
                and "no confident" not in (v.get("why") or "").lower():
            fails.append(f"VENT why not a vent stop: {v}")

        # ---- (4) DAY MODE: preview the whole day, still no execution ----
        rows = core.live_memory.capturer.remember.recent(50)
        day = {"previews": [core.dryrun_remembered(str(r.get("id"))) for r in rows]}
        day["would_execute_count"] = sum(1 for p in day["previews"] if p.get("would_execute"))
        if day["would_execute_count"] != 3:  # CALENDAR + DRAFT + NOTE
            fails.append(f"day mode would_execute_count wrong: {day['would_execute_count']} "
                         f"(expected 3)")
        if len(day["previews"]) != 7:
            fails.append(f"day mode did not preview all lines: {len(day['previews'])}")

        # ---- (0) THE LOAD-BEARING ASSERTION: NOTHING executed across all dry-runs ----
        if counts["start_goal"] != 0 or counts["_drive"] != 0:
            fails.append(f"dry-run EXECUTED something (must be zero): {counts}")
        if core.store.all():
            fails.append(f"dry-run persisted a goal (must be none): "
                         f"{[g.intent for g in core.store.all()]}")
        # the NOTE dry-run must NOT have written a memory note (no side effect)
        loops = [l.text for l in core.live_memory.memory.open_loops.all()]
        if any("patio permit" in t.lower() for t in loops):
            fails.append(f"dry-run wrote a memory note as a side effect: {loops}")

        # a dry-run added no due/remind field -> trigger_tick now AND +10y fires ZERO
        now = now_ts()
        fired_now = await core.proactive.trigger_tick(now=now)
        fired_future = await core.proactive.trigger_tick(now=now + 3650 * 86400.0)
        if fired_now or fired_future:
            fails.append(f"dry-run made the remembered store auto-fire: "
                         f"now={fired_now} future={fired_future}")
        if counts["start_goal"] != 0 or counts["_drive"] != 0:
            fails.append(f"orchestrator fired after dry-run + trigger_tick: {counts}")

        return out, day, counts
    finally:
        await core.stop()


async def main():
    fails = []
    out, day, counts = await run(fails)

    print("==== LIVE DRY-RUN PREVIEW ====")
    print(f"  (0) EXECUTES NOTHING: start_goal={counts['start_goal']} "
          f"_drive={counts['_drive']} (must be 0/0)")
    print(f"  (1) WHITELIST preview (would_execute=true, concrete plan):")
    for name in ("CALENDAR", "DRAFT", "NOTE"):
        p = out[name]
        print(f"      {name:8s} -> intent={p.get('intent')} tool={p.get('tool')!r}")
        print(f"               args={p.get('args')}")
        print(f"               note={p.get('note')!r}")
    print(f"  (2) NON-WHITELIST preview (would_execute=false, handback):")
    for name in ("SEND", "MONEY", "MESSAGE"):
        p = out[name]
        print(f"      {name:8s} -> would_execute={p.get('would_execute')} "
              f"intent={p.get('intent')} why={p.get('why')!r}")
    v = out["VENT"]
    print(f"  (3) VENT      -> would_execute={v.get('would_execute')} why={v.get('why')!r}")
    print(f"  (4) DAY MODE  -> previewed {len(day['previews'])} lines, "
          f"would_execute_count={day['would_execute_count']}")

    if fails:
        print("==== FAIL ===="); [print("   -", f) for f in fails]; raise SystemExit(1)
    print("==== PASS: dry-run shows the concrete planned intent+tool+args for whitelisted "
          "lines and handback for the rest, while executing NOTHING (start_goal=0, "
          "_drive=0, no goal, no note, no auto-fire) ====")


if __name__ == "__main__":
    asyncio.run(main())
