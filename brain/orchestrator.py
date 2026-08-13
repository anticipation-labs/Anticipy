"""Anticipy orchestration brain.

Takes a line of transcript, decides ignore / act / ask, and for 'act'
produces a concrete browser goal. When it acts it runs the task FIRST,
then asks the user to confirm anything irreversible (send/book/pay).
"""
from __future__ import annotations

import json
import re
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
  A THING HE SAYS HE HAS TO DO IS THE WHOLE JOB. "I have to email Priya
  about the invoice", "I've gotta call the dentist back", "I still need to
  send that deposit" — this is how people voice a real errand, and it is
  precisely what you exist to catch. It being HIS obligation, and stated to
  nobody in particular, is not a reason to stay out of it; it is the reason
  to get involved. Never dismiss one of these as thinking aloud.
- "ignore": a great assistant stays quiet: chatter, venting, jokes, questions
  aimed at other people, facts merely mentioned, and commitments that belong
  to someone else. Everything is remembered regardless; ignore only means no
  task right now.
  The line between a to-do and a mere wish is whether there is a REAL,
  FINISHABLE act at the end of it — something you could tell somebody had
  been done. "I have to email Priya" finishes. "I should get to the gym
  more", "I need to be better about this", "we should hang out sometime" do
  not: no act, no anchor, nothing to complete. Those stay quiet. And this is
  about the ACT, never the verb — "have to", "need to", "gotta", "should"
  and "must" all mean the same thing and none of them decides anything.

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

