"""S5 guarded-step cell — deterministic verify-and-recover unit test.

Pins the anti-self-grading read-back layers (§4.2), the L0–L5 recovery ladder
(§4.3), the nine contingency detectors (§4.4), the loop/stuck detectors + the
frontier-call cap (§4.6), and that agent/proof.py's confirm_stable_artifact is
genuinely CALLED for irreversible-artifact confirmation.

Zero model calls, zero network — the whole point is that verification is
deterministic code, never the acting model.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_guarded_step.py
"""
import asyncio

from anticipy_engine.agent.guarded_step import (
    Contingency,
    FrontierBudget,
    Ladder,
    LadderState,
    LoopDetector,
    Progress,
    captcha_recovery,
    classify_contingency,
    confirm_irreversible,
    next_recovery,
    readback_verify,
    state_delta,
    success_token_present,
    typed_field_landed,
)


# ── Layer 1: state delta (the ~34.2% silent-no-op class) ──────────────────────
def test_state_delta():
    assert state_delta("a", "a") is Progress.NO_CHANGE
    assert state_delta("a", "b") is Progress.PROGRESS
    assert state_delta("a", "b", visited={"b": 1}) is Progress.REGRESSION
    print("PASS state_delta: NO_CHANGE / PROGRESS / REGRESSION off signatures")


# ── Layer 2a: typed-field read-back (.value == intent) — the silent-write class ─
def test_typed_field_readback():
    landed = {"elements": [{"idx": 3, "name": "Email", "value": "a@b.com"}]}
    silent = {"elements": [{"idx": 3, "name": "Email", "value": ""}]}
    reformatted = {"elements": [{"idx": 5, "name": "Zip", "state": "value=90210"}]}
    assert typed_field_landed(landed, "a@b.com", index=3) is True
    assert typed_field_landed(silent, "a@b.com", index=3) is False, "silent-write must NOT pass"
    assert typed_field_landed(reformatted, "90210", index=5) is True, "read .value from state="
    assert typed_field_landed(landed, "a@b.com", name="Email") is True, "match by name too"
    print("PASS typed_field: value==intent lands; empty value is caught as silent-write")


# ── Layer 2b: success token (the un-fakeable receipt) ─────────────────────────
def test_success_token():
    echoed = {"text": 'order-XZ9 received', "url": "https://httpbin.org/post"}
    assert success_token_present(echoed, ["order-XZ9"]) is True
    assert success_token_present(echoed, ["order-NOPE"]) is False
    assert success_token_present({"text": ""}, ["x"]) is False
    print("PASS success_token: an echoed receipt confirms a submit; absence does not")


# ── A4 readback_verify dispatches to the right layer ──────────────────────────
def test_readback_verify_dispatch():
    # A type whose value landed passes even if the coarse sig didn't move.
    obs = {"elements": [{"idx": 1, "name": "Name", "value": "Ada"}], "url": "u", "text": ""}
    v = readback_verify({"action": "type", "index": 1}, prev_sig="s", new_obs=obs,
                        new_sig="s", intent="Ada")
    assert v.ok and v.mode == "typed_field", v

    # A type whose value is empty is a silent-write => not ok.
    obs2 = {"elements": [{"idx": 1, "name": "Name", "value": ""}], "url": "u", "text": ""}
    v2 = readback_verify({"action": "type", "index": 1}, prev_sig="s", new_obs=obs2,
                         new_sig="s", intent="Ada")
    assert not v2.ok and v2.mode == "typed_field", v2

    # A submit with the receipt token present passes.
    obs3 = {"text": "Thank you order-99", "url": "u2", "elements": []}
    v3 = readback_verify({"action": "click", "text": "Submit"}, prev_sig="s", new_obs=obs3,
                         new_sig="s2", success_tokens=["order-99"])
    assert v3.ok and v3.mode == "success_token", v3

    # A plain click that moved the page passes on state-delta.
    v4 = readback_verify({"action": "click"}, prev_sig="s", new_obs={"url": "u3"}, new_sig="s3")
    assert v4.ok and v4.mode == "state_delta" and v4.progress is Progress.PROGRESS, v4

    # A plain click that changed nothing fails (silent no-op).
    v5 = readback_verify({"action": "click"}, prev_sig="s", new_obs={"url": "u"}, new_sig="s")
    assert not v5.ok and v5.progress is Progress.NO_CHANGE, v5
    print("PASS readback_verify: routes type/submit/click to the correct deterministic layer")


