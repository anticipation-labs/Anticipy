"""Anticipy brain worker — the server-side mind loop.

The phone posts raw transcript lines to PocketBase (`events`, kind
"transcript"). This worker is the one place they all flow through:
each line -> Anticipy.hear() -> memory graph + triage + (held) job, then the
decision and anything Anticipy wants to say are written back as events the
app renders in its feed. It also closes loops as jobs finish.

Run:  .venv/bin/python -m brain.worker
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import time
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone

import requests

from . import pb
from . import research

from .anticipy_core import Anticipy, goal_tokens
from .memory import Memory
from .segmenter import SegmentStore, place_turn
from .conversation import Conversation, MockTransport, TwilioTransport
from .llm import LLM, TZ as TZ_FALLBACK
from .voice_arm import VoiceArm, has_credentials, rest_credential
from .workflow import (claim as claim_plan, fail as fail_plan,
                       from_params as workflow_from_params,
                       put_in_params, recover_expired as recover_expired_plan,
                       succeed as succeed_plan)

PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
POLL_SECONDS = 2

# Every production worker process is bound to exactly one account.  Keeping
# this context process-local is deliberate: Memory, Conversation, the clock,
# and the model's owner timezone all contain mutable state and therefore must
# never be shared between people.
ACTIVE_OWNER_REF = os.environ.get("ANTICIPY_OWNER_REF", "").strip()
ACTIVE_OWNER_ID = os.environ.get("ANTICIPY_OWNER_ID", "").strip()

# ---- the clock: time-fired proactivity, with guardrails OUTSIDE the model
CLOCK_EVERY_SECONDS = 30 * 60
CLOCK_MIN_GAP_SECONDS = 4 * 3600      # at most one unprompted outreach per 4h
CLOCK_TZ = ZoneInfo(os.environ.get("ANTICIPY_TZ", "America/Vancouver"))
CLOCK_QUIET_START, CLOCK_QUIET_END = 22, 8   # never initiate at night
CLOCK_STATE = os.environ.get("ANTICIPY_CLOCK_STATE", "/data/clock_state.json")

# ---- nightly memory consolidation (roadmap §1): while he sleeps, distill the
# day's episodes into profile facts. Once a night, inside the clock's quiet
# hours; the cursor and last-run stamp live in the memory DB itself, so a
# redeploy resumes instead of repeating.
CONSOLIDATE_MIN_GAP_SECONDS = 20 * 3600
CONSOLIDATE_MAX_BATCHES = 10          # bounds one night's model spend
CONSOLIDATE_RETRY_SECONDS = 30 * 60   # a failing model retries gently, not per tick


def owner_filter(anticipy) -> str:
    """Canonical account scope for every worker-side collection query."""
    owner_ref = str(getattr(anticipy, "owner_ref", "") or "").strip()
    if owner_ref:
        return f'owner_ref="{owner_ref}"'
    owner_id = str(getattr(anticipy, "owner_id", "") or "").strip()
    return f'owner="{owner_id}"' if owner_id else ""


def _escaped(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _active_owner_ref(owner_ref: str = "") -> str:
    return str(owner_ref or ACTIVE_OWNER_REF or "").strip()


def _scoped_filter(base: str, owner_ref: str = "") -> str:
    """Narrow a collection query to this process' account.

    Unit tests for pre-account behaviour intentionally run with no active
    owner, so an empty context preserves their local fake-query semantics.
    `main()` itself refuses to poll without a canonical owner, which makes the
    production path fail closed.
    """
    ref = _active_owner_ref(owner_ref)
    scope = f'owner_ref="{_escaped(ref)}"' if ref else ""
    if base and scope:
        return f"({base}) && {scope}"
    return scope or base


def _latest_profile(owner_ref: str = "") -> dict | None:
    ref = _active_owner_ref(owner_ref)
    params = {"sort": "-updated", "perPage": 1}
    if ref:
        params["filter"] = _scoped_filter("", ref)
    r = pb.get(
        f"{PB}/api/collections/owner_profile/records",
        params=params,
        timeout=10,
    )
    if not r.ok:
        return None
    items = r.json().get("items", [])
    return items[0] if items else None


def run_nightly_consolidation(memory, now: float | None = None) -> None:
    """Distill the day into the profile layer (memory.consolidate).

    Guardrails live HERE, outside the model, like the clock's: only during
    quiet hours, at most once per night, bounded batches. With no live LLM
    the pass is skipped outright — the profile stays empty, nothing crashes,
    and hearing is never touched."""
    try:
        if getattr(memory, "llm", None) is None:
            return
        now = now if now is not None else time.time()
        hour = datetime.fromtimestamp(now, CLOCK_TZ).hour
        if not (CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END):
            return          # daytime belongs to hearing
        if now - memory.last_consolidation_ts() < CONSOLIDATE_MIN_GAP_SECONDS:
            return          # already ran tonight
        # Only a SUCCESSFUL pass stamps last_run_ts, and this runs on every
        # poll tick — so without an attempt gap, one flaky night means a
        # model call every two seconds until dawn.
        if now - getattr(memory, "_nightly_attempt_ts", 0.0) < CONSOLIDATE_RETRY_SECONDS:
            return
        memory._nightly_attempt_ts = now
        totals = {"episodes": 0, "new": 0, "merged": 0}
        for _ in range(CONSOLIDATE_MAX_BATCHES):
            out = memory.consolidate(now=now)
            if not out.get("ran"):
                print(f"consolidation: pass skipped ({out.get('reason', '?')})")
                break
            for k in totals:
                totals[k] += out.get(k, 0)
            if not out.get("remaining"):
                break
        print(f"consolidation: {totals['episodes']} episodes -> "
              f"{totals['new']} new facts, {totals['merged']} merged")
    except Exception as e:
        # This must never be able to take hearing down with it.
        print(f"consolidation failed (harmless): {e}")


def fetch_owner_phone(owner_ref: str = "") -> str | None:
    """The owner's number as THEY entered it in the app. Falls back to the
    env var so an existing deployment keeps working, but the app is now the
    source of truth — nobody should have to hand-edit a server variable to
    make their own assistant able to text them."""
    try:
        profile = _latest_profile(owner_ref)
        phone = (profile.get("phone") or "").strip() if profile else ""
        if phone:
            return phone
    except Exception:
        pass
    # The profile is not the only place a number lives: signup writes it onto
    # the ACCOUNT. His own profile row carried an empty phone while three
    # legacy rows (owner_ref "") held the real number, so once supervised
    # workers correctly stopped inheriting the founder's env var, she could
    # not text him AT ALL — she composed the questions, recorded them, and
    # sent nothing, for ten hours (2026-08-16).
    #
    # This fallback is ACCOUNT-BOUND: it reads the phone belonging to THIS
    # owner_ref only, so it cannot resurrect the cross-account leak.
    if not owner_ref:
        return None
    try:
        r = pb.get(f"{PB}/api/collections/owners/records/{owner_ref}", timeout=10)
        if getattr(r, "ok", False):
            phone = ((r.json() or {}).get("phone") or "").strip()
            if phone:
                print("owner phone read from the account record "
                      "(their profile row carries none)")
                return phone
    except Exception:
        pass
    return None


def fetch_owner_timezone(owner_ref: str = "") -> str | None:
    """The owner's own IANA zone, as their phone reported it.

    Before this, the zone was one server-wide env var, so every prompt was
    grounded in Vancouver's time of day whoever was speaking, and the quiet
    hours that stop her texting at night were somebody else's night. It also
    means she finally knows the CITY — an identifier like America/Vancouver
    carries both, and costs the user no permission prompt and no typing.

    None when unknown, which restores the old behaviour exactly.
    """
    try:
        profile = _latest_profile(owner_ref)
        tz = (profile.get("timezone") or "").strip() if profile else ""
        return tz or None
    except Exception:
        return None


def fetch_owner_first_name(owner_ref: str = "") -> str | None:
    """The owner's own first name, so every prompt knows the person it is
    writing TO — not just the person it is writing about.

    Same beat and same shape as the zone above, for the same reason: this is a
    profile column the app already collects, and llm.who_line() needs it to
    stop the composer using the owner's own name as a third-person subject in
    a text addressed to him ("what pharmacy does he use?", sent to him).

    None when unknown, which leaves every prompt exactly as it was.
    """
    try:
        profile = _latest_profile(owner_ref)
        first = (profile.get("first_name") or "").strip() if profile else ""
        return first or None
    except Exception:
        return None


def maybe_welcome_new_owner(anticipy, state: dict, now: float | None = None) -> bool:
    """Day zero's first proactive touch: the moment a BRAND-NEW owner saves
    their number, she says hello — once, ever, per number.

    Guardrails outside any model:
      - only when the owner_profile record itself is young (a fresh
        onboarding), so a long-standing owner editing their settings is
        never suddenly 'welcomed';
      - one durable stamp per number in the clock state file, so a redeploy
        can never re-send it.
    Returns True when a welcome actually went out."""
    now = now if now is not None else time.time()
    phone = anticipy.owner_phone
    if not phone:
        return False
    digits = "".join(ch for ch in phone if ch.isdigit())[-10:]
    if not digits or digits in state.get("welcomed_phones", []):
        return False
    try:
        profile = _latest_profile(getattr(anticipy, "owner_ref", ""))
        items = [profile] if profile else []
        created = (profile.get("created") or "") if profile else ""
        ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() \
            if created else 0
    except Exception:
        return False
    if not ts or now - ts > 3600:
        # An old profile only means the stamp file was lost — mark it so the
        # check never runs again, but say nothing.
        state.setdefault("welcomed_phones", []).append(digits)
        _save_clock_state(state)
        return False
    first = (items[0].get("first_name") or "").strip()
    said = anticipy._voice({
        "situation": "their very first minutes with you — they just finished "
                     "onboarding and saved their number; introduce yourself "
                     "warmly in one or two short sentences",
        "their_name": first or "unknown",
        "what_you_do": "you listen through the day, remember what matters, "
                       "and handle errands — always asking before anything "
                       "consequential goes out",
    }) or (f"Hey{' ' + first if first else ''} — I'm here. I listen, remember "
           "what matters, and handle things; I'll always ask before anything "
           "real goes out. Text me anytime.")
    if not anticipy.notify_owner(said):
        return False
    state.setdefault("welcomed_phones", []).append(digits)
    _save_clock_state(state)
    post_event("anticipy_says", said, decision="welcome", goal="",
               owner_ref=getattr(anticipy, "owner_ref", ""),
               owner_id=getattr(anticipy, "owner_id", ""))
    print(f"welcomed new owner …{digits[-4:]}")
    return True


_PROFILE_SEEN: dict[str, str] = {}


def seed_profile_identity(memory, _seen=None, owner_ref: str = "") -> None:
    """Day zero: what he TOLD her at onboarding (name, email) becomes profile
    knowledge the moment the worker sees it — she must never have to overhear
    her own owner's name. Idempotent: remember_fact merges restatements, and
    the seen-cache keeps the poll from re-writing unchanged values."""
    try:
        seen = _PROFILE_SEEN if _seen is None else _seen
        p = _latest_profile(owner_ref)
        if not p:
            return
        first = (p.get("first_name") or "").strip()
        last = (p.get("last_name") or "").strip()
        email = (p.get("email") or "").strip()
        name = " ".join(x for x in (first, last) if x)
        for key, fact in (("name", f"Their name is {name}." if name else ""),
                          ("email", f"Their email is {email}." if email else "")):
            if fact and seen.get(key) != fact:
                memory.remember_fact(fact, importance=5, source="interview")
                seen[key] = fact
                print(f"profile seeded from onboarding: {key}")
    except Exception as e:
        print(f"profile identity seed failed (harmless): {e}")


def ingest_profile_events(memory, owner_ref: str = "") -> int:
    """Day zero, part two: the facts the PHONE read off its own calendar and
    address book.

    These arrive as `kind="profile"` events rather than transcripts, and that
    distinction is the whole reason this function exists. A transcript goes
    through hear() and gets triaged, so "Dinner with Priya, Thursday 7:30pm"
    posted as a transcript could mint an errand — she would try to BOOK the
    dinner that is already booked. A profile event is something she should
    KNOW, never something she should start doing, so it goes straight to
    memory and never near the job miner.

    Importance 4, not 5: identity (a name, an email) outranks a diary entry,
    and recall sorts on importance. Source "import" is already in the schema's
    enum alongside "interview" and "consolidation" (brain/memory.py:64-65), so
    provenance survives without a migration.

    Idempotent by two mechanisms, because the poll runs every couple of
    seconds: the event is marked processed the moment it lands, and
    remember_fact merges restatements anyway — so the same event replayed after
    a crash cannot double up.

    Returns how many facts were written. Failures are swallowed the way
    seed_profile_identity swallows them: seeding must never take hearing down.
    """
    written = 0
    try:
        for event in fetch_unprocessed(kind="profile", owner_ref=owner_ref):
            text = (event.get("text") or "").strip()
            if not text:
                mark_processed(event.get("id", ""), "ignore")
                continue
            # PROVENANCE COMES FROM THE EVENT, not from this line.
            #
            # This used to hard-code source="import" for every profile event,
            # and "import" is not a neutral label — anticipy_core.py's
            # _UNTRUSTED_SOURCES marks it as attacker-controlled. So the six
            # answers a person typed with their own thumbs were quarantined
            # exactly like a meeting title a stranger put on their calendar:
            # "They asked me never to touch: anything to do with my bank" was
            # fenced as quoted hostile text instead of obeyed, could never
            # settle a plan value, and the briefing attributed the owner's own
            # words to their calendar.
            #
            # Anything unrecognised falls back to "import", so the failure mode
            # is over-fencing rather than trusting text nobody vouched for.
            claimed = (event.get("source") or "").strip()
            source = claimed if claimed in ("interview", "import") else "import"
            # Importance rides on the event too, because the questions are not
            # equal: a boundary ("never touch my bank") must outrank the thing
            # it is a boundary on, and recall is ranked on importance x recency.
            # A missing or absurd value degrades to 4, which is what every
            # calendar and contacts import is.
            try:
                importance = int(event.get("importance") or 4)
            except (TypeError, ValueError):
                importance = 4
            importance = min(5, max(1, importance))
            memory.remember_fact(text, importance=importance, source=source)
            # Mark before counting: an unmarked event is replayed by the next
            # poll, which is the one failure mode that turns a seed into a
            # flood.
            mark_processed(event.get("id", ""), "ignore")
            written += 1
            print(f"profile fact via {source} (importance {importance}): {text[:60]}")
    except Exception as e:
        print(f"profile import failed (harmless): {e}")
    return written


# The two source tags a supervised read may claim. An ALLOW-LIST, not a
# validation: both are in anticipy_core._UNTRUSTED_SOURCES, so anything
# unrecognised degrading to the first of them over-fences rather than letting
# a mangled or invented tag arrive as trusted text. `params.source` on the job
# is "mail" / "professional"; these are what the derived FACT is labelled.
_READ_SOURCES = ("supervised_mail", "supervised_professional")

# design/day-zero.md §3, and it is a hard ceiling rather than a default:
# "importance 5 is reserved for boundaries the owner stated in their own words"
# ("never touch anything to do with my bank"). Recall ranks on importance x
# recency and a briefing takes the top ten, so a fact NOBODY TYPED outranking
# one they did is not a cosmetic ordering bug — it is her leading with a
# stranger's subject line over the owner's own instruction.
READ_FACT_MAX_IMPORTANCE = 4

# HOW MANY FACTS ONE SUPERVISED READ MAY EVER CONTRIBUTE. Matches
# `extension/supervised_read.js` FACT_CEILING (15), which is design/day-zero.md
# §3's "5–15 facts per source" — and that is the point: the number is the
# client's own stated bound, enforced somewhere the client cannot reach.
#
# A CLIENT-SIDE CAP IS NOT A CAP. The extension counts its own facts and stops;
# a build with a broken counter, a replayed event stream, or anything that is
# not the extension posts as many `read_fact` events as it likes, and every one
# of them lands in the profile. This is the last deterministic gate before the
# row exists (CLAUDE-ONBOARDING.md:19-20 — safety gates in code).
#
# It does not, and cannot, fix ranking: 15 honest facts still out-rank the
# owner's older answers on `salience = importance x recency`. That is fixed
# where the window is taken (`memory._provenance_window`). This bounds VOLUME,
# which matters on its own because recall here is FTS5 keyword matching with no
# embeddings (brain/memory.py:9) — fifty facts do not make her smarter, they
# bury the ten that matter.
READ_FACTS_PER_JOB = 15


def ingest_read_facts(memory, owner_ref: str = "") -> int:
    """Day zero, part three: what a SUPERVISED READ concluded.

    The extension distils 5-15 facts per source and posts each as its own
    `kind="read_fact"` event (design/day-zero.md §3). Only the conclusion
    travels — never the page slice, never a subject line verbatim, never a
    message body — which is design/LOCAL-FIRST.md:9-11 held at the transport,
    and it is why this reads `text` and nothing else off the event.

    Same reason as `ingest_profile_events` for not going through hear(): a
    distilled fact is something she should KNOW, and a transcript would be
    triaged and could mint an errand off somebody else's mail.

    Returns how many facts were written. A fact past `READ_FACTS_PER_JOB` is
    REFUSED and recorded as such on the event, never counted. Failures are
    swallowed exactly as the other two seeders swallow them: day zero must
    never take hearing down.
    """
    written = 0
    try:
        # VETOES FIRST, within the same poll. If the owner has already tapped
        # a fact away, processing the facts first would write it and delete it
        # a moment later — a window in which recall can see it, and a needless
        # write to a store the veto exists to keep clean.
        ingest_read_vetoes(memory, owner_ref=owner_ref)
        for event in fetch_unprocessed(kind="read_fact", owner_ref=owner_ref):
            text = (event.get("text") or "").strip()
            if not text:
                # Skips record nothing; never an empty fact.
                # (design/briefs/08-day-zero.md:30)
                mark_processed(event.get("id", ""), "ignore")
                continue
            # THE PER-JOB CEILING, checked before anything is written. `goal`
            # is the supervised_read job this fact came off — the backend
            # refuses a read_fact whose goal does not name a live job of this
            # owner (extension/background.js:1016) — so it is the unit a read
            # is bounded in. An event arriving with no job is not exempted; it
            # shares one bucket, because a fact that cannot be attributed to a
            # read is the last thing that should get an unbounded allowance.
            job = (event.get("goal") or "").strip() or "unattributed"
            if memory.read_facts_admitted(job) >= READ_FACTS_PER_JOB:
                # A RECORDED REFUSAL, not a silent drop. The decision lands on
                # the event row, so an overflowing read is visible in the data
                # and not only in a log line nobody is tailing — and the mark
                # is what stops the 2s poll replaying this event forever.
                mark_processed(event.get("id", ""), "refused_read_fact_ceiling")
                print(f"read fact REFUSED: job {job} is already at its ceiling "
                      f"of {READ_FACTS_PER_JOB} facts — {text[:60]}")
                continue
            # PROVENANCE FROM THE EVENT, defaulting to the fenced mail tag.
            # It has to land in remember_fact, because `source` is the ONLY
            # thing that makes the fence apply downstream: every prompt sink
            # asks whether this string is in _UNTRUSTED_SOURCES, and a fact
            # that arrives labelled "interview" is read as the owner's own
            # words for the rest of its life.
            claimed = (event.get("source") or "").strip()
            source = claimed if claimed in _READ_SOURCES else _READ_SOURCES[0]
            # 3, matching `DEFAULT_READ_IMPORTANCE` in
            # extension/supervised_read.js, which is what the emitter puts on
            # a fact whose importance the model did not state. A missing value
            # here means the field never arrived at all, and a fact whose
            # importance is unknown must not outrank one whose importance was
            # actually judged — so the fallback is the lower of the two halves,
            # not the design note's worked example of 4.
            try:
                importance = int(event.get("importance") or 3)
            except (TypeError, ValueError):
                importance = 3
            # Clamped, not trusted. The ceiling is enforced HERE rather than on
            # the phone or in the extension because this is the last
            # deterministic gate before the row exists, and
            # CLAUDE-ONBOARDING.md:19-20 puts safety gates in code — a model
            # asked to pick an importance is not a gate.
            importance = min(READ_FACT_MAX_IMPORTANCE, max(1, importance))
            landed = memory.remember_fact(text, importance=importance,
                                          source=source)
            if landed:
                # Only a row that exists counts against the ceiling. A vetoed
                # fact wrote nothing, so it floods nothing — charging it would
                # let a veto quietly spend the read's allowance.
                memory.note_read_fact_admitted(job)
            # Mark before counting, exactly like the profile loop: an unmarked
            # event is replayed by the next poll, which is the one failure mode
            # that turns a read into a flood.
            mark_processed(event.get("id", ""), "ignore")
            written += 1
            print(f"read fact via {source} (importance {importance}): {text[:60]}")
    except Exception as e:
        print(f"supervised read ingest failed (harmless): {e}")
    return written


def ingest_read_vetoes(memory, owner_ref: str = "") -> int:
    """The other half of the tap. design/day-zero.md §3: "Every fact is
    vetoable. A tap deletes it and marks it never-re-derive."

    `kind="read_veto"` carries the vetoed fact text and nothing else.
    memory.forget_fact() does both halves — delete the row, record the veto —
    because deleting alone means the next read of the same inbox derives the
    same fact and hands it back, which reads as her ignoring him.

    The vetoed text NEVER reaches a prompt: it goes into vetoed_facts and is
    only ever compared against. That matters because a veto's text came off a
    read like any other, so it is attacker-influenced — it just has no sink.

    Returns how many veto events were applied (not rows deleted: a veto that
    deleted nothing still has to stick, so the count that matters is vetoes).
    """
    applied = 0
    try:
        for event in fetch_unprocessed(kind="read_veto", owner_ref=owner_ref):
            text = (event.get("text") or "").strip()
            if not text:
                mark_processed(event.get("id", ""), "ignore")
                continue
            # The veto carries the provenance of the thing being vetoed, so a
            # read cannot delete what the owner told us. Absent source reads as
            # trusted, which is right: the only other caller is the owner.
            removed = memory.forget_fact(
                text, source=str(event.get("source") or ""))
            # Mark before counting, same reason as everywhere else in this file.
            mark_processed(event.get("id", ""), "ignore")
            applied += 1
            print(f"read fact vetoed ({removed} row(s) deleted, never "
                  f"re-derive): {text[:60]}")
    except Exception as e:
        print(f"veto failed (harmless, the fact stays): {e}")
    return applied


def same_phone(a: str, b: str) -> bool:
    """E.164 comparison tolerant of formatting. Empty owner phone never
    matches — an unconfigured owner must not authorize the whole world."""
    digits = lambda s: "".join(ch for ch in str(s or "") if ch.isdigit())
    da, db = digits(a), digits(b)
    if not da or not db or len(db) < 7:
        return False
    return da[-10:] == db[-10:]


def _clock_state() -> dict:
    try:
        return json.load(open(CLOCK_STATE))
    except Exception:
        return {"last_outreach_ts": 0, "reached_loop_ids": []}


def _save_clock_state(state: dict) -> None:
    try:
        json.dump(state, open(CLOCK_STATE, "w"))
    except Exception:
        pass


def clock_should_run(now: float, state: dict) -> bool:
    hour = datetime.fromtimestamp(now, CLOCK_TZ).hour
    if CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END:
        return False
    return now - state.get("last_outreach_ts", 0) >= CLOCK_MIN_GAP_SECONDS


# ---- the number must keep pointing at US -------------------------------
# On 2026-08-03 the Twilio number's inbound webhook was pointing at
# https://anticipy-nick-demo.vercel.app/api/sms/inbound — a Vercel deployment
# that is NOT on the owner's account. Every text he sent went there instead of
# here for about a day: he texted "Book it" about a real dinner booking, a
# stranger's app answered him about an IANA example page, and the held job sat
# waiting for a yes that was being delivered somewhere else. From his side the
# product had simply gone mad.
#
# Nothing in this repo did that, and it is not something he should have to
# notice. So the brain checks its own ear: if the number stops pointing here,
# say so loudly and point it back.
WEBHOOK_CHECK_EVERY_SECONDS = 10 * 60
WEBHOOK_PATH = "/sms/inbound"


def reachable_by_twilio(url: str) -> str:
    """Empty if Twilio can reach this URL, else why it cannot.

    A LOCAL RIG MUST NOT BE ABLE TO BREAK HIS REAL PHONE NUMBER.

    `ensure_inbound_webhook` rewrites the inbound binding of a LIVE Twilio
    number. Run once on a laptop with the production credentials in the
    environment — which is exactly what inheriting a shell's exports does — and
    it pointed +1 619 658 4447 at http://127.0.0.1:8090/sms/inbound (observed
    2026-08-19). Twilio cannot reach a loopback address, so every text he sent
    would have been dropped on the floor, and the only signal was one line of
    stdout on the laptop.

    Twilio has to be able to REACH the URL for the write to be an improvement,
    so a URL it demonstrably cannot reach is never an improvement. HTTPS-only
    for the same reason the token used to ride in the query: the signature is
    computed over the exact URL Twilio requests.
    """
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if not host:
        return "it names no host"
    if (host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
            or host.endswith(".local")
            or host.startswith(("10.", "192.168.", "169.254."))
            or re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host) is not None):
        return f"{host} is only routable from this machine"
    if parsed.scheme != "https":
        return f"{parsed.scheme or 'no scheme'} is not https"
    return ""


def webhook_target() -> tuple[str, str]:
    """THE one URL the owner's number must point at, or ("", why not).

    THE SINGLE CORRECT VALUE is the public https origin of the PocketBase
    service plus /sms/inbound — that service is the one serving the route
    (backend/pb_hooks/sms.pb.js), and the hook authenticates whatever URL
    Twilio actually requested. ANTICIPY_PB *is* that origin: it is the address
    this process already uses to read and write the database. So the value is
    DERIVED from something already proven to work, not configured a second
    time in a second service where it can drift.

    Drift is not hypothetical. ANTICIPY_TWILIO_WEBHOOK_URL had to be identical
    on the worker (which binds the number) and on PocketBase (which validated
    against it); on 2026-08-12→15 they disagreed and every inbound text 403ed
    for three days. The hook no longer needs the variable at all. The worker
    keeps honouring it as a PIN for the one case derivation cannot cover — a
    proxy or custom domain whose public origin is not the one the worker talks
    to — and REFUSES when both are stated, both are plausible and they
    disagree, because that is the drift, and only one of them can be the
    service Twilio should reach. Refusing leaves a working binding alone;
    guessing overwrites one.
    """
    pinned = (os.environ.get("ANTICIPY_TWILIO_WEBHOOK_URL") or "").strip()
    derived = f"{PB.rstrip('/')}{WEBHOOK_PATH}"
    # Base URLs compared without the query: a legacy "?token=..." pin is the
    # same service with a secret stapled on, not a different destination.
    if pinned and reachable_by_twilio(derived) == "" \
            and pinned.split("?")[0] != derived:
        return "", (
            f"ANTICIPY_TWILIO_WEBHOOK_URL pins {pinned.split('?')[0]} but "
            f"ANTICIPY_PB derives {derived}. TWO SERVICES DISAGREE about where "
            f"his texts should land, which is the 2026-08-12 outage exactly. "
            f"Unset the pin to use the derived URL, or point ANTICIPY_PB at "
            f"the same origin")
    ours = pinned or derived
    why = reachable_by_twilio(ours)
    if why:
        return "", f"{ours.split('?')[0]} is not a URL Twilio can reach ({why})"
    return ours, ""


def ensure_inbound_webhook() -> None:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    number = os.environ.get("TWILIO_PHONE_NUMBER") or os.environ.get("TWILIO_FROM")
    # Reading the number's configuration is a REST call like any other, so it
    # authenticates with the same preferred-API-key credential as a send. An
    # inbound signature is the only thing that still needs the auth token
    # itself, and that check does not live in this service.
    credential = rest_credential()
    if not (sid and number and credential):
        return          # not our job to guess; stay quiet
    ours, refusal = webhook_target()
    if not ours:
        print(f"NOT repointing inbound SMS: {refusal}. Leaving the existing "
              f"binding alone.")
        return
    try:
        r = requests.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
            auth=credential.basic(), timeout=15)
        if not r.ok:
            # Was silent, which made "the credential cannot read this account"
            # and "the binding is fine" the same observation.
            print(f"could not read the inbound binding from Twilio: HTTP "
                  f"{r.status_code} using {credential.describes}")
            return
        rows = [n for n in r.json().get("incoming_phone_numbers", [])
                if n.get("phone_number") == number]
        if not rows:
            print(f"TWILIO_PHONE_NUMBER …{str(number)[-4:]} is not on this "
                  f"account — nothing to point at {ours.split('?')[0]}. Her "
                  f"inbound texts are going somewhere this worker cannot see.")
            return
        n = rows[0]
        current = n.get("sms_url") or ""
        # An application SID silently overrides every sms_* URL, so a matching
        # URL with one set is still not a working inbound binding.
        shadowed = bool(str(n.get("sms_application_sid") or "").strip())
        # FULL-string equality. Comparing with the query stripped declared a
        # stale "?token=..." URL healthy for three days while Twilio's
        # signature — computed over the full URL including the query — failed
        # against the clean env URL on every single inbound text (found
        # 2026-08-15: zero inbound events since Aug 12, all 403).
        if current == ours and not shadowed:
            return
        print(f"WEBHOOK HIJACK: inbound SMS was pointing at {current.split('?')[0] or '(empty)'}"
              f"{' (shadowed by an application SID)' if shadowed else ''} — "
              f"pointing it back at {ours.split('?')[0]}")
        # THE URL WE ARE ABOUT TO HAND TWILIO HAS TO BE OUR BACKEND.
        #
        # Reachability says the URL is routable from the internet; it says
        # nothing about what answers there. One GET to /api/health on the same
        # origin turns "the two services agree" from a claim about environment
        # variables into an observation: if that origin is not a PocketBase
        # that answers, then whatever the number currently points at is likelier
        # to be right than a URL serving nothing, and the safe move is to leave
        # the live binding alone and say so.
        origin = urlparse(ours)
        health = f"{origin.scheme}://{origin.netloc}/api/health"
        try:
            probe = requests.get(health, timeout=10)
            answered = bool(getattr(probe, "ok", False))
            detail = f"HTTP {getattr(probe, 'status_code', '?')}"
        except Exception as exc:
            answered, detail = False, str(exc)
        if not answered:
            print(f"NOT repointing inbound SMS: {health} is not answering as "
                  f"our PocketBase ({detail}), so this URL cannot be the one "
                  f"Twilio should reach. Leaving {current.split('?')[0] or '(empty)'} "
                  f"in place.")
            return
        u = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers/{n['sid']}.json",
            auth=credential.basic(), timeout=15,
            data={"SmsUrl": ours, "SmsMethod": "POST", "SmsApplicationSid": ""})
        print("webhook repointed" if u.ok else f"could not repoint the webhook: {u.status_code}")
    except Exception as e:
        # This must never be able to stop her hearing or texting.
        print(f"webhook check failed (harmless): {e}")


def post_event(kind: str, text: str, decision: str = "", goal: str = "",
               owner_ref: str = "", owner_id: str = "",
               source: str = "") -> None:
    ref = _active_owner_ref(owner_ref)
    legacy = str(owner_id or ACTIVE_OWNER_ID or "").strip()
    body = {
        "device_id": "anticipy-brain", "kind": kind, "text": text,
        "decision": decision, "goal": goal or "",
    }
    if ref:
        body["owner_ref"] = ref
    if legacy:
        body["owner"] = legacy
    # WHICH EARS SET THIS OFF, carried onto the row the brain itself writes.
    #
    # An anticipy_says row is the only durable record that she spoke, and it
    # is what every speak-once guard reads back. Until now those rows were
    # provenance-blind: the transcript line that CAUSED the reply knew it came
    # from the pendant (events.source, written by the app), and the reply it
    # produced knew nothing, so "how did the pendant run of this errand go?"
    # could be answered about the hearing and not about the answering. The
    # brain passes the causing line's source through so both halves of one
    # exchange carry the same microphone.
    #
    # Omitted rather than blanked when the caller has no provenance to give: a
    # clock initiative and a welcome message were heard by nobody, and every
    # one of the 2209 events already in production has an empty source, so an
    # explicit "" here would be a claim where there is none.
    provenance = str(source or "").strip()
    if provenance:
        body["source"] = provenance
    response = pb.post(f"{PB}/api/collections/events/records", json=body, timeout=10)
    response.raise_for_status()


_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "to", "of", "in", "on", "at",
    "for", "with", "is", "are", "was", "were", "be", "been", "it", "this",
    "that", "you", "your", "i", "im", "ive", "id", "hey", "hi", "just", "got",
    "get", "have", "has", "do", "did", "does", "can", "will", "would", "about",
    "any", "some", "there", "here", "up", "out", "so", "we", "me", "my",
}


def _content_words(text: str) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


REPORTED: set = set()
STALL_MINUTES = 10        # queued this long with nothing to run it is stuck
AGENT_FRESH_SECONDS = 90  # the extension heartbeats far more often than this


# What actually LEFT the building, remembered locally for a short while.
#
# Every durable dedupe guard she has reads back the anticipy_says event, and
# every notification site sends the text FIRST and writes that event second.
# post_event ends in raise_for_status(), so a PocketBase write outage — a
# restart, or the nightly backup holding the write lock while reads keep
# succeeding — means the text went out and nothing recorded it. Two seconds
# later the same job is re-read, every durable guard says "never mentioned",
# and the identical text goes out again. And again, every two seconds, for
# the length of the outage: the fifteen-texts-in-sixty-five-seconds shape
# arriving through the one door the fix for it never covered.
#
# Deliberately short-lived and keyed on the exact thing that was said, not on
# the job: a job blocking on something NEW still gets its own message, and a
# still-parked job still gets its three-hour second chance.
_SENT_RECENTLY: dict = {}
SEND_SUPPRESS_SECONDS = 45 * 60
_SENT_RECENTLY_MAX = 500


def sent_moments_ago(key: str, within: float = SEND_SUPPRESS_SECONDS,
                     now: float | None = None) -> bool:
    """Did this exact message already leave this process a moment ago?"""
    at = _SENT_RECENTLY.get(key)
    return bool(at and (now if now is not None else time.time()) - at < within)


def mark_sent(key: str, now: float | None = None) -> None:
    stamp = now if now is not None else time.time()
    _SENT_RECENTLY[key] = stamp
    if len(_SENT_RECENTLY) > _SENT_RECENTLY_MAX:
        cutoff = stamp - SEND_SUPPRESS_SECONDS
        for stale in [k for k, v in _SENT_RECENTLY.items() if v < cutoff]:
            _SENT_RECENTLY.pop(stale, None)


# WHAT EARNS AN INTERRUPTION.
#
# On 2026-08-05 quiet work stopped being invisible: an overheard lookup began
# sending one light FYI text instead of landing silently in the feed. That was
# the right call — he had watched it research Paris flights, seen only "Noted
# — nothing needed", and reasonably concluded it was dead.
#
# The correction then became the problem. His words: "why is it also randomly
# messaging me after the fact... 90% of the time it's bad". The only gates on
# an uninvited text were quiet hours and don't-repeat-the-same-goal — nothing
# asked whether the message was WORTH GETTING. So a lookup that found nothing
# still buzzed his phone with "The provided sources do not contain information
# about an Earls restaurant in Vancouver", verbatim, in production.
#
# The answer is not to stop speaking; the good 10% is the whole point of the
# product. It is that an uninvited text has to earn the interruption on three
# counts, and NONE of these lose the finding — everything still lands in the
# feed for whenever he looks. The only question here is whether it is worth a
# buzz in his pocket right now.
UNINVITED_TEXTS_PER_DAY = 3

# How many times ONE stuck task may ask him for help before it goes quiet and
# leaves the card to speak for itself. The comment on the re-ask has always
# said "one question, one second chance, then quiet"; this is what makes that
# true regardless of how the browser rephrases the obstacle.
STUCK_ASKS_CEILING = 2
FYI_STALE_AFTER_SECONDS = 45 * 60

# A lookup that came back empty-handed. Texting this is strictly worse than
# saying nothing: it spends his attention to tell him he learned nothing.
_NON_ANSWER = re.compile(
    r"\b(do(es)? not contain|don'?t contain|no information|not (?:able to )?find|"
    r"could ?n'?t find|couldn't find|unable to|nothing (?:was )?found|no results?|"
    r"i (?:do ?n'?t|don't) have|no relevant|not available|sources? (?:do not|don't))\b",
    re.I)


def worth_interrupting_him(goal: str, result: str, age_seconds: float,
                           sent_today: int) -> tuple[bool, str]:
    """Should this uninvited finding buzz his phone, or just land in the feed?

    Returns (worth_it, reason_if_not). A False here NEVER discards anything —
    the finding still reaches the feed. It only declines to interrupt.
    """
    text = (result or "").strip()
    if len(text) < 25:
        return False, "too thin to be worth a buzz"
    if _NON_ANSWER.search(text):
        return False, "it found nothing — that is not news"
    if age_seconds > FYI_STALE_AFTER_SECONDS:
        return False, (f"the moment has passed "
                       f"({int(age_seconds // 60)} min since he said it)")
    if sent_today >= UNINVITED_TEXTS_PER_DAY:
        return False, f"already sent {sent_today} uninvited texts today"
    return True, ""


def job_age_seconds(job: dict) -> float:
    """How long ago he said the thing this job came from.

    Measured from the job row rather than now-minus-nothing: a finding that
    lands three hours after he mentioned something is not "caught this
    earlier", it is an interruption about a moment that has gone.
    """
    raw = (job.get("created") or "")[:19]
    try:
        made = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc)
    except Exception:
        return 0.0          # unreadable: treat as fresh rather than mute it
    return max(0.0, (datetime.now(timezone.utc) - made).total_seconds())


def uninvited_sent_today(owner_ref: str = "") -> int:
    """How many uninvited texts have already gone out today.

    Read from the durable record rather than a counter in memory: a redeploy
    resetting this to zero is how a daily cap quietly becomes no cap at all.
    """
    try:
        since = (datetime.now(CLOCK_TZ).replace(hour=0, minute=0, second=0,
                                                microsecond=0)
                 .astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        filt = f'kind="anticipy_says" && decision="done" && created>="{since}"'
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 100, "sort": "-created"}, timeout=10)
        if not getattr(r, "ok", False):
            return 0
        return sum(1 for ev in r.json().get("items", [])
                   if (ev.get("params") or "").find("uninvited") >= 0)
    except Exception as e:
        print(f"uninvited count failed: {e}")
        return 0


# One Twilio attempt per finding per two minutes when a send keeps failing.
# Far longer than the two-second sweep that would otherwise hammer Twilio, far
# shorter than a person's patience for an answer he asked for out loud.
FYI_RETRY_SECONDS = 120


def deliver_fyi(anticipy, goal: str, result: str, overheard: bool) -> bool:
    """Text him what she found — her words, varied every time, one text.

    Returns whether the text actually went out. That return value is not
    bookkeeping: "held for morning" and "delivered" used to be the same
    silent None, so the caller marked a held FYI as delivered and the
    morning never came. Quiet hours are ten hours long, so every overheard
    lookup that finished overnight was destroyed rather than deferred —
    exactly the "I'll text you what I find" that never arrives. A caller
    that gets False must leave the finding undelivered so a later sweep
    can send it — a failed SEND is one of those cases, see below.

    Overheard FYIs ("caught this earlier, looked into it") respect the same
    quiet hours as every other uninvited text; an answer he asked for out
    loud goes out whenever it is ready. The caller's already_raised guard
    on the goal is what keeps this to one text per finding — this function
    is only ever reached for a fresh result."""
    trimmed = (result or "").strip()
    if not trimmed:
        return False
    if overheard:
        hour = datetime.now(CLOCK_TZ).hour
        if CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END:
            print(f"fyi held for morning (quiet hours): {goal[:50]}")
            return False
    if len(trimmed) > 320:
        trimmed = trimmed[:317] + "…"
    # A HARD SEND FAILURE IS NOT A DELIVERY.
    #
    # This used to return True whatever came back, so a Twilio 4xx, an account
    # with no owner number and the rig guard all read to the caller as "he has
    # it": the finding was recorded as delivered and never sent again. What
    # justified that was fear of a retry storm, since the caller re-enters this
    # on every two-second sweep for as long as it gets False. So the storm is
    # bounded HERE — one attempt per FYI_RETRY_SECONDS per finding — instead of
    # by lying about the outcome. Only FAILURES back off; a success leaves no
    # mark, because the caller's already_raised guard is what stops a second
    # text of a delivered finding.
    #
    # Reporting False is also what every other send in this file does with a
    # failure (the stall notice, the result text, the stuck-job notice all
    # `continue` without recording), so a finding that cannot be texted stays
    # on the books with a log line saying why, on every pass.
    failed_recently = f"fyi-failed:{goal}"
    if sent_moments_ago(failed_recently, within=FYI_RETRY_SECONDS):
        return False
    try:
        say = anticipy._voice({
            "situation": ("you caught something he said to someone earlier, "
                          "quietly looked into it, and are sharing what you "
                          "found — a light fyi, nothing needed from him, do "
                          "not ask a question"
                          if overheard else
                          "you finished looking into what he asked out loud "
                          "and are texting him the answer"),
            "goal": goal, "answer": trimmed,
        }) or (f"caught the {goal} thing earlier — fyi: {trimmed}"
               if overheard else trimmed)
        if not anticipy.notify_owner(say):
            mark_sent(failed_recently)
            print(f"fyi NOT delivered — the send failed, so it stays "
                  f"undelivered: {goal[:50]}")
            return False
    except Exception as e:
        mark_sent(failed_recently)
        print(f"fyi text failed (feed still has it), staying undelivered: {e}")
        return False
    return True


def ambient_job(job: dict) -> bool:
    """Was this job born from speech that was never aimed at her — a
    dictation run, a conversation with another person? Ambient work is done
    quietly and delivered quietly: its results land in the feed, never as a
    text, and it never becomes a reason to buzz his phone (roadmap §7.1).
    The lane rides in the job's own params so it survives redeploys."""
    params = job.get("params")
    if isinstance(params, str):
        try:
            params = json.loads(params or "{}")
        except Exception:
            return False
    return isinstance(params, dict) and params.get("lane") == "ambient"


