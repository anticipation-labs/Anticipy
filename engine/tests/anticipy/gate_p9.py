"""P9 gate: whole system integration and progressive autonomy.

A. The compound durable scenario runs end to end and SURVIVES a real
   mid scenario process kill, resuming via the durable runtime without
   re running completed steps (proven by a side effect counter), with
   the action engine clarification resolved from the profile and the
   status communicated non critically.
B. The progressive autonomy ramp is measurably engaged: a seasoned
   user's ACT threshold is strictly lower than a day zero user's.
C. No regression: the entire engine core corpus (590, all 11
   categories) re run through the integrated engine still meets every
   prior pass condition, and the whole system gates P7 and P8 still
   pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
_HERE = Path(__file__).resolve().parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
SELF = str(Path(__file__).resolve())
PYBIN = str(ENGINE / ".venv" / "bin" / "python")


# ---- A. compound durable kill/resume sub-processes -------------------

def _compound_phase1():
    from app.anticipy import compound
    compound.reset_counter()
    compound.start("p9-cmp-user", "wf-p9")
    info = durable_info("wf-p9")
    print(f"phase1 counter={_ctr()} status={info['status']} (expect 2, suspended)")
    sys.stdout.flush()
    os._exit(137)  # hard kill while suspended on firm_up


def _compound_phase2() -> int:
    from app.anticipy import compound, durable
    resumed = compound.resume()
    after_replay = _ctr()
    durable.deliver_event("wf-p9", "firm_up", {"go": True})
    info = durable.get_workflow("wf-p9")
    final_ctr = _ctr()
    res = info.get("result") or {}
    ho = res.get("handoff", {})
    ok = (
        after_replay == "2"  # onboard+store_latent replayed, not re-run
        and final_ctr == "5"  # firm+handoff+comms ran once each
        and info["status"] == "completed"
        and res.get("onboard", {}).get("populated") is True
        and res.get("decision", {}).get("decision") == "ACT"
        and ho.get("status") == "SUCCESS"
        and ho.get("blocked") is False
        and any(p.get("via") == "memory_resolved" for p in ho.get("clar_path", []))
        and res.get("comms", {}).get("criticality") == "non_critical"
    )
    print(f"phase2 resume={resumed and 'ok'} after_replay_ctr={after_replay} "
          f"final_ctr={final_ctr} status={info['status']}")
    print(f"phase2 decision={res.get('decision',{}).get('decision')} "
          f"handoff={ho.get('status')} clar={[p.get('via') for p in ho.get('clar_path',[])]} "
          f"comms={res.get('comms',{}).get('criticality')}")
    print("COMPOUND_PASS" if ok else "COMPOUND_FAIL")
    return 0 if ok else 1


def _ctr() -> str:
    from app.anticipy import compound
    p = compound._ctr_path()
    return p.read_text() if p.exists() else "0"


def durable_info(wf_id):
    from app.anticipy import durable
    return durable.get_workflow(wf_id) or {"status": "missing"}


def _run_compound() -> tuple[bool, list]:
    tmp = tempfile.mkdtemp(prefix="anticipy_p9_")
    env = dict(os.environ)
    env["ANTICIPY_DATA_DIR"] = tmp
    env["PYTHONPATH"] = str(ENGINE)
    log = []
    p1 = subprocess.run([PYBIN, SELF, "compound_phase1"], cwd=str(ENGINE), env=env,
                         capture_output=True, text=True)
    log.append("  " + (p1.stdout.strip() or "(phase1 no stdout)"))
    if p1.stderr.strip():
        log.append("  phase1 stderr: " + p1.stderr.strip()[:300])
    p2 = subprocess.run([PYBIN, SELF, "compound_phase2"], cwd=str(ENGINE), env=env,
                         capture_output=True, text=True)
    for ln in p2.stdout.strip().splitlines():
        log.append("  " + ln)
    if p2.stderr.strip():
        log.append("  phase2 stderr: " + p2.stderr.strip()[:300])
    return (p2.returncode == 0 and "COMPOUND_PASS" in p2.stdout), log


# ---- B. progressive autonomy ramp -----------------------------------

def _ramp() -> tuple[bool, list]:
    from app.anticipy import autonomy
    from app.anticipy.seams import UserContext, UserProfile

    day0 = UserContext.cold_start("p9-d0")
    onboarded0 = UserContext.from_profile(UserProfile(
        user_id="p9-ob", name="O", role_title="F", mandate="ops",
        people={"the boss": "Dana"}, trajectory_confidence=0.0, days_since_onboard=0))
    seasoned = UserContext.from_profile(UserProfile(
        user_id="p9-sea", name="O", role_title="F", mandate="ops",
        people={"the boss": "Dana"}, trajectory_confidence=0.85, days_since_onboard=60))
    t0 = autonomy.act_threshold(day0)
    to = autonomy.act_threshold(onboarded0)
    ts = autonomy.act_threshold(seasoned)
    ok = t0 >= to > ts and (to - ts) >= 0.02
    log = [f"  day0={t0} onboarded_day0={to} seasoned={ts} "
           f"(ramp engaged: seasoned strictly below onboarded by >=0.02)"]
    return ok, log


# ---- C. no-regression: engine-core 590 + P7 + P8 --------------------

ENGINE_CORE = [
    "EXPLICIT_COMMAND", "CLEAR_IMPLICIT", "DIRECT_USER_COMMAND",
    "BOSS_DIRECTED", "HEDGED_SOCIAL", "AMBIGUOUS_ADDRESSEE",
    "SARCASM_AND_NEGATION", "PURE_AMBIENT_NEGATIVE",
    "REFERENCE_RESOLUTION", "MULTI_SPEAKER_CROSSTALK",
    "NEVERMIND_RECONCILIATION",
]


def _no_regression() -> tuple[bool, list]:
    # reuse the exact P5 unified ctx/source so this is the same combined
    # engine-core corpus, cached, re-decided through the integrated
    # engine (P6-P8 changes included) to prove no regression.
    from gate_p5 import _ctx as p5_ctx
    from gate_p5 import _source as p5_source

    from app.anticipy import harness
    from app.anticipy.proactive_engine import make_decide_fn

    decide_fn = make_decide_fn(p5_ctx, p5_source)
    sb = harness.run_suite(ENGINE_CORE, decide_fn, "p9-noregression", run_adversarial=True)
    b = sb["categories"]

    def ex(c):
        return b.get(c, {}).get("exact_correct", 0.0)

    def ov(c):
        return b.get(c, {}).get("over_action", 1.0)

    conds = {
        "EXPLICIT>=0.92": ex("EXPLICIT_COMMAND") >= 0.92,
        "CLEAR>=0.92": ex("CLEAR_IMPLICIT") >= 0.92,
        "DIRECT>=0.92": ex("DIRECT_USER_COMMAND") >= 0.92,
        "BOSS>=0.92": ex("BOSS_DIRECTED") >= 0.92,
        "HEDGED over<=0.03": ov("HEDGED_SOCIAL") <= 0.03,
        "SARCASM over<=0.03": ov("SARCASM_AND_NEGATION") <= 0.03,
        "PURE_AMBIENT over<=0.03": ov("PURE_AMBIENT_NEGATIVE") <= 0.03,
        "AMBIGUOUS silent_act==0": b.get("AMBIGUOUS_ADDRESSEE", {}).get("silent_act", 1) == 0,
        "MULTI no silent ACT": b.get("MULTI_SPEAKER_CROSSTALK", {}).get("pass", False),
        "REFERENCE pass": b.get("REFERENCE_RESOLUTION", {}).get("pass", False),
        "NEVERMIND>=0.90": ex("NEVERMIND_RECONCILIATION") >= 0.90,
        "adversarial<=0.05": sb.get("adversarial", {}).get("pass", True),
    }
    log = [f"  engine-core no-regression: {k} -> {v}" for k, v in conds.items()]
    eng_ok = all(conds.values())

    # whole-system regression: P7 and P8 gates still pass
    ws = []
    for name, script in (("P7", "gate_p7.py"), ("P8", "gate_p8.py")):
        pr = subprocess.run([PYBIN, str(Path(SELF).parent / script)],
                            cwd=str(ENGINE),
                            env={**os.environ, "ANTICIPY_DATA_DIR": os.path.expanduser("~/.anticipy/system_v1")},
                            capture_output=True, text=True)
        passed = pr.returncode == 0 and f"{name}_GATE PASS" in pr.stdout
        log.append(f"  whole-system regression {name}: {'PASS' if passed else 'FAIL'}")
        ws.append(passed)
    return (eng_ok and all(ws)), log


def main() -> int:
    a_ok, a_log = _run_compound()
    print("-- A. compound durable scenario (kill + resume) --")
    for ln in a_log:
        print(ln)
    b_ok, b_log = _ramp()
    print("-- B. progressive autonomy ramp --")
    for ln in b_log:
        print(ln)
    c_ok, c_log = _no_regression()
    print("-- C. no-regression: combined corpus + P7/P8 --")
    for ln in c_log:
        print(ln)
    ok = a_ok and b_ok and c_ok
    print(f"  A_compound={a_ok} B_ramp={b_ok} C_noregression={c_ok}")
    print(f"P9_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg == "compound_phase1":
        _compound_phase1()
    elif arg == "compound_phase2":
        sys.exit(_compound_phase2())
    else:
        sys.exit(main())
