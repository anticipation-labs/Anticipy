"""S6 signup-and-verify skill core — unit test.

Pins the typed params + precondition, the abstract selector-free step list, the composed
sub-steps (captcha solve + email code read), and — the load-bearing part — the un-gameable
verify contract: a deterministic signed-in read-back that rejects "form submitted", a
still-gated page, and a post-submit success flash that reverts (repeated-read proof). No
browser, no real signup — every outside call is injected.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_signup_verify.py
"""
import asyncio

from anticipy_engine.agent.signup_verify import (
    SIGNUP_STEPS,
    SignupRequest,
    StepKind,
    check_precondition,
    confirm_signed_up,
    fetch_verification_code,
    handle_captcha_step,
    verify_signed_up,
)
from anticipy_engine.hands.captcha_solver import CaptchaSolver
from anticipy_engine.hands.email_verifier import VerificationEmail


def test_params_and_precondition():
    ok = SignupRequest(service_url="https://svc.test/signup", email="me@inbox.test")
    assert ok.missing_required() == []
    bad = SignupRequest(service_url="", email="not-an-email")
    assert set(bad.missing_required()) == {"service_url", "email"}

    p = check_precondition(ok, actor_connected=True, inbox_ready=True, solver_available=True)
    assert p.ok and p.missing == (), p
    p2 = check_precondition(ok, actor_connected=False, inbox_ready=True, solver_available=False)
    assert not p2.ok and "actor_connected" in p2.missing and "solver" in p2.detail, p2
    print("PASS params+precondition: required params validated; missing prereqs reported")


def test_steps_are_selector_free():
    assert SIGNUP_STEPS[0] is StepKind.NAVIGATE and SIGNUP_STEPS[-1] is StepKind.VERIFY
    assert StepKind.SOLVE_CAPTCHA in SIGNUP_STEPS and StepKind.READ_CODE in SIGNUP_STEPS
    # steps are semantic labels, not selectors
    assert all(isinstance(s.value, str) and " " not in s.value for s in SIGNUP_STEPS)
    print("PASS steps: ordered, semantic, selector-free workflow")


def test_verify_contract():
    signed_in = {"text": "Welcome, you're signed in", "url": "https://svc.test/dashboard"}
    assert verify_signed_up(signed_in) is True
    # "submitted the form" but still on a verification wall -> NOT done
    assert verify_signed_up({"text": "Enter your verification code", "url": "u"}) is False
    # signed-in signal but the account-specific token is required and absent -> NOT done
    assert verify_signed_up(signed_in, expected_tokens=["me@inbox.test"]) is False
    assert verify_signed_up({"text": "Welcome, signed in as me@inbox.test", "url": "u"},
                            expected_tokens=["me@inbox.test"]) is True
    print("PASS verify: signed-in read-back; rejects gated page; honors account receipt")


async def test_confirm_repeated_read():
    stable = [({"text": "dashboard — you are signed in", "url": "u"}, "s")] * 3

    async def read_stable():
        return stable.pop(0)

    async def no_sleep(_s):
        return None

    proof = await confirm_signed_up(read_stable, reads=3, delay_seconds=0.0, sleep=no_sleep)
    assert proof.confirmed and proof.reads == 3, proof

    # a success flash that reverts to a login wall fails closed at the bad read
    flick = [({"text": "you are signed in", "url": "u"}, "a"),
             ({"text": "please sign in to continue", "url": "u"}, "b")]

    async def read_flicker():
        return flick.pop(0)

    proof2 = await confirm_signed_up(read_flicker, reads=2, delay_seconds=0.0, sleep=no_sleep)
    assert not proof2.confirmed, proof2
    print("PASS confirm_signed_up: repeated read-back; a reverting flash is not 'done'")


def test_composed_substeps():
    # captcha sub-step composes the solver; no captcha -> not solved, no crash
    solver = CaptchaSolver(capsolver_key="k", http=lambda *a, **k: type("R", (), {"json": lambda s: {}})(),
                           sleep=lambda *_: None)
    out = handle_captcha_step({"url": "u", "html": "<p>no challenge</p>"}, solver)
    assert out.solved is False

    # email code sub-step reads the latest code for the service from fixtures
    req = SignupRequest(service_url="https://svc.test/signup", email="me@inbox.test")
    emails = [VerificationEmail(from_addr="noreply@svc.test", subject="verify",
                               body="Your code is 909090", internal_ts=10)]
    assert fetch_verification_code(req, emails=emails) == "909090"
    print("PASS substeps: captcha-solve + email-code composition wired to the hands")


def main():
    test_params_and_precondition()
    test_steps_are_selector_free()
    test_verify_contract()
    asyncio.run(test_confirm_repeated_read())
    test_composed_substeps()
    print("ALL SIGNUP-VERIFY TESTS PASSED")


if __name__ == "__main__":
    main()
