"""Phase V4-4 unit tests for DSv4SkillRunner. CDP and OpenRouter mocked."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.action_engine import dsv4_skill_runner as M  # noqa: E402
from app.action_engine.dsv4_skill_runner import DSv4SkillRunner, _json_from  # noqa: E402
from app.action_engine.openrouter_client import ORResponse  # noqa: E402
from app.action_engine.vision_verifier import Verdict  # noqa: E402


def _client(*contents):
    c = MagicMock()
    c.chat.side_effect = [ORResponse(content=ct, model="m", latency_s=0.1)
                          for ct in contents]
    return c


def test_json_from_plain():
    assert _json_from('{"a":1}') == {"a": 1}


def test_json_from_embedded():
    assert _json_from('noise {"action":"done"} tail')["action"] == "done"


def test_json_from_garbage():
    assert _json_from("no json here") == {}


def test_decompose_single_task():
    c = _client('{"subtasks":["just one thing"]}')
    r = DSv4SkillRunner(client=c, verifier=MagicMock())
    assert r._decompose("just one thing") == ["just one thing"]


def test_decompose_compound():
    c = _client('{"subtasks":["open sheets","type A1","add header row"]}')
    r = DSv4SkillRunner(client=c, verifier=MagicMock())
    out = r._decompose("open sheets then type A1 then add header row")
    assert len(out) == 3 and out[1] == "type A1"


def test_decompose_falls_back_to_whole_task_on_garbage():
    c = _client("not json")
    r = DSv4SkillRunner(client=c, verifier=MagicMock())
    assert r._decompose("do the thing") == ["do the thing"]


def _ledgered(runner, items, status_seq):
    """Patch the ledger so loop tests focus on dispatch/verify. items:
    fixed ledger. status_seq: list of bool-lists returned in order by
    _ledger_status (last value repeats)."""
    runner._build_ledger = lambda subgoal: items
    calls = {"i": 0}

    def _status(ledger, ptext, ax):
        i = min(calls["i"], len(status_seq) - 1)
        calls["i"] += 1
        return status_seq[i]

    runner._ledger_status = _status
    # Vision auditor is the completion authority; in unit tests stub
    # it to confirm so loop tests focus on dispatch/verify behavior.
    runner._vision_confirm = lambda subgoal, b64: (True, "stub-confirmed")
    return runner


def test_subtask_completes_when_ledger_satisfied():
    # Ledger already satisfied on first check -> immediate SUCCESS.
    c = _client('{"action":"done"}')
    r = DSv4SkillRunner(client=c, verifier=MagicMock())
    _ledgered(r, ["python year is 1991"], [[True]])
    sess = MagicMock()
    with patch.object(M, "capture_screenshot", return_value=b"png"), \
         patch.object(M, "_css_viewport", return_value=(800, 600)), \
         patch.object(M, "_normalize_for_model", return_value=b"png"), \
         patch.object(M, "_ax_tree_and_refs", return_value=("(tree)", {})), \
         patch.object(M, "_page_text", return_value="Python released 1991"):
        out = r._run_subtask(sess, "find python year", Path("/tmp"), 0, {})
    assert out["status"] == "SUCCESS"


def test_subtask_dispatches_then_ledger_satisfied():
    # iter0 ledger pending -> decide click -> CERTIFIED; iter1 ledger done.
    c = MagicMock()
    c.chat.side_effect = [
        ORResponse(content='{"action":"click","target_ref":"@e1"}', model="m", latency_s=0.1),
    ]
    verifier = MagicMock()
    verifier.verify.return_value = Verdict("CERTIFIED", "progress", 0.9)
    r = DSv4SkillRunner(client=c, verifier=verifier)
    _ledgered(r, ["the Go button was pressed"], [[False], [True]])
    sess = MagicMock()
    refmap = {"@e1": {"x": 10, "y": 20, "role": "button", "name": "Go"}}
    with patch.object(M, "capture_screenshot", return_value=b"png"), \
         patch.object(M, "_css_viewport", return_value=(800, 600)), \
         patch.object(M, "_normalize_for_model", return_value=b"png"), \
         patch.object(M, "_ax_tree_and_refs", side_effect=[("@e1 [button] \"Go\"", refmap),
                                                            ("(tree)", {})]), \
         patch.object(M, "_page_text", return_value=""), \
         patch.object(M, "humanlike_click") as click, \
         patch.object(M, "wait_for_settle"):
        out = r._run_subtask(sess, "press go", Path("/tmp"), 0, {})
    assert out["status"] == "SUCCESS"
    click.assert_called_once()


def test_diverged_repeatedly_hard_fails():
    c = MagicMock()
    c.chat.side_effect = lambda *a, **kw: ORResponse(
        content='{"action":"click","target_ref":"@e1"}', model="m", latency_s=0.1)
    verifier = MagicMock()
    verifier.verify.return_value = Verdict("DIVERGED", "nothing changed", 0.9)
    r = DSv4SkillRunner(client=c, verifier=verifier, max_iters=10)
    _ledgered(r, ["x done"], [[False]])
    sess = MagicMock()
    refmap = {"@e1": {"x": 1, "y": 2, "role": "button", "name": "X"}}
    with patch.object(M, "capture_screenshot", return_value=b"png"), \
         patch.object(M, "_css_viewport", return_value=(800, 600)), \
         patch.object(M, "_normalize_for_model", return_value=b"png"), \
         patch.object(M, "_ax_tree_and_refs", return_value=("@e1 [button] \"X\"", refmap)), \
         patch.object(M, "_page_text", return_value=""), \
         patch.object(M, "humanlike_click"), \
         patch.object(M, "wait_for_settle"):
        out = r._run_subtask(sess, "do x", Path("/tmp"), 0, {})
    assert out["status"] == "HARD_FAIL"
    assert "diverged" in out["evidence"].lower()


def test_no_confirmation_gate_on_send():
    # An action targeting a "Send" button dispatches directly, no pause.
    c = MagicMock()
    c.chat.side_effect = [
        ORResponse(content='{"action":"click","target_ref":"@e9"}', model="m", latency_s=0.1),
    ]
    verifier = MagicMock()
    verifier.verify.return_value = Verdict("CERTIFIED", "sent", 0.9)
    r = DSv4SkillRunner(client=c, verifier=verifier)
    _ledgered(r, ["email sent"], [[False], [True]])
    sess = MagicMock()
    refmap = {"@e9": {"x": 5, "y": 5, "role": "button", "name": "Send"}}
    with patch.object(M, "capture_screenshot", return_value=b"png"), \
         patch.object(M, "_css_viewport", return_value=(800, 600)), \
         patch.object(M, "_normalize_for_model", return_value=b"png"), \
         patch.object(M, "_ax_tree_and_refs", side_effect=[("@e9 [button] \"Send\"", refmap),
                                                            ("(t)", {})]), \
         patch.object(M, "_page_text", return_value=""), \
         patch.object(M, "humanlike_click") as click, \
         patch.object(M, "wait_for_settle"):
        out = r._run_subtask(sess, "send the email", Path("/tmp"), 0, {})
    click.assert_called_once()  # Send was clicked with no gate
    assert out["status"] == "SUCCESS"


def test_ledger_false_positive_does_not_fabricate_success():
    """Integrity: ledger says ALL done but the vision auditor says
    NOT done. The runner must NOT return SUCCESS (this is the exact
    fabrication bug found on the empty Sheets canvas)."""
    c = MagicMock()
    c.chat.side_effect = lambda *a, **kw: ORResponse(
        content='{"action":"key","text":"Enter"}', model="m", latency_s=0.1)
    verifier = MagicMock()
    verifier.verify.return_value = Verdict("DIVERGED", "still empty", 0.95)
    r = DSv4SkillRunner(client=c, verifier=verifier, max_iters=10)
    r._build_ledger = lambda subgoal: ["A1 has the title"]
    r._ledger_status = lambda ledger, p, a: [True]      # ledger LIES
    r._vision_confirm = lambda subgoal, b64: (False, "sheet is empty")
    sess = MagicMock()
    with patch.object(M, "capture_screenshot", return_value=b"png"), \
         patch.object(M, "_css_viewport", return_value=(800, 600)), \
         patch.object(M, "_normalize_for_model", return_value=b"png"), \
         patch.object(M, "_ax_tree_and_refs", return_value=("(t)", {})), \
         patch.object(M, "_page_text", return_value="title text"), \
         patch.object(M, "_send_key"), \
         patch.object(M, "wait_for_settle"):
        out = r._run_subtask(sess, "put title in A1", Path("/tmp"), 0, {})
    # Core integrity property: a lying ledger must never yield SUCCESS.
    assert out["status"] != "SUCCESS"
    assert out["status"] == "HARD_FAIL"


def test_vision_confirm_gates_real_success():
    """Ledger done AND vision confirms -> SUCCESS with vision evidence."""
    c = MagicMock()
    c.chat.side_effect = lambda *a, **kw: ORResponse(
        content='{"action":"key","text":"Enter"}', model="m", latency_s=0.1)
    r = DSv4SkillRunner(client=c, verifier=MagicMock())
    r._build_ledger = lambda subgoal: ["done item"]
    r._ledger_status = lambda ledger, p, a: [True]
    r._vision_confirm = lambda subgoal, b64: (True, "title visible in A1")
    sess = MagicMock()
    with patch.object(M, "capture_screenshot", return_value=b"png"), \
         patch.object(M, "_css_viewport", return_value=(800, 600)), \
         patch.object(M, "_normalize_for_model", return_value=b"png"), \
         patch.object(M, "_ax_tree_and_refs", return_value=("(t)", {})), \
         patch.object(M, "_page_text", return_value="x"):
        out = r._run_subtask(sess, "put title", Path("/tmp"), 0, {})
    assert out["status"] == "SUCCESS"
    assert "vision-confirmed" in out["evidence"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
