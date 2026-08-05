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
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from . import pb

from .llm import LLM, now_line
from .memory import Memory
from .orchestrator import (Brain, Decision, IRREVERSIBLE, ADDRESSEES,
                           AMBIENT_ADDRESSEES, AUTHORED_ADDRESSEES,
                           _extract_json)

NAME = "Anticipy"

# Policy layer OUTSIDE the model: any goal whose text implies something that
# leaves the owner's world (sending, booking, buying, signing up, calling,
# posting, deleting) is held for confirmation regardless of what triage said.
# LLM goal strings are free-form, so exact-match sets are not enough.
# VERB forms only, never the -ation/-ment noun: "find Earls hours and
# reservation options" is research whose sentence happens to contain the
# noun "reservation" in action position, and the broad reserv\w* read it as
# the verb "reserve" — a pure lookup became a held card with a text asking
# permission to look. Same trap for invitation/confirmation/cancellation.
_VERBS = (
    r"send\w*|email\w*|book\w*|reserv(?:e|es|ed|ing)|buy\w*|purchas\w*|order\w*|pay\w*|"
    r"sign(?:\s+\w+)?\s*up|sign\w*|register\w*|subscrib\w*|submit\w*|post\w*|publish\w*|"
    r"repl(?:y|ies|ying)|messag\w*|text\w*|call\w*|cancel(?:s|led|ling|ed|ing)?|delet\w*|"
    r"unsubscrib\w*|transfer\w*|schedul\w*|invit(?:e|es|ed|ing)|rsvp|"
    r"shar\w*|forward\w*|respond\w*|confirm(?:s|ed|ing)?|appl(?:y|ies|ying)|"
    r"wire|venmo|e-?transfer|donat(?:e|es|ed|ing)|checkout|check\s*out|upload\w*|deposit\w*"
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
    # "Plan the weekend at Earls" is PREPARATION — options, hours, logistics
    # — nothing leaves his world until a book/send verb appears. Held "plan"
    # cards were the seed of every two-card night: the model words early
    # vague turns as "plan X", the real "book X" arrives minutes later, and
    # whenever the judge blinked he got two cards and two texts for one
    # dinner.
    r"pull\s+up|view|display|tell|plan(?:s|ned|ning)?\b)",
    re.IGNORECASE,
)


# Addressee pre-filter OUTSIDE the model (roadmap §7.1). The obvious case is
# decided deterministically: a very long, fluent run of instruction-like
# prose with no interlocutor is the owner dictating to a machine (Wispr Flow
# into another AI, voice-typing a message) — nobody speaks paragraphs of
# clean spec at a person. On 2026-08-04 exactly those lines were triaged as
# work for HER, and the owner got "On it" texts about messages he was
# dictating to a different assistant. The model also classifies (folded into
# triage), but for lines this unmistakable her lane must not depend on it.
DICTATION_MIN_WORDS = 40

# Real speech is disfluent; dictation engines emit clean prose. Any of these
# marks a line as spoken to the room, not typed by voice.
_DICTATION_FILLERS_RE = re.compile(
    r"\b(um+|uh+|erm+|hm+|y'?know|you know|i mean)\b[, ]", re.IGNORECASE)

# Instruction-prose markers: the spec-speak of someone telling a machine (or
# an absent reader) what to do. Two or more of these in one long fluent run
# is dictation, not conversation.
_DICTATION_INSTRUCT_RE = re.compile(
    r"\b(make sure|please|you should|you need to|i want you to|i need you to|"
    r"can you|could you|go ahead and|instead of|rather than|"
    r"it should|that should|this should|so that|"
    r"(?:add|change|update|fix|remove|create|write|use|rename|delete|keep)\s+"
    r"(?:a|an|the|that|this|it)\b)", re.IGNORECASE)


def looks_like_dictation(line: str) -> bool:
    """Deterministic pre-filter for the unmistakable case only. Anything it
    is unsure about returns False and is left to the model's classification —
    a False here never forces anything, it just declines to override."""
    text = (line or "").strip()
    if len(text.split()) < DICTATION_MIN_WORDS:
        return False
    if NAME.lower() in text.lower():
        return False          # she was addressed by name: not dictation
    if _DICTATION_FILLERS_RE.search(text):
        return False          # disfluent = spoken to the room
    return len(_DICTATION_INSTRUCT_RE.findall(text)) >= 2


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


