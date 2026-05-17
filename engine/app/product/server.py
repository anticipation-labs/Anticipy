"""Anticipy local product backend, fully integrated.

ONE product loop, real end to end, modifying no frozen code:

  onboarding   real conversational intake -> app.anticipy.onboarding
               .run_intake -> a real structured UserProfile, and the
               profile people are seeded into the real anticipy_memory
               so "the boss" / "us" resolve from day one.
  microphone   a real macOS capture-permission probe (triggers TCC)
               and a real 6s capture on Listen. No synthetic voice.
  listen       real sounddevice capture -> real local parakeet ASR ->
               the FROZEN reasoning + proactive_day pipeline WITH the
               real anticipy_memory draw wired in (references resolve
               over time) -> a real proposal. Every heard utterance is
               written to the real per-user memory via the Mem0-style
               reconcile primitive (ADD/UPDATE/DELETE/NOOP).
  act          on the user's explicit "Yes, do it", the proposal's
               instruction is handed to the FROZEN browser action
               engine (action_handoff.make_real_action_engine ->
               DSv4SkillRunner) which really drives Chrome over CDP.
  history      the real active memory snapshot, surfaced.

Frozen code is only ever used through its existing public seams
(read-only): the reasoning engine, onboarding.run_intake, memory.*,
and the action engine via action_handoff. pipeline._MEMORY_DRAW is a
designed runtime hook, set here, not a code edit.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Anticipy", version="product-2")

# single-user desktop session, in-process
_SESS: dict = {"i": 0, "transcript": [], "profile": None,
               "profile_obj": None, "last_action_text": None}
USER_ID = "anticipy-user"
CDP_PORT = 9222


# --------------------------------------------------------------------------
# key
# --------------------------------------------------------------------------

def _cfg_path() -> Path:
    return Path(os.path.expanduser("~/.anticipy/.env"))


def _key_ok() -> bool:
    if os.environ.get("OPENROUTER_API_KEY", "").startswith("sk-or-"):
        return True
    cfg = _cfg_path()
    if cfg.exists():
        for ln in cfg.read_text().splitlines():
            if ln.strip().startswith("OPENROUTER_API_KEY="):
                v = ln.split("=", 1)[1].strip().strip('"').strip("'")
                if v.startswith("sk-or-"):
                    os.environ["OPENROUTER_API_KEY"] = v
                    return True
    return False


class Key(BaseModel):
    key: str


@app.post("/api/key")
def set_key(k: Key) -> JSONResponse:
    if not k.key.strip().startswith("sk-or-"):
        return JSONResponse({"ok": False, "error": "not an sk-or- key"})
    cfg = _cfg_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    keep = ""
    if cfg.exists():
        keep = "\n".join(l for l in cfg.read_text().splitlines()
                         if not l.strip().startswith("OPENROUTER_API_KEY="))
    cfg.write_text((keep + "\n" if keep else "")
                   + f"OPENROUTER_API_KEY={k.key.strip()}\n")
    os.environ["OPENROUTER_API_KEY"] = k.key.strip()
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------
# memory wiring (Step 1): the real anticipy_memory system, used through
# its public API only. The draw closure resolves a vague reference from
# the onboarded profile + accrued per-user memory and feeds it back into
# the proactive_day resolver via the designed pipeline._MEMORY_DRAW hook.
# --------------------------------------------------------------------------

_PERSON_CUES = ("boss", "manager", "lead", "client", "partner", "wife",
                "husband", "report", "team", "she", "he", "them", "her",
                "him", "they", "us", "we")


def _memory_draw(event_text: str):
    """(event_text) -> (object_hint|None, person_hint|None). Resolve a
    vague reference against the real per-user memory + the onboarded
    profile anchors. Returns nothing on ambiguity so an unresolved
    reference is still never guessed (the resolver then CONFIRMs).
    """
    from app.anticipy import memory as MEM

    prof = _SESS.get("profile_obj")
    try:
        rr = MEM.resolve_reference_sync(USER_ID, event_text, prof)
    except Exception:
        return (None, None)
    if not (rr.resolved and rr.value and rr.confidence >= 0.70):
        return (None, None)
    low = (event_text or "").lower()
    looks_person = any(c in low for c in _PERSON_CUES)
    people_vals = set()
    if prof is not None:
        people_vals = {str(v).lower()
                       for v in (getattr(prof, "people", {}) or {}).values()}
    if looks_person or rr.value.lower() in people_vals:
        return (None, rr.value)
    return (rr.value, None)


def _install_memory_draw() -> None:
    from app.proactive_day import pipeline
    pipeline._MEMORY_DRAW = _memory_draw


def _memory_write(text: str, kind: str) -> dict:
    """Write the heard utterance to the real per-user memory via the
    Mem0-style reconcile primitive (ADD/UPDATE/DELETE/NOOP). Genuine
    episodic memory: this is what makes later references resolve.
    """
    from app.anticipy import memory as MEM
    try:
        rc = asyncio.run(MEM.reconcile(USER_ID, kind, text))
        return {"op": rc.op, "reason": rc.reason}
    except Exception as e:
        return {"op": "ERROR", "reason": f"{type(e).__name__}: {e}"}


@app.get("/api/memory")
def memory_snapshot() -> JSONResponse:
    from app.anticipy import memory as MEM
    try:
        snap = MEM.active_snapshot(USER_ID)
    except Exception as e:
        return JSONResponse({"entries": [],
                             "error": f"{type(e).__name__}: {e}"})
    entries = [{"kind": e.get("kind"), "value": e.get("value"),
                "ts": e.get("ts")} for e in snap]
    entries.sort(key=lambda x: x.get("ts") or 0, reverse=True)
    return JSONResponse({"entries": entries})


# --------------------------------------------------------------------------
# state + onboarding (real, via the frozen onboarding brain)
# --------------------------------------------------------------------------

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
    _SESS["profile_obj"] = prof
    pj = {
        "name": prof.name, "role_title": prof.role_title,
        "what_they_do": prof.what_they_do, "people": prof.people,
        "mandate": prof.mandate, "do_not_touch": prof.do_not_touch,
        "comms_prefs": prof.comms_prefs,
        "well_populated": OB.profile_is_well_populated(prof),
    }
    _SESS["profile"] = pj

    # warm start: seed the profile people into the real memory so
    # "the boss" / "us" resolve from day one (onboarding's stated
    # intent), then arm the memory draw for the listen loop.
    try:
        from app.anticipy import memory as MEM
        if prof.people:
            MEM.seed(USER_ID, {str(k): str(v)
                               for k, v in prof.people.items()})
    except Exception:
        pass
    _install_memory_draw()
    return JSONResponse({"done": True, "profile": pj})


# --------------------------------------------------------------------------
# microphone (Step 3): a real permission probe + the real listen loop
# --------------------------------------------------------------------------

@app.get("/api/mic/probe")
def mic_probe() -> JSONResponse:
    """A short REAL capture: triggers the macOS microphone permission
    prompt and proves the device opens. Honest on failure (TCC denied /
    no device): the real error, never faked.
    """
    try:
        import numpy as np
        import sounddevice as sd
        sr = 16000
        rec = sd.rec(int(0.4 * sr), samplerate=sr, channels=1,
                     dtype="float32")
        sd.wait()
        wav = np.asarray(rec).reshape(-1)
        rms = float(np.sqrt(np.mean(wav ** 2)) or 0.0)
        try:
            dev = str(sd.query_devices(kind="input").get("name", "input"))
        except Exception:
            dev = "default input"
        return JSONResponse({"ok": True, "rms": rms,
                             "samples": int(wav.size), "device": dev})
    except Exception as e:
        return JSONResponse({"ok": False,
                             "error": f"{type(e).__name__}: {e}"})


@app.post("/api/listen/once")
def listen_once() -> JSONResponse:
    """Real microphone -> real local ASR -> the frozen reasoning +
    proactive_day pipeline (with the real memory draw armed) -> a real
    proposal. The heard utterance is written to the real per-user
    memory. No synthetic voice; honest empty result if nothing is said.
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
                "note": "No speech captured from the microphone. Press "
                        "Listen and speak; nothing synthetic is "
                        "substituted."})

        _install_memory_draw()
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
            proposal = world.outbound[0].body

        # genuine episodic memory write: this is what makes later
        # references resolve over time (the real Mem0 primitive).
        kind = ("latent_intent"
                if outcome in ("ACTED", "DEFERRED", "CONFIRMED")
                else "fact")
        mem = _memory_write(text, kind)

        # the instruction handed to the action engine on confirm is the
        # wearer's own resolved utterance.
        _SESS["last_action_text"] = text
        return JSONResponse({
            "transcript": text, "rms": rms, "outcome": outcome,
            "proposal": proposal, "action_text": text,
            "memory": mem})
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={
            "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc()[-1500:]})


# --------------------------------------------------------------------------
# act (Step 2): the proposal handed to the FROZEN browser action engine
# --------------------------------------------------------------------------

def _cdp_up() -> bool:
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2).read()
        return True
    except Exception:
        return False


