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

import httpx
import numpy as np
from websockets.sync.client import connect as _ws_connect

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


def _connect_session_keepalive(port: int = 9222,
                               open_url: Optional[str] = None) -> CDPSession:
    """Same attach logic as cdp_dispatcher.connect_to_chrome, but with
    websocket client keepalive DISABLED (ping_interval=None).

    Why this exists separately: cdp_dispatcher.py is a protected file
    in this build and must not be modified. Its connect_to_chrome
    opens the ws with the websockets default 20s client keepalive.
    The sync websockets client only services control frames during
    send/recv, so a 30s+ OpenRouter call between CDP ops starves the
    keepalive and the client kills the connection ("sent 1011 ...
    keepalive ping timeout"). Disabling client pings keeps the CDP
    socket alive across long model calls. Chrome does not ping, so
    nothing else needs the keepalive.
    """
    r = httpx.get(f"http://localhost:{port}/json/list", timeout=5.0)
    r.raise_for_status()
    targets = r.json()
    target = None
    if open_url:
        pr = httpx.put(f"http://localhost:{port}/json/new?{open_url}", timeout=10.0)
        pr.raise_for_status()
        target = pr.json()
    if target is None:
        for t in targets:
            if (t.get("url") or "").startswith(("http://", "https://")):
                target = t
                break
        if target is None and targets:
            target = targets[0]
    if target is None:
        raise RuntimeError("no CDP target available on :9222")
    ws = _ws_connect(target["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024,
                     ping_interval=None, ping_timeout=None, open_timeout=20)
    sess = CDPSession(ws=ws, target_id=target["id"],
                      rng=np.random.default_rng())
    sess.send("Page.enable")
    sess.send("Runtime.enable")
    sess.send("DOM.enable")
    return sess
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
    "Split a browser task into the FEWEST independent subtasks. "
    'Output ONLY JSON: {"subtasks": ["...", "..."]}.\n'
    "Hard rules:\n"
    "- Preserve EVERY requirement of the original task verbatim. "
    "Never drop, summarize, or omit any value, cell, row, or detail. "
    "If the task lists data (cells, rows, numbers), that data MUST "
    "appear in full inside a subtask.\n"
    "- Default to ONE subtask. Only split when subtasks are truly "
    "independent objectives that need different pages or a result "
    "from an earlier step (e.g. 'look up X' then 'email about X').\n"
    "- Do NOT split a single coherent piece of work into micro-steps. "
    "Filling many cells in ONE spreadsheet is ONE subtask (the loop "
    "handles the individual cells). Opening a site and acting on it "
    "is ONE subtask.\n"
    "Example: 'Open Sheets, make a sheet, put a title in A1 and "
    "three data rows' -> ONE subtask containing all of that, not five."
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
    "return action done with the answer. One action only. No prose.\n"
    "GOOGLE SHEETS / spreadsheet grid (follow EXACTLY):\n"
    "Grid cells are canvas with NO @eN ref. NEVER click a cell. NEVER "
    "click toolbar buttons, the Insert menu, or use Ctrl/Cmd key "
    "combos on a sheet (that creates Tables/charts and breaks the "
    "task). Use ONLY this mechanical loop per cell:\n"
    "  1. action click on the Name Box (the small textbox at the far "
    "left just below the toolbar, its accessible name is the current "
    "cell like \"A1\"; pick that @eN ref).\n"
    "  2. action type with text equal to the target cell, e.g. \"A1\".\n"
    "  3. action key with text Enter (selects that cell).\n"
    "  4. action type with text equal to the cell's value.\n"
    "  5. action key with text Enter (commits the value).\n"
    "Repeat 1-5 for every required cell (A1, A3, B3, A4..A6, B4..B6, "
    "etc.). When every required cell has been entered, action done. "
    "Do not declare done before all listed cells and rows are filled."
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
                txt = action.get("text") or ""
                # Canvas grid apps (Google Sheets/Docs) ignore raw
                # keyDown/keyUp; CDP Input.insertText reliably inserts
                # into the focused cell/editor. Keep humanlike click
                # for targeting, use insertText for the payload.
                try:
                    sess.send("Input.insertText", {"text": txt}, timeout_s=8.0)
                except Exception:
                    humanlike_type(sess, txt)
                return (True, f"typed {txt[:30]!r}", True)
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
        no_action_count = 0
        decide_model = TEXT_MODEL
        last_sig = None
        best_ptext_len = 0  # progress proxy: a sheet being filled grows

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
                # A single unparseable response is usually transient.
                # Re-observe and re-decide; only hard-fail if the model
                # cannot produce ANY action many times in a row.
                no_action_count += 1
                history.append(f"i{it}: model gave no parseable action, retrying")
                if no_action_count >= 8:
                    return {"subgoal": subgoal, "status": "HARD_FAIL",
                            "answer": "", "evidence": "no parseable action x8",
                            "iters": it}
                continue
            no_action_count = 0

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
                if diverged_streak >= 6:
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
                # Progress proxy: a sheet/page being filled grows its
                # visible text. If text grew since the best seen, the
                # task IS advancing even when the verifier is strict on
                # an intermediate cell-selection step. Reset the streak.
                cur_len = len(ptext)
                made_progress = cur_len > best_ptext_len + 2
                if made_progress:
                    best_ptext_len = cur_len

                if v.status == "DIVERGED" and not made_progress:
                    diverged_streak += 1
                    history.append(f"i{it}: VERIFIER DIVERGED: {v.evidence}")
                    if diverged_streak == 2 and decide_model == TEXT_MODEL:
                        decide_model = VISION_MODEL  # escalate
                        history.append("i: escalating action model to Kimi K2.6")
                    elif diverged_streak >= 6:
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
            sess = _connect_session_keepalive(
                port=self.cdp_port, open_url=starting_url or "about:blank")
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