A plan under discussion is LIVE until the conversation moves on, and later
lines routinely change it. A line that corrects a detail of that plan —
"actually make it 8 not 7", "make it earlier, like 7", "the Brooklyn one
instead" — is an "act" whose goal is the FULL plan restated with the
corrected detail, never a fragment and never the stale value. A line that
calls the plan off — "scratch that", "never mind the gym", "cancel it" —
is an "act" whose goal is "cancel <the plan>", naming what he called off.

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
  errand and never becomes one on their say-so. THE TEST: if the friend
  vanished, would the owner still be on the hook? "Leave the flights with
  me" — no, entirely theirs, "other". "Let's do dinner tomorrow, I'll
  text you a time" — yes: the dinner is a plan HE agreed to attend, so it
  is "owner" even though the friend owes one detail. A shared plan is
  never "other" just because the other person owns a piece of it.
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
#
# "self" belongs here too. On identical lines the addressee label wobbles
# between person and self while the goal stays identical — and a plan she
# fully understood must not live or die on that one-word coin flip. Talking
# to himself and talking to a friend earn the same treatment: remembered,
# prepared quietly, one held card through the ambient lane's dedupe. What
# stays special about self-talk is her VOICE (the unasked-question rule),
# not her hands.
AMBIENT_ADDRESSEES = ("person", "dictation", "self")

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
#
# "other" is deliberately NOT here, and adding it was tried and reverted on
# 2026-08-08. It looks like an omission — the prompt says of "other" that "it
# is not his errand and never becomes one on their say-so" — but that case
# already has its own branch in anticipy_core (search: "someone else took this
# on"), which blocks it AND records an accurate reason. Routing it through here
# instead changes nothing except the reason he sees, from "someone else took
# this on" to the plainly wrong "no obligation to anyone".
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

    SECOND_LOOK = """A transcript line was triaged and the verdict came back
contradictory: "do nothing", yet a concrete task was extracted from the
owner's own words. One question, judged on meaning alone: does the OWNER
himself plainly commit to this plan or errand in the line — agreeing to it,
sealing it, taking it on — as opposed to it being someone else's promise,
venting, a hypothetical, or a plan he only heard about?

Reply ONLY with compact JSON: {"owner_committed": true|false}"""

    def triage(self, transcript_line: str, candidates: int = 0,
               explicit: bool = False) -> Decision:
        """`candidates` is how many numbered earlier lines the caller showed.
        It is the only thing that makes a "continues" answer meaningful, and
        it is what an out-of-range number is checked against. Left at 0 — the
        default, and what every existing caller passes — the field is always
        discarded, so this parameter cannot change any current behaviour."""
        # Judgment is a classification, not prose: sampled at 0 so the same
        # words get the same verdict every time, instead of a plan being
        # caught on two runs out of three.
        #
        # And a reply we cannot parse becomes "ignore", which means the line
        # is dropped and he is told nothing at all — the most expensive
        # outcome in the system, spent on the cheapest possible cause. Unlike
        # the browser agent, this call does not constrain the model to JSON
        # (the same client writes her texts, which are prose), so a stray
        # sentence around the object is the whole failure. Ask once more
        # before throwing his plan away; only a second bad reply falls back.
        raw = None
        for attempt in range(2):
            res = self.llm.chat(TRIAGE_SYSTEM, transcript_line, temperature=0.0)
            try:
                raw = json.loads(_extract_json(res.text))
                break
            except Exception:
                if attempt:
                    print("triage: unparseable model output twice — ignoring the line")
                raw = None
        if raw is None:
            raw = {"decision": "ignore", "goal": None, "reason": "unparseable model output"}
        decision = raw.get("decision", "ignore")
        goal = raw.get("goal")
        if goal in ("null", ""):
            goal = None
        # A syntactically valid model reply can still miss an unmistakable
        # request.  That is especially costly on a direct channel: the owner
        # deliberately sent the line to this assistant, yet a single semantic
        # wobble silently discards it.  Re-triage exactly once with the channel
        # evidence made explicit.  Ambient audio never gets this privilege,
        # and a second ignore remains an ignore, so chatter and facts are not
        # mechanically promoted into work.
        if explicit and decision == "ignore" and not goal:
            retry_line = (
                f"{transcript_line}\n(Channel check: the OWNER deliberately "
                "sent this line directly to this assistant. If it plainly "
                "asks for a finishable task, classify that task as act or "
                "ask and preserve every stated name, number, date and "
                "constraint in the goal. Direct delivery is addressee "
                "evidence, not proof that small talk or a bare fact is a "
                "task.)")
            try:
                retry = self.llm.chat(TRIAGE_SYSTEM, retry_line,
                                      temperature=0.0)
                repaired = json.loads(_extract_json(retry.text))
                repaired_decision = repaired.get("decision")
                repaired_goal = repaired.get("goal")
                if (repaired_decision in ("act", "ask")
                        and repaired_goal not in (None, "", "null")):
                    raw = repaired
                    decision = repaired_decision
                    goal = repaired_goal
            except Exception:
                pass
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
        # An "ignore" that still names a concrete task is the model
        # contradicting itself — the exact shape of a real plan slipping by
        # ("let's do it" sealed a dinner; verdict said nothing to do). One
        # isolated second look settles it; anything but a clear yes stays
        # ignored, so venting and other people's promises are unaffected.
        if decision == "ignore" and goal and raw.get("owes") != "other":
            try:
                second = self.llm.chat(self.SECOND_LOOK, transcript_line,
                                       temperature=0.0)
                if json.loads(_extract_json(second.text)).get(
                        "owner_committed") is True:
                    decision = "act"
                    # A commitment of his own IS the answer to whose job it
                    # is — without this the flipped verdict worked silently.
                    if owes in (None, "nobody"):
                        owes = "owner"
            except Exception:
                pass
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


# Verbs she is entitled to use; they are hers, not his.
_GOAL_VERBS = {
    "book", "email", "research", "add", "open", "send", "draft", "reschedule",
    "prepare", "confirm", "remind", "check", "update", "find", "make", "pull",
    "edit", "identify", "fix", "look", "call", "text", "order", "buy", "cancel",
    "schedule", "invite", "reply", "post", "share", "upload", "review", "plan",
    "the", "a", "an", "and", "or", "for", "to", "at", "of", "on", "in", "with",
    "i", "it", "this", "that", "today", "tomorrow", "tonight", "morning",
    "afternoon", "evening", "week", "month", "day", "days", "time", "table",
    "dinner", "lunch", "breakfast", "meeting", "invoice", "reservation",
}


