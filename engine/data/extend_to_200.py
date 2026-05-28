"""Append ~55 NEW scenarios to engine/data/proactive_e2e.jsonl covering the
patterns the previous extends missed: sensitive medical/financial,
pronoun+temporal, negated intent, phone half-listening, foreign-language,
5+ intents in one breath, memory follow-up, ambient single buried intent,
multi-speaker family logistics, missing-slot variants, concrete browser-doable.

Each pattern carries category + expects_clarification. Gemini at temp 0.9
writes the actual transcripts and ground truth.

Run: python /tmp/extend_to_200.py
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from pathlib import Path

import httpx

ROOT = Path("/workspaces/Anticipy")
ENV_FILE = ROOT / ".env.local"
OUT_FILE = ROOT / "engine" / "data" / "proactive_e2e.jsonl"

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


PATTERNS: list[dict] = [
    # ---------- SENSITIVE MEDICAL (4) -----------------------------------------
    {
        "id": "sens_med_diabetes_a1c_results",
        "category": "sensitive_medical",
        "difficulty": "hard",
        "seed": "Wearer just got A1C lab results back. Says 'I need to call Dr. Patel about my A1C tomorrow' (concrete medical intent), 'I should ask about adjusting my metformin' (concrete medical question), 'and order test strips refill from CVS this week'. Three concrete sensitive medical intents that should be flagged importance=important / private.",
        "expects_clarification": False,
    },
    {
        "id": "sens_med_oncologist_referral",
        "category": "sensitive_medical",
        "difficulty": "brutal",
        "seed": "Wearer post-biopsy waiting for results. Says 'I need to schedule the oncologist consult for next week' (concrete) but also '...if the results come back bad I'll call my sister' (conditional, NOT actionable). Sensitive context, must be marked private.",
        "expects_clarification": False,
    },
    {
        "id": "sens_med_mental_health_med_change",
        "category": "sensitive_medical",
        "difficulty": "hard",
        "seed": "Wearer talking to spouse about meds — 'I want to ask Dr. Lee about lowering my Lexapro at next week's appointment' (concrete, sensitive mental health). 'Maybe try one of those meditation apps too' (vague). One concrete sensitive intent.",
        "expects_clarification": False,
    },
    {
        "id": "sens_med_kid_pediatrician_specifics",
        "category": "sensitive_medical",
        "difficulty": "hard",
        "seed": "Parent wearer says 'book the pediatrician for Maya' but never says WHY, doesn't say which week, doesn't pin a time. Sensitive (kid health) + missing slots — should clarify, treat as private.",
        "expects_clarification": True,
    },
    # ---------- SENSITIVE FINANCIAL (4) ---------------------------------------
    {
        "id": "sens_fin_401k_rebalance_now",
        "category": "sensitive_financial",
        "difficulty": "hard",
        "seed": "Wearer says 'I need to rebalance my 401k from 80/20 to 70/30 in Fidelity by Friday' (concrete financial). '...and look at the tax-loss harvesting opportunities' (concrete-ish). Money + private.",
        "expects_clarification": False,
    },
    {
        "id": "sens_fin_wire_50k_sale",
        "category": "sensitive_financial",
        "difficulty": "brutal",
        "seed": "Wearer says 'wire $50,000 to escrow tomorrow morning' — large irreversible financial action. The agent should flag this as importance=important and likely require an explicit confirm. Concrete intent but high-risk.",
        "expects_clarification": False,
    },
    {
        "id": "sens_fin_dispute_capital_one_charge",
        "category": "sensitive_financial",
        "difficulty": "hard",
        "seed": "Wearer reviewing a credit card statement — 'dispute the $238 charge from Acme Co on my Capital One card today', 'pay the rest of the bill by the 15th'. Two concrete financial intents.",
        "expects_clarification": False,
    },
    {
        "id": "sens_fin_taxes_no_specifics",
        "category": "sensitive_financial",
        "difficulty": "hard",
        "seed": "Wearer says 'I need to do my taxes' — no deadline named, no platform, no who's preparing them. Sensitive, missing slots — should clarify.",
        "expects_clarification": True,
    },
    # ---------- PRONOUN + TEMPORAL (4) ----------------------------------------
    {
        "id": "pronoun_temporal_call_them_back_free",
        "category": "pronoun_temporal",
        "difficulty": "brutal",
        "seed": "Wearer says 'call them back when they're free'. Both 'them' and 'when they're free' are unresolved. Earlier in transcript a friend Naomi mentioned wanting to talk later. Should clarify or hold.",
        "expects_clarification": True,
    },
    {
        "id": "pronoun_temporal_pick_up_when_done",
        "category": "pronoun_temporal",
        "difficulty": "hard",
        "seed": "Wearer says 'pick it up when she's done'. 'It' was discussed earlier (a printout, dry cleaning, kid). 'She' is also ambiguous. Temporal 'when done' is unobservable. Should clarify.",
        "expects_clarification": True,
    },
    {
        "id": "pronoun_temporal_text_him_after_meeting",
        "category": "pronoun_temporal",
        "difficulty": "hard",
        "seed": "Wearer says 'text him after the meeting tomorrow about the thing'. 'Him', 'the meeting', 'the thing' — all ambiguous. The meeting has not been pinned. Should clarify.",
        "expects_clarification": True,
    },
    {
        "id": "pronoun_temporal_resolved_via_context",
        "category": "pronoun_temporal",
        "difficulty": "hard",
        "seed": "Wearer is in a clearly-named meeting with Maya about the Q3 deck. Then says 'follow up with her tomorrow morning'. Pronoun resolves via context: her=Maya, follow up about Q3 deck. Temporal: tomorrow morning. Concrete after resolution. Should NOT need clarification.",
        "expects_clarification": False,
    },
    # ---------- NEGATED INTENT (4) --------------------------------------------
    {
        "id": "negated_dont_book_yet",
        "category": "negated",
        "difficulty": "hard",
        "seed": "Wearer says 'don't book it yet, let me think about it'. Refers to a specific hotel or flight discussed earlier. Net intent: ZERO (the negation explicitly defers).",
        "expects_clarification": False,
    },
    {
        "id": "negated_dont_send_email_yet",
        "category": "negated",
        "difficulty": "hard",
        "seed": "Wearer says 'do NOT send that email to Lisa yet, I want to revise it' followed by '...I'll finalize tonight and we can send tomorrow'. Net intent: revise + send tomorrow (one wearer task), negation cancels the immediate send.",
        "expects_clarification": False,
    },
    {
        "id": "negated_skip_the_meeting",
        "category": "negated",
        "difficulty": "medium",
        "seed": "Wearer says 'I'm gonna skip Friday's standup' — negation form expressing a decision NOT to attend. Could be an intent to decline/cancel the calendar event. Or could just be a stated decision. One concrete intent: decline/RSVP-no the standup.",
        "expects_clarification": False,
    },
    {
        "id": "negated_no_more_doordash",
        "category": "negated",
        "difficulty": "medium",
        "seed": "Wearer venting 'I am NOT ordering DoorDash again this week'. This is a self-promise about what they will NOT do. NOT an actionable intent for the assistant. Net: zero intents.",
        "expects_clarification": False,
    },
    # ---------- PHONE HALF-LISTENING (4) --------------------------------------
    {
        "id": "phone_half_listen_voicemail_doctor",
        "category": "phone_half_listening",
        "difficulty": "hard",
        "seed": "Wearer is on a call (one side audible) with their doctor's voicemail system pressing options. Faintly hears 'press 2 for refills'. The wearer also mutters to themselves 'oh and I need to email Drew about Friday'. Voicemail menu = noise. Email Drew = real intent.",
        "expects_clarification": False,
    },
    {
        "id": "phone_half_listen_meeting_drop_in",
        "category": "phone_half_listening",
        "difficulty": "hard",
        "seed": "Wearer on speakerphone with a coworker, occasionally going 'mmhmm yeah'. Coworker assigns Tessa a follow-up (NOT wearer's task). Wearer drops in 'I'll write up the postmortem by tomorrow EOD' — that IS a wearer commitment. One concrete intent.",
        "expects_clarification": False,
    },
    {
        "id": "phone_half_listen_robocall_buried",
        "category": "phone_half_listening",
        "difficulty": "hard",
        "seed": "Wearer hears a robocall about extended warranty in the background, mostly ignores. Mid-call wearer says to spouse 'remind me to renew my driver's license tomorrow afternoon'. One wearer intent buried in robocall noise.",
        "expects_clarification": False,
    },
    {
        "id": "phone_half_listen_zero_intent",
        "category": "phone_half_listening",
        "difficulty": "easy",
        "seed": "Wearer half-listening to a tax-prep ad on the phone while putting away dishes; they don't engage, no commitments are made. Pure ambient phone audio + zero wearer intent.",
        "expects_clarification": False,
    },
    # ---------- AMBIENT + BURIED SINGLE INTENT (4) ----------------------------
    {
        "id": "ambient_buried_one_dentist",
        "category": "ambient_buried",
        "difficulty": "hard",
        "seed": "Loud subway car: announcements, a busker, two strangers debating sports loudly. Wearer (silent for most), at the end mutters 'shoot, I need to schedule the dentist for next Wednesday'. One concrete intent buried in ambient.",
        "expects_clarification": False,
    },
    {
        "id": "ambient_buried_one_milk_run",
        "category": "ambient_buried",
        "difficulty": "medium",
        "seed": "Crowded grocery aisle, people chattering, intercom ('cleanup on aisle 7'). Wearer to themselves 'milk, eggs... oh and let me grab a card for John's birthday today'. One wearer intent (buy card).",
        "expects_clarification": False,
    },
    {
        "id": "ambient_buried_one_email_recruiter",
        "category": "ambient_buried",
        "difficulty": "hard",
        "seed": "Coffee shop, espresso machine, baristas calling names, two people gossiping about TV at next table. Wearer texting on laptop; mutters aloud 'I'll email the recruiter back tonight about the Friday slot'. One concrete wearer intent.",
        "expects_clarification": False,
    },
    {
        "id": "ambient_buried_one_hotel_book",
        "category": "ambient_buried",
        "difficulty": "hard",
        "seed": "Airport gate area — gate agent announcements, kid crying, news on TV. Wearer to spouse 'I'll book the Sheraton in Denver for May 22-25 tonight from the laptop'. ONE concrete wearer intent buried in airport noise.",
        "expects_clarification": False,
    },
    # ---------- FOREIGN-LANGUAGE PLACE NAMES (3) ------------------------------
    {
        "id": "foreign_lang_kyoto_ryokan",
        "category": "foreign_language",
        "difficulty": "hard",
        "seed": "Wearer planning Japan trip says 'book the Tawaraya ryokan in Kyoto for May 18-20', 'find a kaiseki dinner spot near Kiyomizu-dera', 'reserve a JR Pass for two weeks'. Three concrete intents with Japanese place/term names that the LLM must preserve.",
        "expects_clarification": False,
    },
    {
        "id": "foreign_lang_oktoberfest_munich",
        "category": "foreign_language",
        "difficulty": "hard",
        "seed": "Wearer planning Munich Oktoberfest — 'reserve a Tisch at Hofbräu-Festzelt for opening Saturday', 'book the Hilton München Park hotel', 'figure out S-Bahn from Flughafen München'. German place names, three intents.",
        "expects_clarification": False,
    },
    {
        "id": "foreign_lang_são_paulo_paris_routing",
        "category": "foreign_language",
        "difficulty": "hard",
        "seed": "Wearer says 'book the flight São Paulo to Charles de Gaulle for next Thursday' (one intent with foreign place names), 'find a hotel in Le Marais' (concrete with French neighborhood), 'and lunch reservation at L'Ami Louis Friday' (concrete French restaurant). Three intents.",
        "expects_clarification": False,
    },
    # ---------- 5+ INTENTS IN ONE BREATH (4) ----------------------------------
    {
        "id": "many_intents_morning_rapid_fire",
        "category": "many_intents",
        "difficulty": "brutal",
        "seed": "Wearer on a roll first thing in the morning: 'okay, email Sarah about Q3 budget, ping Tom on the deck draft, schedule the dentist for next Wednesday, order more coffee filters from Amazon, RSVP to Maya's birthday, pick up dry cleaning today, and call mom back tonight'. SEVEN concrete wearer intents in one breath.",
        "expects_clarification": False,
    },
    {
        "id": "many_intents_grocery_dump",
        "category": "many_intents",
        "difficulty": "hard",
        "seed": "Wearer making a grocery list out loud quickly: 'eggs, milk, bread, two avocados, salmon for tomorrow night, lemons, basil, parmesan, sparkling water, dog food'. TEN items as one combined shopping intent (or 1 'add to grocery list' intent with 10 items — either reading is acceptable, but 10 distinct intents is wrong).",
        "expects_clarification": False,
    },
    {
        "id": "many_intents_friday_wrapup",
        "category": "many_intents",
        "difficulty": "hard",
        "seed": "End of week wrap-up — wearer says 'before I sign off: send the invoice, schedule the Monday standup, file expense report, send the contract redlines to legal, ping Olivia about the deck, and book my Tuesday 1:1 with the VP'. SIX concrete wearer intents in one sentence.",
        "expects_clarification": False,
    },
    {
        "id": "many_intents_house_chores",
        "category": "many_intents",
        "difficulty": "hard",
        "seed": "Wearer at home Saturday morning: 'okay, run the dishwasher, drop trash, vacuum living room, water plants, fix the squeaky door, clean out the fridge, and start a load of laundry'. SEVEN domestic intents (some are immediate self-tasks rather than agent-doable, but valid wearer commitments).",
        "expects_clarification": False,
    },
    # ---------- MEMORY FOLLOW-UP (4) ------------------------------------------
    {
        "id": "memory_followup_did_i_email",
        "category": "memory_followup",
        "difficulty": "hard",
        "seed": "Wearer asks self / spouse 'did I email Priya the contract yet?' — a STATUS query, not a new intent. The agent should respond with check-history rather than create a new email-Priya intent. Net intent: ZERO new wearer tasks.",
        "expects_clarification": False,
    },
    {
        "id": "memory_followup_pull_forward",
        "category": "memory_followup",
        "difficulty": "hard",
        "seed": "Wearer says 'I never got around to that LinkedIn post — let me draft it now'. References a stale commitment AND creates a fresh now-task. Net intent: ONE — draft LinkedIn post now.",
        "expects_clarification": False,
    },
    {
        "id": "memory_followup_remind_me_did_i",
        "category": "memory_followup",
        "difficulty": "hard",
        "seed": "Wearer says 'remind me, did I confirm the appointment with the contractor for next week?' Pure question, no new task. Net intent: ZERO. (Could trigger a status check, but should not create an intent.)",
        "expects_clarification": False,
    },
    {
        "id": "memory_followup_yes_i_did_it",
        "category": "memory_followup",
        "difficulty": "easy",
        "seed": "Wearer talking to spouse: 'Yeah I sent the rent check yesterday, all good'. Self-confirmation about a past action. Net intent: ZERO new tasks.",
        "expects_clarification": False,
    },
    # ---------- MULTI-SPEAKER FAMILY LOGISTICS (4) ----------------------------
    {
        "id": "msf_logistics_carpool_chaos",
        "category": "multi_speaker_family",
        "difficulty": "hard",
        "seed": "Saturday family scene — three speakers: wearer, spouse, kid. Spouse asks 'can you take Maya to soccer at 9?', wearer says 'sure, AND I'll grab gas on the way back'. Kid demands snacks. Wearer adds 'and remind me to call your mom about Sunday dinner'. Mixed: spouse delegation TO wearer (NOT a self-task — accepted), wearer self-tasks (gas, call mom). 2-3 wearer intents.",
        "expects_clarification": False,
    },
    {
        "id": "msf_logistics_school_pickup_split",
        "category": "multi_speaker_family",
        "difficulty": "hard",
        "seed": "Wearer + spouse coordinating school pickup. Wearer says 'I'll grab Liam at 3, can you handle Emma's dance at 5?' (spouse delegation, NOT wearer task), 'and I'll order pizza for tonight at 6' (wearer task). One wearer commitment.",
        "expects_clarification": False,
    },
    {
        "id": "msf_logistics_grandparents_visit",
        "category": "multi_speaker_family",
        "difficulty": "medium",
        "seed": "Wearer planning grandparents' weekend visit. Spouse says 'I'll prep the guest room' (delegation, NOT wearer). Wearer says 'I'll book their flight from Tampa for Friday afternoon, and order groceries for Saturday brunch'. TWO wearer intents.",
        "expects_clarification": False,
    },
    {
        "id": "msf_logistics_birthday_planning_two_kids",
        "category": "multi_speaker_family",
        "difficulty": "hard",
        "seed": "Two-kid birthday planning. Spouse says 'I'll do the cake'. Older kid says 'I want a piñata'. Wearer says 'I'll book the park pavilion for Saturday May 17th, and send the evite to all the parents tonight'. TWO wearer intents.",
        "expects_clarification": False,
    },
    # ---------- MISSING SLOTS — NEW VARIANTS (5) ------------------------------
    {
        "id": "missing_slot_text_partner_no_what",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'text my partner about that thing' — both content and platform unspecified. Should clarify.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slot_call_doctor_no_who",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I need to call the doctor' — multiple doctors possible, no specific clinic, no time. Should clarify.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slot_buy_a_gift",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I need to buy a gift'. Recipient missing, occasion missing, budget missing, deadline missing. Should clarify.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slot_plan_the_trip",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I need to plan the trip'. No destination, no dates, no party size, no budget. Should clarify all of those.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slot_post_on_social",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I should post about this on social'. No content, no platform (Twitter? LinkedIn? Instagram?), no media. Should clarify.",
        "expects_clarification": True,
    },
    # ---------- CONCRETE BROWSER-DOABLE (5) -----------------------------------
    {
        "id": "browser_doable_search_python_release",
        "category": "browser_doable",
        "difficulty": "easy",
        "seed": "Wearer says 'search for Python 3.13 release notes on python.org and tell me the headline feature'. Concrete, full slots: site=python.org, query=3.13 release notes, target=headline feature.",
        "expects_clarification": False,
    },
    {
        "id": "browser_doable_compare_specs_iphone",
        "category": "browser_doable",
        "difficulty": "medium",
        "seed": "Wearer says 'on apple.com, compare iPhone 16 Pro vs iPhone 16 Pro Max specs and tell me the camera differences'. Site, products, target attribute all specified.",
        "expects_clarification": False,
    },
    {
        "id": "browser_doable_extract_top_repo",
        "category": "browser_doable",
        "difficulty": "easy",
        "seed": "Wearer says 'go to github.com trending today and tell me the #1 repo'. Concrete, full slots: site=github trending, target=top repo.",
        "expects_clarification": False,
    },
    {
        "id": "browser_doable_amazon_book_lookup",
        "category": "browser_doable",
        "difficulty": "easy",
        "seed": "Wearer says 'on Amazon, look up Project Hail Mary by Andy Weir paperback price'. Site, query, attribute all specified.",
        "expects_clarification": False,
    },
    {
        "id": "browser_doable_imdb_rating",
        "category": "browser_doable",
        "difficulty": "easy",
        "seed": "Wearer says 'check the IMDB rating for Dune Part Two'. Site=IMDB, query=Dune Part Two, target=rating.",
        "expects_clarification": False,
    },
    # ---------- ZERO-INTENT EDGE CASES (3) ------------------------------------
    {
        "id": "zero_pure_singing_humming",
        "category": "zero_intent",
        "difficulty": "easy",
        "seed": "Wearer alone humming a tune, occasionally singing snippets, sighing. Truly ZERO actions, ZERO commitments.",
        "expects_clarification": False,
    },
    {
        "id": "zero_only_questions_asked",
        "category": "zero_intent",
        "difficulty": "medium",
        "seed": "Wearer asking spouse a series of clarifying questions about their day — 'how was the meeting?', 'did Tessa call?', 'what's for dinner?'. Pure question-asking, no commitments. ZERO intents.",
        "expects_clarification": False,
    },
    {
        "id": "zero_pure_storytelling",
        "category": "zero_intent",
        "difficulty": "medium",
        "seed": "Wearer telling a long story to a friend about something funny that happened at work today. Pure narrative, no commitments / next steps. ZERO intents.",
        "expects_clarification": False,
    },
]


GENERATOR_SYSTEM = """You generate ONE realistic test scenario for an AI \
wearable's proactive intent-extraction layer.

