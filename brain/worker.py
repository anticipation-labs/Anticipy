"""Anticipy brain worker — the server-side mind loop.

The phone posts raw transcript lines to PocketBase (`events`, kind
"transcript"). This worker is the one place they all flow through:
each line -> Anticipy.hear() -> memory graph + triage + (held) job, then the
decision and anything Anticipy wants to say are written back as events the
app renders in its feed. It also closes loops as jobs finish.

Run:  .venv/bin/python -m brain.worker
"""
from __future__ import annotations

import json
import os
import re
import time
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
from .voice_arm import VoiceArm
from .workflow import (claim as claim_plan, fail as fail_plan,
                       from_params as workflow_from_params,
                       put_in_params, succeed as succeed_plan)

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


def ensure_inbound_webhook() -> None:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth = os.environ.get("TWILIO_AUTH_TOKEN")
    number = os.environ.get("TWILIO_PHONE_NUMBER") or os.environ.get("TWILIO_FROM")
    if not (sid and auth and number):
        return          # not our job to guess; stay quiet
    ours = (os.environ.get("ANTICIPY_TWILIO_WEBHOOK_URL") or
            f"{PB.rstrip('/')}/sms/inbound")
    try:
        r = requests.get(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers.json",
            auth=(sid, auth), timeout=15)
        if not r.ok:
            return
        rows = [n for n in r.json().get("incoming_phone_numbers", [])
                if n.get("phone_number") == number]
        if not rows:
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
              f"{' (shadowed by an application SID)' if shadowed else ''} — pointing it back at us")
        u = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers/{n['sid']}.json",
            auth=(sid, auth), timeout=15,
            data={"SmsUrl": ours, "SmsMethod": "POST", "SmsApplicationSid": ""})
        print("webhook repointed" if u.ok else f"could not repoint the webhook: {u.status_code}")
    except Exception as e:
        # This must never be able to stop her hearing or texting.
        print(f"webhook check failed (harmless): {e}")


def post_event(kind: str, text: str, decision: str = "", goal: str = "",
               owner_ref: str = "", owner_id: str = "") -> None:
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


