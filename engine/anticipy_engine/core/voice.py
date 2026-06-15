"""The product voice — how Anticipy talks to a real human.

Omar's law: talk like a smart, warm friend texting — NEVER like software. No real person says
"Anticipy: got it, dispatching to your engine." Nobody knows (or should need to know) what an
engine, a card, a loop, or an ingest is. Plain words. Two-year-old-proof. This module is the
SINGLE SOURCE OF TRUTH for that voice, used everywhere the product speaks to the user — due
reminders, yes/no asks, and the conversational reply.

Words only: nothing here ever sends, books, pays, or executes. It only chooses the wording.
"""
from __future__ import annotations

import re

from .gateway import PROVIDER_OPENROUTER, SMART

# The rules, injected into every model-written line so the voice is consistent everywhere.
PRODUCT_VOICE = (
    "You are texting a real person as their sharp, warm personal assistant — like a thoughtful "
    "friend, not a computer. RULES: use plain everyday words a twelve-year-old would use; keep it "
    "to 1-2 short sentences; no markdown, no bullet lists, no emoji spam. NEVER use insider or "
    "software words — never say 'Anticipy', 'engine', 'dispatching', 'ingest', 'card', 'loop', "
    "'pipeline', 'system', 'queue', 'task', or any jargon. Never narrate your own inner workings, "
    "never refer to yourself in the third person or by name, and never start with a label like "
    "'Reminder:' or 'Anticipy:'. Just say the human thing, the way a thoughtful friend would text it."
)

# Words/phrases that read as software, not a person. Used by the deterministic guard + tests so
# the rule is enforceable, not just hoped-for.
JARGON_WORDS = (
    "dispatching", "your engine", "the engine", "ingest", "owner_ingest", "harm-line",
    "press-go", "pipeline", "task queue", "anticipy:", "reminder:", "open loop", "the system",
)


def reads_like_a_robot(text: str) -> bool:
    """True if a line uses insider/software words a real person never would. The deterministic
    floor behind the voice rules (so a regression is a failing test, not a vibe)."""
    low = (text or "").lower()
    return any(w in low for w in JARGON_WORDS)


_REMIND_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:remind me to|remind me|remember to|don'?t forget to|"
    r"make sure (?:to|i)|i need to|i have to|i gotta|i should|note to self:?)\s+",
    re.IGNORECASE,
)


def deterministic_reminder(task: str) -> str:
    """A warm nudge built WITHOUT a model (the stub/keyless/error path). Strips the redundant
    'remind me to' framing so it never reads 'Reminder: Remind me to ...' — the exact robot line
    Omar called out."""
    raw = (task or "").strip()
    t = _REMIND_PREFIX.sub("", raw).strip() or raw
    if not t:
        return "Hey — you had something you wanted to get to around now."
    t = t[0].upper() + t[1:]
    return f"Hey, quick nudge — {t[0].lower() + t[1:]}"


async def humanize_reminder(gateway, task: str) -> str:
    """Phrase a due reminder the way a friend would text it. Uses the live model when one is
    behind the line; falls back to the deterministic warm nudge for stub/keyless/error. Words
    only — the decision to fire already passed the harm-line; this just chooses the wording."""
    fallback = deterministic_reminder(task)
    if getattr(gateway, "provider", None) != PROVIDER_OPENROUTER:
        return fallback
    prompt = (
        PRODUCT_VOICE
        + "\n\nIt's the moment they wanted a little nudge about this thing they meant to do:\n\""
        + (task or "").strip()
        + "\"\n\nText them a short, warm reminder to do it now (no 'Reminder:' label, no robot-speak):"
    )
    try:
        out = await gateway.think(prompt, tier=SMART, caller="agent", temperature=0.4, max_tokens=60)
    except Exception:
        return fallback
    out = (out or "").strip().strip('"').strip()
    # never let a model slip back into robot-speak; the deterministic nudge is always clean
    if not out or reads_like_a_robot(out):
        return fallback
    return out


# Why a human-impacting action is being checked first — phrased the way a person would say it,
# derived from the structured harm-line CATEGORY (never the raw internal reason text, which reads
# like robot notes: "memory low-confidence on recipient -> fail-safe ask").
_WHY = {
    "money": "This one spends your money, so I won't do it without your okay.",
    "binding_send": "This sends something to someone else, so I wanted to check first.",
    "casual_send": "This sends a message for you, so I wanted to check first.",
    "auth_wall": "This touches a login, so I'd rather you confirm.",
}


def ask_line(action: str, code: str, category: str = "", reason: str = "") -> str:
    """A human yes/no check before a person-or-money action. KEEPS the reply mechanism (a plain
    YES/NO, with a short code as a tie-breaker when several things are pending) but drops the robot
    framing — no 'Anticipy wants to:' and no 'Why it paused:'. The 'why' comes from the structured
    category, not the internal reason string. Deterministic on purpose: the code must be exact for
    channels/inbound.py to match the reply to THIS ask."""
    a = (action or "").strip().rstrip(".")
    a = (a[0].lower() + a[1:]) if a else a
    line = f"Quick check before I do this — want me to {a}?" if a else "Quick check — is this okay?"
    why = _WHY.get((category or "").strip())
    if not why and reason and not reads_like_a_robot(reason) and len(reason) < 80 \
            and "->" not in reason and ";" not in reason:
        why = reason[0].upper() + reason[1:]
    if why:
        line += " " + why
    code = (code or "").strip()
    tail = "Just reply YES or NO."
    if code:
        # show the code on BOTH a yes and a no so either choice is unambiguous when several pend
        tail = f"Just reply YES or NO — or \"YES {code}\" / \"NO {code}\" if I've asked about a couple things."
    return line + "\n" + tail
