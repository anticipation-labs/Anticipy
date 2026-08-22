"""LLM client for Anticipy's brain.

Uses Google Gemini when GEMINI_API_KEY is set, or OpenRouter when only its
credential is present.
Falls back to a deterministic heuristic engine when no key is present, so the
whole pipeline is provable end-to-end without secrets. The real key only
swaps the reasoning core; the plumbing is identical.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Cheap, fast triage model per the product spec (Omar picked these).
DEFAULT_MODEL = os.environ.get("ANTICIPY_MODEL", "deepseek/deepseek-v3.2")

# A SECOND, CHEAPER MODEL FOR THE MECHANICAL CALLS.
#
# One ambient utterance costs 4-6 model calls, and they are not the same kind of
# work. Triage decides whether to act at all; _voice writes the words the owner
# reads; ends_in_the_world decides whether something is consequential. Those are
# judgement, and they stay on the good model.
#
# Fact extraction, filling a known fact into a goal, and asking whether two
# task descriptions are the same plan are mechanical: structured in, structured
# out, no taste required. Measured 2026-08-21 they were 36% of the spend.
#
# UNSET MEANS NO CHANGE. Absent this variable every call uses the main model, so
# nothing about the default deployment moves.
AUX_MODEL = os.environ.get("ANTICIPY_AUX_MODEL", "")

# The FALLBACK timezone. Per-owner now, because this used to be the only one.
#
# It was a server-wide constant, so every prompt was grounded in Vancouver's
# time of day no matter who was speaking. With one user that is invisible; the
# second person to onboard, from anywhere else, would be told the wrong hour
# and have her quiet hours land in the middle of their afternoon.
TZ = ZoneInfo(os.environ.get("ANTICIPY_TZ", "America/Vancouver"))


def owner_tz(name: Optional[str] = None) -> ZoneInfo:
    """The owner's own zone, falling back to the server default.

    Never raises: a junk or unknown identifier from an old or odd client must
    not stop her thinking, it just means she uses the fallback.
    """
    if name and isinstance(name, str) and name.strip():
        try:
            return ZoneInfo(name.strip())
        except Exception:
            pass
    return TZ


def who_line(first_name: Optional[str] = None) -> str:
    """WHO they are, in one sentence — or nothing at all.

    where_line stops the model inventing a city. This stops it inventing a
    third party out of the owner himself. Live 2026-08-21, on an account whose
    profile first_name is set, "prescription. need to. the repeat one, it runs
    out" came back as "i can get that repeat prescription going for Alex;
    which one is it, and what pharmacy does he use?" — texted TO Alex, about
    Alex. The same session with no name in play was correct ("which accountant
    is that, and which receipts should i attach?"), so the name was the
    trigger: every prompt said what he needed and none of them said he was
    the one reading it.

    The carve-out is load-bearing. A blanket ban on the third person breaks
    the case the product exists for — "send Priya the invoice" must still name
    Priya and still call her "her".

    "" when the name is unknown: nothing can be misattributed and no caller
    pays for the tokens.
    """
    name = (first_name or "").strip().split(" ")[0].strip()
    if not name:
        return ""
    return (f'You are writing TO {name}: {name} is "you" — use the name only '
            f'to greet them, never as a third person ("for {name}", "he", '
            f'"she", "they"), while anyone ELSE you name is a third party, '
            f'named and described normally.')


def where_line(tz_name: Optional[str] = None) -> str:
    """Where the owner is, in one sentence — always one sentence.

    now_line() has always carried the TIME and never the PLACE, which is how
    "book dinner" became a reservation in Seattle for somebody who lives in
    Vancouver. An IANA identifier already holds the city, so this costs the
    user no permission prompt and no typing.

    IT USED TO RETURN "" WHEN THE ZONE WAS UNKNOWN, and silence is not
    neutral. Live 2026-08-22, an account whose profile says
    America/Los_Angeles asked how late "the post office on Main" is open on
    Saturdays and was told about Philadelphia, then hedged in the same
    breath. Nothing in the prompt was wrong; nothing in it said the place was
    unknown either, so the model filled the hole and sounded sure. The
    unknown case now says so out loud, in one sentence, because this text
    rides on every call including the cheap ones.
    """
    raw = (tz_name or "").strip()
    city = raw.rsplit("/", 1)[-1].replace("_", " ").strip() if "/" in raw else ""
    if not city:
        return ("You do not know where they are — never assume a city; if an "
                "answer depends on which locality they mean, ask or say it "
                "depends instead of naming one.")
    return (f"They are in {city} — anything local (a restaurant, a shop, a "
            f"clinic) means {city} unless they say otherwise.")


def now_line(tz_name: Optional[str] = None) -> str:
    """The one sentence that stops date hallucination. A model with no clock
    guessed 'this coming Sunday, July 28th' — a date in the PAST — in a live
    scheduling thread. Humans know what day it is; so does every prompt.

    Takes the owner's zone when known. Called with nothing, it behaves exactly
    as it did before.
    """
    now = datetime.now(owner_tz(tz_name))
    tomorrow = now + timedelta(days=1)
    yesterday = now - timedelta(days=1)
    # Spell out the neighbouring days too. With only "right now" given, the
    # model kept doing the weekday arithmetic itself and getting it wrong:
    # on Saturday it wrote "tomorrow (Saturday)", and on Sunday it wrote the
    # same thing again — a card that contradicts itself in five words, twice
    # in two days. Nothing here needs computing.
    return (
        now.strftime("Right now it is %A, %B %-d, %Y, %-I:%M %p %Z.")
        + tomorrow.strftime(" Tomorrow is %A, %B %-d, %Y.")
        + yesterday.strftime(" Yesterday was %A, %B %-d, %Y.")
        + " Never write a weekday next to a relative day unless it matches"
          " these; if you name a day, name the date with it."
    )


@dataclass
class LLMResult:
    text: str
    used_model: str
    mode: str  # "gemini", "openrouter", or "heuristic"


# ---------------------------------------------------------------- cost ledger
# WHERE THE MONEY GOES, per call, opt-in and off by default.
#
# Measured 2026-08-21: one ambient utterance cost 0.0082 credits, and nothing
# in the tree could say why — how many model calls one line makes, which of
# them is the expensive one, or how much of each prompt is boilerplate. A
# per-decision cost is the budget for the whole test programme, so it has to be
# attributable before it can be argued with.
#
# Set ANTICIPY_LLM_LEDGER=/path/to.jsonl to record one line per call. Unset,
# this costs a single dict lookup and touches nothing. A failure to write must
# never cost a real decision, so every error here is swallowed.
_LEDGER = os.environ.get("ANTICIPY_LLM_LEDGER", "")


def _caller() -> str:
    """The first frame outside this module — i.e. who asked for the call."""
    import traceback
    for frame in reversed(traceback.extract_stack()[:-1]):
        if not frame.filename.endswith("llm.py"):
            return f"{os.path.basename(frame.filename)}:{frame.name}"
    return "unknown"


def _record(model: str, system: str, user: str, usage: dict, mode: str) -> None:
    if not _LEDGER:
        return
    try:
        import time
        row = {
            "at": time.time(),
            "caller": _caller(),
            "model": model,
            "mode": mode,
            "system_chars": len(system),
            "user_chars": len(user),
            "prompt_tokens": (usage or {}).get("prompt_tokens"),
            "completion_tokens": (usage or {}).get("completion_tokens"),
            # Proof the cache breakpoint is actually being honoured. Zero here
            # on a big prompt means the saving is imaginary.
            "cached_tokens": ((usage or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
            "reasoning_tokens": ((usage or {}).get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "cost": (usage or {}).get("cost"),
        }
        with open(_LEDGER, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except Exception:
        pass


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: str = DEFAULT_MODEL,
                 owner_zone: Optional[str] = None,
                 owner_name: Optional[str] = None):
        # The owner's IANA zone, e.g. "America/Vancouver". None means the
        # server default clock and, since 2026-08-22, a place sentence that
        # says the location is UNKNOWN rather than one that says nothing.
        self.owner_zone = owner_zone
        # The owner's own first name, from their profile. None means the
        # prompts stay exactly as they were — there is no name to mistake for
        # somebody else's.
        self.owner_name = owner_name
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY")
        # Passing an API key explicitly preserves the historical meaning:
        # callers asking for one OpenRouter client do not silently use an
        # unrelated process credential instead.
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self.model = model
        self.gemini_model = os.environ.get("ANTICIPY_GEMINI_MODEL", "gemini-2.5-flash")

    @property
    def live(self) -> bool:
        return bool(self.gemini_api_key or self.api_key)

    def chat(self, system: str, user: str, temperature: float = 0.1,
             aux: bool = False) -> LLMResult:
        """`aux=True` marks a MECHANICAL call — extraction or comparison, never
        a judgement about whether to act, what is consequential, or what the
        owner will read. Those callers may be served by ANTICIPY_AUX_MODEL when
        one is configured; every other call site is unaffected."""
        # Grounded at the client so EVERY caller — triage, replies, voice,
        # briefings, the clock — knows the current local date and time, and
        # WHERE the owner is. One place to set it means no caller can forget.
        #
        # `owner_zone` is set from the owner's own profile, reported by their
        # phone. Unset, the clock falls back to the server default and the
        # place sentence tells the model it does not know where they are.
        #
        # THE GROUNDING NOW GOES LAST, and that is a cost decision, not a
        # stylistic one. It used to be PREPENDED, which put a sentence
        # containing the current minute in front of a 3,090-token system prompt
        # that never changes. A prompt cache is keyed on an exact PREFIX, so a
        # clock at the front means every single call is a cache miss forever.
        #
        # Measured 2026-08-21 on the triage prompt: no caching 0.001041 a call,
        # cached 0.000206 — five times cheaper for the identical request, with
        # 3,076 of 3,173 input tokens served from cache. Moving one sentence
        # from the top to the bottom is the whole difference.
        #
        # The model reads the entire system message either way. Nothing about
        # the instruction changes; only where the clock sits inside it.
        #
        # where_line() always speaks now, including when the zone is unknown —
        # a prompt silent about place got Philadelphia invented for a Pacific
        # account — so there is no empty case to guard. who_line() is the
        # opposite: it says nothing at all until a first name is known, so an
        # account without one sends byte-identical prompts to before.
        grounding = "\n".join(part for part in (who_line(self.owner_name),
                                                where_line(self.owner_zone),
                                                now_line(self.owner_zone))
                              if part)
        if self.gemini_api_key:
            # The direct Gemini path uses explicit CachedContent, not this
            # mechanism, so it keeps the original single-string shape.
            return self._gemini(f"{grounding}\n\n{system}", user, temperature)
        if self.live:
            return self._openrouter(system, user, temperature, grounding,
                                    model=(AUX_MODEL if (aux and AUX_MODEL) else self.model))
        return LLMResult(text=self._heuristic(system, user), used_model="heuristic", mode="heuristic")

    def _gemini(self, system: str, user: str, temperature: float) -> LLMResult:
        """Call Gemini directly without exposing its credential downstream."""
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": temperature,
                # Anticipy's model replies are deliberately short structured
                # judgments. A hard bound prevents surprise cost and latency.
                "maxOutputTokens": 2048,
                # Gemini 2.5 Flash otherwise defaults to dynamic thinking,
                # whose private tokens consume the same output allowance and
                # can truncate a tiny JSON judgment mid-key.
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        headers = {
            "x-goog-api-key": self.gemini_api_key,
            "Content-Type": "application/json",
        }
        url = GEMINI_URL.format(model=self.gemini_model)
        with httpx.Client(timeout=60) as c:
            r = c.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
        if not text:
            raise ValueError("Gemini returned no text")
        _record(self.gemini_model, system, user,
                (data.get("usageMetadata") or {}), "gemini")
        return LLMResult(text=text, used_model=self.gemini_model, mode="gemini")

    # A prompt cache only pays for itself above a provider minimum (Gemini
    # wants roughly a thousand tokens). Below that the multipart shape is pure
    # overhead and some providers reject the annotation outright, so the small
    # calls — memory extraction at 278 tokens, sufficiency at 420 — keep the
    # plain string they have always sent. Four chars to a token, conservatively.
    CACHE_MIN_CHARS = 4200

    def _openrouter(self, system: str, user: str, temperature: float = 0.1,
                    grounding: str = "", model: str = "") -> LLMResult:
        model = model or self.model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "temperature": temperature,
            # Ask for the cost of the call back with the call. Without this,
            # `usage` carries token counts but no price, and attributing spend
            # then means reconciling against the account ledger by hand.
            "usage": {"include": True},
            # A fixed seed (passed through to providers that honour it) so a
            # classification is a function of its words, not of which replica
            # served the request. Judgment being a coin flip across identical
            # runs is itself a bug.
            "seed": 11,
            # THE CACHE BREAKPOINT. The static instruction goes first, on its
            # own content block, marked cacheable; the clock and place follow in
            # a second block that changes every minute and is never cached.
            # Only the prefix up to the breakpoint is reused, which is exactly
            # the part that never varies.
            #
            # Providers that do not implement this ignore the annotation and
            # read the same two blocks as one message, so the request is still
            # correct — it just costs what it used to.
            "messages": [
                ({"role": "system", "content": [
                    {"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": grounding},
                ]} if (grounding and len(system) >= self.CACHE_MIN_CHARS)
                 else {"role": "system",
                       "content": f"{grounding}\n\n{system}" if grounding else system}),
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=60) as c:
            r = c.post(OPENROUTER_URL, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        _record(model, system, user, data.get("usage") or {}, "openrouter")
        return LLMResult(text=data["choices"][0]["message"]["content"],
                         used_model=model, mode="openrouter")

    # ---- deterministic fallback so we can prove the pipeline with no key ----
    def _heuristic(self, system: str, user: str) -> str:
        """A tiny rules engine that mimics the JSON the real model returns for triage."""
        text = user.lower()
        # commitments / promises -> ACT
        act_patterns = [
            (r"(send|share) (you |him |her |them |it )?(the |over the |with them )?(deck|pitch|contract|portfolio|file|proposal|link|document)", "draft_and_send_document"),
            (r"(grab|get|book|reserve) .*(dinner|lunch|table|reservation|restaurant)", "find_and_book_restaurant"),
            (r"(schedule|set up|book|put).*(meeting|call|time|thursday|monday|tomorrow|calendar)", "create_calendar_event"),
            (r"(remind me|i should|need to) (to )?(email|message|text|call|follow up)", "create_reminder_or_draft"),
            (r"(cancel|unsubscribe).*(gym|subscription|membership|plan)", "start_cancellation_flow"),
            (r"(reorder|order more|out of|running low)", "reorder_item"),
            (r"(check|find|look up|compare) .*(pric|flight|hotel|availabilit|cost)", "research_and_report"),
            (r"(reschedule|move|change) .*(appointment|clinic|doctor)", "reschedule_appointment"),
            (r"running (late|behind)|tell them i", "notify_contact"),
        ]
        for pat, goal in act_patterns:
            if re.search(pat, text):
                return json.dumps({"decision": "act", "goal": goal, "reason": f"matched intent: {goal}"})
        # questions to the user / ambiguity -> ASK
        if re.search(r"\b(should i|do you think|not sure|maybe we|what about)\b", text):
            return json.dumps({"decision": "ask", "goal": None, "reason": "ambiguous intent, confirm first"})
        # small talk / jokes -> IGNORE
        return json.dumps({"decision": "ignore", "goal": None, "reason": "no actionable commitment detected"})
