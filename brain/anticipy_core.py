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
                           NOT_HIS, check_sufficiency, fill_gaps_from_memory,
                           owner_is_party, ends_in_the_world,
                           unsupported_names,
                           unsupported_counts, read_into_a_machine,
                           not_speech_evidence,
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


# ONE SIDE OF A CONVERSATION.
#
# On a call — AirPods, a handset, anything not on speaker — she hears only him.
# Half of what he says is agreeing with, or repeating back, a person she cannot
# hear. And a request he makes OF THEM looks exactly like a request he makes of
# her: "if you don't mind putting that word in" became the task "Remind Sakib
# about the word", when he was asking the man on the phone to put in a good
# word for him. The obligation was inverted and the sentence was mangled.
#
# The tell is back-channel: "yeah", "ok", "exactly", "of course", "right".
# Nobody talks that way to an assistant, or to themselves. It is what listening
# sounds like.
#
# Measured on his own logs — a real 19-minute investor call against the rest of
# the same day: 28% of lines in the call were almost entirely acknowledgement,
# against 4% outside it. Seven times the rate, with nothing in between.
_BACKCHANNEL = {
    "yeah", "yep", "yes", "ok", "okay", "right", "sure", "exactly", "mhm", "mm",
    "oh", "of", "course", "pardon", "got", "it", "i", "see", "no", "problem",
    "for", "totally", "nice", "wow", "hmm", "cool", "alright", "bye", "thank",
    "you", "thanks", "and", "then", "like", "so", "well", "um", "uh", "that", "s",
}
BACKCHANNEL_LINE = 0.8      # a line that is essentially pure acknowledgement
CONVERSATION_SHARE = 0.20   # how many of the recent lines must look like that
# NOT `CONVERSATION_WINDOW` — that name is already taken further down
# this file, by an unrelated 120-line context bound. Mine was silently
# overridden by it, so the detector read 120 lines instead of 10 and a
# call from an hour ago still marked everything after it as a call.
CALL_WINDOW_LINES = 10


def _is_backchannel(line: str) -> bool:
    words = re.findall(r"[a-z']+", (line or "").lower())
    if not words:
        return False
    hits = sum(1 for w in words if w in _BACKCHANNEL)
    return hits / len(words) >= BACKCHANNEL_LINE


def in_conversation(recent: Optional[list]) -> bool:
    """Is he mid-conversation with someone she cannot hear?

    Deliberately not "is a call in progress" — she has no way to know that
    today, and this covers the same ground from the speech itself: a person
    across a table whose voice the pendant misses reads identically to a
    person on the phone.
    """
    lines = [l for l in (recent or []) if l and l.strip()][-CALL_WINDOW_LINES:]
    if len(lines) < 4:
        return False               # too little to tell; claim nothing
    hits = sum(1 for l in lines if _is_backchannel(l))
    return hits / len(lines) >= CONVERSATION_SHARE


# A web address, an email address or a bare domain is a THING BEING NAMED, not
# somebody being spoken to. Stripped out before anything looks for her name.
_ADDRESSES_RE = re.compile(
    r"""\b(?:[a-z][a-z0-9+.-]*://\S+          # any scheme://…
        |[^\s@]+@[^\s@]+                      # an email address
        |[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+  # a bare domain, foo.ai / a.b.co
        )""",
    re.IGNORECASE | re.VERBOSE)


def addressed_by_name(line: str) -> bool:
    """Did he say HER NAME to her — as a name, not as part of some address?

    Her name is Anticipy. His company's site is anticipy.ai. A plain substring
    test therefore reported "she was addressed by name" for every sentence
    mentioning his own website, which switched the dictation filter OFF for
    exactly the lines it exists to catch.

    Seen live 2026-08-07. He dictated sixty-one words of instruction at Wispr
    Flow — "Please go on anticipY.ai … make sure the wording is correct … the
    job listing essentially" — and because the word anticipy appeared inside
    the domain, the filter stood down, triage read it as work, and a truncated
    follow-on fragment ("Tell people to contact omar@aNt") became a job to
    draft a public post. Delete the domain from that same sentence and the
    filter catches it correctly. One substring test, one bad afternoon.
    """
    text = _ADDRESSES_RE.sub(" ", line or "")
    return re.search(rf"\b{re.escape(NAME)}\b", text, re.IGNORECASE) is not None


