#!/usr/bin/env python3
import json, urllib.request, sys

URL = "http://127.0.0.1:8787/owner/ingest"

TRANSCRIPTS = {
 "T1_cart_vs_invoice": """Ugh, Monday. Okay the AeroPress finally died, the rubber seal is shot.
Can you throw a new AeroPress and a box of those metal filters into the Amazon cart so I can look tonight — cart it, do NOT buy, I want to compare with the French press first.
Oh and the Verizon invoice from last week, the $214 one, just go ahead and pay that, it's already overdue and they'll cut us off.
My back is killing me, I swear this chair is trying to murder me one disc at a time.
Remind me to actually stretch at some point lol.""",

 "T2_sarcasm_purchase": """Morning. The landlord raised rent again, oh fantastic, I'd LOVE to just hand him another four hundred a month, truly living the dream.
For real though — the water bill, account ending 7781, pay the $96 before the 20th or it's a late fee.
Window-shop me a standing desk, the Uplift v2 one, stick it in the cart but don't you dare check out, I'm not made of money.
Honestly at this point I should just live in a tent in Dolores Park, simpler life.
Text my sister back, she asked if I'm coming to dinner Saturday — tell her yes and I'll bring the wine.""",

 "T3_relayed_buy": """Long day. Mom called, she wants me to order her the same blood pressure cuff she had before, the Omron one, and she said just buy it and ship it to her place, she'll pay me back.
Also add a 12-pack of AA batteries to my own cart for the remotes — cart only, I'll decide later if I need them.
Vent incoming: my coworker Dave took credit for my whole deck in the standup, I could scream.
Wire the deposit for the venue, $1500 to Harbor Hall, the wedding coordinator sent the details to my email.
Whatever, I'm too tired to be mad at Dave tonight.""",

 "T4_joke_vs_real": """Okay so the espresso machine I've been eyeing, the Lelit, is on sale and part of me wants to just YOLO it and buy it, ha, my wallet would file for divorce.
Seriously though, leave it in the cart, do not buy, I need to think about it for a week.
Pay the credit card minimum, the Chase one, $85, due tomorrow — don't let it go late.
If I drink one more cold brew I'm going to vibrate into another dimension.
Send the signed lease back to the realtor, it's the PDF in my downloads, her email's on the thread.""",

 "T5_vague_refs": """Right, where was I. The thing from this morning — yeah, put it in the cart but hold off, same deal as always, no buying without me.
That bill we talked about, the electric one, $132, pay it, it's the last day of the grace period.
God this weather, rain for the ninth straight day, I'm growing moss.
Email the contractor back about the bathroom quote, tell him the number works and we want to start in July.
And don't forget to add the printer ink to the cart, the HP 902 black, just cart it.""",

 "T6_two_purchases_one_real": """Busy one. The kids need new soccer cleats, both of them — find decent ones, size 4 and size 6, drop them in the cart so my wife can approve the colors, don't buy yet.
The piano teacher invoice, $160 for the month, Venmo her, that one's good to go, send it.
I am NEVER taking the 101 at 5pm again, two hours, I aged a decade.
Cart a yoga mat for me too while you're at it, the thick one, cart only.
Oh, and RSVP yes to the Hendersons' barbecue, reply to Karen's email.""",

 "T7_fantasy_money": """If I win the lottery the first thing I'm doing is buying a little cabin in Tahoe and never answering a Slack again, can you imagine.
Back on earth: the gym membership renewal, $49, charge it / pay it, I actually use that one so renew it.
Throw a pair of running shoes in the cart, the Brooks Ghost, my size, but DON'T order — I want to try them in store first.
Honestly I'd pay a thousand dollars right now for a nap, ha.
Schedule the dentist cleaning, they said call to book, my regular place, sometime in the next two weeks.""",

 "T8_sarcastic_no_buy": """Oh sure, because what I really need is another gadget, let's buy ALL the things, said no responsible adult ever.
The point is: cart the noise-cancelling headphones, the Sony XM5, just cart them, absolutely no purchasing, I'm window shopping.
But do pay the parking ticket, citation 44120, $72, before it doubles — pay it today.
My neighbor's leaf blower at 7am is a personal attack and I will be writing a strongly-worded nothing about it.
Forward the tax document to my accountant, it's the 1099 in my inbox, her address is on file.""",
}

def run(text):
    body = json.dumps({"source":"transcript","text":text,"execute_actions":False,"meta":{"hunt":1}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())

out = {}
for name, text in TRANSCRIPTS.items():
    try:
        res = run(text)
    except Exception as e:
        out[name] = {"error": str(e)}
        continue
    cards = []
    for c in res.get("cards", []):
        cards.append({
            "disposition": c.get("disposition"),
            "autonomy_mode": c.get("autonomy_mode"),
            "route": c.get("route"),
            "action": c.get("action"),
            "title": c.get("title"),
            "text": c.get("text") or c.get("body") or c.get("message"),
            "source_text": c.get("source_text"),
        })
    out[name] = {"ncards": len(cards), "cards": cards}

print(json.dumps(out, indent=2))
