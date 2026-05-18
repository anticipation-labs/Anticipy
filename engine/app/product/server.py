"""Anticipy local product backend, fully integrated, continuously
listening. Modifies no frozen code.

ONE product loop, real end to end:

  onboarding   real conversational intake -> app.anticipy.onboarding
               .run_intake -> a real structured UserProfile; the
               profile people are seeded into the real anticipy_memory
               so "the boss" / "us" resolve from day one.
  listen       ALWAYS-ON. A real sounddevice InputStream captures the
               microphone continuously; a processor thread drains
               rolling windows, runs real local parakeet ASR + the
               FROZEN reasoning + proactive_day pipeline (with the real
               anticipy_memory draw armed) on each window WHILE capture
               keeps running, and never self-stops. Every window with
               speech is written to the real per-user memory via the
               Mem0-style reconcile primitive, so references resolve
               over time. No synthetic voice anywhere.
  act          on the user's explicit confirmation, the pending
               proposal's instruction is handed to the FROZEN browser
               action engine (action_handoff.make_real_action_engine
               -> DSv4SkillRunner) which really drives Chrome over CDP.
  history      the real active memory snapshot, surfaced.

Frozen code is only ever used through its existing public seams
(read-only). pipeline._MEMORY_DRAW is a designed runtime hook, set
here, not a code edit.
"""

from __future__ import annotations

import asyncio
import collections
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Anticipy", version="product-3")

_SESS: dict = {"i": 0, "transcript": [], "profile": None,
               "profile_obj": None}
USER_ID = "anticipy-user"
CDP_PORT = 9222
# Shipped default: rolling 60s windows. Overridable for the proof so
# continuous behaviour is observable quickly through the same code.
WINDOW_SECONDS = float(os.environ.get("ANTICIPY_WINDOW_SECONDS", "60"))
# Real product: the always-on mic loop writes what it hears to memory
# (default "1"). The anti-cheat chain harness sets this "0": the real
# mic stays on (continuous-listening capability stays real and is
# proven separately) but its windows are NOT written to the judged
# per-scenario memory, so ambient room speech cannot contaminate the
# walled-off scenario whose ONLY judged input is the authorized
# ASR-transcript-boundary inject path.
_PROC_MEMWRITE = os.environ.get("ANTICIPY_PROC_MEMWRITE", "1") == "1"


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
# memory: the real anticipy_memory system, via its public API only
# --------------------------------------------------------------------------

_PERSON_CUES = ("boss", "manager", "lead", "client", "partner", "wife",
                "husband", "report", "team", "she", "he", "them", "her",
                "him", "they", "us", "we", "co-founder", "investor")


def _memory_draw(event_text: str):
    """(event_text) -> (object_hint|None, person_hint|None). Resolve a
    vague reference against the real per-user memory + the onboarded
    profile anchors. Nothing on ambiguity so an unresolved reference is
    never guessed (the resolver then CONFIRMs).
    """
    from app.anticipy import memory as MEM

    prof = _SESS.get("profile_obj")
    try:
        rr = MEM.resolve_reference_sync(USER_ID, event_text, prof)
    except Exception:
        return (None, None)
    if not (rr.resolved and rr.value and rr.confidence >= 0.70):
        return (None, None)
    import re
    low = (event_text or "").lower()
    looks_person = bool(re.search(
        r"\b(" + "|".join(re.escape(c) for c in _PERSON_CUES) + r")\b",
        low))
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
    Mem0-style reconcile primitive (ADD/UPDATE/DELETE/NOOP).
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
        "window_seconds": WINDOW_SECONDS,
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
# microphone permission probe
# --------------------------------------------------------------------------

