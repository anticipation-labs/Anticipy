"""Brief 01, enforcement: no browser agent — including 0.2.3 and older
extensions in the wild — may ever claim a research-lane job. The new
extension excludes the lane itself; the backend hook enforces it for
everyone else via the filter the SERVER applies and a claim-write refusal."""
import re
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# What a 0.2.3 extension in the wild actually polls with (background.js
# before this brief), and what the worker's research pass polls with now.
OLD_EXT_FILTER = 'status="queued" && (owner="abc123" || owner="")'
WORKER_RESEARCH_FILTER = 'status="queued" && lane="research"'


def _hook_source():
    return (ROOT / "backend" / "pb_hooks" / "research_lane.pb.js").read_text()


def _hook_regex(src, name):
    m = re.search(rf"const {name} = /(.+)/;", src)
    assert m, f"{name} not found in research_lane.pb.js"
    return re.compile(m.group(1))


def test_new_extension_claim_filter_excludes_the_lane():
    src = (ROOT / "extension" / "background.js").read_text()
    m = re.search(r"const cond = `([^`]+)`", src)
    assert m, "claim filter not found in background.js"
    assert 'lane!="research"' in m.group(1)
    assert 'status="queued"' in m.group(1)


def test_hook_rewrite_catches_the_old_extensions_poll():
    src = _hook_source()
    queued = _hook_regex(src, "QUEUED_POLL")
    lane = _hook_regex(src, "MENTIONS_LANE")
    # A 0.2.3 poll: queued, no lane clause -> the server appends one.
    assert queued.search(OLD_EXT_FILTER)
    assert not lane.search(OLD_EXT_FILTER)
    # The appended clause parenthesizes the original, so `A || B` cannot be
    # re-associated by &&'s tighter binding.
    assert '"(" + filter + ")' in src


def test_hook_rewrite_leaves_lane_aware_polls_alone():
    src = _hook_source()
    queued = _hook_regex(src, "QUEUED_POLL")
    lane = _hook_regex(src, "MENTIONS_LANE")
    # The worker's own research poll names the lane -> never rewritten.
    assert queued.search(WORKER_RESEARCH_FILTER)
    assert lane.search(WORKER_RESEARCH_FILTER)
    # So does the 0.2.4 extension's poll.
    new_ext = OLD_EXT_FILTER + ' && lane!="research"'
    assert lane.search(new_ext)


def test_hook_refuses_a_browser_claim_outright():
    src = _hook_source()
    # Layer 2: a claim-shaped PATCH (claimed_by / status running) on a
    # research job is 403'd unless it is the worker's.
    assert '"claimed_by" in b' in src
    assert 'b["status"] === "running"' in src
    assert "403" in src
    assert "X-Anticipy-Worker" in src
    assert 'WORKER_CLAIMANT = "worker-research"' in src


def test_worker_requests_carry_the_worker_marker(monkeypatch):
    monkeypatch.delenv("ANTICIPY_SERVICE_TOKEN", raising=False)
    import brain.pb as pb
    assert pb.headers().get("X-Anticipy-Worker") == "1"
    monkeypatch.setenv("ANTICIPY_SERVICE_TOKEN", "tok")
    h = pb.headers()
    assert h["X-Anticipy-Worker"] == "1" and h["X-Anticipy-Token"] == "tok"


def test_worker_claimant_names_agree():
    import brain.worker as W
    src = _hook_source()
    assert f'"{W.RESEARCH_CLAIMANT}"' in src, \
        "the hook and the worker disagree on the claimant name"


# ---- the SMS channel marker degrades gracefully across core versions ------

def _convo(core):
    from brain.conversation import Conversation
    return Conversation(core)


class _Base:
    llm = None
    memory = types.SimpleNamespace(recall=lambda *a, **k: [])

    @staticmethod
    def _out():
        return {"decision": types.SimpleNamespace(decision="act"),
                "anticipy_says": "on it"}


def test_think_marks_the_sms_channel():
    calls = {}

    class A(_Base):
        def hear(self, text, may_say=None, explicit=False, channel=""):
            calls.update(channel=channel, explicit=explicit)
            return self._out()

    assert _convo(A())._think("what's the weather") == "on it"
    assert calls["channel"] == "sms"
    assert calls["explicit"] is True


def test_think_survives_a_core_without_channel():
    calls = {}

    class A(_Base):
        def hear(self, text, may_say=None, explicit=False):
            calls.update(explicit=explicit)
            return self._out()

    assert _convo(A())._think("what's the weather") == "on it"
    assert calls["explicit"] is True


def test_think_survives_the_oldest_core():
    class A(_Base):
        def hear(self, text):
            return self._out()

    assert _convo(A())._think("what's the weather") == "on it"