def looks_like_dictation(line: str) -> bool:
    """Deterministic pre-filter for the unmistakable case only. Anything it
    is unsure about returns False and is left to the model's classification —
    a False here never forces anything, it just declines to override."""
    text = (line or "").strip()
    if len(text.split()) < DICTATION_MIN_WORDS:
        return False
    if addressed_by_name(text):
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
    strip -ing, strip a plural s. Nothing here knows any venue.

    Numbers count HOWEVER they were written: "7pm" carries the same 7 as
    "7 PM", and "two"/"seven" the same digit a transcriber might have typed.
    "book at 7pm" once read as covered by "book at 8" — both spellings were
    invisible — so a spoken correction never rewrote the card."""
    words = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
             "five": "5", "six": "6", "seven": "7", "eight": "8",
             "nine": "9", "ten": "10", "eleven": "11", "twelve": "12"}
    out = set()
    for w in re.findall(r"[a-z0-9']+", (text or "").lower()):
        w = w.replace("'", "")
        if w in words:
            out.add(words[w])
            continue
        if w.isdigit():
            out.add(w)
            continue
        # "7pm", "3x", "2nd": the digits are the detail worth matching on.
        m = re.match(r"^(\d+)[a-z]+$", w)
        if m:
            out.add(m.group(1))
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
goes out until they give the word. NEVER say or imply an action already
happened ("got you a table", "booked it", "sent it") when you are holding it
for their OK — you have a plan, not a result, and claiming a result that
doesn't exist is the one unforgivable text. If a detail is listed as missing,
your job is to ASK for it — never supply a value for it, however obvious it
seems from their habits.
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
        # Gaps memory answered for the goal being decided right now; consumed
        # into the job's params so the agent sees them as facts.
        self._memory_filled: dict = {}
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
        # (job id, when, the goal it was raised with). The GOAL is what makes
        # "is this the same plan?" answerable here, without a backend read.
        self._open_plan: Optional[tuple[str, float, str]] = None

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

    # Contentless approval — nothing in it but the yes. Anything carrying a
    # detail ("let's do Earls at 7") falls through to triage as before.
    _GO_AHEAD_RE = re.compile(
        r"^(ok(ay)?|yes|yeah|yep|sure|perfect|alright|cool|great)?[,!.\s]*"
        r"(let'?s do it|do it|go ahead|go for it|make it happen|i'?m in|"
        r"sounds good|let'?s go|book it|send it)[,!.\s]*$", re.IGNORECASE)

    def _release_freshest_held(self, line: str) -> Optional[str]:
        """Release the plan he was JUST asked about — and only that: the
        newest held card, and only while the asking is minutes old. A yes an
        hour later is about something else and stays with triage."""
        try:
            filt = 'status="awaiting_confirm"'
            if self.owner_id:
                filt += f' && owner="{self.owner_id}"'
            r = pb.get(f"{self.backend_url}/api/collections/jobs/records",
                       params={"filter": filt, "perPage": 1, "sort": "-created"},
                       timeout=10)
            items = r.json().get("items", []) if r.ok else []
            if not items:
                return None
            job = items[0]
            import datetime as _dt
            try:
                created = _dt.datetime.strptime(
                    (job.get("created") or "")[:19], "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=_dt.timezone.utc).timestamp()
            except Exception:
                created = time.time()
            if time.time() - created > 900:
                return None
            try:
                params = json.loads(job.get("params") or "{}")
            except Exception:
                params = {}
            params["authorized"] = True
            params["approved_scope"] = (
                f"Task: {job.get('goal', '')}. "
                f'They said: "{line.strip()}". '
                f"Heard originally: {params.get('source', '')}").strip()
            pr = pb.patch(
                f"{self.backend_url}/api/collections/jobs/records/{job['id']}",
                json={"status": "queued", "params": json.dumps(params)},
                timeout=10)
            return (job.get("goal") or None) if getattr(pr, "ok", False) else None
        except Exception:
            return None

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
            got = may_say(text, goal or "", kind)
            # "defer" is a third verdict and must survive the bool: NOT NOW
            # (quiet hours — the card is real, morning raises it) is not
            # NEVER (a dedupe refusal — the card must not exist).
            return got if got == "defer" else bool(got)
        except Exception as e:
            # A broken guard must never silence a genuine message.
            print(f"may_say check failed ({kind}): {e}")
            return True

    def hear(self, line: str, context: Optional[list[str]] = None,
             may_say=None, explicit: bool = False, channel: str = "",
             speaker: Optional[str] = None,
             link_candidates: Optional[list[str]] = None) -> dict:
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
        The honesty wall applies — no verdict changes NOTHING.

        link_candidates are recent lines, oldest first, shown to the model
        NUMBERED so it can say which one this line carries on from. The
        answer comes back on decision.continues as a 1-based index into this
        exact list (0 = starts something new, None = no usable answer). The
        caller owns the mapping back to ids, because only the caller knows
        them. Omitted — the default, and what every caller did before links
        existed — the question is never asked and no verdict is produced."""
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
        # Two filters, because they catch opposite shapes. looks_like_dictation
        # wants a LONG fluent run of instruction-prose (Wispr Flow into another
        # assistant). The three lines that became real jobs on 2026-08-04 were
        # the other shape entirely — short, garbled, number-dense fragments —
        # and it missed all three. read_into_a_machine only spends a model call
        # when the line carries mechanical evidence, so ordinary speech costs
        # nothing and never reaches it.
        dictated = not explicit and (looks_like_dictation(line)
                                     or read_into_a_machine(self.llm, line))
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
        # A bare spoken go-ahead ("Okay let's do it") names nothing on its
        # own — the "it" is the plan she just held and asked about. Triaging
        # it as a fresh line is how a contentless yes once minted a brand-new
        # goal out of injected context ("extract memory into compact JSON", a
        # leaked internal instruction, live 2026-08-11). His yes lands on the
        # freshly held plan; only when nothing is freshly held does the line
        # fall through to triage.
        if not dictated and speaker != "other" \
                and self._GO_AHEAD_RE.match(line.strip()):
            released = self._release_freshest_held(line)
            if released:
                self._prev = None
                for l in self.loops:
                    if l.what == released and l.status == "awaiting_ok":
                        l.status = "handling"
                return {"memory": mem, "decision": Decision(
                    decision="act", goal=released,
                    reason="his go-ahead — released the plan he was asked about",
                    addressee="assistant", owes="owner"),
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
        # The phone's verdict, in the roster's vocabulary: "owner",
        # "other" (a person it cannot place), or "other:<who>" where <who>
        # is a stable local voice id or a name he has taught it ("Sarah").
        # Anything else — "unknown", empty, a garbled value from a build we
        # have never seen — is NO VERDICT, and no verdict must change
        # nothing at all.
        speaker_name = None
        if speaker == "owner":
            pass
        elif isinstance(speaker, str) and speaker.startswith("other"):
            _, _, who = speaker.partition(":")
            who = who.strip()
            # A bare local id ("v2") names nobody; a real name does.
            if not who or not re.fullmatch(r"v\d+", who):
                # Bare "other" is the roster saying it is confident this is
                # not him. A NAME is that plus who. Both are evidence.
                speaker_name = who or None
                speaker = "other"
            else:
                # AN AUTO-GENERATED ID IS NOT A PERSON. "other:v215" means the
                # roster could not place this voice, so it filed a new one —
                # and failing to recognise a voice is not the same thing as
                # recognising a different one.
                #
                # Passed through as "other" it became strong evidence, because
                # the triage prompt rightly treats a first-person commitment
                # from someone who is NOT the owner as that person's promise.
                # So his own to-dos were being handed to a stranger. Both of
                # the "I have to email Priya" lines she ignored were tagged
                # other:v210 and other:v215.
                #
                # Measured on 200 real tagged lines: 195 distinct identities,
                # 97% of them seen exactly once, and the owner recognised
                # twice. He has never enrolled, so there is no voiceprint to
                # match against and every utterance becomes a new stranger. A
                # signal that wrong is worse than no signal, and no verdict is
                # the state the honesty wall was built for.
                speaker = None
        else:
            speaker = None
        decision = self._decide(line, mem, prev_line=prev_line, convo=context,
                                prev_addressee=prev_addressee, dictated=dictated,
                                speaker=speaker, speaker_name=speaker_name,
                                link_candidates=link_candidates,
                                mid_conversation=in_conversation(context))
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

        # THE SECOND KEY (2026-08-05). Triage saying "act" is one key; this
        # is the other, and both must turn. Whose job did these words create?
        # If nobody's — he was reading a list into his laptop, or venting, or
        # the transcript is mush — there is nothing to do, whatever the verbs
        # looked like. On 2026-08-04 one dictation about a newsletter list
        # became three real jobs ("remove items 491, 492, 493", "update the
        # KTHAI list", "reply to Toby's email") because the only question
        # being asked was "does this look actionable", and it did.
        #
        # An EXPLICIT line is exempt: if he typed it at her or texted her, he
        # is the one asking, and no second opinion overrides him.
        # No verdict at all (older model, unparseable reply) changes nothing:
        # the honesty wall, same as every other judgement she makes.
        # The price of being wrong is not the same in both directions, so the
        # bar is not either. Looking something up is silent, free and
        # reversible — being generous there costs him nothing. Booking,
        # sending, buying, or buzzing his phone costs him trust. So:
        #
        #   machine  -> silence, full stop. He is voice-typing; the machine
        #               in front of him is already doing it, and "helpfully"
        #               doing it again is the 2026-08-04 bug.
        #   nobody   -> no consequential work and no interruption, but a
        #               read-only lookup may still run quietly. "Let's go out
        #               tomorrow" carries no firm obligation yet, and going
        #               silent on it is how she went deaf last time.
        if (decision.owes in NOT_HIS and not explicit
                and decision.decision in ("act", "ask")):
            goal = decision.goal
            may_look = (decision.owes == "nobody" and decision.decision == "act"
                        and goal and not decision.missing
                        and not is_consequential(goal))
            if not may_look:
                reason = ("operating a machine by voice — it is already doing it"
                          if decision.owes == "machine"
                          else "no obligation to anyone")
                self._prev = (line, time.time())
                # goal="" is deliberate: ignore + a goal is the feed's
                # "Looking into it — I'll text you what I find" card, and
                # she is doing NOTHING here. A do-nothing verdict wearing
                # that label is a promise she never intends to keep — he
                # watched four of them in a row and reasonably concluded
                # every plan "gets stuck there".
                return {"memory": mem, "decision": Decision(
                    decision="ignore", goal="",
                    reason=f"not his to do: {reason} — {goal!r}",
                    addressee=addressee, owes=decision.owes),
                    "anticipy_says": None}
            params = {"source": line, "now": now_line(), "lane": "ambient"}
            job_id = self._queue_job(goal, params)
            self.loops.append(LoopRecord(
                commitment_id=mem.get("commitment_id") or -1,
                what=goal, status="handling", job_id=job_id))
            self._prev = None
            return {"memory": mem, "decision": Decision(
                decision="ignore", goal=goal,
                reason="no firm obligation yet — looking quietly, saying nothing",
                addressee=addressee, owes="nobody"),
                "anticipy_says": None}

        # Someone ELSE took it on. Remember it — he may want it tracked, and
        # a promise made to him is exactly the sort of loop that goes quiet —
        # but their word never becomes his errand.
        if (decision.owes == "other" and not explicit
                and decision.decision in ("act", "ask")):
            # "other" is right about WHO OWNS THE NEXT STEP and wrong about
            # whose plan it is: shown a dinner he plainly agreed to where the
            # friend said "I'll text you a time", triage filed the whole plan
            # under the friend, six for six, and she went inert on his own
            # dinner. Ask that one question on its own — is he a party to
            # this plan? — and only an explicit yes flips it back into his
            # lane. "Leave the flights with me" still stays theirs.
            if not owner_is_party(self.llm, line, decision.goal or ""):
                self._prev = (line, time.time())
                # goal="" for the same reason as above: she is tracking, not
                # looking, and the feed must not claim otherwise.
                return {"memory": mem, "decision": Decision(
                    decision="ignore", goal="",
                    reason="someone else took this on; remembered, not "
                           f"started: {decision.goal!r}",
                    addressee=addressee, owes="other"),
                    "anticipy_says": None}

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
            # A goal of pure whitespace is no goal at all — a blank card must
            # never be prepared, held, or texted about.
            goal = (decision.goal or "").strip() or None
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
            # The verb regex is a coin flip on sealed plans: the model words
            # the same committed dinner "book X" one run and "plan X" the
            # next, and "plan" reads as read-only — the whole thing went
            # quiet. When the WORDING says read-only, one isolated question
            # judges the SUBSTANCE: a plan that inherently ends in a
            # reservation, order or message is consequential whatever its
            # verb. Genuine research stays quiet, exactly as before.
            if goal and not consequential \
                    and ends_in_the_world(self.llm, line, goal):
                consequential = True
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
                # Triage's own "missing" field is empty essentially always
                # (measured; see the sufficiency comment below for the direct
                # lane). The ambient lane returned before that check ever ran,
                # so "dinner tomorrow, I don't know when though" arrived with
                # missing=[] — and the one text about it filled the gap from
                # habit and said 7 PM. Same gate, same reason, this lane too.
                if not explicit:
                    try:
                        for gap in check_sufficiency(self.llm, goal):
                            if gap not in decision.missing:
                                decision.missing.append(gap)
                    except Exception:
                        pass
                # Memory answers before he is asked: a gap his own history
                # settles (the location he always books, his home city)
                # becomes an assumption on the card he approves, not another
                # question in the one text.
                filled = {}
                if decision.missing:
                    try:
                        filled, decision.missing = fill_gaps_from_memory(
                            self.llm, self.memory, goal, decision.missing)
                    except Exception:
                        filled = {}
                if filled:
                    picked = "; ".join(f"{v}" for v in filled.values())
                    decision.assumption = (
                        (decision.assumption + " — " if decision.assumption
                         else "") + f"from what I know about you: {picked}")
                params = {"source": line, "now": now_line(), "lane": "desk"}
                for k, v in filled.items():
                    key = re.sub(r"\W+", " ", k).strip().lower()[:48]
                    if key:
                        params[key] = v
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
                    said = self._voice({
                        "situation": "overheard a plan he made with someone; "
                                     "prepared it but NOTHING IS BOOKED OR "
                                     "SENT YET — you are asking his go-ahead"
                                     + ("; essential details are missing — "
                                        "ask for them, never fill them in"
                                        if missing else ""),
                        "heard": line, "goal": goal,
                        "missing": missing or None,
                        "assumption": assumption,
                    })
                    # A number she never heard is an invention, whatever the
                    # prompt says — a live text once announced "Monday at
                    # 7 p.m." for a dinner whose time he explicitly did not
                    # know. Any digit in her text must have been spoken or be
                    # part of the plan; otherwise the plain fallback speaks.
                    if said:
                        allowed = goal_tokens(
                            f"{line} {goal} {assumption or ''} "
                            + " ".join(missing or []))
                        nums = {t for t in goal_tokens(said) if t.isdigit()}
                        if nums - {t for t in allowed if t.isdigit()}:
                            said = None
                    handled = said or (
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
                    # NOT ALLOWED TO SPEAK and TRIED AND FAILED TO SPEAK are
                    # different things and must not share a branch. A refused
                    # guard means he will never hear about this card, so it
                    # must not exist. A failed Twilio call means the card is
                    # real and simply undelivered — cancelling it would destroy
                    # genuine work over a network blip.
                    verdict = self._may_say(may_say, handled, goal,
                                            "ambient_act")
                    if verdict == "defer":
                        # Quiet hours. He planned something at midnight; the
                        # plan is real and so is the card — it simply waits
                        # for a civilised hour. Cancelling here would make
                        # every plan made late at night silently vanish.
                        handled = None
                        decision = Decision(
                            decision="act", goal=goal,
                            reason=(f"{addressee}-directed: held quietly "
                                    "overnight; raised in the morning"),
                            needs_confirmation=True, addressee=addressee)
                    elif not verdict:
                        handled = None
                        # SILENCE MUST MEAN STILLNESS.
                        #
                        # 2026-08-07, live, and the worst failure of the day.
                        # He told Priya "I'll send it to your email". This lane
                        # built the card and held it — correct. Then the
                        # anti-nag guard refused the text ("already put this to
                        # him twice with no answer") and the card stayed on his
                        # desk. He approved something nobody had ever told him
                        # about, and it opened Gmail.
                        #
                        # The comment eight lines up says it outright: "Held
                        # work never sits silent." It did. The job is queued
                        # BEFORE the speech is decided, so every guard in this
                        # file silences her mouth and none of them stop her
                        # hands — which makes the worst outcome the default.
                        #
                        # `fresh` is what makes this safe: a plan firming up
                        # merges into its existing card and never reaches here,
                        # so the card he IS waiting on is never touched. Only a
                        # brand-new card that he was never told about dies.
                        print(f"not allowed to raise {goal!r} — cancelling the "
                              "card rather than leaving one he never heard of")
                        self._cancel_job(job_id, "she was not allowed to raise "
                                                 "this, so it was never his to "
                                                 "approve")
                        for l in self.loops:
                            if getattr(l, "job_id", None) == job_id:
                                l.status = "cancelled"
                        decision = Decision(
                            decision="ignore", goal="",
                            reason=(f"{addressee}-directed: could not raise "
                                    f"{goal!r}, so it was cancelled rather "
                                    "than left waiting on him"),
                            addressee=addressee)
                    elif not self.notify_owner(handled):
                        # Allowed, attempted, and the send failed. The card is
                        # real and he simply has not been told yet — leave it
                        # standing so a retry can reach him. `handled` is
                        # dropped so nothing records it as said: a failed
                        # Twilio call used to leave it truthy, the worker
                        # posted it as said, and the speak-once guard then
                        # suppressed every retry forever.
                        handled = None
            else:
                # Dictation he is AUTHORING (voice-typing, instructing another
                # AI) is content, not commitment — a booking inside it is a
                # sentence, not a plan, and acting on it is the 2026-08-04
                # "On it" bug. Likewise a question would interrupt him about
                # speech never aimed at her. Remembered; nothing queued.
                # goal="" — nothing is queued here, and ignore + a goal is
                # the feed's "Looking into it" card. Only actual quiet work
                # gets to say so.
                decision = Decision(
                    decision="ignore", goal="",
                    reason=f"{addressee}-directed: stays ambient — {goal!r}",
                    addressee=addressee)
            acted = decision.decision == "act" or quiet_research
            self._prev = None if acted else (line, time.time())
            return {"memory": mem, "decision": decision,
                    "anticipy_says": handled}

        self._prev = None if decision.decision in ("act", "ask") else (line, time.time())

        # Sufficiency: starting work that is guaranteed to stall on an unknown
        # is worse than one good question. An "act" with essential unknowns
        # becomes that question — the generic behavior, never a special case.
        # Triage's own "missing" field is empty essentially always — measured
        # on his real failures, four for four. Ask the question on its own,
        # where the same model gets it right, and only for work about to be
        # started. Anything it returns joins missing and falls into the gate
        # immediately below, which already knows what to do with it.
        # NOT when this plan is already on his desk. The live dinner proof
        # caught this immediately: the plan was raised, he then said "can you
        # book dinner for 7pm tomorrow", and a fresh sufficiency question
        # ("which Cactus Club Park location?") went out as a SECOND text about
        # one dinner. Whatever is underspecified about a plan she has already
        # spoken to him about, a second question is not how it gets fixed —
        # one plan, one voice. The dedupe that knows this runs later, so the
        # check has to consult it here rather than assume it will be reached.
        # ONLY when the pending thing is THIS goal. The first cut of this
        # guard also skipped whenever ANY plan happened to be open
        # (`self._open_plan`), which is not evidence about the goal in hand at
        # all — and it cost him immediately. "Email Priya about the invoice"
        # sailed straight past the check while an unrelated email job sat
        # pending, so she never asked who Priya was, opened Gmail, typed the
        # word "Priya" into the address field and pressed send. Both remaining
        # tests are goal-specific and answer a question about THIS work; a bare
        # open plan answers a question about some other work.
        already = None
        if decision.decision == "act" and decision.goal:
            try:
                already = (self._same_pending(decision.goal)
                           or self._refines_pending(decision.goal))
                # And the plan she is already holding, IF it is this plan. The
                # first cut skipped on any open plan at all, which let the
                # Priya email past unasked. Deleting the check outright then
                # broke the other direction: every refining line of one dinner
                # ("Brooklyn one", "Saturday at one", "us four") re-ran the
                # sufficiency check and came back as a fresh question, so the
                # plan never became a card. Same plan, skip; different plan,
                # ask.
                if not already and self._open_plan:
                    open_goal = self._open_plan[2] if len(self._open_plan) > 2 else ""
                    if open_goal and self._same_plan(decision.goal, open_goal):
                        already = self._open_plan[0]
            except Exception:
                already = None
        if decision.decision == "act" and decision.goal and not explicit and not already:
            try:
                gap = check_sufficiency(self.llm, decision.goal)
            except Exception:
                gap = []
            # A name she never heard is not a detail, it is an invention, and
            # acting on it books the wrong restaurant in the wrong city. Folded
            # into the same gate: it becomes a question instead of a booking.
            try:
                heard_bits = (decision.goal and [line, " ".join(context or []),
                                                 prev_line or ""]) or []
                made_up = (unsupported_names(decision.goal, *heard_bits)
                           + unsupported_counts(decision.goal, *heard_bits))
            except Exception:
                made_up = []
            if made_up:
                gap = list(gap) + [
                    n if n.startswith("how many")
                    else f"which {n} you meant — I do not think you actually said that"
                    for n in made_up]
            # Memory before questions, this lane too — but never for a
            # made-up detail: an invented name must be ASKED about, not
            # quietly ratified by a memory lookup.
            if gap and not made_up:
                try:
                    filled, gap = fill_gaps_from_memory(
                        self.llm, self.memory, decision.goal, gap)
                except Exception:
                    filled = {}
                if filled:
                    picked = "; ".join(filled.values())
                    decision = Decision(
                        decision=decision.decision, goal=decision.goal,
                        reason=decision.reason, missing=decision.missing,
                        assumption=((decision.assumption + " — "
                                     if decision.assumption else "")
                                    + f"from what I know about you: {picked}"),
                        addressee=decision.addressee, owes=decision.owes,
                        continues=decision.continues)
                    self._memory_filled = dict(filled)
            if gap:
                decision = Decision(
                    decision=decision.decision, goal=decision.goal,
                    reason=decision.reason,
                    missing=list(decision.missing or []) + gap,
                    assumption=decision.assumption, addressee=decision.addressee,
                    owes=decision.owes, continues=decision.continues)

        if decision.decision == "act" and decision.missing:
            decision = Decision(
                decision="ask", goal=decision.goal, reason=decision.reason,
                missing=decision.missing, assumption=decision.assumption,
                addressee=decision.addressee, owes=decision.owes,
                continues=decision.continues)

        if decision.decision == "act" and decision.goal:
            # The executor needs temporal ground truth: a job run today with
            # no "now" produced an OpenTable result dated a YEAR in the past.
            params = {"source": line, "now": now_line()}
            if channel:
                params["channel"] = channel
            for k, v in (getattr(self, "_memory_filled", None) or {}).items():
                key = re.sub(r"\W+", " ", k).strip().lower()[:48]
                if key:
                    params[key] = v
            self._memory_filled = {}
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
            elif held and repeat:
                print(f"already waiting on him for {decision.goal!r} — not asking twice")
            elif held and not explicit:
                # SILENCE MUST MEAN STILLNESS.
                #
                # 2026-08-07, live. He told Priya "I'll send it to your email".
                # A job was built and HELD for his approval — correct. Then the
                # anti-nag guard refused the text ("already put this to him
                # twice with no answer"), and the card stayed on his desk
                # anyway. He approved something nobody had ever told him about,
                # and it opened Gmail.
                #
                # Every guard here silences her MOUTH. None of them stopped her
                # HANDS, because the job is queued before the speech is decided.
                # That makes the worst outcome the default one: she does
                # something real and says nothing.
                #
                # So a held card she is not allowed to speak about does not get
                # to exist. Not deleted — cancelled, with the reason on it, so
                # the record still says what happened.
                #
                # `explicit` is the exception and must stay: when he TEXTS her,
                # conversation.py deliberately passes a muted guard
                # (may_say=quiet, explicit=True) because it delivers her words
                # itself, in-thread. Cancelling there would break the SMS lane
                # outright.
                print(f"not allowed to raise {decision.goal!r} — cancelling the "
                      "card rather than leaving one he was never told about")
                self._cancel_job(job_id, "she was not allowed to raise this, "
                                         "so it was never his to approve")
                for l in self.loops:
                    if getattr(l, "job_id", None) == job_id:
                        l.status = "cancelled"
                handled = None
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
            # TRIED AND REVERTED, 2026-08-07 — do not narrow this to goalless
            # asks. The reasoning looked airtight: the incident above was about
            # GOALLESS asks dodging the goal-keyed dedupe, so with a goal
            # present _may_say should stop the repeats. It does not. Each turn
            # of one dinner produces a slightly DIFFERENT goal — "Book dinner
            # reservation for tomorrow at 7 PM", then "...for 2 tomorrow at
            # 7 PM" — and the dedupe reads those as separate errands.
            #
            # Measured on the live model the moment it was tried:
            #   dinner_demo_proof      FAIL 3/3 — FOUR texts for one dinner
            #   second_scenario_proof  FAIL 2/3 — SIX texts, and no held booking
            #
            # This guard is load-bearing. The real complaint it looks
            # responsible for — a card headed "Quick question for you" with no
            # question under it — is the CARD lying about a silence that was
            # correct, and belongs in ConversationCard.swift, not here.
            if decision.addressee == "self" and not explicit:
                print(f"self-talk question stays unasked: {handled!r}")
                handled = None
            elif self._may_say(may_say, handled, decision.goal, "ask"):
                self.notify_owner(handled)
            else:
                print(f"already asked him about {decision.goal!r} — staying quiet")
            # A question with no card behind it is a plan that evaporates:
            # "which saturday?" got its answer, the answer got a warm reply,
            # and nothing existed for the answer to land on (live 2026-08-11).
            # The asked-about plan is held — the answer amends it, his
            # go-ahead releases it, and "forget it" kills it.
            if handled and decision.goal:
                params = {"source": line, "now": now_line()}
                if channel:
                    params["channel"] = channel
                if decision.missing:
                    params["missing"] = ", ".join(
                        str(m) for m in decision.missing)
                if decision.assumption:
                    params["assumption"] = decision.assumption
                job_id = self._queue_job(decision.goal, params, hold=True,
                                         explicit=explicit)
                if job_id:
                    self.loops.append(LoopRecord(
                        commitment_id=mem.get("commitment_id") or -1,
                        what=decision.goal, status="awaiting_ok",
                        job_id=job_id))

        return {
            "memory": mem,
            "decision": decision,
            "anticipy_says": handled,
        }

    def _decide(self, line: str, mem: dict, prev_line: Optional[str] = None,
                convo: Optional[list[str]] = None,
                prev_addressee: Optional[str] = None,
                dictated: bool = False,
                speaker: Optional[str] = None,
                speaker_name: Optional[str] = None,
                link_candidates: Optional[list[str]] = None,
                mid_conversation: bool = False) -> Decision:
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
            # MEASURED, not guessed: a fifth or more of his recent lines were
            # pure acknowledgement, which is what listening sounds like. He is
            # talking WITH someone whose side never reached the microphone.
            if mid_conversation:
                prompt = (f"{prompt}\n(Pre-check: he is mid-conversation with "
                          f"someone whose side you CANNOT hear — a fifth of his "
                          f"recent lines are pure acknowledgement. So \"you\" in "
                          f"his words almost certainly means THAT PERSON, not "
                          f"you; a request he makes is a request OF THEM, and "
                          f"the obligation is theirs. He may also be repeating "
                          f"back what they just said, which is not his intent. "
                          f"Only take on what he plainly commits HIMSELF to.)")
            # The phone's LOCAL voice verdict — measured evidence, stronger
            # than anything wording can imply. It rides in as context the
            # model must weigh: "I'll get into it" in someone else's voice
            # is someone else's promise.
            if speaker == "owner":
                prompt = (f"{prompt}\n(Voice check: this line was spoken by "
                          f"the OWNER himself — his enrolled voice matched.)")
            elif speaker == "other":
                who = (f"{speaker_name} — a person he knows, not him"
                       if speaker_name else
                       "someone who is NOT the owner — a different person's "
                       "voice")
                prompt = (f"{prompt}\n(Voice check: this line was spoken by "
                          f"{who}. Their commitments, promises and errands "
                          f"are THEIRS, never the owner's own; only things "
                          f"the owner would plainly want caught from another "
                          f"person's words deserve quiet work"
                          + (f". When it matters who said it, say "
                             f"{speaker_name} by name." if speaker_name else "")
                          + ".)")
            if context:
                # Memory holds what people SAID, and models will happily store
                # a stray instruction as a fact. Injected back here, one such
                # note became the referent of a bare "let's do it" and a goal
                # of its own. Prose only — anything shaped like an instruction
                # or a schema stays out of the model's view.
                notes = "; ".join(
                    f["fact"] for f in context
                    if not re.search(r"reply only|compact json|[{}]",
                                     f.get("fact") or "", re.IGNORECASE))
                if notes:
                    prompt = f"{prompt}\n(Related memory: {notes})"
            # The link question. Recent lines numbered so the model can point
            # at ONE of them, which is how every disentanglement benchmark
            # since 2019 poses it — an index, never a free-text id, so a
            # hallucinated answer is out of range and therefore discarded
            # rather than followed.
            #
            # NOTHING IS FILTERED OUT HERE, deliberately. The returned index
            # is 1-based into the caller's list exactly as given, and the
            # caller maps it back to a record id. Dropping a blank candidate
            # at this layer would shift every number after it and silently
            # link lines to the wrong parent — a bug with no symptom. The
            # caller owns removing blanks, from the same place it takes ids,
            # so texts and ids cannot drift apart.
            numbered = list(link_candidates or [])
            if numbered:
                shown = "\n".join(f"[{n}] {(c or '').strip()}"
                                  for n, c in enumerate(numbered, 1))
                prompt = (f"{prompt}\n(Recent lines, oldest first — say in "
                          f"\"continues\" which ONE this line carries on "
                          f"from, or 0 if it starts something new:\n{shown})")
                return self.brain.triage(prompt, candidates=len(numbered))
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
            # Ends on the question. The old wording tacked on "Nothing goes out
            # until you say so" — which Omar read, correctly, as a release note
            # rather than something a person says. Asking IS the promise.
            return f"Got this ready: {pretty}. Want me to go ahead?"
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

    def _cancel_job(self, job_id, why: str) -> bool:
        """Take a card off his desk that he was never told about.

        Cancelled, never deleted: the row stays, carrying the reason, so the
        record still says what happened. "cancelled" is the status the
        extension already uses when a run is stopped from Chrome, and the app
        only renders awaiting_confirm/needs_user as cards — so this removes it
        from his desk without inventing new vocabulary.

        Never raises. A cancel that fails must not take hearing down with it;
        the worst case is the behaviour that existed before this.
        """
        if not job_id:
            return False
        try:
            pb.patch(f"{self.backend_url}/api/collections/jobs/records/{job_id}",
                     json={"status": "cancelled", "result": why}, timeout=10)
            return True
        except Exception as e:
            print(f"could not cancel {job_id}: {e}")
            return False

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
        if self._RETRACT_RE.match(goal or ""):
            retracted = self._retract_pending(goal)
            # An overheard "scratch that" ends here either way. If she held
            # the plan, it is now cancelled; if she never held it, there is
            # nothing in the world she could safely cancel from a half-heard
            # remark — a card reading "cancel the gym" with no gym anywhere
            # is nonsense work. Only a direct, explicit ask ("cancel my
            # Comcast subscription") that names something she is NOT already
            # holding earns a real cancellation errand.
            if retracted:
                return None
            if not explicit and self._retracting_mere_talk(goal):
                return None
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
                        self._merge_into(job_id, current, goal, params)
                    self._open_plan = (job_id, time.time(), goal)
                    return job_id

        existing = self._same_pending(goal)
        if existing:
            # Same card — but a correction ("make it 7 not 8") arrives as the
            # same plan with a changed detail, and returning without writing
            # would keep the stale card. Patch unless the pending wording
            # already says everything this one does.
            try:
                current = next((j for j in self._pending_jobs()
                                if j.get("id") == existing), None)
                if current and not self._covered_by(
                        goal, current.get("goal") or ""):
                    self._merge_into(existing, current, goal, params)
            except Exception:
                pass
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
            current = next((j for j in self._pending_jobs()
                            if j.get("id") == refined), None)
            if current:
                self._merge_into(refined, current, goal, params)
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
                self._open_plan = (job_id, time.time(), goal)
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

    def _merge_into(self, job_id: str, current: dict, goal: str,
                    params: dict) -> None:
        """A re-mention may ADD to a card; it must never bleach one out.

        Live, 2026-08-09: "Book a table for 2 at Earls in West Vancouver for
        tomorrow evening" was a held card; he then said "I'll get that booked
        now", triaged as "Confirm Earls West Van tomorrow at 7 PM" — same
        plan, so the merge fired, and the old REPLACE-the-goal merge wrote
        that meta-wording over the card. The booking verb, the party size and
        the venue details were gone; the browser agent read "Confirm …" as
        "send a confirmation" and opened GMAIL.

        A correction is different: "7 PM not 8 PM" arrives with the same
        shape and ONE detail swapped, and there the new wording must win —
        keeping the 8 was a live bug of its own. What tells the two apart is
        how much of the card the new wording would erase: a correction
        preserves nearly everything, a meta-rewording bleaches most of it.
        Either way the ORIGINAL conversation is kept — the new params'
        source ("booked now") is a fragment, not a replacement for what was
        actually heard."""
        try:
            cur_params = json.loads(current.get("params") or "{}")
        except Exception:
            cur_params = {}
        cur_goal = current.get("goal") or ""
        cur_src = (cur_params.get("source") or "").strip()
        new_src = (params.get("source") or "").strip()
        merged = dict(cur_params, **params)
        if cur_src and new_src and new_src not in cur_src:
            merged["source"] = f"{cur_src} … then: {new_src}"
        elif cur_src:
            merged["source"] = cur_src
        fields = {}
        have = goal_tokens(cur_goal)
        want = goal_tokens(goal)
        erased = have - want
        gained = want - have
        ratio = len(erased) / len(have) if have else 0
        # Counting only what a re-mention ERASES asks half the question, and
        # the missing half is the one that decides a real conversation.
        #
        # Measured on his own 2026-08-04 dinner: the card read "Confirm dinner
        # reservation for 2 people tomorrow at 7 PM" and he then named the
        # place — "Book dinner for 2 at Cactus Club Park location tomorrow at
        # 7 PM". That drops three near-synonyms (confirm, reservation, people)
        # and ADDS the venue, which is the single fact a booking cannot be
        # carried out without. Three of seven is 0.43, over the third, so the
        # better goal was refused and the card kept its venue-less wording:
        # she then texted him "what restaurant?" about a restaurant he had
        # just said out loud, and any browser run released from that card
        # would go looking for a venue nobody had told it.
        #
        # So weigh both sides. A wording that brings more than it takes is an
        # enrichment and must land. The bleaching this guard exists to stop
        # looks the opposite way round — "Confirm Earls West Van tomorrow at
        # 7 PM" over "Book a table for 2 at Earls in West Vancouver for
        # tomorrow evening" erases five and adds two — and is still refused.
        if ratio <= 1 / 3 or len(gained) > len(erased):
            fields["goal"] = goal          # richer or corrected: new wins
        else:
            merged["update"] = goal        # both hold detail: lose neither
            if merged.get("source"):
                merged["source"] += f" (update: {goal})"
        fields["params"] = json.dumps(merged)
        try:
            pb.patch(f"{self.backend_url}/api/collections/jobs/records/{job_id}",
                     json=fields, timeout=10)
        except Exception:
            pass

    @staticmethod
    def _covered_by(goal: str, other: str) -> bool:
        """Does `other` already say everything `goal` says? Then patching
        would only lose detail."""
        want = goal_tokens(goal)
        have = goal_tokens(other)
        return bool(want) and want <= have

    # "cancel …", "call off …" — a retraction names the thing it is
    # retracting. The verb list is deliberately tiny and unambiguous:
    # these words have no other meaning at the head of a goal.
    _RETRACT_RE = re.compile(
        r"^\s*(?:cancel|call\s+off|scrap|drop|abandon|un-?do)\b[\s:,-]*(.+)",
        re.IGNORECASE)

    def _retract_pending(self, goal: str) -> bool:
        """He scratched a plan SHE is still holding — take it off his desk.

        "Actually scratch the gym" used to mint a brand-new 'cancel gym'
        card while the original gym card (and the research it spawned) sat
        there untouched: three jobs about a plan that no longer exists.
        A cancellation of work that is still only hers — queued or waiting
        on his yes, nothing booked in the world yet — is not a new errand;
        it is the death of an old one. Anything already RUNNING, or a
        cancellation of something real out in the world ("cancel my Comcast
        subscription"), matches no pending job and flows through untouched.
        Returns True when at least one pending job was retracted."""
        m = self._RETRACT_RE.match(goal or "")
        if not m:
            return False
        what = m.group(1).strip()
        want = goal_tokens(what)
        if not want:
            return False
        hit = False
        try:
            for j in self._pending_jobs():
                other = j.get("goal") or ""
                have = goal_tokens(other)
                if not have:
                    continue
                overlap = len(want & have) / min(len(want), len(have))
                if overlap >= 0.5 or self._same_plan(what, other):
                    if self._cancel_job(j.get("id"),
                                        "he called this off out loud"):
                        hit = True
                        # The promise behind the job dies with it, or the
                        # clock later chases a plan he already called off.
                        try:
                            self.memory.close_matching(other, "cancelled")
                        except Exception:
                            pass
                        if self._open_plan and self._open_plan[0] == j.get("id"):
                            self._open_plan = None
        except Exception:
            pass
        return hit

    def _retracting_mere_talk(self, goal: str) -> bool:
        """Is this cancellation aimed at TALK — a plan that only ever existed
        in the conversation she just heard — or at something standing in the
        world (a membership, a subscription, a real booking)?

        Calling off talk is a no-op: she holds nothing about it and there is
        nothing out in the world either, so a card would be nonsense work.
        Cancelling a standing arrangement is a genuine errand. The words
        cannot tell these apart, so the model answers with the conversation
        in view; with no model, the errand survives — a useless card is an
        annoyance, a swallowed real cancellation is a loss."""
        if not (self.llm and getattr(self.llm, "live", False)):
            return False
        try:
            convo = getattr(self, "_last_convo", None) or []
            user = f"Task: {goal}"
            if convo:
                user += "\nThe conversation it came from: " + " | ".join(convo)
            res = self.llm.chat(
                "Someone's assistant heard them call something off. Decide "
                "what the cancellation is aimed at. \"talk\": a casual plan "
                "or idea that only existed in this conversation — nothing "
                "was ever booked, bought, or arranged in the world, so there "
                "is nothing to cancel. \"world\": a standing real-world "
                "arrangement — a membership, subscription, reservation, "
                "appointment, order — that exists outside this conversation "
                "and needs a real cancellation. Reply ONLY with JSON: "
                '{"aimed_at": "talk"} or {"aimed_at": "world"}.',
                user)
            return json.loads(_extract_json(res.text)).get("aimed_at") == "talk"
        except Exception:
            return False

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
                        if loop.commitment_id > 0:
                            self.memory.resolve(loop.commitment_id,
                                                "cancelled")
                except Exception:
                    pass
            out.append({"what": loop.what, "status": loop.status, "job": loop.job_id})
        return out
