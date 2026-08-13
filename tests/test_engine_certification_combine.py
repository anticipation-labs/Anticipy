import json

import pytest

from proof.engine_certification.combine import combine_brain, combine_browser


def _write(path, value):
    path.write_text(json.dumps(value))
    return path


def _case_document():
    return {
        "candidate": {"commit": "abc", "dirty": False, "candidate_sha256": "123"},
        "seed_hex": "cafe",
        "cases": [
            {"id": "story-0001-a", "browser_tasks": [{}, {}]},
            {"id": "story-0002-b", "browser_tasks": []},
        ],
    }


def test_brain_combiner_requires_every_story_exactly_once(tmp_path):
    cases = _case_document()
    cases_path = _write(tmp_path / "cases.json", cases)
    common = {"candidate": cases["candidate"], "seed_hex": "cafe", "complete": True}
    one = _write(tmp_path / "one.json", {**common, "rows": [
        {"n": 1, "id": "story-0001-a", "passed": True}]})
    two = _write(tmp_path / "two.json", {**common, "rows": [
        {"n": 2, "id": "story-0002-b", "passed": True}]})
    summary = combine_brain(cases_path, [two, one], tmp_path / "combined.json")
    assert summary["passed"] == summary["total"] == 2
    assert [row["n"] for row in summary["rows"]] == [1, 2]
    with pytest.raises(ValueError, match="coverage mismatch"):
        combine_brain(cases_path, [one], tmp_path / "incomplete.json")


def test_browser_combiner_requires_every_action_exactly_once(tmp_path):
    cases = _case_document()
    cases_path = _write(tmp_path / "cases.json", cases)
    common = {
        "candidate": cases["candidate"], "seed_hex": "cafe", "complete": True,
        "model": "server-model", "model_transport": "paired-backend-proxy",
    }
    one = _write(tmp_path / "one.json", {**common, "results": [
        {"scenario": "story-0001-a-action-1", "ok": True}]})
    two = _write(tmp_path / "two.json", {**common, "results": [
        {"scenario": "story-0001-a-action-2", "ok": True}]})
    summary = combine_browser(cases_path, [one, two], tmp_path / "combined.json")
    assert summary["passed"] == summary["total"] == 2
    with pytest.raises(ValueError, match="duplicate browser action"):
        combine_browser(cases_path, [one, one, two], tmp_path / "duplicate.json")
