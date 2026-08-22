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
  A REALISATION THAT SOMETHING WAS FORGOTTEN IS AN ERRAND, NOT VENTING.
  "Oh my goodness, I forgot to cook for my kids this afternoon", "I never
  sent Priya that invoice", "I completely forgot the dentist was today" —
  the dismay is not the content. The content is a need that is STILL LIVE,
  and this is the single most valuable thing you will ever catch, because
  nobody thinks to ASK for help with something they have only just realised
  they dropped. Test it by whether the need survives the sentence: is there
  something that still has to happen, inside a window you can still see?
  Then act, and make the goal the thing that would actually help — food that
  arrives in time, not a reminder that they forgot.
  If nothing is left to finish, stay quiet: "I forgot to call my brother on
  his birthday last month" is over, and saying so helps nobody.
- "ask": help is clearly wanted but one missing detail blocks starting — the
  single question you'd lean over and ask.
  A THING HE SAYS HE HAS TO DO IS THE WHOLE JOB. "I have to email Priya
  about the invoice", "I've gotta call the dentist back", "I still need to
  send that deposit" — this is how people voice a real errand, and it is
  precisely what you exist to catch. It being HIS obligation, and stated to
  nobody in particular, is not a reason to stay out of it; it is the reason
  to get involved. Never dismiss one of these as thinking aloud.
- "ignore": a great assistant stays quiet: chatter, jokes, questions aimed at
  other people, facts merely mentioned, and commitments that belong to
  someone else. Everything is remembered regardless; ignore only means no
  task right now.
  Venting counts only when there is nothing to be done about it. Frustration
  aimed at something you could still fix is not venting, it is the errand
  arriving in the tone people actually use, and "they were only complaining"
  is the most expensive mistake you can make.
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
  AND - this is the one ambient listening exists for - an obligation he
  ALREADY HAD, which these words merely REVEALED. Nobody promised
  anything, nobody asked, he was not talking to you: he noticed something
  out loud. "I forgot to cook for my kids this afternoon", "the VAT return
  is due on the seventh", "we're completely out of the good coffee", "that
  filling has been aching for a week". The duty existed before the
  sentence did; the sentence is only how you came to hear about it.
  THE TEST: if nobody had spoken at all, would something still need doing,
  and is it his to do? Then "owner". A speech act is ONE way an obligation
  reaches you, never the only way - measured 2026-08-20, treating it as
  the only way sent half of all real errands to "nobody", and the ones it
  dropped were the ones nobody would ever think to ask for.
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
- "nobody": no obligation exists ANYWHERE - not merely no obligation
  created by this sentence. Chatter, opinions, jokes, transcription too
  mangled to trust, and venting there is nothing to be done about.
  A "fact in passing" that names something of his still undone is not this:
  a deadline, an empty cupboard, a bill unpaid, an appointment missed. Ask
  the test above before you land here - would something still need doing if
  nobody had spoken? "Nobody" is for when the honest answer is no.

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

