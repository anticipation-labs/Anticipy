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

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

from . import pb

from .llm import LLM

REPLY_SYSTEM = """You are Anticipy, a warm, sharp personal assistant who lives
in the owner's pendant and texts like a trusted friend — brief, natural, no
corporate tone, no emojis. You are mid-conversation over SMS.

You will get: the recent thread, what you're currently preparing (pending
items, each with an id), and relevant memory. Classify the owner's latest
text and draft your reply. Respond with EXACTLY one JSON object:

{"intent": "...", "pending_id": "... or null", "changes": {...} or null,
 "reply": "your next text, 1-2 sentences, conversational"}

intents:
- "confirm": an explicit go-ahead for a pending item (any phrasing: "yeah
  send it", "looks good, go", "do it but cc Mark" — the latter is confirm
  WITH changes).
- "decline": calling it off ("actually don't", "forget it", "not yet") AND
  rejecting the premise of a task at all — "I never said that", "that's not
  mine", "I didn't ask for this", "where did that come from". Denying that
  something is real IS calling it off; it is never an "answer".
- "modify": changes requested but NOT yet a go-ahead ("make it shorter
  first", "which restaurant did you pick?" then wait).
- "answer": they are answering a question you asked. If "blocked" is not
  empty, it lists tasks stopped waiting for information and what each needs —
  a reply that supplies any of it is an "answer", even if you have no memory
  of asking (your thread does not survive a restart; the blocked list does).
  Capture the substance in changes.
- "new_request": something new to handle. NEVER use this to cancel or call
  off something — calling anything off is "decline" even when no pending item
  matches (pending_id null); do not invent a cancellation task.
- "chat": ONLY social talk — greetings, thanks, jokes, how-are-you. Anything
  that asks for information or for something to be done is "new_request",
  however casually it is phrased. "what's the weather in Vancouver", "what
  time do they close", "how much is it" are all new_request.

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
  task he is rejecting must be named by its id, not left null. If their text
  could genuinely refer to more than one item, or refers to something in
  neither list, set pending_id to null AND make your reply a clarifying
  question ("the newsletter or the pitch deck?") — do not guess.
- If nothing is pending and they seem to confirm, ask what they mean.
- When "blocked" is not empty and their message supplies what a blocked task
  needed, say so plainly and that you are getting on with it ("Perfect — I'll
  finish the booking now"). Never ask what the information was for; the
  blocked list already tells you.
Match their energy; be human."""


class MockTransport:
    """Captures outbound texts instead of sending — the dead-end wall."""

    def __init__(self):
        self.sent: list[dict] = []

    def send(self, to: str, body: str) -> dict:
        rec = {"to": to, "body": body, "ts": time.time(), "mock": True}
        self.sent.append(rec)
        return rec


class TwilioTransport:
    def __init__(self, voice_arm):
        self.voice = voice_arm

    def send(self, to: str, body: str) -> dict:
        return self.voice.text(to, body)


@dataclass
class Turn:
    role: str  # "anticipy" | "owner"
    text: str
    ts: float = field(default_factory=time.time)


