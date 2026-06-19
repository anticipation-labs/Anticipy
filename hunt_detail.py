#!/usr/bin/env python3
import json, urllib.request

URL = "http://127.0.0.1:8787/owner/ingest"
from hunt_retract import TRANSCRIPTS

def post(text):
    body = json.dumps({"source":"transcript","text":text,"execute_actions":False,"meta":{"hunt":1}}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode())

# Focus: which observed lines became cards vs got dropped, and full card text/args/wording.
for name in ["T1_landlord_retract","T2_wire_hedge","T4_relay_buy_retract","T6_vague_send_retract","T8_charity_relay_hedge"]:
    resp = post(TRANSCRIPTS[name])
    print("="*70)
    print(name)
    print("OBSERVED LINES:")
    for l in resp.get("observed_lines",[]):
        print(f"   moat={l.get('moat_task')} ask={l.get('force_ask')} :: {l.get('text')}")
    print(f"ignored_line_count={resp.get('ignored_line_count')}")
    print("CARDS:")
    for c in resp.get("cards",[]):
        print(f"   [{c.get('disposition')}/{c.get('autonomy_mode')}] title={c.get('title')!r}")
        print(f"        src={c.get('source_text')!r} route={c.get('route')} action={c.get('action')} conf={c.get('confidence')}")
        print(f"        args={c.get('args')}")
    # middle trace resolutions to understand retraction handling
    mt = resp.get("middle_trace",{})
    if mt.get("resolutions"):
        print("RESOLUTIONS:", json.dumps(mt["resolutions"]))
    print("CAPTURED:", [ (m.get('text'), m.get('kind')) for m in mt.get('captured_memories',[]) ])