def browser_reachable(owner_ref: str = "") -> bool:
    """Is his Chrome actually there to do the work?

    Nothing in the brain ever asked. A resumed task goes to `queued` and waits
    for the extension to claim it — so if he answers from his phone with the
    laptop shut, she says "I'll finish the booking now" and then nothing
    happens, forever, with no word to him. Answering by text away from the
    desk is the normal case, not the edge case."""
    try:
        r = pb.get(f"{PB}/api/collections/agents/records",
                   params={"filter": _scoped_filter("paired=true", owner_ref), "sort": "-updated",
                           "perPage": 1}, timeout=10)
        if not r.ok:
            return True          # unknown is not "absent": never invent bad news
        items = r.json().get("items", [])
        if not items:
            return False
        seen = (items[0].get("last_seen") or items[0].get("updated") or "")
        t = datetime.fromisoformat(seen.replace(" ", "T").replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - t).total_seconds() < AGENT_FRESH_SECONDS
    except Exception:
        return True


def report_stalled_work(anticipy) -> None:
    """Say so when work cannot start because his browser is not there."""
    try:
        if browser_reachable():
            return
        # Nothing here is urgent enough to wake him. Same quiet hours the
        # clock respects — a stalled task at 3am can wait until morning.
        hour = datetime.now(CLOCK_TZ).hour
        if CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END:
            return
        since = (datetime.now(timezone.utc) - timedelta(minutes=STALL_MINUTES)
                 ).strftime("%Y-%m-%d %H:%M:%S")
        # `running` counts too. The extension requeues its own stale jobs —
        # but only while Chrome is open, so a task whose browser died partway
        # sits at `running` forever and looks like work in progress. That is
        # worse than a queued one: it reads as "she is on it".
        # The research lane is excluded: it never needs his Chrome — this
        # same process runs it — so "I just need your browser open" would be
        # a false alarm about work she is about to do herself.
        filt = (f'(status="queued" || status="running") && updated<="{since}"'
                f' && lane!="research"')
        scope = owner_filter(anticipy)
        if scope:
            filt = f"({filt}) && {scope}"
        r = pb.get(f"{PB}/api/collections/jobs/records",
                   params={"filter": filt, "perPage": 5, "sort": "updated"},
                   timeout=10)
        if not r.ok:
            return
        for job in r.json().get("items", []):
            goal = (job.get("goal") or "").strip()
            # Quiet work stays quiet: an ambient job that cannot run is not
            # worth his attention — it was never something he asked her for.
            if ambient_job(job):
                continue
            # Deduped on the KIND of message, not on wording — her phrasing is
            # generated fresh and comparing it to itself has failed twice now.
            if already_raised(goal, decision="stalled"):
                continue
            # ...and the same again when the durable record of it could not be
            # written. already_raised reads the event post_event writes AFTER
            # the text has gone out, so a write outage made every pass believe
            # nothing had been said and re-sent the notice every two seconds.
            local_key = f'stalled:{job["id"]}:{job.get("status")}'
            if sent_moments_ago(local_key):
                continue
            midway = job.get("status") == "running"
            said = anticipy._voice({
                "situation": ("this stopped partway because their browser "
                              "closed — say so plainly, no alarm, and that you "
                              "will pick it up when it is open again" if midway
                              else "you are ready to do this but their browser "
                              "is not open, so nothing can run — tell them "
                              "plainly, no alarm, and that it will go as soon "
                              "as it is"),
                "task": goal,
            }) or (f"{goal} stopped partway — your Chrome closed. I'll pick it "
                   f"up when it's open." if midway else
                   f"I'm ready to finish {goal} — I just need your Chrome open.")
            if not anticipy.notify_owner(said):
                print(f"stall notice for {job['id']}: send failed, not recording it")
                continue
            mark_sent(local_key)
            post_event("anticipy_says", said, decision="stalled", goal=goal)
            print(f"stalled (no browser): {job['id']} — told him")
    except Exception as e:
        print(f"stalled-work report failed: {e}")


