"""How Anticipy asks for what she does not know.

A missing-facts list is BOOKKEEPING. It is what triage wrote down so the plan
could be parked; it is not a sentence. Pasted straight into a text it produced
this, live on 2026-08-21, after his child said "Dad can you sign the thing for
the trip, it's due Friday":

    Caught your plan — ready to go: Get document for trip signed. First I need:
    What trip?, What document?, Where is the document?, which document, which

Five items in one breath, comma-spliced behind a template prefix, two of them
("What document?" / "which document") the SAME question asked twice, and the
message stopping dead on "which" — a fragment that is not a question at all.
Nobody answers that. It is a form, and it arrived by text.

Contrast, from the same session, when the model was available to speak:

    i'm holding a draft email to the accountant for the receipts; which
    accountant is that, and which receipts should i attach?

Same shape of ignorance, two unknowns, one sentence a person answers in one
reply. That is the target this module renders toward when the model is not
there to say it.

Three rules, all of them about what is NOT said:

1. A question with no subject is not a question. "which", "what", "the" carry
   nothing on their own and are dropped, not spoken. That alone deletes the
   trailing "which" that made the live text look cut off mid-sentence.
2. Two questions about the same thing along the same axis are one question.
   "What document?" and "which document" both ask WHICH DOCUMENT; asking twice
   in one breath reads as a machine, not an assistant. "Where is the document?"
   asks something genuinely different and survives.
3. At most SPOKEN_LIMIT unknowns ever leave in one message. orchestrator's
   check_sufficiency already caps the list it TRACKS at four ("Four unknowns is
   already a task that should never have been started from one sentence"). What
   she SAYS is stricter than what she knows, because a text is answered in one
   breath: two fits one natural sentence joined by "and" — exactly the shape of
   the good message above — and three needs a list, which is the defect.
   Everything past two stays on the card and gets asked next time.

Nothing here ever cuts a word in half. When something has to give, a WHOLE
question is dropped; the only per-entry shortening happens at a space.

Pure functions over the list — no model, no backend, no clock. The caller owns
delivery; this owns the words.
"""
from __future__ import annotations

# What she says at once. See rule 3 above.
SPOKEN_LIMIT = 2

# Longest a single unknown may be spoken. Past this it is an explanation
# somebody stored in the missing list, not a question — cut at a space, never
# inside a word.
_ENTRY_CHARS = 90

# The axis a question asks along. Two questions about the same thing are the
# same question only when they also want the same KIND of answer: "what
# document" and "which document" are one, "where is the document" is another.
_AXIS = {
    "what": "which", "which": "which", "who": "which", "whom": "which",
    "whose": "which", "where": "where", "when": "when", "how": "how",
    "why": "why",
}

# Words that carry no subject of their own, so they cannot distinguish one
# question from another. Only the dedupe KEY sees this list — her actual words
# are never rewritten by it.
_NOISE = frozenset("""
a an the is are was were be been am do does did of for to in on at from with
by about i me my he him his she her they them their you your we us our it its
that this these those there here need needs needed require required want wants
should would will can could shall may might get got give given tell told know
knows exactly actually please and or if then thing things one some any
""".split())


def _tokens(text: str) -> list:
    """The words of a question, lowercased, punctuation gone."""
    out, word = [], []
    for ch in str(text).lower():
        if ch.isalnum():
            word.append(ch)
        elif word:
            out.append("".join(word))
            word = []
    if word:
        out.append("".join(word))
    return out


def _stem(word: str) -> str:
    """Enough morphology that a plural cannot pose as a second question.
    "receipts"/"receipt" are one word. Short words are left alone: "is"/"i"
    and "gas"/"ga" are not the same trade."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _key(question: str) -> tuple:
    """What makes this question a DIFFERENT question. No subject -> ()."""
    words = _tokens(question)
    axis = ""
    for word in words:
        if word in _AXIS:
            axis = _AXIS[word]
            break
    subject = frozenset(_stem(w) for w in words
                        if w not in _NOISE and w not in _AXIS)
    if not subject:
        return ()
    # A question with a subject but no interrogative ("the accountant's email")
    # is an identity ask; grouping it with "which" is what makes the pair
    # "email address" / "which email address" one question rather than two.
    return (axis or "which", subject)


def _clip(text: str) -> str:
    """Shorten at a space or not at all. Never mid-word."""
    text = " ".join(str(text).split())
    if len(text) <= _ENTRY_CHARS:
        return text
    cut = text.rfind(" ", 0, _ENTRY_CHARS + 1)
    return text[:cut] if cut > 0 else text[:_ENTRY_CHARS]


def speakable(missing) -> list:
    """The unknowns worth saying out loud, in the order they arrived.

    Fragments with no subject are dropped, duplicates of an earlier question
    are dropped, and the tail past SPOKEN_LIMIT stays on the card.
    """
    if not missing:
        return []
    if not isinstance(missing, (list, tuple)):
        # Model-shaped junk arrives here too — a bare string, a number, a
        # dict. Whatever it is, it is ONE thing, and iterating it would
        # either explode or spell a word out letter by letter.
        missing = [missing]
    out, seen = [], set()
    for item in missing:
        text = _clip(item if isinstance(item, str) else
                     ("" if item is None else str(item)))
        key = _key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) == SPOKEN_LIMIT:
            break
    return out


def _mid_sentence(text: str) -> str:
    """Drop a leading capital that is only there because a list item started
    with one. She texts in lower case, and "First I need: Client name" is
    half of why the bad message read as a form rather than a sentence.

    An ALL-CAPS lead is left alone: "NHS number", "COSHH sheet", "BOL" are
    the word, not a capitalised word.
    """
    head, sep, rest = text.partition(" ")
    if len(head) > 1 and head[0].isupper() and head[1:].islower():
        return head.lower() + sep + rest
    return text


def _as_question(text: str) -> str:
    """One unknown, phrased so it can sit inside her sentence."""
    return _mid_sentence(text.strip().rstrip("?.!,;: ").strip())


def ask_line(goal: str, missing=None) -> str:
    """What she texts when she is holding a plan and the model cannot speak.

    Says the same two things the template always said — the work is prepared,
    NOTHING has gone out — and then asks, at most, one sentence's worth of
    questions. With nothing to ask it asks for the go-ahead instead; the two
    are different messages and must not be stapled together, because "answer
    these and also say go" is the form again.
    """
    goal = _mid_sentence(" ".join(str(goal or "").split()).rstrip(".")) or "that"
    asks = [q for q in (_as_question(m) for m in speakable(missing)) if q]
    held = f"i've got {goal} ready to go — nothing's booked or sent yet"
    if not asks:
        return f"{held}. say go and i'll run it."
    return f"{held}; " + ", and ".join(asks) + "?"
