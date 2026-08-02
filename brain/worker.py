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
            # Durable: has she already delivered THIS result? Keyed on the goal
            # and on being a result, so her earlier "want me to?" about the same
            # task does not silence the answer.
            if already_raised(goal, decision="done"):
                REPORTED.add(job["id"])
                continue
            if not result and not failed:
                continue
            said = anticipy._voice({
                "situation": ("you tried to do this for them and it did not work "
                              "— say so plainly and briefly" if failed else
                              "you finished what they asked and are giving them "
                              "the answer"),
                "task": goal,
                "what_you_found": result or "no result was recorded",
            }) or (f"Couldn't get there on {goal}." if failed else result)
            anticipy.notify_owner(said)
            post_event("anticipy_says", said,
                       decision="done", goal=goal)
            REPORTED.add(job["id"])
            print(f"reported {job['status']} job {job['id']}: {said[:80]}")
    except Exception as e:
        print(f"result report failed: {e}")


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
        if decision:
            filt += f' && decision="{decision}"'
        r = pb.get(f"{PB}/api/collections/events/records",
                   params={"filter": filt, "perPage": 100, "sort": "-created"},
                   timeout=10)
        if not r.ok:
            return False
        return any((ev.get("goal") or "").strip() == goal
                   for ev in r.json().get("items", []))
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


def fetch_unprocessed(kind: str = "transcript") -> list[dict]:
    r = pb.get(
        f"{PB}/api/collections/events/records",
        params={"filter": f'kind="{kind}" && decision=""',
                "perPage": 20, "sort": "created"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("items", [])


def mark_processed(event_id: str, decision: str) -> bool:
    """Returns whether the mark actually landed. A silently-failed PATCH left
    the event unmarked and the 2s poll replayed it — minting a duplicate job
    and a duplicate text per cycle."""
    try:
        r = pb.patch(f"{PB}/api/collections/events/records/{event_id}",
                     json={"decision": decision}, timeout=10)
        return bool(getattr(r, "ok", False))
    except Exception:
        return False


def claim(event_id: str) -> bool:
    """Take the event BEFORE doing side effects. If this fails we skip the
    event this cycle rather than acting twice on it."""
    return mark_processed(event_id, "processing")


ASKED_ABOUT: set[str] = set()


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
            if job["id"] in ASKED_ABOUT:
                continue
            ASKED_ABOUT.add(job["id"])
            blocker = (job.get("result") or "").strip()
            if not blocker:
                continue
            said = anticipy._voice({
                "situation": "you got most of the way through a task in their browser "
                             "and need one thing from them to finish",
                "task": job.get("goal", ""),
                "what_you_need": blocker,
            }) or f"I'm nearly through {job.get('goal', 'that')} — {blocker}"
            # ASKED_ABOUT only remembers within one process; a redeploy would
            # make her ask for his name and email all over again. What she
            # actually sent is the durable record.
            if already_raised(job.get("goal", ""), said):
                print(f"stuck job {job['id']}: already asked, staying quiet")
                continue
            anticipy.notify_owner(said)
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
            # The clock: she reviews her open loops on her own schedule and
            # may initiate — rarely, in daytime, rate-limited, gated.
            now = time.time()
            if now - last_clock >= CLOCK_EVERY_SECONDS:
                last_clock = now
                state = _clock_state()
                if clock_should_run(now, state):
                    out = anticipy.clock_tick(
                        now, already_reached_out=set(state.get("reached_loop_ids", [])),
                        may_say=lambda t, g="": not already_raised(g, t))
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
                    out = anticipy.hear(line, context=convo_context)
                except Exception as e:
                    mark_processed(ev["id"], "error")
                    print(f"heard: {line!r} -> error: {e}")
                    continue
                decision = out["decision"].decision
                mark_processed(ev["id"], decision)
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
