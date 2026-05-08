"""
Extend /workspaces/Anticipy/engine/data/proactive_e2e.jsonl with adversarial
edge-case scenarios. Each NEW pattern is fed to Gemini 2.5 Flash at temp 0.9
which produces the actual transcript text. We APPEND to the existing JSONL
without touching prior entries.

Adds:
  - 10 missing-slot scenarios (adds expected_clarification field)
  - 4  conditional/temporal traps
  - 3  multi-intent stress tests
  - 3  pleasantries-with-specifics
  - 3  delegation traps
  - 3  retraction patterns
  - 4  family-mode mixed-task scenarios
  - 3  privacy/sensitive scenarios
  - 2  brainstorming (no-commitments) scenarios
  - 5  ambient/noise zero-intent scenarios
  - 5  multi-day cross-session reference scenarios
  - 5  pure zero-intent variants
  - 10 concrete real-action half tests (full slots)
  - ~10 hard production cases (LLM-driven from broad pattern prompts)

Run: python /workspaces/Anticipy/engine/data/extend_proactive_e2e.py
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
# New patterns — every one carries a `category` so the dataset can be sliced
# during eval. The LLM still writes the actual transcript & ground-truth.
# ---------------------------------------------------------------------------

PATTERNS: list[dict] = [
    # ------- 1-10  MISSING SLOTS (the demo killer) ------------------------
    {
        "id": "missing_slots_book_flight",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says some variant of 'book a flight' with no origin, no destination, no dates. Maybe a partner answers vaguely. The wearer doesn't fill in the gaps.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_message_david",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'send David a message' or 'text David' with NO message body and NO platform (sms? slack? whatsapp?). Conversation moves on without resolving.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_buy_coffee_maker",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I should buy a coffee maker' with no specific brand, price ceiling, or store preference. Maybe a partner agrees vaguely.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_hotel_next_week",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'book a hotel for next week' but never names the destination, doesn't say party size, doesn't pin dates beyond 'next week'.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_call_with_sarah",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'schedule a call with Sarah' with no time, no agenda, no platform (zoom? phone?).",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_order_food",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'order food' with no cuisine, no time, no place. Maybe partner says 'sure'. No further details.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_remind_me_later",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'remind me later' with no specific thing being referenced and no clear time. Maybe a vague 'about the thing'.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_pay_the_bill",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I gotta pay the bill' — but multiple bills could be intended (electric? rent? credit card?). No specific bill named, no due date stated.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_cancel_subscription",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I should cancel that subscription' but never names which one. Earlier conversation may mention multiple services in passing.",
        "expects_clarification": True,
    },
    {
        "id": "missing_slots_netflix_show",
        "category": "missing_slots",
        "difficulty": "hard",
        "seed": "Wearer says 'I should watch that Netflix show I was telling you about' — no title given. Conversation moves on.",
        "expects_clarification": True,
    },
    # ------- 11-14  CONDITIONAL / TEMPORAL TRAPS -------------------------
    {
        "id": "conditional_rain_picnic",
        "category": "conditional",
        "difficulty": "brutal",
        "seed": "Wearer says 'if it rains tomorrow, cancel the picnic'. The condition is unresolved at end of transcript. The watcher should track-but-not-act, OR mark as conditional/deferred. Do NOT auto-cancel.",
        "expects_clarification": False,
    },
    {
        "id": "conditional_pronoun_3pm_meeting",
        "category": "conditional",
        "difficulty": "hard",
        "seed": "Wearer says 'move my 3pm to 4pm' but does NOT identify which meeting. The pronoun 'my 3pm' is ambiguous if multiple 3pm meetings exist.",
        "expects_clarification": True,
    },
    {
        "id": "conditional_call_them_back",
        "category": "conditional",
        "difficulty": "brutal",
        "seed": "Wearer says 'call them back when they get home' — pronoun 'them' is unclear, condition 'when home' is unobservable, future timing.",
        "expects_clarification": True,
    },
    {
        "id": "conditional_groceries_on_way",
        "category": "conditional",
        "difficulty": "hard",
        "seed": "Wearer says 'pick up groceries on the way home' — implicit time (whenever returning), implicit list (no items named), implicit route.",
        "expects_clarification": True,
    },
    # ------- 15-17  MULTI-INTENT STRESS ----------------------------------
    {
        "id": "multi_intent_three_in_one_breath",
        "category": "multi_intent",
        "difficulty": "hard",
        "seed": "Wearer rattles off 'email Sarah about the budget, ping John about the deck, and add a reminder to call mom' in basically one sentence. Three independent intents.",
        "expects_clarification": False,
    },
    {
        "id": "multi_intent_chained_hotel_search",
        "category": "multi_intent",
        "difficulty": "brutal",
        "seed": "Wearer says 'find me three hotels in Asheville under $300, book the cheapest, and email me the receipt'. Chained dependent steps — find, then book, then notify.",
        "expects_clarification": False,
    },
    {
        "id": "multi_intent_meeting_plus_invites",
        "category": "multi_intent",
        "difficulty": "hard",
        "seed": "Wearer says 'schedule a meeting with the design team and send invites with the agenda' — implicit deliverables (which team members? when? agenda content?).",
        "expects_clarification": True,
    },
    # ------- 18-20  PLEASANTRIES THAT LOOK ACTIONABLE --------------------
    {
        "id": "pleasantry_eleven_madison_dinner",
        "category": "pleasantry_specific",
        "difficulty": "hard",
        "seed": "Wearer or friend says 'we should grab dinner at Eleven Madison sometime'. Specific place + vague time = pleasantry, NOT an actionable booking.",
        "expects_clarification": False,
    },
    {
        "id": "pleasantry_coffee_next_week",
        "category": "pleasantry_specific",
        "difficulty": "medium",
        "seed": "Two acquaintances bumping into each other 'let's catch up over coffee next week'. Vague — no concrete day, no place. Pleasantry.",
        "expects_clarification": False,
    },
    {
        "id": "pleasantry_conference_next_year",
        "category": "pleasantry_specific",
        "difficulty": "medium",
        "seed": "Someone tells the wearer 'you should come to the conference next year'. Far future + invitation, no commitment.",
        "expects_clarification": False,
    },
    # ------- 21-23  DELEGATION TRAPS -------------------------------------
    {
        "id": "delegation_sarah_book_room",
        "category": "delegation",
        "difficulty": "hard",
        "seed": "Wearer says 'Sarah, can you book the conference room for 2pm?' — delegated TO Sarah. NOT the wearer's task. Sarah is in the room and acknowledges.",
        "expects_clarification": False,
    },
    {
        "id": "delegation_already_told_john",
        "category": "delegation",
        "difficulty": "hard",
        "seed": "Wearer narrates 'I told John to send the deck, hopefully he does'. Already-delegated, no wearer task. Possibly add a contingent follow-up if John doesn't deliver, but only if the wearer states it.",
        "expects_clarification": False,
    },
    {
        "id": "delegation_marcus_contract",
        "category": "delegation",
        "difficulty": "hard",
        "seed": "Wearer says 'Marcus, handle the contract review please' — direct delegation. Marcus may be on the call. Not the wearer's task.",
        "expects_clarification": False,
    },
    # ------- 24-26  RETRACTION PATTERNS ----------------------------------
    {
        "id": "retraction_la_flight_never_mind",
        "category": "retraction",
        "difficulty": "hard",
        "seed": "Wearer says 'book a flight to LA. Actually, never mind, I'll do it later.' Net intent on the flight: zero. Retraction trigger goes in noise.",
        "expects_clarification": False,
    },
    {
        "id": "retraction_picnic_pivot_noon_two",
        "category": "retraction",
        "difficulty": "hard",
        "seed": "Wearer says 'move the picnic to noon. Wait, scratch that, leave it at 2pm.' Pivot — the move is retracted, original time stays. Net intent: probably zero (or 'leave at 2pm' confirmation).",
        "expects_clarification": False,
    },
    {
        "id": "retraction_email_to_call_pivot",
        "category": "retraction",
        "difficulty": "hard",
        "seed": "Wearer says 'email Sarah about the proposal. Hold on, I'll just call her instead.' Email retracted, call is the surviving intent.",
        "expects_clarification": False,
    },
    # ------- 27-30  PERSONAL/FAMILY MODE MIXED TASKS ---------------------
    {
        "id": "family_dinner_milk_run",
        "category": "family_mixed",
        "difficulty": "medium",
        "seed": "Family dinner. Wearer says 'I'll grab the milk on the way home tomorrow'. Spouse/kids chatter is noise. ONE concrete wearer task.",
        "expects_clarification": False,
    },
    {
        "id": "family_kids_bedtime_delegation",
        "category": "family_mixed",
        "difficulty": "medium",
        "seed": "Wearer (parent) tells kids 'bedtime by 9 tonight, no exceptions'. Delegation to kids — not a wearer task, but the wearer might set a 9pm bedtime check reminder.",
        "expects_clarification": False,
    },
    {
        "id": "family_honey_check_laundry",
        "category": "family_mixed",
        "difficulty": "medium",
        "seed": "Wearer says 'honey, can you check on the laundry?' Spouse delegation. Wearer separately says 'oh and I'll empty the dishwasher in a sec' — that IS a wearer task but it's domestic and immediate.",
        "expects_clarification": False,
    },
    {
        "id": "family_mixed_homework_plus_grocery",
        "category": "family_mixed",
        "difficulty": "medium",
        "seed": "Family scene with kid asking for homework help (delegated to spouse), plus wearer saying 'I'll add eggs and bread to the shopping list for tomorrow' (wearer task).",
        "expects_clarification": False,
    },
    # ------- 31-33  PRIVACY / SENSITIVE ----------------------------------
    {
        "id": "sensitive_doctor_back_pain",
        "category": "sensitive",
        "difficulty": "hard",
        "seed": "Wearer says 'I should schedule a doctor's appointment about my back'. Health context — should be flagged as importance=important, treated with privacy care.",
        "expects_clarification": False,
    },
    {
        "id": "sensitive_pay_rent_first",
        "category": "sensitive",
        "difficulty": "medium",
        "seed": "Wearer says 'pay rent on the 1st'. Financial + recurring. Concrete intent with monthly recurrence.",
        "expects_clarification": False,
    },
    {
        "id": "sensitive_therapy_recurring",
        "category": "sensitive",
        "difficulty": "medium",
        "seed": "Wearer says 'therapy on Tuesdays at 4'. Recurring + sensitive (mental health). Should be marked private/sensitive.",
        "expects_clarification": False,
    },
    # ------- 34-35  BRAINSTORMING (no commitments) -----------------------
    {
        "id": "brainstorm_graphql_exploration",
        "category": "brainstorm",
        "difficulty": "hard",
        "seed": "Two engineers chatting 'we should explore using GraphQL for the new service' — pure discussion, no decision, no concrete next step.",
        "expects_clarification": False,
    },
    {
        "id": "brainstorm_whistler_offsite",
        "category": "brainstorm",
        "difficulty": "hard",
        "seed": "Wearer says 'what if we did a winter offsite in Whistler?' — hypothetical. No booking, no decision.",
        "expects_clarification": False,
    },
    # ------- 36-40  AMBIENT / NOISE ZERO INTENT --------------------------
    {
        "id": "ambient_cafe_noise_zero",
        "category": "ambient_zero",
        "difficulty": "easy",
        "seed": "Cafe scene — barista calls, espresso machine, music, neighboring table chatter. Wearer is silent or makes only pleasantries. ZERO intents.",
        "expects_clarification": False,
    },
    {
        "id": "ambient_baby_crying_intermittent",
        "category": "ambient_zero",
        "difficulty": "easy",
        "seed": "Baby crying intermittently. Wearer talking gently to baby, partner makes small comments. No tasks. ZERO intents.",
        "expects_clarification": False,
    },
    {
        "id": "ambient_dog_barking_park",
        "category": "ambient_zero",
        "difficulty": "easy",
        "seed": "At the park, dog barking, kids playing, brief stranger interaction. Wearer makes only weather/pleasantry talk. ZERO intents.",
        "expects_clarification": False,
    },
    {
        "id": "ambient_tv_background_chatter",
        "category": "ambient_zero",
        "difficulty": "easy",
        "seed": "TV running in background (news anchor, ads), wearer half-watching, occasional comment 'ugh this guy'. Bystander/anchor speech is noise. ZERO wearer intents.",
        "expects_clarification": False,
    },
    {
        "id": "ambient_subway_announcements",
        "category": "ambient_zero",
        "difficulty": "easy",
        "seed": "On the subway — PA announcements, fellow passengers, wearer scrolling silently. ZERO wearer-actionable items.",
        "expects_clarification": False,
    },
    # ------- 41-45  MULTI-DAY CROSS-SESSION REFERENCES -------------------
    {
        "id": "cross_session_gucci_shoes",
        "category": "cross_session",
        "difficulty": "brutal",
        "seed": "Wearer says 'I told you yesterday about the Gucci shoes, did you order them?' — references a prior-day commitment. Engine must use cross-session memory to resolve. The intent is to follow up / order if not done.",
        "expects_clarification": False,
    },
    {
        "id": "cross_session_yesterday_proposal",
        "category": "cross_session",
        "difficulty": "brutal",
        "seed": "Wearer says 'remember the proposal we talked about yesterday for client X — let's send it today'. Cross-session reference, intent NOW.",
        "expects_clarification": False,
    },
    {
        "id": "cross_session_last_week_dentist",
        "category": "cross_session",
        "difficulty": "hard",
        "seed": "Wearer says 'last week I said I'd reschedule the dentist — I still haven't done it, do it today'. Cross-session pull-forward.",
        "expects_clarification": False,
    },
    {
        "id": "cross_session_morning_followup",
        "category": "cross_session",
        "difficulty": "hard",
        "seed": "Wearer says 'this morning I said I'd ping the recruiter — let me actually do that now'. Same-day cross-conversation reference.",
        "expects_clarification": False,
    },
    {
        "id": "cross_session_anniversary_gift",
        "category": "cross_session",
        "difficulty": "hard",
        "seed": "Wearer says 'I told my partner two days ago I'd order the anniversary gift — totally forgot. Doing it now'. Cross-session, surfacing a stale commitment.",
        "expects_clarification": False,
    },
    # ------- 46-50  PURE ZERO-INTENT VARIANTS ----------------------------
    {
        "id": "zero_intent_pure_pleasantries",
        "category": "zero_intent",
        "difficulty": "easy",
        "seed": "Pure pleasantries — bumping into a colleague in the elevator. Weather, weekend, family-pleasantries. ZERO intents, ZERO commitments.",
        "expects_clarification": False,
    },
    {
        "id": "zero_intent_pure_ambient",
        "category": "zero_intent",
        "difficulty": "easy",
        "seed": "Wearer alone, ambient noises only — keyboard typing, sip of coffee, occasional sigh. Maybe a hum. ZERO intents.",
        "expects_clarification": False,
    },
    {
        "id": "zero_intent_work_no_actions",
        "category": "zero_intent",
        "difficulty": "medium",
        "seed": "Work conversation — recap of yesterday's meeting, observations, jokes. No promises, no follow-ups, no commitments. ZERO wearer actions.",
        "expects_clarification": False,
    },
    {
        "id": "zero_intent_family_chitchat",
        "category": "zero_intent",
        "difficulty": "easy",
        "seed": "Family dinner — recapping the day, kids' funny moments, school anecdotes. No tasks anyone needs to do. ZERO wearer intents.",
        "expects_clarification": False,
    },
    {
        "id": "zero_intent_walking_alone",
        "category": "zero_intent",
        "difficulty": "easy",
        "seed": "Wearer walking alone — internal mutters, observations about the neighborhood, a couple of 'hmms'. No actions. ZERO intents.",
        "expects_clarification": False,
    },
    # ------- 51-60  REAL-ACTION HALF TESTS (full slots) ------------------
    {
        "id": "real_action_wikipedia_einstein_birthyear",
        "category": "real_action",
        "difficulty": "easy",
        "seed": "Wearer says 'search Wikipedia for Albert Einstein's birth year'. Concrete, full slots — site=Wikipedia, query=Einstein, target=birth year.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_iceland_population_ddg",
        "category": "real_action",
        "difficulty": "easy",
        "seed": "Wearer says 'find the population of Iceland on duckduckgo'. Full slots: site=DuckDuckGo, query=population of Iceland.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_hackernews_top",
        "category": "real_action",
        "difficulty": "easy",
        "seed": "Wearer says 'open Hacker News and find the top story title'. Site=HN, target=top story title.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_youtube_lofi",
        "category": "real_action",
        "difficulty": "easy",
        "seed": "Wearer says 'search YouTube for lo-fi study music, report the first video'. Site=YouTube, query=lo-fi study music, target=first result.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_google_flights_nyc_la",
        "category": "real_action",
        "difficulty": "medium",
        "seed": "Wearer says 'compare flight prices on Google Flights from NYC to LA on Friday return Sunday'. Full slots with dates relative to today.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_amazon_wireless_mouse",
        "category": "real_action",
        "difficulty": "medium",
        "seed": "Wearer says 'find a wireless mouse under $30 on Amazon with 4+ stars'. Full slots: site=Amazon, product, price ceiling, rating filter.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_gcal_meeting_2pm",
        "category": "real_action",
        "difficulty": "medium",
        "seed": "Wearer says 'schedule a meeting in Google Calendar for tomorrow 2pm'. Full slots: app, date, time. (Title is mildly underspecified but acceptable.)",
        "expects_clarification": False,
    },
    {
        "id": "real_action_gdocs_q3_report",
        "category": "real_action",
        "difficulty": "easy",
        "seed": "Wearer says 'open Google Docs and start a new doc titled Q3 Report'. Full slots: app=Google Docs, title='Q3 Report'.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_bbc_headline",
        "category": "real_action",
        "difficulty": "easy",
        "seed": "Wearer says 'find the headline on bbc.com/news'. Full slots: URL given, target=headline.",
        "expects_clarification": False,
    },
    {
        "id": "real_action_tokyo_weather",
        "category": "real_action",
        "difficulty": "easy",
        "seed": "Wearer says 'look up the weather in Tokyo'. Full slots: target=weather, location=Tokyo. Site can be inferred (any weather source).",
        "expects_clarification": False,
    },
    # ------- 61-100  HARD PRODUCTION CASES (LLM-driven from prompts) -----
    {
        "id": "prod_family_logistics_carpool",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Family logistics — sorting out carpool to soccer Saturday. Mix of delegations to spouse, wearer's own commitment ('I'll grab the orange slices and waters'), and pleasantry chitchat about other parents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_work_meeting_mixed_delegations_owns",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Work standup. Wearer assigns one task to a teammate ('Priya, you take the migration script') AND takes one themselves ('I'll write the rollback doc by Thursday'). Both must be correctly attributed.",
        "expects_clarification": False,
    },
    {
        "id": "prod_errand_list_pharmacy_dry_cleaner",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer narrating an errand list to themselves while driving — pharmacy for refill, dry cleaner pickup, return library books, gas station. 4 concrete intents with implicit ordering.",
        "expects_clarification": False,
    },
    {
        "id": "prod_travel_planning_san_diego",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer planning San Diego trip with partner — concrete: 'book flights for May 22-25 from SFO', 'find a hotel near Balboa Park'. Vague: 'we should hit a beach' (pleasantry). Mixed.",
        "expects_clarification": False,
    },
    {
        "id": "prod_financial_review_taxes",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer reviewing finances — 'send the tax docs to the accountant by Friday', 'transfer $5000 to savings tomorrow', '...we should look at refinancing some day' (last one is vague/noise).",
        "expects_clarification": False,
    },
    {
        "id": "prod_social_birthday_party",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer planning friend's birthday party — RSVP confirmation to send, gift to buy ('something under $50, maybe a candle set'), pickup of cake on Saturday morning. 3 intents, one slightly underspecified gift.",
        "expects_clarification": False,
    },
    {
        "id": "prod_medical_specialist_referral",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer recapping after doctor visit — 'they want me to see a cardiologist, get the referral form Monday, schedule the visit within 2 weeks, also pick up the lisinopril today'. Multiple medical intents with timing.",
        "expects_clarification": False,
    },
    {
        "id": "prod_gift_ideas_partners_birthday",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer brainstorming gift ideas for partner's birthday — lots of hypotheticals ('maybe a watch, or that camera lens she mentioned, or a weekend in Sonoma'). Possibly ONE concrete decision at the end ('okay let's go with the camera lens, order it tonight'). Or none.",
        "expects_clarification": False,
    },
    {
        "id": "prod_learning_resources_python",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer telling friend they want to learn Python — 'maybe I'll do that Coursera course' (vague), then concrete 'okay sign me up for the Andrew Ng one tonight'. Mix of vague and concrete.",
        "expects_clarification": False,
    },
    {
        "id": "prod_fitness_goal_5k",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer saying they want to run a 5k in 3 months — 'sign up for the May 18th race today' (concrete), 'I should follow that training plan' (vague), 'maybe get new shoes' (vague).",
        "expects_clarification": False,
    },
    {
        "id": "prod_house_repairs_plumber",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer + spouse discussing house repairs — 'call the plumber about the leak today', 'spouse, can you get a quote on the roof?' (delegation), 'we should repaint the living room sometime' (vague).",
        "expects_clarification": False,
    },
    {
        "id": "prod_pet_vet_appointment",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer notes 'Buddy's overdue for shots, schedule a vet appointment this week, pick up the heartworm meds at the pharmacy on Friday'. Two concrete pet-care intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_book_club_logistics",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer organizing book club — 'send the reading list to the group chat tonight', 'reserve the back room at the cafe for next Thursday', 'pick up snacks day-of'. Three intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_volunteer_signup_clarify",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer says 'I want to volunteer at the food bank' — no specific date, no role, no shift. Underspecified — should ask clarifying questions.",
        "expects_clarification": True,
    },
    {
        "id": "prod_subscription_renew_decision",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer reviewing 'NYT renews next week — keep it', 'cancel Spotify family' (concrete), 'maybe drop one of the streaming things' (vague — which one?).",
        "expects_clarification": True,
    },
    {
        "id": "prod_school_permission_slip",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer (parent) — 'sign the field trip permission slip tonight', 'pack lunch for Maya tomorrow', 'remember to pay the after-school program by Friday'. Three school-related intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_freelance_invoice_chase",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Freelancer wearer — 'send invoice to ClientCo today', 'follow up on the overdue Acme invoice', 'set up a recurring monthly invoice for the retainer client'. Three intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_car_maintenance_oil_tires",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer noting car needs — 'schedule oil change for next Saturday', 'buy new wiper blades online', 'check tire pressure tomorrow morning'. Three car intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_immigration_paperwork",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer dealing with visa renewal — 'fill out the I-765 by next Tuesday', 'gather pay stubs from last 6 months', 'schedule biometrics appointment'. Three concrete bureaucratic intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_wedding_planning_florist",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer planning a wedding — 'finalize florist contract Friday', 'send save-the-dates by end of month', 'taste-test bakery on Saturday at 2pm'. Three intents with dates.",
        "expects_clarification": False,
    },
    {
        "id": "prod_apartment_move_logistics",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer prepping for move — 'book movers for May 14', 'cancel internet at old place after move', 'change address with USPS this week'. Three intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_charity_donation_year_end",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer year-end giving — 'donate $500 to local food bank by Dec 31', 'set up monthly recurring to ACLU', 'we should look at the local shelter sometime' (last one vague).",
        "expects_clarification": False,
    },
    {
        "id": "prod_tech_support_router",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer dealing with home tech — 'restart the router tonight if it's still slow', 'call Comcast tomorrow morning if not fixed', 'order a mesh network if the Comcast call doesn't help' (chained conditional intents).",
        "expects_clarification": False,
    },
    {
        "id": "prod_reading_list_curation",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer + friend swapping book recs — 'add Project Hail Mary to my list' (concrete), 'maybe read more nonfiction' (vague), 'order the Sapiens audiobook tonight' (concrete). Mixed.",
        "expects_clarification": False,
    },
    {
        "id": "prod_recurring_meditation_streak",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer reflecting — 'I want to meditate every morning at 7' (recurring habit), 'set the daily alarm tonight'. One recurring habit intent + one setup intent.",
        "expects_clarification": False,
    },
    {
        "id": "prod_neighborhood_complaint",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer + neighbor venting about a noise complaint — 'I'll file a 311 report tomorrow' (concrete), neighbor says 'I'll talk to the landlord' (delegation, NOT wearer task). One wearer intent.",
        "expects_clarification": False,
    },
    {
        "id": "prod_calendar_conflict_resolution",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer notices conflict — 'I have a 3pm and the dentist at 3:30, move the dentist to 4:30 if they have it' (conditional), 'and tell Jamie I'll be 15 minutes late to dinner'. Two intents, one conditional.",
        "expects_clarification": False,
    },
    {
        "id": "prod_subscribe_newsletter_research",
        "category": "production_hard",
        "difficulty": "easy",
        "seed": "Wearer says 'subscribe me to Stratechery' (concrete site), 'sign up for that AI newsletter someone mentioned' (vague — which one?). One concrete, one underspecified.",
        "expects_clarification": True,
    },
    {
        "id": "prod_legal_lawyer_followup",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer post legal call — 'send the signed NDA to counsel by EOD Friday', 'review the term sheet draft this weekend', 'schedule a follow-up call for next Wednesday at 11am'. Three concrete legal intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_hr_benefits_enrollment",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer doing open enrollment — 'pick the high-deductible plan by Friday', 'increase 401k contribution to 12%', 'enroll in the FSA for $2000'. Three benefit intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_party_potluck_signup",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer organizing potluck — 'sign up to bring the salad on the shared spreadsheet tonight', 'remind everyone in the group chat tomorrow morning', 'pick up serving bowls Saturday'. Three intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_blog_post_draft",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer creator — 'finish the draft of the LLM evals post by Thursday', 'commission a header image from the designer', 'schedule the Substack publish for Friday 8am'. Three intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_garden_seedlings_planning",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer gardener — 'order tomato seedlings from Burpee by tonight', 'water the basil tomorrow morning', 'we should expand the herb bed someday' (vague).",
        "expects_clarification": False,
    },
    {
        "id": "prod_software_pr_review",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Engineer wearer — 'review Priya's PR by EOD', 'leave comments on the design doc by tomorrow', 'merge the migration tonight if CI green' (conditional). Three intents, one conditional.",
        "expects_clarification": False,
    },
    {
        "id": "prod_kid_birthday_party_invites",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer parent — 'send out kids party invites by Sunday', 'order the cake from Magnolia by Wednesday', 'reserve the trampoline park for next Saturday 2pm'. Three intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_freezer_shopping_meal_prep",
        "category": "production_hard",
        "difficulty": "medium",
        "seed": "Wearer doing meal prep — 'order chicken and broccoli on Instacart for Sunday delivery', 'meal prep on Sunday afternoon', 'maybe try a new recipe' (vague). Two concrete + one vague.",
        "expects_clarification": False,
    },
    {
        "id": "prod_cross_session_followup_priya",
        "category": "production_hard",
        "difficulty": "brutal",
        "seed": "Wearer says 'last week Priya asked me to look over the architecture doc — I haven't, do it now'. Cross-session pulled-forward stale commitment.",
        "expects_clarification": False,
    },
    {
        "id": "prod_relationship_anniversary_combined",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer planning anniversary — 'book Dave's Hot Chicken' (joking, retracted by partner), 'okay actually book Atelier for next Friday 7pm', 'order flowers from local florist for delivery that morning'. Pivot + two real intents.",
        "expects_clarification": False,
    },
    {
        "id": "prod_negotiation_followup",
        "category": "production_hard",
        "difficulty": "hard",
        "seed": "Wearer post-negotiation call — 'send the revised offer to candidate by tomorrow noon', 'loop in the recruiter on the email', 'set up a 30-min call for Friday if they want to discuss' (conditional).",
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
  layer SHOULD extract for the WEARER. 0 to 5 items. ZERO is valid.
- noise_should_NOT_act_on: array of short strings describing transcript
  items that LOOK actionable but are NOT wearer-tasks (delegations,
  retracted statements, conditionals that resolved false, hypotheticals,
  ambient/bystander speech, pleasantries, third-party reported commitments).
- name: short snake_case scenario id, max 6 words.
- difficulty: one of "easy", "medium", "hard", "brutal".
- expected_clarification (ONLY when the seed says expects_clarification=True):
  one-line natural-language question the agent SHOULD ask the wearer to
  resolve missing slots, e.g. "Where from, where to, and what dates?"

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
- Do not reuse names across scenarios; invent diverse plausible names.
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
- Keep transcript between 6 and 30 lines (shorter for ambient/zero-intent OK).
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
                            expects_clarification=pattern.get(
                                "expects_clarification", False
                            ),
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

    required = (
        "name",
        "difficulty",
        "transcript",
        "expected_intents",
        "noise_should_NOT_act_on",
    )
    if not all(k in sc for k in required):
        if attempt < 2:
            return await gemini_one(pattern, attempt=attempt + 1)
        return None
    if not isinstance(sc["transcript"], list) or len(sc["transcript"]) < 4:
        if attempt < 2:
            return await gemini_one(pattern, attempt=attempt + 1)
    if not isinstance(sc["expected_intents"], list) or not isinstance(
        sc["noise_should_NOT_act_on"], list
    ):
        return None

    # Validate clarification expectation
    if pattern.get("expects_clarification") and "expected_clarification" not in sc:
        if attempt < 2:
            return await gemini_one(pattern, attempt=attempt + 1)

    sc["pattern_id"] = pattern["id"]
    sc["category"] = pattern["category"]
    return sc


async def main() -> int:
    # Load existing names so we don't duplicate
    seen_names: set[str] = set()
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            for line in f:
                if line.strip():
                    try:
                        seen_names.add(json.loads(line)["name"])
                    except Exception:
                        pass
    print(
        f"Existing scenarios: {len(seen_names)}. Generating {len(PATTERNS)} new ones.",
        flush=True,
    )

    sem = asyncio.Semaphore(8)
    results: list[dict] = []
    fail_patterns: list[str] = []

    async def one(pattern: dict, idx: int) -> None:
        async with sem:
            sc = await gemini_one(pattern)
            if sc is None:
                fail_patterns.append(pattern["id"])
                print(
                    f"  [{idx + 1:3}/{len(PATTERNS)}] FAIL pattern={pattern['id']}",
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

    # Append-only write
    with OUT_FILE.open("a") as f:
        for sc in results:
            f.write(json.dumps(sc, ensure_ascii=False) + "\n")

    from collections import Counter

    cats = Counter(s["category"] for s in results)
    diffs = Counter(s["difficulty"] for s in results)
    print(f"\nAppended {len(results)} scenarios → {OUT_FILE}")
    print(f"  category counts: {dict(cats)}")
    print(f"  difficulty counts: {dict(diffs)}")
    if fail_patterns:
        print(f"  failed patterns: {fail_patterns}")

    # Final overall
    total = 0
    if OUT_FILE.exists():
        with OUT_FILE.open() as f:
            total = sum(1 for line in f if line.strip())
    print(f"  TOTAL scenarios in file: {total}")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
