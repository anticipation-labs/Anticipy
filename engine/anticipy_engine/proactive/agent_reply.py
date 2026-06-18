"""The conversational agent reply — the real AI brain behind the voice/text line.

When the owner TEXTS or CALLS their agent, it must answer like a real assistant (Donna from
Suits): a clean, specific, helpful reply EVERY time — not a canned "Got it." This generates that
reply with the SMART model, GROUNDED in what the action engine actually did with the message (so
it never over-promises) plus optional recall context.

SAFETY: words only. This never sends, books, pays, or executes — the real act/ask already flowed
through the proactive spine (owner_ingest, harm-line). The reply just reflects that and answers the
owner. The model is told, in-band, never to claim an action the ground-truth context didn't take.
"""
from __future__ import annotations

from ..core.gateway import SMART
from ..core.voice import PRODUCT_VOICE

_SYSTEM = (
    PRODUCT_VOICE
    + " You are their always-on personal assistant (think Donna from Suits: sharp, warm, brief). "
    "The WHAT-HAPPENED block below is the GROUND TRUTH of what you just quietly took care of for "
    "them — reflect it exactly, in plain human words. If you set a reminder or made a calendar "
    "plan, confirm it specifically (what and when) without naming any machinery. If something is "
    "waiting on their okay (money, messaging someone, anything you can't undo), say it's ready and "
    "you're just waiting for their go. NEVER claim you sent a message, spent money, booked, or did "
    "anything the WHAT-HAPPENED block does not say you did. If they asked a question, answer it from "
    "the context and memory; if you don't know, say so briefly. Be specific and genuinely useful — "
    "never generic, never robotic."
)

_FALLBACK = "I'm here — give me one more sec, my brain hiccuped. Say that again?"


def summarize_actions(result: dict | None) -> str:
    """Ground truth for the reply: what the action engine actually did with this message."""
    cards = (result or {}).get("cards") or []
    if not cards:
        return ("WHAT HAPPENED: nothing actionable was found — it read as chit-chat, a vent, or a "
                "question (no task was created, nothing was done).")
    lines = []
    for c in cards[:6]:
        disp = c.get("disposition")
        title = (c.get("title") or c.get("source_text") or "").strip()[:120]
        if disp == "do":
            lines.append(f"- DID (prepared, reversible — nothing irreversible happened): {title}")
        elif disp == "ask":
            lines.append(f"- SET UP, WAITING FOR YOUR OK (touches money or another person): {title}")
        elif disp == "blocked":
            lines.append(f"- BLOCKED, needs you (money is a hard stop): {title}")
        elif disp == "remember":
            lines.append(f"- REMEMBERED for you: {title}")
        else:
            lines.append(f"- {disp}: {title}")
    return "WHAT HAPPENED:\n" + "\n".join(lines)


_FINDS_FALLBACK = "Heads up — I caught a few things that need your okay before I can act. They're ready in the app whenever you are."


async def notify_finds(gateway, cards: list[dict]) -> str | None:
    """Proactive, HUMAN text telling the owner what the engine just found that it CANNOT act on
    without their okay (money / a send to a person / anything irreversible) — and that it's ready
    and waiting. Words only; it never acted. Returns None when there is nothing gated to report (so
    no needless text). One consolidated message (never one-per-item -> no flood). Model-written in
    the product voice, grounded in the actual gated cards, never claiming it did them."""
    gated = [c for c in (cards or [])
             if c.get("disposition") in ("blocked", "ask")
             or (c.get("autonomy_mode") in ("PREPARE_THEN_STOP", "CLARIFY_FIRST"))]
    if not gated:
        return None
    items = []
    for c in gated[:5]:
        what = (c.get("title") or c.get("source_text") or "").strip()[:120]
        why = "money — your hard stop" if c.get("disposition") == "blocked" else "needs your okay"
        items.append(f"- {what}  ({why})")
    if gateway is None:
        return _FINDS_FALLBACK
    prompt = (_SYSTEM
              + "\n\nYou just quietly went through your owner's day. These are the ONLY things you "
              "could NOT do on your own — each touches money, another person, or something you can't "
              "undo, so you prepared them and STOPPED, waiting for their okay. You did NOT do any of "
              "them.\n\nWAITING FOR THEIR OKAY:\n" + "\n".join(items)
              + "\n\nText them ONE short, warm, human heads-up (1-2 sentences): tell them plainly what "
              "you caught that's waiting on their go, and that you've got it ready but won't act "
              "without their okay. Be specific about the items, never robotic, never a list dump, "
              "never claim you did them. Your text:")
    try:
        out = await gateway.think(prompt, tier=SMART, caller="agent", temperature=0.5, max_tokens=160)
    except Exception:
        return _FINDS_FALLBACK
    return (out or "").strip() or _FINDS_FALLBACK


async def agent_reply(gateway, message: str, *, result: dict | None = None, recall: str = "",
                      ground: str = "", caller: str = "agent") -> str:
    """Generate the agent's reply to the owner's message (SMS or voice). Words only; never executes.
    Returns a safe fallback line on any model/transport error so the owner is NEVER left unanswered.

    ``ground`` overrides the WHAT-HAPPENED context: the SMS path leaves it empty and the
    reply is grounded in ``summarize_actions(result)`` (the cards owner_ingest produced); the
    voice path has no card result yet, so it passes a verdict-derived ground-truth line
    (ACT/ASK/SILENT) here. Either way the reply may only reflect what that block actually did."""
    if gateway is None:
        return _FALLBACK
    context = ground.strip() if ground and ground.strip() else summarize_actions(result)
    if recall:
        context += "\n\nRELEVANT MEMORY:\n" + str(recall)[:1200]
    prompt = (_SYSTEM + "\n\n" + context + "\n\nThe user just said to you: \""
              + (message or "").strip() + "\"\n\nYour reply (1-2 short, natural sentences):")
    try:
        out = await gateway.think(prompt, tier=SMART, caller=caller, temperature=0.5, max_tokens=160)
    except Exception:
        return _FALLBACK
    return (out or "").strip() or _FALLBACK
