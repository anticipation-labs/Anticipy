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
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import requests

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
- "answer": they are answering a question you asked; capture the substance
  in changes.
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

        acted = None
        if intent == "confirm":
            acted = self._release(pending_id, changes)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one()
                acted = None
        elif intent == "decline":
            acted = self._cancel(pending_id)
            if acted == "ambiguous":
                parsed["reply"] = self._which_one(cancel=True)
                acted = None
        elif intent == "modify" and pending_id and changes:
            acted = self._amend(pending_id, changes)
        elif intent in ("new_request", "answer"):
            # Feed it back through the one brain — same path as the pendant.
            self.anticipy.hear(text)

        reply = parsed.get("reply") or "Got it."
        self.say(phone, reply)
        return {"intent": intent, "pending_id": pending_id,
                "changes": changes, "acted": acted, "reply": reply}

    # ------------------------------------------------------------ internals

    def _thread(self, phone: str) -> list[Turn]:
        return self.threads.setdefault(phone, [])

    def _pending(self) -> list[dict]:
        try:
            filt = 'status="awaiting_confirm"'
            if self.anticipy.owner_id:
                filt += f' && owner="{self.anticipy.owner_id}"'
            r = requests.get(
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
                              "memory": memory, "owner_text": text})
        if self.llm and self.llm.live:
            try:
                return self._parse(self.llm.chat(REPLY_SYSTEM, payload).text)
            except Exception:
                pass
        # Offline fallback keeps the old keyword behavior so tests run keyless.
        low = text.lower().strip()
        if any(w in low for w in ("yes", "go ahead", "send it", "do it", "confirm")):
            return {"intent": "confirm", "pending_id": None, "reply": "On it."}
        if any(w in low for w in ("no", "don't", "forget it", "cancel", "stop")):
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

    def _job(self, job_id: Optional[str]):
        """Resolve the job the owner means. Falls back to the pending item
        ONLY when there is exactly one — with several (or none), guessing is
        how the wrong thing gets sent or cancelled."""
        if job_id:
            try:
                r = requests.get(
                    f"{self.anticipy.backend_url}/api/collections/jobs/records/{job_id}",
                    timeout=10)
                if r.ok:
                    return r.json()
            except Exception:
                return None
        pending = self._pending()
        if len(pending) == 1:
            return pending[0]
        return "ambiguous" if pending else None

    def _release(self, job_id: Optional[str], changes: Optional[dict]) -> Optional[str]:
        job = self._job(job_id)
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        fields = {"status": "queued"}
        if changes:
            try:
                params = json.loads(job.get("params") or "{}")
            except Exception:
                params = {}
            params.update(changes)
            fields["params"] = json.dumps(params)
        requests.patch(
            f"{self.anticipy.backend_url}/api/collections/jobs/records/{job['id']}",
            json=fields, timeout=10)
        return f"released:{job['id']}"

    def _cancel(self, job_id: Optional[str]) -> Optional[str]:
        job = self._job(job_id)
        if job == "ambiguous":
            return "ambiguous"
        if not job:
            return None
        requests.patch(
            f"{self.anticipy.backend_url}/api/collections/jobs/records/{job['id']}",
            json={"status": "cancelled"}, timeout=10)
        return f"cancelled:{job['id']}"

    def _amend(self, job_id: Optional[str], changes: dict) -> Optional[str]:
        job = self._job(job_id)
        if job == "ambiguous" or not job:
            return None
        try:
            params = json.loads(job.get("params") or "{}")
        except Exception:
            params = {}
        params.update(changes)
        requests.patch(
            f"{self.anticipy.backend_url}/api/collections/jobs/records/{job['id']}",
            json={"params": json.dumps(params)}, timeout=10)
        return f"amended:{job['id']}"
