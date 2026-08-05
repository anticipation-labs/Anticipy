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

from .anticipy_core import Anticipy
from .memory import Memory
from .segmenter import SegmentStore, place_turn
from .conversation import Conversation, MockTransport, TwilioTransport
from .llm import LLM
from .voice_arm import VoiceArm

PB = os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")
POLL_SECONDS = 2

# ---- the clock: time-fired proactivity, with guardrails OUTSIDE the model
CLOCK_EVERY_SECONDS = 30 * 60
CLOCK_MIN_GAP_SECONDS = 4 * 3600      # at most one unprompted outreach per 4h
CLOCK_TZ = ZoneInfo(os.environ.get("ANTICIPY_TZ", "America/Vancouver"))
CLOCK_QUIET_START, CLOCK_QUIET_END = 22, 8   # never initiate at night
CLOCK_STATE = os.environ.get("ANTICIPY_CLOCK_STATE", "/data/clock_state.json")


def fetch_owner_phone() -> str | None:
    """The owner's number as THEY entered it in the app. Falls back to the
    env var so an existing deployment keeps working, but the app is now the
    source of truth — nobody should have to hand-edit a server variable to
    make their own assistant able to text them."""
    try:
        r = pb.get(f"{PB}/api/collections/owner_profile/records",
                   params={"sort": "-updated", "perPage": 1}, timeout=10)
        if not r.ok:
            return None
        items = r.json().get("items", [])
        phone = (items[0].get("phone") or "").strip() if items else ""
        return phone or None
    except Exception:
        return None


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
    smstok = os.environ.get("ANTICIPY_SMS_TOKEN")
    number = os.environ.get("TWILIO_PHONE_NUMBER") or os.environ.get("TWILIO_FROM")
    if not (sid and auth and smstok and number):
        return          # not our job to guess; stay quiet
    ours = f"{PB}/sms/inbound?token={smstok}"
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
        if current.split("?")[0] == ours.split("?")[0] and not shadowed:
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


def post_event(kind: str, text: str, decision: str = "", goal: str = "") -> None:
    pb.post(f"{PB}/api/collections/events/records", json={
        "device_id": "anticipy-brain", "kind": kind, "text": text,
        "decision": decision, "goal": goal or "",
    }, timeout=10)


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


def browser_reachable() -> bool:
    """Is his Chrome actually there to do the work?

    Nothing in the brain ever asked. A resumed task goes to `queued` and waits
    for the extension to claim it — so if he answers from his phone with the
    laptop shut, she says "I'll finish the booking now" and then nothing
    happens, forever, with no word to him. Answering by text away from the
    desk is the normal case, not the edge case."""
    try:
        r = pb.get(f"{PB}/api/collections/agents/records",
                   params={"filter": "paired=true", "sort": "-updated",
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
        if anticipy.owner_id:
            filt = f'({filt}) && owner="{anticipy.owner_id}"'
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
        if anticipy.owner_id:
            filt = f'({filt}) && owner="{anticipy.owner_id}"'
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
            claim = pb.patch(
                f"{base}/api/collections/jobs/records/{job['id']}",
                json={"status": "running", "claimed_by": RESEARCH_CLAIMANT,
                      "claimed_at": datetime.now(timezone.utc)
                      .strftime("%Y-%m-%d %H:%M:%S")},
                timeout=10)
            if not getattr(claim, "ok", False):
                continue
            check = pb.get(f"{base}/api/collections/jobs/records/{job['id']}",
                           timeout=10)
            if not getattr(check, "ok", False):
                continue
            fresh = check.json()
            if fresh.get("claimed_by") != RESEARCH_CLAIMANT \
                    or fresh.get("status") != "running":
                continue
            try:
                params = json.loads(job.get("params") or "{}") or {}
            except Exception:
                params = {}
            out = (runner or research.run_research)(
                job.get("goal", ""), params, llm=anticipy.llm, api_key=api_key)
            ok = bool(out.get("ok"))
            pb.patch(f"{base}/api/collections/jobs/records/{job['id']}",
                     json={"status": "done" if ok else "failed",
                           "result": (out.get("result") or "")[:6000]},
                     timeout=10)
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
        if anticipy.owner_id:
            filt = f'({filt}) && owner="{anticipy.owner_id}"'
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
                if result and not failed and not already_raised(goal, decision="done"):
                    post_event("anticipy_says", result, decision="done", goal=goal)
                REPORTED.add(job["id"])
                print(f"ambient job {job['id']} finished quietly ({job.get('status')})")
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


def need_already_asked(goal: str, blocker: str, within_hours: float = 24.0,
                       covered: float = 0.5) -> bool:
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
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": f'kind="anticipy_says" && created>="{since}"',
                           "perPage": 100, "sort": "-created"}, timeout=10)
        if not r.ok:
            return False
        for ev in r.json().get("items", []):
            if (ev.get("goal") or "").strip() != goal:
                continue
            said = _content_words(ev.get("text", ""))
            if said and len(want & said) / len(want) >= covered:
                return True
    except Exception as e:
        print(f"need_already_asked check failed: {e}")
    return False