Hard requirements:
- transcript: array of 6-30 lines, each formatted "Speaker: text". Use real
  spoken English, fillers, interruptions, half-thoughts. AT LEAST 1 speaker.
  For multi-speaker scenes use 2+ distinct names.
- expected_intents: array of one-line strings — what a perfect proactive
  layer SHOULD extract for the WEARER. 0 to 7 items. ZERO is valid.
- noise_should_NOT_act_on: array of short strings describing transcript
  items that LOOK actionable but are NOT wearer-tasks (delegations,
  retracted statements, conditionals that resolved false, hypotheticals,
  ambient/bystander speech, pleasantries, third-party reported commitments).
- name: short snake_case scenario id, max 6 words.
- difficulty: one of "easy", "medium", "hard", "brutal".
- expected_clarification (ONLY when expects_clarification=True): one-line
  natural-language question the agent SHOULD ask the wearer to resolve
  missing slots, e.g. "Where from, where to, and what dates?"

DO NOT output `required_slots` or any structured slot schema — only the
clarification question, if appropriate.

Output: ONE JSON object only, no commentary, no code fences. Schema:
{
  "name": "<snake_case>",
  "difficulty": "<easy|medium|hard|brutal>",
  "transcript": ["Speaker: ...", ...],
  "expected_intents": ["<one-line>", ...],
  "noise_should_NOT_act_on": ["<short desc>", ...],
  "expected_clarification": "<one-line question>"  // only if expects_clarification=True
}

