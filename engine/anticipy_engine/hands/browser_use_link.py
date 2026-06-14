"""3.10-SAFE engine client for the open-source browser arm.

Slice 6 step 3. This module MUST import cleanly under Python 3.10 (the engine):
it NEVER imports `browser_use` at the top level (or anywhere). It only shells
out to the bridge runner (browser_use_runner.py), which is executed by the
durable 3.11 bridge venv. The engine and the bridge never share an interpreter.

Flow:
  engine (3.10)  --JSON task on stdin-->  [3.11 bridge python] browser_use_runner
  engine (3.10)  <--JSON result line---   browser-use + OUR OpenRouter model

Trust model (Slice-0 read-back insight applied):
  browser-use's final_result is a model-summarized read of a live page — useful,
  but the actor grading its own homework. So:
    - we NEVER claim success the runner didn't report (success mirrors the
      runner's honest is_done+result flag).
    - we mark FINE-GRAINED extracted facts (structured / JSON pulls of specific
      fields) as low-trust `needs_cross_check=True`: a second independent read
      should confirm them before they're treated as ground truth.
    - COARSE facts (the whole-page summary read) are higher trust but still not
      a write-receipt; they're a read proof, labeled as such.

Guardrails: READ-ONLY only; the runner appends the read-only guard to the task,
uses browser-use's own throwaway browser, and never the user's Chrome. This
client adds a hard subprocess TIMEOUT so a hung browser can never hang the
engine, and surfaces a clear blocker instead of faking a success.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Sentinel the runner tags its single result line with (kept in sync by value,
# NOT by importing the runner — importing it would risk pulling browser_use).
_RESULT_SENTINEL = "__ANTICIPY_BU_RESULT__"

_REPO_ROOT = Path(__file__).resolve().parents[3]
# Durable, gitignored 3.11 bridge venv python (default). Overridable via env.
_DEFAULT_BRIDGE_PY = str(_REPO_ROOT / "engine" / ".bu-venv" / "bin" / "python")
_RUNNER_PATH = str(Path(__file__).resolve().parent / "browser_use_runner.py")

# Generous default: a real browser read of a public page typically finishes well
# under this, but cold Chromium launch + model latency needs headroom.
_DEFAULT_TIMEOUT_S = 240


def bridge_python() -> str:
    """The interpreter that runs the bridge. Env override wins; else the durable
    venv path. We do NOT require it to exist here — `available()` reports that."""
    return os.environ.get("ANTICIPY_BROWSERUSE_PYTHON", _DEFAULT_BRIDGE_PY)


def available() -> Dict[str, Any]:
    """Cheap, import-free readiness probe: does the bridge python + runner exist?
    The engine can call this to decide whether the browser arm is usable at all
    without ever launching a browser."""
    py = bridge_python()
    py_ok = bool(py) and (os.path.exists(py) or shutil.which(py) is not None)
    runner_ok = os.path.exists(_RUNNER_PATH)
    return {
        "ok": py_ok and runner_ok,
        "bridge_python": py,
        "bridge_python_exists": py_ok,
        "runner": _RUNNER_PATH,
        "runner_exists": runner_ok,
    }


@dataclass
class BrowseReadResult:
    """A proof-bearing result from a read-only browser read.

    `success` mirrors the runner's HONEST done+result flag — never invented.
    `needs_cross_check` flags low-trust fine-grained facts (the Slice-0 insight).
    """

    success: bool
    result: Optional[str]
    url: Optional[str]
    steps: int = 0
    structured: bool = False
    needs_cross_check: bool = True
    trust: str = "low"  # "coarse" (whole-page read) | "low" (fine-grained)
    urls: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    elapsed_s: Optional[float] = None
    error: Optional[str] = None
    # The host-scoped navigation wall the runner applied (None = allow-all because
    # no host could be derived). Surfaced so callers can prove off-domain nav is
    # blocked by browser-use's security watchdog.
    allowed_domains: Optional[List[str]] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "result": self.result,
            "url": self.url,
            "steps": self.steps,
            "structured": self.structured,
            "needs_cross_check": self.needs_cross_check,
            "trust": self.trust,
            "urls": self.urls,
            "actions": self.actions,
            "elapsed_s": self.elapsed_s,
            "error": self.error,
            "allowed_domains": self.allowed_domains,
        }


def _parse_runner_output(stdout: str) -> Optional[Dict[str, Any]]:
    """Pull OUR single sentinel-tagged json line out of the runner's stdout,
    ignoring any browser-use log noise around it."""
    payload = None
    for line in stdout.splitlines():
        idx = line.find(_RESULT_SENTINEL)
        if idx != -1:
            frag = line[idx + len(_RESULT_SENTINEL):].strip()
            try:
                payload = json.loads(frag)
            except Exception:
                continue
    return payload


def browse_read(
    task: str,
    *,
    url: Optional[str] = None,
    structured: bool = False,
    max_steps: int = 10,
    timeout_s: int = _DEFAULT_TIMEOUT_S,
) -> BrowseReadResult:
    """Run a READ-ONLY browser read through the open-source arm and return a
    proof-bearing result. Honest by construction: any blocker (missing bridge,
    subprocess failure, timeout, runner error) yields success=False with a clear
    `error`, never a faked success."""
    probe = available()
    if not probe["ok"]:
        missing = []
        if not probe["bridge_python_exists"]:
            missing.append(f"bridge python not found: {probe['bridge_python']}")
        if not probe["runner_exists"]:
            missing.append(f"runner not found: {probe['runner']}")
        return BrowseReadResult(
            success=False,
            result=None,
            url=url,
            structured=structured,
            error="browser bridge unavailable: " + "; ".join(missing),
        )

    req = {
        "task": task,
        "url": url,
        "structured": bool(structured),
        "max_steps": int(max_steps),
    }
    cmd = [probe["bridge_python"], _RUNNER_PATH]
    # Pass through the creds the runner needs; the runner also reads .env.local.
    child_env = dict(os.environ)

    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(req),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=child_env,
        )
    except subprocess.TimeoutExpired:
        return BrowseReadResult(
            success=False,
            result=None,
            url=url,
            structured=structured,
            error=f"browser bridge timed out after {timeout_s}s",
        )
    except Exception as e:
        return BrowseReadResult(
            success=False,
            result=None,
            url=url,
            structured=structured,
            error=f"browser bridge launch failed: {type(e).__name__}: {e}",
        )

    payload = _parse_runner_output(proc.stdout)
    if payload is None:
        tail = (proc.stderr or proc.stdout or "")[-400:]
        return BrowseReadResult(
            success=False,
            result=None,
            url=url,
            structured=structured,
            error=(
                f"no result from bridge (exit {proc.returncode}); "
                f"tail: {tail.strip()}"
            ),
        )

    # NEVER claim more success than the runner reported.
    runner_success = bool(payload.get("success"))
    result_text = payload.get("result")
    # Trust grading: fine-grained (structured field pulls) => low trust, must be
    # cross-checked; coarse whole-page reads => higher trust but still a read,
    # not a write receipt.
    if structured:
        trust = "low"
        needs_cross_check = True
    else:
        trust = "coarse"
        # Even a coarse read is the actor reading the page; a downstream verifier
        # may still want a second look, so we keep cross-check advisory-on for
        # any factual claim, but flag coarse reads as the higher tier.
        needs_cross_check = True

    return BrowseReadResult(
        success=runner_success and bool(result_text),
        result=result_text,
        url=payload.get("url") or url,
        steps=int(payload.get("steps") or 0),
        structured=structured,
        needs_cross_check=needs_cross_check,
        trust=trust,
        urls=list(payload.get("urls") or []),
        actions=list(payload.get("actions") or []),
        elapsed_s=payload.get("elapsed_s"),
        error=payload.get("error"),
        allowed_domains=payload.get("allowed_domains"),
        raw=payload,
    )


if __name__ == "__main__":
    # Tiny CLI for manual probing: `python browser_use_link.py <url> [task...]`
    _url = sys.argv[1] if len(sys.argv) > 1 else "https://news.ycombinator.com"
    _task = (
        " ".join(sys.argv[2:])
        if len(sys.argv) > 2
        else "Report the exact title of the #1 (top) story on the front page."
    )
    res = browse_read(_task, url=_url)
    print(json.dumps(res.as_dict(), indent=2, default=str))
