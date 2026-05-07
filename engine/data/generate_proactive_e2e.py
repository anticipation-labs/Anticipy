"""
Generate /workspaces/Anticipy/engine/data/proactive_e2e.jsonl.

50 day-in-the-life conversation transcripts produced by Gemini 2.5 Flash at
temperature 0.9, one per pattern (with repeats so we hit 50). Every scenario
ships ground-truth labels (expected_intents, noise_should_NOT_act_on,
difficulty) so test_proactive_dataset.py can score the production
/api/engine/analyze pipeline.

Run:
    python /workspaces/Anticipy/engine/data/generate_proactive_e2e.py
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT / ".env.local"
OUT_FILE = Path(__file__).resolve().parent / "proactive_e2e.jsonl"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

GEMINI_KEY = os.environ["GOOGLE_API_KEY"]
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


# ---------------------------------------------------------------------------
# 25 distinct adversarial patterns; we sample 50 scenarios from these so the
# coverage requirement (one per pattern, plus extras) is satisfied. The first
# 20 are the explicit asks in the spec; the remainder are "breadth of real
# life" filler.
# ---------------------------------------------------------------------------


PATTERNS: list[dict] = [
    {
        "id": "morning_buried_intents",
        "difficulty": "medium",
        "description": (
            "Morning chat at home — 8-15 lines. 2 to 3 buried real intents "
            "(e.g. order something, schedule a thing, send a message). Mix "
            "with weather small-talk, breakfast pleasantries, half-thoughts."
        ),
    },
    {
        "id": "work_meeting_delegations",
        "difficulty": "hard",
        "description": (
            "Workday meeting, 4 speakers, 18-26 lines. Several DELEGATIONS "
            "to colleagues by name (Sarah will pull the report, Dan grabs "
            "the contract). Include 1-2 wearer actions buried in the same "
            "convo. The delegations must NOT be extracted — the wearer's "
            "agent is not Sarah's or Dan's agent."
        ),
    },
    {
        "id": "all_pleasantries_zero_intent",
        "difficulty": "easy",
        "description": (
            "Pure social chatter — bumping into a neighbour. 8-12 lines of "
            "weather, kid talk, 'we should grab coffee sometime'. ZERO "
            "expected intents. The system must extract nothing."
        ),
    },
    {
        "id": "retraction_same_convo",
        "difficulty": "hard",
        "description": (
            "Wearer states an intent then explicitly RETRACTS it within a "
            "few lines ('book the flight to Austin... actually no, not yet, "
            "let me check with Maya first'). Possibly include 1 OTHER intent "
            "that survives. The retracted item must be in noise."
        ),
    },
    {
        "id": "cafe_ambient_one_intent",
        "difficulty": "medium",
        "description": (
            "Wearer is in a noisy cafe overhearing fragments — barista "
            "calls, the next table, music lyrics. ONE buried real intent "
            "from the wearer ('oh I need to renew my passport'). Bystander "
            "speech must NOT be acted on."
        ),
    },
    {
        "id": "weather_conditional_retracted",
        "difficulty": "hard",
        "description": (
            "Wearer says 'if it rains tomorrow, cancel the picnic and book "
            "the bowling alley'. Then later confirms 'actually weather looks "
            "fine, never mind'. Net intents: zero on the conditional. "
            "Possibly 1 unrelated intent."
        ),
    },
    {
        "id": "evening_errands_list",
        "difficulty": "medium",
        "description": (
            "End-of-day brain dump 'okay before bed I need to...': 3-5 "
            "concrete errands (pay parking ticket, refill prescription, "
            "RSVP wedding, set 6am alarm). All clearly intents."
        ),
    },
    {
        "id": "phone_call_half_listening",
        "difficulty": "medium",
        "description": (
            "Wearer on the phone with mom while half watching TV. Mom "
            "rambles. Wearer drops 1-2 real intents into the convo "
            "('I'll order you that book' / 'I'll book your hotel'). Mom's "
            "complaints are not intents."
        ),
    },
    {
        "id": "multi_day_yesterday_reference",
        "difficulty": "hard",
        "description": (
            "Wearer references 'yesterday I said I'd email Karen — let me "
            "actually do that today'. The reference IS a real intent NOW. "
            "Other yesterday-references that are just storytelling are not."
        ),
    },
    {
        "id": "delegations_only_zero_wearer_actions",
        "difficulty": "hard",
        "description": (
            "Manager wearer assigning work to direct reports — every "
            "actionable verb is to someone else ('Mike, can you...', "
            "'Lisa will draft...'). Expected intents: 0. Noise: every "
            "delegation."
        ),
    },
    {
        "id": "urgent_low_importance_mixed",
        "difficulty": "medium",
        "description": (
            "Wearer states 'URGENT — call cardiologist back, today' "
            "alongside 'whenever — research a vacuum cleaner brand'. Both "
            "real intents but timing/priority differs. Capture both."
        ),
    },
    {
        "id": "ambiguous_referent",
        "difficulty": "hard",
        "description": (
            "Two friends discussing options. Wearer says 'yeah do that' or "
            "'sure, that one' with no clear referent visible in the next "
            "few lines. Either resolve to a concrete intent OR treat as "
            "ambient (label as noise if truly unresolvable)."
        ),
    },
    {
        "id": "negated_intent",
        "difficulty": "hard",
        "description": (
            "Wearer says 'don't book the flight yet, wait until Friday' or "
            "'no, do NOT email the team about this'. The system must NOT "
            "extract an action. May include 1 positive intent for contrast."
        ),
    },
    {
        "id": "third_person_reported",
        "difficulty": "hard",
        "description": (
            "Wearer narrating 'Dan said he'd handle the contract. Maya "
            "told me she'd get back to us by Tuesday.' These are reported "
            "third-party commitments — NOT wearer actions. Possibly 1 "
            "wearer follow-up ('I should ping Dan if I don't hear back by "
            "Wed')."
        ),
    },
    {
        "id": "family_dinner_multispeaker",
        "difficulty": "medium",
        "description": (
            "Family dinner — wearer (parent), spouse, two kids, 18-25 "
            "lines. Wearer agrees to several parental tasks (sign permission "
            "slip, buy soccer cleats, schedule pediatrician). Spouse's "
            "tasks are delegations. Kids' demands are noise unless wearer "
            "agrees."
        ),
    },
    {
        "id": "brainstorm_options_not_decisions",
        "difficulty": "brutal",
        "description": (
            "Two cofounders brainstorming 'we could try X, or maybe Y, "
            "or even Z'. NO decisions made. Every option is hypothetical. "
            "Expected intents: 0. Noise: every floated idea."
        ),
    },
    {
        "id": "ordering_food_casual",
        "difficulty": "easy",
        "description": (
            "Wearer ordering takeout with partner — discussing menu, "
            "ultimately deciding 'okay let's get the pad thai and a "
            "panang curry from Thai Spice'. ONE concrete intent: place the "
            "order. Earlier menu chatter is noise."
        ),
    },
    {
        "id": "medical_instruction_with_timing",
        "difficulty": "hard",
        "description": (
            "Doctor's voice giving the wearer instructions — take amoxicillin "
            "twice daily 7 days, follow-up appointment in 2 weeks, schedule "
            "blood draw before next visit. Concrete medical intents with "
            "specific timing. Doctor's small-talk is noise."
        ),
    },
    {
        "id": "financial_bills_payments",
        "difficulty": "medium",
        "description": (
            "Wearer reviewing bills 'electric is due Tuesday, gotta pay it. "
            "Cancel the gym membership — haven't been in months. Renew "
            "Netflix, that's fine.' 2-3 financial intents. Hypothetical "
            "comparisons ('we should look at switching insurance some day') "
            "are noise."
        ),
    },
    {
        "id": "travel_concrete_and_vague",
        "difficulty": "hard",
        "description": (
            "Wearer planning a trip — concrete dates and bookings ('book "
            "United IAH-LGA April 22 evening, hotel near Times Square') "
            "alongside vague mentions ('we should hit Italy someday', "
            "'Tokyo is on the bucket list'). Only the concrete bookings "
            "are intents."
        ),
    },
    # ---- breadth-of-real-life extras ---------------------------------------
    {
        "id": "kids_drop_off_pickup",
        "difficulty": "medium",
        "description": (
            "School-run morning. Mix of 'pick Kayla up at 3, dentist for "
            "Liam Friday 10am, sign the field-trip form'. Kids' chatter is "
            "noise. 2-3 wearer parental intents."
        ),
    },
    {
        "id": "gym_workout_chatter",
        "difficulty": "easy",
        "description": (
            "Wearer at the gym chatting with a friend about reps and "
            "weekend plans. Maybe ONE intent ('I should book a personal "
            "trainer session for Saturday'). Mostly small-talk noise."
        ),
    },
    {
        "id": "client_pitch_call",
        "difficulty": "hard",
        "description": (
            "Wearer running a sales call. Promises to send a proposal, "
            "schedule a follow-up, intro the prospect to a colleague. "
            "Client's questions/concerns are noise (those are notes, not "
            "actions)."
        ),
    },
    {
        "id": "uber_smalltalk_with_intent",
        "difficulty": "medium",
        "description": (
            "Wearer in an Uber chatting with the driver. Mostly weather and "
            "city talk. Wearer says to themselves or on speaker 'oh I need "
            "to text Mark I'll be 10 minutes late'. ONE intent."
        ),
    },
    {
        "id": "shopping_indecision",
        "difficulty": "medium",
        "description": (
            "Wearer at a store debating purchases — 'maybe I'll get the "
            "blue one... no the grey... actually let's not buy anything "
            "today'. Net intents: 0 (everything retracted). Possibly 1 "
            "unrelated intent ('email Lisa about Saturday')."
        ),
    },
]

# Pad to 50 by repeating each pattern roughly twice.
SCENARIO_PATTERNS: list[dict] = []
for i in range(50):
    p = PATTERNS[i % len(PATTERNS)].copy()
    SCENARIO_PATTERNS.append(p)


GENERATOR_SYSTEM = """You generate ONE realistic day-in-the-life test scenario for an AI \
wearable's proactive intent-extraction layer.