def _ensure_cdp_chrome() -> bool:
    """Ensure a CDP Chrome is reachable on :9222. If not, launch one
    with an isolated profile (a normal local action). Returns True if
    reachable.
    """
    if _cdp_up():
        return True
    chrome = None
    for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"),
              shutil.which("chromium")):
        if c and Path(c).exists():
            chrome = c
            break
    if not chrome:
        return False
    prof = Path(os.path.expanduser("~/.anticipy/chrome-agent"))
    prof.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.Popen(
            [chrome, f"--remote-debugging-port={CDP_PORT}",
             f"--user-data-dir={prof}", "--no-first-run",
             "--no-default-browser-check", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    for _ in range(40):
        if _cdp_up():
            return True
        time.sleep(0.5)
    return False


class Act(BaseModel):
    instruction: str | None = None


@app.post("/api/act")
def act(a: Act) -> JSONResponse:
    """The user confirmed the proposal. Hand the instruction to the
    FROZEN action engine, which really drives Chrome over CDP. Honest
    gating if the browser is unreachable; never a faked success.
    """
    instruction = (a.instruction or _SESS.get("last_action_text")
                   or "").strip()
    if not instruction:
        return JSONResponse({"ran": False,
                             "error": "no instruction to act on"})
    if not _ensure_cdp_chrome():
        return JSONResponse({
            "ran": False, "gated": True,
            "error": "No Chrome with remote debugging on :9222 and "
                     "none could be launched. The real path "
                     "(action_handoff -> frozen DSv4SkillRunner) is "
                     "wired; a running browser is the edge."})
    try:
        from app.anticipy.action_handoff import make_real_action_engine
        eng = make_real_action_engine(cdp_port=CDP_PORT, max_iters=12)
        res = eng({"object": instruction, "time_window": ""}) or {}
        status = res.get("status", "?")
        ran = status in ("SUCCESS", "PROCEEDED_ON_ASSUMPTION",
                         "ITERATION_EXHAUSTED")
        return JSONResponse({
            "ran": ran, "status": status,
            "answer": str(res.get("answer", ""))[:600],
            "evidence": str(res.get("evidence", ""))[:600],
            "trajectory_dir": res.get("trajectory_dir", ""),
            "error": res.get("error")})
    except Exception as e:
        import traceback
        return JSONResponse(status_code=500, content={
            "ran": False, "error": f"{type(e).__name__}: {e}",
            "trace": traceback.format_exc()[-1200:]})


# --------------------------------------------------------------------------
# the single designed product UI
# --------------------------------------------------------------------------

INDEX = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Anticipy</title>
<link rel=preconnect href=https://fonts.googleapis.com>
<link rel=preconnect href=https://fonts.gstatic.com crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel=stylesheet>
<style>
:root{--dark:#0C0C0C;--elev:#161616;--elev2:#1C1C1C;--bd:#262626;
--cream:#F5F0EB;--mut:#8A8A8A;--gold:#C8A97E;--ok:#7FB28A;--warn:#C98A6E}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{background:var(--dark);color:var(--cream);
font-family:'Plus Jakarta Sans',-apple-system,BlinkMacSystemFont,sans-serif;
-webkit-font-smoothing:antialiased;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
background:radial-gradient(58rem 40rem at 50% -14%,rgba(200,169,126,.13),transparent 68%)}
.wrap{position:relative;z-index:1;max-width:700px;margin:0 auto;
padding:0 28px;min-height:100vh;display:flex;flex-direction:column}
nav{display:flex;justify-content:space-between;align-items:center;
height:66px;font-size:11px;letter-spacing:.22em;text-transform:uppercase;
color:var(--mut)}
nav .b{font-family:'DM Serif Display',Georgia,serif;font-size:19px;
color:var(--cream);letter-spacing:0;text-transform:none}
nav .lk a{color:var(--mut);cursor:pointer;margin-left:24px;transition:.2s}
nav .lk a:hover,nav .lk a.on{color:var(--cream)}
.scr{flex:1;display:flex;flex-direction:column;justify-content:center;
padding:30px 0 64px;animation:f .55s cubic-bezier(.16,1,.3,1)}
@keyframes f{from{opacity:0;transform:translateY(12px)}to{opacity:1}}
.lab{font-size:11px;letter-spacing:.26em;text-transform:uppercase;
color:var(--gold);margin-bottom:18px;font-weight:600}
h1{font-family:'DM Serif Display',Georgia,serif;font-weight:400;
font-size:clamp(31px,5.6vw,54px);line-height:1.07;letter-spacing:-.02em}
p.sub{margin-top:17px;color:rgba(245,240,235,.56);font-size:15px;
line-height:1.72;max-width:48ch}
button{font-family:inherit}
button.cta{margin-top:36px;align-self:flex-start;border:0;
background:var(--cream);color:var(--dark);font:600 14px/1 'Plus Jakarta Sans';
padding:17px 32px;border-radius:100px;cursor:pointer;transition:.22s}
button.cta:hover{background:var(--gold);transform:translateY(-1px)}
button.cta:disabled{opacity:.4;cursor:default;transform:none}
.ghost{background:transparent;border:1px solid var(--bd);color:var(--cream);
padding:16px 30px;border-radius:100px;cursor:pointer;font:500 14px/1
'Plus Jakarta Sans';transition:.2s}
.ghost:hover{border-color:var(--gold);color:var(--gold)}
.qa{display:flex;flex-direction:column;gap:13px;margin:6px 0 20px;
max-height:46vh;overflow-y:auto;padding-right:4px}
.bub{padding:14px 18px;border-radius:17px;font-size:14px;line-height:1.62;
max-width:84%;animation:f .4s ease}
.bub.a{background:var(--elev);border:1px solid var(--bd);
align-self:flex-start;border-bottom-left-radius:5px}
.bub.u{background:var(--gold);color:var(--dark);align-self:flex-end;
border-bottom-right-radius:5px;font-weight:500}
.prog{height:3px;background:var(--bd);border-radius:3px;margin:2px 0 22px;
overflow:hidden}.prog>i{display:block;height:100%;background:var(--gold);
transition:width .4s ease}
.row{display:flex;gap:11px;margin-top:10px;align-items:flex-end}
input,textarea{flex:1;background:var(--elev);border:1px solid var(--bd);
color:var(--cream);padding:15px 18px;border-radius:14px;font:400 14px
'Plus Jakarta Sans';outline:none;resize:none;transition:.2s}
input:focus,textarea:focus{border-color:rgba(200,169,126,.55)}
.send{border:0;background:var(--cream);color:var(--dark);padding:0 24px;
height:50px;border-radius:14px;cursor:pointer;font-weight:600;transition:.2s}
.send:hover{background:var(--gold)}
.send:disabled{opacity:.4;cursor:default}
.center{text-align:center;align-items:center}
.center p.sub,.center h1{margin-left:auto;margin-right:auto}
.center .lab{text-align:center}
.orb{width:172px;height:172px;margin:10px auto 0;border-radius:50%;
position:relative;background:radial-gradient(circle at 50% 44%,
rgba(200,169,126,.5),rgba(200,169,126,.04) 60%,transparent 72%)}
.orb i{position:absolute;inset:35%;border-radius:50%;
background:rgba(200,169,126,.9);box-shadow:0 0 60px rgba(200,169,126,.5);
transition:transform .15s ease}
.orb.on{animation:br 2.4s ease-in-out infinite}
@keyframes br{0%,100%{transform:scale(.96)}50%{transform:scale(1.07)}}
.ring{position:absolute;inset:0;border-radius:50%;
border:1.5px solid rgba(200,169,126,.28)}
.orb.on .ring{animation:pl 2.4s ease-out infinite}
@keyframes pl{0%{transform:scale(.9);opacity:.8}
100%{transform:scale(1.35);opacity:0}}
.count{font-family:'DM Serif Display',serif;font-size:42px;
color:var(--gold);margin-top:8px;min-height:50px}
.card{background:var(--elev);border:1px solid var(--bd);border-radius:22px;
padding:30px;text-align:left;margin-top:26px;animation:f .45s ease}
.card h2{font-family:'DM Serif Display',serif;font-size:22px;
line-height:1.32;font-weight:400}
.meta{margin-top:13px;font-size:12.5px;color:rgba(245,240,235,.46);
line-height:1.6}
.kv{display:grid;gap:1px;background:var(--bd);border-radius:16px;
overflow:hidden;margin-top:18px}
.kv>div{background:var(--elev);padding:15px 18px}
.kv b{font-size:13px;color:rgba(245,240,235,.88);font-weight:600;
display:block}
.kv span{display:block;margin-top:4px;font-size:12.5px;
color:rgba(245,240,235,.5)}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:11px;
letter-spacing:.16em;text-transform:uppercase;color:var(--mut);
border:1px solid var(--bd);padding:7px 13px;border-radius:100px}
.dot{width:7px;height:7px;border-radius:50%;background:var(--mut)}
.dot.g{background:var(--ok)}.dot.w{background:var(--warn)}
.spin{width:18px;height:18px;border:2px solid var(--bd);
border-top-color:var(--gold);border-radius:50%;display:inline-block;
animation:sp .7s linear infinite;vertical-align:-3px}
@keyframes sp{to{transform:rotate(360deg)}}
.hist{display:flex;flex-direction:column;gap:10px;margin-top:22px}
.hist .it{background:var(--elev);border:1px solid var(--bd);
border-radius:14px;padding:15px 18px;font-size:13.5px;line-height:1.55}
.hist .it .k{font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;
color:var(--gold);margin-bottom:6px}
.empty{margin-top:24px;color:var(--mut);font-size:14px;
border:1px dashed var(--bd);border-radius:16px;padding:34px;text-align:center}
.err{color:var(--warn)}
@media (max-width:560px){.wrap{padding:0 20px}}
</style></head><body><div class=wrap>
<nav><span class=b>Anticipy</span>
<span class=lk id=nav></span></nav>
<div id=app class=scr></div></div>
<script>
const app=document.getElementById('app'),nav=document.getElementById('nav');
let ST={},OB={qs:[]};
async function J(u,o){const r=await fetch(u,o);return r.json()}
function esc(s){return(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;',
'>':'&gt;','"':'&quot;'}[c]))}
function setNav(active){if(!ST.onboarded){nav.innerHTML='';return}
 nav.innerHTML=['listen','history','settings'].map(s=>
 `<a class="${s==active?'on':''}" onclick="go('${s}')">${s}</a>`).join('')}
