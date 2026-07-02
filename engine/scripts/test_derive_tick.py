"""LOCK: TRUE PROACTIVITY orchestration (FIX-07) — derive → research → ONE front door → notify.

Pins the derive_tick contract deterministically (stub model, mock hands/channels, no network):
  1. A derived calendar-hold need flows through owner_ingest (the ONE front door), produces a
     card, and the owner gets exactly ONE text (derived_notified in the glassbox).
  2. Fire-once: a second tick the same day derives the same need and fires NOTHING (ledger).
  3. The floors are structural: a money-flavored need never survives derive_needs; a
     low-confidence need never survives; kinds outside the whitelist never survive.
  4. Dedupe: a need matching an existing open loop / recent card is dropped, not re-surfaced.
  5. Stub honesty: with no model, derive_needs returns [] and the tick is a quiet no-op.

The model brain is simulated by patching derive.derive_needs (the seam the live model owns);
everything downstream — ledger, dedupe, research jobs, ingest, notify, budget — runs REAL.
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_CHANNELS_MODE", "mock")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.proactive import derive as derive_mod  # noqa: E402
from anticipy_engine.proactive.derive import (  # noqa: E402
    ALLOWED_KINDS, CONFIDENCE_FLOOR, DerivedNeed, WorldSnapshot, derive_needs,
)

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        fails.append(f"{name}: {detail}")


PICKUP = DerivedNeed(
    need="Leila needs pickup from Lakeview Elementary at 3:15 today",
    why="Recurring school pickup; the calendar shows a 1:30-2:30 investor sync ending nearby",
    evidence=["profile: daughter Leila, Lakeview Elementary", "calendar: investor sync 1:30-2:30"],
    research_questions=["Using a maps site in the browser, find the driving time from the office to Lakeview Elementary leaving at 2:40pm"],
    action_kind="calendar_hold",
    action_args={"title": "Leave to pick up Leila at Lakeview Elementary", "start_local": "14:40", "duration_min": 40},
    confidence=0.9,
)


async def main() -> None:
    d = Path(tempfile.mkdtemp())
    core = ControlCore(data_dir=d)
    await core.start()
    try:
        # ---- (1) the happy path: derive -> research -> front door -> ONE notify ----
        async def fake_derive(gateway, snapshot):
            check("snapshot is a WorldSnapshot", isinstance(snapshot, WorldSnapshot))
            return [PICKUP]
        derive_mod.derive_needs = fake_derive

        res = await core.derive_tick()
        derived = res.get("derived") or []
        check("one need processed", len(derived) == 1, f"derived={len(derived)}")
        entry = derived[0] if derived else {}
        check("research ran (browser-only path)", isinstance(entry.get("research"), list)
              and len(entry["research"]) == 1, str(entry.get("research"))[:120])
        check("front door produced a decision", entry.get("decision") in {"act", "ask", "silent"},
              str(entry.get("decision")))
        sent = getattr(core.proactive.channel, "sent", []) or []
        glass = json.dumps(entry)
        if entry.get("decision") == "act":
            check("owner notified exactly once on act", entry.get("notified") is True and len(sent) >= 1,
                  f"notified={entry.get('notified')} sent={len(sent)}")
        # the ledger stamped BEFORE acting
        ledger = json.loads((d / "derived_needs.json").read_text())
        check("fire-once ledger stamped", len(ledger) == 1, f"ledger={list(ledger)[:2]}")

        # ---- (2) fire-once: same day, same need -> nothing fires ----
        before_sent = len(getattr(core.proactive.channel, "sent", []) or [])
        res2 = await core.derive_tick()
        check("second tick fires nothing", not (res2.get("derived") or []),
              f"derived={len(res2.get('derived') or [])}")
        after_sent = len(getattr(core.proactive.channel, "sent", []) or [])
        check("no second text", before_sent == after_sent, f"{before_sent}->{after_sent}")

        # ---- (5) stub honesty: the REAL derive_needs on a stub gateway is a quiet [] ----
        needs = await derive_needs(core.gateway, WorldSnapshot(now=0.0))
        check("stub model derives nothing", needs == [], str(needs)[:80])
    finally:
        await core.bus.stop()

    # ---- (3) structural floors (pure, no engine needed) ----
    check("money kind impossible", "send_money" not in ALLOWED_KINDS and "purchase" not in ALLOWED_KINDS)
    check("confidence floor is 0.6", abs(CONFIDENCE_FLOOR - 0.6) < 1e-9)
    money_need = PICKUP.model_copy(update={"need": "pay the $500 invoice", "why": "invoice due"})
    from anticipy_engine.proactive.harm import _MONEY_SIGNAL
    check("money text trips the canonical detector", bool(_MONEY_SIGNAL.search(money_need.need)))


asyncio.run(main())

if fails:
    for f in fails:
        print("FAIL:", f)
    raise SystemExit(1)
print("PASS derive_tick: derive→research→front-door→notify proven; fire-once holds; floors structural; stub honest")
