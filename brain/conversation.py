"""Anticipy's conversational text channel.

Not a "reply YES/NO" wall — a real back-and-forth, modeled on the two best
text-native agents in the wild (researched):

- Boardy (boardy.ai): a persistent character, not a command parser. Every
  conversation deepens its profile of you; consequential things (intros) are
  double-opt-in — the confirmation itself is conversational, never a keyword.
- Tomo (tomo.ai): texts YOU first, remembers everything across threads, and
  check-ins feel like a friend who knows your goals, not notifications.

So this layer keeps a per-number thread, lets Anticipy open conversations
proactively, and understands free-form replies with the LLM: "yeah go ahead
but make the subject friendlier" is a confirm + a modification, "who's it
going to again?" is a question to answer before acting, "actually forget it"
cancels. The safety boundary is unchanged: understanding is the model's job,
but RELEASING a held job is a queue-status flip this code performs only when
the classified intent is an explicit go-ahead.

Transport is pluggable: TwilioTransport sends real SMS; MockTransport captures
the exact texts that WOULD be sent (for tests and while inbound webhooks
aren't deployed).
"""
from __future__ import annotations

import contextlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

from . import pb

from .anticipy_core import TEXTING_STYLE, _missing_fact_question, memory_notes
from .llm import LLM
from .orchestrator import CALENDAR_YES, calendar_plan_verdict
from .workflow import (approve as approve_plan, cancel as cancel_plan,
                       from_params as workflow_from_params,
                       merge as merge_plan, put_in_params)

REPLY_SYSTEM = """You are Anticipy, a warm, sharp personal assistant who lives
in the owner's pendant and texts like a trusted friend — brief, natural, no
corporate tone, no emojis. You are mid-conversation over SMS.

You will get: the recent thread, what you're currently preparing (pending
items, each with an id), and relevant memory. Classify the owner's latest
text and draft your reply. Respond with EXACTLY one JSON object:

{"intent": "...", "pending_id": "... or null",
 "pending_ids": ["every pending/blocked item their text applies to — one id,
 several, or all of them; [] when none"], "changes": {...} or null,
 "redo": "the errand they actually wanted, or null",
 "reply": "your next text, 1-2 sentences, conversational"}

Understand them the way a person would — slang, swearing, sarcasm, typos,
half-sentences are all normal texting and none of it changes the meaning:
"fuck it, send it" is a confirm; "nah scrap both of those" is a decline of
both items; "the first one, and honestly kill the other" confirms one and
declines the other (use pending_ids for what the main intent applies to).
There are NO command words. If you genuinely cannot tell what they mean,
say so like a person ("wait — which one do you mean?") rather than guessing.

SELF-CORRECTIONS: dictated texts revise themselves mid-sentence. When a
message states a value and then corrects it — "tomorrow, no wait, Thursday",
"two people... actually make it four", "can I do it tomorrow, not tomorrow,
four days from now" — the LAST version is the one they mean. changes must
carry only the corrected value, never the retracted one, and your reply must
say the corrected value back so a misread surfaces immediately. A reply that
repeats a value their own text just corrected away is a misread.

FINISHING IS NOT CANCELLING: "do you wanna finish that", "can you finish
it", "pick that back up", "let's get that done" — any language about
finishing, resuming or completing a held or blocked item is a "confirm" of
THAT item, never a decline. Scrapping something they asked you to finish is
the opposite of what they said.

ONE PLAN, NOT TWO: when their text redirects a pending item to a different
place, person, day or thing ("let's do X instead", "make it Earls", "actually
the blue one"), that IS the pending item, changed — carry the new target in
changes on that pending_id. Never leave the old version alive beside a new
one; parallel copies of the same errand is how the wrong one gets executed.
And a bare follow-up go-ahead ("sounds good", "perfect") applies to whatever
YOUR OWN last text said you were doing — never to an older sibling item.

WRONG-THING CORRECTIONS: "I told you to book X", "that's not what I asked
for", "you were supposed to email Y" is a decline of the wrong item AND a
live request for the right one. Set intent "decline" on the wrong item and
put the errand they actually wanted — with every detail already given in the
thread (place, day, time, count) — in "redo". Leaving redo null there strands
them: the wrong thing dies and the right thing never starts.

AN ANSWER MUST CONTAIN THE THING. When a blocked task needs a specific value
(a verification code, a name, an address), their text is only an "answer" if
the value is actually IN it. "There it is", "just sent it", "check your
messages" carries nothing — you cannot see anything outside this thread. Do
not put a placeholder in changes, and never say you'll use a value you never
received; say plainly that you still need the actual thing pasted here.

RECENT OUTCOMES: "recent_outcomes" lists what just finished, failed or
stopped. When they ask why nothing is happening, what the status is, or
complain that you are idle, answer from it truthfully — name what failed or
stopped and why, and offer to retry (or put the retry in "redo" if they are
plainly telling you to get on with it). "There are no active requests" is
never the answer when something of theirs failed minutes ago — and neither
is asking THEM which thing is stuck: when recent_outcomes names failed or
stopped work, name it yourself, first.

intents:
- "confirm": an explicit go-ahead for a pending item (any phrasing: "yeah
  send it", "looks good, go", "do it but cc Mark" — the latter is confirm
  WITH changes).
- "decline": calling it off ("actually don't", "forget it", "not yet") AND
  rejecting the premise of a task at all — "I never said that", "that's not
  mine", "I didn't ask for this", "where did that come from". Denying that
  something is real IS calling it off; it is never an "answer".
- "modify": changes requested but NOT yet a go-ahead ("make it shorter
  first", "which restaurant did you pick?" then wait). A text that ONLY
  changes a detail of a held item — "make it 6pm instead", "actually
  Tuesday", "two people, not four" — is a modify, NEVER a confirm: changing
  something is not approving it, and releasing on it executes a plan they
  were still correcting.
- "answer": they are answering a question you asked. If "blocked" is not
  empty, it lists tasks stopped waiting for information and what each needs —
  a reply that supplies any of it is an "answer", even if you have no memory
  of asking (your thread does not survive a restart; the blocked list does).
  Capture the substance in changes. BUT a reply that supplies the detail AND
  plainly says to proceed — "let's do 7", "yeah, 7 works, go ahead", "make it
  Tuesday and book it" — is "confirm" with the detail in changes: they are
  not merely informing you, they are telling you to go.
- "new_request": something new to handle. NEVER use this to cancel or call
  off something — calling anything off is "decline" even when no pending item
  matches (pending_id null); do not invent a cancellation task. And NEVER use
  it for a text that picks a detail for something already pending: with a
  dinner waiting on a time, "let's do 7" or "make it Tuesday" is about THAT
  dinner (confirm or answer, changes filled in) — a bare number or time next
  to a pending question is almost never a brand-new errand.
- "chat": ONLY social talk — greetings, thanks, jokes, how-are-you. Anything
  that asks for information or for something to be done is "new_request",
  however casually it is phrased. "what's the weather in Vancouver", "what
  time do they close", "how much is it" are all new_request.
  EXCEPTION — conversational repair: a bare "What", "huh", "wait what",
  "??", "come again" right after one of YOUR messages is them asking you to
  say it again, not a new task. That is "chat", and your reply restates your
  last message more plainly — never "What do you mean?" back at them.

Never say you cannot do something. You have a browser and you can look
things up; deciding what is possible is not your job here. If you are unsure
whether something is doable, classify it as new_request and let it be tried.

Grounding rules (hard):
- Never claim you already did something. Each pending item includes its
  status — nothing is sent/booked/done until its status says "done". Your
  reply after a confirm is "on it" language, never "I sent it".
- pending_id must be the item the owner is actually talking about — match on
  topic. It may name anything in EITHER list: something under "pending", or
  something under "blocked". Calling a task off applies to both, so a blocked
  task he is rejecting must be named by its id, not left null. When their text
  covers several items ("both", "all of it", "everything except the dinner"),
  list every one in pending_ids. Only if their text could genuinely mean more
  than one thing AND you cannot tell which, set them null/[] AND make your
  reply a clarifying question ("the newsletter or the pitch deck?") — do not
  guess, and never re-ask a question they have already answered.
- If nothing is pending and they seem to confirm, ask what they mean.
- Facts about the owner's life come ONLY from "memory" and the thread. If
  they ask something those don't answer (their usual spot, a name, a date),
  say you're not sure — never invent a plausible-sounding answer.
- Never claim a booking, reservation, order or draft EXISTS unless a pending
  item says so, and never carry a detail (a party size, a time) from a
  cancelled or failed task into a new one as if they had said it — details
  come from their words in this thread or from what you are explicitly told.
- When "blocked" is not empty and their message supplies what a blocked task
  needed, say so plainly and that you are getting on with it ("Perfect — I'll
  finish the booking now"). Never ask what the information was for; the
  blocked list already tells you.
Match their energy; be human.

When answering their multi-choice question replies: "both", "all of them",
"neither", "the second one" are complete answers — classify by what they do
(confirm/decline) and never re-ask a question they have already answered.
""" + TEXTING_STYLE


