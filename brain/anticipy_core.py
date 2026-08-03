"""Anticipy — the one who's responsible for everything.

Anticipy is the orchestrator AND its personality. One mind that:
- hears every transcript line and files it into the temporal memory graph,
- decides what matters (ignore / ask / act) with memory as context,
- delegates: browser work to the action arm (extension / browser-use via the
  job queue), texts and calls to the voice arm (Twilio),
- tracks every open loop (commitment) until it's done,
- speaks in the first person: "I caught X — I'm handling it. I'll ask
  before anything goes out." ("caught"/"heard", never "overheard" — she's
  a partner, not an eavesdropper)

Nothing irreversible executes without confirmation — that gate lives in the
job queue, outside any model.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from . import pb

from .llm import LLM, now_line
from .memory import Memory
from .orchestrator import Brain, Decision, IRREVERSIBLE

NAME = "Anticipy"

# Policy layer OUTSIDE the model: any goal whose text implies something that
# leaves the owner's world (sending, booking, buying, signing up, calling,
# posting, deleting) is held for confirmation regardless of what triage said.
# LLM goal strings are free-form, so exact-match sets are not enough.
_VERBS = (
    r"send\w*|email\w*|book\w*|reserv\w*|buy\w*|purchas\w*|order\w*|pay\w*|"
    r"sign(?:\s+\w+)?\s*up|sign\w*|register\w*|subscrib\w*|submit\w*|post\w*|publish\w*|"
    r"repl(?:y|ies|ying)|messag\w*|text\w*|call\w*|cancel\w*|delet\w*|"
    r"unsubscrib\w*|transfer\w*|schedul\w*|invit\w*|rsvp|book\w*|"
    r"shar\w*|forward\w*|respond\w*|confirm\w*|appl(?:y|ies|ying)|"
    r"wire|venmo|e-?transfer|donat\w*|checkout|check\s*out|upload\w*|deposit\w*"
)
# Only in ACTION position — the start of the goal, or after and/then/to/&/comma.
# A verb buried in a noun phrase is not an action: "noise CANCELLING
# headphones" and "MEETING notes" are not things that leave the owner's world,
# and holding them taught the owner to tap through prompts without reading.
_IRREVERSIBLE_RE = re.compile(
    r"(?:^|\b(?:and|then|to|also|please|&)\s+|,\s*)(?:" + _VERBS + r")\b",
    re.IGNORECASE,
)

# Goals that only READ the world. Anything not clearly read-only is held —
# the safe default, because a missed verb means something leaves the owner's
# world without their word, while an over-hold costs one tap.
_READ_ONLY_RE = re.compile(
    r"^\s*(research|compar\w*|look\s*up|find|check(?!\s*out)\w*|search\w*|read\w*|"
    r"summar\w*|gather\w*|browse|price|monitor|watch|list|"
    r"open(?!\s+(?:an?\s+)?account)|go\s+to|visit|navigat\w*|show|load|"
    r"pull\s+up|view|display|tell)\b",
    re.IGNORECASE,
)


def is_consequential(goal: str, params: dict | None = None,
                     explicit: bool = False) -> bool:
    """Does this goal change the world? Judged on the GOAL only — params carry
    the raw transcript, whose stray words ("cancel my flight" mentioned in
    passing) must not decide whether a research task is held.

    explicit=True means the owner ASKED for this in so many words (a direct
    text/command, not something overheard). Their ask is the go-ahead, so only
    goals that actually leave their world (send/book/buy…) are still held —
    making them confirm "open wikipedia" teaches them to tap through prompts
    without reading."""
    g = (goal or "").strip()
    if _IRREVERSIBLE_RE.search(g):
        return True
    if explicit:
        return False
    # Overheard: default to holding — only explicitly read-only runs unattended.
    return not _READ_ONLY_RE.search(g)

# How the best text-native agents actually sound (studied: Tomo — the
# iMessage coach people text 20 days a month because check-ins read like a
# friend who remembers, "hey how's that thing going?"; and Boardy — a
# persistent character that is curious about the person first and playful
# about its own nature). Shared by every place she speaks.
TEXTING_STYLE = """
How you text (non-negotiable):
- Like a sharp friend over SMS: short, lowercase-casual is fine, contractions
  always. Most texts are one sentence; two is the ceiling.
