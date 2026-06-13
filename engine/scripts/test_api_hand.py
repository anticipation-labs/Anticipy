"""Piece 1 test: the API hand — all logic against an injected FakeArcade (no network).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_api_hand.py
"""
import asyncio
import os
from types import SimpleNamespace

from anticipy_engine.core.envelopes import Job, JobStatus, Risk
from anticipy_engine.hands.api_hand import ApiHand, NotFundedError, MODE_LIVE, MODE_MOCK


class FakeErr(Exception):
    def __init__(self, code):
        self.status_code = code
        super().__init__(f"http {code}")


# Read-back tools the live write path now calls as its SECOND independent execute().
READ_TOOLS = {"Gmail.ListEmails", "GoogleCalendar.ListEvents", "Gmail.ListThreads",
              "GoogleDocs.GetDocumentById"}


class FakeTools:
    def __init__(self, fake):
        self.f = fake

    def authorize(self, tool_name, user_id):
        return SimpleNamespace(status=self.f.auth_status, url=self.f.auth_url)

    def execute(self, tool_name, input, user_id):
        # The live write path calls execute TWICE: once to WRITE, then a SECOND,
        # independent READ to confirm the artifact. The double models both legs.
        is_read = tool_name in READ_TOOLS
        if not is_read and self.f.exec_behavior.startswith("raise"):
            raise FakeErr(int(self.f.exec_behavior[5:]))
        self.f.executed.append((tool_name, input, user_id))
        if is_read:
            # the independent read-back leg: returns a list-shaped store. By default it
            # RE-OBSERVES the just-written id; readback_finds_id=False simulates a write
            # that never landed (fail-closed). id=request-distinct for the audit trail.
            if self.f.readback_finds_id:
                value = {"events": [self.f.exec_value]}
            else:
                value = {"events": []}
            return SimpleNamespace(id="read-req-1",
                                   output=SimpleNamespace(value=value, error=None))
        # the WRITE leg
        if self.f.exec_behavior == "empty":
            return SimpleNamespace(output=SimpleNamespace(value=None, error=None))
        return SimpleNamespace(output=SimpleNamespace(value=self.f.exec_value, error=None))


class FakeArcade:
    def __init__(self):
        self.tools = FakeTools(self)
        self.auth_status = "completed"
        self.auth_url = "https://connect.example/grant"
        self.exec_behavior = "success"   # success|empty|raise401|raise403|raise429|raise500
        self.exec_value = {"id": "msg-123"}
        self.readback_finds_id = True    # independent read re-observes the written id
        self.executed = []


def job(intent, **args):
    return Job(intent=intent, args=args, goal_id="g1")


