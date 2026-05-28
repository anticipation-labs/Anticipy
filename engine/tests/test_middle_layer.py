"""End-to-end Phase 4 middle layer test against real Supabase.

Builds a synthetic TypedIntent, runs through:
   slot_resolver  → skill_router  → policy  → dispatcher

Asserts the right Task lands in anticipy_tasks_v2 (or that the policy
correctly refuses).

Per Rule 13: this is the passing end-to-end test for Phase 4.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT.parent / ".env.local")

from app.middle import (  # noqa: E402
    Dispatcher,
    PolicyDispatchAction,
    PolicyEngine,
    SkillRouter,
    SlotResolver,
)
from app.proactive.intent_extraction import IntentSlots, TypedIntent  # noqa: E402


def make_intent(
    *,
    user_id: str = "midtest",
    action_category: str = "schedule_event",
    filled: dict | None = None,
    needs_memory: list[str] | None = None,
    needs_inference: list[str] | None = None,
    ambiguous: list[str] | None = None,
    proactivity: float = 0.85,
    hedge_decision: str = "COMMIT",
    skill_hint: str | None = None,
) -> TypedIntent:
    return TypedIntent(
        intent_id=str(uuid.uuid4()),
        user_id=user_id,
        utterance_window={
            "transcript_segments": [{"speaker": "wearer", "text": "test"}],
            "start_ts": "",
            "end_ts": "",
        },
        action_category=action_category,
        proposed_skill_hint=skill_hint,
        slots=IntentSlots(
            filled=filled or {},
            needs_memory=needs_memory or [],
            needs_inference=needs_inference or [],
            ambiguous=ambiguous or [],
        ),
        detection_confidence=0.9,
        hedge_filter_decision=hedge_decision,
        hedge_filter_reason="test",
        proactivity_score=proactivity,
        source="typed",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def case(name: str, ok: bool, detail: str = "") -> tuple[str, bool, str]:
    sym = "PASS" if ok else "FAIL"
    print(f"[{sym}] {name}{('  — ' + detail) if detail else ''}")
    return (name, ok, detail)


def main() -> int:
    resolver = SlotResolver()
    router = SkillRouter()
    policy = PolicyEngine()
    dispatcher = Dispatcher()

    cases: list[tuple[str, bool, str]] = []

    # ── Case 1: schedule_event with day "next Tuesday" ────────────────
    intent = make_intent(
        action_category="schedule_event",
        filled={"title": "Coffee with Sarah", "day": "next Tuesday", "time": "14:00"},
        needs_inference=["date", "duration_min"],
    )
    # The dispatcher writes a Task that FKs to anticipy_intents_v2.
    # We must insert the Intent first so the FK is satisfied.
    sb_for_setup = dispatcher._ensure_supabase()
    if sb_for_setup is not None:
        sb_for_setup.table("anticipy_intents_v2").insert(intent.to_db_row()).execute()
    slots = resolver.resolve(intent)
    cases.append(
        case(
            "case1.slot_resolver.date_inferred",
            "date" in slots.resolved_by_inference,
            f"date={slots.resolved_by_inference.get('date')}",
        )
    )
    cases.append(
        case(
            "case1.slot_resolver.duration_default",
            slots.resolved_by_inference.get("duration_min") == 60,
            f"duration_min={slots.resolved_by_inference.get('duration_min')}",
        )
    )
    route = router.route(intent)
    cases.append(
        case(
            "case1.skill_router.miss_on_empty_library",
            route.hit is False,
            "library empty → miss expected",
        )
    )
    decision = policy.decide(intent, slots, route)
    cases.append(
        case(
            "case1.policy.fire_when_reversible_resolved",
            decision.action == PolicyDispatchAction.FIRE,
            f"action={decision.action.value} reason={decision.reason}",
        )
    )
    dr = dispatcher.dispatch(intent, slots, route, decision)
    cases.append(
        case(
            "case1.dispatcher.task_inserted",
            dr.dispatched and dr.task_id is not None,
            f"task_id={dr.task_id}",
        )
    )

    # ── Case 2: irreversible category (send_email) → AEVOY_CONFIRM ────
    intent2 = make_intent(
        action_category="send_email",
        filled={"recipient": "Sarah", "body": "Confirming Tuesday at 3"},
    )
    slots2 = resolver.resolve(intent2)
    route2 = router.route(intent2)
    decision2 = policy.decide(intent2, slots2, route2)
    cases.append(
        case(
            "case2.policy.email_requires_aevoy_confirm",
            decision2.action == PolicyDispatchAction.AEVOY_CONFIRM
            and decision2.aevoy_confirmation_required,
            f"action={decision2.action.value} reason={decision2.reason}",
        )
    )

    # ── Case 3: STORE_AS_LATENT → REFUSE (never dispatched) ───────────
    intent3 = make_intent(
        action_category="schedule_event",
        hedge_decision="STORE_AS_LATENT",
    )
    slots3 = resolver.resolve(intent3)
    route3 = router.route(intent3)
    decision3 = policy.decide(intent3, slots3, route3)
    cases.append(
        case(
            "case3.policy.store_as_latent_refused",
            decision3.action == PolicyDispatchAction.REFUSE
            and decision3.reason == "store_as_latent_only",
            f"reason={decision3.reason}",
        )
    )

    # ── Case 4: low proactivity → AEVOY_CONFIRM even if reversible ───
    intent4 = make_intent(
        action_category="set_reminder",
        proactivity=0.4,
    )
    slots4 = resolver.resolve(intent4)
    route4 = router.route(intent4)
    decision4 = policy.decide(intent4, slots4, route4)
    cases.append(
        case(
            "case4.policy.low_proactivity_confirms",
            decision4.action == PolicyDispatchAction.AEVOY_CONFIRM,
            f"action={decision4.action.value} reason={decision4.reason}",
        )
    )

    # ── Case 5: financial commitment above floor ──────────────────────
    intent5 = make_intent(
        action_category="reorder",
        filled={"item": "laptop stand", "amount_usd": 51.25},
    )
    slots5 = resolver.resolve(intent5)
    route5 = router.route(intent5)
    decision5 = policy.decide(intent5, slots5, route5)
    cases.append(
        case(
            "case5.policy.financial_above_floor_confirms",
            decision5.action == PolicyDispatchAction.AEVOY_CONFIRM
            and "financial_above_floor" in decision5.reason,
            f"action={decision5.action.value} reason={decision5.reason}",
        )
    )

    # ── Case 6: financial commitment BELOW floor → fire ───────────────
    intent6 = make_intent(
        action_category="reorder",
        filled={"item": "dog food refill", "amount_usd": 2.99},
    )
    slots6 = resolver.resolve(intent6)
    route6 = router.route(intent6)
    decision6 = policy.decide(intent6, slots6, route6)
    cases.append(
        case(
            "case6.policy.financial_below_floor_fires",
            decision6.action == PolicyDispatchAction.FIRE,
            f"action={decision6.action.value} reason={decision6.reason}",
        )
    )

    # ── Case 7: day-label inference (Thursday → next Thu ISO) ─────────
    intent7 = make_intent(
        action_category="schedule_event",
        filled={"day": "Thursday"},
        needs_inference=["date"],
    )
    slots7 = resolver.resolve(intent7)
    cases.append(
        case(
            "case7.slot_resolver.thursday_to_iso",
            slots7.resolved_by_inference.get("date") is not None,
            f"date={slots7.resolved_by_inference.get('date')}",
        )
    )

    # ── Summary ───────────────────────────────────────────────────────
    n = len(cases)
    hits = sum(1 for _, ok, _ in cases if ok)
    print()
    print(f"== SUMMARY: {hits}/{n} ==")
    if hits != n:
        for name, ok, detail in cases:
            if not ok:
                print(f"   FAIL  {name}  {detail}")
    return 0 if hits == n else 1


if __name__ == "__main__":
    sys.exit(main())