def already_raised(goal: str, text: str = "", within_hours: float = 24.0,
                   decision: str | None = None) -> bool:
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
        return already_said(text, within_hours=within_hours)
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
                   params={"filter": filt, "perPage": 100, "sort": "-created"},
                   timeout=10)
        if not r.ok:
            return False
        # The goal is model-phrased fresh each time ("book dinner for 2 at
        # Cactus…" vs "confirm the Cactus Club plan for tomorrow"), so exact
        # equality was a guard that never fired across rephrasings. Same
        # word-overlap idea the job queue uses.
        want = {w for w in re.findall(r"[a-z0-9']+", goal.lower()) if len(w) > 3}
        for ev in r.json().get("items", []):
            other = (ev.get("goal") or "").strip()
            if not other:
                continue
            if other == goal:
                return True
            have = {w for w in re.findall(r"[a-z0-9']+", other.lower()) if len(w) > 3}
            if (want and have
                    and len(want & have) / min(len(want), len(have)) >= 0.6):
                return True
        return False
    except Exception as e:
        print(f"already_raised check failed: {e}")
        return False


def already_said(text: str, within_hours: float = 24.0, overlap: float = 0.6) -> bool:
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
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": f'kind="anticipy_says" && created>="{since}"',
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


def SPEAK_ONCE(text: str, goal: str = "", kind: str = "") -> bool:
    """May she say this unprompted? Only if she has not already — and, for
    speech born from OVERHEARD plans (kind="ambient_act"), only in waking
    hours. He never invited that text, so it obeys the same quiet hours as
    the clock; the card is already on his desk either way, and the morning
    clock pass raises anything still waiting. A direct ask keeps texting at
    any hour — answering him is a reply, not an interruption."""
    if kind == "ambient_act":
        hour = datetime.now(CLOCK_TZ).hour
        if CLOCK_QUIET_START <= hour or hour < CLOCK_QUIET_END:
            return False
    return not already_raised(goal, text,
                              decision=_KIND_TO_DECISION.get(kind))


