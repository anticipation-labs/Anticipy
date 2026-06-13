"""Slice 0: the read-back completion gate.

A live external WRITE is done ONLY after a SECOND, independent read re-observes the
written artifact. The write call's own echo is never proof. This test FAILS if anyone
reverts ApiHand to self-attestation, or weakens orchestrator._verify to accept a
self-reported proof.

No real network: all logic runs against an injected FakeArcade whose execute() models
both legs (write + independent read-back). The genuine live end-to-end proof is
deferred to Slice 1 (one real day).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_api_readback.py
"""
import asyncio
from types import SimpleNamespace

from anticipy_engine.core.envelopes import Job, JobStatus, Result, Risk
from anticipy_engine.core.orchestrator import Orchestrator
from anticipy_engine.hands.api_hand import ApiHand, MODE_LIVE, MODE_MOCK, READ_BACK


# A FakeArcade whose execute() distinguishes the WRITE tool from the independent READ
# tool: it returns the created id only on the read AFTER the write happened, and can be
# told to "lose" the artifact (read returns empty) to prove fail-closed behavior.
class FakeTools:
    def __init__(self, fake):
        self.f = fake

    def authorize(self, tool_name, user_id):
        return SimpleNamespace(status="completed", url="https://connect.example/grant")

    def execute(self, tool_name, input, user_id):
        self.f.calls.append(tool_name)
        if tool_name == self.f.write_tool:
            self.f.wrote = True
            return SimpleNamespace(output=SimpleNamespace(value={"id": self.f.written_id}, error=None))
        if tool_name == self.f.read_tool:
            # independent read-back: the artifact is visible only if it was written AND
            # the scenario allows the read to find it.
            if self.f.wrote and self.f.read_finds_id:
                items = [{"id": self.f.written_id, "summary": "Lunch", "start": "2026-06-14T12:00"}]
            else:
                items = []
            return SimpleNamespace(id="readback-req-7",
                                   output=SimpleNamespace(value={"events": items}, error=None))
        raise AssertionError(f"unexpected tool: {tool_name}")


class FakeArcade:
    def __init__(self, write_tool, read_tool, written_id="evt-777"):
        self.tools = FakeTools(self)
        self.write_tool = write_tool
        self.read_tool = read_tool
        self.written_id = written_id
        self.read_finds_id = True
        self.wrote = False
        self.calls = []


def ev_job():
    return Job(intent="create_event", risk=Risk.low, goal_id="g1", args={
        "title": "Lunch", "start_datetime": "2026-06-14T12:00", "end_datetime": "2026-06-14T13:00"})


async def main():
    # (1) live create_event where the read-back RE-OBSERVES the id -> success, proof is
    # read-backed and explicitly NOT self-attested.
    fake = FakeArcade("GoogleCalendar.CreateEvent", READ_BACK["create_event"])
    hand = ApiHand(user_id="omar@anticipy.ai", client=fake, mode=MODE_LIVE)
    r = await hand.handle(ev_job())
    assert r.status == JobStatus.success, r
    assert r.proof["id"] == "evt-777"
    assert r.proof["readback"] is True and r.proof["self_attested"] is False
    assert r.proof["verified_by_read"] == "GoogleCalendar.ListEvents"
    assert r.proof["read_request_id"] == "readback-req-7"  # distinct read req, audited
    assert fake.write_tool in fake.calls and fake.read_tool in fake.calls
    assert fake.calls.count(fake.write_tool) == 1, "exactly one write"
    assert fake.calls.count(fake.read_tool) >= 1, "at least one independent read-back"

    # (2) FAIL-CLOSED: live write succeeds at the API, but the independent read-back
    # does NOT contain the id -> status=failed, proof=None. (Reverting to self-attestation
    # would make this success and FAIL the test.)
    fake2 = FakeArcade("GoogleCalendar.CreateEvent", READ_BACK["create_event"])
    fake2.read_finds_id = False
    hand2 = ApiHand(user_id="u", client=fake2, mode=MODE_LIVE)
    r = await hand2.handle(ev_job())
    assert r.status == JobStatus.failed and r.proof is None, r
    assert fake2.wrote is True, "the write DID fire; only the read-back failed"
    assert fake2.read_tool in fake2.calls, "the second independent read WAS attempted"

    # (3) Unverified read tool (send_email_draft has no wired read-back yet) -> the live
    # path CANNOT confirm -> needs_human, NEVER success on the write echo alone.
    assert READ_BACK["send_email_draft"] is None, "drafts read tool intentionally TODO"

    class DraftFake:
        def __init__(self):
            self.tools = SimpleNamespace(
                authorize=lambda tool_name, user_id: SimpleNamespace(status="completed", url=None),
                execute=lambda tool_name, input, user_id: SimpleNamespace(
                    output=SimpleNamespace(value={"draft_id": "draft-1"}, error=None)))
    hand3 = ApiHand(user_id="u", client=DraftFake(), mode=MODE_LIVE)
    r = await hand3.handle(Job(intent="send_email_draft", risk=Risk.low, goal_id="g1",
                               args={"recipient": "t@x.com", "subject": "hi", "body": "yo"}))
    assert r.status == JobStatus.needs_human and r.proof is None, r
    assert r.output.get("unverified_write") is True

    # (4) orchestrator._verify rejects a self-attested-only proof, and accepts a
    # read-backed one. This is the central gate; it must not be silently weakened.
    assert Orchestrator._verify(Result(job_id="x", status=JobStatus.success,
                                       proof={"id": "z", "self_attested": True})) is False
    assert Orchestrator._verify(Result(job_id="x", status=JobStatus.success,
                                       proof={"id": "z", "self_attested": True,
                                              "verified_by_read": "Gmail.ListEmails"})) is True
    # legitimate non-API proof shapes still pass (no self_attested marker)
    assert Orchestrator._verify(Result(job_id="x", status=JobStatus.success,
                                       proof={"memory_id": "m1", "kind": "history"})) is True
    assert Orchestrator._verify(Result(job_id="x", status=JobStatus.success,
                                       proof={"id": "mock-1", "mock": True, "tool": "Gmail.SendEmail"})) is True
    # no proof -> not done
    assert Orchestrator._verify(Result(job_id="x", status=JobStatus.success, proof=None)) is False

    # (5) MOCK write exercises the SAME read-back code and tags readback:true.
    mh = ApiHand(user_id="u", mode=MODE_MOCK)
    r = await mh.handle(Job(intent="create_event", risk=Risk.low, goal_id="g1",
                            args={"title": "x", "start_datetime": "2026-06-14T12:00"}))
    assert r.status == JobStatus.success and r.proof["mock"] is True
    assert r.proof.get("readback") is True and r.proof.get("self_attested") is False

    # (6) FAIL-CLOSED in mock: if the simulated read-back loses the artifact, the mock
    # write is NOT done either. This proves the same gate guards mock and live.
    class BlindMockHand(ApiHand):
        async def _mock_read_once(self, written_id):
            return {"events": []}, "mock-read-empty"  # artifact not found
    bm = BlindMockHand(user_id="u", mode=MODE_MOCK)
    r = await bm.handle(Job(intent="create_event", risk=Risk.low, goal_id="g1",
                            args={"title": "x", "start_datetime": "2026-06-14T12:00"}))
    assert r.status == JobStatus.failed and r.proof is None, r

    print("PASS read-back gate: live write requires a SECOND independent read; "
          "fail-closed when the artifact is not re-observed; _verify rejects self-attested-only.")


if __name__ == "__main__":
    asyncio.run(main())