_NUMWORD = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
            "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
            "eleven": "11", "twelve": "12", "a": "1", "an": "1", "couple": "2",
            "single": "1", "dozen": "12"}


def _numbers(text: str) -> set:
    """Every number in the text, as digits, however it was written.

    "four" and "4" are the same fact. Without this, a goal saying "at 4 PM"
    built from him saying "at four" would read as invented, and the check
    would block correct work — which is worse than the bug it exists to stop.
    """
    out = set()
    low = (text or "").lower()
    for w in re.findall(r"[a-z0-9]+", low):
        if w.isdigit():
            out.add(str(int(w)))
        elif w in _NUMWORD:
            out.add(_NUMWORD[w])
    return out


def unsupported_counts(goal: str, *heard: str) -> list:
    """Head counts in the goal that he never gave.

    "For two" is what she reaches for when nobody said how many, and she does
    it constantly: measured across every real job carrying a head count,
    SEVEN OF TEN invented it. On 2026-08-06 that produced "Book lunch for two
    at Cactus" from a line with no number of people in it — and the venue only
    takes parties of six to eight, so the invented two was the reason the
    whole booking failed.

    A party size is not a detail to guess. Two people and six people are
    different bookings, different tables, sometimes different restaurants.
    """
    if not goal:
        return []
    said = set()
    for h in heard:
        said |= _numbers(h)
    out = []
    for m in re.finditer(r"\b(?:for|party of|table for|group of)\s+"
                         r"(one|two|three|four|five|six|seven|eight|nine|ten|"
                         r"eleven|twelve|a|an|couple|dozen|\d+)\b",
                         goal, re.I):
        raw = m.group(1).lower()
        digits = _NUMWORD.get(raw, raw if raw.isdigit() else None)
        if digits is None:
            continue
        digits = str(int(digits))
        if digits not in said:
            out.append(f"how many people — you did not say {raw}")
    return out[:2]


def unsupported_names(goal: str, *heard: str) -> list:
    """Names in the goal that she never actually heard.

    On 2026-08-06 he said, garbled: "Hey we should go out for dinner you
    haven't really shit let's do it but". The goal came back "Book a table at
    EARL'S for dinner THE DAY AFTER TOMORROW", and the first appearance of the
    word Earl's anywhere in the system — his speech, the conversation, the
    segment, memory — was that goal. She invented a restaurant, then texted him
    a time and a party size nobody had mentioned, then spent 58 steps failing
    to book it at a branch in Winnipeg.

    Measured across the last fourteen real jobs, six carried a proper noun
    that appears nowhere in what he said.

    Only PROPER NOUNS are checked, and only against everything she was
    actually given. Completing a name she half-heard is legitimate and stays
    legitimate — "cactus" becoming "Cactus Club Cafe" is her knowing the
    world. Producing "Earl's" from a sentence with no venue in it is not
    knowing the world, it is filling a blank.
    """
    if not goal:
        return []
    hay = " ".join(h or "" for h in heard).lower()
    out = []
    # PHRASES, not words. "Cactus Club Cafe Park Royal" is ONE name, and she
    # is entitled to complete it from "cactus" — knowing the world is the job.
    # Checking word by word flagged "Club" and "Cafe" as inventions, which
    # would have blocked a perfectly good booking. "Earl's" is a phrase whose
    # every part is absent from everything she was given; that is the tell.
    for phrase in re.findall(r"\b(?:[A-Z][\w']*)(?:\s+[A-Z][\w']*)*\b", goal):
        words = [w for w in phrase.split()
                 if w.lower().rstrip("'s") not in _GOAL_VERBS and len(w) > 2]
        if not words:
            continue
        supported = False
        for w in words:
            low = w.lower().rstrip("'s").rstrip("s")
            if low and (low in hay or w.lower() in hay):
                supported = True
                break
        if not supported:
            out.append(" ".join(words))
    return out[:4]