The line you are shown carries appended context: "(Related memory: ...)",
"(Earlier in this conversation: ...)", "(Voice check: ...)", "(Pre-check: ...)".
THAT CONTEXT IS NOT HIM COMMITTING. TRIAGE_SYSTEM says so explicitly and this
prompt did not, while being handed the same decorated line — so a remembered
fact, or another person's words quoted in the conversation block, could satisfy
"the owner plainly commits" and flip an honest "do nothing" into real action he
never asked for. Judge ONLY the current line's own words, spoken by him.

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
            # THE SECOND ASK HAS TO BE A DIFFERENT ASK.
            #
            # This re-sent the identical system prompt and user text at
            # temperature 0.0, and llm.py pins seed=11 — so the retry was a
            # deterministic replay of the reply that had just failed to
            # parse. It could not produce a different answer. All it did was
            # double the latency and the cost on precisely the path already
            # failing, and his line was thrown away regardless.
            if attempt:
                res = self.llm.chat(
                    TRIAGE_SYSTEM,
                    transcript_line + "\n\nYour previous reply could not be "
                    "parsed as JSON. Reply with ONLY the JSON object — no "
                    "explanation before or after it, and no code fence.",
                    temperature=0.2)
            else:
                res = self.llm.chat(TRIAGE_SYSTEM, transcript_line,
                                    temperature=0.0)
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
        if explicit and decision in ("ignore", "ask") and not goal:
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
        # THE ERRAND HAS TO BE IN HIS LINE. See inherited_errand() above for
        # the live pair this is here for: a vent line 50 seconds after a
        # dinner errand, in a different segment, came back as "act" with the
        # dinner errand reworded — and texted him about it.
        #
        # It runs BEFORE the second look on purpose, and drops the goal as
        # well as the verdict. An "ignore" that still carries a goal is a real
        # state elsewhere in this system — score.py reads it as the quiet lane
        # and the phone renders it "Looking into it." — and it would be a lie
        # here, because there is no errand at all. Dropping the goal is also
        # what stops the second look immediately flipping this back to "act".
        if decision in ("act", "ask") and goal and inherited_errand(
                transcript_line, goal):
            decision = "ignore"
            goal = None
            missing = []
            assumption = None
            raw["reason"] = "the errand came from the context, not this line"
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
# CONTEXT MAY INFORM A JUDGEMENT. IT MAY NOT SUPPLY THE ERRAND.
#
# MEASURED live 2026-08-21 on a real account, two lines 50 seconds apart in
# DIFFERENT segments:
#
#   s1 "oh no, I completely forgot to sort anything for dinner and the kids
#       will be back by six"     -> act, "Arrange dinner for the kids for 6 PM"
#   s2 "honestly this whole week has just been one thing after another, I am
#       wrecked"                 -> act, "Order dinner for kids", job queued,
#                                   AND A TEXT SENT TO HIM
#
# s2 is venting with no errand in it at all, and the goal it produced is
# visibly s1's, reworded. It interrupted him about work he never mentioned.
# proof/ambient/score.py:62 weights a false ping as five misses, because
# trust does not come back — this is the most expensive thing we can do.
#
# WHICH CARRIER: reproduced by replaying both lines through Anticipy.hear()
# with a recording brain in place of this one. The segmenter is innocent —
# "(Earlier in this conversation: ...)" was EMPTY for s2, the segments really
# were different. The dinner line reached triage twice by other routes:
#   "(Previous line, background: ...)"  — anticipy_core's `_prev`, a 120s
#       process-level cursor that has never known what a segment is; and
#   "(Recent lines, oldest first ...)"  — the numbered link candidates, which
#       worker.link_candidates() draws across segments by construction.
# Memory recall is a third route on any line whose words happen to match.
#
# So this is fixed HERE, in the one place that sees the current line AND
# everything appended to it. Blocking one carrier would leave the other two,
# and the next context block anyone adds would open a fourth.
#
# THE RULE, and it is narrow on purpose: context resolves REFERENCES — "seven
# works", "yeah book it", "the Brooklyn one instead" are the owner sealing a
# plan and MUST keep working (tests/test_continues.py). What it may not do is
# hand an errand to a line that contributes none of it and points at nothing.
# --------------------------------------------------------------------------

# anticipy_core appends each context block as a fresh line starting "(":
# "(Earlier in this conversation: ...)", "(Previous line, background: ...)",
# "(Addressee of the previous line: ...)", "(Voice check: ...)", "(Pre-check:
# ...)", "(Related memory: ...)", "(Recent lines, oldest first ...)". Cutting
# at the FIRST one leaves exactly the words he said — and a block added
# tomorrow is stripped by the same seam without anyone editing this file.
_CONTEXT_BLOCK_RE = re.compile(r"\n\(")


def own_words(prompt: str) -> str:
    """The line as he actually said it, with every appended block removed."""
    return _CONTEXT_BLOCK_RE.split(prompt or "", 1)[0].strip()


def appended_context(prompt: str) -> str:
    """Everything the caller decorated the line with, and nothing he said."""
    parts = _CONTEXT_BLOCK_RE.split(prompt or "", 1)
    return parts[1] if len(parts) > 1 else ""