RESEARCH_CLAIMANT = "worker-research"
# One research run is a Brave search, up to three page fetches and an LLM
# summarize with a 60s timeout and a fallback client. End to end that passes
# two minutes routinely — and two minutes was the workflow lease's default,
# never heartbeated. The backend refuses a "done" write from an expired lease
# ("expired executor may only recover, park, or fail"), so the answer he asked
# for was computed, refused, and thrown away while the row sat at running.
RESEARCH_LEASE_SECONDS = 600
# And when the process dies mid-lookup anyway — a redeploy is a SIGTERM, and
# the finish PATCH can simply fail — the row stays at running with nobody
# looking at it: this pass only ever polls status="queued", and
# report_stalled_work deliberately skips this lane because it never needs his
# Chrome. The extension's stale-job sweep is browser-lane work and only runs
# while Chrome is open, which is the one thing this lane exists not to need.
# So the worker hands its own abandoned claims back. He asked a question out
# loud, a deploy landed mid-lookup, and the answer never came, with no symptom
# anywhere.
RESEARCH_STRANDED_MINUTES = 15


def release_stranded_research(anticipy,
                              older_than_minutes: int = RESEARCH_STRANDED_MINUTES) -> int:
    """Requeue research jobs this worker claimed and never finished."""
    base = anticipy.backend_url
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
              ).strftime("%Y-%m-%d %H:%M:%S")
    filt = (f'status="running" && lane="research"'
            f' && claimed_by="{RESEARCH_CLAIMANT}" && updated<="{cutoff}"')
    scope = owner_filter(anticipy)
    if scope:
        filt = f"({filt}) && {scope}"
    try:
        r = pb.get(f"{base}/api/collections/jobs/records",
                   params={"filter": filt, "perPage": 20, "sort": "updated"},
                   timeout=10)
        if not getattr(r, "ok", False):
            return 0
        items = r.json().get("items", [])
    except Exception as e:
        print(f"research sweep failed: {e}")
        return 0
    freed = 0
    for job in items:
        body = {"status": "queued", "claimed_by": "", "claimed_at": ""}
        headers = None
        try:
            params = json.loads(job.get("params") or "{}") or {}
        except Exception:
            params = {}
        workflow = workflow_from_params(params)
        if workflow:
            try:
                # A read-only lookup leaves nothing in the world to reconcile,
                # so recovery is a plain requeue — until the attempt cap, where
                # recover_expired fails it instead and he finally hears about
                # it rather than waiting on a row that retries forever.
                workflow = recover_expired_plan(workflow)
            except Exception as e:
                print(f"research sweep: {job['id']} cannot be recovered: {e}")
                continue
            body.update(workflow.job_fields())
            body["params"] = json.dumps(put_in_params(params, workflow))
            headers = {"X-Anticipy-Lease": job.get("lease_token") or ""}
        try:
            back = pb.patch(f"{base}/api/collections/jobs/records/{job['id']}",
                            json=body, headers=headers, timeout=10)
        except Exception as e:
            print(f"research sweep: {job['id']} could not be handed back: {e}")
            continue
        if getattr(back, "ok", False):
            freed += 1
    if freed:
        print(f"research: handed back {freed} job(s) a dead run left at running")
    return freed