def fetch_unprocessed(kind: str = "transcript") -> list[dict]:
    r = pb.get(
        f"{PB}/api/collections/events/records",
        params={"filter": f'kind="{kind}" && decision=""',
                "perPage": 20, "sort": "created"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("items", [])


def mark_processed(event_id: str, decision: str, addressee: str = "") -> bool:
    """Returns whether the mark actually landed. A silently-failed PATCH left
    the event unmarked and the 2s poll replayed it — minting a duplicate job
    and a duplicate text per cycle.

    The addressee (who the owner was judged to be talking to) is stamped
    alongside the decision so a misclassification — a dictated line that
    fired, a direct ask that went ambient — is auditable from the record."""
    try:
        body = {"decision": decision}
        if addressee:
            body["addressee"] = addressee
        r = pb.patch(f"{PB}/api/collections/events/records/{event_id}",
                     json=body, timeout=10)
        return bool(getattr(r, "ok", False))
    except Exception:
        return False


def claim(event_id: str) -> bool:
    """Take the event BEFORE doing side effects. If this fails we skip the
    event this cycle rather than acting twice on it."""
    return mark_processed(event_id, "processing")


def ask_about_stuck_jobs(anticipy, convo) -> None:
    """Text the owner about anything the browser handed back, once each.

    The agent reports exactly what it needs ("I need your birthday to finish
    the reservation"); she puts that in her own words and asks. His reply
    comes back through the normal SMS path, where the answer is remembered
    and the job resumes — so nothing has to be pre-programmed per field."""
    try:
        filt = 'status="needs_user"'
        if anticipy.owner_id:
            filt += f' && owner="{anticipy.owner_id}"'
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
            said = anticipy._voice({
                "situation": "you got most of the way through a task in their browser "
                             "and need one thing from them to finish",
                "task": job.get("goal", ""),
                "what_you_need": blocker,
            }) or f"I'm nearly through {job.get('goal', 'that')} — {blocker}"
            # What she actually sent is the durable record — a set in memory
            # would forget across a redeploy and re-ask for his name and email.
            if need_already_asked(job.get("goal", ""), blocker):
                print(f"stuck job {job['id']}: already asked for this, staying quiet")
                continue
            # Only record it if it actually left the building. notify_owner
            # swallows transport failures and returns None; recording anyway
            # turned a refused send into 24 hours of silence about that task,
            # because the dedup guard reads these records as proof she spoke.
            if not anticipy.notify_owner(said):
                print(f"stuck job {job['id']}: send failed, not recording it as said")
                continue
            post_event("anticipy_says", said, decision="needs_user",
                       goal=job.get("goal", ""))
            print(f"asked about stuck job {job['id']}: {said[:80]}")
    except Exception as e:
        print(f"stuck-job ask failed: {e}")


def main() -> None:
    llm = LLM()
    mem_db = os.environ.get("ANTICIPY_MEMORY_DB", ":memory:")
    memory = Memory(path=mem_db, llm=llm if llm.live else None)
    anticipy = Anticipy(llm=llm if llm.live else None, memory=memory, backend_url=PB,
                        owner_phone=os.environ.get("ANTICIPY_OWNER_PHONE", "owner"),
                        owner_id=os.environ.get("ANTICIPY_OWNER_ID", ""))
    # Live texting when Twilio credentials are present; mock otherwise.
    live_sms = all(os.environ.get(k) for k in
                   ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"))
    voice = VoiceArm() if live_sms else None
    if voice:
        anticipy.voice = voice
    convo = Conversation(anticipy, transport=TwilioTransport(voice) if voice else MockTransport())
    anticipy.conversation = convo
    # Observation only in step 1; a failure here must never touch hearing.
    segments = SegmentStore(PB, owner=anticipy.owner_id) \
        if os.environ.get("ANTICIPY_SEGMENTS", "1") == "1" else None
    print(f"worker up · llm={'live:' + llm.model if llm.live else 'heuristic'}"
          f" · sms={'live' if live_sms else 'mock'} · pb={PB}")
    if not anticipy.owner_id:
        # Paired extensions only claim their owner's jobs, so unstamped jobs
        # would sit queued forever with nothing reporting a problem.
        print("WARNING: ANTICIPY_OWNER_ID is unset — queued jobs will carry no "
              "owner and NO browser agent will ever claim them.")
    if not same_phone(anticipy.owner_phone, anticipy.owner_phone):
        print("WARNING: ANTICIPY_OWNER_PHONE is not a usable phone number — "
              "every inbound text will be ignored as non-owner.")

    sent_seen = 0
    last_clock = 0.0
    last_profile = 0.0
    last_webhook = 0.0
    while True:
        try:
            # Pick up the owner's number from the app (and any change to it)
            # without a redeploy.
            if time.time() - last_profile > 60:
                last_profile = time.time()
                entered = fetch_owner_phone()
                if entered and entered != anticipy.owner_phone:
                    anticipy.owner_phone = entered
                    print(f"owner phone updated from the app: …{entered[-4:]}")
            # Is the number still wired to us? Cheap, and the failure it
            # catches is invisible from in here — she simply never hears him.
            if time.time() - last_webhook > WEBHOOK_CHECK_EVERY_SECONDS:
                last_webhook = time.time()
                ensure_inbound_webhook()
            # The clock: she reviews her open loops on her own schedule and
            # may initiate — rarely, in daytime, rate-limited, gated.
            now = time.time()
            if now - last_clock >= CLOCK_EVERY_SECONDS:
                last_clock = now
                state = _clock_state()
                if clock_should_run(now, state):
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
            for ev in fetch_unprocessed():
                line = ev.get("text", "").strip()
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
                # What was already said in this conversation, so a question
                # never arrives stripped of what it was about.
                convo_context = []
                if segments is not None:
                    try:
                        open_seg = segments.open_segment()
                        if open_seg:
                            convo_context = segments.recent_turns(open_seg["id"])
                    except Exception:
                        convo_context = []
                try:
                    out = anticipy.hear(line, context=convo_context,
                                        may_say=SPEAK_ONCE)
                except Exception as e:
                    mark_processed(ev["id"], "error")
                    print(f"heard: {line!r} -> error: {e}")
                    continue
                decision = out["decision"].decision
                mark_processed(ev["id"], decision,
                               addressee=getattr(out["decision"], "addressee",
                                                 "") or "")
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
            for ev in fetch_unprocessed("sms_reply"):
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

            # Surface anything she "texted" (mock transport) into the feed too.
            sent = getattr(convo.transport, "sent", None)
            if sent is not None:
                for msg in sent[sent_seen:]:
                    post_event("anticipy_text", msg["body"])
                sent_seen = len(sent)

            anticipy.review_loops()
        except requests.RequestException as e:
            print(f"backend unreachable: {e}")
        except Exception as e:
            print(f"worker error: {e}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