Rules of the world:
- The wearer's agent only acts on the WEARER's commitments.
- Retractions in same conversation cancel an intent.
- Pleasantries ("we should grab lunch sometime") are NOT intents even if
  they name specific places.
- Conditionals not yet resolved → don't auto-extract; surface for
  clarification or watch.
- Specific-place + vague-time = pleasantry, NOT actionable.
- Negations ("don't book it yet") cancel the embedded intent.
- Memory follow-up questions ("did I do X yet?") are NOT new intents.
- Phrasing must NOT match prior generations literally.
"""


GENERATOR_USER = """Generate ONE scenario.

Pattern: {pattern_id}
Category: {category}
Difficulty target: {difficulty}
expects_clarification: {expects_clarification}

Seed (interpret loosely — bring it to life with realistic dialog):
{seed}

Constraints:
- Use the difficulty target above as the scenario's difficulty field.
- Keep transcript between 6 and 30 lines.
- Make it feel like a real moment — fresh setting, fresh names, fresh topic.
- Be honest about expected_intents: include only what a competent human
  would genuinely act on after listening. ZERO is valid and often correct.
- If expects_clarification is True, the scenario MUST have at least one
  intent that's underspecified, and you MUST include "expected_clarification"
  asking the user to fill the missing slots in plain English.