def goal_tokens(text: str) -> set:
    """The meaningful words of a goal, normalized just enough that trivial
    morphology cannot defeat a match. "Earls" / "Earl's" / "earl" are one
    word; "book" / "booking" are one word. And NUMBERS ARE KEPT whatever
    their length — "for 4 people" vs "for 2 people" and "at 1" vs "at 7"
    are exactly the details a plan-card match must see, and the old
    len>3 filter silently deleted them: a card saying "2 people" could
    never be corrected by "all four of us", because the 4 and the 2 were
    both invisible.

    This is generic morphology, not scenario tuning: strip a possessive,
    strip -ing, strip a plural s. Nothing here knows any venue."""
    out = set()
    for w in re.findall(r"[a-z0-9']+", (text or "").lower()):
        w = w.replace("'", "")
        if w.isdigit():
            out.add(w)
            continue
        if len(w) <= 3:
            continue
        if len(w) > 5 and w.endswith("ing"):
            w = w[:-3]
        elif len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


# How long a conversation stays "live" — the window the split-thought carry
# and the addressee stickiness already use. People pause for seconds.
CONVERSATION_WINDOW = 120

# How long a PLAN under discussion stays open. Deliberately much longer than
# the sentence-to-sentence window above: a dinner gets talked into shape over
# whole minutes — greeting, catching up, "seven?", "where?", "the park one" —
# and the card minted by the first line must still be the card the last line
# improves. Safe to be generous, because reaching the open plan never merges
# by itself: _same_plan (words first, then meaning) still has to agree.
OPEN_PLAN_WINDOW = 600


# The browser as a TARGET is a navigational construction — "in my browser",
# "open Chrome", "pull it up in a new tab" — never the bare word. The first
# version matched the word anywhere, so "research the best Chrome extensions"
# and an overheard "my browser keeps crashing" rerouted server research into
# his actual Chrome.
_BROWSER_TARGET_RE = re.compile(
    r"\b(?:in|into|on|via|using|with|through)\s+(?:my\s+|the\s+|your\s+|a\s+)?"
    r"(?:web\s+)?(?:browser|chrome|safari|firefox|new\s+tab|browser\s+tab)\b"
    r"|\bopen\s+(?:my\s+|the\s+|a\s+)?(?:web\s+)?(?:browser|chrome|safari|firefox)\b",
    re.IGNORECASE,
)