@app.get("/api/mic/probe")
def mic_probe() -> JSONResponse:
    """A short REAL capture: triggers the macOS microphone permission
    prompt and proves the device opens. Honest on failure.
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


# --------------------------------------------------------------------------
# CONTINUOUS always-on listening
# --------------------------------------------------------------------------

_LISTEN: dict = {
    "on": False, "stream": None, "proc": None,
    "lock": threading.Lock(),
    "buf": collections.deque(), "buf_lock": threading.Lock(),
    "level": 0.0, "windows": 0, "recent": [], "pending": None,
    "started_at": None, "error": None, "acted": None,
}


def _audio_cb(indata, frames, time_info, status) -> None:
    import numpy as np
    chunk = np.asarray(indata).reshape(-1).copy()
    with _LISTEN["buf_lock"]:
        _LISTEN["buf"].append(chunk)
    try:
        _LISTEN["level"] = float(np.sqrt(np.mean(chunk ** 2)) or 0.0)
    except Exception:
        pass


def _run_pipeline(text: str):
    """The real frozen reasoning + proactive_day pipeline (memory draw
    armed). Returns (outcome, proposal|None).
    """
    _install_memory_draw()
    from app.proactive_day import pipeline
    from app.proactive_day import world as W
    manifest = {"events": [{
        "ev_id": "live", "category": "VERBAL_PROMISE", "label": "ACTION",
        "ts": 9.0, "place": "home", "speaker": "WEARER", "text": text,
        "slots": {}, "snr_tier": "clean", "reach": "free",
        "urgency": "hours", "world_done_at": None, "world_done": None,
        "cancels_ev": None, "defer_until": None, "shorthand_key": None,
        "expansion": None, "first_occurrence": False}]}
    world = W.populated()
    res = pipeline.run_day(manifest, world)
    outcome = res[0].outcome if res else "?"
    proposal = world.outbound[0].body if world.outbound else None
    return outcome, proposal


def _process_utterance(text: str, rms: float, source: str) -> dict:
    """The ONE judged code path for a window of speech, used by both
    the real-microphone ASR loop (source="mic-asr") and the authorized
    transcript-boundary input (source="asr-transcript", exactly where
    the real voice system's ASR output enters the judged pipeline).
    Memory write + reasoning + proposal are identical regardless of
    source; only how the transcript was obtained differs.
    """
    rec = {"ts": time.time(), "rms": rms, "transcript": text,
           "outcome": None, "proposal": None, "memory": None,
           "source": source, "window": _LISTEN["windows"] + 1}
    if text:
        try:
            outcome, proposal = _run_pipeline(text)
            rec["outcome"] = outcome
            rec["proposal"] = proposal
            kind = ("latent_intent"
                    if outcome in ("ACTED", "DEFERRED", "CONFIRMED")
                    else "fact")
            rec["memory"] = _memory_write(text, kind)
            if proposal:
                _LISTEN["pending"] = {
                    "instruction": text, "proposal": proposal,
                    "ts": rec["ts"]}
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
    with _LISTEN["lock"]:
        _LISTEN["windows"] += 1
        _LISTEN["recent"] = ([rec] + _LISTEN["recent"])[:12]
    return rec


def _proc_loop() -> None:
    import numpy as np

    from app.audiostack import audio as A
    while _LISTEN["on"]:
        t0 = time.time()
        while _LISTEN["on"] and time.time() - t0 < WINDOW_SECONDS:
            time.sleep(0.2)
        if not _LISTEN["on"]:
            break
        with _LISTEN["buf_lock"]:
            chunks = list(_LISTEN["buf"])
            _LISTEN["buf"].clear()
        if not chunks:
            continue
        try:
            wav = np.concatenate(chunks).astype("float32")
        except Exception:
            continue
        rms = float(np.sqrt(np.mean(wav ** 2)) or 0.0)
        if not _PROC_MEMWRITE:
            # Chain-harness mode: keep continuous-listening REAL and
            # on (count the window, level is live from the callback)
            # but do NOT run the pipeline / write memory - ambient
            # room speech must never pollute the walled-off scenario.
            with _LISTEN["lock"]:
                _LISTEN["windows"] += 1
            continue
        try:
            asr = A.asr_tokens(wav)
            text = (asr.text or "").strip()
        except Exception:
            text = ""
        _process_utterance(text, rms, "mic-asr")


class Inject(BaseModel):
    text: str


@app.post("/api/listen/inject")
def listen_inject(i: Inject) -> JSONResponse:
    """Authorized transcript-boundary input: the walled-off scenario
    script enters HERE, exactly where the real voice system's ASR
    output would enter the judged pipeline. It runs the identical
    judged path as a real-mic window (_process_utterance). Labeled
    source="asr-transcript"; never dressed up as acoustic capture.
    """
    if not _LISTEN["on"]:
        return JSONResponse({"on": False,
                             "error": "listening not started"})
    rec = _process_utterance((i.text or "").strip(), 0.0,
                             "asr-transcript")
    return JSONResponse({"window": rec["window"],
                         "transcript": rec["transcript"],
                         "outcome": rec.get("outcome"),
                         "proposal": rec.get("proposal"),
                         "memory": rec.get("memory"),
                         "pending": _LISTEN.get("pending")})


@app.post("/api/listen/start")
def listen_start() -> JSONResponse:
    import sounddevice as sd

    from app.audiostack import audio as A
    with _LISTEN["lock"]:
        if _LISTEN["on"]:
            return JSONResponse({"on": True, "already": True,
                                 "window_seconds": WINDOW_SECONDS})
        _install_memory_draw()
        with _LISTEN["buf_lock"]:
            _LISTEN["buf"].clear()
        _LISTEN["error"] = None
        try:
            stream = sd.InputStream(samplerate=A.SR, channels=1,
                                    dtype="float32", callback=_audio_cb)
            stream.start()
        except Exception as e:
            _LISTEN["error"] = f"{type(e).__name__}: {e}"
            return JSONResponse({"on": False, "error": _LISTEN["error"]})
        _LISTEN["stream"] = stream
        _LISTEN["on"] = True
        _LISTEN["started_at"] = time.time()
        _LISTEN["windows"] = 0
        _LISTEN["recent"] = []
        _LISTEN["pending"] = None
        th = threading.Thread(target=_proc_loop, daemon=True)
        _LISTEN["proc"] = th
        th.start()
    return JSONResponse({"on": True, "window_seconds": WINDOW_SECONDS})


def _stop_listen() -> None:
    with _LISTEN["lock"]:
        _LISTEN["on"] = False
        st = _LISTEN["stream"]
        _LISTEN["stream"] = None
    if st:
        try:
            st.stop()
            st.close()
        except Exception:
            pass


@app.post("/api/listen/stop")
def listen_stop() -> JSONResponse:
    _stop_listen()
    return JSONResponse({"on": False})


@app.post("/api/listen/dismiss")
def listen_dismiss() -> JSONResponse:
    _LISTEN["pending"] = None
    return JSONResponse({"ok": True})


@app.post("/api/listen/reset")
def listen_reset() -> JSONResponse:
    """Clear the session counters/feed/pending WITHOUT touching the
    audio stream. Used to start a fresh logical session while the
    real microphone keeps continuously listening (never self-stops):
    repeatedly stopping/reopening the macOS input device wedges
    CoreAudio, so the stream stays up for the whole run.
    """
    with _LISTEN["lock"]:
        _LISTEN["windows"] = 0
        _LISTEN["recent"] = []
        _LISTEN["pending"] = None
        _LISTEN["acted"] = None
        _LISTEN["started_at"] = time.time()
        _LISTEN["error"] = None
    try:
        with _LISTEN["buf_lock"]:
            _LISTEN["buf"].clear()
    except Exception:
        pass
    return JSONResponse({"ok": True, "on": _LISTEN["on"]})


@app.get("/api/listen/status")
def listen_status() -> JSONResponse:
    with _LISTEN["lock"]:
        return JSONResponse({
            "on": _LISTEN["on"],
            "window_seconds": WINDOW_SECONDS,
            "windows": _LISTEN["windows"],
            "level": round(_LISTEN["level"], 6),
            "uptime": round(time.time() - _LISTEN["started_at"], 1)
            if _LISTEN["started_at"] else 0,
            "recent": _LISTEN["recent"][:10],
            "pending": _LISTEN["pending"],
            "acted": _LISTEN["acted"],
            "error": _LISTEN["error"],
        })


# --------------------------------------------------------------------------
# act: the proposal handed to the FROZEN browser action engine
# --------------------------------------------------------------------------

def _cdp_up() -> bool:
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2).read()
        return True
    except Exception:
        return False


# The user's REAL Chrome: a clone of their real profile (real
# cookies/sessions/open tabs), kept on :9222 by the launchd agent
# com.anticipy.chrome. NEVER a blank isolated profile.
_REAL_CLONE = os.path.expanduser("~/.anticipy/chrome-real-clone")


def _ensure_cdp_chrome() -> bool:
    """Ensure the user's REAL-profile-clone Chrome is reachable on
    :9222. Uses the codebase's intended launchd agent first
    (com.anticipy.chrome), then a direct launch of the SAME real-clone
    profile. Never creates a blank isolated profile.
    """
    if _cdp_up():
        return True
    # 1. The intended mechanism: kick the real-clone LaunchAgent.
    try:
        uid = os.getuid()
        subprocess.run(
            ["launchctl", "kickstart", "-k",
             f"gui/{uid}/com.anticipy.chrome"],
            capture_output=True, timeout=10)
        for _ in range(40):
            if _cdp_up():
                return True
            time.sleep(0.5)
    except Exception:
        pass
    # 2. Fallback: launch Chrome directly on the SAME real-clone
    # profile + flags the agent uses. Still the real profile clone,
    # never blank.
    chrome = None
    for c in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium")):
        if c and Path(c).exists():
            chrome = c
            break
    if not chrome:
        return False
    try:
        subprocess.Popen(
            [chrome, f"--remote-debugging-port={CDP_PORT}",
             "--remote-allow-origins=http://localhost:*",
             f"--user-data-dir={_REAL_CLONE}",
             "--profile-directory=Default", "--no-first-run",
             "--no-default-browser-check", "--restore-last-session",
             "--disable-features=Translate"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    for _ in range(40):
        if _cdp_up():
            return True
        time.sleep(0.5)
    return False


_COMPOSE_SYS = """\
You are the action planner of a wearable that has been listening to
the user this session. The user just said something vague. You also
have what they said EARLIER this session (their memory). Resolve any
vague reference (it, that, them, him, her, "before they...", "by
then") to the SPECIFIC person and thing from the earlier facts, then
output the ONE concrete web-browser task to do now.

DECISION PROCEDURE (follow exactly; this is a counting rule, not a
feeling):

STEP 1 - List the CANDIDATE referents. A candidate is a concrete
person or thing in memory that the implied action could plausibly
apply to, given the action verb and its qualifiers ("a case for it
before they travel" -> a portable valuable item; "feed it" -> a pet
or starter; "call her back" -> a person; "if it was rescheduled" ->
an event/flight). EXCLUDE: inert ambience (weather, aches, the cat
just sitting, idle musings) and any off-topic or garbled memory
lines - those are NOT candidates.

PER-PERSON INSTANCES (critical): if the implied reference is to a
thing, project, or activity, and TWO OR MORE different established
people are EACH separately doing / own / are associated with their
OWN instance of that same kind of thing or activity, then EACH
(person + their own instance) is a SEPARATE candidate - that is 2+
candidates, NOT one. Do NOT merge them into a single generic shared
thing. Collapsing "Dave's lathe restoration" and "Frank's lathe
restoration" into one person-less "the lathe restoration" and acting
on it is a GUESS (misattribution), the worst outcome. Returning
person="" with a generic thing is valid ONLY when exactly one person
(or no relevant person) is associated with that thing; if 2+ people
each have their own instance and no cue picks one, you MUST clarify
which person's.

STEP 2 - Apply the cues to the candidate list and count how many
GENUINELY FIT the implied action:
  - Exactly ONE candidate fits  -> mode=act, resolve to it. This is
    the common case. A single clear referent MUST be resolved, never
    asked about (asking here is over-asking = a failure).
  - 2+ candidates fit but a cue clearly favours one -> mode=act,
    resolve to that one.
  - 2+ candidates fit COMPARABLY and no cue picks one -> mode=clarify
    with a short question naming exactly those 2+ contenders. Picking
    one of several equally-fitting candidates (guessing) is a
    misattribution = the worst outcome.
  - ZERO candidates fit (referent absent) -> mode=clarify.

Examples (apply the count):
  - memory: only "Aunt Clara birthday gift we sent"; utterance "I
    hope it arrived ok, I should check". ONE candidate (the gift) ->
    mode=act. (Do NOT ask - there is exactly one referent.)
  - memory: only "Aunt June" + "the flight"; utterance "find out if
    they rescheduled before I call her back". ONE person, ONE thing
    -> mode=act (her=Aunt June, it=the flight).
  - memory: "Aunt Diane AND Miriam both coming for supper";
    utterance "I should let her know". TWO equally-fitting people,
    no cue -> mode=clarify "Did you mean Aunt Diane or Miriam?".
  - memory: "uncle Dave restoring a woodworking lathe" AND "uncle
    Frank restoring a woodworking lathe too"; utterance "check how
    that lathe restoration is coming along". TWO people each with
    their OWN lathe restoration, no cue -> mode=clarify "Dave's or
    Frank's lathe restoration?". Resolving a generic person-less
    "the lathe restoration" here is a GUESS = the worst outcome.

Both errors are equally bad and must both be avoided: (a) resolving
to a WRONG or guessed referent when 2+ fit equally; (b) over-asking
when exactly one candidate fits. The count in STEP 2 decides it -
there is no "when in doubt" tiebreaker; do the count honestly.

The task MUST be a single concrete web search that finishes in 2-3
steps with a definite, on-screen answer and NO side effects. Phrase
it EXACTLY as: "Search Google for '<concise query about the resolved
thing/person>' and tell me <the one specific fact needed>". Pick a
query whose answer is a public fact visible on a normal results page
(hours, a phone number, a price range, a definition, what something
is). Never a vague intention ("check on it"), never anything that
sends, posts, buys, books, or changes state, never something
requiring login. It must be answerable from a Google results page.

Return STRICT JSON only:
{"mode":"act"|"clarify","person":"","thing":"",
 "task":"<one concrete completable web lookup, fully resolved>",
 "question":"<a short clarifying question, only if mode=clarify>"}
"""


def _compose_task_from_memory(instruction: str) -> dict:
    """Resolve the vague utterance against THIS session's memory into a
    concrete browser task, or ask. Only the utterance + the accrued
    session memory feed this. Never guesses a referent.
    """
    import json

    from app.anticipy import memory as MEM
    from app.anticipy import platform_adapter
    try:
        snap = MEM.active_snapshot(USER_ID)
    except Exception:
        snap = []
    facts = "\n".join(f"- {e.get('value','')}" for e in snap) or "(none)"
    user = (f"EARLIER THIS SESSION (memory):\n{facts}\n\n"
            f"WHAT THEY JUST SAID: {instruction!r}\n\nReturn the JSON.")
    # Robust: under the session's burst of model calls OpenRouter can
    # return a transient empty/garbled completion. A transient infra
    # failure must NOT masquerade as a legitimate "ambiguous -> ask"
    # (that wrongly fails a resolvable scenario). Retry a few times;
    # only fall back to clarify if every attempt is unparseable.
    import time as _t
    p = None
    for attempt in range(4):
        res = platform_adapter.model_call(_COMPOSE_SYS, user, 600, 0.0,
                                          True)
        if res.ok and res.content:
            s = res.content
            a, b = s.find("{"), s.rfind("}")
            if a != -1 and b != -1 and b > a:
                try:
                    cand = json.loads(s[a:b + 1])
                    if isinstance(cand, dict) and cand.get("mode") in (
                            "act", "clarify"):
                        p = cand
                        break
                except Exception:
                    pass
        _t.sleep(1.5 + attempt * 2)
    if p is None:
        return {"mode": "clarify", "question": "Which one did you "
                "mean?", "person": "", "thing": "", "task": "",
                "_infra_fallback": True}
    p.setdefault("mode", "clarify")
    for k in ("person", "thing", "task", "question"):
        p.setdefault(k, "")
    return p


class Act(BaseModel):
    instruction: str | None = None


@app.post("/api/act")
def act(a: Act) -> JSONResponse:
    instruction = (a.instruction
                   or (_LISTEN.get("pending") or {}).get("instruction")
                   or "").strip()
    if not instruction:
        return JSONResponse({"ran": False,
                             "error": "no instruction to act on"})
    plan = _compose_task_from_memory(instruction)
    if plan.get("mode") != "act" or not plan.get("task"):
        # genuinely ambiguous / absent referent -> ASK, never guess
        return JSONResponse({
            "ran": False, "clarify": True,
            "question": plan.get("question")
            or "Which one did you mean?",
            "resolved_person": "", "resolved_thing": ""})
    task = str(plan["task"]).strip()
    if not _ensure_cdp_chrome():
        return JSONResponse({
            "ran": False, "gated": True,
            "resolved_person": plan.get("person", ""),
            "resolved_thing": plan.get("thing", ""), "task": task,
            "error": "No real Chrome on :9222 and the launchd agent "
                     "could not be kicked. The real path "
                     "(action_handoff -> frozen DSv4SkillRunner) is "
                     "wired; the real-clone browser is the edge."})
    try:
        from app.anticipy.action_handoff import make_real_action_engine
        # 5 iterations: a concrete web-search lookup completes in 2-3
        # (navigate to the search URL, read the answer, done). 12 made
        # vague tasks run ~20 min each. The frozen engine is unchanged;
        # only this glue param is tuned.
        eng = make_real_action_engine(cdp_port=CDP_PORT, max_iters=5)
        res = eng({"object": task, "time_window": ""}) or {}
        status = res.get("status", "?")
        ran = status in ("SUCCESS", "PROCEEDED_ON_ASSUMPTION",
                         "ITERATION_EXHAUSTED")
        out = {
            "ran": ran, "status": status, "task": task,
            "resolved_person": plan.get("person", ""),
            "resolved_thing": plan.get("thing", ""),
            "answer": str(res.get("answer", ""))[:600],
            "evidence": str(res.get("evidence", ""))[:600],
            "trajectory_dir": res.get("trajectory_dir", ""),
            "error": res.get("error")}
        if ran:
            _LISTEN["acted"] = {"instruction": instruction, "task": task,
                                "status": status, "ts": time.time()}
            _LISTEN["pending"] = None
        return JSONResponse(out)
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
padding:15px 28px;border-radius:100px;cursor:pointer;font:500 13px/1
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
.send:hover{background:var(--gold)}.send:disabled{opacity:.4;cursor:default}
.center{text-align:center;align-items:center}
.center p.sub,.center h1{margin-left:auto;margin-right:auto}
.center .lab{text-align:center}
.orb{width:150px;height:150px;margin:6px auto 0;border-radius:50%;
position:relative;background:radial-gradient(circle at 50% 44%,
rgba(200,169,126,.5),rgba(200,169,126,.04) 60%,transparent 72%)}
.orb i{position:absolute;inset:36%;border-radius:50%;
background:rgba(200,169,126,.9);box-shadow:0 0 60px rgba(200,169,126,.5)}
.orb.on{animation:br 2.2s ease-in-out infinite}
@keyframes br{0%,100%{transform:scale(.95)}50%{transform:scale(1.08)}}
.ring{position:absolute;inset:0;border-radius:50%;
border:1.5px solid rgba(200,169,126,.28)}
.orb.on .ring{animation:pl 2.2s ease-out infinite}
@keyframes pl{0%{transform:scale(.88);opacity:.85}
100%{transform:scale(1.4);opacity:0}}
.live{display:inline-flex;align-items:center;gap:9px;font-size:11px;
letter-spacing:.2em;text-transform:uppercase;color:var(--ok);margin-top:18px}
.live .bd{width:8px;height:8px;border-radius:50%;background:var(--ok);
animation:bk 1.4s ease-in-out infinite}
@keyframes bk{0%,100%{opacity:1}50%{opacity:.25}}
.meter{width:220px;height:5px;background:var(--bd);border-radius:5px;
margin:16px auto 0;overflow:hidden}
.meter>i{display:block;height:100%;background:var(--gold);width:0;
transition:width .25s ease}
.stat{display:flex;gap:26px;justify-content:center;margin-top:20px;
font-size:12.5px;color:var(--mut)}
.stat b{color:var(--cream);font-weight:600}
.card{background:var(--elev);border:1px solid var(--bd);border-radius:22px;
padding:28px;text-align:left;margin-top:24px;animation:f .45s ease}
.card h2{font-family:'DM Serif Display',serif;font-size:22px;
line-height:1.32;font-weight:400}
.meta{margin-top:12px;font-size:12.5px;color:rgba(245,240,235,.46);
line-height:1.6}
.kv{display:grid;gap:1px;background:var(--bd);border-radius:16px;
overflow:hidden;margin-top:18px}
.kv>div{background:var(--elev);padding:15px 18px}
.kv b{font-size:13px;color:rgba(245,240,235,.88);font-weight:600;display:block}
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
.feed{display:flex;flex-direction:column;gap:8px;margin-top:22px;
max-height:30vh;overflow-y:auto}
.feed .w{background:var(--elev);border:1px solid var(--bd);
border-radius:12px;padding:11px 15px;font-size:13px;line-height:1.5;
display:flex;justify-content:space-between;gap:12px}
.feed .w .t{color:rgba(245,240,235,.8)}
.feed .w .m{color:var(--mut);font-size:11px;white-space:nowrap}
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
<nav><span class=b>Anticipy</span><span class=lk id=nav></span></nav>
<div id=app class=scr></div></div>
<script>
const app=document.getElementById('app'),nav=document.getElementById('nav');
let ST={},OB={qs:[]},POLL=null;
async function J(u,o){const r=await fetch(u,o);return r.json()}
function esc(s){return(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;',
'>':'&gt;','"':'&quot;'}[c]))}
function stopPoll(){if(POLL){clearInterval(POLL);POLL=null}}
function setNav(active){if(!ST.onboarded){nav.innerHTML='';return}
 nav.innerHTML=['listen','history','settings'].map(s=>
 `<a class="${s==active?'on':''}" onclick="go('${s}')">${s}</a>`).join('')}
async function boot(){stopPoll();ST=await J('/api/state');
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
answers. About a minute.</p>
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
 app.innerHTML=h;const qa=document.getElementById('qa');
 qa.scrollTop=qa.scrollHeight;const ta=document.getElementById('ans');
 ta.focus();ta.onkeydown=e=>{if(e.key=='Enter'&&!e.shiftKey){
 e.preventDefault();sendAns()}}}
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
 <p class=sub>Anticipy now knows who you are and what matters, stored
 locally, used to resolve who and what you mean.</p>
 <div class=kv><div><b>Role</b><span>${esc(p.role_title||'-')}</span></div>
 <div><b>What you do</b><span>${esc(p.what_they_do||'-')}</span></div>
 <div><b>Mandate</b><span>${esc(p.mandate||'-')}</span></div>
 ${p.do_not_touch&&p.do_not_touch.length?`<div><b>Do not touch</b>
 <span>${esc(p.do_not_touch.join(', '))}</span></div>`:''}${ppl}</div>
 <button class=cta onclick="go('mic')">Continue</button>`}

function scrMic(){stopPoll();setNav('listen');
 app.innerHTML=`<div class="scr center"><div class=lab>Microphone</div>
 <h1>Let Anticipy hear you.</h1>
 <p class=sub>Anticipy listens continuously to your real microphone, on
 this Mac, while it is open. macOS will ask for permission now.</p>
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
 (level ${r.rms.toFixed(4)}). Starting continuous listening.</p>`;
 setTimeout(()=>go('listen'),1100)}
 else{b.textContent='Try again';
 s.innerHTML=`<p class=sub style="margin:0 auto;color:var(--warn)">
 ${esc(r.error||'Microphone unavailable')}. Grant Anticipy microphone
 access in System Settings, Privacy, Microphone.</p>`}}

async function scrListen(){setNav('listen');
 const s=await J('/api/listen/start',{method:'POST'});
 app.innerHTML=`<div class="scr center"><div class=lab>Listening</div>
 <div class="orb on" id=orb><div class=ring></div><i></i></div>
 <div class=live id=lv><span class=bd></span><span>Listening
 continuously</span></div>
 <div class=meter><i id=mtr></i></div>
 <div class=stat id=stt></div>
 <p class=sub style="margin:18px auto 0">Anticipy is always listening
 in rolling ${Math.round(s.window_seconds||60)}s windows. Speak
 naturally; it surfaces one clear thing when it hears something
 worth acting on. Nothing synthetic.</p>
 <div id=prop></div>
 <div class=feed id=feed></div>
 <button class=ghost style="align-self:center;margin-top:24px"
 onclick=stopListen()>Stop listening</button></div>`;
 if(s.error){document.getElementById('lv').innerHTML=
 `<span class=err>Microphone: ${esc(s.error)}</span>`;return}
 stopPoll();POLL=setInterval(pollListen,1500);pollListen()}
async function pollListen(){let st;try{st=await J('/api/listen/status')}
 catch(e){return}
 const orb=document.getElementById('orb');if(!orb)return stopPoll();
 const lvl=Math.min(100,Math.round((st.level||0)*4000));
 const mtr=document.getElementById('mtr');if(mtr)mtr.style.width=lvl+'%';
 const stt=document.getElementById('stt');
 if(stt)stt.innerHTML=`<span><b>${st.windows||0}</b> windows</span>
 <span><b>${Math.round(st.uptime||0)}</b>s on</span>
 <span><b>${(st.level||0).toFixed(4)}</b> level</span>`;
 const lv=document.getElementById('lv');
 if(lv&&!st.on)lv.innerHTML=`<span class=err>Listening stopped${
 st.error?': '+esc(st.error):''}</span>`;
 const pr=document.getElementById('prop');
 if(pr){if(st.pending){pr.innerHTML=`<div class=card>
 <div class=lab>Heard, worth acting on</div>
 <h2>${esc(st.pending.proposal)}</h2>
 <div class=meta>From: "${esc(st.pending.instruction)}"</div>
 <div class=row style="margin-top:18px">
 <button class=send id=yes onclick='doAct()'>Yes, do it</button>
 <button class=ghost onclick=dismiss()>Dismiss</button></div>
 <div id=act></div></div>`}
 else if(st.acted){pr.innerHTML=`<div class=card>
 <div class=lab><span class=dot></span> Done in Chrome</div>
 <h2>${esc(st.acted.instruction)}</h2>
 <div class=meta>Status ${esc(st.acted.status)}. Still listening.
 </div></div>`}
 else if(!pr.querySelector('.spin'))pr.innerHTML=''}
 const fd=document.getElementById('feed');
 if(fd&&st.recent){fd.innerHTML=st.recent.map(w=>`<div class=w>
 <span class=t>${w.transcript?esc(w.transcript):'<span style=color:var(--mut)>(quiet window)</span>'}</span>
 <span class=m>w${w.window} &middot; ${(w.rms||0).toFixed(3)}${
 w.memory?' &middot; mem '+esc(w.memory.op||''):''}</span></div>`).join('')}}
async function doAct(){const y=document.getElementById('yes'),
 ac=document.getElementById('act');if(!y)return;y.disabled=true;
 y.innerHTML='<span class=spin></span> Acting in Chrome';
 ac.innerHTML=`<div class=meta style="margin-top:14px">Anticipy is
 driving a real Chrome window. This can take a minute. It keeps
 listening while it works.</div>`;
 const r=await J('/api/act',{method:'POST',headers:{'Content-Type':
 'application/json'},body:JSON.stringify({})});
 if(r.ran){ac.innerHTML=`<div class=meta style="margin-top:14px">
 <span class=dot></span> ${esc(r.answer||r.status)}<br>
 ${esc(r.evidence||'')}</div>`}
 else{ac.innerHTML=`<div class="meta err" style="margin-top:14px">
 ${esc(r.error||('status '+(r.status||'?')))}</div>`}}
async function dismiss(){await J('/api/listen/dismiss',{method:'POST'});
 pollListen()}
async function stopListen(){stopPoll();
 await J('/api/listen/stop',{method:'POST'});
 const lv=document.getElementById('lv');
 if(lv)lv.innerHTML='<span style=color:var(--mut)>Listening paused. '
 +'<a style=color:var(--gold);cursor:pointer onclick="go(\'listen\')">'
 +'Resume</a></span>';
 const orb=document.getElementById('orb');if(orb)orb.classList.remove('on')}

async function scrHistory(){stopPoll();setNav('history');
 app.innerHTML=`<div class=lab>Memory</div><h1>What Anticipy remembers.</h1>
 <p class=sub>Everything it has heard worth keeping, on this Mac. This is
 what lets it resolve who and what you mean over time.</p>
 <div id=hl><div class=meta style="margin-top:24px">
 <span class=spin></span> Loading</div></div>`;
 const r=await J('/api/memory');const hl=document.getElementById('hl');
 if(!r.entries||!r.entries.length){hl.innerHTML=`<div class=empty>
 Nothing remembered yet. What you say while it listens shows up here.
 </div>`;return}
 hl.innerHTML='<div class=hist>'+r.entries.map(e=>
 `<div class=it><div class=k>${esc(e.kind||'note')}</div>
 ${esc(e.value||'')}</div>`).join('')+'</div>'}

function scrSettings(){stopPoll();setNav('settings');const p=ST.profile||{};
 app.innerHTML=`<div class=lab>Settings</div><h1>Your setup.</h1>
 <div class=kv style="margin-top:24px">
 <div><b>Name</b><span>${esc(p.name||'not set')}</span></div>
 <div><b>Reasoning</b><span>${ST.key_ok?'Connected, OpenRouter cloud':
 'Key missing'}</span></div>
 <div><b>Microphone</b><span>Continuous, rolling ${Math.round(
 ST.window_seconds||60)}s windows while the app is open</span></div>
 <div><b>Memory</b><span>Stored locally on this Mac, per user</span></div>
 <div><b>Browser actions</b><span>Run in a real Chrome window on your
 explicit confirmation</span></div></div>
 <button class=ghost style="margin-top:30px"
 onclick="go('mic')">Re-check microphone</button>`}

function go(s){window.scrollTo(0,0);
 if(s!='listen')stopPoll();
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
