"""Anticipy the orchestrator: hearing, loops, briefing, confirmation gate."""
import sys
sys.path.insert(0, "/home/ubuntu/anticipy_app")

from brain.anticipy_core import Anticipy, NAME


class NoBackend(Anticipy):
    """Offline Anticipy: job queue is stubbed so tests need no PocketBase."""
    def __init__(self, **kw):
        super().__init__(backend_url="http://127.0.0.1:1", **kw)
        self.queued = []

    def _queue_job(self, goal, params, hold=False, explicit=False):
        self.queued.append((goal, params))
        return f"job{len(self.queued)}"


def test_commitment_becomes_loop_and_waits_for_ok():
    a = NoBackend()
    out = a.hear("I'll send Sarah the pitch deck right after this call.")
    assert out["decision"].decision == "act"
    assert len(a.loops) == 1
    assert a.loops[0].status == "awaiting_ok", "irreversible work must be gated"
    assert "Nothing goes out until you say so" in out["anticipy_says"]


def test_small_talk_is_ignored():
    a = NoBackend()
    out = a.hear("Haha yeah the weather is wild lately.")
    assert out["decision"].decision == "ignore"
    assert a.loops == [] and a.queued == []


def test_briefing_speaks_first_person():
    a = NoBackend()
    a.hear("I'll email Marcus the invoice on Friday.")
    b = a.briefing()
    assert NAME in b or "I'm handling" in b
    assert "invoice" in b


def test_briefing_when_quiet():
    a = NoBackend()
    b = a.briefing()
    assert "live your day" in b.lower()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"PASS {name}")
    print("anticipy: all tests passed")
