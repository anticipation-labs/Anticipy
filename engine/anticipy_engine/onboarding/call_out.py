"""Outbound onboarding CALL — the missing arm of the scrape<->call loop.

The four-layer inhale (loop.py) reads the owner's own accounts and dossier.py synthesizes a dossier
that honestly lists the GAPS a short call should fill. clarify.py ranks those gaps into a couple of
spoken questions. THIS module closes the loop: it INITIATES the outbound call (CallChannel.send —
mock records, live dials Twilio), runs the warm OnboardingCallBrain over the ranked gap-questions,
and writes the answers back into the profile/dossier so the next pass — and the first cards — are
re-aimed by what the owner just said.

Gating (honest, mirrors the rest of the engine): the LIVE call only dials when
ANTICIPY_CHANNELS_MODE=live + Twilio creds are present (CallChannel._live()). In MOCK mode the whole
loop still runs deterministically — the call is recorded as a mock send and a deterministic "owner"
supplies canned answers — so the wiring is provable WITHOUT a real Twilio call. Simulated answers are
written back TAGGED (provenance="onboarding_call", simulated=True) so a mock answer is never mistaken
for something the owner actually said. In live mode the real two-way conversation runs over the /cr
ConversationRelay socket; this module dials and hands off (answers_pending) and never fabricates.

Nothing here spends, sends, books, or executes — it dials, talks, and writes memory. Money/irreversible
stays a hard ASK on the ambient spine exactly as before.
"""
from __future__ import annotations

from contextlib import suppress
from typing import Any, Dict, List, Optional, Tuple

from . import dossier as _dossier
from .clarify import (
    DEFAULT_MAX_QUESTIONS,
    ClarifyingQuestion,
    _dossier_identity,
    clarifying_questions_from_dossier,
)

# Identity fields whose answer carries a value we can re-aim the dossier identity with.
_IDENTITY_FIELDS = ("role", "location", "name")

# Deterministic MOCK owner — (spoken answer, extracted value). Used only when no real answers are
# supplied AND the call is not live, so the mock loop is fully provable without a Twilio call.
_SIM_REPLY: Dict[str, Tuple[str, str]] = {
    "role": ("I'm a founder and product lead.", "founder and product lead"),
    "location": ("I'm based in Austin, Texas.", "Austin, Texas"),
    "org": ("I run a small startup — that's the company from my inbox.", ""),
    "name": ("Yep, you've got my name right.", ""),
}


def _slug(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())[:48]


def _greeting(questions: List[ClarifyingQuestion], name: Optional[str] = None) -> str:
    who = f" {name.split()[0]}" if isinstance(name, str) and name.strip() else ""
    n = len(questions)
    couple = "a couple of" if n <= 2 else f"{n}"
    return (
        f"Hey{who}, it's your Anticipy assistant. I went through what you shared and I've got "
        f"just {couple} quick questions to finish getting you set up — is now an okay time?"
    )


def _owner_reply(q: ClarifyingQuestion, supplied: Dict[str, Any]) -> Tuple[str, str]:
    """The owner's answer to one question: a real supplied answer when present, else the
    deterministic mock. Returns (spoken_answer, extracted_value)."""
    if q.field in supplied and str(supplied[q.field]).strip():
        v = str(supplied[q.field]).strip()
        return v, (v if q.field in _IDENTITY_FIELDS else "")
    if q.reason in supplied and str(supplied.get(q.reason) or "").strip():
        v = str(supplied[q.reason]).strip()
        return v, (v if q.field in _IDENTITY_FIELDS else "")
    if q.field in _SIM_REPLY:
        return _SIM_REPLY[q.field]
    return ("Good question — noted, let's keep it moving.", "")