class MockTransport:
    """Captures outbound texts instead of sending — the dead-end wall."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to: str, body: str, media=None) -> dict:
        # `delivered` is False for the same reason it exists on a live send: a
        # record that nobody delivered must not be readable as one that was.
        # `mock` is what distinguishes "captured" from "Twilio has it, delivery
        # pending"; both are honest, and neither is "sent".
        #
        # `media` is captured rather than ignored: this is the rig every test
        # of the picture runs through, and a mock that silently drops it would
        # make a broken chain look wired.
        rec = {"to": to, "body": body, "ts": time.time(), "mock": True,
               "delivered": False, "media": list(media or [])}
        self.sent.append(rec)
        return rec


class TwilioTransport:
    """The live lane. Sends through the voice arm and nowhere else.

    Deliberately thin: the guarantee that a rig cannot text a real person is
    enforced once, in brain/voice_arm.py `_rig_reason`, because the voice arm is
    the only code in the brain that reaches Twilio. Duplicating the check here
    would give two places to forget it. What this class owes is the other half —
    a failed send must never come back looking like a delivered one, so
    exceptions from the arm propagate untouched to `say()` and up to
    notify_owner (brain/anticipy_core.py:2153), which is what drops `handled`
    so the record never claims the owner was told.

    NOTHING IS CAUGHT HERE ON PURPOSE. A 4xx/5xx from Twilio, a status of
    failed/undelivered on a 201, and a rig refusal all arrive as SendFailed
    from voice_arm._result; swallowing any of them into a return value would
    hand the brain a truthy record for a text that does not exist. The record
    that does come back carries `delivered`, which is False for a queued
    message: Twilio has accepted it, and no handset has seen it yet.
    """

    def __init__(self, voice_arm):
        if voice_arm is None:
            # Worker construction is `TwilioTransport(voice) if voice else
            # MockTransport()`. A None arm would have made every send raise
            # AttributeError — safe, but unreadable at 3am.
            raise ValueError("TwilioTransport needs a VoiceArm; use MockTransport "
                             "when Twilio is not configured")
        self.voice = voice_arm

    def send(self, to: str, body: str, media=None) -> dict:
        # ONLY PASSED WHEN THERE IS ONE. Transports and arms that predate the
        # picture are still in the tree and still in production — the SMS
        # webhook's suppressing transport, proof/smoke_worker.py's `T`, every
        # `def text(self, to, body)` fake in tests/ — and handing them a
        # keyword they have never seen is a TypeError on the ONE path that
        # must never fail. A text with no picture is exactly the call it was
        # yesterday.
        if media:
            return self.voice.text(to, body, media=media)
        return self.voice.text(to, body)


@dataclass
class Turn:
    role: str  # "anticipy" | "owner"
    text: str
    ts: float = field(default_factory=time.time)


class Conversation:
    """One continuous conversation between Anticipy and her owner.

    Not "one SMS thread" any more, and the distinction is load-bearing. The
    owner can answer a question by text or by typing into the app, and both
    must land in the SAME conversation: docs leg 2 is "IT WAS ONE
    CONVERSATION", and brief ex 120 forbids a second path to a decision this
    one already owns. So `phone` below is a CONVERSATION KEY and a reply
    address -- every lookup of jobs, profile and history goes through
    `_owner_filter()` instead, which is why one function can serve both
    channels without knowing which it is serving.
    """

    def __init__(self, anticipy, transport=None, llm: Optional[LLM] = None):
        self.anticipy = anticipy
        self.transport = transport or MockTransport()
        self.llm = llm or anticipy.llm
        self.threads: dict[str, list[Turn]] = {}
        # Set only inside `reply_in_app()`. See say().
        self._reply_suppressed = False

    @contextlib.contextmanager
    def reply_in_app(self):
        """Answer the owner where he answered HER, not by text.

        Whether SMS is the primary channel or a backstop is an open product
        question (docs Part 5 demotes it; the owner has asked for the
        opposite), and this deliberately does not settle it. It settles
        something narrower and uncontroversial: a reply belongs on the channel
        the answer arrived on. Typing into the app and being texted back is a
        second conversation about one exchange, which is the split ex 120
        warns about.

        The pattern is copied rather than invented: the SMS webhook already
        suppresses the transport while it rides the TwiML response
        (`backend/sms_server.py` `_SMSTransport.suppress`).
        """
        prev = self._reply_suppressed
        self._reply_suppressed = True
        try:
            yield
        finally:
            self._reply_suppressed = prev

    def _owner_filter(self) -> str:
        """Canonical tenant boundary, with legacy compatibility for tests.

        The worker still carries the old pendant owner id during the staged
        migration, but an authenticated account id is the only durable owner
        identity.  Prefer it everywhere and never silently fall back when it
        exists.
        """
        owner_ref = str(getattr(self.anticipy, "owner_ref", "") or "").strip()
        if owner_ref:
            return f'owner_ref="{owner_ref}"'
        owner_id = str(getattr(self.anticipy, "owner_id", "") or "").strip()
        return f'owner="{owner_id}"' if owner_id else ""

    def _belongs_to_owner(self, record: dict) -> bool:
        owner_ref = str(getattr(self.anticipy, "owner_ref", "") or "").strip()
        if owner_ref:
            return str(record.get("owner_ref") or "") == owner_ref
        owner_id = str(getattr(self.anticipy, "owner_id", "") or "").strip()
        legacy = str(record.get("owner") or "")
        return not owner_id or not legacy or legacy == owner_id

    # ------------------------------------------------------------ outbound

    def say(self, phone: str, body: str, media=None) -> dict:
        # THE DEDUPE STILL READS THE BODY ALONE, AND THAT IS A DECISION.
        # A second attempt that differs only by having a picture on it is
        # deduped away by the loop below (spec §13 question 9, settled here by
        # whoever holds brain/). It is the right way round: the owner reading
        # the same sentence twice in his thread is a worse day than the owner
        # reading it once without a photo, and the photo is reachable in the
        # app either way — the evidence host serves the owner's own rows to
        # his signed-in session with no public window at all.
        #
        # The same sentence never goes out twice in a row within minutes — on
        # 2026-08-02 one "which one should I call off" question was sent three
        # times inside 30 seconds. Saying it once is the human behavior.
        thread = self._thread(phone)
        now = time.time()
        for turn in reversed(thread[-8:]):
            if turn.role != "anticipy":
                continue
            if turn.text == body and now - turn.ts < 600:
                return {"to": phone, "body": body, "deduped": True}
            break
        thread.append(Turn("anticipy", body))
        if self._reply_suppressed:
            # The turn is still recorded, so this is one conversation and the
            # dedupe above still sees it. Only the SMS leg is skipped: the
            # caller is delivering this reply on the channel the answer came
            # in on. See reply_in_app().
            #
            # NO PICTURE ON THIS LANE, and none is needed: the app reads the
            # owner's own evidence rows through his signed-in session
            # (backend/pb_hooks/evidence.pb.js), so an in-app reply does not
            # need a public URL to exist for a picture to be seen.
            return {"to": phone, "body": body, "via": "in-app"}
        # Conditional for the reason TwilioTransport.send gives: transports
        # that predate the picture are still in the tree and still shipping.
        if media:
            return self.transport.send(phone, body, media=media)
        return self.transport.send(phone, body)

    def reach_out(self, phone: str, about: str, media=None) -> dict:
        """Anticipy texts first (Tomo-style), conversationally, about a
        pending item or something she overheard."""
        if self.llm and self.llm.live:
            res = self.llm.chat(
                REPLY_SYSTEM,
                json.dumps({
                    "thread": [],
                    "pending": self._pending(),
                    "task": f"Open the conversation: text the owner about: {about}",
                    "owner_text": None,
                }),
            )
            body = self._parse(res.text).get("reply") or about
        else:
            body = about
        # The composer may rewrite the words; it never touches the picture.
        # WHICH picture was settled by the browser model at the moment it
        # declared the errand done, and nothing on the way out re-opens it.
        return self.say(phone, body, media=media)

    # ------------------------------------------------------------- inbound

    def on_reply(self, phone: str, text: str) -> dict:
        """Free-form owner text in; understood intent + conversational reply
        out. Job release/cancel happens HERE (queue flip), not in the model."""
        self._thread(phone).append(Turn("owner", text))
        parsed = self._classify(phone, text)
        intent = parsed.get("intent", "chat")
        pending_id = parsed.get("pending_id")
        changes = parsed.get("changes")

        # Whatever he just told her about HIMSELF is worth keeping — a date
        # of birth, an allergy, a loyalty number — filed under whatever it was
        # about. Deliberately NOT gated on the "answer" label: classification
        # is a guess, and a task sitting blocked for information is a fact.
        learned, resumed = {}, None
        if intent != "decline":
            learned = self._remember_about_owner(text)
            if learned:
                resumed = self._resume_stuck(learned, owner_text=text)

        # The MODEL is the understander — there are no command words. It may
        # name several items at once ("scrap both", "do everything except
        # dinner"). The deterministic parsing below (digits, "both"/"neither")
        # exists ONLY for when the model is unreachable or named nothing.
        model_ids = [i for i in (parsed.get("pending_ids") or []) if i]
        if not model_ids and pending_id:
            model_ids = [pending_id]

        text_for_guard = text
        if not model_ids:
            # Offline fallback: "2", "the second one", "both", "neither"
            # against the list she herself offered.
            picked = self._choice_from_position(text)
            group = self._group_choice(text)
            if picked and intent in ("confirm", "decline", "answer"):
                pending_id, text_for_guard = picked, None
                model_ids = [picked]
                self._forget_offer()
            elif (group and intent in ("confirm", "decline", "answer")
                    and self._just_asked(phone)):
                # NEVER for chat, and only right after she asked a numbered
                # question. "it's all good" / "how's everything?" contain
                # group words, and the old gate released every offered job
                # off a greeting (hunt find, 2026-08-15).
                offered = (list(self._offered) if self._offer_live()
                           else self._offered_from_thread())
                asked_cancel = self._asked_to_cancel()
                pool = self._open_work() if asked_cancel else self._pending()
                offered = [o for o in offered if any(p["id"] == o for p in pool)]
                if offered:
                    self._forget_offer()
                    if group == "none" and asked_cancel:
                        reply = "Okay — keeping them all."
                        self.say(phone, reply)
                        return {"intent": "chat", "pending_id": None,
                                "changes": None, "acted": None, "reply": reply}
                    intent = ("decline" if asked_cancel or group == "none"
                              or intent == "decline" else "confirm")
                    model_ids, text_for_guard = offered, None
        elif self._just_asked(phone):
            # He is answering HER question; the model matched his words to the
            # item(s). Demanding his text also share a word with the goal is
            # what forced the re-ask loop — an answer to her question is a
            # naming in itself.
            text_for_guard = None

        acted = None
        asked_back = False   # her reply is already a clarifying question

        # Several items at once — act on each; one text back covering all.
        if len(model_ids) > 1 and intent in ("confirm", "decline"):
            do_cancel = intent == "decline"
            # A detail he gave belongs to exactly ONE of them. "yes to both,
            # make the dinner 7pm" used to write time=7pm into the email job
            # too — into its params AND into its approved_scope as a value
            # that "overrides the task wording". The email went out under a
            # number he never said a word about.
            target = pending_id if pending_id in model_ids else None
            if changes and target is None and not do_cancel:
                # And releasing both WITHOUT the detail books the old time
                # while her reply reads the new one back — the acknowledged-
                # in-words, ignored-in-deed failure. Neither smear it nor
                # drop it: ask which one it was for.
                reply = ("Which one is that change for? Tell me and I'll set "
                         "it and send them both off.")
                self.say(phone, reply)
                return {"intent": "modify", "pending_id": None,
                        "changes": changes, "acted": None, "reply": reply}
            done_goals, stalled = [], []
            for jid in model_ids:
                mine = changes if jid == target else None
                res = (self._cancel(jid, owner_text=None) if do_cancel
                       else self._release(jid, mine, owner_text=None))
                job = self._fetch(jid)
                name = ((job or {}).get("goal") or "that").replace("_", " ")
                (done_goals if res and not str(res).startswith("failed")
                 and res != "ambiguous" else stalled).append(name)
            if done_goals or stalled:
                # NEVER the model's pre-drafted sentence here — it was written
                # before either write was attempted. One of the two loses the
                # race often enough (the extension claims it inside the 2.1s
                # poll window) that "Done — scrapped both." went out while one
                # of them was still running. Build it from what actually
                # flipped, and name what did not.
                reply = ""
                if done_goals:
                    names = " and ".join(done_goals)
                    reply = (f"Done — scrapped {names}." if do_cancel
                             else f"On it — {names}.")
                if stalled:
                    left = " and ".join(stalled)
                    verb = "stop" if do_cancel else "start"
                    reply = (f"{reply} I couldn't {verb} {left} — say that one "
                             "again and I'll go after it.").strip()
                self.say(phone, reply)
                return {"intent": intent, "pending_id": None, "changes": changes,
                        "acted": "multi" if done_goals else None,
                        "reply": reply}
        if model_ids:
            pending_id = model_ids[0]

        if intent == "confirm" and changes and phone \
                and self._about_pending(phone, text) == "detail":
            # "make it 6pm instead" classified as a confirm is the correction
            # that gets acknowledged in words and ignored in deed: the job
            # releases under its OLD scope while the reply claims the new
            # value. A change with no go-ahead in it amends and keeps holding.
            intent = "modify"
        if intent == "confirm":
            acted = self._release(pending_id, changes, owner_text=text_for_guard)
            if acted == "ambiguous":
                # "Do it" seconds after he asked for something is about THAT
                # thing — a numbered menu here reads as her not listening.
                fresh = self._freshest_pending()
                if fresh:
                    acted = self._release(fresh, changes, owner_text=None)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one()
                acted, asked_back = None, True
        elif intent == "decline":
            acted = self._cancel(pending_id, owner_text=text_for_guard)
            if acted == "ambiguous":
                fresh = self._freshest_pending()
                if fresh:
                    acted = self._cancel(fresh, owner_text=None)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one(cancel=True)
                acted, asked_back = None, True
        elif intent == "modify" and changes:
            # No pending_id is normal (the model is told to null it when
            # unsure); _amend's single-pending fallback resolves it.
            acted = self._amend(pending_id, changes, owner_text=text)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one(include_blocked=True)
                acted, asked_back = None, True
        elif intent == "answer":
            # The owner is ANSWERING her question — that answer belongs on the
            # job she asked about. Feeding it to hear() instead (the old path)
            # dropped one-word answers entirely via the fragment guard, and
            # re-triaged longer ones into DUPLICATE jobs, while the reply
            # cheerfully said "Sunday it is".
            blocked = self._blocked()
            if changes or pending_id or len(blocked) == 1:
                # The words are evidence even when the generic classifier did
                # not choose a field name. A typed workflow can structure them
                # in `_amend`; dropping them here forked a new task while the
                # original draft stayed unanswered. With several blocked jobs
                # and no model-picked id, however, an unstructured sentence is
                # not evidence of WHICH job it answers. Do not turn a surname
                # into a booking detail or offer an empty pending-card menu;
                # the truth guard below will restate what is actually missing.
                acted = self._amend(
                    pending_id, changes or {"owner_answer": text}, owner_text=text)
                if acted == "ambiguous":
                    parsed["reply"] = self._which_one(include_blocked=True)
                    acted, asked_back = None, True
            if not acted and not asked_back and not learned and not resumed:
                # Nothing absorbed it — treat it as a fresh thought.
                spoken = self._think(text, phone)
                if spoken:
                    parsed["reply"] = spoken
        elif self._is_repair(text):
            # "What" / "huh" / "??" right after her message is the owner
            # asking her to say it again — not a new task. Routing it into
            # triage queued literal garbage ("What" became a job) while the
            # reply asked "What do you mean?" back at him. Restate instead.
            last = self._last_anticipy_line(phone)
            if last:
                parsed["reply"] = f"Sorry — what I meant was: {last}"
            intent = "chat"
        elif intent in ("new_request", "chat") and not changes \
                and self._bare_ack(text):
            # "Sounds good" after her own "got it, booking it" is warmth,
            # not work. Re-triaging it forked the plan: a duplicate held
            # card appeared whose text — "I'll hold off until you give me
            # the word" — contradicted the booking already running (live
            # 2026-08-12). A bare acknowledgment releases whatever is
            # genuinely waiting; with nothing waiting and a plan in motion
            # it earns a nod, never a new card.
            if self._pending() and not self._asked_to_cancel():
                fresh = self._freshest_pending()
                acted = self._release(fresh, None, owner_text=None) \
                    if fresh else None
                intent = "confirm"
            else:
                running = self._running()
                if running:
                    goal = (running[0].get("goal") or "that").replace("_", " ")
                    parsed["reply"] = f"On it — {goal} is moving."
                intent = "chat"
        elif intent == "new_request" and self._pending() and \
                (verdict := self._about_pending(phone, text)) != "no":
            # A wobbly classification must not FORK the plan: "let's do 7,
            # go ahead" with a dinner already held once spawned a second card
            # for "7 people". One isolated second look settles whether the
            # text belongs to the held item — a go-ahead releases it, a bare
            # detail amends it, and only a genuinely new errand goes to triage.
            if verdict == "go":
                acted = self._release(pending_id, changes, owner_text=text_for_guard)
                if acted == "ambiguous":
                    fresh = self._freshest_pending()
                    acted = self._release(fresh, changes, owner_text=None) \
                        if fresh else None
                intent = "confirm"
            else:
                acted = self._amend(pending_id, changes or {"note": text},
                                    owner_text=text)
                if acted == "ambiguous":
                    acted = None
                intent = "answer"
        elif intent in ("new_request", "chat"):
            # A status answer the classifier already grounded in a recent
            # failure must SURVIVE: re-thinking "why is nothing happening"
            # through triage overwrote "your booking failed — want me to
            # retry?" with a deflecting question. If the drafted reply names
            # recently failed/stopped work, it is the honest answer — keep it.
            reply_now = parsed.get("reply") or ""
            grounded = any(
                o.get("status") in ("failed", "cancelled")
                and self._references(reply_now, o)
                for o in self._recent_outcomes())
            # Feed it back through the one brain — same path as the pendant.
            #
            # "chat" is included deliberately. This classifier is not the
            # authority on what she can do, and left to itself it invents
            # limits: asked "what's the weather in Vancouver today?" with two
            # tasks blocked, it called that small talk and answered "I'm not
            # able to look up the weather right now" — which is false, and the
            # request never reached her brain at all. Triage decides what is
            # actionable; a genuinely social line comes back "ignore" and her
            # warm reply stands.
            if not grounded:
                spoken = self._think(text, phone)
                if spoken:
                    parsed["reply"] = spoken

        # An answer that answers nothing is not an answer. On 2026-08-02 she
        # asked for his name, email and phone to finish a booking; he replied
        # "Do it"; she said "Got it, I'll finish up that booking now" — and
        # then did nothing, because he had supplied nothing. Saying she is
        # getting on with it while the task is still blocked is the one thing
        # that makes her useless to trust. Enforced here, in code, rather than
        # asked for in a prompt: if nothing resumed or moved, she does not get
        # to claim progress.
        #
        # FILING A FACT IS NOT PROGRESS. `learned` used to sit in this
        # condition and it let the exact incident back through: two tasks
        # blocked (one on a 6-digit code, one on a phone number), he texts "my
        # last name is Ebrahim", _remember_about_owner returns
        # {"last_name": "Ebrahim"}, nothing matches either requirement, and
        # the truthy dict waved "Perfect — I'll finish that booking now"
        # straight past the guard while both tasks stayed parked.
        if (intent in ("answer", "confirm", "modify")
                and not (resumed or acted or asked_back)):
            still = self._blocked()
            if still:
                parsed["reply"] = self._still_need(still)
        # A decline that cancelled NOTHING must never read as a cancellation.
        # "wait, cancel that!" seconds after a release found the queued job
        # invisible and still texted back "Okay — scrapping it" while the
        # booking ran (hunt find, 2026-08-15). If the model believed it was
        # declining something and nothing actually flipped, say so.
        if (intent == "decline" and model_ids
                and not (acted or resumed or asked_back)):
            parsed["reply"] = ("I couldn't stop anything just now — tell me "
                               "which one you mean and I'll go after it.")

        # A wrong-thing correction carries two acts: kill the wrong item
        # (handled above as the decline) and START the right one. Dropping
        # the second half is how "I told you to book Earls" ended with
        # nothing booked and "there are no active requests".
        redo = parsed.get("redo")
        redo_spoken = None
        if isinstance(redo, str) and redo.strip() and intent in ("decline", "chat"):
            redo_spoken = self._think(redo.strip(), phone)

        reply = parsed.get("reply") or "Got it."
        # Ground the reply in the job actually acted on — the model sometimes
        # drafts its sentence about a different pending item than the one the
        # queue flip touched.
        if acted and ":" in acted:
            verb, job_id_acted = acted.split(":", 1)
            if verb == "failed":
                # The queue flip did not land. Never claim it did.
                reply = "Hit a snag updating that on my end — say it again in a minute?"
            else:
                job = self._fetch(job_id_acted)
                goal = ((job or {}).get("goal") or "").replace("_", " ").strip()
                # What the queue did is ground truth; the model's sentence is
                # a draft written before the flip. For the two verbs that mean
                # "this did NOT start", the sentence is replaced outright —
                # the old gate ran only when the reply shared no 4-letter word
                # with the job, and `params` carries the whole transcript, so
                # any on-topic reply sailed through. "make it 7 instead" ->
                # amended -> "Perfect — moving the dinner to 7, I'll get it
                # booked" shares "dinner", kept its claim, and he stopped
                # replying to a job still holding for his yes.
                if verb == "amended":
                    reply = (f"Updated — {goal} is still waiting on your go-ahead."
                             if goal else
                             "Updated — that's still waiting on your go-ahead.")
                elif verb == "cancelled":
                    reply = (f"Okay — I've scrapped the {goal}." if goal
                             else "Okay — I've called that off.")
                elif job and not self._references(reply, job):
                    # released/resumed genuinely ARE moving, so her own
                    # wording stands when it names the job — that sentence is
                    # where the corrected value gets read back to him.
                    reply = f"On it — {goal or 'that'} is moving."
        if redo_spoken:
            reply = f"{reply} {redo_spoken}".strip()
        self.say(phone, reply)
        return {"intent": intent, "pending_id": pending_id,
                "changes": changes, "acted": acted, "reply": reply}


    REMEMBER_SYSTEM = """The owner just replied to a question about themselves.