- If expects_clarification is False, OMIT the expected_clarification field.

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
                            category=pattern["category"],
                            difficulty=pattern["difficulty"],
                            seed=pattern["seed"],
                            expects_clarification=pattern.get("expects_clarification", False),
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
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
                if attempt < 2:
                    await asyncio.sleep(2 * (attempt + 1))
                    return await gemini_one(pattern, attempt=attempt + 1)
                return None
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            sc = json.loads(txt)
    except Exception as e:
        print(f"   gemini error: {type(e).__name__}: {e}", flush=True)
        if attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))
            return await gemini_one(pattern, attempt=attempt + 1)
        return None

    required = ("name", "difficulty", "transcript", "expected_intents", "noise_should_NOT_act_on")
    if not all(k in sc for k in required):
        if attempt < 2:
            return await gemini_one(pattern, attempt=attempt + 1)
        return None
    if not isinstance(sc["transcript"], list) or len(sc["transcript"]) < 4:
        if attempt < 2:
            return await gemini_one(pattern, attempt=attempt + 1)
    if not isinstance(sc["expected_intents"], list) or not isinstance(sc["noise_should_NOT_act_on"], list):
        return None

    if pattern.get("expects_clarification") and "expected_clarification" not in sc:
        if attempt < 2:
            return await gemini_one(pattern, attempt=attempt + 1)

    sc["pattern_id"] = pattern["id"]
    sc["category"] = pattern["category"]
    return sc


