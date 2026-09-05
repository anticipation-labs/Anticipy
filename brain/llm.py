"""LLM client for Anticipy's brain.

Every credential the process holds is a TRANSPORT, and a second one is a
fallback, not a switch: they are tried in ANTICIPY_LLM_ORDER (default
"gemini,openrouter"), and when the first machine is absent the next one
carries the call — see `_transports` and `_fall_through`.
Falls back to a deterministic heuristic engine when no key is present, so the
whole pipeline is provable end-to-end without secrets. The real key only
swaps the reasoning core; the plumbing is identical.
"""
from __future__ import annotations

import json
import os
import random
import re
import time
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


# ---------------------------------------------------- transient-failure retry
# A 429 USED TO MAKE HER IGNORE A SPOKEN LINE.
#
# Both providers were called with `raise_for_status()` and no retry of any
# kind. On the decision path that exception reaches triage's handler, which
# tries once more and then files the line as "ignore" — so a rate-limit blip
# lasting one second silently discarded an errand the owner had spoken aloud.
# Nothing recorded that it happened; the line simply read as chatter.
#
# WHAT IS AND IS NOT RETRIED, because "retry on error" is how a wallet empties.
# Only transport-level transients: 429 (slow down), 5xx (their fault), and a
# timeout or connection failure. Deliberately NOT retried are the codes that
# mean the request itself is wrong or the account cannot pay — 400, 401, 403,
# 404 and especially 402. overnight/MORNING.md records the night this system
# went silent because OpenRouter credits hit 160/160 and every model returned
# 402; retrying that would have spent the same nothing three times as fast and
# made the logs harder to read, not the outcome better.
#
# This is a TRANSPORT decision, not a meaning one: it keys on an HTTP status
# and an exception type, never on anything the model said. Bounded at two
# retries so the worst case adds about two seconds to a call that already
# carries a 60-second timeout, and jittered so a fleet of workers that all
# stalled on the same provider blip do not return in lockstep.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_RETRY_ATTEMPTS = 3          # the first try plus two retries
_RETRY_BASE_SECONDS = 0.5


def _sleep_before_retry(attempt: int) -> None:
    delay = _RETRY_BASE_SECONDS * (2 ** attempt)
    time.sleep(delay * (0.75 + random.random() * 0.5))


def _post_json(url: str, headers: dict, payload: dict) -> dict:
    """POST, retrying only what is worth retrying, and say when it happened."""
    last: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            with httpx.Client(timeout=60) as c:
                r = c.post(url, headers=headers, json=payload)
            # A POSITIVE retryable status, or nothing happens. `getattr` rather
            # than attribute access because absence is not a verdict here
            # either: a response object that cannot say what its status was is
            # not evidence that the provider asked us to slow down, and
            # treating "I don't know" as "retry" is how a retry policy starts
            # hammering an endpoint it has never successfully read.
            status = getattr(r, "status_code", None)
            if status in _RETRY_STATUS and attempt + 1 < _RETRY_ATTEMPTS:
                print(f"llm: provider returned {status}, "
                      f"retry {attempt + 1}/{_RETRY_ATTEMPTS - 1}")
                _sleep_before_retry(attempt)
                continue
            r.raise_for_status()
            return r.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = exc
            if attempt + 1 >= _RETRY_ATTEMPTS:
                break
            print(f"llm: {type(exc).__name__}, "
                  f"retry {attempt + 1}/{_RETRY_ATTEMPTS - 1}")
            _sleep_before_retry(attempt)
    # Only reachable when every attempt raised a transport error: the status
    # path cannot arrive here, because the final attempt stops short-circuiting
    # and lets raise_for_status carry the provider's own error upward. An
    # earlier draft had a re-issue block here for that case and it was dead
    # code claiming to handle something — which is worse than no code, because
    # a reader trusts it.
    assert last is not None
    raise last