- Reference the specific thing and the specific detail, never a category —
  "the 7:30 at Cactus Club" beats "your reservation".
- Never open two texts in a row the same way. Ban openers: "Hey, just",
  "Just a quick", "Just checking", "I wanted to", "Friendly reminder".
- One question max, and only the question that actually unblocks you.
- Never repeat a question they haven't answered — a follow-up must add
  something new (a deadline getting closer, an easier way to answer).
- No emojis, no exclamation cheer, no corporate filler ("I'll go ahead and"),
  no restating what they just said back at them.
- Match their energy: terse gets terse, chatty gets a little warmth.
- Own mistakes plainly ("my fault — scrapping it") and never over-apologize."""

VOICE_SYSTEM = f"""You are {NAME}, texting the person whose day you share. You
are their sharp, warm chief of staff — a real human voice, never a template.
Write ONE or two short sentences, specific to this exact moment: name the
actual thing (the restaurant, the person, the date), not a category. Vary
your shape and opening every time; plain words; no emojis; no corporate
filler; no exclamation-point cheer. If you're asking, ask exactly ONE clear
question — the single thing that unblocks you. If you relied on an assumption
from earlier context, say it casually so they can correct you. If you're
starting something consequential, make clear in your own words that nothing
goes out until they give the word.
{TEXTING_STYLE}"""


CLOCK_SYSTEM = f"""You are {NAME}, reviewing your open loops on your own
initiative — nobody spoke; the CLOCK woke you. You are a great chief of
staff, which means you initiate RARELY and only when timing makes it
genuinely valuable: a plan whose date is approaching with nothing arranged,
a commitment going stale, a promise whose deadline is near. Mere existence
of an open loop is NOT a reason to speak — most reviews should conclude
"stay quiet". Never nag, never repeat an outreach about the same loop.
Given the local time and your open loops (each with its age), decide whether
to reach out NOW. If yes, write the text in your own warm human voice —
short, specific, one question at most.
Reply ONLY with compact JSON:
{{"initiate":true|false,"say":"<the text, or null>","goal":"<job goal to prepare, or null>","loop_ids":[<ids you are acting on>],"reason":"<8 words>"}}"""


BRIEFING_SYSTEM = f"""You are {NAME}, the person's personal assistant who lives
in their Anticipy pendant. You are warm, brief, and competent — a trusted
chief-of-staff, never a robot. Given what you heard today and your open
to-dos, write a 2-4 sentence spoken-style briefing in the first person, e.g.:
"You promised Sarah the pitch deck — I've got a draft ready and I'll send it
the second you say so." Open naturally and vary it — never a canned greeting,
never the same opening twice. Say "heard" or "caught", never "overheard" —
you're their partner, not an eavesdropper. Never invent things that aren't in
the notes. Every item carries a status — only say something is done if its
status is "done"; declined or cancelled items were NOT done; anything else is
at most "in progress" or "waiting on you". No emojis, no bullets."""


@dataclass
class LoopRecord:
    """One open loop Anticipy is personally responsible for closing."""
    commitment_id: int
    what: str
    status: str = "handling"     # handling | awaiting_ok | done | failed
    job_id: Optional[str] = None
    opened_ts: float = field(default_factory=time.time)


class Anticipy:
    def __init__(
        self,
        memory: Optional[Memory] = None,
        llm: Optional[LLM] = None,
        backend_url: str = "http://127.0.0.1:8090",
        voice=None,
        owner_phone: Optional[str] = None,
        owner_id: str = "",
        conversation=None,
    ):
        self.llm = llm
        self.memory = memory or Memory(llm=llm)
        self.brain = Brain(llm=llm) if llm else None
        self.backend_url = backend_url.rstrip("/")
        self.voice = voice
        self.owner_phone = owner_phone
        self.owner_id = owner_id
        self.conversation = conversation
        self.loops: list[LoopRecord] = []
        self.session_start = time.time()
        self._prev: Optional[tuple[str, float]] = None  # (last ignored line, ts)

    # ------------------------------------------------------------ hearing

    # Deliberately narrow. These used to fire on ambient speech — "where are
    # we going for dinner with the Hendersons?" was answered with a status
    # report, and the line never reached memory at all.
    _BRIEFING_RE = re.compile(
        r"(give me (a|my|the) (briefing|debrief|rundown)|catch me up|"
        r"what('?s| is) (still )?(open|left|outstanding|pending)\b|"
        r"where do (we|things) stand|status update|what do you have for me)",
        re.IGNORECASE)
    # A real question ENDS in a question mark; imperatives never do. "Remind
    # me to call the dentist" is a task, not a memory lookup.
    _RECALL_RE = re.compile(
        r"^\s*(what|when|who|where|which|did|do|have|has)\b.*\?\s*$",
        re.IGNORECASE)
    _IMPERATIVE_RE = re.compile(r"^\s*(remind me to|remember to|make sure)\b", re.IGNORECASE)

    @staticmethod
    def _may_say(may_say, text: str, goal: Optional[str], kind: str) -> bool:
        """One rule for every unprompted thing she says: has she already
        brought this up? The caller owns the check because it needs the record
        of what actually went out, which lives in the backend rather than in
        this process — a redeploy must not hand her a clean slate and a reason
        to repeat herself."""
        if not may_say:
            return True
        try:
            return bool(may_say(text, goal or "", kind))
        except Exception as e:
            # A broken guard must never silence a genuine message.
            print(f"may_say check failed ({kind}): {e}")
            return True

    def hear(self, line: str, context: Optional[list[str]] = None,
             may_say=None, explicit: bool = False) -> dict:
        """One transcript line in; memory, decision, and delegation out."""
        # Owner questions are answered, not triaged: a briefing request goes
        # to the briefing engine, and a memory question is answered straight
        # from the graph. Neither should ever spawn a browser job.
        if self._BRIEFING_RE.search(line):
            # Remember it either way — the early return used to skip ingest,
            # so anything phrased like a briefing request left no trace.
            mem = self.memory.ingest(line)
            said = self.status_report() if re.search(
                r"open|left|outstanding|pending|status|stand", line, re.I) \
                else self.briefing()
            return {"memory": mem, "decision": Decision(
                decision="answer", goal=None, reason="briefing request"),
                "anticipy_says": said}
        if self._RECALL_RE.match(line) and not self._IMPERATIVE_RE.match(line):
            answer = self._answer_from_memory(line)
            if answer:
                mem = self.memory.ingest(line)
                return {"memory": mem, "decision": Decision(
                    decision="answer", goal=None, reason="memory recall"),
                    "anticipy_says": answer}
        mem = self.memory.ingest(line)
        # A stray fragment ("Tomorrow", "Okay") carries no intent of its own,
        # but related memories injected as context can make triage hallucinate
        # one — live incident: the single word "Tomorrow" plus a stale memory
        # spawned a full draft-email job. Fragments are remembered, never acted on.
        if len(line.split()) < 2:
            self._prev = (line, time.time())
            return {"memory": mem, "decision": Decision(
                decision="ignore", goal=None, reason="fragment, no intent"),
                "anticipy_says": None}
        # Split-thought context is only the last line, only if it's recent
        # (people pause seconds, not hours), and only if it wasn't already
        # acted on — an acted line re-fed as context mints duplicate jobs.
        prev = self._prev
        prev_line = prev[0] if prev and time.time() - prev[1] < 120 else None
        decision = self._decide(line, mem, prev_line=prev_line, convo=context)
        self._prev = None if decision.decision in ("act", "ask") else (line, time.time())
        handled = None

        # Sufficiency: starting work that is guaranteed to stall on an unknown
        # is worse than one good question. An "act" with essential unknowns
        # becomes that question — the generic behavior, never a special case.
        if decision.decision == "act" and decision.missing:
            decision = Decision(
                decision="ask", goal=decision.goal, reason=decision.reason,
                missing=decision.missing, assumption=decision.assumption)

        if decision.decision == "act" and decision.goal:
            # The executor needs temporal ground truth: a job run today with
            # no "now" produced an OpenTable result dated a YEAR in the past.
            params = {"source": line, "now": now_line()}
            if decision.assumption:
                params["assumption"] = decision.assumption
            # The EFFECTIVE hold: triage's flag OR the policy layer. The owner
            # must be told whenever the job is actually held, or held jobs
            # would sit silently forever.
            held = (decision.needs_confirmation
                    or decision.goal in IRREVERSIBLE
                    or is_consequential(decision.goal, params, explicit=explicit))
            # Was this already waiting on him before he said it again? The
            # queue has deduped identical goals since the five-copies incident,
            # but the TEXT went out every single time regardless — which is why
            # his history has six messages about one email to Marcus. If it was
            # already pending she has already asked; saying it again is nagging,
            # not diligence.
            repeat = bool(self._same_pending(decision.goal))
            job_id = self._queue_job(decision.goal, params, hold=held,
                                     explicit=explicit)
            loop = LoopRecord(
                commitment_id=mem.get("commitment_id") or -1,
                what=decision.goal,
                status="awaiting_ok" if held else "handling",
                job_id=job_id,
            )
            self.loops.append(loop)
            # Her words are GENERATED for this exact moment — a template can
            # never sound like a person.
            handled = self._voice({
                "situation": "held for approval" if held else "quietly started",
                "heard": line, "goal": decision.goal,
                "assumption": decision.assumption,
            }) or self.say_handling(decision.goal, held)
            # Details first, browser second: before anything irreversible she
            # texts the owner — their go-ahead releases the held job.
            if held and not repeat and self._may_say(may_say, handled, decision.goal, "act"):
                self.notify_owner(handled)
            elif held:
                print(f"already waiting on him for {decision.goal!r} — not asking twice")
        elif decision.decision == "ask":
            handled = self._voice({
                "situation": "one essential detail is missing before you can start",
                "heard": line, "goal": decision.goal,
                "missing": decision.missing or [decision.reason or "what exactly they want"],
                "assumption": decision.assumption,
            }) or f"Quick question — {(decision.missing or [decision.reason or 'want me to take this on'])[0]}?"
            # A question is unprompted speech too, and this branch used to text
            # him every single time with no guard whatever — the held-job path
            # at least had the queue's own dedup behind it. On 2026-07-31 that
            # produced "I need the location for Sharky's Diner before I can
            # check their hours" twice, seventeen seconds apart, and again
            # twenty minutes later. Asking is fine; asking the same thing over
            # and over is what made her exhausting.
            if self._may_say(may_say, handled, decision.goal, "ask"):
                self.notify_owner(handled)
            else:
                print(f"already asked him about {decision.goal!r} — staying quiet")

        return {
            "memory": mem,
            "decision": decision,
            "anticipy_says": handled,
        }

    def _decide(self, line: str, mem: dict, prev_line: Optional[str] = None,
                convo: Optional[list[str]] = None) -> Decision:
        if self.brain:
            context = self.memory.recall(line, limit=4)
            prompt = line
            # What was already said in THIS conversation. Without it a
            # question lands naked — "what time is the demo day Monday" with
            # no idea which demo day, which is exactly what happened live.
            if convo:
                earlier = " | ".join(c for c in convo[-6:] if c and c != line)
                if earlier:
                    prompt = f"{prompt}\n(Earlier in this conversation: {earlier})"
            # People think across pauses: "I'll send the Devon invoice" …
            # "tomorrow morning". The previous line rides along as background
            # so a split thought still triages as one thought.
            if prev_line:
                prompt = f"{prompt}\n(Previous line, background: {prev_line})"
            if context:
                notes = "; ".join(f["fact"] for f in context)
                prompt = f"{prompt}\n(Related memory: {notes})"
            return self.brain.triage(prompt)
        # Deterministic offline path: a fresh commitment means act.
        if mem.get("commitment"):
            return Decision(decision="act", goal="agent_goal",
                            reason="heard a commitment", needs_confirmation=True)
        return Decision(decision="ignore", goal=None, reason="nothing to do")

    # ------------------------------------------------------------ speaking

    def _voice(self, context: dict) -> Optional[str]:
        """Generate what Anticipy says for this exact moment. Returns None
        without a live LLM (callers keep a plain fallback) — but with one,
        her voice is never assembled from a template."""
        if not self.llm:
            return None
        try:
            res = self.llm.chat(VOICE_SYSTEM, json.dumps(context), temperature=0.7)
            text = res.text.strip().strip('"')
            return text or None
        except Exception:
            return None

    def say_handling(self, goal: str, needs_ok: bool) -> str:
        # Goal strings are free-form model output ("prepare Devon invoice
        # email") — jamming them after "the" reads broken ("preparing the
        # prepare Devon invoice email"). A colon keeps any goal grammatical.
        pretty = goal.replace("_", " ").strip()
        if needs_ok:
            return f"I caught that — on it: {pretty}. Nothing goes out until you say so."
        return f"On it: {pretty}."

    def _answer_from_memory(self, question: str) -> Optional[str]:
        """Answer an owner question straight from the graph. Returns None when
        memory doesn't hold the answer, so the line falls through to triage."""
        q_norm = question.strip().lower()
        facts = [f["fact"] + (f' \u2014 original: "{f["quote"]}"'
                              if f.get("quote") and f["quote"] not in f["fact"] else "")
                 for f in self.memory.recall(question, limit=8)
                 # An earlier asking of this same question is not evidence.
                 if (f.get("quote") or "").strip().lower() != q_norm]
        if not facts:
            return None
        if self.llm:
            try:
                res = self.llm.chat(
                    f"You are {NAME}, answering the owner's question over SMS. "
                    "Use ONLY the memory notes given. If the notes contain the "
                    "answer, reply in 1-2 warm, direct sentences quoting the "
                    "specifics (names, times, things promised). If the notes do "
                    "NOT contain the answer, reply with exactly NO_ANSWER.",
                    json.dumps({"question": question, "memory": facts}),
                )
                text = res.text.strip()
                if text and "NO_ANSWER" not in text:
                    return text
                return None
            except Exception:
                pass
        return "Here's what I remember: " + "; ".join(facts[:3])

    def status_report(self) -> str:
        """What's still open — grounded in live queue statuses, never claims."""
        loops = self.review_loops()
        open_loops = [l for l in loops if l["status"] in
                      ("handling", "awaiting_ok", "needs_you")]
        done = [l for l in loops if l["status"] == "done"]
        parts = []
        if open_loops:
            named = "; ".join(
                f"{l['what'].replace('_', ' ')} ({'waiting on you' if l['status'] == 'awaiting_ok' else 'needs you' if l['status'] == 'needs_you' else 'in progress'})"
                for l in open_loops)
            parts.append(f"Still open: {named}.")
        else:
            parts.append("Nothing's open — all loops are closed.")
        if done:
            parts.append(f"Done today: {'; '.join(l['what'].replace('_', ' ') for l in done)}.")
        return " ".join(parts)

    def briefing(self) -> str:
        """Anticipy's greeting: what she heard, what she's handling."""
        facts = self.memory.briefing_facts(self.session_start)
        # Ground the briefing in actual outcomes so she never claims a thing
        # happened that didn't.
        facts["task_statuses"] = [{"what": l.what, "status": l.status}
                                  for l in self.loops]
        if self.llm:
            try:
                res = self.llm.chat(BRIEFING_SYSTEM, json.dumps(facts))
                text = res.text.strip()
                if text:
                    return text
            except Exception:
                pass
        heard = facts["heard"]
        loops = facts["open_loops"]
        parts = [f"How goes it today? I'm {NAME}."]
        if heard:
            parts.append(f"I caught {len(heard)} thing{'s' if len(heard) != 1 else ''} worth remembering.")
        if loops:
            what = "; ".join(l["what"] for l in loops[:3])
            parts.append(f"I'm handling: {what}. I'll ask before anything goes out.")
        else:
            parts.append("Nothing needs you right now — go live your day.")
        return " ".join(parts)

    # ----------------------------------------------------------- voice arm

    def notify_owner(self, message: str, channel: str = "sms") -> Optional[dict]:
        # A failed text must never abort the hearing loop — the job is already
        # queued and the app still surfaces it under "Needs your OK".
        try:
            # Conversational channel first: she opens a real thread, not a
            # "reply YES" wall; replies come back via Conversation.on_reply.
            if self.conversation and self.owner_phone and channel == "sms":
                return self.conversation.reach_out(self.owner_phone, message)
            if not (self.voice and self.owner_phone):
                return None
            if channel == "call":
                return self.voice.call(self.owner_phone, message)
            return self.voice.text(self.owner_phone, message)
        except Exception as e:
            print(f"notify_owner failed ({channel}): {e}")
            return None

    # ---------------------------------------------------------- action arm

    def _queue_job(self, goal: str, params: dict, hold: bool = False,
                   explicit: bool = False) -> Optional[str]:
        # Mentioning the same thing twice must not produce two identical items
        # waiting on the owner. Five copies of "Draft email to Marcus" piled up
        # in production, each one texting him, and every "yes" after that was
        # ambiguous by construction — so she had to ask which one, forever.
        existing = self._same_pending(goal)
        if existing:
            return existing
        try:
            r = pb.post(
                f"{self.backend_url}/api/collections/jobs/records",
                json={"goal": goal, "params": json.dumps(params),
                      "status": "awaiting_confirm"
                      if (hold or goal in IRREVERSIBLE
                          or is_consequential(goal, params, explicit=explicit))
                      else "queued",
                      "device_id": "anticipy", "owner": self.owner_id},
                timeout=10,
            )
            r.raise_for_status()
            return r.json().get("id")
        except Exception:
            return None

    # ------------------------------------------------------------ the clock

    def clock_tick(self, now: Optional[float] = None,
                   already_reached_out: set | None = None,
                   may_say=None) -> Optional[dict]:
        """Layer-2 proactivity: fired by TIME, not speech. Reviews open loops
        and decides — same reasoning doctrine, zero hardcoded triggers —
        whether a great assistant would initiate right now. Guardrails live
        OUTSIDE the model: the caller enforces quiet hours and outreach
        rate limits; this method only reasons and speaks."""
        if not self.llm:
            return None
        loops = self.memory.open_loops()
        if not loops:
            return None
        ts = now or time.time()
        reached = already_reached_out or set()
        candidates = [l for l in loops if l["id"] not in reached]
        # Interrupting him is only earned by evidence. A loop she cannot quote
        # him on is one she invented — on 2026-08-01 that shipped real texts
        # about "car insurance renewal" and "Vienna plans" he had never once
        # mentioned, twice each. Unevidenced loops stay in memory and stay
        # searchable; they simply never justify a text.
        fresh = [l for l in candidates if (l.get("source") or "").strip()]
        if len(fresh) < len(candidates):
            mute = [l["what"] for l in candidates if not (l.get("source") or "").strip()]
            print(f"clock: not raising {len(mute)} unevidenced loop(s): {mute[:5]}")
        if not fresh:
            return None
        from .llm import TZ
        from datetime import datetime as _dt
        payload = {
            # Owner-local, not container-UTC — must agree with the grounded
            # now-line every prompt already carries.
            "local_time": _dt.fromtimestamp(ts, TZ).strftime("%A %H:%M"),
            "open_loops": [
                {"id": l["id"], "what": l["what"],
                 "age_hours": round((ts - l["ts"]) / 3600, 1),
                 # His own words. Reasoning from the quote rather than from a
                 # summary is what keeps her from drifting into a topic he
                 # never raised.
                 "he_said": l["source"]}
                for l in fresh[:10]
            ],
        }
        try:
            res = self.llm.chat(CLOCK_SYSTEM, json.dumps(payload), temperature=0.3)
            raw = json.loads(res.text[res.text.find("{"): res.text.rfind("}") + 1])
        except Exception:
            return None
        if not raw.get("initiate") or not raw.get("say"):
            return None
        say = str(raw["say"]).strip()
        goal = raw.get("goal")
        if goal in ("", "null"):
            goal = None
        # The caller owns the durable "have I already brought this up?" check —
        # it needs the record of what actually went out, which lives in the
        # backend, not in this process. It is given the goal as well as the
        # words, because she rephrases every time and only the goal is stable.
        # Refusing here means nothing is queued and nothing is marked reached:
        # the loop is simply left alone.
        if not self._may_say(may_say, say, goal, "clock"):
            print(f"clock: already raised this, staying quiet -> {say!r}")
            return None
        if goal:
            # Anything she prepares unprompted goes through the same gate as
            # everything else — held if consequential, never auto-sent.
            held = is_consequential(goal)
            job_id = self._queue_job(
                goal, {"source": "clock initiative", "say": say,
                       "now": now_line()}, hold=held)
            # Without a LoopRecord the job is invisible to status_report() and
            # briefing(): she'd text about a booking, then answer "what's
            # open?" with "nothing".
            loop_ids = [int(i) for i in raw.get("loop_ids", []) if str(i).isdigit()]
            self.loops.append(LoopRecord(
                commitment_id=loop_ids[0] if loop_ids else -1,
                what=goal,
                status="awaiting_ok" if held else "handling",
                job_id=job_id,
            ))
        self.notify_owner(say)
        return {"say": say, "goal": goal,
                "loop_ids": [int(i) for i in raw.get("loop_ids", []) if str(i).isdigit()]}

    def _same_pending(self, goal: str) -> Optional[str]:
        """Is this same thing already waiting on the owner? Compared on
        meaningful words, because the model phrases the same intent slightly
        differently each time it hears it."""
        want = {w for w in re.findall(r"[a-z0-9']+", (goal or "").lower()) if len(w) > 3}
        if not want:
            return None
        try:
            filt = 'status="awaiting_confirm" || status="queued"'
            if self.owner_id:
                filt = f'({filt}) && owner="{self.owner_id}"'
            r = pb.get(f"{self.backend_url}/api/collections/jobs/records",
                       params={"filter": filt, "perPage": 20, "sort": "-created"},
                       timeout=10)
            if not r.ok:
                return None
            for j in r.json().get("items", []):
                have = {w for w in re.findall(r"[a-z0-9']+", (j.get("goal") or "").lower())
                        if len(w) > 3}
                if not have:
                    continue
                overlap = len(want & have) / max(len(want), len(have))
                if overlap >= 0.7:
                    return j["id"]
        except Exception:
            pass
        return None

    def review_loops(self) -> list[dict]:
        """Poll the job queue and close loops whose jobs finished."""
        out = []
        for loop in self.loops:
            if loop.job_id and loop.status in ("handling", "awaiting_ok"):
                try:
                    r = pb.get(
                        f"{self.backend_url}/api/collections/jobs/records/{loop.job_id}",
                        timeout=10)
                    status = r.json().get("status")
                    if status == "done":
                        loop.status = "done"
                        if loop.commitment_id > 0:
                            self.memory.resolve(loop.commitment_id)
                    elif status == "failed":
                        loop.status = "failed"
                    elif status == "awaiting_confirm":
                        loop.status = "awaiting_ok"
                    elif status == "needs_user":
                        loop.status = "needs_you"
                    elif status == "cancelled":
                        loop.status = "declined"
                except Exception:
                    pass
            out.append({"what": loop.what, "status": loop.status, "job": loop.job_id})
        return out
