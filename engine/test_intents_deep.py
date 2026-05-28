"""
Deep intent detection tests for Anticipy proactive engine.
50 messy real-world conversation scenarios testing the analyze endpoint's
ability to extract (or correctly ignore) actionable items.

These test the LLM prompt + classification pipeline, NOT the browser agent.
Run: cd engine && python test_intents_deep.py
"""

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, ".")

# Load env vars from .env.local
from pathlib import Path
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from app.router import classify, handle_chat, handle_question
from app.models import CostTracker
from app import messages as msg_module

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []

BANNED_PATTERNS = [
    "json", "api ", "error code", "stack trace", "traceback",
    "exception", "null", "nonetype",
    "dom ", "selector", "xpath", "javascript", "python",
    "function", "debug", "console", "endpoint",
    "playwright", "patchright", "chromium", "webdriver",
    "groq", "gemini", "llama", "deepseek", "fastapi",
    "websocket", "supabase", "httpx", "async", "await",
]

def check_leakage(text: str) -> str | None:
    text_lower = " " + text.lower() + " "
    for word in BANNED_PATTERNS:
        if f" {word}" in text_lower or f"\n{word}" in text_lower:
            return word
    return None


async def run_intent_test(
    test_num: int,
    label: str,
    task_text: str,
    pass_check,
):
    global PASS_COUNT, FAIL_COUNT

    print(f"\n{'='*60}", flush=True)
    print(f"TEST {test_num}: {label}", flush=True)
    print(f"INPUT: {task_text[:120]}{'...' if len(task_text) > 120 else ''}", flush=True)
    print(f"{'='*60}", flush=True)

    start = time.time()
    category = "error"
    response = ""

    try:
        tracker = CostTracker()
        classification = await asyncio.wait_for(classify(task_text, tracker), timeout=30)
        category = classification.category if hasattr(classification, "category") else str(classification)
        print(f"  [classify] -> {category} (degraded={getattr(classification,'degraded',False)})", flush=True)

        if category == "chat":
            response = await asyncio.wait_for(handle_chat(task_text, tracker), timeout=30)
        elif category == "question":
            response = await asyncio.wait_for(handle_question(task_text, tracker), timeout=30)
        elif category == "ambiguous":
            response = msg_module.AMBIGUOUS_REQUEST
        else:
            response = f"[action detected - would launch browser]"
    except Exception as e:
        response = f"[error: {type(e).__name__}]"
        print(f"  [EXCEPTION] {type(e).__name__}: {e}", flush=True)

    elapsed = time.time() - start
    leak = check_leakage(response)
    passed = pass_check(category, response)
    if leak:
        passed = False
        print(f"  LEAKAGE: '{leak}' found in response", flush=True)

    status = "PASS" if passed else "FAIL"
    if passed:
        PASS_COUNT += 1
    else:
        FAIL_COUNT += 1

    print(f"  [{status}] {label} ({elapsed:.1f}s)", flush=True)
    print(f"  CATEGORY: {category}", flush=True)
    print(f"  RESPONSE: {response[:200]}", flush=True)

    RESULTS.append({
        "test": test_num,
        "label": label,
        "passed": passed,
        "elapsed": round(elapsed, 1),
        "category": category,
        "response": response[:500],
        "leak": leak,
    })


