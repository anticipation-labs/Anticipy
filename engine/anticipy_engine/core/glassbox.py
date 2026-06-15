"""The glass-box — trust, from day one.

An append-only local activity log (JSONL). Every event, proactive decision (with
the why), job, and result is written here. It is the source for the app's live
"what I'm doing / what I did" feed. Acting silently with no glass-box is not
allowed. Local only.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from .envelopes import now_ts

# Size cap so the append-only log can NEVER grow unbounded (a runaway glassbox.jsonl once hit
# 21GB and filled the disk). On overflow we keep the most recent lines and drop the old head.
# Tunable via env; this is a dev/activity log surfaced in the app feed, not durable state.
_DEFAULT_MAX_BYTES = 8 * 1024 * 1024   # 8 MB
_DEFAULT_KEEP_LINES = 4000


class GlassBox:
    def __init__(self, path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def log(self, kind: str, data: dict) -> None:
        entry = {"ts": now_ts(), "kind": kind, "data": data}
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")
        self._maybe_rotate()

    def _maybe_rotate(self) -> None:
        """Keep the log bounded: if it exceeds the byte cap, atomically rewrite it with only the
        most recent lines that FIT the byte budget (old head dropped). A true BYTE cap — immune to
        a huge / zero KEEP_LINES or long lines — and it NEVER raises into the caller (logging must
        not crash the engine, even on a malformed env value). Concurrent writers may drop an
        in-flight append during rotation; acceptable for a dev activity log, not durable state."""
        try:
            try:
                max_bytes = int(os.environ.get("ANTICIPY_GLASSBOX_MAX_BYTES", "") or _DEFAULT_MAX_BYTES)
            except (TypeError, ValueError):
                max_bytes = _DEFAULT_MAX_BYTES
            try:
                keep_lines = int(os.environ.get("ANTICIPY_GLASSBOX_KEEP_LINES", "") or _DEFAULT_KEEP_LINES)
            except (TypeError, ValueError):
                keep_lines = _DEFAULT_KEEP_LINES
            if max_bytes <= 0:
                max_bytes = _DEFAULT_MAX_BYTES
            keep_lines = max(1, keep_lines)  # 0 must never mean "keep everything"

            if self.path.stat().st_size <= max_bytes:
                return
            with self.path.open("r") as fh:
                lines = fh.readlines()
            # keep newest-first until we hit EITHER keep_lines OR the byte budget; always >=1 line
            kept, budget = [], max_bytes
            for ln in reversed(lines):
                b = len(ln.encode("utf-8", "replace"))
                if kept and (len(kept) >= keep_lines or budget - b < 0):
                    break
                budget -= b
                kept.append(ln)
            kept.reverse()
            tmp = self.path.with_name(self.path.name + ".tmp")
            with tmp.open("w") as fh:
                fh.writelines(kept)
            os.replace(tmp, self.path)  # atomic rename; readers never see a torn file
        except Exception:
            pass  # logging must NEVER crash the engine (incl. a malformed env value)

    def entries(self) -> List[dict]:
        lines = self.path.read_text().splitlines()
        return [json.loads(ln) for ln in lines if ln.strip()]

    def tail(self, n: int = 50) -> List[dict]:
        return self.entries()[-n:]

    def summaries(self, n: int = 50) -> List[dict]:
        """Pre-rendered, human-readable rows for the app feed (so the Swift side
        never has to decode arbitrary JSON)."""
        return [{"ts": e["ts"], "kind": e["kind"], "summary": _summarize(e)} for e in self.tail(n)]


def _summarize(entry: dict) -> str:
    kind, d = entry["kind"], entry.get("data", {})
    if kind == "event":
        return f"heard: {d.get('text', '')}"
    if kind == "owner_ingest":
        source = d.get("source", "input")
        mode = "ran safe actions" if d.get("execute_actions") else "created cards"
        return (
            f"{source}: processed {d.get('lines', 0)} lines -> "
            f"{d.get('cards', 0)} cards; ignored {d.get('ignored', 0)} ({mode})"
        )
    if kind == "owner_upload_ingest":
        return f"uploaded {d.get('filename', 'file')} as {d.get('kind', 'input')}"
    if kind == "owner_card_resolved":
        decision = "approved" if d.get("approved") else "declined"
        return f"{decision} card {str(d.get('card_id', ''))[:8]} -> {d.get('state', '')}"
    if kind == "memory_loop_resolved":
        return f"closed loop: {d.get('text', '')} -> {d.get('status', '')}"
    if kind == "connection_checked":
        detail = d.get("message") or d.get("connect_url") or d.get("tool") or ""
        return f"connection {d.get('name', 'app')}: {d.get('status', '')} — {detail}"
    if kind == "trigger_fired":
        return f"proactive scan fired: {d.get('task', '')} -> {d.get('decision', '')}"
    if kind == "decision":
        return f"decided {d.get('decision')} — {d.get('text', '')}"
    if kind == "ask_human":
        return f"asking you first: {d.get('text', '')}"
    if kind == "ask_sent":
        action = d.get("action") or d.get("goal_id", "")
        return f"waiting for you: {action}"
    if kind == "ask_approved":
        return f"approved ask {str(d.get('ask_id', ''))[:8]} -> {d.get('state', '')}"
    if kind == "ask_declined":
        return f"declined: {d.get('action', '')}"
    if kind == "blocked":
        return f"hard wall: {d.get('category', 'blocked')} — {d.get('action', '')}"
    if kind == "notify":
        return f"notified you: {d.get('task', '')}"
    if kind == "job":
        return f"doing: {d.get('intent')}"
    if kind == "result":
        ok = d.get("status")
        return f"result: {d.get('status')}" + (" ✓" if ok == "success" else "")
    if kind == "approval":
        return f"approval for {d.get('intent')}: {'yes' if d.get('approved') else 'no'}"
    if kind.startswith("goal_"):
        return f"{kind.replace('_', ' ')}: {d.get('goal_id', '')[:8]}"
    if kind == "reroute":
        return f"rerouting {d.get('from')} → {d.get('to')}"
    return f"{kind}: {d}"