# ------------------------------------------ a second credential is a fallback
# BOTH KEYS SET USED TO MEAN "GEMINI, AND ONLY GEMINI".
#
# chat() was a precedence ladder: Gemini if its key existed, else OpenRouter
# if its key existed, else the heuristic. The second credential was never
# reached while the first was configured — so with both keys set, a Gemini
# 503 that survived _post_json's three attempts, a timeout, or a reply with no
# text raised straight out of chat() while a working OpenRouter key sat
# unused. On the transcript loop that is a held line, a climbing deaf streak,
# and after three lines a text saying she "cannot reach the model" — sent
# while a model she could reach idled.
#
# Now the keyed transports are ORDERED. The first is the primary, the next is
# the fallback, and the fall-through is chosen by structure only: an exception
# TYPE, a finish-reason enum, an HTTP status inside _post_json, and a clock.
# Never by the words of a reply (HARNESS-LAWS.md LAW 1) — _TRANSPORT_FAULTS
# below is the one place that distinction is load-bearing.
#
# Retry stays INSIDE a transport (_post_json: three attempts, one URL).
# Falling through is ACROSS transports and sits above it, so each wire still
# gets its bounded tries and a 402 is still never re-sent to the same
# provider.
#
# ANTICIPY_LLM_ORDER is a comma-separated list of transport names. Unset,
# empty or misspelt it is the old precedence byte for byte; unknown names are
# ignored; and any keyed transport the variable forgot is appended in default
# order, so a typo can never make a credential unreachable.
_DEFAULT_TRANSPORT_ORDER = ("gemini", "openrouter")
_TRANSPORT_ORDER = tuple(
    n.strip() for n in os.environ.get(
        "ANTICIPY_LLM_ORDER", ",".join(_DEFAULT_TRANSPORT_ORDER)).split(",")
    if n.strip())

# THE DEAD-PRIMARY MEMORY. After the primary's MACHINE fails (the types in
# _TRANSPORT_FAULTS), the next minute of calls goes straight to the fallback
# instead of paying the primary's three attempts again, and at the minute the
# primary is probed once. The owner's configured model wins back by default;
# a still-dead primary costs one discovery per minute, not one per line.
#
# Sixty seconds and a single probe are borrowed from Omi's PUSHER circuit
# breaker (research/2026-09-04-omi-architecture-extraction.md, "Degradation
# is the right shape") — the transcription socket, NOT its model gateway.
# Omi's gateway ships every lane with max_attempts 1 and an empty fallback
# list, i.e. no failover at all. The number is a sensible cooldown, not a
# gateway precedent, and the ledger must not launder it into one.
_PRIMARY_RETRY_AFTER_SECONDS = 60.0

# WHICH FAILURES MEAN THE MACHINE WAS ABSENT. Any exception from the primary
# falls through to the fallback — a reply this code cannot parse is still a
# call that produced nothing. But only a TRANSPORT-typed failure is
# REMEMBERED as "the primary is down". `_gemini` raises ValueError for a
# SAFETY or RECITATION refusal or a thoughts-only reply, and those are
# outcomes of that ONE line's content: letting them start the cooldown would
# move the next minute of every call — other lines included — onto a
# different model because of what one sentence said, with no log line saying
# so. Content never steers the wire.
#
# This is brain/worker.py `_UNREACHABLE` minus its `requests` entry, which
# the model path never raises. Keep the two aligned: the exception that
# leaves chat() when both transports fail is chosen from this tuple (rule R,
# `_raise_the_one_that_leaves`) precisely so the worker's hold-or-tombstone
# split reads it the same way.
_TRANSPORT_FAULTS = (
    httpx.HTTPError,     # status, timeout, transport — everything httpx raises
    ConnectionError,
    TimeoutError,
    OSError,             # DNS, socket, and the rest of the plumbing
)


def _raise_the_one_that_leaves(first: Exception, second: Exception) -> None:
    """RULE R: which exception leaves chat() when BOTH transports failed.

    The transport-typed one, preferring the primary's when both are, with
    the other chained on as its cause; only when NEITHER is transport-typed
    is the fallback's raised, chained from the primary's.

    A type check, and it exists so brain/worker.py's hold-or-tombstone split
    never buries a spoken line because the SECOND machine's reply was
    unparseable while the first was merely absent. Primary 503 plus a
    fallback answering 200 with an {"error": …} body is a KeyError in our
    parser, and a KeyError is a tombstone; that line WAITED before this port
    and must not DIE because of it. When neither failure is transport-typed
    the defect is ours and deterministic, and the tombstone is right —
    identical input through identical code cannot come out differently.
    """
    if isinstance(first, _TRANSPORT_FAULTS):
        raise first from second
    raise second from first


