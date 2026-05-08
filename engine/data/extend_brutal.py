"""
Append "brutal" adversarial scenarios to engine/data/proactive_e2e.jsonl.

Targets the 18 hardest proactive-detection patterns — the ones that fool
even a smart human listening half-attentively. Each pattern gets several
LLM-generated variants (Gemini 2.5 Flash, temp ~0.9). We APPEND only.

Patterns (mirror the brief one-to-one):
    1  concealed_delegation                — first-person framed but actually delegated
    2  pronoun_chain_cross_turn            — antecedent 6+ lines back
    3  retraction_by_rephrase              — A then "actually B, do that instead"
    4  sarcasm_irony                       — "oh GREAT, I'd LOVE to..." (NOT intent)
    5  hypothetical_recall_negation        — "remember when I said X, never doing that"
    6  implicit_time_pressure              — past-due / overdue without explicit deadline
    7  multi_speaker_wearer_named          — friend tells the wearer to do X by name
    8  conditional_stale                   — "if 3pm meeting happens" but 3pm is past
    9  meaning_vs_deciding                 — "keep meaning to" vs "I am doing tomorrow"
   10  memory_dependent_pronoun            — "email her" with no in-session antecedent
   11  negation_deferral                   — "don't book the flight yet"
   12  compound_retraction                 — list of N then scratch some
   13  past_completion_confused            — "I just sent that email" (already done)
   14  brainstorm_with_buried_decision     — 8 lines of options then a single "let's go with"
   15  multi_language_mixing               — code-switching English/Spanish/Mandarin
   16  roleplay_movie_song                 — performance speech, not commitment
   17  customer_client_roleplay            — "if a customer asks X tell them Y"
   18  quotes_inside_quotes                — "Sarah said 'I'll send the deck'" (Sarah's task)

Run:
    python /workspaces/Anticipy/engine/data/extend_brutal.py
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


# Each PATTERN is an (id, n_variants, seed_bullets) tuple. The seeds are
# deliberately broad — Gemini fills in fresh transcript text every call.
PATTERNS: list[dict] = [
    # ---- 1  CONCEALED DELEGATION ----------------------------------------
    {
        "id": "concealed_delegation_first_person_framed",
        "category": "brutal_concealed_delegation",
        "n": 4,
        "seed_variants": [
            "Wearer sounds like they own the task: 'I want to make sure that "
            "report goes out today' — but a beat later they turn to a teammate "
            "named in the room: 'Sarah, you're on it, right?' Sarah confirms. "
            "Truth: it's Sarah's task, not the wearer's. Zero wearer-intents.",
            "Wearer says 'I really need this deck wrapped before Friday' but "
            "follows with 'Marcus is locked in on it though, right?' to a "
            "co-worker who acknowledges. Wearer is delegating, not doing.",
            "Wearer at home: 'I want all the laundry done before guests arrive "
            "Saturday — Jamie, you got that?' Jamie groans yes. Delegation "
            "buried inside first-person framing.",
            "Wearer at standup: 'I really want to get the migration shipped "
            "this week.' Then immediately: 'Priya, that's still on you, yeah?' "
            "Priya confirms. Wearer-intent = 0; delegated to Priya.",
        ],
    },
    # ---- 2  PRONOUN CHAIN CROSS TURN ------------------------------------
    {
        "id": "pronoun_chain_cross_turn",
        "category": "brutal_pronoun_chain",
        "n": 4,
        "seed_variants": [
            "Long discussion about three vendors A/B/C — 8+ lines comparing "
            "pricing, integration, support. Then a tangent. Then someone "
            "circles back: 'Yeah, do that.' The 'that' refers to vendor C "
            "selection ~6 lines back. The wearer has to commit to vendor C.",
            "Speaker mentions a specific calendar reschedule (Tuesday → "
            "Thursday) early in transcript. Several unrelated lines pass. At "
            "end wearer says 'Yeah just do that' — the antecedent is the "
            "Tuesday→Thursday move from earlier.",
            "Wearer talks through three holiday gift ideas for partner "
            "(plant, watch, weekend trip). Conversation drifts to traffic, "
            "weather, kids. Then partner says 'Honestly the second one was "
            "best.' Wearer: 'Yeah, do that one.' The 'that' = the watch.",
            "Long debate about whether to upgrade laptop now or wait. Many "
            "lines of cost-benefit. Eventually wearer says 'Fine, let's do "
            "it.' Refers back to the upgrade-now branch. Single intent.",
        ],
    },
    # ---- 3  RETRACTION BY REPHRASE --------------------------------------
    {
        "id": "retraction_by_rephrase",
        "category": "brutal_retraction_rephrase",
        "n": 4,
        "seed_variants": [
            "Wearer: 'Book the flight to LA for Thursday.' Beat. 'Actually "
            "let me think — yeah, Vancouver makes more sense, do that "
            "instead.' Two intents stated, only the second (Vancouver) is "
            "real.",
            "Wearer: 'Order the chicken.' Pause. 'No wait, get the salmon, "
            "salmon is better tonight.' Only one intent: salmon.",
            "Wearer: 'Schedule a call with Sarah at 3.' Then: 'Actually "
            "10am makes more sense for Mark too. Let's go 10am with both.' "
            "Final intent: 10am call with Sarah AND Mark.",
            "Wearer working through email: 'Reply to the recruiter saying "
            "I'm out.' Then: 'Mmm, actually, just say I'm exploring quietly. "
            "That's the line.' Final intent is 'exploring quietly' reply, "
            "the first version is retracted.",
        ],
    },
    # ---- 4  SARCASM / IRONY ---------------------------------------------
    {
        "id": "sarcasm_irony_not_intent",
        "category": "brutal_sarcasm",
        "n": 4,
        "seed_variants": [
            "Wearer drops 'Oh GREAT, I'd LOVE to spend Sunday cleaning the "
            "garage' with heavy sarcasm. Friend laughs. NOT an intent.",
            "Wearer rolls eyes: 'Yeah sure, I'll just rebuild the whole "
            "deployment pipeline tonight, no big deal.' Heavy sarcasm "
            "responding to engineer-friend's chronic dramatic asks. NOT an "
            "intent.",
            "Wearer: 'Right, I'll just hand over my entire weekend to my "
            "in-laws, that sounds amazing.' Friend chuckles. NOT an intent.",
            "Wearer responds to a partner's request with 'Oh totally, I'll "
            "drop everything and reorganize the entire pantry RIGHT NOW.' "
            "Sarcastic refusal. NOT an intent.",
        ],
    },
    # ---- 5  HYPOTHETICAL RECALL NEGATION --------------------------------
    {
        "id": "hypothetical_recall_negation",
        "category": "brutal_recall_negation",
        "n": 3,
        "seed_variants": [
            "Wearer: 'Remember when I said I'd quit caffeine? Yeah, never "
            "doing that again. One cup is one cup.' Past stated intent + "
            "explicit reversal. Not a current intent.",
            "Wearer: 'Remember last year when I swore I'd run a marathon? "
            "What was I thinking. Definitely not happening.' Past intent "
            "explicitly cancelled. Zero new intent.",
            "Wearer: 'I once told myself I'd go vegan for a month. Hilarious "
            "in hindsight, never trying that.' Cancelled past intent. Zero "
            "new intent.",
        ],
    },
    # ---- 6  IMPLICIT TIME PRESSURE --------------------------------------
    {
        "id": "implicit_time_pressure_overdue",
        "category": "brutal_implicit_pressure",
        "n": 3,
        "seed_variants": [
            "Wearer: 'The Stripe invoice is past due, I need to handle "
            "that.' No explicit deadline, but 'past due' = high importance "
            "now. One intent: pay/handle the overdue Stripe invoice.",
            "Wearer: 'Property tax notice has been on my desk for two weeks, "
            "I really need to pay it before they assess late fees.' Implicit "
            "but real urgency. One intent.",
            "Wearer: 'Doctor's portal said my prescription refill expired "
            "three days ago and I'm out of pills tomorrow. I need to call "
            "the office in the morning.' One intent: call doctor for "
            "refill.",
        ],
    },
    # ---- 7  MULTI-SPEAKER WEARER NAMED ----------------------------------
    {
        "id": "multi_speaker_wearer_named_friend_says",
        "category": "brutal_multi_speaker_named",
        "n": 4,
        "seed_variants": [
            "Wearer's name is 'John'. Friend says: 'You should book the "
            "flight, John.' But John (the wearer) just nods/grunts/laughs, "
            "never explicitly agrees. Engine should NOT auto-extract — only "
            "if wearer agrees.",
            "Wearer is 'Maya'. Roommate says 'Maya you really need to call "
            "the landlord about the leak.' Maya replies 'meh, maybe later, "
            "I'm not in the mood.' Soft-deferral; NOT a committed intent.",
            "Wearer 'Diego'. Co-worker tells him 'Diego, you have to send "
            "Andrew the slides by EOD.' Diego: 'Yeah yeah, fine, I'll do "
            "it.' Wearer DID accept — one real intent.",
            "Wearer 'Aanya'. Mom says 'Aanya, please pick up your sister "
            "from soccer.' Aanya: 'I'm in a meeting, ask Dad.' Wearer "
            "explicitly declined; NOT an intent.",
        ],
    },
    # ---- 8  CONDITIONAL STALE -------------------------------------------
    {
        "id": "conditional_stale_past",
        "category": "brutal_conditional_stale",
        "n": 3,
        "seed_variants": [
            "It is 5pm. Earlier in the day someone said 'if the 3pm meeting "
            "happens, prep the deck.' Now at 5pm wearer references the "
            "earlier conditional. The 3pm slot has passed; wearer never "
            "said whether the meeting actually happened. Engine must NOT "
            "extract a 'prep deck' intent without verifying the condition.",
            "Wearer says: 'If the lawyer calls back today, send him the "
            "redline.' Transcript ends at 7pm with no mention of a "
            "callback. Engine should treat as conditional/unresolved, not "
            "auto-extract.",
            "Wearer says: 'If Sam shows up to the offsite tomorrow, set up "
            "the breakout for him.' Transcript next morning happens AFTER "
            "the offsite started — and there's no reference to Sam. Stale "
            "conditional.",
        ],
    },
    # ---- 9  MEANING VS DECIDING -----------------------------------------
    {
        "id": "meaning_vs_deciding",
        "category": "brutal_meaning_vs_deciding",
        "n": 4,
        "seed_variants": [
            "Wearer: 'I keep meaning to refinance the mortgage.' (NO "
            "decision.) Conversation moves on. Zero intent.",
            "Wearer: 'I keep saying I'll learn Spanish and then I just "
            "don't.' Zero intent.",
            "Wearer: 'I'm refinancing the mortgage tomorrow — call's "
            "booked at 10 with the broker.' Concrete commitment. ONE "
            "intent.",
            "Wearer first: 'I should really get my eyes checked.' Soft "
            "wish. Then: 'Actually I'm calling the optometrist on Monday "
            "morning, putting it on my list now.' Soft wish escalates "
            "into a real commitment — ONE intent (call optometrist "
            "Monday).",
        ],
    },
    # ---- 10  MEMORY-DEPENDENT PRONOUN -----------------------------------
    {
        "id": "memory_dependent_pronoun_no_session_antecedent",
        "category": "brutal_memory_pronoun",
        "n": 3,
        "seed_variants": [
            "Cold open: wearer simply says 'Email her about it.' No prior "
            "in-conversation reference to a 'her' or to 'it'. Engine has no "
            "way to resolve the antecedent in this session. Should ask for "
            "clarification — expected_clarification populated.",
            "Wearer says 'Send him the file we talked about.' No 'him', "
            "no 'file' established in this transcript. Cross-session "
            "memory MIGHT resolve it, but raw transcript alone cannot. "
            "Clarification expected.",
            "Wearer: 'Tell them I'll be late.' No 'them' antecedent in "
            "this transcript. Clarification expected.",
        ],
    },
    # ---- 11  NEGATION / DEFERRAL ----------------------------------------
    {
        "id": "negation_deferral_explicit_dont_yet",
        "category": "brutal_negation_deferral",
        "n": 3,
        "seed_variants": [
            "Wearer: 'Don't book the flight yet, wait for HR to confirm "
            "dates.' Active negation; do not extract a 'book flight' "
            "intent. Possibly extract a watcher: 'wait for HR confirmation' "
            "but NO action.",
            "Wearer: 'Hold off on sending the email to legal until I "
            "review it tonight.' Negation + deferral. Zero immediate "
            "intent. Maybe a watcher.",
            "Wearer: 'Don't call the contractor yet — let me think over "
            "the budget first.' No 'call contractor' intent.",
        ],
    },
    # ---- 12  COMPOUND RETRACTION ----------------------------------------
    {
        "id": "compound_retraction_partial_scratch",
        "category": "brutal_compound_retraction",
        "n": 4,
        "seed_variants": [
            "Wearer: 'Email Sarah, John, Liam, and Mark about the budget. "
            "Wait — scratch Sarah, she's out. And Mark — actually never "
            "mind, he doesn't need it.' Final list: John and Liam only. "
            "ONE intent: 'email John and Liam about the budget'.",
            "Wearer to assistant: 'Add Acme, Bravo, Charlie, and Delta to "
            "the invite list. Hmm, drop Bravo — they're our competitor. "
            "Charlie is a maybe so leave them off too.' Final invitees: "
            "Acme + Delta only.",
            "Wearer: 'Order pizza, salad, breadsticks, and tiramisu. Wait, "
            "skip tiramisu, kids don't like it. Salad too actually, no one "
            "ate it last time.' Final: pizza + breadsticks.",
            "Wearer: 'Schedule calls with Maya, Noah, Priya, and Rui this "
            "week. Actually Noah is on vacation — skip him. And Priya, I "
            "already had coffee with her, no need.' Final: calls with Maya "
            "and Rui.",
        ],
    },
    # ---- 13  PAST COMPLETION CONFUSED -----------------------------------
    {
        "id": "past_completion_confused_with_intent",
        "category": "brutal_past_completion",
        "n": 3,
        "seed_variants": [
            "Wearer: 'I just sent that email to the recruiter, finally.' "
            "Past tense; already done. Zero intent.",
            "Wearer: 'Already paid the credit card bill this morning, so "
            "we're good.' Zero intent.",
            "Wearer mid-call: 'I locked the meeting in for 11am Thursday "
            "with finance, all set.' Already booked; zero new intent.",
        ],
    },
    # ---- 14  BRAINSTORM WITH BURIED DECISION ----------------------------
    {
        "id": "brainstorm_buried_decision",
        "category": "brutal_brainstorm_buried",
        "n": 4,
        "seed_variants": [
            "Wearer thinks aloud about three offsite venues: 'What about "
            "Whistler? Or Lake Tahoe? Or Sedona?' 8+ lines of pros and "
            "cons (cost, weather, flight time, vibe). Eventually: 'OK, "
            "let's go with Sedona by Friday — book it.' ONE intent.",
            "Wearer: 'What about Italian, what about Thai, what about "
            "ramen, what about that new Korean place...' 6 lines of "
            "back-and-forth. Final: 'OK, Korean place, 7:30 tomorrow. Book "
            "it.' ONE intent.",
            "Wearer brainstorming team-of-one role hires for 9 lines. "
            "Many candidates listed. Then: 'Honestly let's just hire "
            "Priya — get her offer letter out by Tuesday.' ONE intent.",
            "Wearer planning sister's birthday: ideas about karaoke, "
            "escape room, cooking class, beach day. After 8 lines of "
            "options: 'Cooking class. Book it for the 12th, six people.' "
            "ONE intent.",
        ],
    },
    # ---- 15  MULTI-LANGUAGE MIXING --------------------------------------
    {
        "id": "multi_language_code_switching",
        "category": "brutal_multi_language",
        "n": 3,
        "seed_variants": [
            "Wearer is bilingual English/Spanish at home. Conversation "
            "code-switches mid-sentence: 'Mañana voy a... actually let me "
            "just do it now, llamar al doctor para que me dé cita.' Final "
            "intent: call the doctor for an appointment. Engine must not "
            "fail on Spanish.",
            "Wearer in Mandarin/English household: '我得记得 to send "
            "the school field trip permission slip 明天 before nine.' "
            "Final intent: send permission slip before 9am tomorrow.",
            "Wearer code-switching English/French: 'Bon, je vais order "
            "the diapers ce soir and pick them up demain matin.' Two "
            "intents: order diapers tonight + pick them up tomorrow "
            "morning.",
        ],
    },
    # ---- 16  ROLEPLAY / MOVIE / SONG ------------------------------------
    {
        "id": "roleplay_movie_song_performance",
        "category": "brutal_roleplay_perf",
        "n": 3,
        "seed_variants": [
            "Wearer in car with friend, sings along to a song: 'I'm gonna "
            "fly to Paris and never come back, baby!' Pure performance "
            "(song lyrics). Friend laughs. Zero intent.",
            "Wearer dramatically reciting a movie quote at a party: 'I'm "
            "gonna make him an offer he can't refuse.' Friends laugh. "
            "Zero intent.",
            "Wearer reading a kids' bedtime story: '...and the brave "
            "knight said I will slay the dragon at dawn!' Performance "
            "speech. Zero intent.",
        ],
    },
    # ---- 17  CUSTOMER / CLIENT ROLEPLAY ---------------------------------
    {
        "id": "customer_roleplay_instructional",
        "category": "brutal_customer_roleplay",
        "n": 3,
        "seed_variants": [
            "Wearer is training a new employee: 'If a customer asks for a "
            "refund, tell them we issue store credit only, and forward "
            "their info to me.' Instructional speech to staff. NOT an "
            "intent for the wearer.",
            "Wearer briefing assistant: 'When clients call about pricing, "
            "you offer the standard tier first, then upsell to premium "
            "only if they push back.' Instructional, not a wearer-task.",
            "Wearer training kid on phone manners: 'If grandma calls "
            "while I'm out, tell her I'll call her back after dinner, OK?' "
            "Instructional to the kid. NOT a wearer intent — wearer "
            "doesn't have to call grandma.",
        ],
    },
    # ---- 18  QUOTES INSIDE QUOTES ---------------------------------------
    {
        "id": "quotes_inside_quotes_third_party_commitment",
        "category": "brutal_quotes_in_quotes",
        "n": 4,
        "seed_variants": [
            "Wearer recounting a conversation: 'Sarah told me, quote, "
            "I'll have the deck done by Friday, end quote.' Sarah's "
            "commitment, NOT the wearer's. Zero wearer-intent.",
            "Wearer relaying: 'Mark said he\\'d ship the firmware update "
            "tonight.' Mark's commitment, not the wearer's.",
            "Wearer to spouse: 'My boss literally said, you know, "
            "I\\'ll get back to you on the bonus by end of month.' Boss\\'s "
            "commitment, not the wearer's.",
            "Wearer at family dinner: 'Aunt Linda told me, hey, I'll send "
            "you the recipe Sunday.' Linda's commitment, not the wearer's.",
        ],
    },
]


GENERATOR_SYSTEM = """You generate ONE realistic test scenario for an AI \
wearable's proactive intent-extraction layer. The wearer has an AI agent \
listening passively. We are stress-testing the HARDEST possible signals — \
patterns that fool even an attentive human listener.

