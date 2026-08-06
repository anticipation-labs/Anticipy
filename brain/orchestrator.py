"""Anticipy orchestration brain.

Takes a line of transcript, decides ignore / act / ask, and for 'act'
produces a concrete browser goal. When it acts it runs the task FIRST,
then asks the user to confirm anything irreversible (send/book/pay).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Optional

from .llm import LLM

TRIAGE_SYSTEM = """You are Anticipy, a live-in chief of staff who hears the owner's day
through a pendant microphone and acts WITHOUT being asked — that is the whole
point of your existence. A separate confirmation gate holds anything
irreversible until the owner approves it, so err toward starting work.

For each transcript line, reason the way a great human assistant standing in
the room would: what just happened, and does the OWNER now have an intention,
need, plan, or commitment that competent help could advance? Judge by MEANING
only — there is no magic phrasing, no keyword, no required verb. People speak
sideways: a plan can arrive as a mumble, an agreement, a half-thought — and a
plan can be SEALED in three words: a terse confirmation of something already
discussed ("seven works", a "see you Tuesday" in any language) is the owner
committing, exactly as much as a full sentence would be.

- "act": you can see concrete work worth starting now — preparing, drafting,
  researching options, laying booking groundwork. A vague desire with a real
  anchor (a time, a place, a person) deserves a quiet start on options, not
  silence. Give a short machine goal string.
  When the context shows a plan ALREADY under discussion, a short line that
  adds or changes one of its details — the time, the place, the day, HOW
  MANY people ("it'll be us four", "make it eight instead") — is that plan
  firming up, not chatter: decision "act", and the goal restates the FULL
  plan carrying every detail known so far, the new one included. A detail
  that never makes it into a goal is a detail lost.
  This INCLUDES a factual question the owner says out loud that you could
  answer by looking it up — "what time is the demo day on Monday", "how late
  is that place open", "what did that cost". Looking something up is
  read-only and costs them nothing, so a question with a findable answer is
  work worth doing, not chatter. Make the goal a research goal naming the
  specific thing, and carry every detail they gave (the event, the day).
- "ask": help is clearly wanted but one missing detail blocks starting — the
  single question you'd lean over and ask.
- "ignore": a great assistant stays quiet: chatter, venting, jokes, questions
  aimed at other people, facts merely mentioned, and commitments that belong
  to someone else. Everything is remembered regardless; ignore only means no
  task right now.

Separately from the decision, answer WHO the owner is talking to right now
— "addressee". The pendant hears everything, so a lot of what reaches you
was never aimed at you:
- "assistant": talking to YOU — named you, or spoke a request or question
  the assistant in the room is plainly meant to pick up.
- "person": talking with another human — conversational turns, someone
  there to answer back, plans made together.
- "dictation": dictating to a machine — long fluent runs of instruction-like
  prose with no interlocutor, e.g. voice-typing a message or instructing
  another AI. Nobody speaks paragraphs of clean spec at a person.
- "self": mumbling, thinking aloud, half-thoughts with no audience.
People do not switch addressee mid-breath: when "(Addressee of the previous
line: ...)" is given, keep that classification unless THIS line itself gives
positive evidence of a switch. Classify honestly and still triage the content
on its merits — a plan heard in a person-to-person conversation can deserve
quiet research; whether anything may be SAID about it is decided outside you.