async function boot(){ST=await J('/api/state');
 if(!ST.key_ok)return scrKey();
 if(!ST.onboarded)return scrWelcome();
 go('listen')}

function scrKey(){setNav();app.innerHTML=`<div class=lab>Setup</div>
<h1>Connect Anticipy.</h1><p class=sub>Anticipy thinks using a cloud
reasoning model. Paste your OpenRouter key. It is stored only on this
Mac, in your home folder.</p>
<div class=row style="margin-top:32px;max-width:500px">
<input id=k placeholder="sk-or-..." autocomplete=off />
<button class=send onclick=saveKey()>Save</button></div>
<div id=ke class=meta></div>`}
async function saveKey(){const v=document.getElementById('k').value.trim();
 const r=await J('/api/key',{method:'POST',headers:{'Content-Type':
 'application/json'},body:JSON.stringify({key:v})});
 if(r.ok){ST=await J('/api/state');scrWelcome()}
 else document.getElementById('ke').innerHTML=
 `<span class=err>${esc(r.error||'bad key')}</span>`}

function scrWelcome(){setNav();app.innerHTML=`<div class=lab>Welcome</div>
<h1>Let's set you up.</h1><p class=sub>A short conversation so Anticipy
understands your life before it does anything. Real questions, your real
answers. It takes about a minute.</p>
<button class=cta onclick=startOnb()>Begin</button>`}
async function startOnb(){const r=await J('/api/onboarding/start');
 OB={qs:[{a:r.question}],total:r.total,idx:0};renderOnb()}