def write_call_answers_to_memory(
    core: Any,
    dossier: Any,
    records: List[Dict[str, Any]],
    *,
    simulated: bool,
) -> Dict[str, int]:
    """Write the call answers back into memory (the RE-AIM).

    Each answer lands as a durable profile fact ("From setup call — Q ... Owner said: A") with a
    STABLE id (idempotent re-runs) and provenance="onboarding_call". Identity answers (role /
    location / name) additionally merge into the dossier's identity, which is then re-written
    through dossier.write_dossier_to_memory so the owner-identity fact reflects the call. Simulated
    (mock) answers are tagged simulated=True so they are never mistaken for a real owner statement.
    """
    mem = core.memory
    counts = {"profile": 0, "derived": 0}
    identity_updates: Dict[str, str] = {}
    for r in records:
        fid = "onb:call:" + _slug(r.get("field", "") + "|" + r.get("question", ""))
        mem.profile.write_text(
            f"From setup call — {r.get('question','')} Owner said: {r.get('answer','')}",
            provenance="onboarding_call",
            confidence=0.9,
            id=fid,
            simulated=bool(simulated),
            call_field=r.get("field", ""),
        )
        counts["profile"] += 1
        if r.get("field") in _IDENTITY_FIELDS and str(r.get("value") or "").strip():
            identity_updates[r["field"]] = str(r["value"]).strip()

    if identity_updates:
        # Re-aim the dossier's own identity with what the owner just confirmed, then re-persist it
        # through the SAME writer the inhale used, so the profile's identity fact is refreshed in
        # place (stable id "onb:identity") rather than duplicated.
        if isinstance(dossier, dict) and isinstance(dossier.get("dossier"), dict):
            src_inner = dossier["dossier"]
        elif isinstance(dossier, dict):
            src_inner = dossier
        else:
            src_inner = {}
        ident = dict(src_inner.get("identity") or {})
        ident.update({k: v for k, v in identity_updates.items() if k in ("role", "location", "name")})
        src_inner["identity"] = ident   # re-aim the live dossier object in place
        c2 = _dossier.write_dossier_to_memory({"dossier": dict(src_inner)}, mem)
        counts["profile"] += c2.get("profile", 0)
        counts["derived"] += c2.get("derived", 0)
    return counts


async def run_onboarding_call(
    core: Any,
    dossier: Any,
    *,
    to: Optional[str] = None,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
    answers: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """INITIATE the outbound onboarding/gap-filling call for a built inhale dossier and close the loop.

    Plans the ranked gap-questions (clarify, over the OWNER dossier), dials the owner
    (CallChannel.send — mock records / live places a real Twilio call), runs OnboardingCallBrain over
    those questions, and writes the answers back so the dossier and first cards are re-aimed. Returns a
    structured, serializable summary. Mock-safe and deterministic; live is a one-flag flip
    (ANTICIPY_CHANNELS_MODE=live).
    """
    from ..channels.conversation_relay import OnboardingCallBrain

    questions = clarifying_questions_from_dossier(dossier, max_questions=max_questions)
    result: Dict[str, Any] = {
        "ok": True,
        "initiated": False,
        "source": "owner_inhale_dossier",
        "questions": [q.as_dict() for q in questions],
    }
    if not questions:
        result["reason"] = "no gaps — the inhale was complete; no clarifying call needed"
        return result

    to = (to or core._user_contact() or "").strip()
    live = core.call_channel._live()
    result["mode"] = "live" if live else "mock"
    result["to"] = to

    # 1) INITIATE — the DIAL. Mock records a mock send; live places a real Twilio call whose TwiML
    #    hands the two-way conversation to the /cr ConversationRelay socket.
    greeting = _greeting(questions, _dossier_identity(dossier).get("name"))
    call_rec = core.call_channel.send(to, greeting)
    result["initiated"] = bool(call_rec.get("sent"))
    result["call"] = call_rec
    with suppress(Exception):
        core.glassbox.log(
            "onboarding_call_initiated",
            {"to": to, "mock": call_rec.get("mock"), "questions": len(questions),
             "status": call_rec.get("status")},
        )

    # 2) LIVE: the real conversation + write-back happen over /cr as the owner speaks. Dial and hand
    #    off; never fabricate an answer here.
    if live and not answers:
        result["answers_pending"] = True
        result["note"] = "live call placed; answers arrive over the /cr ConversationRelay socket"
        return result

    # 3) MOCK (or supplied answers): run the warm OnboardingCallBrain over the ranked gap-questions,
    #    collect the answers, and write them back (the re-aim + first cards).
    brain = OnboardingCallBrain(core.gateway, glassbox=core.glassbox)
    supplied = answers if isinstance(answers, dict) else {}
    records: List[Dict[str, Any]] = []
    transcript: List[Dict[str, str]] = [{"speaker": "anticipy", "text": greeting}]
    for q in questions:
        transcript.append({"speaker": "anticipy", "text": q.question_text})
        spoken, value = _owner_reply(q, supplied)
        transcript.append({"speaker": "owner", "text": spoken})
        bridge = await brain.turn(spoken)   # OnboardingCallBrain reacts warmly to the answer
        transcript.append({"speaker": "anticipy", "text": bridge.reply})
        records.append({"field": q.field, "reason": q.reason, "question": q.question_text,
                        "answer": spoken, "value": value})

    simulated = not bool(supplied)   # supplied answers are real; the canned owner is simulated
    counts = write_call_answers_to_memory(core, dossier, records, simulated=simulated)
    result["answers"] = records
    result["transcript"] = transcript
    result["written"] = counts
    result["simulated_answers"] = simulated
    with suppress(Exception):
        core.glassbox.log(
            "onboarding_call_written",
            {"answers": len(records), "written": counts, "simulated": simulated},
        )
    return result
