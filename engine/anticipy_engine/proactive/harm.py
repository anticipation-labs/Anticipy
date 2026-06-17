"""Room 2 — the harm-line: act-first, ask-only-before-harm.

ONE inspectable, DETERMINISTIC policy close to the action (not buried in the LLM loop). For
a surviving event it forms the intended action and answers one question: is this DETRIMENTAL?
Confident-no -> ACT (hand the goal to the orchestrator). Yes or UNSURE -> ASK (pause; never
execute until approved). Memory (inject) resolves the gray middle; when memory confidence is
low / abstain it fails safe to ASK and flags `memory_forced` (Deferred-2 — we count how often
the weak confidence signal forces an ask).

General categories only — no site/test-specific branches. Order matters:
  1. hard detrimental (money / destroy / post-public / sign-up / auth-wall) — OVERRIDE all.
  2. hard send (send/forward/dm) — binding, gray via memory. Scope, not weakening: a send
     token that is only the COMPLEMENT of a timed self-reminder frame ("remind me Wednesday
     at 7pm to send the plan") or the purpose tail of an explicit draft request ("draft it
     so I just hit send") is not the requested action — rules 3/5 own those lines, and the
     deferred send is re-gated when the reminder fires (Room 3 -> this same assess).
  3. reminder / calendar hold — reversible even if it mentions a future action (re-gated when
     it fires; Room 3).
  4. soft send (email/reply/message) WITHOUT a draft frame — binding, gray via memory.
  5. draft / prepare (incl. drafting a message) — reversible.
  6. other reversible (research / add-to-cart / reserve / calendar event / prepare a doc).
  7. unclassified -> cannot confirm safe -> fail-safe ASK.
Recipe + sources: notes/proactive_room2.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..shared.invoice_draft import match_invoice_draft_ask
from ..shared.note_task import match_internal_note, match_note_task
from ..shared.schedule_change import match_schedule_change_hold
from ..shared.slotbooking import match_context_slot_choice_booking, match_slot_choice_booking
from ..shared.storesite import derive_store_site

# Money / amount SIGNAL — the recipient-agnostic detector for "this line moves money"
# without needing a spend verb. Used by (a) the _HARD money idiom set below and (b) the
# MONEY INTERLOCK inside _assess_send that forbids the casual_send downgrade. Three shapes:
# a currency-symbol amount ($500, £20), a spelled/numeric amount carrying a money SCALE
# word (five hundred dollars, 200 dollars, a hundred bucks), and a debt/obligation NOUN
# (owe/owed/rent/deposit/invoice/balance/payment/retainer/copay/tab/bill/dues/fee/...).
# Deliberately NOT bare spend verbs (those already gate via the money verb set) and NOT
# bare cardinals ("send Sam the deck", "table for two") — a scale/obligation word is
# required, so non-money content sends are never newly money-blocked.
_MONEY_SIGNAL = re.compile(
    r"[$£€]\s?\d"                                                  # $500, £20, € 50
    r"|\b\d[\d,]*(?:\.\d{1,2})?\s*(?:dollars?|bucks?|euros?|pounds?|grand|usd|cents?)\b"
    r"|\b(?:a|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|forty|"
    r"fifty|sixty|seventy|eighty|ninety|hundred|thousand|couple|few)\b"
    r"[\w\s-]{0,20}?\b(?:dollars?|bucks?|euros?|pounds?|grand|usd|cents?)\b"             # five hundred dollars
    r"|\b(?:hundred|thousand|grand)\b\s+(?:we|i|they|you|he|she)\s+(?:owe|owed)\b"       # five hundred we owe
    # MONEY OUT via refund/reimburse/credit — "refund the overpayment back to his card",
    # "reimburse the client 1100", "credit her account". Money MOVING is the hard stop; the
    # bug-hunt found these surfacing as a plain ask (or dropped) instead of the visible money block
    # because no scale word ("dollars") nor a debt noun was present. Anchored to a money TARGET
    # (card/account/overpayment/payment) or an amount so "I got a refund" / "refund my library book"
    # never trips it.
    r"|\b(?:refund|reimburse|credit)\b[^.;!?]{0,30}?\b(?:card|account|overpayment|payment|venmo|paypal|zelle|\d)"
    r"|\b(?:owe|owed|owes|owing|rent|deposit|invoice|balance|payment|payments|"
    r"retainer|copay|co-pay|tab|bill|bills|dues|fee|fees|tuition|mortgage)\b",
    re.I,
)
# The LEND-MONEY idiom family — a hand-cash request that carries NO scale word ("dollars"/
# "bucks") and NO currency symbol, only a bare cardinal as the object of a transfer verb:
# "Spot me forty for the cab", "Lend me fifty", "Front me twenty", "Give the mover fifty",
# "Slip the valet ten", "Hand the babysitter forty", "Throw the kid twenty", "Kick in fifty".
# These are binding cash sends, but with no scale word they slipped past _MONEY_SIGNAL to the
# weak ASK tier (unclassified) — where a YES executes a real transfer. Shape: a transfer verb
# (spot|lend|loan|front|float|slip|kick in|chip in) with an optional recipient, OR give|hand|
# throw aimed at a NAMED person (determiner + noun, never "give me ..."), followed by a bare
# cardinal. The cardinal must be a true money OBJECT: immediately at a clause boundary, a
# conjunction/new clause, or a money tail (for .../till payday/back/toward/on the tab|bill).
# If a plain noun follows instead ("give me five minutes", "front the team three laptops",
# "give the kids ten cookies"), the cardinal is a QUANTIFIER of that noun -> NOT money. The
# AFTER lookahead is the false-positive guard; "give me a hand"/"hand me the keys" carry no
# cardinal and never match.
_LEND_XFER_VERB = (
    r"(?:spot|lend|lends|lending|lent|loan|loans|loaning|loaned|front|fronts|fronting|fronted|"
    r"float|floats|floating|floated|slip|slips|slipping|slipped|kick in|kicks in|chip in|chips in)"
)
_LEND_GIVE_VERB = r"(?:give|gives|giving|gave|hand|hands|handing|handed|throw|throws|throwing|threw)"
_LEND_RECIPIENT = r"(?:me|him|her|them|us|you|(?:the|a|an|my|your|his|her|our|their)\s+\w+)"
_LEND_CARDINAL = (
    r"(?:\d[\d,]*|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)"
)
_LEND_OBJECT_END = (
    r"(?="
    r"\s*$"
    r"|\s*[.,;!?]"
    r"|\s+(?:and|or|so|then|please|now|i|i'?ll|we|we'?ll|ok|okay)\b"
    r"|\s+for\b|\s+till\s+payday\b|\s+back\b|\s+toward[s]?\b"
    r"|\s+on\s+(?:the\s+)?(?:tab|bill)\b"
    r")"
)
_LEND_MONEY_IDIOM = (
    r"\b" + _LEND_XFER_VERB + r"\b(?:\s+" + _LEND_RECIPIENT + r")?\s+(?:a\s+)?"
    + _LEND_CARDINAL + _LEND_OBJECT_END
    + r"|\b" + _LEND_GIVE_VERB + r"\b\s+(?:the|a|an|my|your|his|her|our|their)\s+\w+\s+(?:a\s+)?"
    + _LEND_CARDINAL + _LEND_OBJECT_END
)
# Spoken money IDIOMS that carry no canonical spend verb and were slipping to the weak ASK
# tier (unclassified) instead of the money category: square up, cover the tab/bill/rent/
# half/cost, tip, prepay, float (someone N), chip in, settle the invoice, put $N / a
# hundred bucks on (an account/card/tab), plus the lend-money family above.
_MONEY_IDIOMS = (
    r"\bsquare up\b"
    r"|\bcover(?:s|ing)?\s+(?:the|my|his|her|our|your|their)\s+(?:tab|bill|rent|half|cost|costs|share)\b"
    r"|\btip(?:s|ped|ping)?\s+(?:the|him|her|them|our|your|\$?\d|\d|a |an )"
    r"|\bprepay(?:s|ing)?\b"
    r"|\bfloat\s+(?:me|him|her|them|you|us)\b"
    r"|\bchip(?:s|ping)?\s+in\b"
    r"|\bsettle\b[^.;!?]{0,20}\b(?:invoice|tab|bill|balance|debt|account)\b"
    r"|\bput\b\s+(?:\$?\d[\d,]*|a\s+(?:hundred|thousand|couple|few)|(?:one|two|five|ten|twenty|fifty)\b)"
    r"[\w\s-]{0,20}?\b(?:on|toward|towards)\b"
    r"|" + _LEND_MONEY_IDIOM
)
# --- hard detrimental (ASK; override everything). Money = SPENDING verbs, not price mentions. ---
_HARD = [
    ("money", r"\b(pay|paid|buy|buys|buying|bought|purchase|purchasing|wire|transfer|transferring|"
              r"spend|spending|checkout|check out|deposit|withdraw|venmo|zelle|cash ?app|paypal|donate|reimburse)\b"
              r"|\border (a|an|the|me|us|food|lunch|dinner|takeout|delivery|coffee|\d)"
              + "|" + _MONEY_IDIOMS + "|" + _MONEY_SIGNAL.pattern),
    ("destroy", r"\b(delete|deletes|deleting|destroy|destroys|destroying|wipe|wipes|wiping|"
                r"erase|erases|erasing|unsubscribe|unsubscribes|deactivate|deactivates)\b"
                r"|\bcancel\w*\b.*\b(subscription|membership|order|account|reservation|booking|plan|"
                r"trial|appointment|payment|transfer|flight|hotel|service|policy|card|insurance)\b"
                r"|\b(remove|close)\b.*\b(account|subscription|file|files|data)\b"
                r"|\bdrop (the )?(table|database|db)\b"),  # cancel needs an object (avoids "noise-cancelling")
    ("public", r"\b(publish|publishes|publishing|tweet|tweets|announce|broadcast)\b"
               r"|\bpost\b.*\b(public|online|twitter|x|linkedin|instagram|blog|forum|sub-?reddit)\b"
               r"|\b(share|make) (it |this |them )?(public|publicly)\b|\bgo live\b"
               r"|\bpublic (calendar )?event\b"),
    ("signup", r"\b(sign up|signs up|signing up|subscribe|subscribes|enroll|enrolls)\b"
               r"|\bcreate (an |a )?account\b|\bstart (a )?(trial|subscription|membership)\b"
               r"|\bregister (for|with|on|at)\b"),
    ("auth_wall", r"\b(log ?in|sign ?in|password|passcode|captcha|authenticate|2fa|"
                  r"two[- ]factor|otp|one[- ]time (code|password))\b|\bverify (my |your )?identity\b"),
]
_HARD_SEND = re.compile(r"\b(send|sends|sending|forward|forwards|forwarding|dm|dms|reach out|"
                        r"invite|invites|inviting)\b")
# Room 3 refire marker (proactive.trigger_tick builds its follow-up events with this
# prefix): a refired loop line must NEVER re-cancel the send reading, so a deferred
# "remind me ... to send X" terminates at the ask when it fires instead of looping.
FOLLOWUP_PREFIX = "Follow up on your commitment:"
# Timed SELF-reminder frame: when it PRECEDES the send token and carries a concrete
# time anchor in its own clause, the requested action is the reminder (rule 3) — the
# hold is reversible and _fire_reminder re-gates the embedded action at fire time.
# Money (rule 1) is checked first and always outranks this exception.
_SELF_REMINDER = re.compile(r"\b(?:remind me|set (?:a |an )?reminder|reminder to|don'?t forget)\b")
_REMINDER_TIME_ANCHOR = re.compile(
    r"\b(?:today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"noon|midnight|in \d+ (?:minutes?|hours?|days?))\b"
    r"|\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b")
_CLAUSE_END = re.compile(r"[.;!?]")
# An explicit draft request may NAME the send the owner will do later ("can someone
# draft that so I just hit send", "...so it's ready to send"): the purpose tail is not
# the requested action. Stripped ONLY when a draft frame is present; a real send
# command ("send the Vicky order email, it's sitting in drafts") never matches.
_SEND_PURPOSE_TAIL = re.compile(
    r"\bso (?:that )?(?:i|we) (?:can |could |just |finally )?(?:hit |press |click |tap )?send\b"
    r"|\bready (?:to send|for (?:me|us) to send)\b")
# Money = SPENDING verbs; a money GERUND modifying a closed-class non-transaction noun
# ("the purchasing window closes soon") is procurement/deadline vocabulary, not a spend
# instruction — strip the compound before the money test. Any real spend verb elsewhere
# in the line still gates, and stripping alone never acts (the rest of the line must
# still match an explicit reversible shape or it stays fail-safe ask).
_MONEY_GERUND_NOUN = re.compile(
    r"\b(?:purchasing|buying|spending)\s+"
    r"(?:window|windows|deadline|deadlines|cutoff|cutoffs|freeze|cycle|cycles|"
    r"period|periods|process|processes|policy|policies|approval|approvals|paperwork|"
    r"department|departments|office|team|teams|manager|managers|decision|decisions)\b")
_CART_ONLY_ACTION = re.compile(
    r"\b(?:add|put|stick|throw|toss|drop)\b[^.;!?]{0,80}\b(?:cart|basket|bag)\b"
    r"|\bcart\s+(?:one|a|an|the|\d)\b",
    re.I,
)
_NO_PURCHASE_BOUND = re.compile(
    r"\b(?:don'?t|do not)\s+(?:buy|purchase|checkout|check out|pay|order)\b"
    r"|\bno\s+(?:buying|purchase|checkout|payment)\b"
    r"|\bwithout\s+(?:buying|purchasing|checking out|paying)\b",
    re.I,
)
_MEMORY_DELETE_METAPHOR = re.compile(
    r"\b(?:my|your|his|her|our)?\s*(?:brain|memory|head|mind)\s+"
    r"(?:deletes?|erases?|wipes?)\s+(?:it|that|this)\b",
    re.I,
)
_SOFT_SEND = re.compile(r"\b(email|emails|emailing|message|messages|messaging|text|texts|texting|"
                        r"reply|replies|replying|respond|responds|responding|tell|tells|telling|"
                        r"ping|pings|pinging)\b")
# delegation ("have someone look into X", "someone should chase Y") and the spoken
# hand-off idiom ("get those answers over to Sam") are messages/requests TO a person —
# binding direction, so they route through the send assessment (memory-gray -> ask).
_DELEGATED_SEND = re.compile(r"\b(?:have|get|ask|tell)\s+someone\b"
                             r"|\bsomeone\s+(?:should|needs?\s+to|has\s+to)\b"
                             r"|\b(?:get|gets|shoot|fire)\b[^.;!?]{0,50}\bover to\b")
_REMINDER = re.compile(r"\b(remind me|set (a |an )?reminder|reminder to|don'?t forget|pencil in)\b"
                       r"|\badd .* to (my |the )?calendar\b|\bblock (off |out )?(time|my calendar|an hour|the morning|the afternoon)\b"
                       # spoken calendar-put: "put that on my calendar", "that goes on the
                       # calendar now", "I need that on my calendar", "block it on the calendar"
                       r"|\b(?:put|puts|putting|get|gets|getting|go|goes|going|add|adds|adding|"
                       r"make|makes|stick|sticks|throw|throws|block|blocks|blocking|need|needs|"
                       r"needed|drop|drops|fix|fixes|update|updates|change|changes|correct|"
                       r"corrects|move|moves)\b[^.;!?]{0,60}\b(?:on|in|into|onto|to)\s+(?:my|the|his|her|our)\s+calendar\b"
                       r"|\b(?:update|fix)\s+(?:my|the)\s+calendar\b"
                       # "block 9 to noon", "block Monday 8 to 9" — a hold phrased as a time range
                       r"|\bblock\b[^.;!?]{0,40}?\b(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\s*"
                       r"(?:to|until|till|through|-|–)\s*(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|midnight)\b")
_FORGET_HOLD = re.compile(
    r"\b(?:before|so)\s+(?:i|we)\s+(?:don'?t\s+)?forget\b",
    re.I,
)
_DRAFT_FRAME = re.compile(r"\b(draft|drafts|drafted|drafting|prepare|prepares|preparing|compose|composes|composing|"
                          r"write up|writes up|outline|outlines|put together)\b")
_VAGUE_CART = re.compile(
    # the spoken anaphor carries modifiers between determiner and head ("that
    # water table thing", "the clamp one") — bounded {0,3}, never open-ended
    r"\b(?:get|grab|add|put)\b[\w' ,.-]{0,80}\b(?:that|the)\s+(?:[\w-]+\s+){0,3}(?:thing|one|item|product)\b",
    re.I,
)
_MEM_SITE = re.compile(r"https?://|(?:[a-z0-9-]+\.)+[a-z]{2,}", re.I)
# same verb family as the orchestrator's _PRODUCT_HINT_RE (they had drifted —
# "comparing" was missing here, so a compared-then-chosen memory never resolved)
_MEM_PRODUCT = re.compile(
    r"\b(?:looked at|looking at|viewed|found|considered|considering|wanted|shopping for|"
    r"compared|comparing|researched|researching|checked out|checking out|"
    r"product|item|thing|cart|kitchen)\b",
    re.I,
)
_RESOLUTION_STOP = {
    "the", "that", "this", "thing", "one", "item", "product", "earlier", "before",
    "looked", "looking", "at", "for", "from", "with", "grab", "get", "add", "put",
    "cart", "basket", "bag", "please", "later", "was", "were", "been", "had", "and",
}
# --- other reversible (ACT) ---
_REVERSIBLE: List[Tuple[str, str]] = [
    # "check with <person>" is consulting a human, not research — falls through to ask
    ("research", r"\b(research|look up|looks up|looking up|look into|find|finds|finding|find out|"
                 r"check(?:s|ing)?(?!\s+with\b)\b|read up|search|searches|searching|browse|browses|"
                 r"compare|compares|summari[sz]e|review|reviews|gather)\b"),
    ("cart", r"\badd\b(?![^.;!?]{0,80}\bnote\b)[^.;!?]*\bcart\b"
             r"|\bput\b(?![^.;!?]{0,80}\bnote\b)[^.;!?]*\bcart\b"),   # add/put <item> to/in (amazon) cart -> reversible
    # natural phrasing: allow filler between the verb and the noun ("book us a table", "set up a
    # quick sync", "prepare a short brief"). Detrimental is checked FIRST, so a paid/binding action
    # can never reach here -> this only moves genuinely-reversible asks to act.
    ("reservation", r"\b(book|books|booking|reserve|reserves|reserving|hold)\b[\w' ]{0,20}"
                    r"\b(table|reservation|appointment|spot|slot|room|court|tee time)\b"),
    ("calendar", r"\b(schedule|set up|book)\b[\w' ]{0,20}\b(meeting|call|standup|sync|appointment|"
                 r"1:1|one[- ]on[- ]one|interview|review|follow[- ]?up)\b"),
    ("calendar_event", r"\b(create|add|make|put)\b[\w' \"\[\]\-:,.]{0,80}"
                       r"\b(calendar event|calendar entry|event (on|in) (my |the )?calendar)\b"),
    ("doc", r"\b(prepare|create|put together|make)\b[\w' ]{0,20}\b(doc|document|memo|brief|report|deck|"
            r"notes|agenda|outline|summary|list|plan)\b"),
]


@dataclass
class HarmVerdict:
    detrimental: bool
    category: str
    reason: str
    memory_forced: bool = False
    confidence: str = "rule"   # rule | memory | unsure


def _first_match(text: str, table: List[Tuple[str, str]]) -> Optional[str]:
    for name, pat in table:
        if re.search(pat, text):
            return name
    return None


_CASUAL = ("mom", "mum", "dad", "wife", "husband", "partner", "spouse", "brother", "sister",
           "friend", "friends", "buddy", "family", "kid", "kids", "son", "daughter",
           "girlfriend", "boyfriend", "roommate", "sibling")


class HarmLine:
    """The single act-first, ask-before-harm policy. Deterministic; memory resolves the gray."""

    def __init__(self, send_casual_floor: float = 0.66) -> None:
        # a SEND downgrades to ACT only if memory is HIGH-confidence (>= floor, not abstain)
        # that the recipient is casual/non-binding. Same scale as the memory abstain floor.
        self.send_casual_floor = send_casual_floor

    def assess(self, action_text: str, ctx: Optional[dict] = None) -> HarmVerdict:
        t = (action_text or "").lower()
        # 1) hard detrimental — overrides everything (including the rule-2 scoping below:
        #    "remind me tomorrow at 9 to pay the vendor" stays an ask). The money test
        #    ignores gerund-noun compounds ("the purchasing window closes"), never verbs.
        hard_text = _MEMORY_DELETE_METAPHOR.sub(" ", _MONEY_GERUND_NOUN.sub(" ", t))
        if _CART_ONLY_ACTION.search(t) and self._memory_has_cart_target(ctx, t):
            hard_text = _NO_PURCHASE_BOUND.sub(" ", hard_text)
        # An invoice DRAFT/REVIEW shape ("invoice the client? no, draft it and let Jordan
        # sanity-check the hours") owns its own dedicated ask path (rule 3.5,
        # match_invoice_draft_ask). The new money-signal obligation noun "invoice" must NOT
        # absorb it into the generic money branch — strip the bare invoice noun for this
        # shape ONLY so it routes to the invoice_draft ask. A real spend on an invoice ("pay
        # the invoice") never matches this shape and still gates as money via the verb.
        if match_invoice_draft_ask(action_text or ""):
            hard_text = re.sub(r"\binvoic(?:e|es|ing)\b", " ", hard_text)
        # INTERNAL NOTE (NOT money): "make sure the retainer NOTE is in the CRM", "add a note in
        # the client file about the retainer". A money/obligation noun (retainer/invoice/...) can
        # be the SUBJECT of an internal record entry without the line ever moving money — the
        # _MONEY_SIGNAL obligation-noun catch wrongly read the bare word as money and blocked the
        # admin note (the lawyer seam). Strip those obligation nouns for this note shape ONLY so it
        # falls through to the reversible `note` branch (rule 3). The note detector itself refuses
        # any line carrying a spend/transaction verb, so a real payment ("pay/wire/chase the
        # retainer") never matches and still gates as money below.
        if match_internal_note(action_text or ""):
            hard_text = re.sub(
                r"\b(?:retainer|copay|co-pay|invoice|invoices|balance|deposit|dues|fee|fees|"
                r"tuition|mortgage|payment|payments|bill|bills|tab|rent)\b",
                " ", hard_text)
        hard = _first_match(hard_text, _HARD)
        if hard is not None:
            return HarmVerdict(True, hard, f"detrimental:{hard} -> ask before acting")
        # 2) hard send (send/forward/dm) — binding, gray via memory. Two SCOPE exceptions
        #    (the send token is provably not the requested action): a draft request's
        #    purpose tail is stripped first, and a send that is the complement of a timed
        #    self-reminder frame falls through to rule 3 (re-gated when the hold fires).
        t_send = _SEND_PURPOSE_TAIL.sub(" ", t) if _DRAFT_FRAME.search(t) else t
        send_ms = list(_HARD_SEND.finditer(t_send))
        if send_ms and not all(self._reminder_scoped_send(t_send, m.start()) for m in send_ms):
            return self._assess_send(t, ctx)
        # 2b) delegation / hand-off to a person ("have someone look into X", "get those
        #     answers over to Sam") — work direction aimed at a human is ALWAYS binding;
        #     the casual-recipient memory downgrade is for first-person social messages
        #     ("text mom I'll be late"), never for delegated work
        if _DELEGATED_SEND.search(t):
            return HarmVerdict(True, "binding_send",
                               "delegated request aimed at a person -> ask before sending")
        # 3) reminder / calendar hold — reversible (the future action is re-gated when it fires)
        if _REMINDER.search(t):
            return HarmVerdict(False, "calendar_hold", "reversible:reminder/hold -> act (re-gated on fire)")
        if match_schedule_change_hold(action_text or "") is not None:
            return HarmVerdict(False, "calendar_hold",
                               "reversible:schedule-change hold -> act (re-gated on fire)")
        if match_context_slot_choice_booking(action_text or "", ctx) is not None:
            return HarmVerdict(False, "calendar_hold",
                               "reversible:memory-resolved slot-choice hold -> act")
        if _FORGET_HOLD.search(t) and _REMINDER_TIME_ANCHOR.search(t):
            return HarmVerdict(False, "calendar_hold",
                               "reversible:time-anchored forget-hold -> act (re-gated on fire)")
        if match_note_task(action_text or "") is not None:
            return HarmVerdict(False, "note", "reversible:note capture -> act")
        # An INTERNAL note in a CRM/file/record whose subject mentions a money word ("the retainer
        # note is in the CRM") is reversible internal admin, not a payment. The note detector
        # already excludes any line with a spend verb, so a real money move never reaches here.
        if match_internal_note(action_text or "") is not None:
            return HarmVerdict(False, "note", "reversible:internal note/record -> act")
        if match_invoice_draft_ask(action_text or ""):
            return HarmVerdict(True, "invoice_draft",
                               "invoice/client financial draft needs confirmation -> ask")
        # 4) soft send WITHOUT a draft frame — binding, gray via memory
        if _SOFT_SEND.search(t) and not _DRAFT_FRAME.search(t):
            return self._assess_send(t, ctx)
        # 5) draft / prepare (incl. drafting a message) — reversible
        if _DRAFT_FRAME.search(t):
            return HarmVerdict(False, "draft", "reversible:draft (not send) -> act")
        if ((_VAGUE_CART.search(t) or _CART_ONLY_ACTION.search(t))
                and self._memory_has_cart_target(ctx, t)):
            return HarmVerdict(False, "cart", "reversible:memory-resolved cart target -> act")
        # 5b) anaphoric slot-choice booking ("they have Friday 9am or Tuesday 2.
        #     Book the Friday 9am one") — the slot anaphor's head is "one", so the
        #     rule-6 verb..noun shapes never see the appointment. Shared shape
        #     (slotbooking.py): same-line appointment-noun anchor + concrete time
        #     in the slot + commerce/travel deny; hard rules above always outrank.
        if match_slot_choice_booking(t) is not None:
            return HarmVerdict(False, "reservation",
                               "reversible:slot-choice booking anchored to an appointment -> act")
        # 6) other reversible
        rev = _first_match(t, _REVERSIBLE)
        if rev is not None:
            return HarmVerdict(False, rev, f"reversible:{rev} -> act")
        # 7) cannot confirm safe -> fail-safe ASK
        return HarmVerdict(True, "unclassified", "cannot confirm safe -> fail-safe ask", confidence="unsure")

    @staticmethod
    def _reminder_scoped_send(t: str, send_pos: int) -> bool:
        """True iff the send token at send_pos is the COMPLEMENT of a timed self-reminder
        frame that precedes it ("remind me Wednesday at 7pm to send the plan") — then the
        requested action is the reminder (rule 3, reversible, re-gated at fire time). A
        refired loop line (FOLLOWUP_PREFIX) never re-cancels, so the deferred send still
        terminates at the ask. Deny-direction: frame after the send, send outside the
        frame's own clause ("remind me at 7pm to call Dee. Send Sam the file now."), or
        no concrete time anchor inside that clause, keeps the binding-send reading."""
        if t.lstrip().startswith(FOLLOWUP_PREFIX.lower()):
            return False
        rem = _SELF_REMINDER.search(t)
        if rem is None or rem.start() > send_pos:
            return False
        end = _CLAUSE_END.search(t, rem.start())
        clause_end = end.start() if end is not None else len(t)
        if send_pos >= clause_end:
            return False
        return bool(_REMINDER_TIME_ANCHOR.search(t[rem.start():clause_end]))

    def _assess_send(self, t: str, ctx: Optional[dict]) -> HarmVerdict:
        # MONEY INTERLOCK (hard stop, money is the line we never auto-cross): a send that
        # carries a money/amount signal — currency symbol, $N, a spelled/numeric amount with
        # a scale word ("five hundred"), a debt/obligation noun (owe/rent/deposit/invoice/
        # balance/payment/retainer/tab/bill/...), or a spoken money idiom — is MONEY even
        # when it has no canonical spend verb ("Send Priya the five hundred we owe her").
        # Force money (ASK/BLOCK) BEFORE the casual downgrade so a casual-recipient memory
        # match can NEVER turn a payment into a casual_send ACT. _HARD already catches these
        # at the top of assess(); this is the binding second gate on the send path.
        if _MONEY_SIGNAL.search(t) or re.search(_MONEY_IDIOMS, t, re.I):
            return HarmVerdict(True, "money",
                               "send carries a money/amount signal -> money hard stop, ask/block "
                               "(no casual downgrade)")
        top = float((ctx or {}).get("top_relevance", 0.0) or 0.0)
        abstain = bool((ctx or {}).get("abstain", True))
        if (not abstain) and top >= self.send_casual_floor and self._recipient_casual(t, ctx):
            return HarmVerdict(False, "casual_send",
                               "send to a casual/known contact (memory high-confidence) -> act",
                               confidence="memory")
        # memory can't confidently say casual/non-binding -> fail safe to ASK, and FLAG it (Deferred-2)
        return HarmVerdict(True, "binding_send",
                           "send to a real person; memory low-confidence on recipient -> fail-safe ask",
                           memory_forced=True, confidence="memory")

    @staticmethod
    def _recipient_casual(t: str, ctx: Optional[dict]) -> bool:
        # SAFETY: match a casual marker ONLY in the action text — where the recipient is named
        # ("text MOM", "send my SISTER the photos") — NEVER across the whole memory-context blob.
        # The old blob match let a stray casual word ANYWHERE in memory ("...hey, remember...")
        # downgrade an unrelated BINDING send ("email the lawyer the signed contract") into an
        # auto-executed casual_send. Memory relevance still gates entry to this check upstream
        # (not abstain AND top >= send_casual_floor); this only removes the off-recipient match.
        return any(re.search(r"\b" + re.escape(w) + r"\b", t) for w in _CASUAL)

    @staticmethod
    def _memory_has_cart_target(ctx: Optional[dict], action_text: str = "") -> bool:
        mem = (ctx or {}).get("context") if isinstance(ctx, dict) else {}
        if not isinstance(mem, dict):
            return False
        action_norm = re.sub(r"\s+", " ", action_text or "").strip().lower()
        vals = []
        for key in ("notes", "open_loops", "history", "profile", "derived"):
            value = mem.get(key)
            if isinstance(value, str):
                vals.extend(line.strip() for line in value.splitlines() if line.strip())
            elif isinstance(value, list):
                vals.extend(str(v) for v in value)
        vals = [
            line for line in vals
            if re.sub(r"\s+", " ", line or "").strip().lower() != action_norm
        ]
        # a real site is a spoken hostname OR a store named the way people speak
        # ("at Target", "on Amazon") in a product-shaped line — the same deny-bounded
        # derivation the orchestrator's resolver uses (shared/storesite.py), so the
        # ACT here is exactly the population the plan layer can complete
        candidates = [line for line in vals
                      if _MEM_PRODUCT.search(line)
                      and (_MEM_SITE.search(line) or derive_store_site(line))]
        if not candidates:
            return False
        hints = {
            t for t in re.findall(r"[a-z0-9]+", (action_text or "").lower())
            if len(t) >= 3 and t not in _RESOLUTION_STOP
        }
        if hints and not any(hints & set(re.findall(r"[a-z0-9]+", line.lower())) for line in candidates):
            return False
        return True
