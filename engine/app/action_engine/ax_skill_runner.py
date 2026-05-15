"""Accessibility-tree skill runner. Phase AX-3.

Replacement for the Fara vision-coordinate architecture. Loop:

  1. Snapshot the live page accessibility tree (agent-browser), then
     hard-compact it to <=30 interactive lines so an 8B model does
     not drown in article-body link spam.
  2. Ask Ollama (Qwen3-8B) for ONE action as forced JSON
     {"action","ref","text","key","url","answer"}. format=json plus a
     one-shot example kills the "let me describe this page" chattiness.
  3. Dispatch via agent-browser.
  4. On a `done` action, a SEPARATE Ollama call (different prompt,
     different context) verifies the answer against the page.
  5. Loop until done, stuck, or iteration budget exhausted.

Three hard design rules from the user (2026-05-15):

  - No setup_url crutch. The runner gets a goal and a BLANK tab. The
    agent itself must choose to navigate to a search engine or a
    destination. First action is the model's decision, not ours.

  - The agent operates in a dedicated background Chrome window named
    "Anticipy Agent" (CDP Target.createTarget newWindow+background).
    The user's foreground tabs are never touched. Chrome's colored
    tab-groups need the extension tabGroups API; with a CDP-only
    architecture a dedicated background window is the isolation
    primitive (same user-can-work-in-parallel guarantee).

  - No service APIs. No fabrication. Real artifacts in .anticipy/PROOF.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PROOF_DIR = REPO_ROOT / ".anticipy" / "PROOF" / "ax_v1"
AGENT_STATE = Path(os.path.expanduser("~/.anticipy/ax_agent_target.json"))
AGENT_WINDOW_NAME = "Anticipy Agent"

_logger = logging.getLogger("anticipy.action_engine.ax")

LOCAL_BIN = os.path.expanduser("~/.local/bin")
NPM_BIN = os.path.expanduser("~/.npm-global/bin")
_PATH_FOR_SUB = f"{LOCAL_BIN}:{NPM_BIN}:{os.environ.get('PATH', '')}"

CDP_HOST = "localhost"
CDP_PORT = 9222

CRITICAL_WORDS = (
    "send", "submit", "buy", "purchase", "order", "book", "reserve",
    "confirm", "pay", "delete", "remove", "publish", "post",
)


@dataclass
class AXAction:
    kind: str
    ref: Optional[str] = None
    text: Optional[str] = None
    key: Optional[str] = None
    direction: Optional[str] = None
    pixels: Optional[int] = None
    url: Optional[str] = None
    answer: Optional[str] = None
    raw: str = ""

    def is_terminal(self) -> bool:
        return self.kind == "done"


@dataclass
class AXStep:
    iteration: int
    ax_tree: str
    action: Optional[AXAction]
    dispatch_ok: bool
    dispatch_stderr: str = ""
    verifier_verdict: str = ""
    verifier_reason: str = ""
    latency_decide_s: float = 0.0
    latency_verify_s: float = 0.0
    latency_dispatch_s: float = 0.0


@dataclass
class SkillResult:
    intent_goal: str
    iterations: list[AXStep] = field(default_factory=list)
    final_verdict: str = "UNKNOWN"
    final_answer: str = ""
    final_evidence: str = ""
    error: Optional[str] = None
    proof_dir: Optional[str] = None


# ─── subprocess + CDP helpers ─────────────────────────────────────────


def _run(cmd: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PATH"] = _PATH_FOR_SUB
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def _cdp_http(path: str) -> list | dict:
    with urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}{path}", timeout=6) as r:
        return json.loads(r.read())


def _cdp_browser_ws() -> str:
    return _cdp_http("/json/version")["webSocketDebuggerUrl"]


def _create_agent_window() -> tuple[str, str]:
    """CDP Target.createTarget newWindow+background. Returns
    (targetId, page_ws_url). The window is opened in the background so
    the user's foreground tab keeps focus."""
    from websockets.sync.client import connect
    ws = connect(_cdp_browser_ws(), max_size=8 * 1024 * 1024)
    try:
        ws.send(json.dumps({
            "id": 1,
            "method": "Target.createTarget",
            "params": {"url": "about:blank", "newWindow": True, "background": True},
        }))
        deadline = time.time() + 8
        tid = None
        while time.time() < deadline:
            m = json.loads(ws.recv())
            if m.get("id") == 1:
                tid = m["result"]["targetId"]
                break
        if not tid:
            raise RuntimeError("Target.createTarget returned no targetId")
    finally:
        ws.close()
    ws_url = ""
    for x in _cdp_http("/json/list"):
        if x.get("id") == tid:
            ws_url = x["webSocketDebuggerUrl"]
            break
    if not ws_url:
        raise RuntimeError("agent window target not found in /json/list")
    return tid, ws_url