def run_research_jobs(anticipy, runner=None) -> None:
    """Run the research lane HERE, in the worker — never in his Chrome.

    Read-only goals are queued with lane="research" (anticipy_core.job_lane);
    the extension's claim filter and the backend's research_lane hook keep
    every browser agent away from them. Claiming follows the extension's own
    doctrine — stamp, read back, only run if the stamp survived — so two
    workers can never run the same job. Owner scoping is identical to every
    other job read this file does."""
    try:
        base = anticipy.backend_url
        # Before asking for new work, take back what a dead run abandoned —
        # otherwise the only thing that ever moves a stranded row is a person
        # hand-editing it.
        release_stranded_research(anticipy)
        filt = 'status="queued" && lane="research"'
        scope = owner_filter(anticipy)
        if scope:
            filt = f"({filt}) && {scope}"
        r = pb.get(f"{base}/api/collections/jobs/records",
                   params={"filter": filt, "perPage": 5, "sort": "created"},
                   timeout=10)
        if not r.ok:
            return
        jobs = r.json().get("items", [])
        if not jobs:
            return
        # Read per pass, not at import: no new global state, and a key added
        # or removed on a redeploy takes effect without a code path changing.
        api_key = os.environ.get("BRAVE_API_KEY")
        for job in jobs:
            if not api_key:
                # Graceful fallback: no key means no research arm, and a job
                # queued for an executor that does not exist would sit
                # forever. Hand it to the browser lane — slower and noisier,
                # but it runs. Queue-time routing already does this; this
                # catches rows queued before the key went away.
                pb.patch(f"{base}/api/collections/jobs/records/{job['id']}",
                         json={"lane": ""}, timeout=10)
                print(f"research: no BRAVE_API_KEY — {job['id']} handed to "
                      "the browser lane")
                continue
            try:
                params = json.loads(job.get("params") or "{}") or {}
            except Exception:
                params = {}
            workflow = workflow_from_params(params)
            lease_token = ""
            claim_body = {"status": "running", "claimed_by": RESEARCH_CLAIMANT,
                          "claimed_at": datetime.now(timezone.utc)
                          .strftime("%Y-%m-%d %H:%M:%S")}
            if workflow:
                try:
                    workflow = claim_plan(
                        workflow, expected_version=workflow.version,
                        actor_id=RESEARCH_CLAIMANT,
                        lease_seconds=RESEARCH_LEASE_SECONDS)
                except Exception:
                    continue
                lease_token = workflow.lease.token
                params = put_in_params(params, workflow)
                claim_body.update(workflow.job_fields())
                claim_body["params"] = json.dumps(params)
            claim = pb.patch(
                f"{base}/api/collections/jobs/records/{job['id']}",
                json=claim_body,
                timeout=10)
            if not getattr(claim, "ok", False):
                continue
            check = pb.get(f"{base}/api/collections/jobs/records/{job['id']}",
                           timeout=10)
            if not getattr(check, "ok", False):
                continue
            fresh = check.json()
            if fresh.get("claimed_by") != RESEARCH_CLAIMANT \
                    or fresh.get("status") != "running" \
                    or (lease_token and fresh.get("lease_token") != lease_token):
                continue
            out = (runner or research.run_research)(
                job.get("goal", ""), params, llm=anticipy.llm, api_key=api_key)
            ok = bool(out.get("ok"))
            result = (out.get("result") or "")[:6000]
            finish_body = {"status": "done" if ok else "failed",
                           "result": result}
            finish_headers = None
            if workflow:
                # A cited URL is independently inspectable evidence.  An
                # executor saying "ok" without one is not proof of research.
                evidence = [u.rstrip(".,);]") for u in
                            re.findall(r"https?://[^\s]+", result)]
                try:
                    if ok and evidence:
                        workflow = succeed_plan(
                            workflow, lease_token=lease_token,
                            summary=result, evidence=evidence, verified=True)
                    else:
                        workflow = fail_plan(
                            workflow, lease_token=lease_token,
                            reason=(result or "research produced no verifiable source"))
                        ok = False
                    params = put_in_params(params, workflow)
                    finish_body.update(workflow.job_fields())
                    finish_body["params"] = json.dumps(params)
                    finish_headers = {"X-Anticipy-Lease": lease_token}
                except Exception:
                    continue
            finished = pb.patch(
                f"{base}/api/collections/jobs/records/{job['id']}",
                json=finish_body, headers=finish_headers, timeout=10)
            if not getattr(finished, "ok", False):
                # The answer exists and the row still says running. Say so:
                # this used to be a bare `continue`, and a silently discarded
                # result is indistinguishable from her never having looked.
                # release_stranded_research hands the row back on a later
                # pass so the lookup is retried rather than lost.
                print(f"research: {job['id']} finished but the write was "
                      f"refused ({getattr(finished, 'status_code', '?')}) — "
                      f"leaving it for the stranded-claim sweep")
                continue
            # Delivery is report_finished_jobs' job: a desk card by default,
            # an in-thread text only when the ask came in over SMS.
            print(f"research: {job['id']} {'done' if ok else 'failed'} — "
                  f"{job.get('goal', '')[:60]}")
    except Exception as e:
        print(f"research pass failed: {e}")


FINISHED_PER_PAGE = 200
FINISHED_MAX_PAGES = 10


def _finished_jobs(filt: str) -> list[dict]:
    """Every finished job in the window, oldest first.

    This was one page of the ten NEWEST rows. A finished job's `updated`
    never moves again, so after a burst of more than ten done/failed jobs —
    exactly what the 38-job backlog replay produced — every later pass
    re-read the same ten rows, all already in REPORTED, and jobs 11..N were
    never fetched at all. Being older they aged out of the 12h window first,
    so their results were dropped with no text, no feed event and no log
    line: answers he asked for out loud, and failures he should have heard
    about, gone.
    """
    rows: list[dict] = []
    page = 1
    while page <= FINISHED_MAX_PAGES:
        r = pb.get(f"{PB}/api/collections/jobs/records",
                   params={"filter": filt, "perPage": FINISHED_PER_PAGE,
                           "page": page, "sort": "updated"},
                   timeout=10)
        if not getattr(r, "ok", False):
            break
        payload = r.json() or {}
        rows.extend(payload.get("items", []))
        if page >= int(payload.get("totalPages") or 1):
            break
        page += 1
    return rows


def already_delivered(goal: str, within_hours: float = 24.0,
                      owner_ref: str = "") -> bool:
    """Has the answer to THIS job already gone out?

    This used to be already_raised(goal, decision="done"), whose overlap is
    measured over the SHORTER of the two goals — so a short goal contained in
    a longer one scores 1.0 and any question that resembles one she answered
    yesterday is destroyed rather than deferred. "weather in Montreal this
    Sunday" scores 0.67 against Monday's "look up weather in Montreal": no
    text, no feed event, nothing — the exact three-silent-weather-questions
    failure report_finished_jobs was written to end, rebuilt out of fuzzy
    similarity.

    Fuzzy matching earns its keep for outreach, where the model rephrases an
    open loop's goal every time it raises it. It earns nothing here: a job's
    goal is read verbatim off the row, so it is byte-identical every time the
    same job is re-read, and re-reading the same job is the only repeat this
    guard exists to stop.
    """
    goal = (goal or "").strip()
    if not goal:
        return False
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=within_hours)).strftime("%Y-%m-%d %H:%M:%S")
        filt = (f'kind="anticipy_says" && decision="done"'
                f' && created>="{since}"')
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 200, "sort": "-created"}, timeout=10)
        if not getattr(r, "ok", False):
            return False
        return any((ev.get("goal") or "").strip() == goal
                   for ev in r.json().get("items", []))
    except Exception as e:
        print(f"already_delivered check failed: {e}")
        return False


def can_reach_owner(anticipy) -> bool:
    """Is there anyone at the other end, before we pay to compose a sentence?

    THE COMPOSE IS THE EXPENSIVE PART. Live, 2026-08-22, on a real account
    with no phone number on it: a finished job reached the notify path, a
    fresh model call wrote the sentence, notify_owner refused it for want of
    a number ("NO OWNER PHONE on this account — composed but NOT sent"), the
    job was deliberately left out of REPORTED so that a failed send could
    retry, and two seconds later the whole thing happened again — for hours,
    one paid model call per sweep, for a message that could never leave.

    Retrying is right; paying for the sentence before knowing anyone can
    receive it is not. The rule for WHO is reachable is deliberately not
    copied here — it lives once, beside the send it guards, in
    Anticipy.can_notify_owner. A core (or a test double) without that method
    cannot answer cheaply, so this answers yes and the caller behaves exactly
    as it did before: the wasted call is the old bug, a wrong silence would
    be a worse new one.
    """
    reachable = getattr(anticipy, "can_notify_owner", None)
    return bool(reachable()) if callable(reachable) else True


def report_finished_jobs(anticipy) -> None:
    """Tell him the answer.

    Until now nothing in the brain ever did. Questions became research jobs,
    the browser ran them and wrote the answer onto the job row, and there the
    answer stayed: review_loops() only updated an in-RAM status, and the five
    places she texts were all "want me to?", "which one?", "I need X" and the
    clock. He asked "What's the weather in Mtl" on 2026-07-31 and got nothing,
    ever — same for the same question on 07-15 and "What's the weather this
    Sunday" on 07-17. Three questions, three silences.

    Failures are reported too. Silence after a question is the worst answer,
    but "I couldn't get it" is a real one."""
    try:
        filt = '(status="done" || status="failed")'
        scope = owner_filter(anticipy)
        if scope:
            filt = f"({filt}) && {scope}"
        # Only recent work: this must never blast a backlog on first deploy.
        since = (datetime.now(timezone.utc) - timedelta(hours=12)
                 ).strftime("%Y-%m-%d %H:%M:%S")
        filt += f' && updated>="{since}"'
        for job in _finished_jobs(filt):
            if job["id"] in REPORTED:
                continue
            goal = (job.get("goal") or "").strip()
            result = (job.get("result") or "").strip()
            failed = job.get("status") == "failed"
            # Ambient work is delivered to the desk, never to his phone: the
            # result goes into the feed for whenever he looks, and a failure
            # of work he never asked for is not news at all.
            if ambient_job(job):
                # Nothing overheard can go out during quiet hours, so leave
                # the whole finding untouched and look again after they end.
                # Checked BEFORE already_delivered on purpose: that call is a
                # round trip, and re-asking it about every held job on every
                # two-second sweep would run all night for an answer that
                # cannot change until 08:00.
                hour = datetime.now(CLOCK_TZ).hour
                if result and not failed and (CLOCK_QUIET_START <= hour
                                              or hour < CLOCK_QUIET_END):
                    continue
                if result and not failed and not already_delivered(goal):
                    # EARN THE INTERRUPTION. The finding lands in the feed
                    # either way; this only decides whether it is also worth
                    # a buzz in his pocket. "Randomly messaging me after the
                    # fact ... 90% of the time it's bad" — the 90% is empty
                    # answers, findings that arrive long after the moment
                    # passed, and a chatty day with no ceiling.
                    age = job_age_seconds(job)
                    worth, why = worth_interrupting_him(
                        goal, result, age, uninvited_sent_today(
                            job.get("owner_ref") or ""))
                    if not worth:
                        print(f"fyi to the feed only ({why}): {goal[:50]}")
                        deliver_to_feed_only = True
                    else:
                        deliver_to_feed_only = False
                    # A held FYI is not a delivered one. Recording the feed
                    # event and marking the job reported are what make this
                    # finding "already raised" forever, so both must wait
                    # until the text has actually gone out — otherwise every
                    # overheard lookup that finished between 22:00 and 08:00
                    # was silently destroyed instead of held.
                    if not deliver_to_feed_only and not deliver_fyi(
                            anticipy, goal, result, overheard=True):
                        continue
                    # Rule change 2026-08-05, Omar's call: quiet work is no
                    # longer INVISIBLE work. He watched her research Paris
                    # flights and dinner spots, saw only "Noted — nothing
                    # needed", and reasonably concluded she was dead. A
                    # finished overheard lookup now sends ONE light FYI text
                    # in her own words and lands in the feed. Failures stay
                    # silent — a dead end on work he never asked for is not
                    # news. Text first, then the durable feed record (the
                    # record is what dedupes, so it must land second).
                    #
                    # Marked reported BEFORE that write, though: post_event
                    # ends in raise_for_status, and letting it unwind with the
                    # FYI already sent meant the next two-second pass sent the
                    # same FYI again, for as long as PocketBase refused
                    # writes.
                    REPORTED.add(job["id"])
                    post_event("anticipy_says", result, decision="done", goal=goal)
                REPORTED.add(job["id"])
                print(f"ambient job {job['id']} finished — fyi'd and on the feed")
                continue
            # Durable: has she already delivered THIS result? Keyed on the job's
            # own goal, exactly, and on being a result — so her earlier "want me
            # to?" about the same task does not silence the answer, and neither
            # does yesterday's answer to a DIFFERENT question that happens to
            # share most of its words.
            if already_delivered(goal):
                REPORTED.add(job["id"])
                continue
            # DESK delivery for the research lane (roadmap §3 lane 2): the
            # answer is written on the job and lands in the feed as a
            # conversation entry — never an SMS. The one exception is a job
            # he asked for OVER SMS: that answer belongs in that thread, so
            # it falls through to the normal notify path below.
            try:
                channel = (json.loads(job.get("params") or "{}") or {}) \
                    .get("channel", "")
            except Exception:
                channel = ""
            if (job.get("lane") or "") == "research" and channel != "sms":
                said = result or (f"Couldn't get there on {goal}." if failed
                                  else f"That's done: {goal}.")
                # He asked for this one out loud, so the answer goes to his
                # hand, not just the feed (same 2026-08-05 rule change).
                if result and not failed:
                    # Return value deliberately not gating: for this lane the
                    # FEED write below is the delivery ("never an SMS"), and the
                    # text is an extra. deliver_fyi logs its own failure, so a
                    # text that did not go out is visible without holding a job
                    # open for an answer that has already landed on his desk.
                    deliver_fyi(anticipy, goal, result, overheard=False)
                # Reported first, then the feed write. A refused post_event
                # raises, and with the text already in his hand that unwound
                # before anything remembered it — so the same answer went out
                # again two seconds later, and again, until writes recovered.
                REPORTED.add(job["id"])
                post_event("anticipy_says", said, decision="done", goal=goal)
                print(f"desk: research {job['status']} {job['id']} — {goal[:60]}")
                continue
            # CANNOT REACH IS NOT FAILED TO SEND, and this is the line where
            # the difference costs money. A transient failure — Twilio 5xx, a
            # dropped connection — must retry, which is why REPORTED is only
            # set after a send succeeds. But an account with no number will
            # not grow one between two sweeps, so that same retry recomposed
            # this same answer with a fresh model call every two seconds for
            # hours on 2026-08-22.
            #
            # THE CHANNEL WAS THE PROBLEM, NEVER THE ANSWER. Stopping the
            # burn by dropping the result on the floor threw away real work:
            # on that same account the browser HAD drafted the invoice email
            # to Devon in his Gmail, and the only sentence that said so was
            # composed, refused, recomposed and refused again for hours. He
            # was never told, by anything, that the errand he asked for was
            # finished. Two failures, and the silent one is the worse one.
            #
            # No phone is not unreachable, it is UNTEXTABLE. The feed needs
            # no number and no Twilio — the app reads these rows, and for the
            # research lane above the feed write IS the delivery. So compose
            # ONCE, put the answer where he will actually find it, and record
            # it as said, because this time it was. That is the difference
            # from the loop: the loop paid for a sentence aimed at a channel
            # that did not exist.
            untextable = not can_reach_owner(anticipy)
            # A finished task with nothing written on it is still finished, and
            # he asked for it. Staying quiet here would mean his table gets
            # booked and he never learns it — the success case of the exact
            # task he is waiting on, lost. The browser fills `result` from the
            # model's own done-claim, and a model that finishes without
            # articulating one leaves it empty.
            said = anticipy._voice({
                "situation": ("you tried to do this for them and it did not work "
                              "— say so plainly and briefly" if failed else
                              "you finished what they asked and are giving them "
                              "the answer" if result else
                              "it is done, but nothing was written down about how "
                              "it went — tell them it is done and do NOT invent "
                              "any details you were not given"),
                "task": goal,
                "what_you_found": result or "(nothing recorded)",
            }) or (f"Couldn't get there on {goal}." if failed
                   else result or f"That's done: {goal}.")
            if untextable:
                # REPORTED first, then the durable write — the same order as
                # every other delivery in this function, for the same reason:
                # post_event ends in raise_for_status, and unwinding after the
                # answer has been delivered is what put the identical message
                # out again two seconds later, forever.
                REPORTED.add(job["id"])
                post_event("anticipy_says", said, decision="done", goal=goal)
                print(f"result for {job['id']} has nowhere to go by text — no "
                      f"phone on this account — so it went to the feed "
                      f"instead of to a text: {said[:80]}")
                continue
            if not anticipy.notify_owner(said):
                print(f"result for {job['id']}: send failed, not recording it as said")
                continue
            # Same order for the same reason: the text has landed, so nothing
            # a failing feed write does may let this pass send it twice.
            REPORTED.add(job["id"])
            post_event("anticipy_says", said,
                       decision="done", goal=goal)
            print(f"reported {job['status']} job {job['id']}: {said[:80]}")
    except Exception as e:
        print(f"result report failed: {e}")


