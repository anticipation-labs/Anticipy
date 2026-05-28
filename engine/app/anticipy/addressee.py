"""Addressee and authority resolution. New build code, not preserved
cascade, so the prompt is owned here.

Determines, for a diarized transcript with exactly one WEARER, whether
the salient content is:

  agent_direct        the WEARER directly commands the agent
  wearer_task_implied the WEARER states an actionable task for themselves
  boss_to_wearer      someone with authority over the WEARER instructs
                      the WEARER to do something and the WEARER does not
                      refuse: that instruction is itself a WEARER relevant
                      actionable task ("if your boss tells you to do
                      something you need to hear the boss")
  other_human         a task that is plainly directed at another human,
                      not the WEARER and not the agent
  ambient             ordinary conversation, no task for the agent

The WEARER is the authority whose intent carries direct action weight.
Other speakers generate context or, in the boss case, a WEARER relevant
task. The resolver also extracts the EFFECTIVE actionable task text
(which may be a sentence the boss spoke, not the WEARER), flags genuine
low commitment hedging using the build's strict definition, and flags a
reference that cannot be resolved without memory or the profile.

A direct user command (InboundMessage.source == "direct") bypasses this
resolver entirely: the user deliberately addressed the agent, so it is
the highest authority lowest uncertainty path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from app.anticipy import platform_adapter

_SYSTEM = """\
You resolve who the single most salient potential task in a short
diarized transcript is for, and whether it carries action weight for the
WEARER of an ambient assistant. Exactly one speaker is labelled WEARER.

Return STRICT JSON only:
{
  "addressee": "agent_direct" | "wearer_task_implied" | "boss_to_wearer" | "other_human" | "ambient",
  "authority_ok": true | false,
  "effective_task_text": "<one clean imperative, or "">",
  "genuinely_hedged": true | false,
  "reference_unresolved": true | false,
  "confidence": 0.0,
  "reason": "<short>"
}

Decide the addressee with this ordered procedure. Stop at the first that
applies:

0. SARCASM, IRONY, OR NEGATION FIRST. If the WEARER's task shaped line
   is sarcastic, ironic, or negated, the real intent is the opposite of
   the literal words, so there is NO genuine task -> "ambient". Tells:
   an undesirable action paired with fake enthusiasm or a contradicting
   clause ("set the thermostat to 85, I love sweating indoors";
   "order the extra spicy wings, I love heartburn"; "remind me to
   volunteer for the weekend shift, I have nothing better to do"; "let's
   DEFINITELY book the most expensive place"; "what could possibly go
   wrong"; "great, another Saturday at the DMV"), or an explicit
   retraction ("never mind", "forget it", "actually no"). When in doubt
   between a literal command and sarcasm given a contradicting or
   exaggerated cue, treat it as sarcasm -> ambient. Acting on a
   sarcastic command is a severe failure.

1. No concrete actionable task anywhere -> "ambient".

2. A non WEARER speaker (a present human) takes or offers ownership of
   the task ("I'll do it", "I can do that", "I can remind you",
   "already on it", "I got it", "let me handle that"), OR a non WEARER
   speaker responds substantively to a WEARER request (an answer, a
   suggestion, an opinion, naming an option, discussing it) -> a present
   human is handling or was the intended target -> "other_human". This
   holds even for device style asks like "set a timer". Example: WEARER
   "find a good Thai place nearby", FRIEND "there's that one on Main
   Street" is a human conversation -> other_human.

3. Someone with authority over the WEARER (boss, manager, directing
   client) tells the WEARER to do something AND the WEARER explicitly
   accepts or acknowledges it ("okay", "sure", "on it", "got it", "will
   do", "I'll do it", "I'll have it ready"). Acceptance is REQUIRED. A
   non committal reply ("that's tight", "the numbers look off", a
   question, a complaint, silence, changing the subject) is NOT
   acceptance: in that case the task was not confirmed as the WEARER's,
   so return "other_human" with low confidence, never boss_to_wearer.
   When acceptance is present -> "boss_to_wearer".

4. In a multi speaker transcript, a "can you / could you / would you"
   that is not unmistakably addressed to a named assistant could have
   been meant for a present human -> "other_human". Only "agent_direct"
   here if the WEARER explicitly names or unmistakably invokes the
   assistant.

5. The WEARER issues a command clearly meant for an assistant ->
   "agent_direct".

6. The WEARER states their own concrete actionable task, not addressed
   to anyone in particular -> "wearer_task_implied".

Never resolve genuine ambiguity by assuming the task is for the
assistant. Acting silently on something meant for a present human is the
exact failure to avoid: when unsure, prefer "other_human".

authority_ok is true ONLY for agent_direct, wearer_task_implied,
boss_to_wearer. False for other_human and ambient.

effective_task_text MUST be one clean standalone imperative of the
action. No speaker names, no quotes, no acknowledgments ("okay I'll do
that", "sure", "got it"), no "I need you to" framing, no future or past
recap framing ("I'll do it tomorrow"). Rewrite to a direct command.
Boss "I need you to call the client about the contract changes" + WEARER
"okay I'll do that tomorrow" -> "Call the client about the contract
changes". No concrete action -> "".

genuinely_hedged is true ONLY for low commitment language: "maybe",
"sometime", "we could", "we should maybe", "I might", "at some point",
hypotheticals, AND tentative musing about a possible intention ("I was
thinking of", "thinking about", "I might just", "maybe I'll",
"considering", "I could probably"). FALSE for a committed task even if
first person ("I need to email Sarah the deck before end of day" is
committed, NOT hedged; "draft the report by Friday" is committed).

reference_unresolved is true only if the task points at something ("the
usual", "that place", "them") unactionable without a prior memory or
profile lookup not present in the transcript.
"""


@dataclass(frozen=True, slots=True)
class AddresseeResult:
    addressee: str
    authority_ok: bool
    effective_task_text: str
    genuinely_hedged: bool
    reference_unresolved: bool
    confidence: float
    reason: str


_VALID = {"agent_direct", "wearer_task_implied", "boss_to_wearer", "other_human", "ambient"}


def _safe_default(reason: str) -> AddresseeResult:
    # Safe direction on any failure: no authority, no task. The decision
    # policy then yields IGNORE or ASK, never a wrong ACT.
    return AddresseeResult("ambient", False, "", False, False, 0.0, reason)


async def resolve(transcript: list[dict], wearer_label: str = "WEARER") -> AddresseeResult:
    import asyncio

    lines = "\n".join(
        f"{ln.get('speaker_id', 'S?')}: {ln.get('text', '')}" for ln in transcript
    )
    user = (
        f"TRANSCRIPT (one speaker is {wearer_label}):\n{lines}\n\n"
        "Return the JSON object now."
    )
    res = await asyncio.to_thread(
        platform_adapter.model_call, _SYSTEM, user, 400, 0.0, False
    )

    def _obj(text: str):
        a, b = text.find("{"), text.rfind("}")
        if a == -1 or b == -1 or b <= a:
            return None
        try:
            return json.loads(text[a : b + 1])
        except Exception:
            return None

    p = _obj(res.content) if res.ok else None
    if p is None:
        # One stricter reparse before safe defaulting (section 8: the
        # decider model degenerates to word salad on some prompts; the
        # safe default here is ambient which wrongly drops a real boss
        # task, so recover the recoverable transient first).
        stricter = (
            user
            + "\n\nReturn ONLY the single JSON object, nothing else. Start "
            "with { and end with }."
        )
        res2 = await asyncio.to_thread(
            platform_adapter.model_call, _SYSTEM, stricter, 400, 0.0, False
        )
        p = _obj(res2.content) if res2.ok else None
    if p is None:
        return _safe_default("addressee_unparseable_after_reparse")
    addressee = p.get("addressee")
    if addressee not in _VALID:
        return _safe_default(f"addressee_invalid:{addressee!r}")
    return AddresseeResult(
        addressee=addressee,
        authority_ok=bool(p.get("authority_ok")) and addressee in {"agent_direct", "wearer_task_implied", "boss_to_wearer"},
        effective_task_text=str(p.get("effective_task_text", ""))[:600],
        genuinely_hedged=bool(p.get("genuinely_hedged")),
        reference_unresolved=bool(p.get("reference_unresolved")),
        confidence=float(p.get("confidence", 0.0) or 0.0),
        reason=str(p.get("reason", ""))[:240],
    )
