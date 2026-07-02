"""sector/skeleton.py — THE one walking skeleton.

hear → infer → decide → remember → act → warm check-in → learn, as ONE orchestrated line.
This is what overnight/done_gate.py exercises and what every later step of CANON/THE_MAP.md's
order-of-attack WIDENS (never forks). It reimplements nothing — it wires the canonical modules
(see wire.py) into one path. Grafts (multi_intent recall, style learning, the browser voting
ensemble) plug into the named seams below as they land.

Run the proof:  ANTICIPY_MODEL_PROVIDER=stub PYTHONPATH=engine \
                engine/.venv/bin/python sector/proof/thin_path_test.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ThinTrace:
    """One pass of the whole line, as a human-readable trace of each stage."""
    heard: str = ""
    tasks: List[str] = field(default_factory=list)   # real tasks the brain caught
    ignored: int = 0                                 # vents/asides left silent (cardinal-sin guard)
    decisions: List[str] = field(default_factory=list)  # do / ask / blocked per task
    check_in: str = ""                               # the ONE warm message a human would see
    memory_written: int = 0                          # facts/loops the memory received
    ok: bool = False

    def summary(self) -> str:
        return (f"heard={self.heard[:50]!r} tasks={self.tasks} ignored={self.ignored} "
                f"decisions={self.decisions} mem+={self.memory_written} check_in={self.check_in[:60]!r}")


def _human_check_in(cards: list) -> str:
    """The ONE warm, human check-in for what was caught. Draft-then-ask, never a status code.
    SEAM: step 4 replaces this with the model-backed humanize_ask() for full conversational warmth."""
    actionable = [c for c in cards if (c.get("disposition") in ("do", "ask"))]
    if not actionable:
        return ""
    titles = [(_c.get("title") or _c.get("source_text") or "").strip() for _c in actionable]
    titles = [t for t in titles if t][:3]
    if not titles:
        return ""
    if len(titles) == 1:
        return f"Caught this: {titles[0]}. Want me to handle it?"
    lead = "; ".join(titles)
    return f"Caught {len(titles)} things: {lead}. Okay to go ahead?"


def _memory_delta(core, before: int) -> int:
    try:
        after = len(list(core.memory.open_loops.all())) + len(list(core.memory.profile.all()))
        return max(0, after - before)
    except Exception:
        return 0


def _memory_count(core) -> int:
    try:
        return len(list(core.memory.open_loops.all())) + len(list(core.memory.profile.all()))
    except Exception:
        return 0


async def run_thin_path(core, *, text: str = "", mp3_path: str = "") -> ThinTrace:
    """The whole product in one line. Returns a ThinTrace of every stage."""
    # 1. HEAR — mp3 (real transcription) or text.
    if mp3_path:
        # SEAM (step 4): route MP3 through capture/transcribe -> local Whisper. For the skeleton,
        # the file-ingest endpoint path already does this; here we keep the text path canonical.
        from anticipy_engine.capture.transcribe import transcribe_file  # noqa: F401
        text = transcribe_file(mp3_path) if callable(globals().get("transcribe_file", None)) else text
    heard = (text or "").strip()
    if not heard:
        return ThinTrace(heard="", ok=False)

    mem_before = _memory_count(core)

    # 2-5. INFER → DECIDE → REMEMBER → ACT — the real spine runs these as one motion.
    #      SEAM (step 2): multi_intent recall grafts in front of owner_ingest here.
    res = await core.owner_ingest("skeleton", heard, {"skeleton": True}, execute_actions=True)
    cards = res.get("cards") or []

    tasks = [(c.get("title") or c.get("source_text") or "").strip() for c in cards]
    tasks = [t for t in tasks if t]
    decisions = [c.get("disposition") for c in cards]
    ignored = int(res.get("ignored_line_count") or 0)

    # 6. WARM CHECK-IN — the ONE message the human sees.
    check_in = _human_check_in(cards)

    # 7. LEARN — did memory compound? (step 3 deepens this: style + never-re-ask + per-person)
    mem_written = _memory_delta(core, mem_before)

    tr = ThinTrace(heard=heard, tasks=tasks, ignored=ignored, decisions=decisions,
                   check_in=check_in, memory_written=mem_written)
    # The line "worked" if it caught at least one real task AND produced a human check-in for it.
    tr.ok = bool(tasks) and bool(check_in)
    return tr
