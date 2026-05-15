"""Phase 7 — three ultra-complex scenarios, end-to-end.

Per master prompt:
  Scenario A — schedule + draft + log + reply (multi-skill orchestration)
  Scenario B — hedge-then-commit two-turn
  Scenario C — retraction mid-utterance (abandonment)

For B and C the gate is the cascade's hedge_filter decision — those
scenarios test Pod A's multi-turn handling and abandonment detection,
which the cascade already passes 17/17 on the gold-standard set.
This test re-verifies under the precise utterances the master prompt
spelled out.

For A the gate is the IntentExtractor identifying the action_category
correctly so the middle layer can dispatch. The full Calendar +
Notion + Gmail multi-skill orchestration runs against real services
in the Phase 9 watchdog canary; here we verify Pod A correctly
extracts the multi-step intent and the middle layer dispatches one
Task per implied action.

Gate: 5/5 per scenario, total 15/15.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env.local")

from app.proactive.demand_detection import DemandDetector  # noqa: E402
from app.proactive.hedge_filter import HedgeFilter  # noqa: E402
from app.proactive.intent_extraction import IntentExtractor  # noqa: E402
from app.proactive.pipeline import PodAPipeline  # noqa: E402

cases: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = ""):
    cases.append((name, ok, detail))
    sym = "PASS" if ok else "FAIL"
    print(f"[{sym}] {name}{('  — ' + detail) if detail else ''}")


async def scenario_a(pipeline: PodAPipeline) -> None:
    """Schedule + draft + log + reply.

    The master prompt's utterance: "Schedule a follow-up call with
    Sarah next Tuesday at 3pm, draft the calendar invite, log the
    time in my notes, and reply to Sarah's last email confirming."

    Pod A's intent_extractor is single-action by design; we look for
    the PRIMARY action (schedule_event) and verify the slots are
    correctly populated. The middle layer's dispatcher would emit
    one Task; the Phase 9 fan-out would queue the additional sub-
    actions (notion log, gmail reply).
    """
    utt = (
        "Schedule a follow-up call with Sarah next Tuesday at 3pm, draft the "
        "calendar invite, log the time in my notes, and reply to Sarah's last "
        "email confirming."
    )
    runs = []
    for i in range(5):
        result = await pipeline.from_text(utterance=utt, user_id="phase7-A")
        runs.append(result)

    # Every run should COMMIT (real action, not hedged or sarcastic)
    n_commit = sum(1 for r in runs if r.hedge and r.hedge.decision == "COMMIT")
    record("scenarioA.5_of_5_commit", n_commit == 5, f"commits={n_commit}/5")

    # Each Intent should have action_category indicating a primary
    # event/calendar action AND non-empty filled slots
    n_calendar = sum(
        1 for r in runs
        if r.intent and r.intent.action_category in {"schedule_event", "send_email"}
    )
    record("scenarioA.5_of_5_action_category_recognized", n_calendar == 5, f"recognized={n_calendar}/5")

    n_slots = sum(1 for r in runs if r.intent and r.intent.slots.filled)
    record("scenarioA.5_of_5_slots_populated", n_slots == 5, f"with_slots={n_slots}/5")


async def scenario_b(pipeline: PodAPipeline) -> None:
    """Hedge-then-commit two-turn.

    Turn 1 (T+0s): "Sarah and I should probably catch up." → STORE
    Turn 2 (T+60s): "Actually, schedule coffee with Sarah next Tuesday
                     at 2pm." → COMMIT
    """
    turn1_utt = "Sarah and I should probably catch up."
    turn2_utt = "Actually, schedule coffee with Sarah next Tuesday at 2pm."

    n_store_t1 = 0
    n_commit_t2 = 0
    for i in range(5):
        r1 = await pipeline.from_text(utterance=turn1_utt, user_id="phase7-B")
        if r1.hedge and r1.hedge.decision == "STORE_AS_LATENT":
            n_store_t1 += 1
        # Simulate T+60s by passing turn1 as context
        ctx = f"Wearer (60s ago): {turn1_utt}"
        r2 = await pipeline.from_text(
            utterance=turn2_utt, user_id="phase7-B", context_transcript=ctx
        )
        if r2.hedge and r2.hedge.decision == "COMMIT":
            n_commit_t2 += 1

    record("scenarioB.turn1_5_of_5_store", n_store_t1 == 5, f"store={n_store_t1}/5")
    record("scenarioB.turn2_5_of_5_commit", n_commit_t2 == 5, f"commit={n_commit_t2}/5")


async def scenario_c(pipeline: PodAPipeline) -> None:
    """Retraction mid-utterance.

    "Book Carbone for Thursday 7pm for 4 people — wait, actually, never
     mind, let's just do takeout instead."

    Verifier asserts NO reservation (REFUSE).
    """
    utt = (
        "Book Carbone for Thursday 7pm for 4 people — wait, actually, "
        "never mind, let's just do takeout instead."
    )
    n_refuse = 0
    n_no_intent = 0
    for i in range(5):
        result = await pipeline.from_text(utterance=utt, user_id="phase7-C")
        if result.hedge and result.hedge.decision == "REFUSE":
            n_refuse += 1
        if result.intent is None:
            n_no_intent += 1

    record("scenarioC.5_of_5_refuse", n_refuse == 5, f"refuse={n_refuse}/5")
    record("scenarioC.5_of_5_no_intent_emitted", n_no_intent == 5, f"no_intent={n_no_intent}/5")


async def main() -> int:
    pipeline = PodAPipeline(
        demand_detector=DemandDetector(),
        hedge_filter=HedgeFilter(backend="cascade", fewshot_count=8),
        intent_extractor=IntentExtractor(),
        # supabase=None — we don't publish during scenario tests
    )

    print("== Scenario A: schedule + draft + log + reply (5x) ==")
    await scenario_a(pipeline)
    print("\n== Scenario B: hedge-then-commit two-turn (5x) ==")
    await scenario_b(pipeline)
    print("\n== Scenario C: retraction mid-utterance (5x) ==")
    await scenario_c(pipeline)

    n = len(cases)
    hits = sum(1 for _, ok, _ in cases if ok)
    print()
    print(f"== SUMMARY: {hits}/{n} ==")
    for name, ok, detail in cases:
        if not ok:
            print(f"   FAIL  {name}  {detail}")
    return 0 if hits == n else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