Hard requirements:
- transcript: array of 8-30 lines, each formatted "Speaker: text". The
  WEARER speaks under whatever name the seed assigns or "Wearer:" if
  unspecified. Use real spoken English (or a code-switch where requested),
  fillers, interruptions, half-thoughts. Multi-speaker scenes need 2+
  distinct named speakers.
- expected_intents: array of one-line strings — what a perfect proactive
  layer SHOULD extract for the WEARER. ZERO is a valid and often correct
  count for these brutal patterns. NEVER include other people's
  commitments. NEVER include sarcastic, hypothetical, retracted, or
  past-completed items.
- noise_should_NOT_act_on: array of short descriptions of transcript items
  that LOOK actionable but are NOT wearer-tasks. List every retracted
  item, every delegated item, every sarcastic / hypothetical / quoted
  third-party commitment. This is what we hold the engine accountable for.
- name: short snake_case scenario id, max 7 words. Must be unique-feeling.
- difficulty: ALWAYS the literal string "brutal".
- expected_clarification (ONLY when the seed says expects_clarification=True):
  one-line natural-language question the agent SHOULD ask the wearer to
  resolve missing slots, e.g. "Who do you want me to email about what?"

Output: ONE JSON object only, no commentary, no code fences. Schema:
{
  "name": "<snake_case>",
  "difficulty": "brutal",
  "transcript": ["Speaker: ...", ...],
  "expected_intents": ["<one-line>", ...],
  "noise_should_NOT_act_on": ["<short desc>", ...],
  "expected_clarification": "<one-line>"  // only if expects_clarification=True
}