@dataclass
class LLMResult:
    text: str
    used_model: str
    mode: str  # "gemini", "openrouter", or "heuristic"
    # DID THE MODEL FINISH THE SENTENCE, or did it run out of room?
    #
    # Both providers say so and this client threw the answer away: Gemini in
    # `candidates[0].finishReason`, OpenRouter in `choices[0].finish_reason`.
    # A reply cut at the token ceiling was returned as if it were complete.
    #
    # For a JSON judgment that mostly self-corrects — the parse fails and
    # triage re-asks. For PROSE it does not: `_voice`, `_clock` and the
    # briefing compose the words that go to the owner's phone, and a
    # composition truncated mid-word was sent as-is. That is the failure Omi's
    # own ranked improvement list calls small to fix and expensive to ship
    # ("a sentence that stops mid-word as a final answer"), and it costs more
    # here than there, because the destination is a text message rather than
    # a chat bubble a person can scroll.
    #
    # A POSITIVE SIGNAL ONLY. True means the provider said it stopped early;
    # absence is NOT a verdict, and an unrecognised or missing reason leaves
    # this False rather than guessing. Same honesty wall the rest of the brain
    # uses: a check that fires when it cannot see would discard good answers
    # the first time a provider renamed a field.
    truncated: bool = False
    # WHICH WIRE WAS ASKED FIRST, when it was not the one that answered.
    #
    # "" when the primary transport answered, or there was only one. The
    # primary's NAME when the fallback carried this call. Provenance for the
    # log and the live leg, read by nobody as a verdict; `mode` stays what it
    # always was — the transport that actually answered — which is what
    # memory.py's _LIVE_EXTRACTOR_MODES keeps reading.
    fell_through_from: str = ""


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
        # The dead-primary memory: a monotonic deadline before which the
        # primary transport is skipped. 0.0 means nothing is remembered, and
        # it is only ever set by a transport-typed failure (_TRANSPORT_FAULTS).
        self._primary_down_until = 0.0
        # What carried each call, counted here and printed by the worker as
        # one `llm: gateway tally` line per tick that saw a call. Nothing
        # about a call is decided by it; it is the denominator the live leg
        # needs to tell "the primary answered 900 and the fallback 3" from
        # "the primary answered nothing and the fallback carried everything".
        self.gateway_tally = {"primary_ok": 0, "rescued": 0, "skipped": 0,
                              "reissued": 0, "both_dead": 0}

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
        transports = self._transports(system, user, temperature, grounding, aux)
        if not transports:
            return LLMResult(text=self._heuristic(system, user), used_model="heuristic", mode="heuristic")
        if len(transports) == 1:
            # ONE credential is the pre-port path, byte for byte: no try, no
            # clock, no print, no tally. There is nothing to fall through to,
            # and the exception that leaves here is the one the worker's
            # hold-or-tombstone split has always classified.
            return transports[0][1]()
        return self._fall_through(transports[0], transports[1])

    # WHAT WAS HERE UNTIL 2026-09-05 (Omi port 09b), and why it is gone.
    #
    #     if self.gemini_api_key:
    #         return self._gemini(f"{system}\n\n{grounding}", user, temperature,
    #                             model=self._gemini_model_for(aux))
    #     if self.live:
    #         return self._openrouter(system, user, temperature, grounding,
    #                                 model=(AUX_MODEL if (aux and AUX_MODEL) else self.model))
    #     return LLMResult(text=self._heuristic(system, user), used_model="heuristic", mode="heuristic")
    #
    # A precedence ladder. The presence of GEMINI_API_KEY was a provider
    # SWITCH, and OpenRouter was reachable only while that key was absent;
    # commit 4c3cf7e3 ("add billed model fallback") added the Gemini branch
    # and called it a fallback, and it was a precedence. With both keys set, a
    # Gemini failure that survived _post_json's three attempts — 429, 5xx, a
    # timeout, a refused connection — or a reply with no text raised straight
    # out of chat() (raise_for_status, `raise last`, "Gemini returned no
    # text") while a working OpenRouter credential idled. The worker held the
    # line, the deaf streak climbed, and after three lines the owner was told
    # she "cannot reach the model". The empty-reply case was worse: ValueError
    # is not on the worker's _UNREACHABLE list, so that spoken line was
    # tombstoned with no retry. Replaced by _transports (which wires exist, in
    # which order) and _fall_through (which one answers — by exception type,
    # finish reason and clock, never by what a reply said).

    def _transports(self, system: str, user: str, temperature: float,
                    grounding: str, aux: bool) -> list:
        """Every credential this process holds, as (name, thunk) pairs in
        the order they are to be tried. A thunk is one complete call on that
        wire, and it is aux-aware on BOTH transports: a mechanical call that
        falls through still lands on the fallback's aux model, and a
        judgement call never lands on an aux model on any wire — the split
        ANTICIPY_AUX_MODEL draws does not move when the wire does.

        Configuration only. A credential is present or it is not, and
        ANTICIPY_LLM_ORDER is a string; nothing here has seen a reply.
        """
        wires: dict = {}
        if self.gemini_api_key:
            # THE GROUNDING GOES LAST HERE TOO, for the identical reason
            # spelled out above: a prompt cache is keyed on an exact PREFIX,
            # so a sentence carrying the current minute in FRONT of a
            # 3,090-token instruction misses on every call, forever. This
            # path prepended it until 2026-08-24 while claiming in a comment
            # that it used "explicit CachedContent" instead. There is no
            # CachedContent call anywhere in brain/ and never has been, so
            # that comment excused a live regression instead of describing a
            # mechanism — which is why the measured saving above was real on
            # OpenRouter and imaginary here.
            #
            # aux is honoured here too. Before this, ANTICIPY_AUX_MODEL was
            # silently unreachable whenever GEMINI_API_KEY was set, because
            # this branch returns before the aux-aware one below it: every
            # mechanical call paid the judgement model's rate and nothing
            # said so.
            wires["gemini"] = lambda: self._gemini(
                f"{system}\n\n{grounding}", user, temperature,
                model=self._gemini_model_for(aux))
        if self.api_key:
            wires["openrouter"] = lambda: self._openrouter(
                system, user, temperature, grounding,
                model=(AUX_MODEL if (aux and AUX_MODEL) else self.model))
        ordered: list = []
        for name in (*_TRANSPORT_ORDER, *_DEFAULT_TRANSPORT_ORDER):
            if name in wires and name not in ordered:
                ordered.append(name)
        return [(name, wires[name]) for name in ordered]

    def transport_names(self) -> list:
        """The wires in order, by name — for the worker's boot banner."""
        return [name for name, _ in self._transports("", "", 0.0, "", False)]

    def _fall_through(self, primary: tuple, secondary: tuple) -> LLMResult:
        """Two wires: the first that answers, chosen by structure only.

        POLARITY, decided here and nowhere else. Primary raised, fallback
        answered: the line is judged and the owner hears nothing about it,
        because she CAN hear — a broken primary is an ops signal and goes to
        the log, the banner and the live leg, not to his phone. Both dead:
        the exception that leaves is chosen by TYPE (rule R) so the worker
        holds a line whose machines were absent and tombstones one that our
        own code broke, exactly as it did with one wire. Cooldown running and
        the fallback dies: forget the cooldown and probe the primary in the
        SAME call — the safe side is "forget what you knew when both are
        down", never "wait out a minute with both known dead". Truncated
        primary and dead fallback: return the primary's reply with its flag
        intact — an honest flag beats no answer, and every consumer already
        handles the flag. Truncation never starts the cooldown: the primary
        answered.
        """
        pname, first_wire = primary
        sname, second_wire = secondary
        tally = self.gateway_tally
        if time.monotonic() < self._primary_down_until:
            # The primary's machine was absent inside the last minute. Skip
            # it — silently; the tally carries the count — and if the
            # fallback now dies too, drop the memory and probe the primary
            # right here rather than raising with one wire untried.
            tally["skipped"] += 1
            try:
                res = second_wire()
            except Exception as second:
                self._primary_down_until = 0.0
                print(f"llm: gateway {sname} {type(second).__name__} during "
                      f"{pname} cooldown -> probing {pname}")
                try:
                    res = first_wire()
                except Exception as first:
                    tally["both_dead"] += 1
                    print(f"llm: gateway {pname} {type(first).__name__} too "
                          f"— no transport answered")
                    _raise_the_one_that_leaves(first, second)
                tally["primary_ok"] += 1
                print(f"llm: gateway {pname} answered the probe")
                return res
            res.fell_through_from = pname
            tally["rescued"] += 1
            return res
        try:
            res = first_wire()
        except Exception as first:
            # Anything falls through. Only a machine-absent failure is
            # REMEMBERED; a ValueError for an empty reply, or our own parse
            # error, is rescued and forgotten — content never steers the wire.
            if isinstance(first, _TRANSPORT_FAULTS):
                self._primary_down_until = (time.monotonic()
                                            + _PRIMARY_RETRY_AFTER_SECONDS)
            print(f"llm: gateway {pname} {type(first).__name__} -> trying {sname}")
            try:
                res = second_wire()
            except Exception as second:
                tally["both_dead"] += 1
                print(f"llm: gateway {sname} {type(second).__name__} too "
                      f"— no transport answered")
                _raise_the_one_that_leaves(first, second)
            res.fell_through_from = pname
            tally["rescued"] += 1
            print(f"llm: gateway {sname} answered for {pname}")
            return res
        if res.truncated:
            # The provider's own finish-reason enum says it ran out of room.
            # One bounded re-issue on the other wire; if that dies, the
            # primary's flagged reply stands and the caller's existing
            # handling (template speaks, triage re-asks) takes it from here.
            print(f"llm: gateway {pname} truncated -> reissuing on {sname}")
            try:
                again = second_wire()
            except Exception:
                # Counted as the primary's call, because that is whose reply
                # goes back: the tally says which wire CARRIED it, and the
                # `truncated -> reissuing` line above says why it was tried.
                tally["primary_ok"] += 1
                return res
            again.fell_through_from = pname
            tally["reissued"] += 1
            print(f"llm: gateway {sname} answered for {pname} (truncation)")
            return again
        tally["primary_ok"] += 1
        return res

    def _gemini_model_for(self, aux: bool) -> str:
        """Which Gemini model serves this call.

        ANTICIPY_AUX_MODEL is written as an OpenRouter slug
        ("google/gemini-2.5-flash-lite") because that is the path it was
        measured on, while the direct endpoint wants the bare id. That
        endpoint also serves Google models only, so a slug naming any other
        vendor is not something this path can honour: fall back to the main
        model rather than send a name that 404s a real decision.
        """
        if not (aux and AUX_MODEL):
            return self.gemini_model
        vendor, _, bare = AUX_MODEL.rpartition("/")
        if vendor and vendor.lower() != "google":
            return self.gemini_model
        return bare or self.gemini_model

    def _gemini(self, system: str, user: str, temperature: float,
                model: str = "") -> LLMResult:
        """Call Gemini directly without exposing its credential downstream."""
        model = model or self.gemini_model
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
        url = GEMINI_URL.format(model=model)
        data = _post_json(url, headers, payload)
        candidate = (data.get("candidates") or [{}])[0]
        parts = ((candidate.get("content") or {}).get("parts") or [])
        text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
        if not text:
            raise ValueError("Gemini returned no text")
        _record(model, system, user,
                (data.get("usageMetadata") or {}), "gemini")
        # MAX_TOKENS is the one reason that means "there was more to say".
        # SAFETY and RECITATION are refusals, not truncations, and are left to
        # the caller's own emptiness handling rather than relabelled here.
        return LLMResult(
            text=text, used_model=model, mode="gemini",
            truncated=str(candidate.get("finishReason") or "") == "MAX_TOKENS")

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
        data = _post_json(OPENROUTER_URL, headers, payload)
        _record(model, system, user, data.get("usage") or {}, "openrouter")
        choice = data["choices"][0]
        # OpenAI-compatible providers spell the same thing "length".
        return LLMResult(text=choice["message"]["content"],
                         used_model=model, mode="openrouter",
                         truncated=str(choice.get("finish_reason") or "") == "length")

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
