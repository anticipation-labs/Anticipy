"""Onboarding intake. The warm start that fixes cold start.

A scripted structured interview (delivered in app text now, over the two
way text channel and as a real phone call later, SAME structured output)
produces the section 5 UserProfile. The core has consumed the profile
seam since P2, so wiring the real profile in here changes nothing in the
core: a freshly onboarded user is no longer an empty memory agent
guessing, it can resolve "the boss" and "us" on day one.

The interview script is fixed. A single model call maps the user's free
form answers to the structured profile. The profile is persisted per
user through the isolation scoped spine client, never cross tenant.
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from app.anticipy import platform_adapter, spine
from app.anticipy.seams import UserProfile

INTERVIEW_SCRIPT = [
    "What is your name and your role or title?",
    "In one sentence, what do you do day to day?",
    "What time zone are you in and what are your usual working hours?",
    "Who are the most important people around you and how do they relate "
    "to you (your boss or skip level, your reports, key clients, your "
    "partner)? Name who 'the boss' and 'us' refer to.",
    "Which three to five tools or systems do you live in every day "
    "(email, calendar, the rest)?",
    "What do you want Anticipy to do for you, and what is strictly off "
    "limits, the do not touch list?",
    "How should I reach you for non critical vs critical things, and "
    "what are your quiet hours?",
]

_EXTRACT_SYS = """\
You convert a completed onboarding interview into a strict structured
profile. Return STRICT JSON only with EXACTLY these keys:
{
 "name": "", "role_title": "", "what_they_do": "", "timezone": "UTC",
 "working_hours": "", "people": {"<relation>": "<who>"},
 "critical_software": {"<tool>": true},
 "mandate": "", "do_not_touch": ["..."],
 "comms_prefs": {"non_critical": "", "critical": ""}, "quiet_hours": ""
}
people MUST resolve the anchors the user gave for "the boss" and "us"
when stated. Do not invent facts the interview did not contain; leave a
field empty rather than guessing. No prose, no fences.
"""


async def _extract(intake_text: str) -> dict:
    res = await asyncio.to_thread(
        platform_adapter.model_call, _EXTRACT_SYS,
        f"COMPLETED INTERVIEW:\n{intake_text}\n\nReturn the JSON now.",
        700, 0.0, False,
    )
    if not res.ok:
        return {}
    s = res.content
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1 or b <= a:
        return {}
    try:
        return json.loads(s[a : b + 1])
    except Exception:
        return {}


def _intake_to_text(case_transcript: list[dict]) -> str:
    """A simulated intake conversation is a diarized transcript of the
    scripted interview. Flatten it to the completed interview text the
    extractor reads.
    """
    return "\n".join(
        f"{ln.get('speaker_id', '?')}: {ln.get('text', '')}" for ln in case_transcript
    )


async def run_intake(case_transcript: list[dict], user_id: str) -> UserProfile:
    parsed = await _extract(_intake_to_text(case_transcript))
    prof = UserProfile(
        user_id=user_id,
        name=str(parsed.get("name", "")),
        role_title=str(parsed.get("role_title", "")),
        what_they_do=str(parsed.get("what_they_do", "")),
        timezone=str(parsed.get("timezone", "UTC")) or "UTC",
        working_hours=str(parsed.get("working_hours", "")),
        people={str(k): str(v) for k, v in (parsed.get("people") or {}).items()},
        critical_software={str(k): bool(v) for k, v in (parsed.get("critical_software") or {}).items()},
        mandate=str(parsed.get("mandate", "")),
        do_not_touch=[str(x) for x in (parsed.get("do_not_touch") or [])],
        comms_prefs={str(k): str(v) for k, v in (parsed.get("comms_prefs") or {}).items()},
        quiet_hours=str(parsed.get("quiet_hours", "")),
        autonomy_level=0.92,
        days_since_onboard=0,
        trajectory_confidence=0.0,
    )
    # persist per user through the isolation scoped client (durable,
    # never cross tenant)
    try:
        spine.scoped_client(user_id).put("user_profile", "profile", {
            "name": prof.name, "role_title": prof.role_title,
            "what_they_do": prof.what_they_do, "people": prof.people,
            "critical_software": prof.critical_software, "mandate": prof.mandate,
            "do_not_touch": prof.do_not_touch, "comms_prefs": prof.comms_prefs,
        })
    except Exception:
        pass
    return prof


def profile_is_well_populated(prof: UserProfile) -> bool:
    """The P7 onboarding pass condition: identity, what they do, the
    people anchors, and the mandate were captured.
    """
    return bool(
        prof.name and prof.role_title and prof.what_they_do
        and prof.people and prof.mandate and prof.is_populated()
    )