Rules of the world:
- The wearer's agent only acts on commitments the WEARER themselves makes.
- Sarcasm, song lyrics, movie quotes, performance speech, hypothetical
  recall, and explicitly retracted statements are NEVER intents.
- A first-person framed task that gets handed off to a named teammate
  ("Sarah, you're on it, right?") is a DELEGATION, not a wearer-intent.
- Quoted third-party commitments ("Sarah told me she'd send the deck") are
  NEVER the wearer's intents.
- Negated and deferred actions ("don't book yet") are NEVER intents.
- Past-completed items ("I just sent that email") are NEVER intents.
- "I keep meaning to" / "I should really" without concrete commitment is
  NEVER an intent. A concrete decision IS.
- Multi-language input must not break — extract intents in English even
  if dialog code-switches.
- Use fresh diverse names. Do NOT reuse names across runs.
- Do NOT copy phrasing from prior outputs.
"""


GENERATOR_USER = """Generate ONE brutal test scenario.

Pattern id: {pattern_id}
Category:  {category}
Variant index: {variant_idx} of {n_variants}

Seed (interpret loosely — bring it to life with realistic dialog, real
characters, a believable setting):
{seed}

Constraints:
- difficulty MUST be "brutal".
- Transcript 8-30 lines. Multi-speaker scenes mandatory if the pattern
  involves another speaker.