async def main():
    # LIVE success: the write is confirmed by a SECOND, independent read-back (not the
    # write echo). Proof carries readback evidence and is explicitly NOT self-attested.
    fake = FakeArcade()
    hand = ApiHand(user_id="omar@anticipy.ai", client=fake, mode=MODE_LIVE)
    r = await hand.handle(job("send_email", approved=True, recipient="t@x.com", subject="hi", body="yo"))
    assert r.status == JobStatus.success and r.proof["id"] == "msg-123", r
    assert r.proof.get("readback") is True and r.proof.get("self_attested") is False
    assert r.proof.get("verified_by_read") == "Gmail.ListEmails"
    assert r.proof.get("read_request_id") == "read-req-1"  # distinct read req id, audited
    # the live write path executed TWICE: the write, then >=1 independent read-back
    write_calls = [c for c in fake.executed if c[0] == "Gmail.SendEmail"]
    read_calls = [c for c in fake.executed if c[0] == "Gmail.ListEmails"]
    assert len(write_calls) == 1 and len(read_calls) >= 1, fake.executed

    # idempotency: a retry of the same write does NOT execute again (no new write, no new read)
    before = len(fake.executed)
    r2 = await hand.handle(job("send_email", approved=True, recipient="t@x.com", subject="hi", body="yo"))
    assert r2.status == JobStatus.success and r2.output.get("idempotent") is True
    assert len(fake.executed) == before, "must not re-send (or re-read) on retry"

    # defense in depth: HIGH-RISK write without approval flag -> needs_human, never executes
    fake2 = FakeArcade()
    hand2 = ApiHand(user_id="u", client=fake2, mode=MODE_LIVE)
    r = await hand2.handle(Job(intent="send_email", args={"recipient": "t@x.com"},
                               risk=Risk.needs_confirm, goal_id="g1"))
    assert r.status == JobStatus.needs_human and not fake2.executed

    # auth needed -> needs_human + connect URL; never the word "API" in the user surface
    fake3 = FakeArcade(); fake3.auth_status = "pending"
    hand3 = ApiHand(user_id="u", client=fake3, mode=MODE_LIVE)
    r = await hand3.handle(job("send_email", approved=True))
    assert r.status == JobStatus.needs_human and r.output["connect"] == "Gmail"
    assert "API" not in r.output["connect"]

    # empty/invalid proof -> failure, not success
    fake4 = FakeArcade(); fake4.exec_behavior = "empty"
    hand4 = ApiHand(user_id="u", client=fake4, mode=MODE_LIVE)
    r = await hand4.handle(job("send_email", approved=True))
    assert r.status == JobStatus.failed and r.proof is None

    # 401 -> loud NOT-FUNDED (raises)
    fake5 = FakeArcade(); fake5.exec_behavior = "raise401"
    hand5 = ApiHand(user_id="u", client=fake5, mode=MODE_LIVE)
    raised = False
    try:
        await hand5.handle(job("send_email", approved=True))
    except NotFundedError:
        raised = True
    assert raised, "401 must raise NotFundedError"

    # 403 -> re-authorize (needs_human + connect)
    fake6 = FakeArcade(); fake6.exec_behavior = "raise403"
    hand6 = ApiHand(user_id="u", client=fake6, mode=MODE_LIVE)
    r = await hand6.handle(job("send_email", approved=True))
    assert r.status == JobStatus.needs_human and r.output.get("connect") == "Gmail"

    # 429 -> rate limited, retryable failure
    fake7 = FakeArcade(); fake7.exec_behavior = "raise429"
    hand7 = ApiHand(user_id="u", client=fake7, mode=MODE_LIVE)
    r = await hand7.handle(job("send_email", approved=True))
    assert r.status == JobStatus.failed and "rate limited" in r.error

    # 500 -> transient, retryable failure
    fake8 = FakeArcade(); fake8.exec_behavior = "raise500"
    hand8 = ApiHand(user_id="u", client=fake8, mode=MODE_LIVE)
    r = await hand8.handle(job("send_email", approved=True))
    assert r.status == JobStatus.failed and "transient" in r.error

    # no Arcade tool for the intent -> route to the browser hand (marker), not a hard fail
    r = await hand.handle(job("frobnicate", approved=True))
    assert r.status == JobStatus.failed and r.output.get("needs_other_worker") is True

    # read intent in MOCK mode -> success with mock proof, no client needed
    rh = ApiHand(user_id="u", mode=MODE_MOCK)
    r = await rh.handle(job("read_email"))
    assert r.status == JobStatus.success and r.proof.get("mock") is True

    # missing key in LIVE -> loud NOT-FUNDED
    saved = os.environ.pop("ARCADE_API_KEY", None)
    try:
        nokey = ApiHand(user_id="u", mode=MODE_LIVE)  # client=None -> builds from env
        raised = False
        try:
            await nokey.handle(job("read_email"))
        except NotFundedError:
            raised = True
        assert raised, "missing ARCADE_API_KEY must raise NotFundedError"
    finally:
        if saved is not None:
            os.environ["ARCADE_API_KEY"] = saved

    print("PASS piece 1: API hand (authorize/execute, idempotency, proof validation, error matrix, routing)")
    print("  send proof id=msg-123 | executes after one retry =", len(fake.executed), "(idempotent)")


if __name__ == "__main__":
    asyncio.run(main())