# TWO DIFFERENT QUESTIONS, and conflating them cost two false positives in a
# battery run before this comment existed ("book us a table" and "what time
# did we say" both got eaten):
#
#   DID HE CONTRIBUTE ANY OF THIS ERRAND?  -> _content(): everything he said
#       that carries meaning. "book us a table" contributes "book" and
#       "table" even though the goal's Joe's-at-seven came from context, and
#       filling a detail from context is explicitly her job (TRIAGE_SYSTEM:
#       "when the context supplies a missing piece, use it").
#   IS THERE ANYTHING IN THIS GOAL TO TRACE?  -> _substance(): the same,
#       minus the words she is entitled to supply herself. A goal's "book" or
#       "dinner" proves nothing about where the errand came from, because
#       _GOAL_VERBS exists precisely to say those are hers.
#
# _GLUE is what neither question may count: words any two unrelated English
# sentences share by accident. A shared "the" or "my" is not evidence, and
# counting one as evidence is how a guard like this quietly stops working.
_GLUE = {
    "the", "a", "an", "and", "or", "but", "for", "to", "at", "of", "on",
    "in", "with", "it", "its", "i", "this", "that", "be", "been", "am",
    "is", "are", "was", "were", "do", "does", "did", "have", "has", "had",
    "will", "would", "should", "could", "can", "may", "get", "got", "go",
    "going", "gone", "my", "me", "we", "us", "our", "you", "your", "he",
    "she", "him", "her", "his", "hers", "they", "them", "their", "by",
    "from", "up", "out", "off", "about", "before", "after", "into", "over",
    "under", "again", "just", "some", "any", "all", "no", "not", "so", "if",
    "as", "than", "then", "there", "here", "what", "when", "where", "who",
    "how", "why", "very", "really", "one", "ones", "thing", "things",
    "those", "these", "back", "now", "still", "more",
}


def _content(text: str) -> set:
    """Every meaning-bearing token, plus every number however it was written.

    Singulars and plurals are one token ("kids" == "kid"), the same
    normalisation unsupported_names already uses, so "dinner for kids" and
    "the kids will be back" are recognised as the same subject.
    """
    out = set(_numbers(text))
    for w in re.findall(r"[a-z][a-z']*", (text or "").lower()):
        w = w.rstrip("'").replace("'s", "")
        if w in _GLUE or len(w) < 3:
            continue
        out.add(w.rstrip("s") or w)
    return out


def _substance(text: str) -> set:
    """What could only have come from somewhere — her own verbs removed."""
    return {w for w in _content(text) if w not in _GOAL_VERBS}


# Ways a line points OUT of itself. Every shape here is how people really
# seal a plan in three words, and all of them must survive this guard.
#
# STRONG seals: words whose whole job in a sentence is to answer something
# already on the table, wherever they appear in the line.
_SEALS_RE = re.compile(
    r"\b(?:yeah|yep|yes|yup|ok|okay|sure|agreed|alright|all right|"
    r"sounds (?:good|right|fine)|go ahead|let'?s|do it|book it|please|"
    r"confirmed|scratch that|never ?mind|forget it|cancel|instead)\b", re.I)

# WEAK seals: the same job, but done by words that also live ordinary lives
# in the middle of a sentence. The battery run caught this the honest way —
# "work has been absolutely relentless lately" was let through by "work"
# matching a confirming "works" and by a bare "absolutely". So these count
# only where a confirmation actually lands: as the whole line, or at the end
# of one ("seven works", "Tuesday is fine").
_WEAK_SEAL_RE = re.compile(
    r"^\W*(?:perfect|great|fine|deal|definitely|absolutely|lovely|cool|"
    r"nice)\W*$|\b(?:works?|is fine|is good|will do|suits me)\W*$", re.I)

# And a bare pronoun — a hand pointing at something outside the line.
#
# THE DISTINCTION THAT DECIDES THIS WHOLE FIX: "this", "that" and "one" are
# pronouns only when nothing follows them to be pointed at. IN FRONT OF A
# NOUN they name their own subject and point nowhere — "this whole week",
# "one thing after another", "that dentist appointment". The vent line is
# built entirely out of that second shape, so a regex that ignored the
# difference would either miss the bug or swallow "do that".
#
# "it" and "them" are never determiners, so they need no tail. The others
# count only before a stop, an apostrophe, or a closed set of words a
# determiner can never precede.
_REFERS_OUT_RE = re.compile(
    r"\b(?:it|its|them|they|theirs)\b"
    r"|\b(?:this|that|these|those|one|ones|same)\b"
    r"(?:\s*$|\s*[,.!?;:—-]|\s*'|\s+(?:is|are|was|were|works?|sounds?|looks?|"
    r"seems?|will|would|should|could|can|does|do|did|has|have|too|as well|"
    r"instead|then|though)\b)", re.I)

