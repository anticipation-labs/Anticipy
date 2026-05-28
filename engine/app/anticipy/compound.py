"""The P9 whole system compound scenario as ONE durable workflow.

It chains every layer end to end and is journaled step by step on the
P0 durable runtime, so a process kill mid scenario resumes exactly
where it left off without re running completed steps:

  1. onboard a new user, build and persist the profile
  2. a hedged dinner mention is stored as a latent intent
  3. later a direct command firms it up, resolved against profile and
     memory, decided ACT
  4. handed off, the action engine asks party size, resolved from the
     profile (memory first), executed (mocked action result)
  5. status communicated non critically over the two way channel

Each side effecting step increments a durable side effect counter so a
test can prove replay re ran nothing. The deterministic parts (the
fixed onboarding answers, the firmed command, the mocked action engine)
make the scenario reproducible across a kill; the profile party size is
what the action engine clarification resolves against.
"""

from __future__ import annotations

import asyncio
import json

from app.anticipy import action_handoff, durable, memory, platform_adapter, spine
from app.anticipy.seams import OutboundMessage

_FIXED_INTAKE = [
    {"speaker_id": "INTERVIEWER", "text": "Your name and role?"},
    {"speaker_id": "WEARER", "text": "I'm Omar, founder of an AI hardware startup."},
    {"speaker_id": "INTERVIEWER", "text": "One sentence on what you do?"},
    {"speaker_id": "WEARER", "text": "I run product and ops day to day."},
    {"speaker_id": "INTERVIEWER", "text": "Time zone and hours?"},
    {"speaker_id": "WEARER", "text": "US Eastern, roughly 9 to 7."},
    {"speaker_id": "INTERVIEWER", "text": "Important people, and who are 'the boss' and 'us'?"},
    {"speaker_id": "WEARER", "text": "The boss is Dana, my lead investor. 'Us' means me and my "
     "wife Priya, a party of two for dinners."},
    {"speaker_id": "INTERVIEWER", "text": "Daily tools?"},
    {"speaker_id": "WEARER", "text": "Gmail, Google Calendar, Slack, Notion, Linear."},
    {"speaker_id": "INTERVIEWER", "text": "What should Anticipy do, and what is off limits?"},
    {"speaker_id": "WEARER", "text": "Handle scheduling, dinner bookings and email proactively. "
     "Do not touch payroll or legal."},
    {"speaker_id": "INTERVIEWER", "text": "How to reach you, quiet hours?"},
    {"speaker_id": "WEARER", "text": "Text for normal, call only if truly urgent. Quiet hours "
     "after 10pm."},
]


def _ctr_path():
    return platform_adapter.data_dir() / "compound_side_effects.txt"


def _bump():
    p = _ctr_path()
    n = int(p.read_text()) if p.exists() else 0
    p.write_text(str(n + 1))


def _bumped() -> int:
    p = _ctr_path()
    return int(p.read_text()) if p.exists() else 0


def reset_counter():
    p = _ctr_path()
    if p.exists():
        p.unlink()


def _mock_party_size_engine():
    """Mock action engine that, like the real one may, asks a
    clarifying question (party size) the first time, then succeeds once
    the handoff has answered it from the profile.
    """
    def impl(contract: dict) -> dict:
        if not contract.get("_clarification_answer"):
            return {"clarification": {
                "intent_id": contract.get("intent_id"),
                "question": "How many people for the dinner reservation, the usual us?",
                "options": [], "criticality_hint": "low",
            }}
        return {"status": "SUCCESS",
                "answer": f"booked dinner for {contract.get('_clarification_answer')}",
                "evidence": "mocked action result"}
    return impl


async def _wf(ctx):
    uid = ctx.input["user_id"]

    async def step_onboard():
        from app.anticipy import onboarding
        prof = await onboarding.run_intake(_FIXED_INTAKE, uid)
        _bump()
        return {"name": prof.name, "people": prof.people, "mandate": prof.mandate,
                "populated": onboarding.profile_is_well_populated(prof)}

    prof_d = await ctx.journal_step("onboard", step_onboard)

    def step_store_latent():
        memory.add_latent(uid, "we should maybe grab dinner sometime")
        _bump()
        return {"latent": "dinner", "active": memory.has_active_matching(uid, "dinner")}

    latent_d = await ctx.journal_step("store_latent", step_store_latent)

    # The narrative durable boundary: the hedged mention is stored as
    # latent and LATER firmed up by a direct command. "Later" is a real
    # suspension that must survive a process kill. The scenario is
    # killed while suspended here; on resume the onboard and
    # store_latent steps replay from the journal (no re execution,
    # proven by the side effect counter) and the workflow continues.
    await ctx.await_external("firm_up", timeout_s=None)

    async def step_firm_decision():
        from app.anticipy.proactive_engine import ProactiveEngine
        from app.anticipy.seams import UserContext, UserProfile
        prof = UserProfile(
            user_id=uid, name=prof_d["name"], role_title="Founder",
            what_they_do="runs an AI hardware startup",
            mandate=prof_d["mandate"], people=prof_d["people"],
            trajectory_confidence=0.8, days_since_onboard=40,
        )
        eng = ProactiveEngine()
        r = await eng.decide(
            [{"speaker_id": "WEARER",
              "text": "Book that dinner we talked about, Friday at 7 at the usual place."}],
            UserContext.from_profile(prof), "direct")
        _bump()
        return {"decision": r.decision, "intent": r.intent, "unit": r.unit_text}

    dec_d = await ctx.journal_step("firm_decision", step_firm_decision)

    def step_handoff():
        platform_adapter.set_action_engine_impl(_mock_party_size_engine())
        from app.anticipy.action_handoff import ProactiveContract, handoff
        from app.anticipy.seams import UserContext, UserProfile
        prof = UserProfile(user_id=uid, name=prof_d["name"], role_title="Founder",
                            mandate=prof_d["mandate"], people=prof_d["people"])
        c = ProactiveContract(intent_id="cmp-1", action="book_reservation",
                              object=dec_d.get("unit") or "Book the dinner Friday 7 at the usual place")
        res = handoff(c, UserContext.from_profile(prof))
        _bump()
        return {"status": res.status, "answer": res.answer,
                "clar_path": res.clarification_path, "blocked": res.blocked}

    ho_d = await ctx.journal_step("handoff", step_handoff)

    def step_comms_status():
        platform_adapter.comms_send(OutboundMessage(
            task_id="cmp-1", user_id=uid, channel="text",
            body=f"Done: {ho_d.get('answer','dinner booked')}",
            criticality="non_critical", ts=0.0).to_dict())
        _bump()
        return {"notified": True, "channel": "text", "criticality": "non_critical"}

    comms_d = await ctx.journal_step("comms_status", step_comms_status)

    return {"onboard": prof_d, "latent": latent_d, "decision": dec_d,
            "handoff": ho_d, "comms": comms_d}


durable.register_workflow("p9_compound", _wf)


def start(user_id: str, wf_id: str) -> dict:
    return durable.start_workflow("p9_compound", wf_id, {"user_id": user_id})


def resume() -> list:
    return durable.resume_all()