- Be honest about expected_intents. Many of these patterns expect ZERO
  wearer-intents. Don't pad.
- Populate noise_should_NOT_act_on thoroughly — list every red-herring.
- Use distinctive proper nouns; do not reuse common test names like
  "Sarah", "John", "Mark" unless the seed specifies them.
- {clarification_clause}

Return JSON only.
"""


def expects_clarification(pattern_id: str) -> bool:
    """Patterns that should produce a clarification request when triggered."""
    return pattern_id in {
        "memory_dependent_pronoun_no_session_antecedent",
    }


async def gemini_one(
    pattern: dict, seed: str, variant_idx: int, *, attempt: int = 0
) -> dict | None:
    expects = expects_clarification(pattern["id"])
    clarification_clause = (
        "expected_clarification REQUIRED — include a one-line question the agent "
        "would ask the wearer to resolve the ambiguity."
        if expects
        else "OMIT the expected_clarification field."
    )

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
                            variant_idx=variant_idx + 1,
                            n_variants=pattern["n"],
                            seed=seed,
                            clarification_clause=clarification_clause,
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
                    return await gemini_one(
                        pattern, seed, variant_idx, attempt=attempt + 1
                    )
                return None
            txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            sc = json.loads(txt)
    except Exception as e:
        print(f"   gemini error: {type(e).__name__}: {e}", flush=True)
        if attempt < 2:
            await asyncio.sleep(2 * (attempt + 1))
            return await gemini_one(
                pattern, seed, variant_idx, attempt=attempt + 1
            )
        return None

    required = (
        "name",
        "difficulty",
        "transcript",
        "expected_intents",
        "noise_should_NOT_act_on",
    )
    if not all(k in sc for k in required):
        if attempt < 2:
            return await gemini_one(
                pattern, seed, variant_idx, attempt=attempt + 1
            )
        return None
    if not isinstance(sc["transcript"], list) or len(sc["transcript"]) < 5:
        if attempt < 2:
            return await gemini_one(
                pattern, seed, variant_idx, attempt=attempt + 1
            )
        return None
    if not isinstance(sc["expected_intents"], list) or not isinstance(
        sc["noise_should_NOT_act_on"], list
    ):
        return None

    if expects and "expected_clarification" not in sc:
        if attempt < 2:
            return await gemini_one(
                pattern, seed, variant_idx, attempt=attempt + 1
            )

    sc["difficulty"] = "brutal"
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

    total_to_generate = sum(p["n"] for p in PATTERNS)
    print(
        f"Existing scenarios: {len(seen_names)}. "
        f"Generating {total_to_generate} new BRUTAL ones across "
        f"{len(PATTERNS)} patterns.",
        flush=True,
    )

    sem = asyncio.Semaphore(8)
    results: list[dict] = []
    fail_patterns: list[str] = []

    async def one(pattern: dict, variant_idx: int, seed: str, idx: int) -> None:
        async with sem:
            sc = await gemini_one(pattern, seed, variant_idx)
            if sc is None:
                fail_patterns.append(pattern["id"])
                print(
                    f"  [{idx + 1:3}/{total_to_generate}] FAIL pattern={pattern['id']}",
                    flush=True,
                )
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
                f"  [{idx + 1:3}/{total_to_generate}] {name:<54} "
                f"d={sc['difficulty']:<6} "
                f"lines={len(sc['transcript']):<2} "
                f"exp={len(sc['expected_intents'])} "
                f"noise={len(sc['noise_should_NOT_act_on'])} "
                f"clar={'Y' if 'expected_clarification' in sc else '-'}",
                flush=True,
            )

    tasks = []
    overall_idx = 0
    for pattern in PATTERNS:
        for variant_idx in range(pattern["n"]):
            seed = pattern["seed_variants"][
                variant_idx % len(pattern["seed_variants"])
            ]
            tasks.append(one(pattern, variant_idx, seed, overall_idx))
            overall_idx += 1

    await asyncio.gather(*tasks)

    with OUT_FILE.open("a") as f:
        for sc in results:
            f.write(json.dumps(sc, ensure_ascii=False) + "\n")

    from collections import Counter

    cats = Counter(s["category"] for s in results)
    pats = Counter(s["pattern_id"] for s in results)
    diffs = Counter(s["difficulty"] for s in results)
    print(f"\nAppended {len(results)} brutal scenarios -> {OUT_FILE}")
    print(f"  category counts: {dict(cats)}")
    print(f"  pattern counts:  {dict(pats)}")
    print(f"  difficulty counts: {dict(diffs)}")
    if fail_patterns:
        print(f"  failed patterns: {fail_patterns}")

    total = 0
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            total = sum(1 for line in f if line.strip())
    print(f"  TOTAL scenarios in file now: {total}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
