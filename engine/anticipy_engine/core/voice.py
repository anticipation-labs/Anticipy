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

from .gateway import PROVIDER_OPENROUTER, SMART, CHEAP

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
    """A human check before a person-or-money action. Reads like a thoughtful friend texting,
    while still carrying the short reply code needed when several asks are pending."""
    a = (action or "").strip().rstrip(".")
    # Strip internal prefixes that sound robotic in SMS
    for prefix in ("Follow up on your commitment:", "Follow up:", "Confirm task:"):
        if a.lower().startswith(prefix.lower()):
            a = a[len(prefix):].strip()
    a = (a[0].lower() + a[1:]) if a else a
    if a:
        line = f"Hey — should I go ahead and {a}?"
    else:
        line = "Hey — want me to go ahead with this?"
    why = _WHY.get((category or "").strip())
    if not why and reason and not reads_like_a_robot(reason) and len(reason) < 80 \
            and "->" not in reason and ";" not in reason:
        why = reason[0].upper() + reason[1:]
    if why:
        line += " " + why
    if code:
        line += f" Reply YES {code} or NO {code}."
    return line


# ---- CARD COPY (M2): turn the engine's structured card into the human line the user sees ----
# The card's title/reason are born as engine templates ("Block money action", "Owner task: ...",
# "...-> fail-safe ask"). The user must NEVER see those. This is the single seam that renders every
# card in the product voice: a deterministic, always-clean floor (no IDs, no engine words, no arrows,
# varied so it never reads formulaic) plus a live-model polish for true per-utterance variety.
import json as _json

_ID_RE = re.compile(r"\b[0-9a-f]{12,}\b", re.I)
_PREFIX_RE = re.compile(
    r"^\s*(?:owner task|confirm task|prepare(?: message for)?|follow up(?: on your commitment)?|"
    r"block money action|resolve browser task|capture reminder or open loop|reminder set|task)\s*:?\s*",
    re.I)


def _clean_task_text(text: str) -> str:
    t = _ID_RE.sub("", _PREFIX_RE.sub("", (text or "").strip())).strip()
    t = _REMIND_PREFIX.sub("", t).strip() or t
    return t


def _doing_phrase(disp: str) -> str:
    return {"do": "you're handling it", "ask": "you want to check first",
            "blocked": "it touches money so you'll hold it",
            "remember": "you're just noting it"}.get(disp, "you're handling it")


def humanize_card(card) -> None:
    """Deterministic, model-free human copy for a card's title + reason — the ALWAYS-clean floor:
    no IDs, no engine templates, no '->' arrows, and seeded by the user's words so different cards
    never read identically. humanize_cards() polishes on top with the live model."""
    disp = (getattr(card, "disposition", "") or "")
    act = (getattr(card, "action", "") or "")
    route = (getattr(card, "route", "") or "")
    args = getattr(card, "args", None) or {}
    task = _clean_task_text(getattr(card, "source_text", "") or getattr(card, "title", "") or "")
    short = task[:60].rstrip(" .,")
    low = (short[0].lower() + short[1:]) if short else ""
    who = (args.get("person") or "").strip()
    if disp == "blocked":
        opts = ["This one spends money, so I'll hold it for your okay.",
                "Money — I'll wait for your go before I do this.",
                "Left for you: it touches money, so you make the call."]
        why = "It spends your money, so I won't move without your okay."
    elif disp == "remember":
        opts = ["Got it — I'll remember that.", "Noted.", "Filed that away for you."]
        why = "Worth keeping in mind."
    elif disp == "ask":
        if who and ("message" in act or "draft" in act or route == "voice_text"):
            opts = [f"Want me to message {who}?", f"Should I reach out to {who}?",
                    f"I can write to {who} — say the word."]
            why = "It reaches someone else, so I'll check with you first."
        elif route == "browser" or "research" in act or "find" in act:
            opts = ([f"Want me to look into {low}?", f"Should I dig up {low} for you?",
                     f"I can chase down {low} — go?"] if low
                    else ["Want me to look into this?", "Should I dig this up?", "I can chase this down — go?"])
            why = "I want to get it right before I act."
        else:
            opts = ([f"Want me to handle {low}?", f"Should I take care of {low}?",
                     f"I can do {low} — give me the nod?"] if low
                    else ["Want me to handle this?", "Should I take this on?", "I can do this — give me the nod?"])
            why = "I'll confirm before I act on this."
    else:  # do
        title_lc = (getattr(card, "title", "") or "").lower()
        if "calendar" in act or "reminder" in act or "pickup" in title_lc or "timing" in title_lc:
            opts = ([f"I've got {low}.", f"Locked in — {low}.", f"On it — {low}, I'll watch the time."] if low
                    else ["I've got the timing on this.", "Locked in.", "On it — I'll keep the time."])
            why = "Low-risk, so I'll just keep it for you."
        else:
            opts = ([f"On it — {low}.", f"I've got {low}.", f"Taking care of {low}."] if low
                    else ["On it.", "I've got this.", "Taking care of it."])
            why = "Low-risk, so I'll take care of it."
    title = opts[hash((task or "") + disp) % len(opts)]
    card.title = _ID_RE.sub("", title).strip()[:120]
    card.reason = why


def _extract_json_array(raw: str) -> str:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-z]*\s*|\s*```$", "", s).strip()
    a, b = s.find("["), s.rfind("]")
    return s[a:b + 1] if a != -1 and b != -1 and b > a else s


async def humanize_cards(gateway, cards) -> None:
    """Render every card in the product voice. Deterministic floor first (always clean on both the
    ingest response AND the durable board), then ONE batched live-model call for per-utterance variety
    ('never the same line twice'). Words only — execution already decided upstream."""
    if not cards:
        return
    for c in cards:
        humanize_card(c)
    if getattr(gateway, "provider", None) != PROVIDER_OPENROUTER:
        return
    items = [{"n": i, "said": (getattr(c, "source_text", "") or "")[:160],
              "doing": _doing_phrase(getattr(c, "disposition", "") or "")} for i, c in enumerate(cards)]
    prompt = (PRODUCT_VOICE + "\n\nFor EACH item below, write a fresh human one-line TITLE (what you'd "
              "text them you're doing about it) and a short WHY. Vary the wording — never two identical "
              "lines, never a label or a colon-prefix. Return ONLY a JSON array like "
              "[{\"n\":0,\"title\":\"...\",\"why\":\"...\"}].\n\nITEMS:\n" + _json.dumps(items))
    try:
        raw = await gateway.think(prompt, tier=CHEAP, caller="copy", json_mode=True,
                                  temperature=0.8, max_tokens=700)
        arr = _json.loads(_extract_json_array(raw))
        by = {int(x["n"]): x for x in arr if isinstance(x, dict) and "n" in x}
    except Exception:
        return
    for i, c in enumerate(cards):
        x = by.get(i)
        if not x:
            continue
        t = (x.get("title") or "").strip().strip('"').strip()
        w = (x.get("why") or "").strip().strip('"').strip()
        if t and not reads_like_a_robot(t) and "->" not in t and "→" not in t and not _PREFIX_RE.match(t):
            c.title = _ID_RE.sub("", t)[:120]
        if w and not reads_like_a_robot(w) and "->" not in w and "→" not in w:
            c.reason = w[:160]