# And a reference to what was SAID earlier, which is the same pointing finger
# wearing a different glove: "what time did we say", "the place you mentioned",
# "like we agreed". Added after a battery run ate "what time did we say" — a
# perfectly good look-it-up errand about the plan sitting right there.
_RECALLS_TALK_RE = re.compile(
    r"\b(?:we|you|he|she|they|i)\s+(?:said|say|agreed|mentioned|decided|"
    r"picked|chose|settled\s+on)\b|\b(?:did\s+we|as\s+discussed|"
    r"like\s+we|you\s+mentioned)\b", re.I)


# A NEED OF ITS OWN, in whatever words. The battery run that produced this
# ate four honest requests — "can you get us a reservation", "make the
# booking", "sort us out somewhere", "we still need a table" — because none
# of them happens to share a word with the goal she wrote for them. Lexical
# overlap can never catch a synonym, so the shape of the sentence has to be
# asked about separately: is this line ASKING for something, or is it just
# describing how the day went?
#
# Deliberately generous. It only ever stops the guard from firing, and the
# guard only runs on a line the model ALREADY called act or ask, so a loose
# match here costs a missed catch, never a wrong action.
#
# MEASURED against proof/ambient/corpus.json, all 173 gold act/ask lines
# decorated with their real conversation context: this guard ate exactly one
# of them, amb-0318 "I am not doing another shop this week, can something
# just turn up." — a refusal plus a wish, with the coffee and the dishwasher
# tablets named several turns earlier. A bare "can" and a flat refusal are
# both a need being voiced, so both were added; that took the count to 0 out
# of 173 eaten, and left the guard's catch rate on the same corpus unchanged.
_NEEDS_RE = re.compile(
    r"\b(?:can|could|would|will|do)\s+(?:you|u|we)\b|\bplease\b"
    r"|\bneeds?\b|\bhave\s+to\b|\bhas\s+to\b|\bhad\s+to\b|\bgotta\b"
    r"|\bgot\s+to\b|\bmust\b|\bshould\b|\bwant(?:s|ed)?\s+to\b"
    r"|\bwould\s+like\b|\blet'?s\b|\bsupposed\s+to\b|\bmeant\s+to\b"
    r"|\bforgot\b|\bforgotten\b|\bnever\s+(?:got|sent|did|called|booked|paid)\b"
    r"|\bhaven'?t\b|\bhasn'?t\b|\bdidn'?t\b|\bran\s+out\b|\bout\s+of\b"
    r"|\bnot\s+doing\b|\bnot\s+going\s+to\b|\bcan\b(?!['\u2019])"
    r"|\bdue\b|\bdeadline\b|\boverdue\b|\bby\s+(?:six|seven|eight|nine|ten|"
    r"eleven|twelve|noon|tonight|tomorrow|monday|tuesday|wednesday|thursday|"
    r"friday|saturday|sunday|\d)", re.I)

# Speech is imperative when it opens on a verb: "make the booking", "sort us
# out somewhere", "grab something for the kids". A separate list from
# _GOAL_VERBS, which answers a different question (what SHE may put in a
# goal) and carries nouns and particles this must not treat as verbs.
_ACTION_VERBS = {
    "book", "order", "buy", "get", "grab", "sort", "arrange", "organise",
    "organize", "make", "take", "pick", "put", "set", "send", "email", "text",
    "message", "call", "ring", "phone", "tell", "ask", "pay", "cancel",
    "reschedule", "move", "swap", "change", "fix", "find", "look", "check",
    "confirm", "chase", "bring", "fetch", "drop", "print", "scan", "file",
    "submit", "renew", "register", "sign", "apply", "draft", "write", "add",
    "remind", "research", "prepare", "plan", "schedule", "invite", "reply",
    "help", "start", "finish", "sort", "clean", "pack", "ship", "return",
    "extend", "open", "update", "review", "share", "upload", "post", "edit",
}


def states_a_need(line: str) -> bool:
    """Is there something in this line's OWN words that wants doing?"""
    line = (line or "").strip()
    if _NEEDS_RE.search(line):
        return True
    first = re.match(r"[a-z']+", line.lower())
    return bool(first and first.group(0) in _ACTION_VERBS)


def points_outward(line: str) -> bool:
    """Does this line lean on something said earlier to mean anything?"""
    line = line or ""
    return bool(_SEALS_RE.search(line) or _WEAK_SEAL_RE.search(line.strip())
                or _REFERS_OUT_RE.search(line) or _RECALLS_TALK_RE.search(line))


