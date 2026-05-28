"""MH-P1 gate: the real end-to-end flow, proven once start to finish.

BINDING (hard):
  speech     a REAL waveform was produced (synthetic wearer voice,
             the wearer's prior enrollment decision), not fabricated.
  audiostack REAL parakeet ASR produced a non-empty transcript from
             that real audio AND the FROZEN reasoning engine returned
             a real decision (not an ERROR).
  decide     the recognized utterance ran through the REAL
             proactive_day layers and produced EXACTLY ONE proposal
             (one real proposal from real spoken audio, never a
             flood, never zero).
  accounts   the real-accounts boundary is present and labelled
             SIMULATED, never a faked success.
  frozen     action engine + reasoning + cascade git-clean.

HONEST, not a failure (reported, must be present + labelled, never
faked): the mic-capture stage and the real-browser-action stage may
be GATED on a present human / granted TCC / a running CDP Chrome.
Gated-and-labelled is acceptable; faked is not.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

FROZEN = ["engine/app/action_engine", "desktop", "engine/app/anticipy",
          "engine/app/proactive/demand_detection.py",
          "engine/app/proactive/hedge_filter.py",
          "engine/app/proactive/intent_extraction.py",
          "engine/app/proactive/llm_adapter.py"]


def main() -> int:
    from app.e2e.flow import run_flow

    print("== MH-P1 GATE (real end-to-end flow) ==")
    fr = run_flow()

    log, ok = [], True
    for s in fr.stages:
        tag = "REAL" if s.real else ("GATED" if s.gated else "FAIL")
        log.append(f"  [{tag:5s}] {s.name:10s} {s.detail}")

    sp = fr.stage("speech")
    sp_ok = bool(sp and sp.real and sp.data.get("rms", 0) > 0.005)
    log.append(f"  BINDING speech real waveform -> {sp_ok}")
    ok &= sp_ok

    au = fr.stage("audiostack")
    tx = (au.data.get("transcript", "") if au else "")
    dec = (au.data.get("engine_decision", "") if au else "")
    au_ok = bool(au and au.real and tx.strip()
                 and dec and not dec.startswith("ERROR"))
    log.append(f"  BINDING real ASR transcript + frozen decision "
               f"(transcript={tx!r} decision={dec!r}) -> {au_ok}")
    ok &= au_ok

    de = fr.stage("decide")
    nprop = (de.data.get("n_outbound", 0) if de else 0)
    de_ok = bool(de and de.real and de.data.get("proposal") and nprop == 1)
    log.append(f"  BINDING exactly one real proposal from real spoken "
               f"audio (n={nprop}, proposal={fr.proposal!r}) -> {de_ok}")
    ok &= de_ok

    ac = fr.stage("accounts")
    ac_ok = bool(ac and ac.gated and "SIMULATED" in ac.detail
                 and not ac.real)
    log.append(f"  BINDING real-accounts boundary labelled SIMULATED "
               f"(not faked) -> {ac_ok}")
    ok &= ac_ok

    mic = fr.stage("mic")
    act = fr.stage("action")
    mic_present = bool(mic and (mic.real or mic.gated))
    act_present = bool(act and (act.real or act.gated))
    log.append(f"  HONEST mic stage present+labelled "
               f"(real={mic.real if mic else None} "
               f"gated={mic.gated if mic else None}) -> {mic_present}")
    log.append(f"  HONEST browser-action stage present+labelled "
               f"(real={act.real if act else None} "
               f"gated={act.gated if act else None}) -> {act_present}")
    ok &= mic_present and act_present

    fr2 = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                          cwd=str(ENGINE.parent), capture_output=True,
                          text=True)
    fc = fr2.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    if not fc:
        log.append(f"      DIRTY: {fr2.stdout.strip()!r}")
    ok &= fc

    for ln in log:
        print(ln)
    print("  NOTE segments that ran for REAL vs the honestly-labelled "
          "GATED edges are listed above; no gated edge is faked.")
    print(f"MH_P1_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