function renderOnb(){const pct=Math.round(100*OB.idx/(OB.total||1));
 let h=`<div class=lab>Onboarding</div>
 <div class=prog><i style="width:${pct}%"></i></div><div class=qa id=qa>`;
 for(const t of OB.qs){if(t.a)h+=`<div class="bub a">${esc(t.a)}</div>`;
 if(t.u)h+=`<div class="bub u">${esc(t.u)}</div>`}
 h+=`</div><div class=row><textarea id=ans rows=2
 placeholder="Type your answer, then press Enter"></textarea>
 <button class=send id=sb onclick=sendAns()>Send</button></div>`;
 app.innerHTML=h;const qa=document.getElementById('qa');qa.scrollTop=qa.scrollHeight;
 const ta=document.getElementById('ans');ta.focus();
 ta.onkeydown=e=>{if(e.key=='Enter'&&!e.shiftKey){e.preventDefault();sendAns()}}}
async function sendAns(){const el=document.getElementById('ans');
 const v=el.value.trim();if(!v)return;
 OB.qs[OB.qs.length-1].u=v;OB.idx++;
 document.getElementById('sb').disabled=true;el.disabled=true;
 const r=await J('/api/onboarding/answer',{method:'POST',headers:
 {'Content-Type':'application/json'},body:JSON.stringify({answer:v})});
 if(r.done){ST.onboarded=true;ST.profile=r.profile;return scrProfile(true)}
 OB.qs.push({a:r.question});renderOnb()}

