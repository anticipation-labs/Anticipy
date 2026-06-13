"""The glass-box — trust, from day one.

An append-only local activity log (JSONL). Every event, proactive decision (with
the why), job, and result is written here. It is the source for the app's live
"what I'm doing / what I did" feed. Acting silently with no glass-box is not
allowed. Local only.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .envelopes import now_ts


class GlassBox:
    def __init__(self, path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def log(self, kind: str, data: dict) -> None:
        entry = {"ts": now_ts(), "kind": kind, "data": data}
        with self.path.open("a") as fh:
            fh.write(json.dumps(entry) + "\n")

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