# ── §4.4 the nine contingency detectors ───────────────────────────────────────
def test_contingency_classifier():
    ok = readback_verify({"action": "click"}, prev_sig="s", new_obs={"url": "u2"}, new_sig="s2")
    noop = readback_verify({"action": "click"}, prev_sig="s", new_obs={"url": "u"}, new_sig="s")
    silent = readback_verify({"action": "type", "index": 1}, prev_sig="s",
                             new_obs={"elements": [{"idx": 1, "value": ""}]}, new_sig="s", intent="x")

    assert classify_contingency(verify=ok, page_text="all good") is Contingency.NONE
    assert classify_contingency(verify=noop, page_text="unusual traffic detected") is Contingency.CAPTCHA
    assert classify_contingency(verify=noop, page_text="please log in to continue") is Contingency.LOGIN
    assert classify_contingency(verify=noop, page_text="enter the verification code we sent") is Contingency.MFA
    assert classify_contingency(verify=noop, page_text="429 too many requests") is Contingency.RATE_LIMIT
    assert classify_contingency(verify=silent, page_text="") is Contingency.SILENT_WRITE
    assert classify_contingency(verify=noop, page_text="", target_missing=True) is Contingency.HALLUCINATED_CLICK
    assert classify_contingency(verify=noop, page_text="", has_modal=True) is Contingency.MODAL
    assert classify_contingency(verify=noop, page_text="", is_loop=True) is Contingency.LOOP
    assert classify_contingency(verify=noop, page_text="") is Contingency.SILENT_NOOP
    # A wall beats an incidental loop flag (must not be papered over by a retry).
    assert classify_contingency(verify=noop, page_text="captcha", is_loop=True) is Contingency.CAPTCHA
    print("PASS contingency: all nine classes detected; walls win over transient/loop")


# ── §4.3 the L0–L5 recovery ladder (cheapest first; resets on PROGRESS) ────────
def test_recovery_ladder():
    # A wall goes straight to L4 human gate.
    st = LadderState(frontier=FrontierBudget(cap=2))
    d = next_recovery(Contingency.CAPTCHA, st)
    assert d.level is Ladder.L4_HANDOFF and d.remedy == "handoff", d

    # A transient goes to L1 tactical retry.
    d = next_recovery(Contingency.RATE_LIMIT, st)
    assert d.level is Ladder.L1_RETRY, d

    # First no-op (not yet stuck) -> L0 deterministic reroute, no frontier spend.
    st = LadderState(frontier=FrontierBudget(cap=2))
    d = next_recovery(Contingency.SILENT_NOOP, st)
    assert d.level is Ladder.L0_REROUTE and not d.uses_frontier, d

    # Stuck (>=2) -> L2 reflect+replan, spends a frontier call.
    st.consecutive_stuck = 2
    d = next_recovery(Contingency.SILENT_NOOP, st)
    assert d.level is Ladder.L2_REFLECT_REPLAN and d.uses_frontier, d
    st.replans_used += 1
    st.frontier.spend()

    # Replans spent -> L3 decompose (still frontier-gated).
    st.replans_used = st.max_replans
    d = next_recovery(Contingency.SILENT_NOOP, st)
    assert d.level is Ladder.L3_DECOMPOSE and d.uses_frontier, d
    st.decompositions_used = st.max_decompositions
    st.frontier.spend()  # exhaust the budget

    # Everything spent, still a real contingency -> L4 handoff (ask a human), NOT fake done.
    d = next_recovery(Contingency.SILENT_NOOP, st)
    assert d.level is Ladder.L4_HANDOFF, d

    # Hard step/budget ceiling -> L5 honest abandon.
    st.steps_exhausted = True
    d = next_recovery(Contingency.SILENT_NOOP, st)
    assert d.level is Ladder.L5_ABANDON and d.remedy == "abandon", d
    print("PASS recovery ladder: L0->L1->L2->L3->L4->L5 escalation is monotone and bounded")