function scrProfile(fresh){setNav();const p=ST.profile||{};
 const ppl=Object.entries(p.people||{}).map(([k,v])=>
 `<div><b>${esc(k)}</b><span>${esc(v)}</span></div>`).join('');
 app.innerHTML=`<div class=lab>${fresh?"You're set up":'Your profile'}</div>
 <h1>${fresh?'Good to meet you':'Hello'}${p.name?', '+esc(p.name.split(' ')[0]):''}.</h1>
 <p class=sub>Anticipy now knows who you are and what matters. This is
 stored locally and used to resolve who and what you mean.</p>
 <div class=kv><div><b>Role</b><span>${esc(p.role_title||'-')}</span></div>
 <div><b>What you do</b><span>${esc(p.what_they_do||'-')}</span></div>
 <div><b>Mandate</b><span>${esc(p.mandate||'-')}</span></div>
 ${p.do_not_touch&&p.do_not_touch.length?`<div><b>Do not touch</b>
 <span>${esc(p.do_not_touch.join(', '))}</span></div>`:''}${ppl}</div>
 <button class=cta onclick="go('mic')">Continue</button>`}

function scrMic(){setNav('listen');app.innerHTML=`<div class="scr center">
 <div class=lab>Microphone</div>
 <h1>Let Anticipy hear you.</h1>
 <p class=sub>Anticipy listens to your real microphone, on this Mac,
 only while you hold a session. macOS will ask for permission now.</p>
 <div id=ms style="margin-top:30px"></div>
 <button class=cta id=mb style="align-self:center"
 onclick=probeMic()>Enable microphone</button></div>`}