def job_lane(goal: str, params: dict | None = None) -> str:
    """Choose the executor from intent, not merely the leading verb.

    Ordinary read-only work belongs on the server research arm. An explicit
    request to operate the owner's browser belongs on the browser arm even
    when the action itself is read-only (open, visit, show)."""
    g = (goal or "").strip()
    source = str((params or {}).get("source") or "")
    if _IRREVERSIBLE_RE.search(g):
        return ""
    if _BROWSER_TARGET_RE.search(f"{g} {source}"):
        return ""
    return "research" if _READ_ONLY_RE.search(g) else ""

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
  "the 9am with the dentist" beats "your appointment". Every concrete
  detail you state (a time, a place, a count) must come from THIS moment's
  goal or what was heard — repeat them exactly; NEVER invent or borrow one,
  not from an example, not from anywhere. A live text once said "7pm" about
  a 1pm booking; a wrong detail is worse than no text.
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
        # Who the owner was talking to on the last classified line. Sticky:
        # people don't switch addressee mid-breath, so the previous
        # classification rides along as context and the model needs positive
        # evidence to switch. Same recency window as the split-thought carry.
        self._last_addressee: Optional[tuple[str, float]] = None
        # The one plan this conversation is currently circling: (job id, ts).
        # A dinner gets agreed over five turns — "we should get dinner", "how
        # about seven", "Cactus Club", "the park one", "just the two of us" —
        # and each turn phrases the same intention differently enough that no
        # word-overlap rule can tie them together ("make a dinner reservation"
        # and "reserve a table at Cactus Club" share not one word). What ties
        # them together is that they are the same conversation. One plan under
        # discussion, one card on his desk, getting better as he talks.
        self._open_plan: Optional[tuple[str, float]] = None

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
             may_say=None, explicit: bool = False, channel: str = "",
             speaker: Optional[str] = None) -> dict:
        """One transcript line in; memory, decision, and delegation out.

        channel names where the line arrived from ("sms" when he texted it).
        It rides on the job so the answer can go back the way the question
        came: an SMS ask is replied to in-thread, everything else lands on
        the desk (the app feed) without buzzing his phone.

        speaker is the phone's LOCAL voice verdict for this line — "owner"
        (matched his enrolled voice profile), "other" (someone else's
        voice), or None/"unknown" (no verdict: too short, too noisy, old
        app build). It is evidence about WHO SPOKE, which wording alone can
        never supply: "I'll get into it" from his friend's mouth is the
        friend's promise; the identical words in his voice are his own.
        The honesty wall applies — no verdict changes NOTHING."""
        # The conversation, kept where the plan-matcher can see it: two goals
        # judged as bare strings ("book reservation at Earl's" vs "draft an
        # invitation for Saturday at 1") read as different errands; the same
        # two goals read WITH the lunch being planned around them are plainly
        # one plan. Refreshed every line, so it is always this conversation.
        self._last_convo = [c for c in (context or []) if c][-6:]
        # Unmistakable dictation is known before anything can answer or act:
        # a line the owner voice-typed at another machine must not be
        # answered from memory as if he had asked HER. Explicit lines (he
        # texted/typed them at her) are never dictation by definition.
        dictated = not explicit and looks_like_dictation(line)
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
        if not dictated and self._RECALL_RE.match(line) \
                and not self._IMPERATIVE_RE.match(line):
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
        # WHO is he talking to? The previous classification rides along
        # (people don't switch addressee mid-breath) and the deterministic
        # pre-filter above already marked unmistakable dictation.
        last_a = self._last_addressee
        prev_addressee = last_a[0] if last_a and time.time() - last_a[1] < 120 else None
        if speaker not in ("owner", "other"):
            speaker = None          # unknown and garbage are the same: no verdict
        decision = self._decide(line, mem, prev_line=prev_line, convo=context,
                                prev_addressee=prev_addressee, dictated=dictated,
                                speaker=speaker)
        # The EFFECTIVE addressee — the one her behaviour actually keys on,
        # written back so the event record shows what was applied. An
        # explicit line (he texted/typed it AT her) is assistant by
        # definition; unmistakable dictation is decided outside the model;
        # otherwise the model's classification stands. None (field missing
        # or invalid) fails open to the behaviour she had before this field
        # existed — a misbehaving model must not change her.
        if explicit:
            addressee = "assistant"
        elif dictated:
            addressee = "dictation"
        else:
            addressee = decision.addressee if decision.addressee in ADDRESSEES else None
        decision.addressee = addressee
        if addressee:
            self._last_addressee = (addressee, time.time())
        handled = None

        # The ambient lane (roadmap §7.1): speech not aimed at her — another
        # person, a dictation machine — is remembered, and researched quietly
        # when the work is read-only, but NEVER spawns a text or a
        # confirmation prompt. This is what was missing on 2026-08-04, when
        # messages he dictated to another AI came back as "On it" fires.
        # The outward decision is "ignore" — the one word the feed renders as
        # "Noted — nothing needed", which is the truth of this lane; the
        # addressee logged beside it says why, and any quiet job carries
        # lane=ambient so the whole story is auditable.
        if addressee in AMBIENT_ADDRESSEES and decision.decision in ("act", "ask"):
            goal = decision.goal
            consequential = bool(goal) and (decision.needs_confirmation
                                            or goal in IRREVERSIBLE
                                            or is_consequential(goal))
            # Read-only preparation ALWAYS starts quietly — even when triage
            # wanted a detail first ("plan the Vienna trip", dates unknown:
            # research both weeks; the FYI text delivers whatever is found).
            # She never interrupts his conversation to ask about prep work;
            # a question is only worth his attention when the unknown blocks
            # something consequential — and that path holds a card and asks
            # exactly once, below.
            quiet_research = bool(goal) and not consequential
            if quiet_research:
                # Free to do, lands on her desk — queued unheld, said nowhere.
                params = {"source": line, "now": now_line(), "lane": "ambient"}
                if decision.assumption:
                    params["assumption"] = decision.assumption
                job_id = self._queue_job(goal, params)
                self.loops.append(LoopRecord(
                    commitment_id=mem.get("commitment_id") or -1,
                    what=goal, status="handling", job_id=job_id))
                decision = Decision(
                    decision="ignore", goal=goal,
                    reason=f"{addressee}-directed: quiet research, saying nothing",
                    addressee=addressee)
            elif goal and consequential and addressee not in AUTHORED_ADDRESSEES \
                    and decision.decision in ("act", "ask"):
                # A real plan, made out loud with another human, that ends in
                # something irreversible — the dinner he just agreed to. This
                # is not chatter to be filed; it is the single thing Anticipy
                # exists to catch, and on 2026-08-04 it vanished: the whole
                # Cactus Club plan came back "Noted — nothing needed" because
                # the ambient lane refused all consequential work.
                #
                # The lane was answering the wrong question. "May she SPEAK
                # about this?" and "May she WORK on this?" are different, and
                # collapsing them turned "interrupt almost never" into "do
                # nothing". So: the work is prepared and HELD for his yes —
                # a card on her desk plus ONE text asking for the go-ahead and
                # naming any essential unknowns. Held work never sits silent.
                params = {"source": line, "now": now_line(), "lane": "desk"}
                if decision.assumption:
                    params["assumption"] = decision.assumption
                if decision.missing:
                    params["missing"] = decision.missing
                # He may have agreed to the same thing three times in one
                # conversation ("seven works" … "see you at seven"). One plan,
                # one card — but the dedupe belongs to _queue_job, which also
                # knows how to IMPROVE the card. A _same_pending shortcut here
                # used to swallow late details entirely: "all four of us" on
                # the last line matched the pending card and returned before
                # anything could patch "for 2 people" up to four.
                missing, assumption = decision.missing, decision.assumption
                # A firming-up plan merges into its existing card inside
                # _queue_job; only a genuinely NEW card earns the one text.
                before = {j.get("id") for j in self._pending_jobs()}
                job_id = self._queue_job(goal, params, hold=True)
                fresh = bool(job_id) and job_id not in before
                if fresh:
                    self.loops.append(LoopRecord(
                        commitment_id=mem.get("commitment_id") or -1,
                        what=goal, status="handling", job_id=job_id))
                decision = Decision(
                    decision="act" if fresh else "ignore", goal=goal,
                    reason=(f"{addressee}-directed: prepared, waiting on his OK"
                            if fresh else
                            f"{addressee}-directed: already on her desk"),
                    needs_confirmation=True, addressee=addressee)
                handled = None
                if fresh:
                    # Held work must never sit silently: one text asks for
                    # his go-ahead and names anything essential still
                    # unknown. The queue's dedupe keeps this to ONE per plan.
                    handled = self._voice({
                        "situation": "overheard a plan he made with someone; "
                                     "prepared it, held for his OK"
                                     + ("; essential details are missing"
                                        if missing else ""),
                        "heard": line, "goal": goal,
                        "missing": missing or None,
                        "assumption": assumption,
                    }) or (
                        f"Caught your plan — ready to go: {goal}. "
                        + (f"First I need: {', '.join(missing)}. "
                           if missing else "")
                        + "Say go and I'll book it."
                    )
                    # Kind "ambient_act": the worker's guard gives overheard-
                    # plan texts the clock's quiet hours — he never invited
                    # this one. And the text only counts if it actually SENT:
                    # a failed Twilio call used to leave `handled` truthy,
                    # the worker posted it as said, and the speak-once guard
                    # then suppressed every retry forever — a silent card
                    # wearing a "he was told" sticker.
                    if not (self._may_say(may_say, handled, goal,
                                          "ambient_act")
                            and self.notify_owner(handled)):
                        handled = None
            else:
                # Dictation he is AUTHORING (voice-typing, instructing another
                # AI) is content, not commitment — a booking inside it is a
                # sentence, not a plan, and acting on it is the 2026-08-04
                # "On it" bug. Likewise a question would interrupt him about
                # speech never aimed at her. Remembered; nothing queued.
                decision = Decision(
                    decision="ignore", goal=goal,
                    reason=f"{addressee}-directed: stays ambient",
                    addressee=addressee)
            acted = decision.decision == "act" or quiet_research
            self._prev = None if acted else (line, time.time())
            return {"memory": mem, "decision": decision,
                    "anticipy_says": handled}

        self._prev = None if decision.decision in ("act", "ask") else (line, time.time())

        # Sufficiency: starting work that is guaranteed to stall on an unknown
        # is worse than one good question. An "act" with essential unknowns
        # becomes that question — the generic behavior, never a special case.
        if decision.decision == "act" and decision.missing:
            decision = Decision(
                decision="ask", goal=decision.goal, reason=decision.reason,
                missing=decision.missing, assumption=decision.assumption,
                addressee=decision.addressee)

        if decision.decision == "act" and decision.goal:
            # The executor needs temporal ground truth: a job run today with
            # no "now" produced an OpenTable result dated a YEAR in the past.
            params = {"source": line, "now": now_line()}
            if channel:
                params["channel"] = channel
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
            # not diligence. Judged by what the queue ACTUALLY did (same
            # snapshot pattern as the ambient branch): _same_pending alone
            # missed merges made by _refines_pending and the open-plan carry,
            # and each miss was one more text about the same dinner.
            before_ids = {j.get("id") for j in self._pending_jobs()}
            job_id = self._queue_job(decision.goal, params, hold=held,
                                     explicit=explicit)
            repeat = not (bool(job_id) and job_id not in before_ids)
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
            #
            # `handled` survives when the guard or the repeat check said "no
            # unprompted text" — the SMS conversation layer passes a muted
            # guard on purpose and delivers these words in-thread itself. It
            # is dropped ONLY when a send was attempted and FAILED: a failed
            # Twilio call used to leave `handled` truthy, the worker posted
            # it as said, and the speak-once guard then suppressed every
            # retry forever — a silent card wearing a "he was told" sticker.
            if held and not repeat and self._may_say(may_say, handled,
                                                     decision.goal, "act"):
                if not self.notify_owner(handled):
                    handled = None
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
            # A question is an interruption, and interrupting is earned by
            # being ADDRESSED — he asked her, or typed at her. Thinking
            # aloud is not an invitation: one mumbled dinner plan once drew
            # THREE different "what night were you thinking?" texts in two
            # minutes, because each goalless self-talk ask dodged the
            # goal-keyed dedupe. Self-talk still gets her help — acts queue,
            # plans firm up through the open-plan carry — she just doesn't
            # tug his sleeve about it. (No classification at all keeps the
            # old texting behaviour: the honesty wall cuts both ways.)
            if decision.addressee == "self" and not explicit:
                print(f"self-talk question stays unasked: {handled!r}")
                handled = None
            elif self._may_say(may_say, handled, decision.goal, "ask"):
                self.notify_owner(handled)
            else:
                print(f"already asked him about {decision.goal!r} — staying quiet")

        return {
            "memory": mem,
            "decision": decision,
            "anticipy_says": handled,
        }

    def _decide(self, line: str, mem: dict, prev_line: Optional[str] = None,
                convo: Optional[list[str]] = None,
                prev_addressee: Optional[str] = None,
                dictated: bool = False,
                speaker: Optional[str] = None) -> Decision:
        if self.brain:
            context = self.memory.recall(line, limit=4)
            prompt = line
            # What was already said in THIS conversation. Without it a
            # question lands naked — "what time is the demo day Monday" with
            # no idea which demo day, which is exactly what happened live.
            if convo:
                earlier = " | ".join(c for c in convo[-16:] if c and c != line)
                if earlier:
                    prompt = f"{prompt}\n(Earlier in this conversation: {earlier})"
            # People think across pauses: "I'll send the Devon invoice" …
            # "tomorrow morning". The previous line rides along as background
            # so a split thought still triages as one thought.
            if prev_line:
                prompt = f"{prompt}\n(Previous line, background: {prev_line})"
            # Sticky addressee: who he was talking to a breath ago is who he
            # is talking to now, absent positive evidence of a switch.
            if prev_addressee:
                prompt = f"{prompt}\n(Addressee of the previous line: {prev_addressee})"
            if dictated:
                prompt = (f"{prompt}\n(Pre-check: this line reads as machine "
                          f"dictation — a long fluent run of instruction-prose.)")
            # The phone's LOCAL voice verdict — measured evidence, stronger
            # than anything wording can imply. It rides in as context the
            # model must weigh: "I'll get into it" in someone else's voice
            # is someone else's promise.
            if speaker == "owner":
                prompt = (f"{prompt}\n(Voice check: this line was spoken by "
                          f"the OWNER himself — his enrolled voice matched.)")
            elif speaker == "other":
                prompt = (f"{prompt}\n(Voice check: this line was spoken by "
                          f"someone who is NOT the owner — a different "
                          f"person's voice. Their commitments, promises and "
                          f"errands are THEIRS, never the owner's own; only "
                          f"things the owner would plainly want caught from "
                          f"another person's words deserve quiet work.)")
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
                # No transport is not a FAILED send — dev and test rigs run
                # without Twilio, and her feed voice must survive there. Only
                # an attempted send that errored returns None (below), which
                # is what tells hear() to drop `handled` so the record never
                # claims he was told.
                return {"skipped": "no transport"}
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
        # Is this the plan we are mid-conversation about? Consequential work
        # only: research is cheap, silent and additive, but a card asking him
        # to approve something must not breed. Words alone cannot see this —
        # "make a dinner reservation" and "reserve a table at Cactus Club"
        # share not one word — only the fact that he is still talking about
        # it, plus a meaning check that it IS the same plan and not a second
        # errand raised in the same breath.
        if is_consequential(goal, params, explicit=explicit):
            open_plan = self._open_plan
            if open_plan and time.time() - open_plan[1] < OPEN_PLAN_WINDOW:
                job_id = open_plan[0]
                # Only while it is still his to approve. Once he has said yes
                # and it is running, the next thing he says is a NEW errand.
                current = next((j for j in self._pending_jobs()
                                if j.get("id") == job_id), None)
                if current is None:
                    self._open_plan = None
                elif self._same_plan(goal, current.get("goal") or ""):
                    # The richer wording wins, whichever order they arrived
                    # in — a card must only ever get better.
                    if not self._covered_by(goal, current.get("goal") or ""):
                        try:
                            pb.patch(
                                f"{self.backend_url}/api/collections/jobs/records/{job_id}",
                                json={"goal": goal,
                                      "params": json.dumps(params)},
                                timeout=10)
                        except Exception:
                            pass
                    self._open_plan = (job_id, time.time())
                    return job_id

        existing = self._same_pending(goal)
        if existing:
            return existing
        # A plan is assembled over several turns, not stated once. "Book
        # dinner tomorrow" becomes "book dinner for 2 at Cactus Club park
        # location tomorrow at 7 PM" three sentences later — the SAME plan,
        # better known. Word overlap calls those different jobs (the vague one
        # is half the length), so his desk filled up with one card per turn of
        # the conversation. When the new goal contains the pending one, she
        # has simply learned more: improve that card in place.
        refined = self._refines_pending(goal)
        if refined:
            try:
                pb.patch(f"{self.backend_url}/api/collections/jobs/records/{refined}",
                         json={"goal": goal, "params": json.dumps(params)}, timeout=10)
            except Exception:
                pass
            return refined
        # Route read-only work to the worker's research arm (roadmap §6).
        # Without a Brave key the worker has no way to run it, so the job
        # keeps the browser lane rather than queueing for an executor that
        # does not exist — graceful fallback, never a dead queue.
        lane = job_lane(goal, params) if os.environ.get("BRAVE_API_KEY") else ""
        try:
            r = pb.post(
                f"{self.backend_url}/api/collections/jobs/records",
                json={"goal": goal, "params": json.dumps(params),
                      "status": "awaiting_confirm"
                      if (hold or goal in IRREVERSIBLE
                          or is_consequential(goal, params, explicit=explicit))
                      else "queued",
                      "device_id": "anticipy", "owner": self.owner_id,
                      "lane": lane},
                timeout=10,
            )
            r.raise_for_status()
            job_id = r.json().get("id")
            if job_id and r.json().get("status") == "awaiting_confirm":
                # From here until the conversation goes quiet, anything else
                # consequential he says is this same plan firming up.
                self._open_plan = (job_id, time.time())
            return job_id
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
        differently each time it hears it.

        Only ever within the same consequence class. LOOKING A THING UP IS NOT
        DOING IT: "research Cactus Club availability for 2 at 7pm tomorrow" and
        "book Cactus Club for 2 at 7pm tomorrow" share almost every word, so
        word overlap alone called them the same job — and the booking was
        silently dropped in favour of the lookup that was already queued. That
        is how, on 2026-08-04, a whole dinner plan came to nothing: she
        researched the restaurant, he said "book it", and _queue_job handed
        back the research job's id and created nothing. A job that changes his
        world can never be deduped against one that only reads."""
        want = goal_tokens(goal)
        if not want:
            return None
        want_consequential = is_consequential(goal)
        for j in self._pending_jobs():
            other = j.get("goal") or ""
            if is_consequential(other) != want_consequential:
                continue
            have = goal_tokens(other)
            if not have:
                continue
            overlap = len(want & have) / max(len(want), len(have))
            if overlap >= 0.7:
                return j["id"]
        return None

    @staticmethod
    def _covered_by(goal: str, other: str) -> bool:
        """Does `other` already say everything `goal` says? Then patching
        would only lose detail."""
        want = goal_tokens(goal)
        have = goal_tokens(other)
        return bool(want) and want <= have

    def _same_plan(self, new_goal: str, pending_goal: str) -> bool:
        """Same plan firming up, or a second errand in the same breath?

        This is a MEANING question — "make a dinner reservation" and "reserve
        a table for 2 at Cactus Club" are one plan with zero words in common,
        while "book dinner tomorrow" and "cancel the gym membership" share a
        conversation and must stay two cards — so the model answers it.

        But words decide FIRST, wherever words are enough, and no second
        opinion may override them — live runs watched the model call "make a
        dinner reservation" and "book dinner at Cactus Club at 7 PM" two
        different errands, and a second card appeared on his desk. Both
        containment (one goal's words all survive into the other: the
        definition of a plan gaining detail) and strong overlap of the
        smaller goal into the larger are deterministic merges. Only when the
        words genuinely cannot tell — the full rewording, "make a dinner
        reservation" vs "reserve a table at the park spot" — does the model
        answer, and with no model those stay two cards: a duplicate card is
        an annoyance, a swallowed errand is a loss."""
        want = goal_tokens(new_goal)
        have = goal_tokens(pending_goal)
        if not want or not have:
            return False
        if len(want & have) / min(len(want), len(have)) >= 0.5:
            return True
        if self.llm and getattr(self.llm, "live", False):
            try:
                # The conversation rides along. Judged as bare strings,
                # "book reservation at Earl's Brooklyn" and "draft an
                # invitation for Saturday at 1 PM at Earl's" read as two
                # errands; judged inside the lunch being planned line by
                # line, they are obviously one plan taking shape — and a
                # wrong "different" here is a second card and a second text.
                convo = getattr(self, "_last_convo", None) or []
                user = f"A: {pending_goal}\nB: {new_goal}"
                if convo:
                    user += ("\nThe conversation they both came from, in "
                             "order: " + " | ".join(convo))
                res = self.llm.chat(
                    "Two task descriptions from the SAME conversation, "
                    "minutes apart. They may be one real-world plan worded "
                    "differently — the later one usually richer as details "
                    "(time, place, who) arrive, and the wording may drift "
                    "(a booking phrased as a draft, an invitation, a "
                    "reservation) — or two genuinely different errands with "
                    "different real-world outcomes. Reply ONLY with "
                    'JSON: {"same": true} or {"same": false}.',
                    user)
                return bool(json.loads(_extract_json(res.text)).get("same"))
            except Exception:
                pass
        return False

    def _pending_jobs(self) -> list[dict]:
        """Everything still waiting — queued or held for his yes."""
        try:
            filt = 'status="awaiting_confirm" || status="queued"'
            if self.owner_id:
                filt = f'({filt}) && owner="{self.owner_id}"'
            r = pb.get(f"{self.backend_url}/api/collections/jobs/records",
                       params={"filter": filt, "perPage": 20, "sort": "-created"},
                       timeout=10)
            return r.json().get("items", []) if r.ok else []
        except Exception:
            return []

    def _refines_pending(self, goal: str) -> Optional[str]:
        """Is this a better-informed version of something already pending?

        Asymmetric on purpose. _same_pending asks "are these the same size and
        shape" — the right question for the same thing said twice. This asks
        "does the new goal CONTAIN the old one", which is what a plan being
        filled in actually looks like: every word of "book dinner reservation
        tomorrow" survives into "book dinner reservation for 2 at Cactus Club
        park location tomorrow at 7 PM", plus the details that make it doable.
        Only within one consequence class, and only when the newcomer is
        genuinely richer — otherwise a vague line arriving late would drag a
        good card backwards."""
        want = goal_tokens(goal)
        if not want:
            return None
        want_consequential = is_consequential(goal)
        for j in self._pending_jobs():
            other = j.get("goal") or ""
            if is_consequential(other) != want_consequential:
                continue
            have = goal_tokens(other)
            if not have or len(want) <= len(have):
                continue
            if len(want & have) / len(have) >= 0.8:
                return j["id"]
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