def ensure_agent_window() -> str:
    """Return the page ws URL of the dedicated Anticipy Agent window,
    creating it on first run. Persists the targetId so subsequent runs
    reuse the same window instead of spawning a new one each time."""
    target_id = None
    if AGENT_STATE.exists():
        try:
            target_id = json.loads(AGENT_STATE.read_text()).get("target_id")
        except Exception:
            target_id = None

    if target_id:
        try:
            for x in _cdp_http("/json/list"):
                if x.get("id") == target_id and x.get("type") == "page":
                    return x["webSocketDebuggerUrl"]
        except Exception:
            pass  # fall through to recreate

    tid, ws_url = _create_agent_window()
    AGENT_STATE.parent.mkdir(parents=True, exist_ok=True)
    AGENT_STATE.write_text(json.dumps({"target_id": tid, "name": AGENT_WINDOW_NAME}))
    return ws_url


def ab_connect_ws(ws_url: str) -> None:
    r = _run(["agent-browser", "connect", ws_url], timeout=45.0)
    if r.returncode != 0:
        raise RuntimeError(f"agent-browser connect failed: {r.stderr}")


def ab_open(url: str) -> None:
    r = _run(["agent-browser", "open", url], timeout=30.0)
    if r.returncode != 0:
        raise RuntimeError(f"agent-browser open failed: {r.stderr}")


def _compact_tree(raw: str, max_lines: int = 30) -> str:
    """3a: interactive elements only, max 30 lines, no article-body
    link spam. A bare `- link [ref=eN]` with no quoted accessible
    name is navigation noise; drop it. Keep buttons, textboxes,
    comboboxes, headings, and labelled links."""
    keep = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        if (s.startswith(("- link [ref", "- generic [ref", "- image [ref",
                          "- cell [ref", "- listitem [ref"))
                and '"' not in s):
            continue
        keep.append(ln.rstrip())
        if len(keep) >= max_lines:
            break
    return "\n".join(keep)


def ab_snapshot() -> str:
    r = _run(["agent-browser", "snapshot", "-i", "-c"], timeout=20.0)
    if r.returncode != 0:
        raise RuntimeError(f"snapshot failed: {r.stderr}")
    return _compact_tree(r.stdout)


def ab_get_text(ref: str) -> str:
    r = _run(["agent-browser", "get", "text", ref], timeout=10.0)
    return r.stdout.strip() if r.returncode == 0 else ""


def ab_page_text(max_chars: int = 1400) -> str:
    """Visible body text. Interactive-only snapshots cannot see static
    answer text (a Google featured snippet, an article paragraph, a
    price). Read/extract goals need this channel or the agent is blind
    to the very thing it must report. Boilerplate nav lines are
    dropped; the informative content is kept."""
    r = _run(["agent-browser", "get", "text", "body"], timeout=12.0)
    if r.returncode != 0:
        return ""
    skip = {
        "skip to main content", "accessibility help", "accessibility feedback",
        "ai mode", "all", "images", "forums", "shopping", "videos", "news",
        "more", "tools", "search results", "sign in", "settings",
    }
    lines = []
    for ln in r.stdout.splitlines():
        s = ln.strip()
        if not s or s.lower() in skip or len(s) <= 1:
            continue
        lines.append(s)
    return "\n".join(lines)[:max_chars]


def ab_url() -> str:
    r = _run(["agent-browser", "get", "url"], timeout=6.0)
    return r.stdout.strip() if r.returncode == 0 else ""


def ab_screenshot(path: Path) -> bool:
    r = _run(["agent-browser", "screenshot", str(path)], timeout=15.0)
    return r.returncode == 0


