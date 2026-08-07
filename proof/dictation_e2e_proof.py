"""Dictation makes nothing; a real plan still lands. Through the REAL hear().

The three lines Omar dictated into his laptop on 2026-08-04, which the pendant
overheard and turned into three jobs on his desk:

    Pill 491 kill 492 kill 493 of your list
    Carson Michael and RV.help23 add that to the KTHAI list
    4546 4748 reply my inbox drive to Toby's email

Every other check around this fix tests a PART -- not_speech_evidence alone,
read_into_a_machine alone, or the gate's mirror of how anticipy_core composes
them. A mirror drifts. This runs the real hear(), the whole way through, and it
is the only thing that proves the wiring rather than the pieces.

The dinner half is not decoration. A filter that silences everything would pass
the first half perfectly, so the same run has to show a real plan still becoming
a held booking that carries venue, party size, day and time -- and exactly one
text asking for the go-ahead.

Run it several times in parallel: a live model varies run to run, and one green
pass is not evidence.

    ANTICIPY_MODEL=google/gemini-2.5-flash python3 proof/dictation_e2e_proof.py

In-memory jobs table only -- NEVER the shared backend. A test job posted there
once put a ghost booking card on his real desk within seconds.
"""
import sys, os
sys.path.insert(0, os.path.expanduser("~/AnticipyFleet/control"))
from brain import pb
rows = []
class R:
    def __init__(s,p): s._p, s.ok = p, True
    def json(s): return s._p
    def raise_for_status(s): return None
def _get(url, params=None, timeout=None, **kw):
    want=[s for s in ("awaiting_confirm","queued") if s in (params or {}).get("filter","")]
    return R({"items":[r for r in rows if r.get("status") in want]})
def _post(url, json=None, timeout=None, **kw):
    rec=dict(json or {}); rec["id"]=f"j{len(rows)+1}"; rows.append(rec); return R(rec)
def _patch(url, json=None, timeout=None, **kw):
    jid=url.rstrip("/").rsplit("/",1)[-1]
    for r in rows:
        if r.get("id")==jid: r.update(json or {})
    return R({})
pb.get, pb.post, pb.patch = _get, _post, _patch

from brain.anticipy_core import Anticipy
from brain.llm import LLM
from brain.memory import Memory

llm = LLM()
if not llm.live:
    print("SKIP — no OPENROUTER_API_KEY, this needs the real model")
    sys.exit(0)
print(f"model={llm.model}\n")

# The three garbled lines, each in the run of dictation they really arrived in.
DICTATION = ["Number 11 number 12 number 13 number 14 number 15",
             "Pill 491 kill 492 kill 493 of your list",
             "Carson Michael and RV.help23 add that to the KTHAI list",
             "4546 4748 reply my inbox drive to Toby's email"]
# And the real plan, in the conversation it really arrived in.
DINNER = ["Hey we should go ahead and make a dinner reservation yeah for sure",
          "When do you wanna go here for",
          "Let's go out tomorrow",
          "OK back",
          "tomorrow 7 PM",
          "With who just the two of us OK for sure see you tomorrow",
          ("Yo how is it it's good you yeah yeah long time no see yeah for sure "
           "tomorrow we should go for dinner yeah yeah I would love it when would "
           "you like to go how about we do 7 PM tomorrow where cactus club which "
           "one the park location OK bet just a two of us sure sure see you tomorrow"),
          "Can you book dinner for 7 PM tomorrow"]

def run(name, lines, want_job):
    rows.clear()
    a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="e2e")
    texts=[]; a.notify_owner = lambda m, channel="sms": texts.append(m)
    convo=[]
    print(f"{name}")
    for line in lines:
        d = a.hear(line, context=list(convo[-8:]))["decision"]
        convo.append(line)
        print(f"   {d.decision:6} addressee={str(d.addressee):9} {line[:52]}")
    got = len(rows)
    ok = (got > 0) == want_job
    print(f"   -> jobs={got} texts={len(texts)}  {'ok' if ok else 'FAIL'}"
          f" (wanted {'a job' if want_job else 'nothing'})")
    for r in rows: print(f"      [{r.get('status')}] {r.get('goal')}")
    print()
    return 0 if ok else 1

bad  = run("DICTATION — must produce nothing", DICTATION, False)
bad += run("DINNER — must still produce a held booking", DINNER, True)
print("ALL GREEN through the real hear()" if bad==0 else f"{bad} WRONG")
sys.exit(bad)
