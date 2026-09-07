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
    return (ROOT / "migration" / "workers" / "src" / "policy" / "research_lane.ts").read_text()


def _hook_regex(src, name):
    m = re.search(rf"const {name} = /(.+)/;", src)
    assert m, f"{name} not found in research_lane.ts"
    return re.compile(m.group(1))


def test_new_extension_claim_filter_excludes_the_lane():
    src = (ROOT / "extension" / "background.js").read_text()
    # ONE definition, and both callers named against it. This used to grep for
    # the first `const cond = \`…\`` in the file, which is a promise about
    # variable names rather than about lanes: the claim filter moved behind a
    # shared builder and the regex silently locked on to the research-lane
    # DIAGNOSIS query further down, asserting the exact opposite of the
    # invariant. The invariant is that the claim poll and the stale sweep
    # exclude the same lane, so assert that.
    lane = re.search(r"const BROWSER_LANE = '([^']+)'", src)
    assert lane, "background.js must define the browser's lanes exactly once"
    assert 'lane!="research"' in lane.group(1)
    assert 'workflow_id!=""' in lane.group(1)

    built = re.search(r"const ownerLaneFilter = \([^)]*\) =>\s*`([^`]+)`", src)
    assert built, "the shared filter builder must be one template literal"
    assert 'status="${status}"' in built.group(1)
    assert 'owner_ref="${ownerRef}"' in built.group(1)
    assert "${BROWSER_LANE}" in built.group(1)

    # The claim and the sweep, each exactly once, through that one builder.
    assert src.count('ownerLaneFilter("queued"') == 1
    assert src.count('ownerLaneFilter("running"') == 1


def test_hook_rewrite_catches_the_old_extensions_poll():
    src = _hook_source()
    queued = _hook_regex(src, "QUEUED_POLL")
    # A 0.2.3 poll: queued, no lane clause -> the server appends one.
    assert queued.search(OLD_EXT_FILTER)
    # The Worker parses the filter into an AST and ANDs the exclusion onto it
    # (filter-dsl.ts `andNot`), which is what makes `A || B` impossible to
    # re-associate — the hook did the same with parentheses around a string.
    assert "andNot" in src and "mentionsField" in src
    assert "EXCLUDED_LANES" in src


def test_hook_rewrite_leaves_lane_aware_polls_alone():
    src = _hook_source()
    queued = _hook_regex(src, "QUEUED_POLL")
    # The worker's own research poll names the lane and comes from the worker
    # (`fromWorker`), so it is never rewritten; the rewrite is gated on both.
    assert queued.search(WORKER_RESEARCH_FILTER)
    assert "!ctx.worker.fromWorker" in src
    assert 'mentionsField(ast, "lane")' in src or "mentionsField(" in src


def test_hook_refuses_a_browser_claim_outright():
    src = _hook_source()
    # Layer 2: a claim-shaped PATCH (claimed_by / status running) on a
    # research job is 403'd unless it is the worker's.
    assert '"claimed_by" in b' in src
    assert 'b.status === "running"' in src
    assert "403" in src
    assert "research jobs run in the worker, never in a browser" in src
    assert 'WORKER_CLAIMANT = "worker-research"' in src


def test_worker_requests_carry_the_worker_marker(monkeypatch):
    monkeypatch.delenv("ANTICIPY_SERVICE_TOKEN", raising=False)
    from brain import backend
    assert backend.headers().get("X-Anticipy-Worker") == "1"
    monkeypatch.setenv("ANTICIPY_SERVICE_TOKEN", "tok")
    h = backend.headers()
    assert h["X-Anticipy-Worker"] == "1" and h["X-Anticipy-Token"] == "tok"


def test_worker_claimant_names_agree():
    import brain.worker as W
    src = _hook_source()
    assert f'"{W.RESEARCH_CLAIMANT}"' in src, \
        "the Worker's lane policy and the brain disagree on the claimant name"


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


def test_think_carries_recent_sms_context_into_the_brain():
    from brain.conversation import Turn
    calls = {}

    class A(_Base):
        def hear(self, text, context=None, may_say=None, explicit=False, channel=""):
            calls.update(context=context, channel=channel, explicit=explicit)
            return self._out()

    convo = _convo(A())
    convo.threads["+1"] = [
        Turn("owner", "I need a flight to Paris tomorrow"),
        Turn("anticipy", "what time do you want to land in paris"),
        Turn("owner", "Anytime"),
        Turn("owner", "give me five options"),
    ]
    assert convo._think("give me five options", "+1") == "on it"
    assert calls["context"] == [
        "owner: I need a flight to Paris tomorrow",
        "anticipy: what time do you want to land in paris",
        "owner: Anytime",
    ]


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