def _words(text: str) -> list:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def longest_shared_run(a: str, b: str) -> int:
    """How many words these two share, IN ORDER, gaps allowed.

    This was a strictly contiguous run, and it failed on the very first real
    pair it was tested against. She had stored "i don't have mother's contact
    info can you send that over"; he read it back as "I don't have YOUR
    mother's contact can you send it over". One inserted word cut the
    unbroken run from nine to three and the echo sailed through.

    Nobody reads a sentence back word-perfect, and ASR guarantees they will
    not: small words get inserted, dropped and swapped. What survives is the
    ORDER. So gaps are allowed and order is not — which is exactly the thing
    that separates reading a message aloud from happening to use some of the
    same words.
    """
    x, y = _words(a), _words(b)
    if not x or not y:
        return 0
    prev = [0] * (len(y) + 1)
    for i in range(1, len(x) + 1):
        cur = [0] * (len(y) + 1)
        for j in range(1, len(y) + 1):
            cur[j] = prev[j - 1] + 1 if x[i - 1] == y[j - 1] else max(prev[j], cur[j - 1])
        prev = cur
    return prev[len(y)]


# Measured on real pairs from his own logs. The two genuine echoes score 9
# and 16 shared words in order, at 0.82 and 0.70 of his line; every genuine
# non-echo — a confirmation, a correction, the same topic in his own words,
# the same words rearranged — scores 1, 1, 2, 3, 4 and 5. Six separates them
# with room on both sides. The fraction is the second guard, so a long ramble
# that happens to contain six scattered matches is not mistaken for reading.
ECHO_RUN = 6
ECHO_FRACTION = 0.6


def is_echo_of_her(line: str, minutes: float = 30.0, owner_ref: str = "",
                   before: float | None = None) -> bool:
    """Is he simply reading back something SHE said?

    He does it constantly while testing, and every time she has taken it as a
    fresh instruction. On 2026-08-05 she texted "the August data is ready to
    add in the spreadsheet"; he said that sentence out loud; she made a second
    job out of it. Later she asked for "your mother's contact info", he
    repeated it, and she made a job to go and get it.

    Her own output is not a request. She has a record of everything she has
    said — this reads it, rather than hoping the model notices.
    """
    line = (line or "").strip()
    if len(_words(line)) < ECHO_RUN:
        return False
    try:
        cutoff = before if before is not None else time.time()
        since = datetime.fromtimestamp(
            cutoff - minutes * 60, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        until = datetime.fromtimestamp(
            cutoff, timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%fZ")
        filt = (f'(kind="anticipy_says" || kind="anticipy_text")'
                f' && created>="{since}" && created<="{until}"')
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 40, "sort": "-created"}, timeout=10)
        if not r.ok:
            return False
        mine = len(_words(line))
        for ev in r.json().get("items", []):
            shared = longest_shared_run(line, ev.get("text", ""))
            if shared >= ECHO_RUN and shared / max(1, mine) >= ECHO_FRACTION:
                return True
    except Exception as e:
        print(f"echo check failed: {e}")
    return False


# What we last told him each job was waiting on. In memory only: a restart
# costs at most one repeated message, where getting this wrong the other way
# costs a draft he never sees.
_last_blocker: dict = {}


_FACT_TOKEN = re.compile(r"\d[\d:]*(?:\s*[ap]\.?m\.?)?", re.IGNORECASE)


def _fact_tokens(text: str) -> set:
    """The numbers, times and dates in a sentence, normalized. These are the
    tokens a paraphrase has no license to drop or invent."""
    out = set()
    for m in _FACT_TOKEN.findall(text or ""):
        t = re.sub(r"[\s.]", "", m.lower()).rstrip(":")
        if t:
            out.add(t)
    return out


def carries_facts(said: str, facts: str) -> bool:
    """Did a paraphrase keep every hard fact, and invent none?

    Voice may rephrase freely; numbers, times and dates are not hers to
    change. A rewrite that loses "noon"/"tomorrow" or conjures a figure the
    source never had is worse than sending the source verbatim."""
    want, have = _fact_tokens(facts), _fact_tokens(said)
    if not want <= have:
        return False
    if have - want:
        return False
    # Day words are facts too: a blocker about "tomorrow" must still be
    # about tomorrow after the rewrite.
    day_words = {"today", "tomorrow", "tonight", "noon", "midnight",
                 "monday", "tuesday", "wednesday", "thursday", "friday",
                 "saturday", "sunday"}
    src = {w for w in re.findall(r"[a-z]+", (facts or "").lower()) if w in day_words}
    out = {w for w in re.findall(r"[a-z]+", (said or "").lower()) if w in day_words}
    return src <= out


def asked_about_recently(goal: str, minutes: float = 45.0,
                         owner_ref: str = "") -> bool:
    """Did she already ask about THIS task a moment ago?

    The existing guard compares the browser's words about what it needs
    against HER paraphrase of them, and a paraphrase drops most of the
    original words — so a short, freshly-worded ask slides under the 50%
    threshold every time. On 2026-08-05 that produced FIFTEEN texts about one
    stuck Zoom page in sixty-five seconds, each one a new rewording of the
    same sentence, because the poll runs every few seconds and nothing in the
    loop was keyed to anything stable.

    This one reads no wording at all: has an ask about this exact task gone
    out recently? A blocked job is blocked for minutes at least, so asking
    twice inside the window is never right, whatever the wording.
    """
    goal = (goal or "").strip()
    if not goal:
        return False
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        filt = (f'kind="anticipy_says" && decision="needs_user"'
                f' && created>="{since}"')
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 50, "sort": "-created"}, timeout=10)
        if not r.ok:
            return False
        return any((ev.get("goal") or "").strip() == goal
                   for ev in r.json().get("items", []))
    except Exception as e:
        print(f"asked_about_recently check failed: {e}")
        return False


def asks_for_goal(goal: str, owner_ref: str = "", within_hours: float = 24.0) -> int:
    """How many times she has already raised THIS task today.

    The re-ask above is deliberately bounded by this: one question, one
    second chance, then quiet. Counted from the durable record rather than
    memory, so a redeploy cannot reset it into nagging.
    """
    goal = (goal or "").strip()
    if not goal:
        return 0
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=within_hours)).strftime("%Y-%m-%d %H:%M:%S")
        filt = f'kind="anticipy_says" && decision="needs_user" && created>="{since}"'
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 50, "sort": "-created"}, timeout=10)
        if not getattr(r, "ok", False):
            return 0
        return sum(1 for ev in r.json().get("items", [])
                   if (ev.get("goal") or "").strip() == goal)
    except Exception:
        return 0


def need_already_asked(goal: str, blocker: str, within_hours: float = 24.0,
                       covered: float = 0.5, owner_ref: str = "") -> bool:
    """Has she already told him what THIS task is waiting for?

    Keying on the task alone was wrong in a way that only shows up on the
    second round. If he answers part of what a form wants, the task resumes,
    the browser gets further and stops on something else — and a task-keyed
    guard would keep her quiet about the new thing for the rest of the day.
    The task would die silently, which is the exact failure the stuck-job ask
    exists to prevent.

    So compare against the BLOCKER — the browser's own words about what it
    needs, which are stable — and ask whether a message she already sent
    about this task covered it. Her own wording is generated fresh every time
    and is useless for this; the requirement is not."""
    goal, blocker = (goal or "").strip(), (blocker or "").strip()
    if not goal or not blocker:
        return False
    want = _content_words(blocker)
    if not want:
        return False
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=within_hours)).strftime("%Y-%m-%d %H:%M:%S")
        filt = f'kind="anticipy_says" && created>="{since}"'
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 100, "sort": "-created"}, timeout=10)
        if not r.ok:
            return False
        for ev in r.json().get("items", []):
            if (ev.get("goal") or "").strip() != goal:
                continue
            text = ev.get("text", "")
            said = _content_words(text)
            if said and len(want & said) / len(want) >= covered:
                return True
            # Word overlap misses a paraphrase (live, 2026-08-10: the same
            # parked booking was re-asked every 45 minutes, freshly worded
            # each time). Every ask now carries the blocker's hard facts
            # exactly, so a prior needs_user ask whose facts match IS this
            # question, whatever the words around them. A new requirement has
            # new facts and still gets raised.
            if (ev.get("decision") == "needs_user"
                    and _fact_tokens(blocker)
                    and carries_facts(text, blocker)):
                return True
    except Exception as e:
        print(f"need_already_asked check failed: {e}")
    return False


def already_raised(goal: str, text: str = "", within_hours: float = 24.0,
                   decision: str | None = None, owner_ref: str = "") -> bool:
    """Has she already brought THIS up with him?

    Keyed on the task, not the sentence. Her wording is generated fresh every
    time, so comparing text was never going to hold: on 2026-08-02 the same
    blocked booking produced "I'm almost done booking Cactus Club… I just need
    your first name" and then "I'm setting up that Cactus Club reservation
    now. Can you send over your first name" — plainly the same ask, far enough
    apart in words to slip a similarity threshold, and he got both.

    Falls back to text comparison only when there is no goal to key on."""
    goal = (goal or "").strip()
    if not goal:
        return already_said(text, within_hours=within_hours,
                            owner_ref=owner_ref)
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=within_hours)).strftime("%Y-%m-%d %H:%M:%S")
        filt = f'kind="anticipy_says" && created>="{since}"'
        # "act" and "clock" are two mouths on the same face: a plan raised by
        # a held-plan text must immunize the clock, and vice versa. On
        # 2026-08-05 the held dinner text went out (decision="act"), then the
        # clock — checking only its own class — texted "just confirming for
        # tomorrow night, what time and where…" about the very same dinner.
        if decision in ("act", "clock"):
            filt += ' && (decision="act" || decision="clock")'
        elif decision:
            filt += f' && decision="{decision}"'
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 100, "sort": "-created"},
                   timeout=10)
        if not r.ok:
            return False
        # The goal is model-phrased fresh each time ("book dinner for 2 at
        # Cactus…" vs "confirm the Cactus Club plan for tomorrow"), so exact
        # equality was a guard that never fired across rephrasings. Same
        # word-overlap idea the job queue uses.
        want = goal_tokens(goal)
        for ev in r.json().get("items", []):
            other = (ev.get("goal") or "").strip()
            if not other:
                continue
            if other == goal:
                return True
            have = goal_tokens(other)
            if (want and have
                    and len(want & have) / min(len(want), len(have)) >= 0.6):
                return True
        return False
    except Exception as e:
        print(f"already_raised check failed: {e}")
        return False


def already_said(text: str, within_hours: float = 24.0, overlap: float = 0.6,
                 owner_ref: str = "") -> bool:
    """Has she already sent essentially this message recently?

    She does not repeat herself. Every unprompted message is checked against
    what she has ACTUALLY sent — read back from the events collection, not
    from an in-RAM set that a redeploy wipes. On 2026-08-01 the same
    "car insurance renewal" text went out twice, hours apart, because the
    only guard was `reached_loop_ids` and that depended on the model
    remembering to echo an id back; when it didn't, nothing was recorded and
    the loop was fair game again on the next tick, forever.

    Replies are deliberately NOT deduped — if he asks the same thing twice he
    deserves an answer twice. This is only for messages she starts."""
    mine = _content_words(text)
    if not mine:
        return False
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=within_hours)).strftime("%Y-%m-%d %H:%M:%S")
        filt = f'kind="anticipy_says" && created>="{since}"'
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 100, "sort": "-created"}, timeout=10)
        if not r.ok:
            return False
        for ev in r.json().get("items", []):
            prev = _content_words(ev.get("text", ""))
            if not prev:
                continue
            shared = len(mine & prev) / max(1, min(len(mine), len(prev)))
            if shared >= overlap:
                return True
    except Exception as e:
        # Never let the dedup check itself block a genuine message.
        print(f"already_said check failed: {e}")
    return False


# What triage decided is stamped on every outbound event, so a question can be
# deduped against earlier QUESTIONS and a held job against earlier HELD JOBS,
# without one silencing the other.
_KIND_TO_DECISION = {"ask": "ask", "act": "act", "clock": "clock",
                     "ambient_act": "act"}


# She has raised it twice and he has not resolved it. A third time is not
# diligence, it is nagging, and it is the difference between an assistant and
# an alarm clock. Deliberately small: two is one more chance than one.
NAG_LIMIT = 2
# Long enough to span the way a real question actually decays. The Cactus
# dinner was raised on the 4th, the 5th and the 6th, each time as a brand-new
# open loop with a brand-new id, so every same-day guard passed cleanly.
NAG_WINDOW_DAYS = 14
# How much of the goal a past message must cover to be about the same thing.
NAG_OVERLAP = 0.34