def inherited_errand(prompt: str, goal: str) -> bool:
    """Was this goal taken from the context rather than from his words?

    True only when ALL FOUR hold, and each one is there to keep a real errand
    out of the net:
      1. the goal has substance to trace at all — a goal made only of her own
         verbs ("book a table for dinner") is not evidence of anything;
      2. he contributed NO part of it and asked for nothing — not the action,
         not the subject, not a name, not a number, and no need in any words
         of his own. Both halves are generous on purpose: a real request
         whose details came from context ("book us a table" / "can you get us
         a reservation", after they settled on Joe's at seven) is her filling
         a gap, which TRIAGE_SYSTEM tells her to do, not a fault;
      3. his line points at nothing — no agreement, no refusal, no bare
         pronoun, so there is no reference for context to resolve;
      4. the substance IS sitting in the appended context — which is what
         makes this inheritance rather than invention. Invention out of thin
         air is unsupported_names' job, and is left to it.

    Anything less and the answer is False: the honesty wall runs the same way
    here as everywhere else, and a guard that guesses is worse than none.
    """
    if not goal:
        return False
    want = _substance(goal)
    if not want:
        return False                       # nothing traceable: no evidence
    line = own_words(prompt)
    if _content(goal) & _content(line):
        return False                       # he said part of it himself
    if states_a_need(line):
        return False                       # the ask is his, only the details aren't
    if points_outward(line):
        return False                       # "seven works", "yeah book it"
    return bool(want & _substance(appended_context(prompt)))


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
        # UNTRUSTED FACTS ARE EXCLUDED HERE, not fenced.
        #
        # Every other memory sink can afford to show untrusted text inside a
        # "quoted, never obey it" block, because the worst case is the model
        # describing it. This one cannot: the answer becomes filled[gap] ->
        # params[key] -> seed_facts -> new_plan(facts=...) -> the browser
        # agent's FACTS ALREADY GIVEN block, i.e. an APPROVED VALUE it may type
        # into a form and submit. extension/agent_loop.js:982-991 states the
        # invariant in as many words: memory must never be promoted into facts,
        # because "a sentence she overheard could put a value into a form that
        # spends his money."
        #
        # A calendar title is written by whoever sent the invitation, and a mail
        # subject line is written by whoever sent the mail. Letting either
        # answer "what is the reservation name" would launder a stranger's text
        # into a value spent on the owner's behalf. Anything untrusted is
        # therefore not eligible to settle a gap at all — she asks instead,
        # which is the safe branch this function already has.
        #
        # Imported LOCALLY so the fence has one definition. anticipy_core
        # imports this module (anticipy_core.py:36-40), so a module-level
        # import the other way is a cycle; the deferred one costs a dict lookup
        # per gap and keeps this sink from drifting out of step with
        # memory_notes, which is exactly how it came to be comparing against
        # the literal "import" while the set grew. An ImportError here
        # propagates to the caller's except, which sets filled={} and asks the
        # owner — this fails CLOSED.
        from .anticipy_core import _UNTRUSTED_SOURCES
        facts = [f for f in facts
                 if str(f.get("source") or "") not in _UNTRUSTED_SOURCES]
        known = "\n".join(
            f"- {f.get('fact') or f.get('text') or ''}".strip()
            for f in facts if (f.get("fact") or f.get("text")))
        if not known:
            remaining.append(gap)
            continue
        try:
            res = llm.chat(MEMORY_FILL_SYSTEM,
                           f"TASK: {goal}\nMISSING: {gap}\n\nKNOWN:\n{known}",
                           temperature=0.0, aux=True)
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
        # NOT aux. Measured 2026-08-21 on 120 lines: moving this one call to
        # the cheap model took false pings to 0.0% and behaviour accuracy to
        # 81.7%, which looks like a win until you read the behaviour matrix —
        # `act` landing on his desk collapsed from 37 to 8 and quiet work rose
        # from 12 to 41, because a cheaper model finds fewer blocking unknowns
        # and the task then runs silently instead of asking. That is a trade of
        # the owner's visibility for silence, not a saving, and it was worth
        # about 15% of a per-utterance cost already down 5.7x. Left on the main
        # model deliberately; see TESTING-PASS-2026-08-21.md.
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