# --------------------------------------------------------------------------
# READING DATA INTO A MACHINE
#
# Three lines from Omar's own logs, every one of which became real jobs:
#
#     Pill 491 kill 492 kill 493 of your list
#     Carson Michael and RV.help23 add that to the KTHAI list
#     4546 4748 reply my inbox drive to Toby's email
#
# He was dictating into his laptop. The pendant overheard it. `looks_like_
# dictation` misses all three: it is tuned for Wispr Flow's long fluent
# instruction-prose, and these are short, garbled, number-dense fragments.
#
# MEASURED 2026-08-06 on google/gemini-2.5-flash — the model production
# actually runs, confirmed via `railway variables --service worker`. Eight runs
# per line: all three fired EIGHT TIMES OUT OF EIGHT. On the local deepseek
# default they fired 3/8 and 2/8, which is why this was never caught here.
#
# What did NOT work: asking the model on its own (11/18 silenced, and the
# KTHAI line 0/6 — because "add that to the list" IS a request, just one aimed
# at a machine already doing it). What did NOT work either: deciding
# mechanically (it silences "the flight is AC123" and "I need 2x4s", which are
# real things people say).
#
# What works is mechanical evidence handed to the model as evidence, with the
# model still making the call: 24/24 garbage silenced, 119/120 real speech
# untouched. And because every one of the three carries evidence, the model is
# only ever asked when there is something to look at — so an ordinary spoken
# sentence costs nothing, and no evidence means no call and no change at all.
# --------------------------------------------------------------------------

# Ordinary ways speech really does fuse a number to letters. Everything else
# with digits buried in it is an identifier, and people do not say identifiers
# out loud to each other.
_SPOKEN_NUMERIC_RE = re.compile(
    r"^\d+(?:am|pm|st|nd|rd|th|s|k|m|b|x|hr|hrs|min|mins|sec|secs|kg|g|lb|lbs|"
    r"ml|l|oz|ft|in|cm|mm|km|mi|c|f|pc|%)$", re.I)

# A phone number read aloud to another person is speech. Seven, ten or eleven
# digits is a phone number; it is the reason "text Priya on 604 555 1234" must
# never be mistaken for reference numbers being read into a form.
_PHONE_DIGIT_COUNTS = (7, 10, 11)


def not_speech_evidence(line: str) -> list:
    """Mechanical marks of text being read INTO something. Pure, no model.

    This is EVIDENCE, never a verdict. Acting on it directly silences real
    speech — measured, it kills "the flight is AC123 landing at 6am" and
    "I need 2x4s and a 10mm bolt". It exists to give the judgement something
    to look at, and to keep the judgement from being asked at all on the
    ordinary sentences that make up almost everything he says.
    """
    text = line or ""
    notes = []

    # 1. Tokens that fuse letters and digits — usernames, codes, references.
    ids = []
    for raw in re.findall(r"\S+", text):
        tok = raw.strip(".,!?;:\"'()[]{}")
        if (tok and re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok)
                and not _SPOKEN_NUMERIC_RE.match(tok)):
            ids.append(tok)
    if ids:
        notes.append("tokens that are not pronounceable words: "
                     + ", ".join(ids[:6]))

    # 2. Runs of bare numbers with nothing attached — minus phone numbers.
    runs, cur = [], []
    for raw in re.findall(r"\S+", text):
        tok = raw.strip(".,!?;:\"'()[]{}")
        if re.fullmatch(r"\d+", tok or ""):
            cur.append(tok)
        else:
            if len(cur) >= 2:
                runs.append(" ".join(cur))
            cur = []
    if len(cur) >= 2:
        runs.append(" ".join(cur))
    runs = [r for r in runs
            if len(r.replace(" ", "")) not in _PHONE_DIGIT_COUNTS]
    if runs:
        notes.append("runs of bare numbers: " + "; ".join(runs[:4]))

    # 3. Numbers stepping evenly upward — 491, 492, 493. A list being recited.
    #    Conversation does not count.
    nums = [int(n) for n in re.findall(r"\b\d{1,6}\b", text)]
    for i in range(max(0, len(nums) - 2)):
        a, b, c = nums[i:i + 3]
        step = b - a
        if step != 0 and abs(step) <= 3 and c - b == step:
            notes.append(f"numbers counting upward in step: {a}, {b}, {c}")
            break

    # Every note goes into a model prompt. A transcript of three hundred
    # numbers produced one note over a thousand characters long — cost and
    # latency on the hot path, for no extra signal. Enough to see the shape.
    return [n if len(n) <= 120 else n[:117] + "..." for n in notes]


