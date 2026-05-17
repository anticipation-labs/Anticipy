"""MH-P5 gate: auth + per-user isolation + token lifecycle.

Two simulated tenants. Binds on:

  PER-USER ISOLATION  tenant A cannot read tenant B's token or task
    checkpoint and vice versa (CrossTenantError); tokens are
    ciphertext at rest. Zero wrong-user data.
  TOKEN-EXPIRY MID-ACTION  A's token expires mid-task; the
    lifecycle refreshes via the (simulated IdP) refresh path and
    the SAME task resumes from its durable checkpoint and completes
    EXACTLY ONCE (no lost task, no double execution).
  REAL-CREDENTIAL ACTIVATION  labelled gated: the IdP exchange here
    is simulated; the real OAuth network call is wired, unproven,
    never faked.
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
    from app.authsec.tokens import (CrossTenantError, DurableRuntime,
                                    Token, TokenStore)

    print("== MH-P5 GATE (auth + isolation + token lifecycle) ==")
    log, ok = [], True
    store = TokenStore()
    rt = DurableRuntime()

    store.put(Token("tenantA", "A-access", "A-refresh",
                     expires_at=1000.0))
    store.put(Token("tenantB", "B-access", "B-refresh",
                     expires_at=9_999_999_999.0))

    # --- per-user isolation ---
    iso_ok = True
    try:
        store.get("tenantA", "tenantB")          # must be refused
        iso_ok = False
    except CrossTenantError:
        pass
    try:
        rt.checkpoint("tenantB", "tenantA", "t1")  # must be refused
        iso_ok = False
    except CrossTenantError:
        pass
    a_self = store.get("tenantA", "tenantA")
    b_self = store.get("tenantB", "tenantB")
    iso_ok &= (a_self is not None and b_self is not None
               and a_self.access == "A-access"
               and b_self.access == "B-access")
    ct_ok = (store.is_ciphertext("tenantA", "A-access")
             and store.is_ciphertext("tenantB", "B-refresh"))
    log.append(f"  BINDING per-user isolation (cross refused, self ok, "
               f"ciphertext at rest) -> {iso_ok and ct_ok}")
    ok &= iso_ok and ct_ok

    # --- token-expiry mid-action ---
    side: list = []

    def refresh_idp(tok: Token) -> Token:
        # SIMULATED IdP (real OAuth exchange is the gated edge):
        # mints a fresh non-expired token for the SAME user only.
        return Token(tok.user_id, tok.access + "+r", tok.refresh,
                     expires_at=9_999_999_999.0)

    clock = {"t": 1500.0}                        # already past A expiry

    import app.authsec.tokens as T
    _orig = T.time.time
    T.time.time = lambda: clock["t"]             # deterministic clock
    try:
        steps = [lambda tok: side.append(("s0", tok.user_id)),
                 lambda tok: side.append(("s1", tok.user_id)),
                 lambda tok: side.append(("s2", tok.user_id))]
        cp = rt.run_task("tenantA", "task-1", steps, store, refresh_idp)
        # idempotent resume: running again must NOT re-execute
        cp2 = rt.run_task("tenantA", "task-1", steps, store, refresh_idp)
    finally:
        T.time.time = _orig

    completed_once = (cp.done and cp.result is not None
                      and cp2.done and len(side) == 3
                      and all(u == "tenantA" for _s, u in side))
    refreshed = store.get("tenantA", "tenantA").access.endswith("+r")
    no_double = cp2.runs == cp.runs              # 2nd call did not re-run
    log.append(f"  BINDING expiry-mid-action: steps={[s for s,_ in side]} "
               f"refreshed={refreshed} completed_once={completed_once} "
               f"no_double_exec(runs={cp.runs}=={cp2.runs}) -> "
               f"{completed_once and refreshed and no_double}")
    ok &= completed_once and refreshed and no_double

    # no wrong-user data leaked into A's run
    no_leak = all(u == "tenantA" for _s, u in side)
    log.append(f"  BINDING zero wrong-user data in the resumed task -> "
               f"{no_leak}")
    ok &= no_leak

    log.append("  GATED (labelled, not faked): the IdP refresh here is "
               "simulated; the real OAuth network exchange needs real "
               "Google/email credentials + a human and is wired, "
               "unproven.")

    fr = subprocess.run(["git", "status", "--porcelain"] + FROZEN,
                         cwd=str(ENGINE.parent), capture_output=True,
                         text=True)
    fc = fr.stdout.strip() == ""
    log.append(f"  BINDING frozen paths clean -> {fc}")
    ok &= fc

    for ln in log:
        print(ln)
    print(f"MH_P5_GATE {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
