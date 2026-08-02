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
- "decline": calling it off ("actually don't", "forget it", "not yet").
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
- "chat": everything else — reply warmly, keep it short.

Grounding rules (hard):
- Never claim you already did something. Each pending item includes its
  status — nothing is sent/booked/done until its status says "done". Your
  reply after a confirm is "on it" language, never "I sent it".
- pending_id must be the item the owner is actually talking about — match on
  topic. If their text could refer to more than one pending item, or refers
  to something with NO pending item, set pending_id to null AND make your
  reply a clarifying question ("the newsletter or the pitch deck?") — do not
  guess.
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
                resumed = self._resume_stuck()

        acted = None
        if intent == "confirm":
            acted = self._release(pending_id, changes, owner_text=text)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one()
                acted = None
        elif intent == "decline":
            acted = self._cancel(pending_id, owner_text=text)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one(cancel=True)
                acted = None
        elif intent == "modify" and changes:
            # No pending_id is normal (the model is told to null it when
            # unsure); _amend's single-pending fallback resolves it.
            acted = self._amend(pending_id, changes)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one()
                acted = None
        elif intent == "answer":
            # The owner is ANSWERING her question — that answer belongs on the
            # job she asked about. Feeding it to hear() instead (the old path)
            # dropped one-word answers entirely via the fragment guard, and
            # re-triaged longer ones into DUPLICATE jobs, while the reply
            # cheerfully said "Sunday it is".
            asked_back = False
            if changes:
                acted = self._amend(pending_id, changes)
                if acted == "ambiguous":
                    parsed["reply"] = self._which_one()
                    acted, asked_back = None, True
            if not acted and not asked_back and not learned and not resumed:
                # Nothing absorbed it — treat it as a fresh thought.
                self.anticipy.hear(text)
        elif intent == "new_request":
            # Feed it back through the one brain — same path as the pendant.
            self.anticipy.hear(text)

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
not just the most interesting one: a reply often carries several at once
("Omar Ebrahim, omar@x.com, 604 555 0123" is three facts). Only facts about
the PERSON, never about one task, and NEVER card numbers, passwords or
security codes even if they offer them.
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
            return [{"id": j["id"], "goal": j.get("goal", ""),
                     "needs": (j.get("result") or "")[:300]}
                    for j in r.json().get("items", [])]
        except Exception:
            return []

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

    def _resume_stuck(self) -> Optional[str]:
        """Put a task that stopped for a missing detail back to work. It is
        re-read at the start of every run, so it picks up what she just
        learned without anything being passed through by hand."""
        try:
            base = self.anticipy.backend_url
            filt = 'status="needs_user"'
            if self.anticipy.owner_id:
                filt += f' && owner="{self.anticipy.owner_id}"'
            r = pb.get(f"{base}/api/collections/jobs/records",
                       params={"filter": filt, "perPage": 2, "sort": "-updated"}, timeout=10)
            items = r.json().get("items", []) if r.ok else []
            # Only when there is exactly one — guessing which stuck task he
            # meant is the same mistake as guessing which job a bare yes is for.
            if len(items) != 1:
                return None
            job = items[0]
            try:
                params = json.loads(job.get("params") or "{}")
            except Exception:
                params = {}
            params["authorized"] = True
            pb.patch(f"{base}/api/collections/jobs/records/{job['id']}",
                     json={"status": "queued", "params": json.dumps(params)}, timeout=10)
            return f"resumed:{job['id']}"
        except Exception:
            return None

    # ------------------------------------------------------------ internals

    def _thread(self, phone: str) -> list[Turn]:
        return self.threads.setdefault(phone, [])

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
        names = [p["goal"].replace("_", " ") for p in self._pending()]
        verb = "call off" if cancel else "go ahead with"
        if not names:
            return "Nothing's waiting on you right now — what do you mean?"
        return f"Just to be sure — which one should I {verb}: {' or '.join(names)}?"

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

    def _job(self, job_id: Optional[str], owner_text: Optional[str] = None):
        """Resolve the job the owner means. Falls back to the pending item
        ONLY when there is exactly one — with several (or none), guessing is
        how the wrong thing gets sent or cancelled. Even a model-picked id is
        only trusted with several pending when the owner's own words point at
        that job."""
        pending = self._pending()
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
        job = self._job(job_id, owner_text)
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