READ_ALOUD_SYSTEM = """You are given ONE line a wearable microphone overheard,
and any mechanical observations about it.

Decide one thing only: is this a person SPEAKING — to someone else, or thinking
out loud — or is it a person reading text and data INTO a device (dictating a
message, entering items on a list, spelling out identifiers, reading reference
numbers into a form, instructing another assistant)?

Speech has a request, an opinion, a plan or a thought in it, even when the
transcription is rough. Numbers and names inside real speech are fine: times,
dates, prices, party sizes, a phone number read aloud, a flight number, a part
number. A person really does say "the flight is AC123" and "I need 2x4s".

Numbers that count upward in step are never conversation. They are a list being
recited into something.

Data being read into a device is made of items rather than sentences: bare
reference numbers attached to nothing, codes, usernames, identifiers with
digits buried inside them, a list being recited. It often CONTAINS an
instruction — "add that to the list", "reply to my inbox" — but the instruction
is aimed at the machine already carrying it out, so there is nothing left for
anyone else to do.

The observations are evidence, not a verdict. Weigh them against whether an
actual sentence is being said.

If you cannot tell, it is speech.

Reply with JSON only: {"speech": true|false, "why": "<six words>"}"""


def read_into_a_machine(llm, line: str) -> bool:
    """Was this line read INTO a device rather than said to anybody?

    THE HONESTY WALL. Every failure — no model, no evidence, bad JSON, a
    network error, a blank line — returns False, which is exactly the behaviour
    she had before this existed. This check may only ever take work away that
    was never anybody's; it may never be the reason something happens.
    """
    text = (line or "").strip()
    if not text:
        return False
    evidence = not_speech_evidence(text)
    if not evidence:
        # Nothing to look at. Do not spend a model call, and do not guess.
        return False
    if llm is None or not getattr(llm, "live", False):
        return False
    try:
        res = llm.chat(READ_ALOUD_SYSTEM,
                       f"LINE: {text}\n\nOBSERVATIONS: " + "; ".join(evidence),
                       temperature=0.0)
        got = json.loads(_extract_json(res.text))
    except Exception:
        return False
    # Only an explicit, literal false is a verdict. Absent, null, the STRING
    # "false", a number — none of those are the model saying "this is data",
    # and treating them as one would silence real speech on a malformed reply.
    return got.get("speech") is False


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

But a choice only the OWNER can make is never discoverable: what time THEY
want, how many people are coming, which of two options they'd prefer. A
reservation "tomorrow evening" with no time, or with no party size, cannot be
made — those are their call, and guessing them books the wrong thing.
WHICH PLACE is such a choice too: a business with more than one location (a
chain restaurant, a bank branch, a gym) cannot be booked or visited without
knowing which location they mean — unless this text names it.

Reply ONLY with compact JSON:
{"can_start": true|false, "needed": ["<what they would have to be told>"]}"""


MEMORY_FILL_SYSTEM = """A task is being prepared for someone. One detail was
never stated in the conversation. Below is what is durably KNOWN about them
from memory.

One question: does what is KNOWN plainly settle the missing detail — their own
established choice, habit, or standing preference (their usual place, their
home neighbourhood, the location they always use)? A guess is not an answer.
Something merely plausible is not an answer. Something about a DIFFERENT plan
is not an answer. If memory does not plainly settle it, answer null.