def ab_dispatch(action: AXAction) -> tuple[bool, str]:
    if action.kind == "click":
        r = _run(["agent-browser", "click", action.ref or ""], timeout=15.0)
    elif action.kind == "fill":
        r = _run(["agent-browser", "fill", action.ref or "", action.text or ""], timeout=15.0)
    elif action.kind == "type":
        r = _run(["agent-browser", "type", action.ref or "", action.text or ""], timeout=15.0)
    elif action.kind == "key":
        r = _run(["agent-browser", "press", action.key or ""], timeout=10.0)
    elif action.kind == "scroll":
        r = _run(["agent-browser", "scroll", action.direction or "down", str(action.pixels or 500)], timeout=10.0)
    elif action.kind == "navigate":
        r = _run(["agent-browser", "open", action.url or ""], timeout=30.0)
    elif action.kind == "wait":
        r = _run(["agent-browser", "wait", str(action.pixels or 1500)], timeout=15.0)
    elif action.kind == "done":
        return (True, "")
    else:
        return (False, f"unknown action kind: {action.kind}")
    return (r.returncode == 0, r.stderr if r.returncode != 0 else "")


def wait_for_settle(timeout_s: float = 4.0, stable_polls: int = 2, poll_interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_s
    last_h = None
    stable = 0
    while time.monotonic() < deadline:
        try:
            t = ab_snapshot()
        except Exception:
            return False
        h = hash(t)
        if h == last_h:
            stable += 1
            if stable >= stable_polls:
                return True
        else:
            stable = 0
            last_h = h
        time.sleep(poll_interval)
    return False


# ─── Ollama: forced-JSON action + separate verifier ───────────────────


# 3c: JSON schema. Ollama's format= accepts a JSON schema dict; the
# model is constrained to emit exactly this shape.
_ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string",
                   "enum": ["click", "fill", "type", "key", "scroll",
                            "navigate", "wait", "done"]},
        "ref": {"type": "string"},
        "text": {"type": "string"},
        "key": {"type": "string"},
        "url": {"type": "string"},
        "direction": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["action"],
}

# 3b: one-shot example baked into the system prompt.
_ACTION_SYSTEM = (
    "You drive a web browser to accomplish a goal. You see ONE page "
    "snapshot at a time. Each interactive element has a ref like "
    "[ref=e7]. Output ONLY JSON matching the schema. No prose.\n\n"
    "Actions:\n"
    "  navigate : go to a URL (use this first if the page is blank)\n"
    "  click    : click an element by ref\n"
    "  fill     : clear+type into an input by ref (needs text)\n"
    "  type     : type into focused/by-ref element (needs text)\n"
    "  key      : press a key like Enter or Tab\n"
    "  scroll   : scroll the page (direction up/down)\n"
    "  done     : the goal is met; put the result in answer\n\n"
    "ONE-SHOT EXAMPLE\n"
    "Goal: Find the title of the top post on Hacker News.\n"
    "Page:\n"
    '- link "Hacker News" [ref=e2]\n'
    '- link "Project Gutenberg keeps getting better" [ref=e11]\n'
    '- link "new" [ref=e3]\n'
    "Correct output:\n"
    '{"action":"done","answer":"The top post is \\"Project Gutenberg keeps getting better\\""}\n\n'
    "Another example, blank page:\n"
    "Goal: Find what year Python was released.\n"
    "Page:\n- (blank)\n"
    "Correct output:\n"
    '{"action":"navigate","url":"https://www.google.com/search?q=what+year+was+python+first+released"}\n'
)

_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["DONE", "NOT_DONE"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
}

_VERIFY_SYSTEM = (
    "You are a strict completion verifier. Given a goal, the proposed "
    "answer, and the current page snapshot, decide if the goal is "
    "genuinely satisfied by what is visible. Output ONLY JSON "
    '{"verdict":"DONE|NOT_DONE","reason":"one sentence"}.'
)


def _ollama_json(model: str, system: str, user: str, schema: dict,
                 max_tokens: int = 256) -> tuple[dict, str, float]:
    """One forced-JSON Ollama call. think=False keeps Qwen3 from
    spending the whole budget on a CoT block. Returns (parsed, raw, lat)."""
    import ollama
    t0 = time.monotonic()
    resp = ollama.generate(
        model=model,
        prompt=f"{system}\n\n{user}",
        think=False,
        format=schema,
        options={"temperature": 0.0, "num_predict": max_tokens},
    )
    lat = time.monotonic() - t0
    raw = (resp.get("response", "") or "").strip()
    if not raw:
        raw = (resp.get("thinking", "") or "").strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        parsed = {}
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = {}
    return parsed, raw, lat