def deliver_fyi(anticipy, goal: str, result: str, overheard: bool) -> bool:
    """Text him what she found — her words, varied every time, one text.

    Returns whether the text actually went out. That return value is not
    bookkeeping: "held for morning" and "delivered" used to be the same
    silent None, so the caller marked a held FYI as delivered and the
    morning never came. Quiet hours are ten hours long, so every overheard
    lookup that finished overnight was destroyed rather than deferred —
    exactly the "I'll text you what I find" that never arrives. A caller
    that gets False must leave the finding undelivered so a later sweep
    can send it.

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
        anticipy.notify_owner(say)
    except Exception as e:
        print(f"fyi text failed (feed still has it): {e}")
    # Attempted and concluded. Only a quiet-hours HOLD (above) reports False:
    # that is a deferral with a morning to come, and it is the one case the
    # caller must not record as delivered. A send that was tried and failed
    # keeps its existing behaviour — the feed carries it — because retrying a
    # hard failure on every two-second sweep is a different decision than the
    # bug being fixed here.
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
            post_event("anticipy_says", said, decision="stalled", goal=goal)
            print(f"stalled (no browser): {job['id']} — told him")
    except Exception as e:
        print(f"stalled-work report failed: {e}")


RESEARCH_CLAIMANT = "worker-research"


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
                        actor_id=RESEARCH_CLAIMANT)
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
                continue
            # Delivery is report_finished_jobs' job: a desk card by default,
            # an in-thread text only when the ask came in over SMS.
            print(f"research: {job['id']} {'done' if ok else 'failed'} — "
                  f"{job.get('goal', '')[:60]}")
    except Exception as e:
        print(f"research pass failed: {e}")


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
        r = pb.get(f"{PB}/api/collections/jobs/records",
                   params={"filter": filt, "perPage": 10, "sort": "-updated"},
                   timeout=10)
        if not r.ok:
            return
        for job in r.json().get("items", []):
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
                # Checked BEFORE already_raised on purpose: that call is a
                # round trip, and re-asking it about every held job on every
                # two-second sweep would run all night for an answer that
                # cannot change until 08:00.
                hour = datetime.now(CLOCK_TZ).hour
                if result and not failed and (CLOCK_QUIET_START <= hour
                                              or hour < CLOCK_QUIET_END):
                    continue
                if result and not failed and not already_raised(goal, decision="done"):
                    # A held FYI is not a delivered one. Recording the feed
                    # event and marking the job reported are what make this
                    # finding "already raised" forever, so both must wait
                    # until the text has actually gone out — otherwise every
                    # overheard lookup that finished between 22:00 and 08:00
                    # was silently destroyed instead of held.
                    if not deliver_fyi(anticipy, goal, result, overheard=True):
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
                    post_event("anticipy_says", result, decision="done", goal=goal)
                REPORTED.add(job["id"])
                print(f"ambient job {job['id']} finished — fyi'd and on the feed")
                continue
            # Durable: has she already delivered THIS result? Keyed on the goal
            # and on being a result, so her earlier "want me to?" about the same
            # task does not silence the answer.
            if already_raised(goal, decision="done"):
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
                    deliver_fyi(anticipy, goal, result, overheard=False)
                post_event("anticipy_says", said, decision="done", goal=goal)
                REPORTED.add(job["id"])
                print(f"desk: research {job['status']} {job['id']} — {goal[:60]}")
                continue
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
            if not anticipy.notify_owner(said):
                print(f"result for {job['id']}: send failed, not recording it as said")
                continue
            post_event("anticipy_says", said,
                       decision="done", goal=goal)
            REPORTED.add(job["id"])
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
            window = 24.0 if asks_already >= 2 else 3.0
            if need_already_asked(job.get("goal", ""), blocker,
                                  within_hours=window,
                                  owner_ref=anticipy.owner_ref):
                print(f"stuck job {job['id']}: already asked for this, staying quiet")
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
    # The owner's own zone, from their profile — so every prompt is grounded in
    # THEIR time of day and THEIR city, not the server's. Read once at startup
    # and refreshed on the same beat as the phone number below; unknown simply
    # means the old server-default behaviour.
    owner_zone = fetch_owner_timezone(owner_ref)
    llm = LLM(owner_zone=owner_zone)
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
    # Live texting when Twilio credentials are present; mock otherwise.
    live_sms = all(os.environ.get(k) for k in
                   ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"))
    voice = VoiceArm() if live_sms else None
    if voice:
        anticipy.voice = voice
    convo = Conversation(anticipy, transport=TwilioTransport(voice) if voice else MockTransport())
    anticipy.conversation = convo
    # Observation only in step 1; a failure here must never touch hearing.
    segments = SegmentStore(PB, owner=anticipy.owner_id,
                            owner_ref=anticipy.owner_ref) \
        if os.environ.get("ANTICIPY_SEGMENTS", "1") == "1" else None
    # A fingerprint of the brain that is ACTUALLY running, printed at startup.
    #
    # "Deployed" has meant "Railway said RUNNING" up to now, which is a claim
    # about a container, not about the code inside it. Twice today that gap
    # mattered. This hashes the source of the two files that decide what she
    # does, so the log proves which build is live instead of implying it.
    print(f"worker up · llm={'live:' + llm.model if llm.live else 'heuristic'}"
          f" · sms={'live' if live_sms else 'mock'} · pb={PB}"
          f" · where={llm.owner_zone or 'server-default:' + str(TZ_FALLBACK)}"
          f" · brain={_brain_fingerprint()}")
    if not anticipy.owner_id:
        # Paired extensions only claim their owner's jobs, so unstamped jobs
        # would sit queued forever with nothing reporting a problem.
        print("WARNING: ANTICIPY_OWNER_ID is unset — queued jobs will carry no "
              "owner and NO browser agent will ever claim them.")
    if not same_phone(anticipy.owner_phone, anticipy.owner_phone):
        print("WARNING: ANTICIPY_OWNER_PHONE is not a usable phone number — "
              "every inbound text will be ignored as non-owner.")

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
                # What onboarding collected becomes profile knowledge on the
                # same beat — she should know his name from minute one.
                seed_profile_identity(memory, owner_ref=anticipy.owner_ref)
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
                    out = anticipy.hear(line, context=convo_context,
                                        may_say=SPEAK_ONCE,
                                        explicit=bool(ev.get("explicit")),
                                        speaker=(ev.get("speaker") or None),
                                        link_candidates=[t for _, t in cands]
                                        or None,
                                        source_event_id=ev["id"],
                                        lineage_key=(open_seg.get("id")
                                                     if open_seg else ev["id"]))
                except TypeError:
                    # An older core without the speaker kwarg keeps hearing.
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
                               decision=decision, goal=out["decision"].goal or "")
                print(f"heard: {line!r} -> {decision}"
                      f" ({out['decision'].goal or 'no goal'})")

            # Inbound texts (Twilio webhook -> pb_hooks -> events) flow through
            # the same conversation the pendant path uses; the reply goes back
            # out over the live transport.
            for ev in fetch_unprocessed("sms_reply", anticipy.owner_ref):
                text = ev.get("text", "").strip()
                phone = ev.get("goal", "").strip() or anticipy.owner_phone
                if not text:
                    mark_processed(ev["id"], "ignore")
                    continue
                # ONLY the owner may steer the queue. Twilio's token proves the
                # webhook is Twilio, NOT who texted: without this, any stranger
                # (or a wrong number) texting "yes" releases a held job into
                # the owner's browser, "no" cancels it, and Anticipy replies
                # to them with the owner's private pending list.
                if not same_phone(phone, anticipy.owner_phone):
                    mark_processed(ev["id"], "ignored_nonowner")
                    print(f"sms in: from non-owner {phone!r} — ignored")
                    continue
                if not claim(ev["id"]):
                    print("sms in: could not claim, retrying later")
                    continue
                try:
                    out = convo.on_reply(phone, text)
                except Exception as e:
                    mark_processed(ev["id"], "error")
                    print(f"sms in: {text!r} -> error: {e}")
                    # He texted and heard nothing back — and because the event
                    # is marked processed it will never be retried, so the
                    # silence is permanent. That is exactly what he lived on
                    # 2026-08-01: "yea grab it pls" and "I want to see the
                    # Odyssey at Cineplex Park Royal" both hit an exception and
                    # simply vanished. Whatever broke, he gets an answer.
                    try:
                        convo.say(phone, anticipy._voice({
                            "situation": "your own reasoning just failed on their "
                                         "message and you have no idea what they "
                                         "wanted — own it briefly and ask them to "
                                         "say it again",
                            "their_message": text,
                        }) or "Something went wrong on my end just then — "
                              "can you send that again?")
                    except Exception as e2:
                        print(f"sms in: could not even apologise: {e2}")
                    continue
                mark_processed(ev["id"], out["intent"])
                post_event("anticipy_text", out["reply"])
                print(f"sms in: {text!r} -> {out['intent']}")

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
