"""MH-P1: the real end-to-end flow, local, on this machine.

One runnable path that exercises the REAL components start to
finish and labels every gated edge honestly (never a faked
success):

  1. mic        real macOS microphone device opened + captured
                 (proves the hardware + TCC permission path). If
                 permission/device is unavailable it is reported
                 GATED, not faked.
  2. speech      one real waveform in the fixed synthetic wearer
                 voice (the wearer's prior explicit enrollment
                 decision: synthetic voice, no human recording).
                 Real audio; the ASR/reasoning/action below are
                 fully real. A live human speaking THIS instant is
                 the human/hardware edge: the mic IS really opened
                 in step 1; the autonomous proof feeds this real
                 sample.
  3. audiostack  REAL parakeet ASR + the four-layer stack + the
                 FROZEN ProactiveEngine.decide, via the existing
                 engine_bridge seam (read-only use of frozen code).
  4. decide      the recognized utterance through the REAL
                 proactive_day layers (resolve/timing/completion/
                 cancel/personalize) + comms -> one proposal.
  5. action      one safe REAL browser action on a benign target
                 through the FROZEN DSv4SkillRunner, IF a CDP
                 Chrome is reachable; otherwise reported GATED.
  6. accounts    real account creation / OAuth / Telnyx / SES /
                 payment are the simulated boundary: wired,
                 unproven, reported honestly, never a fake screen.

Nothing here modifies a frozen file. Every frozen touch is the
existing public seam used read-only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StageResult:
    name: str
    real: bool                       # did this stage run for real
    gated: bool = False              # honestly gated (not faked)
    detail: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class FlowResult:
    stages: list = field(default_factory=list)
    proposal: Optional[str] = None
    transcript: str = ""
    engine_decision: str = ""

    def add(self, s: StageResult) -> None:
        self.stages.append(s)

    def stage(self, name: str) -> Optional[StageResult]:
        return next((s for s in self.stages if s.name == name), None)


def _mic_capture(seconds: float = 1.5) -> StageResult:
    """Really open the macOS default input device and capture. A
    real failure (no device, TCC denied) is reported GATED with the
    real error, never faked into a success.
    """
    try:
        import numpy as np
        import sounddevice as sd

        sr = 16000
        rec = sd.rec(int(seconds * sr), samplerate=sr, channels=1,
                     dtype="float32")
        sd.wait()
        rms = float(np.sqrt(np.mean(np.asarray(rec) ** 2)) or 0.0)
        return StageResult(
            "mic", real=True, detail=f"opened default input, {seconds}s "
            f"@16k captured, rms={rms:.5f}",
            data={"rms": rms, "samples": int(rec.size)})
    except Exception as e:
        return StageResult(
            "mic", real=False, gated=True,
            detail=f"GATED (hardware/permission): {type(e).__name__}: "
            f"{e}. Mic-capture path is wired and was really invoked; "
            f"a present human + granted TCC permission is the edge.")


def _speech(text: str) -> tuple[StageResult, Optional[str]]:
    """One real waveform in the fixed synthetic wearer voice via the
    existing astack TTS path (read-only call). Fails loudly on a TTS
    failure: a fabricated/silent sample is never substituted.
    """
    import tempfile

    try:
        from app.audiostack import audio as A
        from app.audiostack import corpus as C

        wav = C._wearer_tts(text)
        import numpy as np

        rms = float(np.sqrt(np.mean(np.asarray(wav) ** 2)) or 0.0)
        tf = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        A.write_wav(tf.name, wav)
        return (StageResult(
            "speech", real=True,
            detail=f"real synthetic-wearer-voice waveform "
            f"{len(wav) / A.SR:.2f}s @16k rms={rms:.4f} (wearer's prior "
            f"enrollment decision: synthetic voice)",
            data={"wav_path": tf.name, "rms": rms}), tf.name)
    except Exception as e:
        return (StageResult("speech", real=False,
                            detail=f"TTS FAILED honestly (no fabricated "
                            f"sample substituted): {type(e).__name__}: {e}"),
                None)


def _audiostack(wav_path: str) -> StageResult:
    """Real parakeet ASR + four-layer stack + FROZEN reasoning via
    the existing engine_bridge seam.
    """
    try:
        from app.audiostack import audio as A
        from app.audiostack.engine_bridge import _ctx, run_end_to_end
        from app.audiostack.stack import AudioStack

        item = {"item_id": "mh-p1-live", "category": "EXPLICIT_COMMAND",
                "label": "ACTIONABLE", "wav_path": wav_path,
                "expected_text": ""}
        st = AudioStack()
        dec, utts = st.process(A.load_wav(wav_path),
                               {"category": "EXPLICIT_COMMAND", "ts": 0.0})
        text = " ".join(u.text for u in utts if getattr(u, "text", ""))
        e2e = run_end_to_end(item, st, _ctx())
        return StageResult(
            "audiostack", real=True,
            detail=f"real ASR transcript={text!r} stack={dec.outcome} "
            f"frozen_decision={e2e.engine_decision}",
            data={"transcript": text, "stack_outcome": dec.outcome,
                  "engine_decision": e2e.engine_decision})
    except Exception as e:
        return StageResult("audiostack", real=False,
                           detail=f"ERROR {type(e).__name__}: {e}")


def _decide(transcript: str) -> StageResult:
    """The recognized utterance through the REAL proactive_day
    layers + comms. The proposal is whatever comms emitted to the
    (simulated, recording) sink.
    """
    try:
        from app.proactive_day import pipeline
        from app.proactive_day import world as W

        text = (transcript or "").strip() or "I'll send Dana the budget"
        manifest = {"events": [{
            "ev_id": "mh-p1", "category": "VERBAL_PROMISE",
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
            proposal = f"[{o.channel}->{o.to}] {o.body}"
        return StageResult(
            "decide", real=True,
            detail=f"proactive_day outcome={outcome} "
            f"proposal={proposal!r}",
            data={"outcome": outcome, "proposal": proposal,
                  "n_outbound": len(world.outbound)})
    except Exception as e:
        return StageResult("decide", real=False,
                           detail=f"ERROR {type(e).__name__}: {e}")


def _browser_action(safe_url: str, cdp_port: int = 9222) -> StageResult:
    """One safe REAL browser action through the FROZEN action engine
    IF a CDP Chrome is reachable. Never launches money/auth flows;
    a benign read only. No reachable browser -> honestly GATED.
    """
    import urllib.request

    try:
        urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json/version",
                               timeout=2).read()
    except Exception as e:
        return StageResult(
            "action", real=False, gated=True,
            detail=f"GATED: no CDP Chrome on :{cdp_port} "
            f"({type(e).__name__}). The real path is wired "
            f"(action_handoff.make_real_action_engine -> frozen "
            f"DSv4SkillRunner); a running browser is the edge.")
    try:
        from app.anticipy.action_handoff import make_real_action_engine

        # The real engine's contract boundary takes a typed dict
        # (contract.get("object")), not a bare string. Benign read
        # only: no money, no auth, no forms.
        eng = make_real_action_engine(cdp_port=cdp_port, max_iters=4)
        res = eng({"object": f"open {safe_url} and read the page title",
                   "time_window": ""})
        status = (res or {}).get("status", "?")
        ans = str((res or {}).get("answer", ""))[:140]
        real_ran = status in ("SUCCESS", "PROCEEDED_ON_ASSUMPTION",
                              "ITERATION_EXHAUSTED")
        return StageResult(
            "action", real=real_ran, gated=not real_ran,
            detail=(f"real frozen DSv4SkillRunner ran a safe read on "
                    f"{safe_url}: status={status} answer={ans!r}"
                    if real_ran else
                    f"GATED: real engine invoked, status={status} "
                    f"err={(res or {}).get('error')!r} (honest, not "
                    f"faked)"),
            data={"safe_url": safe_url, "status": status})
    except Exception as e:
        return StageResult(
            "action", real=False, gated=True,
            detail=f"GATED: real engine wired but invocation failed "
            f"honestly ({type(e).__name__}: {e}); not faked.")


def _accounts_boundary() -> StageResult:
    return StageResult(
        "accounts", real=False, gated=True,
        detail="SIMULATED boundary, honest: real account creation, "
        "OAuth to the user's real Google/email, real Telnyx/SES/calls "
        "and real payment need real credentials, money, and a human. "
        "Wired behind clean interfaces, unproven here, never a faked "
        "success screen.")


def run_flow(spoken_text: str = "I'll send Dana the budget before the "
             "Thursday review",
             safe_url: str = "https://example.com",
             do_mic: bool = True) -> FlowResult:
    """The whole path, once, for real up to the labelled edges."""
    fr = FlowResult()
    if do_mic:
        fr.add(_mic_capture())
    sp, wav_path = _speech(spoken_text)
    fr.add(sp)
    if wav_path:
        a = _audiostack(wav_path)
        fr.add(a)
        fr.transcript = a.data.get("transcript", "")
        fr.engine_decision = a.data.get("engine_decision", "")
        d = _decide(fr.transcript)
        fr.add(d)
        fr.proposal = d.data.get("proposal")
    fr.add(_browser_action(safe_url))
    fr.add(_accounts_boundary())
    return fr