class Conversation:
    """One continuous SMS thread between Anticipy and her owner."""

    def __init__(self, anticipy, transport=None, llm: Optional[LLM] = None):
        self.anticipy = anticipy
        self.transport = transport or MockTransport()
        self.llm = llm or anticipy.llm
        self.threads: dict[str, list[Turn]] = {}

    # ------------------------------------------------------------ outbound

    def say(self, phone: str, body: str) -> dict:
        self._thread(phone).append(Turn("anticipy", body))
        return self.transport.send(phone, body)

    def reach_out(self, phone: str, about: str) -> dict:
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
        return self.say(phone, body)

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
                resumed = self._resume_stuck(learned)

        # "2", "the second one", "first" — he is answering the numbered
        # question she asked. Position names the job as surely as saying its
        # topic would, so it satisfies the guard a bare "yes" cannot, and it
        # overrides the model's own pick: he counted, she should count too.
        picked = self._choice_from_position(text)
        if picked and intent in ("confirm", "decline", "answer"):
            pending_id, text_for_guard = picked, None
        else:
            text_for_guard = text

        acted = None
        asked_back = False   # her reply is already a clarifying question
        if intent == "confirm":
            acted = self._release(pending_id, changes, owner_text=text_for_guard)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one()
                acted, asked_back = None, True
        elif intent == "decline":
            acted = self._cancel(pending_id, owner_text=text_for_guard)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one(cancel=True)
                acted, asked_back = None, True
        elif intent == "modify" and changes:
            # No pending_id is normal (the model is told to null it when
            # unsure); _amend's single-pending fallback resolves it.
            acted = self._amend(pending_id, changes)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one()
                acted, asked_back = None, True
        elif intent == "answer":
            # The owner is ANSWERING her question — that answer belongs on the
            # job she asked about. Feeding it to hear() instead (the old path)
            # dropped one-word answers entirely via the fragment guard, and
            # re-triaged longer ones into DUPLICATE jobs, while the reply
            # cheerfully said "Sunday it is".
            if changes:
                acted = self._amend(pending_id, changes)
                if acted == "ambiguous":
                    parsed["reply"] = self._which_one()
                    acted, asked_back = None, True
            if not acted and not asked_back and not learned and not resumed:
                # Nothing absorbed it — treat it as a fresh thought.
                spoken = self._think(text)
                if spoken:
                    parsed["reply"] = spoken
        elif intent in ("new_request", "chat"):
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
            spoken = self._think(text)
            if spoken:
                parsed["reply"] = spoken

        # An answer that answers nothing is not an answer. On 2026-08-02 she
        # asked for his name, email and phone to finish a booking; he replied
        # "Do it"; she said "Got it, I'll finish up that booking now" — and
        # then did nothing, because he had supplied nothing. Saying she is
        # getting on with it while the task is still blocked is the one thing
        # that makes her useless to trust. Enforced here, in code, rather than
        # asked for in a prompt: if nothing was learned, resumed or acted on,
        # she does not get to claim progress.
        if (intent in ("answer", "confirm", "modify")
                and not (learned or resumed or acted or asked_back)):
            still = self._blocked()
            if still:
                parsed["reply"] = self._still_need(still)

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
                if job and not self._references(reply, job):
                    goal = job.get("goal", "that").replace("_", " ")
                    if verb == "cancelled":
                        reply = f"Okay — I've scrapped the {goal}."
                    elif verb == "amended":
                        # An amendment is NOT a release: saying "it's moving"
                        # about a still-held job makes the owner stop replying
                        # and the job waits forever.
                        reply = f"Updated — {goal} is still waiting on your go-ahead."
                    else:
                        reply = f"On it — {goal} is moving."
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
            filt = 'status="needs_user"'
            if self.anticipy.owner_id:
                filt += f' && owner="{self.anticipy.owner_id}"'
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
                            "remembered_need": (kept or "")[:300]})
            return out
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
            r = pb.get(f"{base}/api/collections/owner_profile/records",
                       params={"perPage": 1, "sort": "-updated"}, timeout=10)
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
            pb.patch(f"{base}/api/collections/owner_profile/records/{rec['id']}",
                     json={"facts": json.dumps(known)}, timeout=10)
            return clean
        except Exception:
            return {}

    @staticmethod
    def _answers_need(learned: dict, needs: str) -> bool:
        """Does what he just told her cover what this task said it needed?

        The task states its own requirement in words ("I need your first name,
        last name, email address, and phone number"), and the facts she stored
        are keyed by what they are. Matching the two is what lets several
        tasks be blocked at once without her having to guess between them."""
        text = (needs or "").lower()
        if not text:
            return False
        # Words that carry no meaning of their own: a task asking for a
        # "phone" is asking for phone_number, and one asking for an "email"
        # is asking for email_address.
        generic = {"number", "address", "code", "id", "of", "the", "a"}
        for key in learned:
            phrase = str(key).replace("_", " ").lower().strip()
            if not phrase:
                continue
            if phrase in text:
                return True
            parts = [p for p in phrase.split() if p not in generic and len(p) > 2]
            if not parts:
                continue
            if " ".join(parts) in text:
                return True
            # The head noun, as a substring so date_of_birth still answers a
            # task that said "birthday".
            if parts[-1] in text:
                return True
        return False

    def _resume_stuck(self, learned: Optional[dict] = None) -> Optional[str]:
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
            if self.anticipy.owner_id:
                filt += f' && owner="{self.anticipy.owner_id}"'
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
            matched = [j for j in items if self._answers_need(learned, _need_text(j))]
            if not matched and len(items) == 1 and learned:
                # Nothing named, but only one thing is waiting and he did tell
                # her something — the long-standing behaviour, kept.
                matched = items
            if not matched:
                return None
            resumed = [self._requeue(j) for j in matched]
            resumed = [rid for rid in resumed if rid]
            return f"resumed:{resumed[0]}" if resumed else None
        except Exception:
            return None

    def _requeue(self, job: dict) -> Optional[str]:
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
            pb.patch(f"{base}/api/collections/jobs/records/{job['id']}",
                     json={"status": "queued", "params": json.dumps(params)}, timeout=10)
            return job["id"]
        except Exception:
            return None

    def _think(self, text: str) -> Optional[str]:
        """Hand it to the one brain and bring back what she decided to say.

        Her message comes back as THIS reply rather than going out as a second
        text. Without that, a new request produced two: the classifier's "got
        it, I can look into that" and, moments later, hear()'s own "want me to
        go ahead?". Same thread, same thought, twice."""
        try:
            out = self.anticipy.hear(text, may_say=lambda *a, **k: False) or {}
        except TypeError:
            # An Anticipy without the may_say hook (older core, or a test
            # double): fall back rather than losing the thought entirely.
            try:
                out = self.anticipy.hear(text) or {}
            except Exception:
                return None
        except Exception:
            return None
        decision = getattr(out.get("decision"), "decision", "")
        if decision in ("act", "ask"):
            return out.get("anticipy_says") or None
        return None

    # ------------------------------------------------------------ internals

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

    def _thread_from_record(self, phone: str, limit: int = 10) -> list[Turn]:
        """Recent turns reconstructed from the backend, newest last."""
        try:
            r = pb.get(
                f"{self.anticipy.backend_url}/api/collections/events/records",
                params={"filter": 'kind="anticipy_says" || kind="sms_reply"',
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
                role = "anticipy" if ev.get("kind") == "anticipy_says" else "owner"
                turns.append(Turn(role, text))
            return turns
        except Exception:
            return []

    def _pending(self) -> list[dict]:
        try:
            filt = 'status="awaiting_confirm"'
            if self.anticipy.owner_id:
                filt += f' && owner="{self.anticipy.owner_id}"'
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

    def _classify(self, phone: str, text: str) -> dict:
        thread = [{"who": t.role, "text": t.text} for t in self._thread(phone)[-10:]]
        memory = [f["fact"] for f in self.anticipy.memory.recall(text, limit=3)]
        payload = json.dumps({"thread": thread, "pending": self._pending(),
                              "blocked": self._blocked(), "memory": memory,
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
        if short and re.search(r"\b(no|nope|don'?t|forget it|cancel|stop|scrap it)\b", low):
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

    def _which_one(self, cancel: bool = False) -> str:
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
        pending = self._open_work() if cancel else self._pending()
        verb = "call off" if cancel else "go ahead with"
        if not pending:
            return "Nothing's waiting on you right now — what do you mean?"
        self._offered = [p["id"] for p in pending]
        listed = ", ".join(f"{i}) {p['goal'].replace('_', ' ')}"
                           for i, p in enumerate(pending, 1))
        return f"Just to be sure — which one should I {verb}: {listed}?"

    # Words he might use instead of a digit. Ordinals only — this never tries
    # to interpret meaning, just position in the list she herself offered.
    _ORDINALS = {"first": 1, "1st": 1, "one": 1, "second": 2, "2nd": 2,
                 "two": 2, "third": 3, "3rd": 3, "three": 3, "fourth": 4,
                 "4th": 4, "four": 4, "fifth": 5, "5th": 5, "five": 5}

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
        offered = list(getattr(self, "_offered", []) or [])
        if not offered:
            # A redeploy cleared it. Rebuild from the numbered question she
            # actually sent — her own format, parsed back, then matched to
            # what is still pending so a stale number cannot release
            # something that is no longer waiting.
            offered = self._offered_from_thread()
        if not offered or idx > len(offered):
            return None
        chosen = offered[idx - 1]
        return chosen if any(p["id"] == chosen for p in self._pending()) else None

    def _offered_from_thread(self) -> list[str]:
        """Recover the order from her last numbered question."""
        for turn in reversed(self._thread_from_record("", limit=10)):
            if turn.role != "anticipy" or "which one" not in turn.text.lower():
                continue
            goals = re.findall(r"\d\)\s*([^,?]+)", turn.text)
            if not goals:
                continue
            pending = self._pending()
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
            return r.json() if r.ok else None
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
        for job in self._pending() + self._blocked():
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
            if not job:
                return None
            if owner_text is not None and len(pending) > 1 \
                    and not self._references(owner_text, job):
                return "ambiguous"
            return job
        if len(pending) == 1:
            return pending[0]
        return "ambiguous" if pending else None

    def _release(self, job_id: Optional[str], changes: Optional[dict],
                 owner_text: str = "") -> Optional[str]:
        job = self._job(job_id, owner_text)
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        # Only a job still waiting on the owner may be released. Without this,
        # a model-supplied id could re-queue a cancelled/failed/done job — the
        # resurrection class the 2026-07-31 audit flagged.
        if job.get("status") != "awaiting_confirm":
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
        params["approved_scope"] = (
            f"Task: {job.get('goal', '')}. "
            f"They said: \"{(owner_text or 'yes').strip()}\". "
            f"Heard originally: {params.get('source', '')}"
        ).strip()
        if changes:
            params.update(changes)
        fields = {"status": "queued", "params": json.dumps(params)}
        return self._flip(job["id"], fields, "released")

    def _cancel(self, job_id: Optional[str], owner_text: str = "") -> Optional[str]:
        job = self._job(job_id, owner_text, pool=self._open_work())
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        return self._flip(job["id"], {"status": "cancelled"}, "cancelled")

    def _amend(self, job_id: Optional[str], changes: dict) -> Optional[str]:
        job = self._job(job_id)
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        try:
            params = json.loads(job.get("params") or "{}")
        except Exception:
            params = {}
        params.update(changes)
        return self._flip(job["id"], {"params": json.dumps(params)}, "amended")

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