def _decide_action(model: str, goal: str, tree: str, page_text: str,
                   history: list[AXStep]) -> tuple[AXAction, float, str]:
    hist = ""
    for s in history[-3:]:
        if s.action:
            hist += f"  did: {s.action.kind} {s.action.ref or s.action.url or s.action.text or ''}\n"
    user = (
        f"GOAL: {goal}\n\n"
        f"RECENT (do not repeat a failed action):\n{hist or '  (nothing yet)'}\n\n"
        f"VISIBLE PAGE TEXT (read this for answers):\n{page_text or '(empty)'}\n\n"
        f"INTERACTIVE ELEMENTS:\n{tree or '- (blank)'}\n\n"
        "If the VISIBLE PAGE TEXT already answers the goal, output "
        '{\"action\":\"done\",\"answer\":\"...\"}. Otherwise output the '
        "JSON for the single next action."
    )
    parsed, raw, lat = _ollama_json(model, _ACTION_SYSTEM, user, _ACTION_SCHEMA, max_tokens=200)
    kind = (parsed.get("action") or "").strip().lower()
    if kind not in ("click", "fill", "type", "key", "scroll", "navigate", "wait", "done"):
        return AXAction(kind="unknown", raw=raw), lat, raw
    ref = parsed.get("ref") or None
    if ref and not str(ref).startswith("@"):
        ref = "@" + str(ref).lstrip("@")
    act = AXAction(
        kind=kind,
        ref=ref,
        text=parsed.get("text") or None,
        key=parsed.get("key") or None,
        direction=parsed.get("direction") or None,
        url=parsed.get("url") or None,
        answer=parsed.get("answer") or None,
        raw=raw,
    )
    return act, lat, raw


def _verify_done(model: str, goal: str, proposed_answer: str, page_text: str) -> tuple[str, str, float]:
    user = (
        f"GOAL: {goal}\n"
        f"PROPOSED ANSWER: {proposed_answer}\n\n"
        f"VISIBLE PAGE TEXT:\n{page_text or '(empty)'}\n\n"
        "Does the visible page text support the proposed answer for "
        "this goal? JSON only."
    )
    parsed, raw, lat = _ollama_json(model, _VERIFY_SYSTEM, user, _VERIFY_SCHEMA, max_tokens=120)
    verdict = (parsed.get("verdict") or "NOT_DONE").upper()
    reason = parsed.get("reason") or raw[:120]
    if verdict not in ("DONE", "NOT_DONE"):
        verdict = "NOT_DONE"
    return verdict, reason, lat


def _is_critical(action: AXAction) -> bool:
    if not action.ref:
        return False
    label = ab_get_text(action.ref).lower()
    return any(w in label for w in CRITICAL_WORDS)


# ─── Runner ───────────────────────────────────────────────────────────


