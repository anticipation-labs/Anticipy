"""Phase V4-5 HARD GATE: the runner completes the easiest possible
real task from a blank tab with zero setup.

If this fails, the architecture is wrong. Per the master prompt: do
not proceed to V4-6, email Omar via Aevoy with the trajectory dump.

Task: "Find what year the Python programming language was first
released. Report the year." Assertions: SUCCESS, "1991" in the
answer or evidence, iterations under 15, wall time under 3 minutes.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.action_engine.dsv4_skill_runner import DSv4SkillRunner  # noqa: E402

TASK = ("Find what year the Python programming language was first "
        "released. Report the year.")


def _reset_chrome_to_blank():
    """Close every page tab and open one fresh about:blank so the run
    starts with zero context (matches the prompt's clean-state rule)."""
    try:
        targets = json.load(urllib.request.urlopen(
            "http://localhost:9222/json/list", timeout=6))
    except Exception as e:
        pytest.skip(f"Chrome :9222 not reachable: {e}")
    pages = [t for t in targets if t.get("type") == "page"]
    # Open a fresh blank tab first so the window never has zero tabs.
    # Chrome 111+ requires PUT (not GET) on /json/new.
    _put = urllib.request.Request(
        "http://localhost:9222/json/new?about:blank", method="PUT")
    urllib.request.urlopen(_put, timeout=6).read()
    for t in pages:
        try:
            urllib.request.urlopen(
                f"http://localhost:9222/json/close/{t['id']}", timeout=5).read()
        except Exception:
            pass
    time.sleep(1.5)


@pytest.mark.timeout(300)
def test_v4_5_wikipedia_smoke():
    _reset_chrome_to_blank()
    runner = DSv4SkillRunner(max_iters=14)
    t0 = time.monotonic()
    result = runner.run(TASK)
    wall = time.monotonic() - t0

    blob = f"{result.answer} {result.evidence}".lower()
    print(json.dumps({
        "status": result.status,
        "answer": result.answer,
        "evidence": result.evidence,
        "n_iterations": result.n_iterations,
        "wall_s": round(wall, 1),
        "trajectory_dir": result.trajectory_dir,
    }, indent=2))

    assert result.status == "SUCCESS", (
        f"status {result.status}, error {result.error}, "
        f"trajectory {result.trajectory_dir}")
    assert "1991" in blob, f"expected 1991, got answer={result.answer!r} evidence={result.evidence!r}"
    assert result.n_iterations < 15, f"too many iters: {result.n_iterations}"
    assert wall < 180, f"too slow: {wall:.0f}s"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "-s", "--timeout=300"]))