Reply ONLY with compact JSON:
{"answer": "<the detail, concretely>" | null}"""


def fill_gaps_from_memory(llm, memory, goal: str, gaps: list) -> tuple:
    """Missing details are a question of last resort, not first. Before any
    of them turns into a text, memory gets a chance to answer — the place he
    always books, the city he lives in — and whatever it settles rides on the
    card as an ASSUMPTION he sees at the go-ahead, where one "no, the other
    one" fixes it. Only what memory cannot answer is ever asked. Every
    failure path leaves the gap exactly as it was: unanswered means asked."""
    filled: dict = {}
    remaining: list = []
    if not gaps:
        return {}, []
    if memory is None or llm is None or not getattr(llm, "live", False):
        return {}, list(gaps)
    for gap in gaps:
        try:
            facts = memory.recall(f"{goal} {gap}", limit=8)
        except Exception:
            facts = []
        known = "\n".join(
            f"- {f.get('fact') or f.get('text') or ''}".strip()
            for f in facts if (f.get("fact") or f.get("text")))
        if not known:
            remaining.append(gap)
            continue
        try:
            res = llm.chat(MEMORY_FILL_SYSTEM,
                           f"TASK: {goal}\nMISSING: {gap}\n\nKNOWN:\n{known}",
                           temperature=0.0)
            raw = json.loads(_extract_json(res.text))
        except Exception:
            remaining.append(gap)
            continue
        ans = raw.get("answer")
        if isinstance(ans, str) and ans.strip() \
                and ans.strip().lower() not in ("none", "null", "n/a"):
            filled[gap] = ans.strip()
        else:
            remaining.append(gap)
    return filled, remaining


PARTY_SYSTEM = """A personal assistant overheard her owner talking with
someone. A plan came up, and the other person owns at least the next step.

One question: is the OWNER a party to this plan — did he agree to be there,
is it his own plan made together with the other person? Or is the work
entirely the other person's, with nothing the owner is on the hook for?

"Let's do dinner tomorrow, I'll text you a time" — the owner agreed to the
dinner, so he IS a party, even though the friend owes the time.
"Leave the flights with me, I'll sort them" — entirely the friend's; he is
NOT a party to any work here.

Reply ONLY with compact JSON: {"owner_is_party": true|false}"""


def owner_is_party(llm, line: str, goal: str) -> bool:
    """The tiebreaker for owes="other". Asked as its own question because
    triage answers it wrong when both are bundled: shown the full mush of a
    dinner he plainly agreed to, it fixates on "I'll text you a time" and
    files the whole plan under the friend — measured six for six on the live
    2026-08-09 conversation. The same model, asked ONLY this, gets it right.
    Only an explicit true flips anything; absent, malformed, or dead-model
    replies leave the inert behavior exactly as it was."""
    if not goal or not llm or not getattr(llm, "live", False):
        return False
    try:
        res = llm.chat(PARTY_SYSTEM,
                       f"HEARD: {line}\n\nTASK: {goal}", temperature=0.0)
        raw = json.loads(_extract_json(res.text))
    except Exception:
        return False
    return raw.get("owner_is_party") is True


WORLD_SYSTEM = """A transcript line was overheard, and one task was extracted
from it. One question, judged on the SUBSTANCE of the plan and never on the
verb the task happens to be worded with: does seeing this plan through
inherently END in an action that leaves the owner's world — a reservation
made, an order placed, a message sent, a payment — as opposed to work that
only ever reads: research, comparing, looking something up, gathering
options? A sealed dinner plan ends in a reservation whether the task says
"book", "plan" or "arrange" it.

Reply ONLY with compact JSON: {"ends_in_the_world": true|false}"""


def ends_in_the_world(llm, line: str, goal: str) -> bool:
    """The tiebreaker for a read-only-WORDED goal. The same sealed dinner
    comes out of triage as "book dinner at X" one run and "plan dinner at X"
    the next; the verb regex reads "plan" as read-only and the whole plan
    went silent — a coin flip on whether he ever got the one text (seen live,
    2026-08-09). Asked as its own question, the model judges the substance.
    Only an explicit true escalates; absent, malformed or dead-model replies
    leave the quiet behaviour exactly as it was."""
    if not goal or not llm or not getattr(llm, "live", False):
        return False
    try:
        res = llm.chat(WORLD_SYSTEM,
                       f"HEARD: {line}\n\nTASK: {goal}", temperature=0.0)
        raw = json.loads(_extract_json(res.text))
    except Exception:
        return False
    return raw.get("ends_in_the_world") is True


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
