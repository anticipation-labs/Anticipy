import json, urllib.request, sys

URL = "http://127.0.0.1:8787/owner/ingest"

def run(text):
    body = json.dumps({"source":"transcript","text":text,"execute_actions":False,"meta":{"hunt":1}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

TRANSCRIPTS = {
 "T1_shoes_vs_invoice": """Ugh Mondays. Okay assistant, those Nike Pegasus I was eyeing — cart them on Amazon but DO NOT buy them, I wanna think about it.
My back is killing me, I could murder for a massage but whatever.
Oh and pay the AC repair invoice, it's the $420 one from CoolBreeze, that one's actually due today.
If the Knicks lose again I'm canceling my whole life lol.""",

 "T2_groceries_and_wire": """Morning. Add the usual oat milk and eggs to the Instacart cart, just cart it though, don't check out, I'll review tonight.
I swear if Greg sends one more 'circle back' email I'm gonna lose it.
Also wire the $1,800 to the landlord for rent, account's the Chase one ending 4471.
Remind me to call mom Sunday.""",

 "T3_vent_then_real_buy": """I am SO done with this job, I should just buy a one-way ticket to Bali and never come back honestly.
Okay for real though — go ahead and buy the printer ink, the HP 63 black, just order it, we're totally out.
Cart the standing desk I sent you the link for but hold off on buying, gotta measure first.
Dave owes me twenty bucks, he's such a deadbeat.""",

 "T4_relayed_and_pay": """Sarah texted, she wants me to send her the Q3 deck before noon — can you email that to her.
Don't actually buy the monitor, just stick it in the cart so I see the total.
Pay the credit card bill, the Amex, full balance, it's like $1,240.
My landlord is a clown, the heat's been broken for a week.""",

 "T5_sarcasm_trap": """Oh sure, let me just spend $5,000 on a new MacBook because money grows on trees, right? Hilarious.
Cart the AirPods Pro though, the real ones, but don't buy, just hold them.
Actually do pay the electric bill before the 18th or they shut it off, it's ConEd, $96.
I'd kill for a vacation.""",

 "T6_two_accounts": """Cart the kids' soccer cleats on Amazon, size 4, don't purchase yet, gotta confirm size with my wife.
Send the wire for the contractor deposit, $3,000, but use the BUSINESS account not my personal one.
If I have to sit through one more all-hands I'm walking into the sea.
Save that I prefer aisle seats on flights.""",

 "T7_joke_buy_real_send": """If I win the lottery I'm buying the whole block, every house, cash. Imagine.
Real talk: forward the signed lease PDF to my agent Priya, she's been waiting.
Add the protein powder to the cart, chocolate, but don't buy it, checking if it's cheaper at Costco.
Settle the dog groomer's invoice, $75, Venmo to Bark Ave Grooming.""",

 "T8_vague_refs_and_pay": """That thing from yesterday — yeah cart it, the blender, but don't buy it, I'm still comparing.
Ngl I kinda wanna just rage-quit and open a taco truck.
Pay her back, you know, the $60 I owe Jess for the concert tickets, Venmo is fine.
Can you also just put the vitamins in the cart, don't order, I'll decide later.""",
}

results = {}
for name, text in TRANSCRIPTS.items():
    try:
        res = run(text)
    except Exception as e:
        print(f"=== {name} : ERROR {e}")
        continue
    results[name] = res
    print("="*90)
    print(f"### {name}")
    print("--- observed_lines ---")
    for ol in res.get("observed_lines", []):
        print(f"  L{ol['line_no']}: {ol['text']!r} force_ask={ol.get('force_ask')} moat={ol.get('moat_task')}")
    print(f"  ignored_line_count={res.get('ignored_line_count')}")
    print("--- cards ---")
    for c in res.get("cards", []):
        print(f"  [{c.get('disposition')}|{c.get('autonomy_mode')}|route={c.get('route')}|act={c.get('action')}]")
        print(f"     title : {c.get('title')!r}")
        print(f"     src   : {c.get('source_text')!r}")
        print(f"     reason: {c.get('reason')!r}")
        args = c.get('args') or {}
        if 'payment_allowed' in args:
            print(f"     payment_allowed={args.get('payment_allowed')}")
    if not res.get("cards"):
        print("  (no cards)")

with open("/Users/omarebrahim/Desktop/Anticipy-executor-working/hunt_out.json","w") as f:
    json.dump(results, f, indent=2)
print("\nWROTE hunt_out.json")