async def main() -> int:
    seen_names: set[str] = set()
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            for line in f:
                if line.strip():
                    try:
                        seen_names.add(json.loads(line)["name"])
                    except Exception:
                        pass
    print(f"Existing scenarios: {len(seen_names)}. Generating {len(PATTERNS)} new ones.", flush=True)

    sem = asyncio.Semaphore(8)
    results: list[dict] = []
    fail_patterns: list[str] = []

    async def one(pattern: dict, idx: int) -> None:
        async with sem:
            sc = await gemini_one(pattern)
            if sc is None:
                fail_patterns.append(pattern["id"])
                print(f"  [{idx + 1:3}/{len(PATTERNS)}] FAIL pattern={pattern['id']}", flush=True)
                return
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
                f"  [{idx + 1:3}/{len(PATTERNS)}] {name:<48} "
                f"d={sc['difficulty']:<6} "
                f"lines={len(sc['transcript']):<2} "
                f"exp={len(sc['expected_intents'])} "
                f"noise={len(sc['noise_should_NOT_act_on'])} "
                f"clar={'Y' if 'expected_clarification' in sc else '-'}",
                flush=True,
            )

    tasks = [one(p, i) for i, p in enumerate(PATTERNS)]
    await asyncio.gather(*tasks)

    with OUT_FILE.open("a") as f:
        for sc in results:
            f.write(json.dumps(sc, ensure_ascii=False) + "\n")

    from collections import Counter
    cats = Counter(s["category"] for s in results)
    diffs = Counter(s["difficulty"] for s in results)
    print(f"\nAppended {len(results)} scenarios -> {OUT_FILE}")
    print(f"  category counts: {dict(cats)}")
    print(f"  difficulty counts: {dict(diffs)}")
    if fail_patterns:
        print(f"  failed patterns: {fail_patterns}")

    total = 0
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            total = sum(1 for line in f if line.strip())
    print(f"  TOTAL scenarios in file: {total}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