# ── §4.6 loop detector + frontier cap ─────────────────────────────────────────
def test_loop_detector_and_frontier_cap():
    ld = LoopDetector(strike=3)
    h = LoopDetector.action_hash({"action": "click", "index": 14}, descriptor="Next")
    assert ld.record(h) == 1 and not ld.is_loop(h)
    assert ld.record(h) == 2 and not ld.is_loop(h)
    assert ld.record(h) == 3 and ld.is_loop(h), "3-strike must trip the loop detector"
    # A different action breaks the run.
    ld.record(LoopDetector.action_hash({"action": "scroll"}))
    assert not ld.is_loop(h)
    # Same descriptor across a re-indexed re-render is still the SAME action.
    a = LoopDetector.action_hash({"action": "click", "index": 5}, descriptor="State")
    b = LoopDetector.action_hash({"action": "click", "index": 9}, descriptor="State")
    assert a == b, "hash keyed on descriptor, not the transient index"
    # Regression memory.
    assert ld.record_state("sigA") is False
    assert ld.record_state("sigA") is True

    fb = FrontierBudget(cap=2)
    assert fb.spend() and fb.spend()
    assert not fb.can_spend() and not fb.spend(), "frontier cap must be exhaustible"
    assert fb.remaining == 0
    print("PASS detectors: 3-strike loop, descriptor-keyed hash, exhaustible frontier cap")


# ── §4.2 tail: confirm_stable_artifact is genuinely wired for irreversibles ────
async def test_confirm_irreversible_wires_proof():
    # A stable artifact confirms across repeated reads.
    reads = [({"url": "https://httpbin.org/post", "ok": True}, "shot")] * 3

    async def read_stable():
        return reads.pop(0)

    async def no_sleep(_s):
        return None

    proof = await confirm_irreversible(read_stable, lambda o: bool(o.get("ok")),
                                       reads=3, delay_seconds=0.1, sleep=no_sleep)
    assert proof.confirmed is True and proof.reads == 3, proof

    # A flicker (present then gone) fails closed at the first bad read.
    flick = [({"ok": True}, "a"), ({"ok": False}, "b"), ({"ok": True}, "c")]

    async def read_flicker():
        return flick.pop(0)

    proof2 = await confirm_irreversible(read_flicker, lambda o: bool(o.get("ok")),
                                        reads=3, delay_seconds=0.0)
    assert proof2.confirmed is False and proof2.failed_read_index == 1, proof2
    print("PASS confirm_irreversible: confirm_stable_artifact enforces repeated read-back")


# ── S6 §4.4 row 5 amended: CAPTCHA auto-solve wired into the ladder ───────────
class _FakeSolver:
    """Minimal captcha solver stand-in for the bridge test."""

    def __init__(self, token="TOK"):
        self.available = True
        self._token = token

    def solve(self, challenge):
        from anticipy_engine.hands.captcha_solver import SolveResult
        if self._token:
            return SolveResult(True, token=self._token, provider="fake", kind=challenge.kind)
        return SolveResult(False, kind=challenge.kind, error="fake fail")


def test_captcha_autosolve_wiring():
    # Default (no solver configured) preserves the design-of-record pause->text.
    st = LadderState()
    assert next_recovery(Contingency.CAPTCHA, st).level is Ladder.L4_HANDOFF

    # Solver configured + budget remaining -> L0 auto-solve (0 LLM, no frontier spend).
    st = LadderState(captcha_solver_available=True, max_captcha_solves=2)
    d = next_recovery(Contingency.CAPTCHA, st)
    assert d.level is Ladder.L0_REROUTE and d.remedy == "solve_captcha" and not d.uses_frontier, d

    # Solve budget exhausted -> fall through to the L4 human gate (never loop forever).
    st.on_captcha_solve_fail()
    st.on_captcha_solve_fail()
    assert next_recovery(Contingency.CAPTCHA, st).level is Ladder.L4_HANDOFF

    # The bridge really solves: detect a captcha + a solver -> token + injection.
    page = {"url": "https://x.test", "html": '<div class="g-recaptcha" data-sitekey="K"></div>'}
    out = captcha_recovery(page, _FakeSolver(token="ABC"))
    assert out.solved and out.token == "ABC" and "ABC" in out.injection, out
    # A failed solve -> not solved (caller bumps the budget -> L4).
    assert captcha_recovery(page, _FakeSolver(token="")).solved is False
    # No captcha on the page -> not solved, no crash.
    assert captcha_recovery({"url": "u", "html": "<p>clean</p>"}, _FakeSolver()).solved is False
    print("PASS captcha auto-solve: ladder solves-then-handoff; bridge returns token+injection")


async def main():
    test_state_delta()
    test_typed_field_readback()
    test_success_token()
    test_readback_verify_dispatch()
    test_contingency_classifier()
    test_recovery_ladder()
    test_loop_detector_and_frontier_cap()
    test_captcha_autosolve_wiring()
    await test_confirm_irreversible_wires_proof()
    print("ALL GUARDED-STEP TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