async def main():
    global PASS_COUNT, FAIL_COUNT

    print("=" * 60)
    print("ANTICIPY PROACTIVE ENGINE - DEEP INTENT TESTS")
    print("50 messy real-world conversation scenarios")
    print("=" * 60)

    # ── ZERO-INTENT: Pure social chat (should NOT trigger actions) ──────────

    await run_intent_test(
        1, "Zero-intent: weather small talk",
        "Man it's been raining all week, I'm so over it",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        2, "Zero-intent: gossip between friends",
        "Did you see what happened at the party last night? Jake was being so weird",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        3, "Zero-intent: complaining about work",
        "Ugh my manager keeps scheduling meetings during lunch. It's so annoying",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        4, "Zero-intent: philosophical musing",
        "I wonder sometimes if we're all just living in a simulation you know",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        5, "Zero-intent: sports recap",
        "The Canucks absolutely destroyed the Oilers last night, 6-1, Pettersson had a hat trick",
        lambda cat, r: cat in ("chat", "ambiguous", "question") and "error" not in r.lower(),
    )

    # ── CLEAR ACTIONS: Obvious actionable items ────────────────────────────

    await run_intent_test(
        6, "Clear action: explicit reminder request",
        "remind me to pick up the dry cleaning tomorrow at 3",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        7, "Clear action: scheduling request",
        "I need to book a dentist appointment for next Tuesday morning",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        8, "Clear action: purchase intent",
        "I gotta order more dog food from Amazon before we run out",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        9, "Clear action: send message",
        "Text mom that we're coming for dinner Sunday at 6",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        10, "Clear action: bill payment",
        "I need to pay the electricity bill before the end of the month, it's like 180 bucks",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    # ── BURIED ACTIONS: Actionable items hidden in casual conversation ─────

    await run_intent_test(
        11, "Buried action: commitment in long ramble",
        "So yeah the meeting was fine, kind of boring, but anyway Sarah asked me "
        "to review her proposal by Friday so I said I would. Then we went to lunch "
        "and the new Thai place is actually really good, you should try it",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        12, "Buried action: task mentioned in passing",
        "Bro the traffic was insane getting home. Oh also I told the landlord "
        "I'd fix the leaky faucet this weekend. Anyway did you watch the game",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        13, "Buried action: deadline in complaint",
        "I can't believe the teacher assigned another essay. It's due Monday and "
        "I haven't even started the reading. Whatever I'll deal with it. Wanna play Fortnite?",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        14, "Buried action: financial obligation in story",
        "So my buddy Jake lent me 200 bucks for the concert tickets last month "
        "and I keep forgetting to pay him back. We had such a good time though, "
        "the opener was way better than expected",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        15, "Buried action: health task in rant",
        "The doctor said my blood pressure is a bit high and I should start taking "
        "that new medication daily. But honestly the pharmacy is always so crowded "
        "and I hate waiting there",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    # ── MULTI-SPEAKER: Conversations with multiple people ──────────────────

    await run_intent_test(
        16, "Multi-speaker: couple planning dinner",
        "[Speaker 1]: What should we do for dinner tonight?\n"
        "[Speaker 2]: I don't know, maybe order from that new sushi place?\n"
        "[Speaker 1]: Oh yeah, can you call them? Their app doesn't work\n"
        "[Speaker 2]: Sure, I'll call after I finish this email",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        17, "Multi-speaker: coworkers assigning tasks",
        "[Speaker 1]: The client wants the mockups by Wednesday\n"
        "[Speaker 2]: I can handle the homepage but someone needs to do the checkout flow\n"
        "[Speaker 1]: I'll take checkout. Can you also ping design for the asset files?\n"
        "[Speaker 2]: Yeah I'll slack them now",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        18, "Multi-speaker: parent and teenager",
        "[Speaker 1]: Did you finish your college applications?\n"
        "[Speaker 2]: Almost, I still need to write the Stanford essay\n"
        "[Speaker 1]: The deadline is January 2nd, that's like 5 days\n"
        "[Speaker 2]: I know I know, I'll do it tonight\n"
        "[Speaker 1]: And don't forget to ask Mr. Chen for that recommendation letter",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        19, "Multi-speaker: friends planning trip",
        "[Speaker 1]: So we're doing Whistler next weekend right?\n"
        "[Speaker 2]: Yeah I booked the cabin already\n"
        "[Speaker 3]: Nice, I'll bring the cooler. Someone needs to rent the ski gear though\n"
        "[Speaker 1]: I can do that, where should I rent from?\n"
        "[Speaker 2]: Try Whistler Village Sports, they had good prices last time\n"
        "[Speaker 3]: Oh and someone text Mike, he doesn't know the plan yet",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        20, "Multi-speaker: business meeting rapid-fire",
        "[Speaker 1]: Q3 numbers are down 12 percent\n"
        "[Speaker 2]: We need to cut the marketing spend on the underperforming channels\n"
        "[Speaker 1]: Agreed. Sarah can you pull the channel breakdown by next standup?\n"
        "[Speaker 3]: Yeah I'll have it by tomorrow 9am\n"
        "[Speaker 2]: Also we should schedule a call with the agency to renegotiate the contract\n"
        "[Speaker 1]: I'll set that up for Thursday",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    # ── SLANG AND ABBREVIATIONS ────────────────────────────────────────────

    await run_intent_test(
        21, "Slang: Gen-Z speak with action",
        "ngl that presentation was lowkey fire but we gotta send the slides to the client asap",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        22, "Slang: text-speak casual",
        "lol ya ill grab groceries otw home, we need milk eggs and bread",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        23, "Slang: pure vibes no action",
        "bro that sunset was absolutely bussin no cap fr fr",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        24, "Abbreviations: work context",
        "fyi the PR is approved, need to merge before EOD and deploy to staging, lmk if CI breaks",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    # ── SARCASM AND NEGATION ───────────────────────────────────────────────

    await run_intent_test(
        25, "Sarcasm: clearly not a real request",
        "Oh yeah I'll totally remember to water the plants like I always do. Not.",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        26, "Negation: explicitly canceling a task",
        "Actually never mind, don't book that restaurant, we're staying in tonight",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        27, "Sarcasm: rhetorical frustration",
        "Sure, let me just add 'fix the entire codebase' to my to-do list right after 'cure cancer'",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        28, "Past tense: already completed (no action needed)",
        "I already sent that invoice to the client this morning and they confirmed receipt",
        lambda cat, r: cat in ("chat", "ambiguous", "question") and "error" not in r.lower(),
    )

    # ── MEDICAL AND HEALTH CONTEXTS ────────────────────────────────────────

    await run_intent_test(
        29, "Medical: prescription refill needed",
        "The pharmacy called and said my prescription for metformin is ready but "
        "I need to pick it up before Saturday or they'll put it back",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        30, "Medical: follow-up appointment",
        "[Speaker 1]: How did the check-up go?\n"
        "[Speaker 2]: Good, but she wants me to come back in two weeks for bloodwork. "
        "I need to schedule that and fast for 12 hours beforehand",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        31, "Medical: vague symptom discussion (no clear action)",
        "I've been having these headaches lately, probably just stress. "
        "I should probably drink more water or something",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    # ── FINANCIAL CONTEXTS ─────────────────────────────────────────────────

    await run_intent_test(
        32, "Financial: multiple obligations in one breath",
        "Rent is due on the 1st, car insurance on the 15th, and I still owe "
        "my sister 500 from last month. Oh and I need to cancel that gym "
        "membership I never use",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        33, "Financial: investment discussion (no immediate action)",
        "I've been thinking about putting some money into index funds but "
        "the market is so volatile right now. What do you think?",
        lambda cat, r: cat in ("chat", "ambiguous", "question") and "error" not in r.lower(),
    )

    await run_intent_test(
        34, "Financial: tax deadline pressure",
        "I totally forgot about taxes. The filing deadline is April 30th and "
        "I haven't even collected my T4s. I need to call my accountant ASAP",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    # ── AMBIGUOUS AND TRICKY ───────────────────────────────────────────────

    await run_intent_test(
        35, "Ambiguous: 'should' vs 'will'",
        "I should probably start exercising more",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        36, "Ambiguous: hypothetical vs real plan",
        "If I get the promotion I'm gonna take the whole family to Hawaii",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        37, "Ambiguous: question about process (not a task)",
        "How do you even file a patent anyway? Is it expensive?",
        lambda cat, r: cat in ("chat", "ambiguous", "question") and "error" not in r.lower(),
    )

    await run_intent_test(
        38, "Ambiguous: vague future intent",
        "We need to do something about the backyard fence at some point",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        39, "Tricky: 'I'll' commitment that's actually polite deflection",
        "Oh yeah I'll think about it and get back to you",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    # ── LONG MESSY CONVERSATIONS ───────────────────────────────────────────

    await run_intent_test(
        40, "Long: 5 minutes of rambling with 2 buried tasks",
        "[Speaker 1]: So how was your weekend?\n"
        "[Speaker 2]: It was good, we went to Stanley Park and the kids loved it. "
        "Oh I need to return those shoes to Nordstrom by the way, they didn't fit. "
        "Anyway the weather was perfect, not too hot, and we found this amazing "
        "food truck near the aquarium. Have you been to the aquarium recently?\n"
        "[Speaker 1]: No not in ages. We should go sometime.\n"
        "[Speaker 2]: Totally. Oh and I forgot to tell you, the school emailed about "
        "the parent-teacher conference next Thursday at 4. We need to RSVP by Wednesday.\n"
        "[Speaker 1]: OK I'll respond to that email tonight.\n"
        "[Speaker 2]: Perfect. So anyway, what are you guys doing for summer?",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        41, "Long: work standup with overlapping action items",
        "[Speaker 1]: OK team, quick standup. What's everyone working on?\n"
        "[Speaker 2]: I'm finishing the API docs, should be done by lunch. Then I'm "
        "picking up the caching bug from the backlog.\n"
        "[Speaker 3]: I'm blocked on the auth PR, waiting for Mike's review. In the "
        "meantime I'm going to spike on the new notification system.\n"
        "[Speaker 1]: Mike is out sick today so I'll review it. Sarah, can you also "
        "update the deployment runbook? We're missing the new env vars.\n"
        "[Speaker 3]: Yeah I'll do that after standup.\n"
        "[Speaker 1]: Great. Oh and everyone remember the team lunch is moved to "
        "Thursday at noon instead of Friday.",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        42, "Long: entirely social conversation zero tasks",
        "[Speaker 1]: Did you see the new Marvel movie?\n"
        "[Speaker 2]: Yeah it was actually pretty good, way better than the last one\n"
        "[Speaker 1]: I know right? The villain was amazing\n"
        "[Speaker 2]: And that twist at the end, I did not see that coming\n"
        "[Speaker 1]: Same. The CGI was insane too\n"
        "[Speaker 2]: I heard they spent like 200 million on it\n"
        "[Speaker 1]: Worth it honestly. Best one since Endgame\n"
        "[Speaker 2]: No way, Infinity War was better. But this is top 5 for sure",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    # ── CONTEXT-DEPENDENT ──────────────────────────────────────────────────

    await run_intent_test(
        43, "Context: refers to someone not present",
        "Tell dad I'll be home late tonight, probably around 10. And ask him "
        "if he can leave the garage door unlocked",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        44, "Context: follow-up to implied prior conversation",
        "Wait did she ever get back to us about the venue? We need to confirm "
        "that booking by end of day or we lose the deposit",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        45, "Context: emotional vent that contains a real task",
        "I'm so stressed about this move. I still haven't called the moving company "
        "to confirm Saturday, the internet needs to be set up at the new place, and "
        "I haven't even started packing the kitchen. Why did I agree to this timeline",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    # ── EDGE CASES ─────────────────────────────────────────────────────────

    await run_intent_test(
        46, "Edge: single word",
        "groceries",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        47, "Edge: just laughter",
        "hahahaha lol that's hilarious",
        lambda cat, r: cat in ("chat", "ambiguous") and "error" not in r.lower(),
    )

    await run_intent_test(
        48, "Edge: mixed languages",
        "We need to envoyer le rapport to the client avant vendredi, c'est urgent",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        49, "Edge: rapid-fire micro-tasks",
        "OK so I need to: call plumber, pick up package from post office, "
        "email Karen about the budget, buy birthday present for mom, "
        "and book the vet for Charlie's shots",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    await run_intent_test(
        50, "Edge: extremely long transcript with one critical item buried at end",
        "So we spent the whole morning in that strategy offsite and honestly "
        "most of it was pretty standard stuff. The CEO talked about the vision "
        "for next year which is basically the same as this year but bigger numbers. "
        "Then marketing presented their plan which looked solid, a lot of focus on "
        "content marketing and SEO. Engineering showed the roadmap and there's some "
        "cool stuff coming in Q2 around AI features. The design team did a nice demo "
        "of the new dashboard. HR announced some new benefits, better dental coverage "
        "which is cool. Finance went through the numbers, we're on track for the year. "
        "Then at the very end the CTO pulled me aside and said they want to acquire "
        "that startup we were looking at and I need to send them a term sheet by "
        "tomorrow 5pm or they're going with another offer. She said this is top priority "
        "and to drop everything else.",
        lambda cat, r: len(r) > 5 and "error" not in r.lower(),
    )

    # ── SUMMARY ────────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"RESULTS: {PASS_COUNT}/{PASS_COUNT + FAIL_COUNT} passed")
    print(f"{'='*60}")
    for r in RESULTS:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] Test {r.get('test', '?')}: {r.get('label', '')}")
        if not r["passed"] and r.get("response"):
            print(f"         Response: {r['response'][:100]}")

    # Save results
    os.makedirs("logs", exist_ok=True)
    with open("logs/test_intents_deep_results.json", "w") as f:
        json.dump({
            "total": PASS_COUNT + FAIL_COUNT,
            "passed": PASS_COUNT,
            "failed": FAIL_COUNT,
            "results": RESULTS,
        }, f, indent=2)

    print(f"\nResults saved to logs/test_intents_deep_results.json")


if __name__ == "__main__":
    asyncio.run(main())