Hard requirements:
- transcript: array of 8-30 lines, each formatted "Speaker: text". Use real
  spoken English, with filler words ("uh", "like", "I mean"), interruptions,
  half-thoughts, and natural rhythm. Vary speaker names — "Wearer" or a
  first name for the wearer is fine. AT LEAST 2 distinct speakers in any
  multi-speaker scenario.
- expected_intents: array of one-line strings — what a perfect proactive
  layer SHOULD extract for the WEARER (not for other people). 0 to 5 items.
  ZERO is valid. Each item is a concrete actionable task ("book United IAH
  to LGA Apr 22 evening", "email Sarah re Friday review").
- noise_should_NOT_act_on: array of short descriptions of things in the
  transcript that LOOK actionable but are NOT wearer-tasks: delegations to
  named third parties, retracted statements, conditionals that resolved
  false, hypotheticals, ambient/bystander speech, pleasantries, third-party
  reported commitments. 0 to many.
- name: short snake_case scenario id, max 5 words.
- difficulty: one of "easy", "medium", "hard", "brutal".

Output: ONE JSON object only, no commentary, no code fences. Schema:
{
  "name": "<snake_case>",
  "difficulty": "<easy|medium|hard|brutal>",
  "transcript": ["Speaker: ...", ...],
  "expected_intents": ["<one-line>", ...],
  "noise_should_NOT_act_on": ["<short desc>", ...]
}

Rules of the world:
- The wearer's agent only acts on the WEARER's commitments. Things other
  people promise to do are NOT wearer-intents.
- Retractions in the same conversation cancel an intent — do NOT include
  it in expected_intents; DO include the retraction trigger in noise.
- Pleasantries like "we should grab lunch sometime" are NOT intents.
- Hypotheticals like "we could try X or Y" are NOT intents.
- Conditionals that explicitly resolved false ("if it rains" + "weather is
  fine") are NOT intents.
- Phrasing must NOT match prior generations literally — vary names, places,
  topics aggressively.
"""


GENERATOR_USER = """Generate ONE scenario.

Pattern: {pattern_id}
Difficulty target: {difficulty}
Pattern description:
{description}

Constraints for THIS scenario specifically:
- Use the difficulty target above as the scenario's difficulty field.
- Keep the transcript between 8 and 30 lines.
- Make it feel like a snippet of a REAL day — pick a fresh setting, fresh
  names, a fresh topic. Do NOT reuse names like Sarah/Dan/Maya across
  generations unnecessarily — invent diverse, plausible names.
- Be honest about expected_intents: include them only if a competent human
  would genuinely act on them after listening to the transcript.

Return JSON only.
"""


async def gemini_one(pattern: dict, *, attempt: int = 0) -> dict | None:
    body = {
        "system_instruction": {"parts": [{"text": GENERATOR_SYSTEM}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": GENERATOR_USER.format(
                            pattern_id=pattern["id"],
                            difficulty=pattern["difficulty"],
                            description=pattern["description"],
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            # Slight jitter so repeated patterns don't collapse.
            "temperature": 0.9 + random.uniform(-0.05, 0.05),
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
        },
    }
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(f"{GEMINI_URL}?key={GEMINI_KEY}", json=body)
            if r.status_code != 200:
                print(f"   gemini {r.status_code}: {r.text[:200]}", flush=True)
                return None
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            sc = json.loads(txt)
    except Exception as e:
        print(f"   gemini error: {type(e).__name__}: {e}", flush=True)
        return None

    # Validate shape
    required = ("name", "difficulty", "transcript", "expected_intents", "noise_should_NOT_act_on")
    if not all(k in sc for k in required):
        if attempt < 1:
            return await gemini_one(pattern, attempt=attempt + 1)
        return None
    if not isinstance(sc["transcript"], list) or not (8 <= len(sc["transcript"]) <= 30):
        if attempt < 1:
            return await gemini_one(pattern, attempt=attempt + 1)
    if not isinstance(sc["expected_intents"], list) or not isinstance(sc["noise_should_NOT_act_on"], list):
        return None
    sc["pattern_id"] = pattern["id"]
    return sc


async def generate_all(n: int = 50, concurrency: int = 6) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    seen_names: set[str] = set()
    results: list[dict] = []

    async def one(pattern: dict, idx: int) -> None:
        async with sem:
            sc = await gemini_one(pattern)
            if sc is None:
                print(f"  [{idx+1:2}/{n}] FAIL pattern={pattern['id']}", flush=True)
                return
            # Deduplicate names — append numeric suffix if collision
            base = sc["name"]
            name = base
            k = 2
            while name in seen_names:
                name = f"{base}_{k}"
                k += 1
            sc["name"] = name
            seen_names.add(name)
            results.append(sc)
            print(
                f"  [{idx+1:2}/{n}] {name:<48} "
                f"d={sc['difficulty']:<7} "
                f"lines={len(sc['transcript']):<2} "
                f"exp={len(sc['expected_intents'])} "
                f"noise={len(sc['noise_should_NOT_act_on'])}",
                flush=True,
            )

    tasks = [one(p, i) for i, p in enumerate(SCENARIO_PATTERNS[:n])]
    await asyncio.gather(*tasks)
    return results


async def main(n: int = 50) -> int:
    print(f"Generating {n} scenarios via Gemini 2.5 Flash → {OUT_FILE}", flush=True)
    scenarios = await generate_all(n=n)
    if not scenarios:
        print("FAIL: zero scenarios produced", flush=True)
        return 1

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w") as f:
        for sc in scenarios:
            f.write(json.dumps(sc, ensure_ascii=False) + "\n")

    # Distribution summary
    from collections import Counter
    diff = Counter(s["difficulty"] for s in scenarios)
    pat = Counter(s["pattern_id"] for s in scenarios)
    print(f"\nWrote {len(scenarios)} scenarios → {OUT_FILE}")
    print(f"  difficulty: {dict(diff)}")
    print(f"  patterns covered: {len(pat)} / {len(PATTERNS)}")
    return 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    raise SystemExit(asyncio.run(main(n=n)))