def raised_and_ignored(goal: str, text: str = "", owner_ref: str = "") -> bool:
    """Has she already put this to him more than once, and got nowhere?

    Every existing guard is same-day and keyed on an open loop's ID. A loop
    gets a fresh id each time the subject comes up in conversation, so the
    same dinner produced a new loop on three consecutive days and every guard
    waved it through:

      Aug 4 15:02  "just checking in about our plan to go to Cactus today..."
      Aug 4 21:32  "Just confirming for the dinner reservation, what date..."
      Aug 5 01:57  "just confirming for tomorrow night, what time and where..."
      Aug 5 21:35  "Just confirming for dinner tomorrow at Cactus Park at 7"
      Aug 6 01:37  "Just confirming for tomorrow: Cactus Club Park Royal at 2:07 PM?"

    So this asks the only question that actually generalises: how many times
    have I said something about THIS, ever. Not "today", and not keyed to an
    id that changes. Silence, twice over, is an answer.
    """
    goal = (goal or "").strip()
    if not goal:
        return False
    want = _content_words(goal)
    if not want:
        return False
    try:
        since = (datetime.now(timezone.utc)
                 - timedelta(days=NAG_WINDOW_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        filt = f'kind="anticipy_says" && created>="{since}"'
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": _scoped_filter(filt, owner_ref),
                           "perPage": 200, "sort": "-created"}, timeout=10)
        if not r.ok:
            return False
        seen = 0
        for ev in r.json().get("items", []):
            said = _content_words((ev.get("goal") or "") + " " + (ev.get("text") or ""))
            shared = want & said
            # Measured on the real five, against four real unrelated subjects.
            # Same dinner scored 0.29, 0.43, 0.57, 0.71, 0.71; Marcus, the car
            # insurance, the Priya email and the headphones all scored 0.00.
            # The gap is the whole width of the range, so the threshold sits
            # in it rather than at either edge — and only two hits are needed,
            # so catching four of the five is ample. The absolute floor stops
            # a short goal from tripping on one generic word.
            if len(shared) >= 2 and len(shared) / len(want) >= NAG_OVERLAP:
                seen += 1
                if seen >= NAG_LIMIT:
                    return True
    except Exception as e:
        print(f"nag check failed: {e}")
    return False


# When a transcript line was last heard. A question asked INTO a live
# conversation is a question asked about a sentence that has not finished.
LAST_HEARD_AT = 0.0
# How long a conversation stays "still going" after the last line. The flush
# ceiling cuts speech into pieces every 8 seconds, so anything shorter would
# call the gaps between a person's own fragments the end of their turn.
LIVE_CONVERSATION_S = 14.0


def SPEAK_ONCE(text: str, goal: str = "", kind: str = "") -> bool:
    """May she say this unprompted? Only if she has not already — and, for
    speech born from OVERHEARD plans (kind="ambient_act"), only in waking
    hours. He never invited that text, so it obeys the same quiet hours as
    the clock; the card is already on his desk either way, and the morning
    clock pass raises anything still waiting. A direct ask keeps texting at
    any hour — answering him is a reply, not an interruption."""
    # DO NOT ASK INTO A SENTENCE THAT IS STILL ARRIVING. Watched live
    # 2026-08-16: "...should grab dinner tomorrow at like 6 PM for" triaged on
    # its own, so she asked "which restaurant, and for how many people?" —
    # and four seconds later the next fragment said "let's do Earls". She had
    # asked for something he was in the middle of saying. Deferring costs one
    # cycle; the card stays, the later fragments merge into it, and she asks
    # only about what is genuinely still missing.
    if kind == "ask" and LAST_HEARD_AT:
        if time.time() - LAST_HEARD_AT < LIVE_CONVERSATION_S:
            return "defer"
    if kind == "ambient_act":
        hour = datetime.now(CLOCK_TZ).hour
        if CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END:
            # NOT NOW is not NEVER: a plan made at midnight is still a plan.
            # A plain False here reads as a dedupe refusal and the core
            # cancels the card — every late-night plan would silently vanish.
            return "defer"
    # NAGGING IS OUTREACH SHE STARTED. It is not a question that is blocking
    # work HE started seconds ago.
    #
    # The first cut of this applied to every kind, and within hours it ate the
    # thing it was never meant to touch: he said "I've gotta email Priya the
    # invoice", the sufficiency check correctly asked WHICH Priya — and the nag
    # limit swallowed the question, because the words "Priya", "email" and
    # "invoice" had come up twice already that day. He got a card that said
    # "Quick question for you" and no question.
    #
    # All five Cactus messages were kind="clock": she woke up and decided to
    # raise something. That is the thing being limited. An "ask" is the
    # opposite — he set the work in motion and she cannot finish without an
    # answer. Silencing that does not stop nagging, it strands the task.
    #
    # An overheard plan (kind="ambient_act") belongs on the "he started it"
    # side of that line, not the nag side. He spoke a NEW plan seconds ago;
    # her one text about it is the receipt for that plan, not a third
    # unprompted knock about an old one. Keying it into the nag count meant
    # any subject she had ever raised twice became permanently untextable:
    # a genuinely fresh dinner made out loud produced a held card that was
    # then CANCELLED because days-old texts about a previous dinner had used
    # up the quota. The pending-card merge is what stops a repeated mention
    # from texting twice.
    if kind == "clock" and raised_and_ignored(goal, text):
        print(f"quiet: already put this to him twice with no answer -> {goal[:60]!r}")
        return False
    # For an overheard plan the CARD is the dedupe, and it is a better one:
    # a re-mention of a plan she is already holding merges into the pending
    # card inside _queue_job and never reaches this guard at all — only a
    # genuinely NEW card earns speech. Word-overlap against yesterday's texts
    # is the wrong key for this kind: a brand-new dinner plan shares most of
    # its words with the last dinner plan, and matching on them silenced the
    # text and then cancelled the card. Three times, live, in one day —
    # each a different guard doing the same wrong thing.
    if kind == "ambient_act":
        return True
    return not already_raised(goal, text,
                              decision=_KIND_TO_DECISION.get(kind))


def _brain_fingerprint() -> str:
    """A short hash of the code that decides what she does.

    Printed at startup so "the fix is live" is something the log PROVES rather
    than something a deploy status implies. Compare it against
    `python3 -c "from brain.worker import _brain_fingerprint; print(_brain_fingerprint())"`
    run on the commit you believe you shipped; if they differ, the container is
    running something else.

    Never raises: a fingerprint that cannot be computed must not stop the
    worker from starting.
    """
    import hashlib
    here = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha256()
    # Every module in the brain counts — conversation.py and memory.py
    # changed once with no fingerprint movement, which silently defeated
    # the whole "the log PROVES it" idea.
    for name in sorted(n for n in os.listdir(here) if n.endswith(".py")):
        try:
            with open(os.path.join(here, name), "rb") as f:
                h.update(f.read())
        except Exception:
            return "unknown"
    return h.hexdigest()[:12]


BATCH = 20
# Read a little wider than the slice, because the re-sort below can only
# reorder rows it can see: if the page is exactly the slice, a line spoken
# first but delivered last sits on page two and is read out of sequence
# anyway. ADDITIVE, not a multiplier — a previous attempt at this pattern
# elsewhere used `limit * 8` and turned a 7-line read into 56 rows.
PAGE = BATCH + 8
# A phone whose clock is off by more than this is not telling us the time,
# it is telling us about its timezone configuration. One naive-local-time
# build is enough to reorder someone's whole day, so past this we stop
# believing the stamp instead of acting on it.
CLOCK_SKEW_MAX_S = 6 * 3600


