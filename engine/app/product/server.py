"""Local product backend: real conversational onboarding (reuses
app.anticipy.onboarding), the real-microphone product loop (real
sounddevice capture -> real local parakeet ASR -> real frozen
reasoning via OpenRouter -> proactive_day -> a real proposal), and
the designed single-page UI it serves. No synthetic voice anywhere.
Modifies no frozen code.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Anticipy", version="product-1")

# single-user desktop session (in-process)
_SESS: dict = {"i": 0, "transcript": [], "profile": None}
USER_ID = "anticipy-user"


def _key_ok() -> bool:
    cfg = Path(os.path.expanduser("~/.anticipy/.env"))
    if os.environ.get("OPENROUTER_API_KEY", "").startswith("sk-or-"):
        return True
    if cfg.exists():
        for ln in cfg.read_text().splitlines():
            if ln.strip().startswith("OPENROUTER_API_KEY="):
                v = ln.split("=", 1)[1].strip().strip('"').strip("'")
                if v.startswith("sk-or-"):
                    os.environ["OPENROUTER_API_KEY"] = v
                    return True
    return False


@app.get("/api/state")
def state() -> JSONResponse:
    from app.anticipy.onboarding import INTERVIEW_SCRIPT

    return JSONResponse({
        "key_ok": _key_ok(),
        "onboarded": _SESS["profile"] is not None,
        "profile": _SESS["profile"],
        "total_questions": len(INTERVIEW_SCRIPT),
    })


@app.get("/api/onboarding/start")
def onb_start() -> JSONResponse:
    from app.anticipy.onboarding import INTERVIEW_SCRIPT

    _SESS["i"] = 0
    _SESS["transcript"] = []
    q = INTERVIEW_SCRIPT[0]
    _SESS["transcript"].append({"speaker_id": "AGENT", "text": q})
    return JSONResponse({"question": q, "index": 0,
                         "total": len(INTERVIEW_SCRIPT)})


class Answer(BaseModel):
    answer: str


@app.post("/api/onboarding/answer")
def onb_answer(a: Answer) -> JSONResponse:
    from app.anticipy import onboarding as OB

    script = OB.INTERVIEW_SCRIPT
    _SESS["transcript"].append({"speaker_id": "WEARER",
                                "text": a.answer.strip()})
    _SESS["i"] += 1
    if _SESS["i"] < len(script):
        q = script[_SESS["i"]]
        _SESS["transcript"].append({"speaker_id": "AGENT", "text": q})
        return JSONResponse({"question": q, "index": _SESS["i"],
                             "total": len(script)})
    # all answered -> real profile via the frozen onboarding brain
    prof = asyncio.run(OB.run_intake(_SESS["transcript"], USER_ID))
    pj = {
        "name": prof.name, "role_title": prof.role_title,
        "what_they_do": prof.what_they_do, "people": prof.people,
        "mandate": prof.mandate, "do_not_touch": prof.do_not_touch,
        "comms_prefs": prof.comms_prefs,
        "well_populated": OB.profile_is_well_populated(prof),
    }
    _SESS["profile"] = pj
    return JSONResponse({"done": True, "profile": pj})


@app.post("/api/listen/once")
def listen_once() -> JSONResponse:
    """Capture the REAL microphone, real local ASR, real reasoning,
    real proposal. No synthetic voice. Honest empty result if no
    speech is captured.
    """
    try:
        import numpy as np
        import sounddevice as sd

        from app.audiostack import audio as A

        seconds = 6
        rec = sd.rec(int(seconds * A.SR), samplerate=A.SR, channels=1,
                     dtype="float32")
        sd.wait()
        wav = np.asarray(rec).reshape(-1)
        rms = float(np.sqrt(np.mean(wav ** 2)) or 0.0)
        asr = A.asr_tokens(wav)
        text = (asr.text or "").strip()
        if not text:
            return JSONResponse({
                "transcript": "", "proposal": None, "rms": rms,
                "note": "No speech captured from the microphone. "
                        "Press Listen and speak; nothing synthetic "
                        "is substituted."})

        from app.proactive_day import pipeline
        from app.proactive_day import world as W

        manifest = {"events": [{
            "ev_id": "live", "category": "VERBAL_PROMISE",
            "label": "ACTION", "ts": 9.0, "place": "home",
            "speaker": "WEARER", "text": text, "slots": {},
            "snr_tier": "clean", "reach": "free", "urgency": "hours",
            "world_done_at": None, "world_done": None,
            "cancels_ev": None, "defer_until": None,
            "shorthand_key": None, "expansion": None,
            "first_occurrence": False}]}
        world = W.populated()
        res = pipeline.run_day(manifest, world)
        outcome = res[0].outcome if res else "?"
        proposal = None
        if world.outbound:
            o = world.outbound[0]
            proposal = f"{o.body}"
        return JSONResponse({
            "transcript": text, "rms": rms, "outcome": outcome,
            "proposal": proposal})
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc()[-1500:]})


INDEX = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Anticipy</title>
<link rel=preconnect href=https://fonts.googleapis.com>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel=stylesheet>
<style>
:root{--dark:#0C0C0C;--elev:#161616;--bd:#252525;--cream:#F5F0EB;
--mut:#8A8A8A;--gold:#C8A97E}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--dark);color:var(--cream);
font-family:'Plus Jakarta Sans',-apple-system,sans-serif;
min-height:100vh;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;
background:radial-gradient(60rem 38rem at 50% -12%,rgba(200,169,126,.12),transparent 70%)}
.wrap{position:relative;max-width:680px;margin:0 auto;
padding:0 26px;min-height:100vh;display:flex;flex-direction:column}
nav{display:flex;justify-content:space-between;align-items:center;
height:62px;font-size:11px;letter-spacing:.22em;text-transform:uppercase;
color:var(--mut)}
nav .b{font-family:'DM Serif Display',Georgia,serif;font-size:18px;
color:var(--cream);letter-spacing:normal;text-transform:none}
nav a{color:var(--mut);cursor:pointer;margin-left:22px}
nav a:hover{color:var(--cream)}
.scr{flex:1;display:flex;flex-direction:column;justify-content:center;
padding:34px 0 60px;animation:fade .6s cubic-bezier(.16,1,.3,1)}
@keyframes fade{from{opacity:0;transform:translateY(10px)}to{opacity:1}}
.lab{font-size:11px;letter-spacing:.24em;text-transform:uppercase;
color:var(--gold);margin-bottom:18px}
h1{font-family:'DM Serif Display',Georgia,serif;
font-size:clamp(30px,5.4vw,52px);line-height:1.08;letter-spacing:-.02em}
p.sub{margin-top:16px;color:rgba(245,240,235,.55);font-size:15px;
line-height:1.7;max-width:46ch}
button.cta{margin-top:34px;align-self:flex-start;border:0;
background:var(--cream);color:var(--dark);font:500 14px/1 'Plus Jakarta Sans';
padding:16px 30px;border-radius:100px;cursor:pointer;
transition:.25s}
button.cta:hover{background:var(--gold);transform:translateY(-1px)}
button.cta:disabled{opacity:.4;cursor:not-allowed}
.qa{display:flex;flex-direction:column;gap:14px;margin:8px 0 22px}
.bub{padding:14px 18px;border-radius:16px;font-size:14px;line-height:1.6;
max-width:84%}
.bub.a{background:var(--elev);border:1px solid var(--bd);
align-self:flex-start;border-bottom-left-radius:4px}
.bub.u{background:var(--gold);color:var(--dark);align-self:flex-end;
border-bottom-right-radius:4px}
.row{display:flex;gap:10px;margin-top:8px}
input,textarea{flex:1;background:var(--elev);border:1px solid var(--bd);
color:var(--cream);padding:15px 18px;border-radius:14px;font:400 14px
'Plus Jakarta Sans';outline:none;resize:none}
input:focus,textarea:focus{border-color:rgba(200,169,126,.5)}
.send{border:0;background:var(--cream);color:var(--dark);
padding:0 22px;border-radius:14px;cursor:pointer;font-weight:600}
.orb{width:168px;height:168px;margin:8px auto 0;border-radius:50%;
background:radial-gradient(circle at 50% 45%,rgba(200,169,126,.55),
rgba(200,169,126,.05) 62%,transparent 73%);position:relative}
.orb.on{animation:br 3.6s ease-in-out infinite}
.orb i{position:absolute;inset:34%;border-radius:50%;
background:rgba(200,169,126,.85);box-shadow:0 0 60px rgba(200,169,126,.45)}
@keyframes br{0%,100%{transform:scale(.95);opacity:.85}
50%{transform:scale(1.06);opacity:1}}
.center{text-align:center}
.card{background:var(--elev);border:1px solid var(--bd);
border-radius:20px;padding:30px;text-align:left;margin-top:26px}
.card h2{font-family:'DM Serif Display',serif;font-size:23px;
line-height:1.3;font-weight:400}
.meta{margin-top:14px;font-size:12.5px;color:rgba(245,240,235,.45);
line-height:1.6}
.kv{display:grid;gap:1px;background:var(--bd);border-radius:16px;
overflow:hidden;margin-top:8px}
.kv>div{background:var(--elev);padding:14px 18px}
.kv b{font-size:13px;color:rgba(245,240,235,.85);font-weight:600}
.kv span{display:block;margin-top:4px;font-size:12.5px;
color:rgba(245,240,235,.5)}
.muted{color:var(--mut);font-size:12.5px;margin-top:14px}
</style></head><body><div class=wrap>
<nav><span class=b>Anticipy</span><span><a onclick="go('listen')">Listen</a>
<a onclick="go('settings')">Settings</a></span></nav>
<div id=app class=scr></div></div>
<script>
const app=document.getElementById('app');let ST={};
async function J(u,o){const r=await fetch(u,o);return r.json()}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
async function boot(){ST=await J('/api/state');
 if(!ST.key_ok)return scrKey();
 if(!ST.onboarded)return scrWelcome();go('listen')}
function scrKey(){app.innerHTML=`<div class=lab>Setup</div>
<h1>Connect Anticipy.</h1><p class=sub>Paste your OpenRouter key so
Anticipy can think. It is stored only on this Mac.</p>
<div class=row style=margin-top:30px;max-width:480px>
<input id=k placeholder="sk-or-..." />
<button class=send onclick=saveKey()>Save</button></div>`}
async function saveKey(){const v=document.getElementById('k').value.trim();
 const r=await J('/api/key',{method:'POST',headers:{'Content-Type':
 'application/json'},body:JSON.stringify({key:v})});
 if(r.ok){ST=await J('/api/state');scrWelcome()}else alert(r.error||'bad key')}
function scrWelcome(){app.innerHTML=`<div class=lab>First run</div>
<h1>Let's set you up.</h1><p class=sub>A short conversation so Anticipy
understands your life before it does anything. Real questions, your
real answers.</p><button class=cta onclick=startOnb()>Begin</button>`}
let OB={qs:[]};
async function startOnb(){const r=await J('/api/onboarding/start');
 OB={qs:[{a:r.question}],total:r.total};renderOnb()}
function renderOnb(){let h=`<div class=lab>Onboarding</div>
<div class=qa>`;for(const t of OB.qs){if(t.a)h+=`<div class="bub a">
${esc(t.a)}</div>`;if(t.u)h+=`<div class="bub u">${esc(t.u)}</div>`}
h+=`</div><div class=row><textarea id=ans rows=2
placeholder="Type your answer..."></textarea>
<button class=send onclick=sendAns()>Send</button></div>`;
app.innerHTML=h;document.getElementById('ans').focus()}
async function sendAns(){const el=document.getElementById('ans');
 const v=el.value.trim();if(!v)return;OB.qs[OB.qs.length-1].u=v;
 el.disabled=true;
 const r=await J('/api/onboarding/answer',{method:'POST',headers:
 {'Content-Type':'application/json'},body:JSON.stringify({answer:v})});
 if(r.done){ST.onboarded=true;ST.profile=r.profile;return scrDone()}
 OB.qs.push({a:r.question});renderOnb()}
function scrDone(){const p=ST.profile||{};
 const ppl=Object.entries(p.people||{}).map(([k,v])=>
 `<div><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join('');
 app.innerHTML=`<div class=lab>You're set up</div>
 <h1>Good to meet you${p.name?', '+esc(p.name):''}.</h1>
 <p class=sub>Anticipy now knows who you are and what matters.</p>
 <div class=kv><div><b>Role</b><span>${esc(p.role_title||'-')}</span></div>
 <div><b>What you do</b><span>${esc(p.what_they_do||'-')}</span></div>
 <div><b>Mandate</b><span>${esc(p.mandate||'-')}</span></div>
 ${ppl}</div>
 <button class=cta onclick="go('listen')">Start listening</button>`}
function scrListen(){app.innerHTML=`<div class="scr center">
<div class=lab>Listening</div><div class="orb" id=orb><i></i></div>
<h1 style=margin-top:26px>Press Listen and speak.</h1>
<p class=sub style="margin:14px auto 0">Anticipy hears your real
microphone, understands it, and proposes one clear thing.</p>
<button class=cta id=lb style="align-self:center"
onclick=doListen()>Listen</button><div id=out></div></div>`}
async function doListen(){const b=document.getElementById('lb');
 const orb=document.getElementById('orb');b.disabled=true;
 b.textContent='Listening, speak now...';orb.classList.add('on');
 const r=await J('/api/listen/once',{method:'POST'});
 orb.classList.remove('on');b.disabled=false;b.textContent='Listen again';
 const o=document.getElementById('out');
 if(r.error){o.innerHTML=`<div class=card><h2>Something went wrong</h2>
 <div class=meta>${esc(r.error)}</div></div>`;return}
 if(!r.transcript){o.innerHTML=`<div class=card><h2>I didn't catch
 anything</h2><div class=meta>${esc(r.note||'')}</div></div>`;return}
 o.innerHTML=`<div class=card><div class=lab>Heard</div>
 <h2>${esc(r.transcript)}</h2>
 <div class=meta>Decision: ${esc(r.outcome||'-')}</div>
 ${r.proposal?`<div class=lab style=margin-top:20px>Proposal</div>
 <p style="margin-top:8px;font-size:15px;line-height:1.6">
 ${esc(r.proposal)}</p><div class=row style=margin-top:18px>
 <button class=send>Yes, do it</button>
 <button class=send style="background:transparent;border:1px solid
 var(--bd);color:var(--cream)">No</button></div>`:
 `<div class=meta style=margin-top:12px>Nothing worth interrupting
 you for. Logged.</div>`}</div>`}
function scrSettings(){const p=ST.profile||{};
 app.innerHTML=`<div class=lab>Settings</div><h1>Your setup.</h1>
 <div class=kv style=margin-top:24px>
 <div><b>Name</b><span>${esc(p.name||'not set')}</span></div>
 <div><b>Reasoning</b><span>${ST.key_ok?'Connected (OpenRouter cloud)':
 'Key missing'}</span></div>
 <div><b>Microphone</b><span>Used live when you press Listen</span></div>
 <div><b>Onboarding</b><span>${ST.onboarded?'Complete':'Not done'}</span>
 </div></div>`}
function go(s){if(s=='listen')scrListen();else if(s=='settings')scrSettings();
 else boot()}
boot();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX)


class Key(BaseModel):
    key: str


@app.post("/api/key")
def set_key(k: Key) -> JSONResponse:
    if not k.key.strip().startswith("sk-or-"):
        return JSONResponse({"ok": False, "error": "not an sk-or- key"})
    cfg = Path(os.path.expanduser("~/.anticipy/.env"))
    cfg.parent.mkdir(parents=True, exist_ok=True)
    keep = ""
    if cfg.exists():
        keep = "\n".join(l for l in cfg.read_text().splitlines()
                         if not l.strip().startswith("OPENROUTER_API_KEY="))
    cfg.write_text((keep + "\n" if keep else "")
                   + f"OPENROUTER_API_KEY={k.key.strip()}\n")
    os.environ["OPENROUTER_API_KEY"] = k.key.strip()
    return JSONResponse({"ok": True})
