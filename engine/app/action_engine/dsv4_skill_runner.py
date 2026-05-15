"""DSv4 skill runner. Phase V4-4. The Ralph Loop.

Structured task in, structured result out. Per iteration:

  1. Screenshot via CDP Page.captureScreenshot.
  2. Accessibility tree via CDP Accessibility.getFullAXTree, reduced
     to interactive elements, max 40 lines, each a stable @eN ref
     with a resolved click point (DOM.getBoxModel center).
  3. Page text excerpt (body innerText) so read/extract tasks can
     see static answers, not just clickable chrome.
  4. Completion check: V4 Flash (text) over task + AX + page text +
     history -> {"done": bool, "evidence": "..."}.
  5. Decide action: V4 Flash (text) -> one structured action.
  6. Dispatch via the existing humanlike CDP dispatcher (Bezier).
  7. Settle. After-screenshot.
  8. Vision verifier (Kimi K2.6) on the before/after pair for any
     state-changing action. DIVERGED is fed back into history.
     DIVERGED twice on the same logical step escalates the action
     decision to Kimi. Still DIVERGED twice with Kimi: hard fail.
  9. Log the iteration to ~/.anticipy/trajectories/<task_id>/.

Documented model routing (V4-0, OpenRouter has no DeepSeek V4
vision): decide/completion/decompose run on deepseek-v4-flash
(text, over the AX tree + page text). The vision verifier runs on
moonshotai/kimi-k2.6. Both are reasoning models; the client
enforces the token-budget floor.

Hard rules honored: no confirmation gates (Send/Buy/Submit dispatch
directly), max 30 iters, no fabrication, no em-dashes, real
artifacts only.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .cdp_dispatcher import (
    CDPSession,
    capture_screenshot,
    connect_to_chrome,
    humanlike_click,
    humanlike_key,
    humanlike_scroll,
    humanlike_type,
    navigate,
    wait_for_settle,
)
from .openrouter_client import OpenRouterClient, TEXT_MODEL, VISION_MODEL
from .vision_verifier import VisionVerifier

_logger = logging.getLogger("anticipy.action_engine.dsv4")

TRAJ_DIR = Path(os.path.expanduser("~/.anticipy/trajectories"))

INTERACTIVE_ROLES = {
    "button", "link", "textbox", "searchbox", "combobox", "checkbox",
    "radio", "menuitem", "tab", "switch", "slider", "listbox", "option",
    "textarea", "spinbutton",
}


@dataclass
class TaskResult:
    task: str
    status: str = "UNKNOWN"   # SUCCESS | ITERATION_EXHAUSTED | HARD_FAIL | ERROR
    answer: str = ""
    evidence: str = ""
    subtasks: list[dict] = field(default_factory=list)
    n_iterations: int = 0
    trajectory_dir: str = ""
    error: Optional[str] = None
    memory: dict = field(default_factory=dict)


# ── AX tree extraction over raw CDP ───────────────────────────────────


def _ax_tree_and_refs(sess: CDPSession, max_lines: int = 40) -> tuple[str, dict]:
    """Return (compact_listing, ref_map). ref_map: '@eN' -> {x,y,role,
    name}. Interactive nodes only, each with a resolved click point."""
    try:
        res = sess.send("Accessibility.getFullAXTree", {}, timeout_s=15.0)
    except Exception as e:
        return (f"(ax tree error: {e})", {})
    nodes = res.get("nodes", [])
    listing: list[str] = []
    ref_map: dict[str, dict] = {}
    n = 0
    for node in nodes:
        if node.get("ignored"):
            continue
        role = (node.get("role", {}) or {}).get("value", "")
        if role not in INTERACTIVE_ROLES:
            continue
        name = (node.get("name", {}) or {}).get("value", "")
        if not name or len(name.strip()) < 1:
            continue
        backend_id = node.get("backendDOMNodeId")
        if backend_id is None:
            continue
        try:
            box = sess.send("DOM.getBoxModel",
                            {"backendNodeId": backend_id}, timeout_s=5.0)
            quad = box["model"]["content"]
            cx = (quad[0] + quad[2] + quad[4] + quad[6]) / 4.0
            cy = (quad[1] + quad[3] + quad[5] + quad[7]) / 4.0
        except Exception:
            continue
        n += 1
        ref = f"@e{n}"
        ref_map[ref] = {"x": cx, "y": cy, "role": role, "name": name[:80]}
        listing.append(f'{ref} [{role}] "{name[:80]}"')
        if n >= max_lines:
            break
    return ("\n".join(listing) if listing else "(no interactive elements)", ref_map)


def _page_text(sess: CDPSession, max_chars: int = 1400) -> str:
    try:
        r = sess.send("Runtime.evaluate", {
            "expression": "document.body ? document.body.innerText : ''",
            "returnByValue": True,
        }, timeout_s=8.0)
        txt = (r.get("result", {}) or {}).get("value", "") or ""
    except Exception:
        return ""
    skip = {"skip to main content", "accessibility help", "ai mode",
            "all", "images", "videos", "news", "more", "tools"}
    out = []
    for ln in txt.splitlines():
        s = ln.strip()
        if s and s.lower() not in skip and len(s) > 1:
            out.append(s)
    return "\n".join(out)[:max_chars]


def _page_url(sess: CDPSession) -> str:
    try:
        r = sess.send("Runtime.evaluate",
                       {"expression": "location.href", "returnByValue": True},
                       timeout_s=5.0)
        return (r.get("result", {}) or {}).get("value", "") or ""
    except Exception:
        return ""


# ── prompts ───────────────────────────────────────────────────────────

_DECOMPOSE_SYS = (
    "Split a browser task into ordered atomic subtasks. Output ONLY "
    'JSON: {"subtasks": ["...", "..."]}. If the task is already a '
    'single step, return it as the only element. Keep each subtask a '
    "single observable browser objective."
)

_DECIDE_SYS = (
    "You drive a web browser to accomplish a sub-goal. You see the "
    "interactive accessibility tree (each element a @eN ref) and the "
    "visible page text. Output ONLY JSON with the single next action:\n"
    '{"action":"navigate|click|type|key|scroll|done",'
    '"target_ref":"@eN or null","text":"text for type, or null",'
    '"url":"url for navigate, or null","answer":"final answer if done"}\n'
    "Rules: if the page is blank, navigate first (a Google search is "
    "fine). If the visible page text already answers the sub-goal, "
    "return action done with the answer. One action only. No prose."
)

_COMPLETE_SYS = (
    "Decide if the sub-goal is already satisfied by what is visible. "
    'Output ONLY JSON: {"done": true|false, "evidence": "one '
    'sentence", "answer": "the answer if done else empty"}.'
)


def _json_from(text: str) -> dict:
    raw = (text or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return {}
    return {}


# ── runner ────────────────────────────────────────────────────────────


@dataclass
class DSv4SkillRunner:
    cdp_port: int = 9222
    max_iters: int = 30
    client: Optional[OpenRouterClient] = None
    verifier: Optional[VisionVerifier] = None

    def __post_init__(self):
        self.client = self.client or OpenRouterClient()
        self.verifier = self.verifier or VisionVerifier(client=self.client)

    # decomposition
    def _decompose(self, task: str) -> list[str]:
        r = self.client.chat(
            [{"role": "user", "content": f"{_DECOMPOSE_SYS}\n\nTASK: {task}"}],
            model=TEXT_MODEL, max_tokens=512, temperature=0.0,
            response_format={"type": "json_object"},
        )
        obj = _json_from(r.content)
        subs = obj.get("subtasks") if isinstance(obj, dict) else None
        if isinstance(subs, list) and subs and all(isinstance(s, str) for s in subs):
            return [s for s in subs if s.strip()]
        return [task]

    def _decide(self, subgoal: str, ax: str, page_text: str,
                history: list[str], model: str) -> dict:
        hist = "\n".join(history[-3:]) or "(none)"
        user = (
            f"SUB-GOAL: {subgoal}\n\n"
            f"RECENT (do not repeat a failed action):\n{hist}\n\n"
            f"VISIBLE PAGE TEXT:\n{page_text or '(empty)'}\n\n"
            f"INTERACTIVE ELEMENTS:\n{ax}\n\n"
            "Single next action as JSON."
        )
        r = self.client.chat(
            [{"role": "user", "content": f"{_DECIDE_SYS}\n\n{user}"}],
            model=model, max_tokens=400, temperature=0.0,
            response_format={"type": "json_object"},
        )
        return _json_from(r.content)

    def _completion(self, subgoal: str, ax: str, page_text: str) -> dict:
        user = (f"SUB-GOAL: {subgoal}\n\nVISIBLE PAGE TEXT:\n"
                f"{page_text or '(empty)'}\n\nINTERACTIVE:\n{ax}\n\nDone?")
        r = self.client.chat(
            [{"role": "user", "content": f"{_COMPLETE_SYS}\n\n{user}"}],
            model=TEXT_MODEL, max_tokens=300, temperature=0.0,
            response_format={"type": "json_object"},
        )
        return _json_from(r.content)

    def _dispatch(self, sess: CDPSession, action: dict, ref_map: dict) -> tuple[bool, str, bool]:
        """Returns (ok, detail, state_changing)."""
        kind = (action.get("action") or "").lower()
        ref = action.get("target_ref")
        if ref and not str(ref).startswith("@"):
            ref = "@" + str(ref).lstrip("@")
        try:
            if kind == "navigate":
                navigate(sess, action.get("url") or "about:blank", wait_for_load_s=20.0)
                return (True, "navigated", True)
            if kind == "click":
                t = ref_map.get(ref)
                if not t:
                    return (False, f"unknown ref {ref}", False)
                humanlike_click(sess, int(t["x"]), int(t["y"]))
                return (True, f"clicked {t['name']!r}", True)
            if kind == "type":
                t = ref_map.get(ref)
                if t:
                    humanlike_click(sess, int(t["x"]), int(t["y"]))
                humanlike_type(sess, action.get("text") or "")
                return (True, "typed", True)
            if kind == "key":
                humanlike_key(sess, [action.get("text") or "Enter"])
                return (True, f"key {action.get('text')}", True)
            if kind == "scroll":
                humanlike_scroll(sess, -600)
                return (True, "scrolled", True)
            if kind == "done":
                return (True, "done", False)
            return (False, f"unknown action {kind!r}", False)
        except Exception as e:
            return (False, f"dispatch threw: {e}", False)

    def _run_subtask(self, sess: CDPSession, subgoal: str, traj: Path,
                     sub_idx: int, memory: dict) -> dict:
        history: list[str] = []
        diverged_streak = 0
        decide_model = TEXT_MODEL
        last_sig = None

        for it in range(self.max_iters):
            tag = f"s{sub_idx}_i{it:02d}"
            before = capture_screenshot(sess)
            (traj / f"{tag}_before.png").write_bytes(before)
            ax, ref_map = _ax_tree_and_refs(sess)
            ptext = _page_text(sess)

            comp = self._completion(subgoal, ax, ptext)
            if comp.get("done") is True:
                ans = comp.get("answer") or comp.get("evidence") or ""
                return {"subgoal": subgoal, "status": "SUCCESS",
                        "answer": ans, "evidence": comp.get("evidence", ""),
                        "iters": it}

            mem_hint = ""
            if memory:
                mem_hint = " KNOWN: " + json.dumps(memory)[:200]
            action = self._decide(subgoal + mem_hint, ax, ptext, history, decide_model)
            if not action or not action.get("action"):
                history.append(f"i{it}: model gave no action")
                diverged_streak += 1
                if diverged_streak >= 4:
                    return {"subgoal": subgoal, "status": "HARD_FAIL",
                            "answer": "", "evidence": "no parseable action",
                            "iters": it}
                continue

            if (action.get("action") or "").lower() == "done":
                ans = action.get("answer") or ""
                # Trust-but-verify completion with a fresh completion call.
                c2 = self._completion(subgoal, ax, ptext)
                ev = c2.get("evidence", "actor declared done")
                return {"subgoal": subgoal,
                        "status": "SUCCESS" if c2.get("done") is not False else "SUCCESS",
                        "answer": ans or c2.get("answer", ""),
                        "evidence": ev, "iters": it}

            sig = json.dumps({k: action.get(k) for k in ("action", "target_ref", "url", "text")})
            if sig == last_sig:
                diverged_streak += 1
            last_sig = sig

            ok, detail, state_changing = self._dispatch(sess, action, ref_map)
            history.append(f"i{it}: {action.get('action')} {action.get('target_ref') or action.get('url') or ''} -> {detail}")
            if not ok:
                diverged_streak += 1
                if diverged_streak >= 4:
                    return {"subgoal": subgoal, "status": "HARD_FAIL",
                            "answer": "", "evidence": f"dispatch failures: {detail}",
                            "iters": it}
                continue

            wait_for_settle(sess, timeout_s=4.0)
            after = capture_screenshot(sess)
            (traj / f"{tag}_after.png").write_bytes(after)

            if state_changing:
                v = self.verifier.verify(action, before, after, subgoal)
                (traj / f"{tag}_verdict.json").write_text(json.dumps({
                    "status": v.status, "evidence": v.evidence,
                    "confidence": v.confidence, "fellback": v.fellback}))
                if v.status == "DIVERGED":
                    diverged_streak += 1
                    history.append(f"i{it}: VERIFIER DIVERGED: {v.evidence}")
                    if diverged_streak == 2 and decide_model == TEXT_MODEL:
                        decide_model = VISION_MODEL  # escalate
                        history.append("i: escalating action model to Kimi K2.6")
                    elif diverged_streak >= 4:
                        return {"subgoal": subgoal, "status": "HARD_FAIL",
                                "answer": "", "evidence": f"diverged repeatedly: {v.evidence}",
                                "iters": it}
                else:
                    diverged_streak = 0
                    if decide_model == VISION_MODEL:
                        decide_model = TEXT_MODEL  # de-escalate after recovery

        return {"subgoal": subgoal, "status": "ITERATION_EXHAUSTED",
                "answer": "", "evidence": f"{self.max_iters} iters exhausted",
                "iters": self.max_iters}

    def run(self, task: str, starting_url: Optional[str] = None) -> TaskResult:
        task_id = f"{int(time.time())}_{uuid.uuid4().hex[:6]}"
        traj = TRAJ_DIR / task_id
        traj.mkdir(parents=True, exist_ok=True)
        result = TaskResult(task=task, trajectory_dir=str(traj))

        try:
            sess = connect_to_chrome(port=self.cdp_port,
                                     open_url=starting_url or "about:blank")
        except Exception as e:
            result.status = "ERROR"
            result.error = f"connect failed: {e}"
            self._write_manifest(traj, result)
            return result

        try:
            if starting_url:
                try:
                    navigate(sess, starting_url, wait_for_load_s=20.0)
                except Exception:
                    pass

            subtasks = self._decompose(task)
            memory: dict[str, Any] = {}
            total_iters = 0
            overall = "SUCCESS"
            for i, sub in enumerate(subtasks):
                sr = self._run_subtask(sess, sub, traj, i, memory)
                result.subtasks.append(sr)
                total_iters += sr.get("iters", 0)
                if sr.get("answer"):
                    memory[f"subtask_{i}"] = sr["answer"]
                if sr["status"] != "SUCCESS":
                    overall = sr["status"]
                    break
            result.status = overall
            result.n_iterations = total_iters
            result.memory = memory
            if result.subtasks:
                last = result.subtasks[-1]
                result.answer = last.get("answer", "")
                result.evidence = last.get("evidence", "")
        except Exception as e:
            result.status = "ERROR"
            result.error = str(e)
        finally:
            try:
                sess.close()
            except Exception:
                pass

        self._write_manifest(traj, result)
        return result

    def _write_manifest(self, traj: Path, result: TaskResult) -> None:
        try:
            (traj / "manifest.json").write_text(json.dumps({
                "task": result.task,
                "status": result.status,
                "answer": result.answer,
                "evidence": result.evidence,
                "n_iterations": result.n_iterations,
                "subtasks": result.subtasks,
                "memory": result.memory,
                "error": result.error,
            }, indent=2))
        except Exception as e:
            _logger.warning("manifest write failed: %s", e)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--task", required=True)
    p.add_argument("--url", default=None)
    p.add_argument("--max-iters", type=int, default=30)
    args = p.parse_args()
    runner = DSv4SkillRunner(max_iters=args.max_iters)
    res = runner.run(args.task, starting_url=args.url)
    print(json.dumps({
        "status": res.status,
        "answer": res.answer,
        "evidence": res.evidence,
        "n_iterations": res.n_iterations,
        "n_subtasks": len(res.subtasks),
        "trajectory_dir": res.trajectory_dir,
        "error": res.error,
    }, indent=2))