def _ts(value) -> float | None:
    """PocketBase and the app both hand us ISO-8601; neither is guaranteed."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def capture_key(ev: dict) -> float:
    """When it was SAID, falling back to when it arrived.

    The phone buffers — offline, backgrounded, no signal, a call holding the
    mic — and then flushes a lump. Ordering by PocketBase's `created` orders
    by the moment the network delivered the row, so a flushed backlog reaches
    the brain shuffled, and a plan reconstructed from shuffled turns is a
    different plan. Omi ships this exact bug (their #6551) and fixed it by
    serialising their writes; our worker is already single-threaded, so for
    us it was only ever the wrong clock.

    Degrades in both directions on purpose. No stamp (every build before this
    one) -> arrival time, i.e. exactly today's behaviour. Implausible stamp ->
    arrival time, so a device with a broken clock cannot reorder his day.
    """
    arrived = _ts(ev.get("created"))
    # `capture_started_at` is the canonical column and the one the phone now
    # writes; `spoken_at` is accepted too so that either name works during a
    # rollout and neither is silently ignored.
    spoken = _ts(ev.get("capture_started_at")) or _ts(ev.get("spoken_at"))
    if spoken is None:
        return arrived if arrived is not None else 0.0
    if arrived is not None and abs(spoken - arrived) > CLOCK_SKEW_MAX_S:
        return arrived
    return spoken


def resolve_owner_ref(legacy_owner: str = "") -> str:
    """Map the pre-account device UUID to the canonical owners record id."""
    configured = os.environ.get("ANTICIPY_OWNER_REF", "").strip()
    if configured:
        return configured
    if not legacy_owner:
        return ""
    try:
        escaped = legacy_owner.replace('"', '\\"')
        r = pb.get(f"{PB}/api/collections/owners/records",
                   params={"filter": f'legacy_uuid="{escaped}"',
                           "perPage": 2}, timeout=10)
        items = r.json().get("items", []) if r.ok else []
        return items[0].get("id", "") if len(items) == 1 else ""
    except Exception:
        return ""


def fetch_unprocessed(kind: str = "transcript", owner_ref: str = "") -> list[dict]:
    if not owner_ref:
        # Fail closed. The former unscoped poll could hear every person's
        # transcript in the shared database as one owner's life.
        return []
    r = pb.get(
        f"{PB}/api/collections/events/records",
        params={"filter": (f'kind="{kind}" && decision="" '
                           f'&& owner_ref="{owner_ref}"'),
                "perPage": PAGE, "sort": "created"},
        timeout=10,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    # Sorted here rather than by PocketBase: `spoken_at` is absent on rows
    # from every build before this one, and an empty string sorts to one end
    # of a server-side sort — which would silently bury exactly the oldest
    # lines rather than ordering them.
    items.sort(key=capture_key)
    return items[:BATCH]


# How many earlier lines the model is shown to point at. 40 is the window
# the masked-hierarchical-transformer disentanglement work uses; wider costs
# tokens on every heard line and buys little, because a line that continues
# something 40 turns back will almost always continue something nearer too.
LINK_WINDOW = 40
# Off by default. The verdict is written to the record and read by nothing,
# so production behaviour is identical either way — but the switch means the
# extra prompt tokens are opt-in until the scoring says they earn their keep.
LINKS_ON = os.environ.get("ANTICIPY_LINKS", "").lower() in ("1", "true", "on")


def link_candidates(kind: str = "transcript", owner_ref: str = "") -> list[tuple[str, str]]:
    """Recent heard lines as (id, text), oldest first, for the link question.

    Blanks are dropped HERE, where ids and texts leave together, so the two
    can never drift: the model answers with a 1-based index into this list
    and the mapping back to an id is positional. Filtering anywhere further
    down would shift every number after the gap and mis-link silently.
    """
    try:
        r = pb.get(
            f"{PB}/api/collections/events/records",
            params={"filter": _scoped_filter(f'kind="{kind}"', owner_ref),
                    "perPage": LINK_WINDOW + 8,
                    "sort": "-created"},
            timeout=10,
        )
        r.raise_for_status()
        rows = r.json().get("items", [])
    except Exception:
        return []                     # no candidates -> question never asked
    rows.sort(key=capture_key)        # speech order, not delivery order
    out = [(row.get("id") or "", (row.get("text") or "").strip())
           for row in rows]
    return [(i, t) for i, t in out if i and t][-LINK_WINDOW:]


def resolve_link(idx, event_id: str,
                 cands: list[tuple[str, str]]) -> str | None:
    """Turn the model's 1-based index into the id to store, or None.

    Extracted from the poll loop so it can be tested: the mapping is
    positional, and an off-by-one here links every line to the wrong parent
    with no symptom anyone would notice. 0 means "starts something new" and
    is stored as a self-link, because "she decided this was new" and "she
    never answered" must stay distinguishable in the record.
    """
    if idx is None or not cands:
        return None
    if idx == 0:
        return event_id
    if 1 <= idx <= len(cands):
        return cands[idx - 1][0]
    return None


def record_link(event_id: str, parent_id: str) -> None:
    """Write which line this one carries on from. Best effort on purpose:
    nothing reads it yet, and a failed PATCH here must never cost the line
    itself — the decision has already been acted on by this point."""
    try:
        pb.patch(f"{PB}/api/collections/events/records/{event_id}",
                 json={"parent_line": parent_id}, timeout=10)
    except Exception as e:
        print(f"link: {event_id} -> {parent_id} failed: {e}")


def stamp_for(decision: str, said) -> str:
    """What to write on the transcript row, given what she actually said.

    AN ASK THAT ASKED NOTHING IS NOT AN ASK.

    2026-08-07, live. He planned dinner out loud with another person. The
    pendant hears one side, so it read as thinking aloud, and the self-talk
    rule held the question back. Holding it is CORRECT — loosening that rule
    the same afternoon produced FOUR texts for one dinner and SIX for the Earls
    plan, and was reverted.

    But the row was still stamped "ask", and the feed renders any "ask" as the
    header "Quick question for you". He got that header with no question under
    it and no text. The silence was right; the card claiming a question was the
    lie.

    Quiet work already has a stamp: decision="ignore" carrying the goal, which
    the app has rendered as "Looking into it" since the Paris-flights incident.
    A held-back question is exactly that — she has the plan, she is carrying
    it, she is not tugging his sleeve. Nothing server-side reads "ask" off a
    transcript row, so this needs no app update and is correct on the build
    already on his phone.

    Only "ask" is ever rewritten, and only when there is genuinely nothing to
    show. Everything else is returned untouched.
    """
    if decision != "ask":
        return decision
    text = said if isinstance(said, str) else ""
    return "ask" if text.strip() else "ignore"


def mark_processed(event_id: str, decision: str, addressee: str = "",
                   goal: str = "") -> bool:
    """Returns whether the mark actually landed. A silently-failed PATCH left
    the event unmarked and the 2s poll replayed it — minting a duplicate job
    and a duplicate text per cycle.

    The addressee (who the owner was judged to be talking to) is stamped
    alongside the decision so a misclassification — a dictated line that
    fired, a direct ask that went ambient — is auditable from the record.

    The goal is stamped too when work came of the line — including QUIET
    work, where the outward decision stays "ignore". That pairing
    (decision=ignore + a goal) is how the app tells "left alone" from
    "looking into it, quietly": Omar watched her research Paris flights
    behind a "Noted — nothing needed" label and reasonably concluded she
    did nothing and it landed nowhere. Old app builds ignore the field —
    they keep rendering exactly what they render today."""
    try:
        body = {"decision": decision}
        if addressee:
            body["addressee"] = addressee
        if goal:
            body["goal"] = goal
        r = pb.patch(f"{PB}/api/collections/events/records/{event_id}",
                     json=body, timeout=10)
        return bool(getattr(r, "ok", False))
    except Exception:
        return False


def claim(event_id: str) -> bool:
    """Take the event BEFORE doing side effects. If this fails we skip the
    event this cycle rather than acting twice on it."""
    return mark_processed(event_id, "processing")


def handle_inbound(ev: dict, convo, anticipy) -> str:
    """Handle ONE answer from the owner, whichever channel it arrived on.

    Extracted from main()'s loop so it can be tested against the real thing.
    proof/test_never_silent.py used to re-type this logic into its own harness
    and then grep worker.py for a `print` to confirm the real code still had the
    guard -- which is a test of a copy plus a test of a string. Anything that
    drives this function is testing what production runs.

    Returns the decision it recorded, for the log and for tests.
    """
    in_app = ev.get("kind") == "app_reply"
    lane = "app in" if in_app else "sms in"
    text = ev.get("text", "").strip()
    # One conversation key for both channels (docs leg 2 "IT WAS ONE
    # CONVERSATION"). The app sends no phone, so it uses the owner's own number
    # and lands in the SAME thread his texts do; answering in the app continues
    # the conversation rather than starting a second one beside it.
    phone = ev.get("goal", "").strip() or anticipy.owner_phone
    if in_app:
        phone = anticipy.owner_phone or f"app:{anticipy.owner_ref}"
    if not text:
        mark_processed(ev["id"], "ignore")
        return "ignore"

    # ONLY the owner may steer the queue, and the two channels prove that
    # differently -- neither proof substitutes for the other.
    #
    # SMS: Twilio's token proves the webhook is Twilio, NOT who texted. Without
    # this check any stranger (or a wrong number) texting "yes" releases a held
    # job into the owner's browser, "no" cancels it, and Anticipy replies to
    # them with the owner's private pending list.
    #
    # App: the row could only exist if a signed-in account created it --
    # backend/pb_hooks/guard.pb.js:159 accepts a POST to `events` only when
    # `owner_ref === authId`, so an account cannot write a row stamped with
    # someone else's owner_ref. With fetch_unprocessed()'s owner scoping, the
    # row IS the proof of who typed it. Demanding same_phone() here as well
    # would refuse every answer from an owner who has given no phone number,
    # which is the entire point of answering in the app.
    if not in_app and not same_phone(phone, anticipy.owner_phone):
        mark_processed(ev["id"], "ignored_nonowner")
        print(f"{lane}: from non-owner {phone!r} — ignored")
        return "ignored_nonowner"
    if not claim(ev["id"]):
        print(f"{lane}: could not claim, retrying later")
        return "unclaimed"

    # An answer typed in the app is answered in the app. This is NOT a ruling on
    # whether SMS is primary or a backstop -- that question stays open -- only
    # that a reply belongs on the channel the answer arrived on.
    deliver = convo.reply_in_app() if in_app else contextlib.nullcontext()
    with deliver:
        try:
            out = convo.on_reply(phone, text)
        except Exception as e:
            mark_processed(ev["id"], "error")
            print(f"{lane}: {text!r} -> error: {e}")
            # He answered and heard nothing back -- and because the event is
            # marked processed it will never be retried, so the silence is
            # permanent. That is exactly what he lived on 2026-08-01: "yea grab
            # it pls" and "I want to see the Odyssey at Cineplex Park Royal"
            # both hit an exception and simply vanished. Whatever broke, he
            # gets an answer.
            try:
                reply = anticipy._voice({
                    "situation": "your own reasoning just failed on their "
                                 "message and you have no idea what they "
                                 "wanted — own it briefly and ask them to "
                                 "say it again",
                    "their_message": text,
                }) or ("Something went wrong on my end just then — "
                       "can you send that again?")
                convo.say(phone, reply)
                # The apology has to reach the app too, or answering in the app
                # and hitting an error is the same silence in a new place.
                if in_app:
                    post_event("anticipy_text", reply)
            except Exception as e2:
                print(f"{lane}: could not even apologise: {e2}")
            return "error"

    mark_processed(ev["id"], out["intent"])
    # How an in-app reply is DELIVERED: the app reads this row. The SMS lane has
    # already sent by now and records it here too, so both channels leave one
    # history rather than two (docs leg 2).
    post_event("anticipy_text", out["reply"])
    print(f"{lane}: {text!r} -> {out['intent']}")
    return out["intent"]


def release_stranded_claims(owner_ref: str = "", older_than_minutes: int = 10) -> int:
    """Give back events claimed by a worker that never finished them.

    claim() stamps decision="processing" before any side effect, and
    fetch_unprocessed only ever selects decision="" — so a restart between
    the claim and the outcome stranded that event PERMANENTLY. There was no
    sweep, no lease and no expiry anywhere, and restarts are routine (every
    deploy is one). The words a person actually said were simply never
    understood, and nothing anywhere said so.

    Ten minutes is far longer than a triage cycle and far shorter than a
    person's patience.
    """
    if not owner_ref:
        return 0
    cutoff = (datetime.now(timezone.utc)
              - timedelta(minutes=older_than_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        r = pb.get(
            f"{PB}/api/collections/events/records",
            params={"filter": (f'decision="processing" && owner_ref="{owner_ref}" '
                               f'&& updated<="{cutoff}"'),
                    "perPage": 100, "sort": "created"},
            timeout=10)
        items = (r.json() or {}).get("items", []) if getattr(r, "ok", False) else []
    except Exception:
        return 0
    freed = 0
    for item in items:
        try:
            back = pb.patch(
                f"{PB}/api/collections/events/records/{item['id']}",
                json={"decision": ""}, timeout=10)
            if getattr(back, "ok", False):
                freed += 1
        except Exception:
            continue
    if freed:
        print(f"released {freed} event(s) stranded mid-understanding by a restart")
    return freed


def ask_about_stuck_jobs(anticipy, convo) -> None:
    """Text the owner about anything the browser handed back, once each.

    The agent reports exactly what it needs ("I need your birthday to finish
    the reservation"); she puts that in her own words and asks. His reply
    comes back through the normal SMS path, where the answer is remembered
    and the job resumes — so nothing has to be pre-programmed per field."""
    try:
        filt = 'status="needs_user"'
        scope = owner_filter(anticipy)
        if scope:
            filt += f" && {scope}"
        r = pb.get(f"{PB}/api/collections/jobs/records",
                   params={"filter": filt, "perPage": 5, "sort": "-updated"}, timeout=10)
        if not r.ok:
            return
        for job in r.json().get("items", []):
            # There used to be an in-RAM ASKED_ABOUT set here, marked before
            # any other check. It defeated the very guard written to replace
            # it: need_already_asked() exists so that a task blocking on a
            # NEW requirement can be raised again, and a set keyed on job id
            # made that impossible for the life of the process. A guard that
            # makes her permanently mute is the one thing no guard may do.
            blocker = (job.get("result") or "").strip()
            if not blocker:
                continue
            # An ambient job that hit a wall does not earn a text — he never
            # asked for it. It stays visible in the app, nothing more.
            if ambient_job(job):
                continue
            # Cheapest guard FIRST. This whole block used to compose the
            # message before deciding whether to send it, so every poll of a
            # stuck job burned a model call whose output was then discarded.
            # The cooldown is for a question REPEATED. It must never swallow
            # something new — and the most important message this path ever
            # sends is the draft of something about to go out in his name,
            # which arrives on the same job and the same goal as whatever was
            # asked before it. Quiet only when we are about to say the same
            # thing again.
            if (_last_blocker.get(job["id"]) == blocker
                    and asked_about_recently(job.get("goal", ""))):
                print(f"stuck job {job['id']}: same thing again moments ago, staying quiet")
                continue
            # Both guards above end at the same durable record, and that
            # record is written AFTER the text goes out. When the write fails
            # — a PocketBase restart, the nightly backup holding the write
            # lock — the text has been sent and nothing knows it, so two
            # seconds later this reads "never asked" and asks again. This one
            # asks the process what it actually sent, so an unrecordable
            # question is asked once instead of every two seconds. Keyed on
            # the blocker, so a NEW requirement still speaks immediately, and
            # short enough that the three-hour second chance still happens.
            local_key = f'stuck:{job["id"]}:{blocker}'
            if sent_moments_ago(local_key):
                print(f"stuck job {job['id']}: that exact ask went out moments "
                      f"ago (its record may not have landed), staying quiet")
                continue
            # The durable record survives restarts and deploys. Check it before
            # composing: production once spent a model call every three seconds
            # rewriting a question this exact guard then threw away.
            # SILENCE MUST HAVE A DEADLINE.
            #
            # The guard's whole window was 24 hours, so ONE question that did
            # not land — missed, or (until tonight) recorded as sent when the
            # transport had nobody to send to — bought a full day of quiet
            # while the job sat parked. From the outside that is
            # indistinguishable from the system being broken, and it is the
            # loop he named: "why are we always in this infinite stall?"
            #
            # So a still-parked job gets a SECOND chance after three hours,
            # and then genuine silence. Not nagging — the six-messages-about
            # -one-email failure is still in living memory — but a single
            # honest re-ask, because a question nobody heard is not a
            # question asked.
            asks_already = asks_for_goal(job.get("goal", ""), anticipy.owner_ref)

            # THE CEILING THE COMMENT ABOVE ALREADY PROMISES.
            #
            # need_already_asked deliberately keys on the BLOCKER rather than
            # the task, and for a good reason it states: when he answers half
            # a form and the browser then stops on something genuinely NEW, a
            # task-keyed guard would stay silent and the job would die quietly.
            #
            # But a stuck run describes the SAME obstacle differently every
            # time it retries — "which location works best", "needs you to
            # check something on the site", "stalled after what looks like a
            # pop-up", "got stuck and needs a site check". Every one of those
            # is a new blocker to the guard, so every retry texted him again.
            # His actual log: 136 of 200 messages were this one path, 63 in a
            # single day, the same booking, one every twenty minutes.
            #
            # asks_for_goal already counts what it needs — it was only used to
            # widen a window, which a freshly-worded blocker walks straight
            # past. Past the ceiling the honest thing is not another text: the
            # card is in his feed, and he has already been told twice.
            if asks_already >= STUCK_ASKS_CEILING:
                print(f"stuck job {job['id']}: asked {asks_already}x about "
                      f"{job.get('goal','')[:40]!r} already — the feed has it, "
                      f"staying quiet")
                continue

            # I ALSO TRIED PUTTING QUIET HOURS ON THIS PATH AND TOOK IT BACK
            # OUT. He does get 06:59 texts, and that looks wrong — but this
            # path is not an uninvited finding, it is HIS OWN errand blocked
            # on one detail, and test_backlog_and_delivery proves the
            # deliberate decision that a genuinely new requirement speaks AT
            # ONCE. Deferring a blocked booking nine hours can kill the
            # errand outright, and his actual complaint was volume, not the
            # hour. Silencing it would have been the same mistake as the
            # rules that fire on a proxy instead of the real condition.
            # Whether a blocked errand should wait until morning is his call
            # to make, not one to smuggle in beside a volume fix.

            window = 24.0 if asks_already >= 2 else 3.0
            if need_already_asked(job.get("goal", ""), blocker,
                                  within_hours=window,
                                  owner_ref=anticipy.owner_ref):
                print(f"stuck job {job['id']}: already asked for this, staying quiet")
                continue
            # Same distinction as the finished-job reporter, for the same
            # measured reason: with no number on the account this composed a
            # fresh ask on every sweep and notify_owner discarded every one of
            # them ("send failed, not recording it as said", forever). Nothing
            # here can change until a phone number does, so do not pay for the
            # sentence.
            #
            # Held under its own local key, never under local_key itself:
            # nothing was sent, so a number arriving mid-window must let the
            # real ask go out at once rather than serve out a suppression it
            # never earned. The key exists only so this lands in the log once
            # instead of every two seconds.
            #
            # AND THIS ONE DOES *NOT* FALL BACK TO THE FEED, unlike the
            # finished-job reporter above. Weighed and rejected, twice over:
            #
            #   1. It is already there. A needs_user job carries the blocker
            #      in its own `result`, and the app renders exactly that —
            #      popup.js: `needs_user: (e) => "I stopped and I need you:
            #      ${e}"`, with Start-a-fresh-attempt beside it. An
            #      anticipy_says row would put the same obstacle on the same
            #      screen a second time in her voice. A finished job's answer
            #      is nowhere until she says it; a stuck job's question is
            #      already on his desk.
            #   2. It would eat the real ask. These records ARE the durable
            #      dedup: need_already_asked and asks_for_goal read them back
            #      as proof she asked. Writing one while nothing was sent
            #      makes the next 3 hours "already asked" — so a number added
            #      to the account mid-window would be met with silence, the
            #      one thing the note above exists to prevent — and three
            #      parked sweeps would spend the whole STUCK_ASKS_CEILING
            #      budget without a single question ever reaching him.
            #
            # So the answer of a finished job goes to the feed, and the
            # question of a parked one waits for a channel that can carry a
            # reply. Duplicating a card in order to lie to a dedup guard is
            # not delivery.
            if not can_reach_owner(anticipy):
                nowhere_key = f"unreachable:{local_key}"
                if not sent_moments_ago(nowhere_key):
                    mark_sent(nowhere_key)
                    print(f"stuck job {job['id']}: nowhere to send this — no "
                          f"phone on this account, not composing")
                continue
            said = anticipy._voice({
                "situation": "you got most of the way through a task in their browser "
                             "and need one thing from them to finish. Carry the facts "
                             "below EXACTLY — every number, time, date and name in "
                             "what_you_need must survive into your text unchanged",
                "task": job.get("goal", ""),
                "what_you_need": blocker,
            })
            # Her paraphrase is voice, not authority: if it dropped or invented
            # a number/time/date, the facts go out verbatim instead. Live,
            # 2026-08-10: "showing 6:30 PM, task is tomorrow at noon" was
            # rewritten as "I'm gonna drive at 6:30. I can change it for
            # tomorrow" — word salad about a booking he was waiting on.
            # The facts she may use are the blocker's AND the task's: the
            # model is shown both, so a sentence mentioning the 6 PM from the
            # goal is not an invention. Judging it against the blocker alone
            # rejected nearly every natural sentence — which is why he kept
            # getting the identical canned line and said, correctly, "feel
            # like it's hard-coded" (2026-08-16).
            allowed = f"{blocker} {job.get('goal', '')}"
            if said and not (carries_facts(said, blocker)
                             or (_fact_tokens(blocker) <= _fact_tokens(said)
                                 and _fact_tokens(said) <= _fact_tokens(allowed))):
                print(f"stuck job {job['id']}: paraphrase mangled the facts, "
                      f"asking again with them pinned")
                said = anticipy._voice({
                    "situation": "you got most of the way through a task in "
                                 "their browser and need one thing to finish. "
                                 "Your reply MUST contain, character for "
                                 "character, every number, time, date and name "
                                 "in what_you_need. Write it the way a person "
                                 "texts, not a status line.",
                    "task": job.get("goal", ""),
                    "what_you_need": blocker,
                })
                if said and not (carries_facts(said, blocker)
                                 or (_fact_tokens(blocker) <= _fact_tokens(said)
                                     and _fact_tokens(said) <= _fact_tokens(allowed))):
                    said = None
            said = said or f"I'm nearly through {job.get('goal', 'that')} — {blocker}"
            # What she actually sent is the durable record — a set in memory
            # would forget across a redeploy and re-ask for his name and email.
            # Only record it if it actually left the building. notify_owner
            # swallows transport failures and returns None; recording anyway
            # turned a refused send into 24 hours of silence about that task,
            # because the dedup guard reads these records as proof she spoke.
            if not anticipy.notify_owner(said):
                print(f"stuck job {job['id']}: send failed, not recording it as said")
                continue
            _last_blocker[job["id"]] = blocker
            mark_sent(local_key)
            post_event("anticipy_says", said, decision="needs_user",
                       goal=job.get("goal", ""))
            print(f"asked about stuck job {job['id']}: {said[:80]}")
    except Exception as e:
        print(f"stuck-job ask failed: {e}")


def main() -> None:
    global ACTIVE_OWNER_REF, ACTIVE_OWNER_ID, CLOCK_TZ
    legacy_owner = os.environ.get("ANTICIPY_OWNER_ID", "").strip()
    owner_ref = resolve_owner_ref(legacy_owner)
    if not owner_ref:
        print("ERROR: canonical owner_ref is unresolved — refusing to start an "
              "unscoped worker")
        return
    ACTIVE_OWNER_REF = owner_ref
    ACTIVE_OWNER_ID = legacy_owner
    # The owner's own zone and name, from their profile — so every prompt is
    # grounded in THEIR time of day, THEIR city, and the fact that THEY are the
    # one reading whatever gets composed. Read once at startup and refreshed on
    # the same beat as the phone number below; unknown simply means the old
    # server-default behaviour.
    owner_zone = fetch_owner_timezone(owner_ref)
    llm = LLM(owner_zone=owner_zone,
              owner_name=fetch_owner_first_name(owner_ref))
    if owner_zone:
        try:
            CLOCK_TZ = ZoneInfo(owner_zone)
        except Exception:
            print(f"owner timezone is invalid, using {CLOCK_TZ}: {owner_zone!r}")
    mem_db = os.environ.get("ANTICIPY_MEMORY_DB", ":memory:")
    memory = Memory(path=mem_db, llm=llm if llm.live else None)
    anticipy = Anticipy(llm=llm if llm.live else None, memory=memory, backend_url=PB,
                        # Second line of defence behind the supervisor's pop():
                        # a SUPERVISED child never falls back to an inherited
                        # number. Texting the wrong person is worse in every
                        # case than not texting at all.
                        owner_phone=("" if os.environ.get("ANTICIPY_SUPERVISED") == "1"
                                     else os.environ.get("ANTICIPY_OWNER_PHONE", "owner")),
                        owner_id=legacy_owner, owner_ref=owner_ref)
    # Live texting when Twilio credentials are present; mock otherwise. The
    # credential may be an API key OR the auth token, so the gate asks the one
    # place that knows (brain/voice_arm.py `has_credentials`) instead of listing
    # variable names here and drifting from it.
    live_sms = has_credentials()
    voice = VoiceArm() if live_sms else None
    if voice:
        anticipy.voice = voice
    convo = Conversation(anticipy, transport=TwilioTransport(voice) if voice else MockTransport())
    anticipy.conversation = convo
    # Observation only in step 1; a failure here must never touch hearing.
    #
    # OFF means explicitly off, and nothing else does. This read used to be
    # `== "1"`, which fails silently OPEN in the one direction that matters:
    # proof/local_rig.sh exported ANTICIPY_SEGMENTS as a FILE PATH (copying the
    # shape of ANTICIPY_MEMORY_DB and ANTICIPY_CLOCK_STATE, which really are
    # paths), a path is not "1", and so the whole segment store was None on the
    # rig. Every local conversation was heard as isolated lines with no context
    # across them - for a product whose entire premise is understanding ordinary
    # multi-turn speech - and it logged nothing to say so. Found 2026-08-20 by
    # the ambient corpus run, after the store had been dark for the whole of
    # local testing. A stray value must never switch a subsystem off in silence.
    _seg = os.environ.get("ANTICIPY_SEGMENTS", "1").strip().lower()
    segments = None if _seg in ("0", "false", "no", "off", "") else \
        SegmentStore(PB, owner=anticipy.owner_id, owner_ref=anticipy.owner_ref)
    # A fingerprint of the brain that is ACTUALLY running, printed at startup.
    #
    # "Deployed" has meant "Railway said RUNNING" up to now, which is a claim
    # about a container, not about the code inside it. Twice today that gap
    # mattered. This hashes the source of the two files that decide what she
    # does, so the log proves which build is live instead of implying it.
    print(f"worker up · llm={'live:' + llm.model if llm.live else 'heuristic'}"
          # "sms=live" is load-bearing text, not a nicety: proof/local_rig.sh:180
          # greps for it and kills a laptop worker that has live credentials. The
          # credential goes in its own field so that assertion keeps matching —
          # after a key is minted, the only way to know whether outbound really
          # moved off the full-access auth token is to read it off the process.
          f" · sms={'live' if live_sms else 'mock'}"
          f"{' · auth=' + voice.credential if voice else ''} · pb={PB}"
          f" · where={llm.owner_zone or 'server-default:' + str(TZ_FALLBACK)}"
          f" · who={llm.owner_name or 'unknown'}"
          f" · brain={_brain_fingerprint()}")
    if not anticipy.owner_id:
        # Paired extensions only claim their owner's jobs, so unstamped jobs
        # would sit queued forever with nothing reporting a problem.
        print("WARNING: ANTICIPY_OWNER_ID is unset — queued jobs will carry no "
              "owner and NO browser agent will ever claim them.")
    if not same_phone(anticipy.owner_phone, anticipy.owner_phone):
        print("WARNING: ANTICIPY_OWNER_PHONE is not a usable phone number — "
              "every inbound text will be ignored as non-owner.")
    if mem_db == ":memory:":
        # AMNESIA HAS TO ANNOUNCE ITSELF.
        #
        # A supervised worker always gets a real file: supervisor.py:91-93
        # writes ANTICIPY_MEMORY_DB into every child environment. So this is
        # the hand-started shape — `python -m brain.worker` in a terminal —
        # which is how the demos and nearly all live debugging are run. The
        # default stays as it is on purpose (nothing is created on disk, and
        # two experiments cannot contaminate each other's memory), but the
        # process then has NO long-term memory while every other log line
        # reads perfectly normal: commitments are stored, answered from, and
        # then evaporate on exit. That shape gets diagnosed as "she forgot the
        # whole conversation, the graph must be broken" when the actual cause
        # is one unset environment variable, so it must be impossible to miss
        # in the log the operator is already reading.
        print("WARNING: ANTICIPY_MEMORY_DB is unset — long-term memory is in "
              "RAM ONLY and dies with this process. Nothing she learns will "
              "survive a restart. Point it at a file path (the supervisor "
              "does that for every worker it spawns).")

    last_clock = 0.0
    last_profile = 0.0
    last_webhook = 0.0
    while True:
        try:
            # Pick up the owner's number from the app (and any change to it)
            # without a redeploy.
            if time.time() - last_profile > 60:
                last_profile = time.time()
                entered = fetch_owner_phone(anticipy.owner_ref)
                if entered and entered != anticipy.owner_phone:
                    anticipy.owner_phone = entered
                    print(f"owner phone updated from the app: …{entered[-4:]}")
                # Day zero: a brand-new owner's first proactive touch — one
                # welcome, stamped durably, never repeated.
                if anticipy.owner_phone:
                    maybe_welcome_new_owner(anticipy, _clock_state())
                # Same beat for the zone: somebody travels, or onboards after
                # the worker started, and every prompt should follow them
                # without a redeploy.
                zone = fetch_owner_timezone(anticipy.owner_ref)
                if zone and zone != llm.owner_zone:
                    llm.owner_zone = zone
                    try:
                        CLOCK_TZ = ZoneInfo(zone)
                    except Exception:
                        pass
                    print(f"owner timezone updated from the app: {zone}")
                # And the name, on the same beat and for the same reason: a
                # worker that started before onboarding finished otherwise
                # composes for the whole day without knowing who it is
                # writing to.
                first = fetch_owner_first_name(anticipy.owner_ref)
                if first and first != llm.owner_name:
                    llm.owner_name = first
                    print(f"owner first name from the app: {first}")
                # What onboarding collected becomes profile knowledge on the
                # same beat — she should know his name from minute one.
                seed_profile_identity(memory, owner_ref=anticipy.owner_ref)
                # And what the PHONE read off its own calendar and contacts.
                # Same beat, same swallow-on-failure posture; these arrive as
                # `profile` events so they reach memory without being triaged
                # into errands.
                ingest_profile_events(memory, owner_ref=anticipy.owner_ref)
                # And what a SUPERVISED READ concluded, plus any fact the owner
                # tapped away while watching. Same beat and same posture: a
                # read that fails to land must never take hearing down with it.
                # ingest_read_facts applies pending vetoes before it writes
                # anything, so a tap during the read cannot be undone by the
                # facts arriving a moment behind it.
                ingest_read_facts(memory, owner_ref=anticipy.owner_ref)
            # Is the number still wired to us? Cheap, and the failure it
            # catches is invisible from in here — she simply never hears him.
            manages_webhook = (os.environ.get("ANTICIPY_SUPERVISED") != "1" or
                               os.environ.get("ANTICIPY_WEBHOOK_MANAGER") == "1")
            if manages_webhook and time.time() - last_webhook > WEBHOOK_CHECK_EVERY_SECONDS:
                last_webhook = time.time()
                ensure_inbound_webhook()
            # The clock: she reviews her open loops on her own schedule and
            # may initiate — rarely, in daytime, rate-limited, gated.
            now = time.time()
            if now - last_clock >= CLOCK_EVERY_SECONDS:
                last_clock = now
                state = _clock_state()
                # Hearing wins over initiative.  A transcript that is already
                # waiting must be interpreted before the clock can speak from
                # memory; otherwise her brand-new output can precede and then
                # falsely echo-match the older input on a replay.
                has_pending_input = bool(fetch_unprocessed(
                    owner_ref=anticipy.owner_ref))
                if not has_pending_input and clock_should_run(now, state):
                    out = anticipy.clock_tick(
                        now, already_reached_out=set(state.get("reached_loop_ids", [])),
                        may_say=SPEAK_ONCE)
                    if out:
                        state["last_outreach_ts"] = now
                        state["reached_loop_ids"] = list(
                            set(state.get("reached_loop_ids", [])) | set(out["loop_ids"]))
                        _save_clock_state(state)
                        post_event("anticipy_says", out["say"], decision="clock",
                                   goal=out.get("goal") or "")
                        print(f"clock: initiated -> {out['say']!r}")
            # Hand back anything a previous life claimed and never finished,
            # BEFORE asking for new work — otherwise a deploy silently eats
            # whatever was mid-understanding at the moment it happened.
            release_stranded_claims(anticipy.owner_ref)
            for ev in fetch_unprocessed(owner_ref=anticipy.owner_ref):
                line = ev.get("text", "").strip()
                # Mark that this person is mid-conversation, so a question
                # born from one fragment waits for the sentence to finish.
                global LAST_HEARD_AT
                LAST_HEARD_AT = time.time()
                if not line:
                    mark_processed(ev["id"], "ignore")
                    continue
                # A crash mid-hear must not leave the event unmarked: the poll
                # would replay it every 2s, minting a duplicate job (and SMS)
                # per attempt — this happened live on 2026-07-30 (6 jobs from
                # one line when the owner-notify SMS failed).
                # Claim first: hear() queues jobs and sends texts, so a
                # post-hoc mark that fails means the whole thing runs again.
                if not claim(ev["id"]):
                    print(f"heard: {line!r} -> could not claim, retrying later")
                    continue
                # Her own words, read back at her, are not an instruction. He
                # does this constantly while testing and every time she has
                # treated it as a fresh order: she texted "the August data is
                # ready to add in the spreadsheet", he said that sentence out
                # loud, and she minted a second job from it. Checked before
                # triage, so it costs a cheap read instead of a model call.
                if is_echo_of_her(line, before=capture_key(ev)):
                    mark_processed(ev["id"], "ignore")
                    print(f"heard: {line!r} -> that is her own message read back, ignoring")
                    continue
                # What was already said in this conversation, so a question
                # never arrives stripped of what it was about.
                convo_context = []
                open_seg = None
                if segments is not None:
                    try:
                        open_seg = segments.open_segment()
                        if open_seg:
                            convo_context = segments.recent_turns(open_seg["id"])
                    except Exception:
                        convo_context = []
                # Which earlier line does this one carry on from? Asked as
                # part of the triage call that already runs, so it costs no
                # extra request. `cands` is the index space the model answers
                # into; it excludes this line itself, because a line cannot
                # continue itself and offering it would invite exactly that.
                cands = []
                if LINKS_ON:
                    cands = [c for c in link_candidates(owner_ref=anticipy.owner_ref)
                             if c[0] != ev["id"]]
                try:
                    # The phone's local voice verdict rides along when the
                    # app stamped one (owner|other); absent on old builds.
                    # capture_source rides along the same way and answers a
                    # different question: WHICH MICROPHONE produced this line
                    # (phone_mic | pendant | typed), read straight off the
                    # event row the app wrote. It is the whole basis of the
                    # pendant-versus-phone comparison, and it is empty on all
                    # 2209 historical rows and on any app build that does not
                    # stamp it. Empty means UNKNOWN, so the core leaves the
                    # key off the job entirely rather than writing a blank
                    # that would read like a measured result.
                    out = anticipy.hear(line, context=convo_context,
                                        may_say=SPEAK_ONCE,
                                        explicit=bool(ev.get("explicit")),
                                        capture_source=(ev.get("source") or ""),
                                        speaker=(ev.get("speaker") or None),
                                        link_candidates=[t for _, t in cands]
                                        or None,
                                        source_event_id=ev["id"],
                                        lineage_key=(open_seg.get("id")
                                                     if open_seg else ev["id"]))
                except TypeError:
                    # An older core keeps hearing. This retry deliberately
                    # passes ONLY the four kwargs hear() has had since the
                    # beginning, so it survives a core that lacks ANY of the
                    # ones added since — speaker, links, lineage, and now
                    # capture_source. Nothing new may be added to this call:
                    # its entire value is that it cannot itself raise
                    # TypeError. The cost is that the fallback line is heard
                    # with no provenance and no voice verdict, which is the
                    # correct trade when the alternative is not hearing it.
                    out = anticipy.hear(line, context=convo_context,
                                        may_say=SPEAK_ONCE,
                                        explicit=bool(ev.get("explicit")))
                except Exception as e:
                    mark_processed(ev["id"], "error")
                    print(f"heard: {line!r} -> error: {e}")
                    continue
                # Store the link. A self-link (points at its own id) is the
                # "starts something new" answer, and it is written down just
                # as explicitly as a continuation — the difference between
                # "she decided this was new" and "she never answered" has to
                # survive into the record, or the scoring cannot tell them
                # apart either.
                parent = resolve_link(
                    getattr(out["decision"], "continues", None),
                    ev["id"], cands)
                if parent:
                    record_link(ev["id"], parent)
                decision = stamp_for(out["decision"].decision,
                                     out.get("anticipy_says"))
                if decision != out["decision"].decision:
                    print("ask with nothing to ask -> filing as quiet work, "
                          "not a question he never got")
                mark_processed(ev["id"], decision,
                               addressee=getattr(out["decision"], "addressee",
                                                 "") or "",
                               goal=getattr(out["decision"], "goal", "") or "")
                # STEP 1 of the capture architecture: record which
                # conversation this turn belongs to. NOTHING reads it yet —
                # triage above is untouched — so this is observation only,
                # here to prove the boundaries land where real conversations
                # actually start and stop before anything depends on them.
                if segments is not None:
                    try:
                        placed = place_turn(segments, ev)
                        print(f"segment: {placed.get('decision')} "
                              f"({placed.get('why')}) seg={placed.get('segment','-')}")
                    except Exception as e:
                        print(f"segment: skipped ({e})")
                if out.get("anticipy_says"):
                    post_event("anticipy_says", out["anticipy_says"],
                               decision=decision,
                               goal=out["decision"].goal or "",
                               source=(ev.get("source") or ""))
                print(f"heard: {line!r} -> {decision}"
                      f" ({out['decision'].goal or 'no goal'})")

            # THE one answer path. An owner answers a question by text (Twilio
            # webhook -> pb_hooks -> events) or by typing into the app (the app
            # writes the row itself), and both arrive at the single `on_reply`
            # inside handle_inbound().
            #
            # Deliberately one path rather than two, because brief ex 120 is
            # explicit that a second path to a decision this one already owns is
            # the bug: the 2026-08-02 two-blocked-tasks failure came from an
            # answer that resolved nothing, and Conversation._resume_stuck is
            # the only resolution. A parallel in-app implementation would have
            # to reimplement release, cancel, refinement and the stuck-task
            # resume, and would drift from this one the first time either moved.
            for ev in fetch_unprocessed("sms_reply", anticipy.owner_ref) + \
                    fetch_unprocessed("app_reply", anticipy.owner_ref):
                handle_inbound(ev, convo, anticipy)

            # The research lane runs HERE, in this process. Read-only goals
            # never wait for — or touch — his browser (roadmap §6).
            run_research_jobs(anticipy)

            # A stuck job must SPEAK. When the browser hands something back —
            # it needs a detail she doesn't have, hit a login wall, found the
            # facts changed — she texts him the question. Without this she
            # goes silent and the task simply dies in a queue he isn't
            # watching, which is the difference between an assistant and a
            # form that failed.
            ask_about_stuck_jobs(anticipy, convo)

            # And when it IS finished, he hears the answer. A question that
            # gets no reply is worse than one she refuses.
            report_finished_jobs(anticipy)

            # And when nothing can run at all, say that too rather than
            # leaving a task queued behind a browser that is not open.
            report_stalled_work(anticipy)

            # Nightly, while he sleeps: distill the day's episodes into
            # profile facts (roadmap §1). Incremental and idempotent — a
            # crash or redeploy resumes at the cursor, never repeats.
            run_nightly_consolidation(memory)

            anticipy.review_loops()
        except requests.RequestException as e:
            print(f"backend unreachable: {e}")
        except Exception as e:
            print(f"worker error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