Pull out EVERY durable fact about them in the message — their name, email
address, phone number, date of birth, an allergy, a preference, a membership
or loyalty number, a home airport, a dietary restriction. Capture all of them,
not just the most interesting one: a reply like "<full name>, <email>,
<phone>" carries three. Only facts about the PERSON, never about one task,
and NEVER card numbers, passwords or security codes even if they offer them.

Every value MUST be copied from THEIR message, character for character. Never
substitute a placeholder, never tidy a value, never invent one, and never
reuse an example from these instructions. If a fact is not in their message,
it does not go in the output.
Reply ONLY with compact JSON: {"facts": {"<short_snake_case_key>": "<value>"}}
Use {"facts": {}} when there is nothing durable."""


    def _blocked(self) -> list[dict]:
        """Tasks stopped waiting for information, and what each needs. This is
        how she knows she asked even after a restart — the thread is in memory
        and dies with the process; this does not."""
        try:
            # A newly minted DRAFT is also stopped for information. Its legacy
            # row status stays awaiting_confirm because PocketBase admits new
            # workflow rows through that entry state, but the canonical state
            # is what decides whether the owner owes details or approval.
            filt = ('(status="needs_user" || '
                    '(status="awaiting_confirm" && workflow_state="draft"))')
            owner_filter = self._owner_filter()
            if owner_filter:
                filt += f" && {owner_filter}"
            r = pb.get(f"{self.anticipy.backend_url}/api/collections/jobs/records",
                       params={"filter": filt, "perPage": 5, "sort": "-updated"}, timeout=10)
            if not r.ok:
                return []
            out = []
            for j in r.json().get("items", []):
                # `result` is the runner's scratch field and it OVERWRITES it:
                # the extension's staleness bounce replaces the requirement
                # with its own note, and with the requirement gone nothing can
                # match an answer to this task ever again. So the requirement
                # is also kept where the brain owns it, and read back from
                # there when the field it was borrowed from has been trampled.
                needs = (j.get("result") or "").strip()
                try:
                    kept = (json.loads(j.get("params") or "{}") or {}).get("needed")
                except Exception:
                    kept = None
                out.append({"id": j["id"], "goal": j.get("goal", ""),
                            "needs": (needs or kept or "")[:300],
                            "remembered_need": (kept or "")[:300],
                            # The other two pools carry these; this one did
                            # not, and _open_work() copies the pool entry
                            # verbatim. So every PARKED job reached _amend
                            # with params="" -> {}, the plan blob living in
                            # params._workflow was silently dropped from the
                            # write, and the backend guard refused it ("id,
                            # version, and lineage are required"). What he
                            # saw was "Hit a snag updating that on my end"
                            # to every answer he texted, forever — the job
                            # stayed parked on the same question.
                            "params": j.get("params", ""),
                            "status": j.get("status", "needs_user"),
                            # WHEN she asked. Without it a caller cannot tell
                            # a reply from a remark made hours later, and the
                            # spoken-answer router needs exactly that.
                            "updated": j.get("updated") or j.get("created") or ""})
            return out
        except Exception:
            return []

    def _recent_outcomes(self) -> list[dict]:
        """What just finished, failed or stopped — the last hour of closed
        work. Without it "why are you not booking?" gets answered "there are
        no active requests" while their job died two minutes earlier."""
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)
                      ).strftime("%Y-%m-%d %H:%M:%S")
            filt = (f'updated>="{cutoff}" && (status="failed" || '
                    f'status="done" || status="cancelled")')
            owner_filter = self._owner_filter()
            if owner_filter:
                filt += f" && {owner_filter}"
            r = pb.get(f"{self.anticipy.backend_url}/api/collections/jobs/records",
                       params={"filter": filt, "perPage": 5, "sort": "-updated"},
                       timeout=10)
            if not r.ok:
                return []
            return [{"goal": j.get("goal", ""), "status": j.get("status", ""),
                     "outcome": (j.get("result") or "")[:200]}
                    for j in r.json().get("items", [])]
        except Exception:
            return []

    def _still_need(self, blocked: list[dict]) -> str:
        """Name what is actually missing, in her own words rather than a
        template — he is answering, he just has not answered THIS yet."""
        said = self.anticipy._voice({
            "situation": "they just replied but did not include the thing you "
                         "are still waiting on, so you cannot move yet. Say "
                         "plainly what is still missing. Do not scold, do not "
                         "claim you are getting on with it",
            "waiting_on": [{"task": b.get("goal", ""), "needs": b.get("needs", "")}
                           for b in blocked[:3]],
        })
        if said:
            return said
        # Only reached when the model is unavailable. It must still name what
        # is missing — "I need something from you" is useless — but it must
        # ATTRIBUTE the blocker rather than speaking it as her own sentence.
        # Read as hers it was gibberish: "Still waiting on this before I can
        # finish: Stopped before acting. I raised this on my own…", because
        # that string is whatever the runner last wrote and is not always a
        # requirement.
        task = (blocked[0].get("goal") or "that").strip()
        needs = (blocked[0].get("needs") or "").strip()
        if not needs:
            return f"I still need something from you before I can finish {task}."
        return f"I can't finish {task} yet. What's outstanding: {needs}"

    def _remember_about_owner(self, text: str) -> dict:
        """Store what he just told us about himself, keyed by whatever it was
        about. No column per field, no app release per question."""
        if not (self.llm and self.llm.live):
            return {}
        try:
            raw = self._parse(self.llm.chat(self.REMEMBER_SYSTEM, text).text)
            facts = raw.get("facts") or {}
            if not isinstance(facts, dict) or not facts:
                return {}
            base = self.anticipy.backend_url
            owner_filter = self._owner_filter()
            if not owner_filter:
                return {}
            r = pb.get(f"{base}/api/collections/owner_profile/records",
                       params={"filter": owner_filter, "perPage": 1,
                               "sort": "-updated"}, timeout=10)
            items = r.json().get("items", []) if r.ok else []
            if not items:
                return {}
            rec = items[0]
            try:
                known = json.loads(rec.get("facts") or "{}")
            except Exception:
                known = {}
            clean = {str(k)[:40]: str(v)[:200] for k, v in facts.items()
                     if k and v and not re.search(r"card|cvv|cvc|password|secur", str(k), re.I)}
            if not clean:
                return {}
            known.update(clean)
            # AN ANSWER GIVEN ONCE IS KNOWN FOREVER — and the canonical
            # identity fields are COLUMNS, not a blob. The browser is handed
            # first_name/last_name/email/phone by name; anything living only
            # in `facts` reaches it as loose trivia. On 2026-08-17 his
            # profile columns were all empty while the blob held
            # {"name": "Ebrahim", "email": "omar@gmail.com",
            #  "full_name": "David Moore"} — a surname, a mistyped address,
            # and SOMEBODY ELSE'S NAME picked up from a conversation in the
            # room. So every booking asked him for an email he had already
            # given, and filled forms from junk.
            #
            # Promote what is unambiguous into the real columns, and never
            # let a fact learned from ambient speech overwrite one already
            # there — a name heard across a table is not his.
            columns = {}
            for key, value in clean.items():
                k = re.sub(r"\W+", "_", str(key).lower()).strip("_")
                v = str(value).strip()
                if not v:
                    continue
                if k in ("email", "email_address") and "@" in v:
                    columns["email"] = v
                elif k in ("phone", "phone_number", "mobile"):
                    columns["phone"] = v
                elif k in ("first_name", "firstname", "given_name"):
                    columns["first_name"] = v
                elif k in ("last_name", "lastname", "surname", "family_name"):
                    columns["last_name"] = v
                elif k in ("full_name", "name") and " " in v:
                    parts = v.split()
                    columns.setdefault("first_name", parts[0])
                    columns.setdefault("last_name", " ".join(parts[1:]))
            # Never overwrite something already recorded: the first answer he
            # gave deliberately outranks anything overheard later.
            columns = {k: v for k, v in columns.items()
                       if not str(rec.get(k) or "").strip()}
            payload = {"facts": json.dumps(known)}
            payload.update(columns)
            pb.patch(f"{base}/api/collections/owner_profile/records/{rec['id']}",
                     json=payload, timeout=10)
            if columns:
                print(f"learned about him for good: {sorted(columns)}")
            return clean
        except Exception:
            return {}

    @staticmethod
    def _disputes_or_directs(owner_text: str, need: str) -> bool:
        """Is he telling her the question itself is wrong, or what to do next?

        A parked job only resumes when the owner supplies the thing it named.
        That is right for a missing email — and exactly wrong when the thing
        it named does not exist. Live, 2026-08-16: the browser wrongly saw a
        CAPTCHA on the Cactus Club page, asked four times over two hours, and
        when he replied "I'm looking at your page, there's no captcha, just
        press submit, enter a date of birth and press submit" — the single
        most useful sentence anyone sent all day — it counted as "not the
        thing I asked for", stayed parked, and repeated itself. Then his next
        "no there is none" was read as calling it off.

        Someone LOOKING AT THE SCREEN outranks the agent's own diagnosis.
        A denial of the premise, or an instruction about the page, resumes the
        run and rides in as authority."""
        text = (owner_text or "").strip().lower()
        if not text:
            return False
        # "there's no captcha", "there is none", "that's not what it says"
        denial = re.search(
            r"\b(no|not|isn'?t|there'?s no|there is no|aren'?t|none)\b", text)
        subject = re.search(
            r"\b(captcha|robot|challenge|login|sign\s?in|password|verification|code|"
            r"popup|banner|button|field|page|screen)\b", text)
        if denial and subject:
            return True
        # A bare denial of EXISTENCE answers the question without naming it:
        # "no there is none" said back to "solve the CAPTCHA" means the
        # CAPTCHA is not there. Note this is deliberately narrower than a
        # plain "no", which is a refusal and must stay one.
        if re.search(r"there'?s? (is )?(no|none|nothing)\b|there is none|"
                     r"isn'?t (any|one|there)|not there|nothing there|"
                     r"^\s*no,? there'?s? none", text):
            return True
        # "press submit", "click continue", "enter a date of birth", "scroll down"
        if re.search(r"\b(press|click|tap|hit|enter|type|select|choose|scroll|"
                     r"look at|check)\b[^.]{0,40}\b(submit|continue|next|button|"
                     r"box|field|date|name|email|page|down|it|that)\b", text):
            return True
        return False

    @staticmethod
    def _need_match(learned: dict, needs: str) -> Optional[str]:
        """How well what he just told her covers what this task said it needed.

        The task states its own requirement in words ("I need your first name,
        last name, email address, and phone number"), and the facts she stored
        are keyed by what they are. Matching the two is what lets several
        tasks be blocked at once without her having to guess between them.

        Two strengths, because they are not equally trustworthy: "phrase" is
        the fact's own words appearing in the requirement, "noun" is only its
        head noun. The caller needs to tell them apart — see _resume_stuck."""
        text = (needs or "").lower()
        if not text:
            return None
        # Words that carry no meaning of their own: a task asking for a
        # "phone" is asking for phone_number, and one asking for an "email"
        # is asking for email_address.
        generic = {"number", "address", "code", "id", "of", "the", "a"}
        weak = None
        for key in learned:
            phrase = str(key).replace("_", " ").lower().strip()
            if not phrase:
                continue
            if phrase in text:
                return "phrase"
            parts = [p for p in phrase.split() if p not in generic and len(p) > 2]
            if not parts:
                continue
            if " ".join(parts) in text:
                return "phrase"
            # The head noun, as a substring so date_of_birth still answers a
            # task that said "birthday".
            if parts[-1] in text:
                weak = "noun"
        return weak

    @staticmethod
    def _answers_need(learned: dict, needs: str) -> bool:
        """Does what he just told her cover what this task said it needed?"""
        return Conversation._need_match(learned, needs) is not None

    def _resume_stuck(self, learned: Optional[dict] = None,
                      owner_text: str = "") -> Optional[str]:
        """Put a task that stopped for a missing detail back to work.

        Resumes the task whose stated need his answer actually covers. The
        rule used to be "only when exactly one thing is blocked", which read
        as caution but was a trap: on 2026-08-02 he had two blocked tasks at
        once, so an answer carrying precisely what one of them asked for would
        have been remembered, resumed nothing, and still been met with "I'll
        finish the booking now". Matching the answer to the requirement is the
        honest version of not guessing."""
        learned = learned or {}
        try:
            base = self.anticipy.backend_url
            filt = 'status="needs_user"'
            owner_filter = self._owner_filter()
            if owner_filter:
                filt += f" && {owner_filter}"
            r = pb.get(f"{base}/api/collections/jobs/records",
                       params={"filter": filt, "perPage": 10, "sort": "-updated"}, timeout=10)
            items = r.json().get("items", []) if r.ok else []
            if not items:
                return None
            # Match against the runner's current note AND the requirement the
            # brain kept when it resumed. The newest note wins for DISPLAY —
            # a task that blocks again on something new is telling the truth —
            # but for MATCHING both count, because the note may have been
            # overwritten with something that is not a requirement at all.
            def _need_text(j):
                try:
                    kept = (json.loads(j.get("params") or "{}") or {}).get("needed") or ""
                except Exception:
                    kept = ""
                return f'{j.get("result") or ""} {kept}'.strip()
            strength = [(j, self._need_match(learned, _need_text(j))) for j in items]
            matched = [j for j, s in strength if s == "phrase"]
            if not matched:
                # A head noun on its own is a coarse match, and coarse is fine
                # right up until two things want the same noun. "I need your
                # full name" and "I need the name of the restaurant" both end
                # in "name": "Omar Ebrahim" resumed BOTH, and the restaurant
                # booking was handed his own name as an answer stamped "final;
                # act on it". One weak match is a fair read of the room; two
                # is a coin toss, so neither moves.
                weak = [j for j, s in strength if s == "noun"]
                matched = weak if len(weak) == 1 else []
            if not matched and len(items) == 1 and learned:
                # Nothing named, but only one thing is waiting and he did tell
                # her something — the long-standing behaviour, kept.
                matched = items
            if not matched:
                return None
            resumed = [self._requeue(j, learned=learned,
                                     owner_text=owner_text) for j in matched]
            resumed = [rid for rid in resumed if rid]
            return f"resumed:{resumed[0]}" if resumed else None
        except Exception:
            return None

    def _requeue(self, job: dict, learned: Optional[dict] = None,
                 owner_text: str = "") -> Optional[str]:
        try:
            base = self.anticipy.backend_url
            try:
                params = json.loads(job.get("params") or "{}")
            except Exception:
                params = {}
            params["authorized"] = True
            # Keep what it was waiting for. The runner may overwrite `result`
            # the moment it picks the job up, and that string is the only
            # thing an answer can be matched against.
            need = (job.get("result") or "").strip()
            if need and not params.get("needed"):
                params["needed"] = need[:300]
            fields = {"status": "queued"}
            workflow = workflow_from_params(params)
            if workflow:
                # A workflow parked in needs_user may move only when the
                # owner's actual answer is retained and approved against the
                # exact parked version.  Never manufacture words here.
                if not owner_text.strip():
                    return None
                clean = self._drop_unquoted_codes(learned or {}, owner_text)
                try:
                    workflow = approve_plan(
                        workflow, expected_version=workflow.version,
                        owner_words=owner_text, changes=clean or None)
                except Exception:
                    return None
                if clean:
                    params.update(clean)
                answer = owner_text.strip()
                asked = (job.get("result") or params.get("needed") or "").strip()
                if params.get("approved_scope"):
                    params["approved_scope"] += (
                        f' You stopped and asked: "{asked}". '
                        f'They answered: "{answer}" — that answer is final; act on it.')
            # His earlier "actually make it 6" is in params["corrections"] and
            # nowhere the browser reads. Fold it before the plan blob is
            # written back, exactly as _release does.
            params = self._fold_corrections(params)
            if workflow:
                params = put_in_params(params, workflow)
                fields.update(workflow.job_fields())
            fields["params"] = json.dumps(params)
            # Through _flip, never around it: this used to fire the PATCH and
            # return the id no matter what came back, so a 409 (the guard
            # refusing an uncertain-effect retry, say) still reported the job
            # as resumed and she told him it was moving. Nothing had moved.
            return (job["id"]
                    if self._flip(job["id"], fields, "resumed").startswith("resumed:")
                    else None)
        except Exception:
            return None

    def _think(self, text: str, phone: str = "") -> Optional[str]:
        """Hand it to the one brain and bring back what she decided to say.

        Her message comes back as THIS reply rather than going out as a second
        text. Without that, a new request produced two: the classifier's "got
        it, I can look into that" and, moments later, hear()'s own "want me to
        go ahead?". Same thread, same thought, twice."""
        # explicit: he TEXTED this himself — an ask in so many words is its
        # own go-ahead for anything that doesn't leave his world, so "open
        # wikipedia" runs instead of demanding a confirmation.
        # channel: the answer goes back the way the question came — a
        # research job born from a text replies in-thread instead of landing
        # silently on the desk.
        # A core without the newer keywords sheds them one at a time.
        # Dropping may_say along with explicit re-opened the double-text this
        # method exists to prevent, so it is the LAST thing to go.
        quiet = lambda *a, **k: False
        context = []
        if phone:
            # Twenty turns is a ten-message conversation — the old bound of
            # eight (then cut to six downstream) is where "after about three
            # messages she forgets what it's doing" came from.
            turns = list(self._thread(phone)[-21:])
            if turns and turns[-1].role == "owner" and turns[-1].text == text:
                turns = turns[:-1]
            context = [f"{t.role}: {t.text}" for t in turns[-20:]]
        attempts = (
            dict(context=context, may_say=quiet, explicit=True, channel="sms"),
            dict(may_say=quiet, explicit=True, channel="sms"),
            dict(may_say=quiet, explicit=True),
            dict(may_say=quiet),
            dict(),
        )
        out = None
        for kwargs in attempts:
            try:
                out = self.anticipy.hear(text, **kwargs) or {}
                break
            except TypeError:
                continue
            except Exception:
                return None
        if out is None:
            return None
        decision = getattr(out.get("decision"), "decision", "")
        if decision in ("act", "ask"):
            return out.get("anticipy_says") or None
        return None

    # ------------------------------------------------------------ internals

    REPAIR = re.compile(
        r"^(wait[\s,]+)?(what|huh|que|come again|say again|say that again"
        r"|what was that|\?{1,3})[\s?!.]*$", re.IGNORECASE)

    def _is_repair(self, text: str) -> bool:
        return bool(self.REPAIR.match(text.strip()))

    ACK = re.compile(
        r"^(ok(ay)?|yes|yep|yeah|sure|perfect|sounds? (good|great)|great"
        r"|cool|nice|awesome|love it|got it|thanks|thank you|amazing)"
        r"[\s!.\U0001F44D\U0001F44C]*$", re.IGNORECASE)

    def _bare_ack(self, text: str) -> bool:
        """An acknowledgment carrying no new content of its own."""
        return bool(self.ACK.match(text.strip()))

    def _running(self) -> list[dict]:
        try:
            return self.anticipy._running_jobs()
        except Exception:
            return []

    def _last_anticipy_line(self, phone: str) -> Optional[str]:
        for turn in reversed(self._thread(phone)):
            if turn.role == "anticipy":
                return turn.text
        return None

    def _thread(self, phone: str) -> list[Turn]:
        t = self.threads.setdefault(phone, [])
        if not t:
            # A redeploy empties this dict, and an assistant who has forgotten
            # what she just asked will attach his answer to the wrong thing.
            # That is not hypothetical: on 2026-08-02 she asked for his name
            # and email to finish a booking, he replied "Do it", and with an
            # empty thread it read as approval of an unrelated held job, which
            # then started running in his browser. What she actually said is
            # durable — rebuild from it rather than trusting process memory.
            t.extend(self._thread_from_record(phone))
        return t

    def _thread_from_record(self, phone: str, limit: int = 20) -> list[Turn]:
        """Recent turns reconstructed from the backend, newest last.

        kind="anticipy_text" is in the filter because that is what the worker
        actually stamps on every SMS reply she sends (worker.py posts the
        reply as anticipy_text). The rebuild originally read only
        anticipy_says/sms_reply, so HER half of every conversation vanished
        on redeploy — the thread came back as him talking to silence, and
        "after about three messages she forgets" was partly this: the worker
        redeployed mid-conversation and her own questions were gone."""
        try:
            owner_filter = self._owner_filter()
            if not owner_filter:
                return []
            kind_filter = ('(kind="anticipy_says" || kind="sms_reply"'
                           ' || kind="anticipy_text")')
            r = pb.get(
                f"{self.anticipy.backend_url}/api/collections/events/records",
                params={"filter": f"{kind_filter} && {owner_filter}",
                        "perPage": limit, "sort": "-created"},
                timeout=10,
            )
            if not r.ok:
                return []
            turns = []
            for ev in reversed(r.json().get("items", [])):
                text = (ev.get("text") or "").strip()
                if not text:
                    continue
                role = ("anticipy"
                        if ev.get("kind") in ("anticipy_says", "anticipy_text")
                        else "owner")
                turns.append(Turn(role, text))
            return turns
        except Exception:
            return []

    def _queued(self) -> list[dict]:
        """Released but not yet claimed — the thirty seconds where 'wait,
        cancel that!' must still work. These were invisible to the cancel
        pool, so the rescind failed silently while the reply said 'Okay —
        scrapping it' (hunt find, 2026-08-15). Unclaimed queued work is
        always safe to cancel."""
        try:
            filt = 'status="queued"'
            owner_filter = self._owner_filter()
            if owner_filter:
                filt += f" && {owner_filter}"
            r = pb.get(
                f"{self.anticipy.backend_url}/api/collections/jobs/records",
                params={"filter": filt, "perPage": 5, "sort": "-created"},
                timeout=10,
            )
            return [{"id": j["id"], "goal": j["goal"],
                     "params": j.get("params", ""),
                     "status": j.get("status", "")}
                    for j in r.json().get("items", [])]
        except Exception:
            return []

    def _pending(self) -> list[dict]:
        try:
            filt = 'status="awaiting_confirm"'
            owner_filter = self._owner_filter()
            if owner_filter:
                filt += f" && {owner_filter}"
            r = pb.get(
                f"{self.anticipy.backend_url}/api/collections/jobs/records",
                params={"filter": filt, "perPage": 5, "sort": "-created"},
                timeout=10,
            )
            return [{"id": j["id"], "goal": j["goal"], "params": j.get("params", ""),
                     "status": j.get("status", "")}
                    for j in r.json().get("items", [])]
        except Exception:
            return []

    ABOUT_PENDING = """A personal assistant is holding work that waits on her
owner's word. He just texted her. One question: is his text about a HELD
item, or a brand-new errand?

Reply ONLY with compact JSON: {"verdict": "go"|"detail"|"no"}
- "go": his text belongs to a held item AND tells her to proceed — a plain
  yes, or a missing detail plus a go-ahead ("let's do 7, go ahead").
- "detail": it belongs to a held item but only supplies or changes a detail,
  with no instruction to proceed.
- "no": it is genuinely a new, unrelated errand or question."""

    def _about_pending(self, phone: str, text: str) -> str:
        """Isolated second look before a 'new_request' may fork a held plan."""
        if not (self.llm and self.llm.live):
            return "no"
        held = "; ".join(p["goal"] for p in self._pending())
        last = self._last_anticipy_line(phone) or ""
        try:
            res = self.llm.chat(
                self.ABOUT_PENDING,
                f"HELD: {held}\nHER LAST TEXT: {last}\nHE TEXTED: {text}",
                temperature=0.0)
            verdict = self._parse(res.text).get("verdict")
        except Exception:
            return "no"
        return verdict if verdict in ("go", "detail") else "no"

    def _classify(self, phone: str, text: str) -> dict:
        thread = [{"who": t.role, "text": t.text} for t in self._thread(phone)[-20:]]
        # Fenced, not raw. REPLY_SYSTEM tells the model that facts about the
        # owner's life come ONLY from `memory` and the thread — so this block is
        # explicitly authoritative, which is the last place attacker-controlled
        # text may sit unmarked. An imported calendar title is a profile fact
        # and _profile_recall's backfill will pad it in even when it matched
        # nothing; the classifier's verdict then drives execution ("confirm"
        # releases a held job). memory_notes segregates anything imported into a
        # nonce-delimited quoted block.
        memory = memory_notes(self.anticipy.memory.recall(text, limit=6))
        payload = json.dumps({"thread": thread, "pending": self._pending(),
                              "blocked": self._blocked(), "memory": memory,
                              "recent_outcomes": self._recent_outcomes(),
                              "owner_text": text})
        if self.llm and self.llm.live:
            try:
                # _parse returns {} on malformed output WITHOUT raising, so the
                # except below never fired: an explicit "yes send it" became
                # intent "chat" with a reassuring "Got it." while the held job
                # stayed put. Only trust a parse that produced an intent.
                parsed = self._parse(self.llm.chat(REPLY_SYSTEM, payload).text)
                if parsed.get("intent"):
                    return parsed
            except Exception:
                pass
        # Offline/parse-failure fallback. Word boundaries, not substrings:
        # "yes" lived inside "yesterday" (released a held job) and "no" inside
        # "know"/"now"/"nothing" (cancelled one).
        low = text.lower().strip()
        short = len(low.split()) <= 6
        has_pending = bool(self._pending())
        if short and re.search(r"\b(yes|yep|yeah|go ahead|send it|do it|confirm|approved)\b", low):
            if not has_pending:
                return {"intent": "chat", "pending_id": None,
                        "reply": "Nothing's queued up on my end right now — what did you mean?"}
            return {"intent": "confirm", "pending_id": None, "reply": "On it."}
        # "no worries", "no rush", "I don't know" are not cancellations. This
        # path runs on ANY malformed model reply, not just an outage, and a
        # bare \bno\b inside a pleasantry cancelled his only held booking and
        # closed the promise behind it — answered with "Okay, scrapped."
        # Strip the idioms first, then look for a refusal in what is left.
        refusal = re.sub(r"\bno (worries|worry|rush|problem|pressure|biggie"
                         r"|stress|sweat)\b|\bdon'?t know\b|\bno idea\b",
                         " ", low)
        if short and re.search(r"\b(no|nope|don'?t|forget it|cancel|stop|scrap it)\b", refusal):
            if not has_pending:
                return {"intent": "chat", "pending_id": None,
                        "reply": "Nothing's queued up on my end right now — what did you mean?"}
            return {"intent": "decline", "pending_id": None, "reply": "Okay, scrapped."}
        return {"intent": "chat", "pending_id": None, "reply": "Got it."}

    @staticmethod
    def _parse(text: str) -> dict:
        import re
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}

    def _which_one(self, cancel: bool = False,
                   include_blocked: bool = False) -> str:
        """Offer the choice NUMBERED.

        She used to list them joined by "or", which gave him no way to pick
        that she could understand. On 2026-07-13 she asked "Which one did you
        mean? - Find a well-rated dinner recipe - Check ingredients", he
        replied "2", and nothing happened: _references demands a shared word
        between his text and the goal, and "2" has none, so the release came
        back ambiguous and she asked again. Numbering makes the position a
        real name, and the numbered question survives in the thread so it can
        still be resolved after a restart."""
        # Calling something off must be able to name a blocked task too, or
        # she offers a list that does not contain the thing he wants stopped.
        pending = self._open_work() if (cancel or include_blocked) else self._pending()
        verb = ("call off" if cancel else
                "answer" if include_blocked else "go ahead with")
        if not pending:
            return "Nothing's waiting on you right now — what do you mean?"
        self._offered = [p["id"] for p in pending]
        self._offered_cancel = cancel
        self._offered_at = time.time()
        listed = ", ".join(f"{i}) {p['goal'].replace('_', ' ')}"
                           for i, p in enumerate(pending, 1))
        return f"Just to be sure — which one should I {verb}: {listed}?"

    # Words he might use instead of a digit. Ordinals only — this never tries
    # to interpret meaning, just position in the list she herself offered.
    _ORDINALS = {"first": 1, "1st": 1, "one": 1, "second": 2, "2nd": 2,
                 "two": 2, "third": 3, "3rd": 3, "three": 3, "fourth": 4,
                 "4th": 4, "four": 4, "fifth": 5, "5th": 5, "five": 5}

    # Whole-list answers to her numbered question. "none"/"neither" mean the
    # opposite of whatever verb she offered.
    _GROUP_ALL = {"both", "all", "everything"}
    _GROUP_NONE = {"neither", "none", "nothing"}

    def _group_choice(self, text: str) -> Optional[str]:
        """'all', 'none', or None — a pick covering the whole offered list."""
        words = re.findall(r"[a-z]+", (text or "").lower())
        if not words or len(words) > 5:
            return None
        if self._GROUP_ALL & set(words):
            return "all"
        if self._GROUP_NONE & set(words):
            return "none"
        return None

    def _freshest_pending(self) -> Optional[str]:
        """The pending item he created moments ago, if there is exactly one
        that fresh. A bare "do it"/"cancel that" right after asking for
        something names it as surely as repeating himself would."""
        try:
            now = datetime.now(timezone.utc)
            fresh = []
            for p in self._pending():
                created = (p.get("created") or "").replace(" ", "T").replace("Z", "+00:00")
                try:
                    ts = datetime.fromisoformat(created)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = (now - ts).total_seconds()
                except Exception:
                    continue
                if age < 180:
                    fresh.append(p["id"])
            return fresh[0] if len(fresh) == 1 else None
        except Exception:
            return None

    def _just_asked(self, phone: str) -> bool:
        """Whether her last message in this thread was a question."""
        for turn in reversed(self._thread(phone)[-6:]):
            if turn.role == "anticipy":
                return turn.text.rstrip().endswith("?")
        return False

    # How long a numbered menu stays answerable. Long enough that he can put
    # the phone down mid-question, short enough that it is not still standing
    # over an unrelated conversation an hour later.
    _OFFER_TTL = 900

    def _offer_live(self) -> bool:
        """Is the menu she offered still the question on the table?

        `_offered`/`_offered_cancel` were set once and never cleared, so a
        CALL-OFF menu from any point in the process's life kept answering
        _asked_to_cancel True. With the model down, "yeah do it all" to her
        much later "want me to lock in Earls for 7?" resolved "all" against
        that stale cancel list, flipped the intent to decline, and scrapped
        every open job in answer to a yes.
        """
        if not getattr(self, "_offered", None):
            return False
        return time.time() - getattr(self, "_offered_at", 0.0) <= self._OFFER_TTL

    def _forget_offer(self) -> None:
        """An answered menu is spent — it must not answer the next question."""
        self._offered, self._offered_cancel, self._offered_at = [], None, 0.0

    def _asked_to_cancel(self) -> bool:
        """Whether her last numbered question offered to CALL THINGS OFF."""
        if self._offer_live() and getattr(self, "_offered_cancel", None) is not None:
            return bool(self._offered_cancel)
        for turn in reversed(self._thread_from_record("", limit=10)):
            if turn.role == "anticipy" and "which one" in turn.text.lower():
                return "call off" in turn.text.lower()
        return False

    def _choice_from_position(self, text: str) -> Optional[str]:
        """Which job he picked by position, or None if he did not pick one.

        A positional answer IS a naming — relative to the list she offered —
        so it is allowed to satisfy the guard that a bare "yes" cannot."""
        low = (text or "").lower().strip()
        words = re.findall(r"[a-z0-9]+", low)
        if not words or len(words) > 4:
            return None          # a sentence names things on its own
        idx = None
        for w in words:
            if w.isdigit() and 1 <= int(w) <= 9:
                idx = int(w)
                break
            if w in self._ORDINALS:
                idx = self._ORDINALS[w]
                break
        if idx is None:
            return None
        offered = list(self._offered) if self._offer_live() else []
        if not offered:
            # A redeploy cleared it. Rebuild from the numbered question she
            # actually sent — her own format, parsed back, then matched to
            # what is still pending so a stale number cannot release
            # something that is no longer waiting.
            offered = self._offered_from_thread()
        if not offered or idx > len(offered):
            return None
        chosen = offered[idx - 1]
        # Validate against the pool the menu was BUILT from. A call-off menu
        # lists blocked and queued work too (_open_work), but this only ever
        # checked _pending() — so "the second one" naming the parked email
        # resolved to None, the cancel fell back to _freshest_pending, and the
        # dinner he never mentioned died instead while he was told it had.
        pool = self._open_work() if self._asked_to_cancel() else self._pending()
        return chosen if any(p["id"] == chosen for p in pool) else None

    def _offered_from_thread(self) -> list[str]:
        """Recover the order from her last numbered question."""
        for turn in reversed(self._thread_from_record("", limit=10)):
            if turn.role != "anticipy" or "which one" not in turn.text.lower():
                continue
            goals = re.findall(r"\d\)\s*([^,?]+)", turn.text)
            if not goals:
                continue
            pending = (self._open_work() if "call off" in turn.text.lower()
                       else self._pending())
            order = []
            for g in goals:
                want = {w for w in re.findall(r"[a-z0-9']+", g.lower()) if len(w) > 3}
                best = None
                for p in pending:
                    have = {w for w in re.findall(r"[a-z0-9']+", (p["goal"] or "").lower())
                            if len(w) > 3}
                    if have and want and len(want & have) / max(len(want), len(have)) >= 0.6:
                        best = p["id"]
                        break
                order.append(best)
            return [o for o in order if o] if all(order) else []
        return []

    @staticmethod
    def _references(text: str, job: dict) -> bool:
        """Whether the owner's text actually names this job's topic. A bare
        go-ahead ("go ahead", "yes do it") names nothing, so with several
        items held the model's pick alone is never enough to act on."""
        import re
        blob = f"{job.get('goal', '')} {job.get('params', '')}".lower()
        job_words = set(re.findall(r"[a-z]{4,}", blob))
        text_words = set(re.findall(r"[a-z]{4,}", text.lower()))
        return bool(job_words & text_words)

    def _fetch(self, job_id: str) -> Optional[dict]:
        try:
            r = pb.get(
                f"{self.anticipy.backend_url}/api/collections/jobs/records/{job_id}",
                timeout=10)
            if not r.ok:
                return None
            record = r.json()
            return record if self._belongs_to_owner(record) else None
        except Exception:
            return None

    def _open_work(self) -> list[dict]:
        """Everything still open in his name — waiting on his yes AND stopped
        for information. Cancelling has to reach both: a task blocked on a
        detail is the one actually nagging him, and until now saying "forget
        it" could not touch one. On 2026-08-02 both of his tasks were blocked,
        so neither could be called off by text while she cheerfully agreed to
        drop them."""
        seen, out = set(), []
        for job in self._pending() + self._blocked() + self._queued():
            if job["id"] in seen:
                continue
            seen.add(job["id"])
            out.append({"id": job["id"], "goal": job.get("goal", ""),
                        "params": job.get("params", ""),
                        "status": job.get("status", "")})
        return out

    def _job(self, job_id: Optional[str], owner_text: Optional[str] = None,
             pool: Optional[list[dict]] = None):
        """Resolve the job the owner means. Falls back to the single candidate
        ONLY when there is exactly one — with several (or none), guessing is
        how the wrong thing gets sent or cancelled. Even a model-picked id is
        only trusted with several candidates when the owner's own words point
        at that job."""
        pending = self._pending() if pool is None else pool
        if job_id:
            job = self._fetch(job_id)
            if job:
                if owner_text is not None and len(pending) > 1 \
                        and not self._references(owner_text, job):
                    return "ambiguous"
                return job
            # A made-up id (the model invents "dinner-1" style handles) must
            # not sink the whole release — resolve as if no id was given.
        if len(pending) == 1:
            return pending[0]
        return "ambiguous" if pending else None

    @staticmethod
    def _fold_corrections(params: dict, changes: Optional[dict] = None) -> dict:
        """Put every value he has retracted-and-replaced into the authority.

        Corrections that arrived EARLIER ("make it 6pm instead" against a
        parked job, which is only noted) live in params["corrections"] and are
        invisible in the goal wording the agent reads. approved_scope is the
        only channel the browser hands read, so unless the correction is
        folded in there the browser confirms 6pm in words and books 8pm in
        deeds. _release did this; _requeue and _amend's resume branch did not,
        so answering the parked question was exactly the path that executed
        the retracted time.
        """
        corrections = dict(params.get("corrections") or {})
        if changes:
            corrections.update(changes)
        if not corrections:
            return params
        params["corrections"] = corrections
        if params.get("approved_scope"):
            corrected = "; ".join(f"{k}: {v}" for k, v in corrections.items())
            params["approved_scope"] += (
                f" They changed: {corrected} — these corrected values "
                "override the task wording and anything heard earlier.")
        return params

    def _release(self, job_id: Optional[str], changes: Optional[dict],
                 owner_text: str = "") -> Optional[str]:
        job = self._job(job_id, owner_text)
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        # Only a job still waiting on the owner may be released. Without this,
        # a model-supplied id could re-queue a cancelled/failed/done job — the
        # resurrection class the 2026-07-31 audit flagged. A job the browser
        # parked with a question (needs_user) is also waiting on the owner:
        # "K do it" after her "showing 6:30, did you mean noon?" must put it
        # back to work, not be answered politely while the job sits parked.
        if job.get("status") not in ("awaiting_confirm", "needs_user"):
            return None
        # The owner's yes is recorded ON the job, so the browser agent knows
        # it may finish the task — including the final Submit. The gate lives
        # here, once; asking again at the button is the same gate twice.
        try:
            params = json.loads(job.get("params") or "{}")
        except Exception:
            params = {}
        params["authorized"] = True
        # Record WHAT was agreed, not just that something was: every later
        # action is measured against this, which is what makes "only stop if
        # reality differs" a rule rather than a vibe.
        if job.get("status") == "needs_user" and params.get("approved_scope"):
            # Resuming a parked run: the original approval stands; what's new
            # is his answer to the question the browser stopped on. The agent
            # reads its authority from this field, so the answer lives here.
            answer = (owner_text or "").strip() or json.dumps(changes or {})
            asked = (job.get("result") or params.get("needed") or "").strip()
            params["approved_scope"] += (
                f' You stopped and asked: "{asked}". '
                f'They answered: "{answer}" — that answer is final; act on it.')
        else:
            said = (owner_text or "").strip()
            # Never invent their words: a release that arrived without the
            # owner's own text (a deterministic path) records the go-ahead as
            # a fact, not as a quote they never said.
            params["approved_scope"] = (
                f"Task: {job.get('goal', '')}. "
                + (f'They said: "{said}". ' if said
                   else "They gave the go-ahead. ")
                + f"Heard originally: {params.get('source', '')}"
            ).strip()
        if changes:
            changes = self._drop_unquoted_codes(changes, owner_text)
            params.update(changes)
        params = self._fold_corrections(params, changes)
        fields = {"status": "queued", "params": json.dumps(params)}
        # Reading the embedded plan can itself refuse — a row whose status and
        # embedded state disagree is exactly the disagreement worth surfacing.
        try:
            workflow = workflow_from_params(params)
        except Exception as e:
            print(f"release could not read the plan on {job['id']}: {str(e)[:160]}")
            return f"failed:{job['id']}"
        if workflow:
            # An approval must carry WORDS. Four callers deliberately pass
            # owner_text=None to bypass the _references guard — and approve()
            # rightly refuses empty words, so the release raised, the bare
            # `except` swallowed it, and the job sat awaiting_confirm forever
            # while she texted "on it". He answers her own question with "yes
            # go for it" and nothing happens, silently. Bypassing the guard is
            # not a reason to lose his consent: fall back to what he actually
            # said, then to an honest record that he agreed.
            words = (owner_text or "").strip() or "They gave the go-ahead."
            try:
                workflow = approve_plan(
                    workflow, expected_version=workflow.version,
                    owner_words=words,
                    changes=changes or None)
            except Exception as e:
                # A refused approval is a FAILURE, not a silent no-op: the
                # caller must never go on to say "on it" about a job that
                # never moved.
                print(f"release refused for {job['id']}: {str(e)[:160]}")
                return f"failed:{job['id']}"
            params = put_in_params(params, workflow)
            fields.update(workflow.job_fields())
            fields["params"] = json.dumps(params)
        return self._flip(job["id"], fields, "released")

    def _cancel(self, job_id: Optional[str], owner_text: str = "") -> Optional[str]:
        job = self._job(job_id, owner_text, pool=self._open_work())
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        fields = {"status": "cancelled"}
        try:
            params = json.loads(job.get("params") or "{}")
        except Exception:
            params = {}
        workflow = workflow_from_params(params)
        if workflow:
            try:
                workflow = cancel_plan(
                    workflow, reason=owner_text or "cancelled by owner")
            except Exception:
                return None
            params = put_in_params(params, workflow)
            fields.update(workflow.job_fields())
            fields["params"] = json.dumps(params)
        out = self._flip(job["id"], fields, "cancelled")
        if out.startswith("cancelled:"):
            # The promise behind the job dies with it — a cancelled plan
            # left "open" in memory becomes a clock follow-up days later.
            try:
                self.anticipy.memory.close_matching(
                    job.get("goal", ""), "cancelled")
            except Exception:
                pass
        return out

    def _amend(self, job_id: Optional[str], changes: dict,
               owner_text: str = "") -> Optional[str]:
        # The pool includes blocked (needs_user) work: an answer that supplies
        # what a parked browser run asked for belongs ON that run — amending a
        # copy while the real job stays parked is how "Noon pls" got a cheerful
        # reply and changed nothing.
        job = self._job(job_id, pool=self._open_work())
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        try:
            params = json.loads(job.get("params") or "{}")
        except Exception:
            params = {}
        workflow = workflow_from_params(params)
        # The generic reply classifier is not a calendar parser. Re-read the
        # original authority together with this answer through the same typed
        # question that selected the EventKit hand, then merge only facts that
        # survived that artifact's closed-shape and ISO validation.
        if (workflow and workflow.act
                and workflow.act.act_type == "calendar_write"
                and workflow.missing and owner_text.strip()):
            calendar = calendar_plan_verdict(
                self.llm,
                f"{workflow.authority_text}\nOWNER ANSWER: {owner_text}",
                workflow.goal,
                str(params.get("now") or ""),
            )
            if calendar.state == CALENDAR_YES:
                changes = dict(changes or {})
                # `owner_answer` is only a lossless envelope used when the
                # generic reply classifier could not name a field. Once this
                # typed artifact has resolved the calendar facts, the raw
                # envelope is no longer a plan fact and must not widen the
                # approved scope or its digest.
                changes.pop("owner_answer", None)
                changes.update(calendar.facts)
        need = (job.get("result") or params.get("needed") or "").strip()
        if job.get("status") == "needs_user":
            changes = self._drop_unquoted_codes(changes, owner_text)
            if not changes:
                return None
            # A parked run stopped for a NAMED thing. An amendment that does
            # not supply that thing ("make it 6" against "I need the 6-digit
            # verification code") is noted on the job but must not requeue it
            # — each empty-handed resume burns a browser run that ends parked
            # on the same question.
            supplied = (self._answers_need(changes, need)
                        or self._disputes_or_directs(owner_text, need)
                        or any(
                            len(str(v).strip()) >= 3 and str(v).strip().lower()
                            in need.lower() for v in changes.values()))
            if need and not supplied:
                params.update(changes)
                corrections = dict(params.get("corrections") or {})
                corrections.update(changes)
                params["corrections"] = corrections
                return self._flip(job["id"],
                                  {"params": json.dumps(params)}, "amended")
        params.update(changes)
        # Two channels, both required. corrections[] survives for whichever
        # release path fires later (SMS go-ahead or app tap) to fold into the
        # authority text; the workflow merge puts the same values into plan
        # FACTS — the only channel the browser hands ever read.
        if job.get("status") == "awaiting_confirm":
            corrections = dict(params.get("corrections") or {})
            corrections.update(changes)
            params["corrections"] = corrections
        if workflow and job.get("status") != "needs_user":
            try:
                # An answer must be able to FILL the fact the plan is
                # waiting on even when the classifier picked a different
                # key shape ("which_location" vs required "location").
                # A required fact that can never be filled wedges the plan
                # in DRAFT forever, which is worse than never blocking.
                merged = dict(changes)
                for need in workflow.missing:
                    if need in merged:
                        continue
                    for k, v in changes.items():
                        if need in str(k) or str(k) in need:
                            merged[need] = v
                            break
                workflow = merge_plan(
                    workflow, expected_version=workflow.version,
                    facts=merged,
                    authority_text=str(params.get("source")
                                       or workflow.authority_text or ""))
                params = put_in_params(params, workflow)
            except Exception:
                return None
        if job.get("status") == "needs_user":
            if need and not params.get("needed"):
                params["needed"] = need[:300]
            if params.get("approved_scope"):
                answer = (owner_text or "").strip() or json.dumps(changes)
                params["approved_scope"] += (
                    f' You stopped and asked: "{need}". '
                    f'They answered: "{answer}" — that answer is final; act on it.')
            # Everything he corrected while it sat parked — the note-only
            # branch above stores those and touches nothing else — has to ride
            # in with the answer, or the resumed run reads 8pm out of the goal
            # and books 8pm after he moved it to 6.
            params = self._fold_corrections(params)
            fields = {"status": "queued", "params": json.dumps(params)}
            if workflow:
                try:
                    workflow = approve_plan(
                        workflow, expected_version=workflow.version,
                        owner_words=owner_text, changes=changes)
                except Exception:
                    return None
                params = put_in_params(params, workflow)
                fields.update(workflow.job_fields())
                fields["params"] = json.dumps(params)
            return self._flip(job["id"], fields, "resumed")
        fields = {"params": json.dumps(params)}
        if workflow:
            fields.update(workflow.job_fields())
            fields["result"] = _missing_fact_question(
                workflow.missing, fallback=params.get("missing") or "")
            fields["params"] = json.dumps(params)
        return self._flip(job["id"], fields, "amended")

    # "code" in a key name does not make it a secret. A postal code, an area
    # code or a promo code is public, is often shorter than four characters
    # ("604"), and was being deleted by the secrecy rule below — so she asked
    # for it again every single time he sent it.
    _PUBLIC_CODE_KEYS = re.compile(
        r"(^|_)(postal|post|zip|area|country|dial|promo|discount|coupon"
        r"|airport|iata)(_|$)")

    @staticmethod
    def _drop_unquoted_codes(changes: Optional[dict],
                             owner_text: Optional[str]) -> Optional[dict]:
        """A value bound for a code/PIN field must be the owner's own
        characters. "I told you to make it 6 dammit" once became
        verification_code="6" and the browser typed a fabricated code into a
        real OTP form — a lockout/fraud-flag risk. A code is never derived,
        completed or guessed: too short, or absent from what they actually
        texted, and it does not exist.

        Compared with spacing, hyphens and case squashed out of BOTH sides.
        The rule is "his characters, not the model's" — and it was reading as
        "his formatting too": he texted "code is 428 913", the model tidied it
        to "428913", the literal substring test failed, and the code he had
        just pasted was thrown away. He pasted it again. And again."""
        if not changes:
            return changes
        squash = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
        typed = squash(owner_text or "")
        out = {}
        for k, v in changes.items():
            key = re.sub(r"\W+", "_", str(k).lower())
            secret = (re.search(r"(^|_)(code|otp|pin)($|_)", key)
                      or "verification" in key)
            if secret and not Conversation._PUBLIC_CODE_KEYS.search(key):
                sv = squash(v)
                if len(sv) < 4 or sv not in typed:
                    continue
            out[k] = v
        return out

    def _flip(self, job_id: str, fields: dict, verb: str) -> str:
        """Every queue change goes through here so a failed PATCH can never be
        reported to the owner as success — the silent-lie class: he texts
        'yes', the write 4xx's, and Anticipy says 'On it' about a job that
        never moved."""
        try:
            r = pb.patch(
                f"{self.anticipy.backend_url}/api/collections/jobs/records/{job_id}",
                json=fields, timeout=10)
            if not getattr(r, "ok", False):
                return f"failed:{job_id}"
        except Exception:
            return f"failed:{job_id}"
        return f"{verb}:{job_id}"