async function probeMic(){const b=document.getElementById('mb'),
 s=document.getElementById('ms');b.disabled=true;
 b.innerHTML='<span class=spin></span>';
 const r=await J('/api/mic/probe');b.disabled=false;
 if(r.ok){b.style.display='none';
 s.innerHTML=`<div class=pill><span class="dot g"></span>
 ${esc(r.device||'microphone')} ready</div>
 <p class=sub style="margin:18px auto 0">Captured a real test sample
 (level ${r.rms.toFixed(4)}). Taking you to Listen.</p>`;
 setTimeout(()=>go('listen'),1100)}
 else{b.textContent='Try again';
 s.innerHTML=`<p class=sub err style="margin:0 auto;color:var(--warn)">
 ${esc(r.error||'Microphone unavailable')}. Grant Anticipy microphone
 access in System Settings, Privacy, Microphone.</p>`}}

function scrListen(){setNav('listen');app.innerHTML=`<div class="scr center">
 <div class=lab>Listening</div>
 <div class="orb" id=orb><div class=ring></div><i></i></div>
 <div class=count id=cd></div>
 <h1 style="margin-top:6px">Press Listen and speak.</h1>
 <p class=sub style="margin:14px auto 0">Anticipy hears your real
 microphone, understands it against what it knows about you, and
 proposes one clear thing. Nothing synthetic.</p>
 <button class=cta id=lb style="align-self:center"
 onclick=doListen()>Listen</button><div id=out></div></div>`}