Suffixes "(Related memory: ...)", "(Earlier in this conversation: ...)",
"(Previous line, background: ...)", "(Addressee of the previous line: ...)",
"(Voice check: ...)" and "(Pre-check: ...)" are context — they help you READ
the current line and are never themselves a reason to act. A Voice check is
MEASURED evidence of who was speaking (the owner's enrolled voiceprint) and
outranks anything the wording implies: a first-person commitment ("I'll get
into it", "I'll book us something") spoken by someone who is NOT the owner
is that person's promise, never the owner's — remember it, and decide as if
a friend said it, because one did. Use them to resolve
what the current line refers to: if the line is "what time is the demo day on
Monday" and the conversation earlier named the Residencies demo day, the goal
must carry that name. A goal built from a line alone, when the conversation
told you what it was about, is a failure.

Before "act", check sufficiency the way a human would: do you know enough to
actually start — the what, the where or who, the when this task needs? First
try to fill gaps YOURSELF from the line and the context; when the context
supplies a missing piece, use it and record it in "assumption" so the owner
can correct you. If something essential is missing and genuinely not
inferable, the right move is "ask" — put the unknowns in "missing". Never
ask about what you can safely infer, and never start work that is guaranteed
to stall on an unknown.
And separately again, the question that decides more than any other:
WHOSE JOB DID THESE WORDS JUST CREATE? — "owes". Wording is a terrible
guide here and meaning is everything, because the same sentence lands
differently depending on who said it and who "you" refers to:
- "owner": the obligation is HIS. He promised someone something; or
  someone asked HIM for something he took on; or he asked you directly.
  This is the only value that can justify doing consequential work.
- "other": the obligation belongs to somebody else in the room. A friend
  saying "I'll book it" or "leave that with me" has taken it on
  THEMSELVES. Remember it — he may want it tracked — but it is not his
  errand and never becomes one on their say-so.
- "machine": he is operating a computer BY VOICE right now — voice-typing,
  dictating a message, reading a list into an app, instructing another
  assistant. Tells: references to things on a screen rather than in the
  world (inboxes, lists, items by number, buttons, fields, files, "reply",
  "include", "remove", "press"), long runs of names/numbers/addresses
  being read out, or commands that only make sense to software. The
  machine he is talking to is ALREADY doing it. There is nothing here for
  you — acting would duplicate work he is doing himself.
- "nobody": no obligation exists. Chatter, opinions, venting, jokes,
  half-thoughts, facts in passing, or transcription too mangled to trust.

"you" is the trap. In "can you look into flights" the "you" is YOU only if
he was addressing you; said to a friend, the friend is "you" and the job is
theirs. Resolve it from who he was talking to, never from the word itself.
When the words are garbled or the obligation is genuinely unclear, answer
"nobody" — silence costs him one missed convenience, a wrong action costs
him trust.

And one last question, only when you are shown numbered earlier lines:
WHICH ONE DOES THIS CARRY ON FROM? — "continues". Give the number of the
single earlier line this one continues: the same subject, an answer to it,
or the next beat of the same thought. Give 0 when it starts something of
its own.

Judge it the way a person in the room would hear it — one thread, or two.
NOT by how much time passed, and NOT by how short the line is. "Can you
book a table" carries on from talk of dinner even after a long silence.
"Did you ever feed the dog" starts something new even with no pause at
all. A cold caller's opening line starts something new; everything they
and he then say back and forth carries on from it, however long the gaps
while the other person talks. If two topics are genuinely interleaved,
point at the one THIS line belongs to, not the nearest one.

Omit "continues" entirely if you truly cannot tell — that is different
from 0, and it is treated as no answer rather than as a new thread.

Reply ONLY with compact JSON:
{"decision":"ignore|ask|act","goal":"<short goal or null>",
 "addressee":"assistant|person|dictation|self",
 "owes":"owner|other|machine|nobody",
 "continues":<number of the line this continues, or 0 for a new one>,
 "missing":["<essential unknowns; empty if none>"],
 "assumption":"<context you relied on, or null>","reason":"<8 words>"}"""

# The only addressee values that mean anything. Anything else the model
# emits is treated as "no classification" — behaviour falls back to what it
# was before this field existed, so a misbehaving model cannot regress her.
ADDRESSEES = ("assistant", "person", "dictation", "self")

# Speech not aimed at her stays in the ambient lane: remembered, worked on
# quietly, but never a text and never an interruption. Silence is about her
# VOICE, not her hands — what she may do is decided separately, below.
AMBIENT_ADDRESSEES = ("person", "dictation")

# The one lane where the words are not his own intentions. When he dictates,
# he is AUTHORING text — voice-typing a message, instructing another AI — so
# "book us a table" inside it is a sentence he is composing, not a plan he is
# making, and acting on it is the 2026-08-04 "On it" bug.
#
# Everything else he says out loud IS intention. A plan agreed with another
# human is the strongest signal Anticipy ever gets — someone else is holding
# him to it — so consequential work there is prepared and held, never binned.
AUTHORED_ADDRESSEES = ("dictation",)

# Whose obligation the words created. The second key: triage may say "act",
# but nothing consequential happens unless the job is actually HIS.
OWES = ("owner", "other", "machine", "nobody")

# The two answers that mean "not his errand". Speech that creates no
# obligation for him is remembered and nothing more — this is what stops
# her acting on a list he is reading into his laptop, or on a friend's
# promise, without needing a single keyword.
NOT_HIS = ("machine", "nobody")

# Goals whose final step changes the world -> require explicit user yes.
IRREVERSIBLE = {
    "draft_and_send_document",
    "find_and_book_restaurant",
    "create_calendar_event",
    "start_cancellation_flow",
    "reorder_item",
    "reschedule_appointment",
    "notify_contact",
}


@dataclass
class Decision:
    decision: str
    goal: Optional[str]
    reason: str
    needs_confirmation: bool = False
    missing: list = None       # essential unknowns blocking a real start
    owes: Optional[str] = None        # whose job these words created
    assumption: Optional[str] = None  # context the model relied on to fill a gap
    addressee: Optional[str] = None   # who the owner was talking to; None = unknown
    # Which numbered earlier line this one carries on from. THREE states, and
    # the difference between the last two is the honesty wall:
    #   >=1  continues that line
    #    0   explicitly starts a new thread
    #   None no answer — fall back to whatever decided this before links
    # An out-of-range number is None, not 0: a model naming line 9 of 4 has
    # told us nothing, and must not be read as confidently starting a thread.
    continues: Optional[int] = None

    def __post_init__(self):
        if self.missing is None:
            self.missing = []

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class Brain:
    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm or LLM()

    def triage(self, transcript_line: str, candidates: int = 0) -> Decision:
        """`candidates` is how many numbered earlier lines the caller showed.
        It is the only thing that makes a "continues" answer meaningful, and
        it is what an out-of-range number is checked against. Left at 0 — the
        default, and what every existing caller passes — the field is always
        discarded, so this parameter cannot change any current behaviour."""
        res = self.llm.chat(TRIAGE_SYSTEM, transcript_line)
        try:
            raw = json.loads(_extract_json(res.text))
        except Exception:
            raw = {"decision": "ignore", "goal": None, "reason": "unparseable model output"}
        decision = raw.get("decision", "ignore")
        goal = raw.get("goal")
        if goal in ("null", ""):
            goal = None
        missing = raw.get("missing") or []
        if not isinstance(missing, list):
            missing = [str(missing)]
        assumption = raw.get("assumption")
        if assumption in ("null", ""):
            assumption = None
        addressee = raw.get("addressee")
        if addressee not in ADDRESSEES:
            addressee = None
        owes = raw.get("owes")
        if owes not in OWES:
            owes = None       # no answer changes nothing: the honesty wall
        continues = _continues(raw.get("continues"), candidates)
        return Decision(
            decision=decision,
            goal=goal,
            reason=raw.get("reason", ""),
            needs_confirmation=(decision == "act" and goal in IRREVERSIBLE),
            missing=[str(m) for m in missing],
            assumption=assumption,
            addressee=addressee,
            owes=owes,
            continues=continues,
        )


SUFFICIENCY_SYSTEM = """A task is about to be started in someone's browser, on
their behalf, while they are not watching.

One question: could a competent assistant sit down RIGHT NOW and carry this
out, using only what is written here?

Not "is it clear what they meant" — could it actually be DONE. Words that
point at something ("the doc", "that spreadsheet", "the team", "the invoice",
a bare first name) only count if this text says WHICH one. If it does not,
the task cannot start.

Two things do NOT block a start: anything discoverable once you are underway
(an opening time, a price, an address), and anything already stated here.

Reply ONLY with compact JSON:
{"can_start": true|false, "needed": ["<what they would have to be told>"]}"""


def check_sufficiency(llm, goal: str) -> list:
    """What would someone have to be TOLD before this could be started?

    The triage prompt already asks for this, in a field called "missing", and
    that field comes back empty essentially always. Measured on the owner's own
    failures: "put the recording link in the doc and email the team", "open
    that budget spreadsheet and add August", "email Priya the invoice" — every
    one returned missing=[] and every one was started and could not finish.
    She did not know which doc, which spreadsheet, or which Priya.

    Adding more instruction to the triage prompt about it changed NOTHING —
    tried, measured on seven cases, zero moved. The field is one of eight in a
    JSON object and it loses. Asked as the ONLY question, the same model on the
    same goals got 8/8, including correctly leaving a fully-specified booking
    and an open-ended research task alone.

    So this is a separate call, and it runs only for goals about to be acted
    on. Returns [] on any failure, which leaves behaviour exactly as it was.
    """
    if not goal or not llm or not getattr(llm, "live", False):
        return []
    try:
        res = llm.chat(SUFFICIENCY_SYSTEM, f"TASK: {goal}", temperature=0.0)
        raw = json.loads(_extract_json(res.text))
    except Exception:
        return []
    if raw.get("can_start") is not False:
        return []                      # only an explicit "no" ever blocks
    needed = raw.get("needed")
    if not isinstance(needed, list):
        return []
    # Bounded: this becomes a question he actually reads. Four unknowns is
    # already a task that should never have been started from one sentence.
    #
    # Filtering on str(n) alone is not enough: str(None) is the four-letter
    # word "None", which is non-empty and would sail through into a question
    # asked out loud — "Quick question: None?". Keep only real strings.
    out = []
    for n in needed:
        if not isinstance(n, str):
            continue
        n = n.strip()
        if n and n.lower() not in ("none", "null", "n/a"):
            out.append(n)
    return out[:4]


def _continues(raw, candidates: int) -> Optional[int]:
    """Read the link answer, refusing everything we cannot act on.

    Returns >=1 (continues that numbered line), 0 (starts a new thread), or
    None (no usable answer — the caller keeps whatever decided this before).

    Everything below collapses to None rather than to 0, because 0 is a
    CLAIM ("this is a new thread") and a confused model has not made one.
    Reading confusion as a claim is how a wall becomes decoration.
    """
    if candidates <= 0:
        return None                       # nothing was shown; nothing to point at
    if isinstance(raw, bool) or raw is None:
        return None                       # True is an int in Python. It is not an index.
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw or raw.lower() in ("null", "none", "new"):
            return None
        try:
            raw = int(raw)
        except ValueError:
            return None
    if not isinstance(raw, int):
        if isinstance(raw, float) and raw.is_integer():
            raw = int(raw)
        else:
            return None
    if raw == 0:
        return 0
    if 1 <= raw <= candidates:
        return raw
    return None                           # out of range: told us nothing


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        return text[start : end + 1]
    return text
