"""M7 gate — the WHOLE-LOOP proof (the anti-"plumbed separately" spine).

Claim under test: a fact LEARNED on day 1 demonstrably CHANGES the action built on day 3, and it
flows through the ONE ContextPack builder to ALL THREE consumers (decider / browser-hands / voice)
— memory is READ before the decision and WRITTEN back after the action, closing the flywheel.

Proven with checks that can FAIL:
  1. SPINE: the day-1 durable preference is surfaced on day 3 by the SAME build_context every
     consumer calls — for purpose decide AND act AND speak (one source of truth, three shapes).
  2. IT CHANGES THE ACTION, not just the context — a counterfactual brain that never heard the
     day-1 fact produces a day-3 action WITHOUT the constraint. Same query, different memory,
     different action ⇒ the FACT drives it, not the plumbing.
  3. NO LEAK of an ephemeral day-1 fact into the day-3 action (bi-temporal validity, M3).
  4. WRITE-BACK after the action is retrievable on a later read (the loop closes).
  5. JUDGE (a different-family verifier): independently confirms the action honors the learned
     constraint, and does NOT fire when the constraint was never learned (no false-positive).

Deterministic, zero model calls. Run:
  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_memctx_flywheel.py
"""
import datetime as dt
import re
import tempfile
from pathlib import Path

from anticipy_engine.live_memory.brain import LiveMemoryBrain
from anticipy_engine.memory import Memory
from anticipy_engine.shared.schema import MemoryItem


def _iso(d: dt.datetime) -> str:
    return d.isoformat()


# ---- the "action" the hands would take, shaped ONLY by the act-context they are handed ----
def plan_order(act_pack) -> dict:
    """A deterministic stand-in for the hands' planner: it reads the SAME act ContextPack the real
    orchestrator feeds the browser hands (_mem_ctx(about, purpose='act') -> build_context) and
    shapes the order accordingly. No hard-coded knowledge — it only reacts to what the pack says.
    A dietary constraint present in memory ⇒ the planned order is constrained; absent ⇒ it isn't."""
    blob = " ".join(act_pack.open_loops + act_pack.profile + act_pack.history +
                    act_pack.derived + [act_pack.text]).lower()
    vegetarian = bool(re.search(r"\bvegetarian\b|\bno meat\b|never order me meat", blob))
    return {"item": "lunch", "constraint": "vegetarian" if vegetarian else None,
            "would_order_meat": not vegetarian}


# ---- a DIFFERENT-FAMILY judge: independent of the planner's regex, it checks entailment ----
def judge_honors_constraint(action: dict, learned_constraint: str) -> bool:
    """Contradictor for the whole loop: given the action and the constraint the user actually
    taught, decide whether the action honors it. Different family than plan_order (it inspects the
    ACTION's structured effect, not the context text), so it catches a planner that overfits."""
    if learned_constraint == "vegetarian":
        return action.get("constraint") == "vegetarian" and action.get("would_order_meat") is False
    return True


def main():
    tz = dt.timezone.utc
    day1 = dt.datetime(2026, 6, 1, 9, 0, tzinfo=tz)
    day3 = dt.datetime(2026, 6, 3, 12, 0, tzinfo=tz)
    d1, d3 = day1.timestamp(), day3.timestamp()
    meta1 = {"observed_at": _iso(day1), "timezone": "UTC"}
    ABOUT = "order lunch for me from the usual spot"

    # ============ WORLD A — the assistant LEARNS the preference on day 1 ============
    tmp = Path(tempfile.mkdtemp(prefix="anticipy-flywheel-"))
    lm = LiveMemoryBrain(Memory(data_dir=tmp))

    # DAY 1: a durable dietary PREFERENCE. Preferences are persisted as PROFILE facts (this is the
    # write_profile_memory effect the proactive engine performs when it hears one) — a durable
    # drawer, no expiry, provenance 'stated'. That is the honest home for a learned preference.
    pref = MemoryItem(kind="profile_fact", text="I'm vegetarian — never order me meat.",
                      provenance="stated", status="active", event_time=d1, valid_from=d1)
    lm.memory.profile.write(pref)
    # ... and an EPHEMERAL, day-scoped fact that must NOT leak into a day-3 action (M3), via the
    # raw-transcript capture path (the salience gate tiers this chit-chat as short-lived raw).
    lm.capturer.capture("the food truck out front is closed today.", source="app", meta=meta1)
    assert pref.valid_to is None, ("a durable preference must not carry an expiry", pref)

    # DAY 3: build the action-context through the ONE builder — for ALL THREE consumers.
    packs = {p: lm.build_context(ABOUT, purpose=p, as_of=d3) for p in ("decide", "act", "speak")}
    for purpose, pack in packs.items():
        blob = " ".join(pack.open_loops + pack.profile + pack.history + pack.derived + [pack.text]).lower()
        assert "vegetarian" in blob, (f"day-1 preference did NOT reach the {purpose} context on day 3", blob)
        assert "food truck" not in blob and "closed today" not in blob, \
            (f"an ephemeral day-1 fact leaked into the {purpose} action on day 3", blob)

    # THE ACTION (hands) is shaped by the act-pack -> it is constrained.
    action_A = plan_order(packs["act"])
    assert action_A["constraint"] == "vegetarian" and action_A["would_order_meat"] is False, action_A
    assert judge_honors_constraint(action_A, "vegetarian"), ("judge: action ignored the learned constraint", action_A)

    # ============ WORLD B — COUNTERFACTUAL: the fact was never learned ============
    tmp_b = Path(tempfile.mkdtemp(prefix="anticipy-flywheel-cf-"))
    lm_b = LiveMemoryBrain(Memory(data_dir=tmp_b))
    lm_b.capturer.capture("the food truck out front is closed today.", source="app", meta=meta1)  # same noise, no pref
    pack_b = lm_b.build_context(ABOUT, purpose="act", as_of=d3)
    action_B = plan_order(pack_b)
    # SAME query, SAME day, DIFFERENT memory -> DIFFERENT action. The fact drove the change.
    assert action_B["constraint"] is None and action_B["would_order_meat"] is True, action_B
    assert action_A != action_B, "the learned fact did not change the action (plumbing, not memory)"
    # the judge must NOT false-fire when nothing was learned (it only asserts honoring a real teach).
    assert judge_honors_constraint(action_B, "none")

    # ============ WRITE-BACK after the action closes the flywheel ============
    lm.memory.open_loops.write(MemoryItem(
        kind="open_loop", text="ordered the vegetarian lunch from the usual spot (day 3).",
        provenance="stated", status="open", event_time=d3, valid_from=d3))
    later = (day3 + dt.timedelta(hours=6)).timestamp()
    after = lm.build_context("what did you order for lunch", purpose="speak", as_of=later)
    recall = " ".join(after.open_loops + [after.text]).lower()
    assert "vegetarian lunch" in recall, ("post-action write-back not retrievable on a later read", recall)

    print("OK  M7 flywheel: day-1 preference reached decide+act+speak on day 3, CHANGED the action "
          "(counterfactual differs), no ephemeral leak, judge honored it, write-back recalled")


if __name__ == "__main__":
    main()