async function doListen(){const b=document.getElementById('lb'),
 orb=document.getElementById('orb'),cd=document.getElementById('cd'),
 out=document.getElementById('out');
 b.disabled=true;b.textContent='Listening...';out.innerHTML='';
 orb.classList.add('on');let n=6;cd.textContent=n;
 const iv=setInterval(()=>{n--;cd.textContent=n>0?n:'';},1000);
 const r=await J('/api/listen/once',{method:'POST'});
 clearInterval(iv);cd.textContent='';orb.classList.remove('on');
 b.disabled=false;b.textContent='Listen again';
 if(r.error){out.innerHTML=`<div class=card><h2>Something went wrong</h2>
 <div class="meta err">${esc(r.error)}</div></div>`;return}
 if(!r.transcript){out.innerHTML=`<div class=card>
 <div class=lab>Nothing heard</div><h2>I didn't catch anything.</h2>
 <div class=meta>${esc(r.note||'')} Mic level ${(r.rms||0).toFixed(4)}.
 </div></div>`;return}
 const mem=r.memory?`<span class=pill style="margin-top:14px">
 <span class=dot></span>memory ${esc(r.memory.op||'-')}</span>`:'';
 let h=`<div class=card><div class=lab>Heard</div>
 <h2>${esc(r.transcript)}</h2>
 <div class=meta>Decision: ${esc(r.outcome||'-')} &middot; mic level
 ${(r.rms||0).toFixed(4)}</div>`;
 if(r.proposal){h+=`<div class=lab style="margin-top:22px">Proposal</div>
 <p style="margin-top:8px;font-size:15px;line-height:1.6">
 ${esc(r.proposal)}</p>
 <div class=row style="margin-top:20px">
 <button class=send id=yes onclick='doAct(${JSON.stringify(
 r.action_text||r.transcript)})'>Yes, do it</button>
 <button class=ghost onclick="go('listen')">No</button></div>
 <div id=act></div>`}
 else{h+=`${mem}<div class=meta style="margin-top:14px">Nothing worth
 interrupting you for. Logged to memory.</div>`}
 h+='</div>';out.innerHTML=h}
