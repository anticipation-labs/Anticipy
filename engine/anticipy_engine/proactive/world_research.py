"""TRUE PROACTIVITY, part 2 — research the real world, browser-only (FIX-07, built 2026-07-02).

The gap this closes: before this module there was ZERO real-world research anywhere in the
proactive path — no maps, no commute, no "where will you be at 3". By design it is fixed
browser-only and general: every research question becomes a `browse_task` Job through the SAME
Bus the rest of the engine uses, which lands in hands/browser_hand._handle_agent — the same
WebVoyagerAgent behind POST /agent/run, with its nav-wall, money guard, judge, and recipe cache
intact. No maps API, no per-site hardcoding: the question is phrased as a task ("Using a maps
site in the browser, find the driving time from X to Y leaving at 2:40pm") and the AGENT picks
and drives the site. In mock-hands mode the mock hand answers deterministically, so the whole
path is suite-testable.

Person resolution reuses proactive/anticipate.research_person (the module that sat orphaned
with no live caller since it was built — this is its real caller now). Its IMAP arm stays
inert unless creds exist; the memory arm always works.
"""
from __future__ import annotations

from typing import List, Optional

from ..core.envelopes import Job

MAX_QUESTIONS = 2


async def research(bus, questions: List[str], max_q: int = MAX_QUESTIONS) -> List[dict]:
    """Answer up to max_q research questions via browse_task jobs on the shared Bus.

    Returns [{question, ok, answer, proof}] — honest per question: a wall, a dead site, or a
    mock hand yields ok=False or the mock's canned answer, never a fabricated fact.
    Failures never raise; a failed question is a recorded miss the caller can surface."""
    out: List[dict] = []
    for q in [str(x or "").strip() for x in (questions or [])][:max_q]:
        if not q:
            continue
        try:
            res = await bus.submit_job(Job(intent="browse_task", args={"task": q}))
            output = getattr(res, "output", None) or {}
            status = str(getattr(getattr(res, "status", None), "value", None)
                         or getattr(res, "status", "") or "")
            answer = (output.get("answer") or output.get("result") or output.get("note")
                      or output.get("reason") or "")
            proof = getattr(res, "proof", None) or {}
            out.append({
                "question": q,
                "ok": status == "success" and bool(str(answer).strip()),
                "answer": str(answer)[:500],
                "proof": str(proof.get("url") or proof.get("read_back") or proof or "")[:300],
            })
        except Exception as exc:
            out.append({"question": q, "ok": False, "answer": "", "proof": "",
                        "error": f"{type(exc).__name__}: {exc}"})
    return out


async def resolve_person(name: str, task_context: str, gateway,
                         remembered_items: Optional[List[dict]] = None) -> Optional[dict]:
    """Who is this person, from what the owner's world already knows.

    The live caller for the formerly-orphaned anticipate.research_person. Fail-closed:
    any error returns None (the derived need proceeds without person context)."""
    try:
        from .anticipate import research_person
        ctx = await research_person(str(name or "").strip(), str(task_context or ""),
                                    gateway, remembered_items or [])
        if ctx is None:
            return None
        if hasattr(ctx, "model_dump"):
            return ctx.model_dump()
        if hasattr(ctx, "__dict__"):
            return dict(ctx.__dict__)
        return {"summary": str(ctx)}
    except Exception:
        return None
