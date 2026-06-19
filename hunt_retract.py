#!/usr/bin/env python3
import json, urllib.request, sys

URL = "http://127.0.0.1:8787/owner/ingest"

# 8 distinct messy day transcripts focused on retractions/changed-mind and self-cancel hedges,
# laced with sarcasm, vents, jokes, vague refs, relayed requests, money, sends.
TRANSCRIPTS = {
    "T1_landlord_retract": """Ugh the radiator's been clanking all night again, I swear this building is held together with tape.
Email the landlord about the heat — actually no, never mind, I'll just call him later, forget the email.
Oh and I'm SO going to win the lottery this weekend, gonna buy the whole block, watch.
Can you put trash night on Thursday, the bins, every week.
Honestly if it clanks one more time I'm going to throw it out the window.""",

    "T2_wire_hedge": """My brother keeps bugging me about the trip money.
I should probably wire him the 500 for the cabin deposit... probably, I don't know, maybe.
Actually hold on, let me check with him on the amount first before anything moves.
Add a note that the cabin is the second weekend of July.
God, splitting money with family is a nightmare, I'd rather set it all on fire.""",

    "T3_email_boss_changedmind": """Set up the 1:1 with my manager for Friday afternoon, 3pm works.
Email Dana the Q3 numbers — no wait, scratch that, she already has them, don't send anything.
I could just quit and become a goat farmer at this point lol.
Remind me to take my meds at 8pm tonight, that one's non-negotiable.
Maybe I'll reply to the recruiter... eh, probably not, leave it.""",

    "T4_relay_buy_retract": """Sarah asked if I could order more of the printer toner for the office.
So order the toner — hmm, actually let me confirm the model number with her first, don't buy it yet.
The printer is basically a paperweight that occasionally prints, what a joke.
Book the dentist cleaning for next week, any morning slot.
Tell my mom I'll call her Sunday — actually never mind, I'll just text her myself.""",

    "T5_double_cancel": """Cancel my gym membership, I never go — wait no, January's coming, keep it, don't cancel.
Schedule the car for an oil change Saturday morning.
I'd kill for a vacation right now, just disappear to an island.
Pay the electric bill — uh, actually it's on autopay already, ignore that.
Probably should water the plants before they stage a revolt, remind me tonight.""",

    "T6_vague_send_retract": """That thing from this morning, can you just send it over to him.
Actually you know what, don't, I'll handle it, forget I said anything.
The deck for Monday's review needs the new logo, remind me to swap it Friday.
If this client emails one more 'quick question' I'm going to lose it.
Venmo Jake the 40 for lunch — actually he owes ME, never mind, drop it.""",

    "T7_buy_then_keep": """Buy the standing desk off Amazon, the one I had in the cart, the black one.
Hmm actually let me sleep on it, don't order it tonight.
Set a reminder to follow up with the contractor about the kitchen quote on Wednesday.
This contractor ghosts harder than my exes, unbelievable.
Refill my prescription at the pharmacy — that one yes, do that, it's almost out.""",

    "T8_charity_relay_hedge": """My coworker wants me to donate to her marathon fundraiser, $50.
I'll probably donate... probably, but check the link is legit first, don't pay anything yet.
Block 30 minutes tomorrow morning for deep work, no meetings.
The new office coffee tastes like burnt regret, someone should be arrested.
Forward the lease PDF to my partner — yeah send that one to Alex, that's fine.""",
}

def post(text):
    body = json.dumps({"source":"transcript","text":text,"execute_actions":False,"meta":{"hunt":1}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())

out = {}
for name, text in TRANSCRIPTS.items():
    try:
        resp = post(text)
        cards = []
        for c in resp.get("cards", []):
            cards.append({
                "title": c.get("title"),
                "disposition": c.get("disposition"),
                "autonomy_mode": c.get("autonomy_mode"),
                "route": c.get("route"),
                "action": c.get("action"),
                "source_text": c.get("source_text"),
                "reason": c.get("reason"),
            })
        out[name] = {"cards": cards, "ignored": resp.get("ignored_line_count"),
                     "observed": [(l.get("text"), l.get("moat_task"), l.get("force_ask")) for l in resp.get("observed_lines",[])]}
    except Exception as e:
        out[name] = {"error": str(e)}

print(json.dumps(out, indent=2))