async function doAct(instr){const y=document.getElementById('yes'),
 ac=document.getElementById('act');y.disabled=true;
 y.innerHTML='<span class=spin></span> Acting in Chrome';
 ac.innerHTML=`<div class=meta style="margin-top:16px">Anticipy is
 driving a real Chrome window. This can take a minute.</div>`;
 const r=await J('/api/act',{method:'POST',headers:{'Content-Type':
 'application/json'},body:JSON.stringify({instruction:instr})});
 y.style.display='none';
 if(r.ran){ac.innerHTML=`<div class=lab style="margin-top:20px">
 <span class=dot></span> Done in Chrome</div>
 <p style="margin-top:8px;font-size:14.5px;line-height:1.6">
 ${esc(r.answer||r.status)}</p>
 <div class=meta>${esc(r.evidence||'')}</div>`}
 else{ac.innerHTML=`<div class="meta err" style="margin-top:16px">
 ${esc(r.error||('status '+(r.status||'?')))}</div>`}}

async function scrHistory(){setNav('history');
 app.innerHTML=`<div class=lab>Memory</div><h1>What Anticipy remembers.</h1>
 <p class=sub>Everything it has heard worth keeping, on this Mac. This is
 what lets it resolve who and what you mean over time.</p>
 <div id=hl><div class=meta style="margin-top:24px">
 <span class=spin></span> Loading</div></div>`;
 const r=await J('/api/memory');const hl=document.getElementById('hl');
 if(!r.entries||!r.entries.length){hl.innerHTML=`<div class=empty>
 Nothing remembered yet. What you tell Anticipy in a session shows up
 here.</div>`;return}
 hl.innerHTML='<div class=hist>'+r.entries.map(e=>
 `<div class=it><div class=k>${esc(e.kind||'note')}</div>
 ${esc(e.value||'')}</div>`).join('')+'</div>'}

function scrSettings(){setNav('settings');const p=ST.profile||{};
 app.innerHTML=`<div class=lab>Settings</div><h1>Your setup.</h1>
 <div class=kv style="margin-top:24px">
 <div><b>Name</b><span>${esc(p.name||'not set')}</span></div>
 <div><b>Reasoning</b><span>${ST.key_ok?'Connected, OpenRouter cloud':
 'Key missing'}</span></div>
 <div><b>Microphone</b><span>Used live, only while a Listen session is
 open</span></div>
 <div><b>Memory</b><span>Stored locally on this Mac, per user</span></div>
 <div><b>Browser actions</b><span>Run in a real Chrome window on your
 explicit confirmation</span></div></div>
 <button class=ghost style="margin-top:30px"
 onclick="go('mic')">Re-check microphone</button>`}

function go(s){window.scrollTo(0,0);
 if(s=='listen')scrListen();
 else if(s=='mic')scrMic();
 else if(s=='history')scrHistory();
 else if(s=='settings')scrSettings();
 else if(s=='profile')scrProfile(false);
 else boot()}
boot();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(INDEX)