@dataclass
class AXSkillRunner:
    model: str = "qwen3:8b"
    max_iters: int = 20
    requires_user_confirm: bool = False
    confirm_callback: Optional[Callable[[AXAction, str], bool]] = None

    def _proof_dir(self, skill_id: str) -> Path:
        d = PROOF_DIR / skill_id / f"run_{int(time.time())}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def run(self, goal: str, skill_id: str = "adhoc") -> SkillResult:
        """Run from a BLANK agent-window tab. No setup_url. The agent
        decides its own first navigation."""
        result = SkillResult(intent_goal=goal)
        proof_dir = self._proof_dir(skill_id)
        result.proof_dir = str(proof_dir.relative_to(REPO_ROOT))

        try:
            ws_url = ensure_agent_window()
            ab_connect_ws(ws_url)
            # Reset the agent tab to blank so each run starts clean and
            # the model must choose its own first navigation.
            ab_open("about:blank")

            stuck = 0
            last_sig = None
            for it in range(self.max_iters):
                try:
                    tree = ab_snapshot()
                except Exception as e:
                    result.iterations.append(AXStep(it, "", None, False, f"snapshot threw: {e}"))
                    result.final_verdict = "ERROR"
                    result.error = str(e)
                    break
                page_text = ab_page_text()
                ab_screenshot(proof_dir / f"step_{it:02d}.png")

                action, dlat, raw = _decide_action(self.model, goal, tree, page_text, result.iterations)

                # Loop detection: identical action signature twice in a
                # row means the agent is spinning on a dead end.
                sig = (action.kind, action.ref, action.url, action.text)
                if sig == last_sig and action.kind not in ("done",):
                    stuck += 1
                    if stuck >= 2:
                        result.iterations.append(AXStep(it, tree[:300], action, False,
                                                        f"repeat-action loop on {sig}",
                                                        latency_decide_s=dlat))
                        result.final_verdict = "STUCK"
                        result.final_evidence = f"looped on {action.kind} {action.ref or action.url}"
                        break
                last_sig = sig

                if action.kind == "unknown":
                    result.iterations.append(AXStep(it, tree[:300], action, False,
                                                    f"unparseable: {raw[:120]!r}",
                                                    latency_decide_s=dlat))
                    stuck += 1
                    if stuck >= 3:
                        result.final_verdict = "STUCK"
                        break
                    continue

                if action.kind == "done":
                    # Separate verifier call (different prompt+context).
                    vv, vr, vlat = _verify_done(self.model, goal, action.answer or "", page_text)
                    result.iterations.append(AXStep(it, tree[:300], action, True,
                                                    verifier_verdict=vv, verifier_reason=vr,
                                                    latency_decide_s=dlat, latency_verify_s=vlat))
                    if vv == "DONE":
                        result.final_verdict = "DONE"
                        result.final_answer = action.answer or ""
                        result.final_evidence = vr
                    else:
                        result.final_verdict = "NOT_DONE"
                        result.final_evidence = vr
                    break

                if self.requires_user_confirm and _is_critical(action):
                    label = ab_get_text(action.ref or "") if action.ref else ""
                    if self.confirm_callback and not self.confirm_callback(action, label):
                        result.final_verdict = "USER_ABORTED"
                        break
                    if not self.confirm_callback:
                        result.iterations.append(AXStep(it, tree[:300], action, False,
                                                        f"paused at critical: {label!r}",
                                                        latency_decide_s=dlat))
                        result.final_verdict = "PAUSED_AT_CRITICAL"
                        result.final_evidence = f"{action.kind} on {label!r}"
                        break

                t0 = time.monotonic()
                ok, err = ab_dispatch(action)
                disp_lat = time.monotonic() - t0
                result.iterations.append(AXStep(it, tree[:300], action, ok, err,
                                                latency_decide_s=dlat,
                                                latency_dispatch_s=disp_lat))
                if not ok:
                    stuck += 1
                    if stuck >= 3:
                        result.final_verdict = "STUCK"
                        result.error = err
                        break
                    continue
                stuck = 0
                wait_for_settle(timeout_s=4.0)

            if result.final_verdict == "UNKNOWN":
                result.final_verdict = "ITERATION_EXHAUSTED"
        except Exception as e:
            result.final_verdict = "ERROR"
            result.error = str(e)

        self._write_manifest(proof_dir, goal, skill_id, result)
        return result

    def _write_manifest(self, proof_dir: Path, goal: str, skill_id: str, result: SkillResult) -> None:
        try:
            manifest = {
                "intent_goal": goal,
                "skill_id": skill_id,
                "model": self.model,
                "max_iters": self.max_iters,
                "final_verdict": result.final_verdict,
                "final_answer": result.final_answer,
                "final_evidence": result.final_evidence,
                "error": result.error,
                "n_iterations": len(result.iterations),
                "iterations": [
                    {
                        "iteration": s.iteration,
                        "action_kind": s.action.kind if s.action else None,
                        "action_ref": s.action.ref if s.action else None,
                        "action_url": s.action.url if s.action else None,
                        "action_text": s.action.text if s.action else None,
                        "action_answer": s.action.answer if s.action else None,
                        "action_raw": (s.action.raw[:200] if s.action else None),
                        "dispatch_ok": s.dispatch_ok,
                        "dispatch_stderr": s.dispatch_stderr[:200],
                        "verifier_verdict": s.verifier_verdict,
                        "verifier_reason": s.verifier_reason,
                        "latency_decide_s": round(s.latency_decide_s, 2),
                        "latency_verify_s": round(s.latency_verify_s, 2),
                        "latency_dispatch_s": round(s.latency_dispatch_s, 2),
                        "screenshot": f"step_{s.iteration:02d}.png",
                    }
                    for s in result.iterations
                ],
            }
            (proof_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        except Exception as e:
            _logger.warning("manifest write failed: %s", e)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--goal", required=True)
    p.add_argument("--skill", default="adhoc")
    p.add_argument("--max-iters", type=int, default=12)
    p.add_argument("--model", default="qwen3:8b")
    args = p.parse_args()
    runner = AXSkillRunner(model=args.model, max_iters=args.max_iters)
    res = runner.run(goal=args.goal, skill_id=args.skill)
    print(json.dumps({
        "final_verdict": res.final_verdict,
        "final_answer": res.final_answer,
        "final_evidence": res.final_evidence,
        "n_iterations": len(res.iterations),
        "proof_dir": res.proof_dir,
        "error": res.error,
    }, indent=2))
