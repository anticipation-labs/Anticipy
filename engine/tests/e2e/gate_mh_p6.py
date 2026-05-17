"""MH-P6 gate: failure recovery in the real world.

Adversarial interruption of an in-flight 3-op action: browser
hang, network drop mid-action, power loss at ~60%, and the site
changing under us. Binds on the single hard invariant:

  every interrupted action EITHER completes on resume (idempotent,
  exactly once) OR fails safe and SURFACES; it is NEVER left
  silently half-applied and NEVER double-applied.

frozen action engine + reasoning + cascade git-clean.
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
    from app.recovery.resume import Interrupt, Op, Recover

    print("== MH-P6 GATE (failure recovery in the real world) ==")
    log, ok = [], True

    def make_ops(effects, world=None):
        return [
            Op("op0", lambda: effects.append("op0"),
               (lambda: world["fact"]) if world else None),
            Op("op1", lambda: effects.append("op1"),
               (lambda: world["fact"]) if world else None),
            Op("op2", lambda: effects.append("op2"),
               (lambda: world["fact"]) if world else None),
        ]

    results = []

    # 1. browser hang before op0 -> resume completes
    for kind, idx in [("hang", 0), ("network", 2), ("power", 2)]:
        eff: list = []
        r = Recover()
        try:
            r.run(f"a-{kind}", make_ops(eff),
                   fault=(idx, Interrupt(kind)))
            raised = False
        except Interrupt:
            raised = True
        j = r.resume(f"a-{kind}", make_ops(eff))
        once = eff == ["op0", "op1", "op2"]        # exactly once, in order
        done = j.status == "completed"
        results.append((kind, raised and once and done, j.status, eff))

    # 2. site changed BEFORE applying op1 -> fail safe + surface
    eff_s: list = []
    surfaced: list = []
    rs = Recover()
    js = rs.run("a-site", make_ops(eff_s),
                fault=(1, Interrupt("site_changed")),
                surface=surfaced.append)
    site_ok = (js.status == "surfaced_failsafe" and js.surfaced
               and eff_s == ["op0"]               # op1/op2 NOT applied
               and len(surfaced) == 1)
    results.append(("site_changed_pre", site_ok, js.status, eff_s))

    # 3. site changed AFTER op applied, detected on RESUME -> surface,
    #    no blind continue
    eff_w: list = []
    world = {"fact": "v1"}
    rw = Recover()
    try:
        rw.run("a-drift", make_ops(eff_w, world),
               fault=(2, Interrupt("power")))      # die before op2
    except Interrupt:
        pass
    world["fact"] = "v2"                            # world moved
    surfaced2: list = []
    jw = rw.resume("a-drift", make_ops(eff_w, world),
                   surface=surfaced2.append)
    drift_ok = (jw.status == "surfaced_failsafe"
                and "op2" not in eff_w             # never blind-applied
                and len(surfaced2) == 1)
    results.append(("site_changed_on_resume", drift_ok, jw.status, eff_w))

    # --- the hard invariant over every scenario ---
    for name, good, status, eff in results:
        terminal = status in ("completed", "surfaced_failsafe")
        no_double = len(eff) == len(set(eff))      # no op re-applied
        inv = good and terminal and no_double
        log.append(f"  [{name:24s}] status={status:18s} effects={eff} "
                   f"-> {inv}")
        ok &= inv

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING every interrupt -> complete-on-resume OR "
               f"fail-safe-surface; never silent-half, never double "
               f"-> {ok and fc}")
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"MH_P6_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
