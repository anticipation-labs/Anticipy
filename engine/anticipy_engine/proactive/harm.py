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

# --- hard detrimental (ASK; override everything). Money = SPENDING verbs, not price mentions. ---
_HARD = [
    ("money", r"\b(pay|paid|buy|buys|buying|bought|purchase|purchasing|wire|transfer|transferring|"
              r"spend|spending|checkout|check out|deposit|withdraw|venmo|paypal|donate|reimburse)\b"
              r"|\border (a|an|the|me|us|food|lunch|dinner|takeout|delivery|coffee|\d)"),
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
_DRAFT_FRAME = re.compile(r"\b(draft|drafts|drafted|drafting|prepare|prepares|preparing|compose|composes|composing|"
                          r"write up|writes up|outline|outlines|put together)\b")
_VAGUE_CART = re.compile(
    r"\b(?:get|grab|add|put)\b[\w' ,.-]{0,80}\b(?:that|the)\s+(?:thing|one|item|product)\b",
    re.I,
)
_MEM_SITE = re.compile(r"https?://|(?:[a-z0-9-]+\.)+[a-z]{2,}", re.I)
_MEM_PRODUCT = re.compile(
    r"\b(?:looked at|looking at|viewed|found|considered|considering|wanted|shopping for|"
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
    ("cart", r"\badd\b.*\bcart\b|\bput\b.*\bcart\b"),   # add/put <item> to/in (amazon) cart -> reversible
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
        hard = _first_match(_MONEY_GERUND_NOUN.sub(" ", t), _HARD)
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
        # 4) soft send WITHOUT a draft frame — binding, gray via memory
        if _SOFT_SEND.search(t) and not _DRAFT_FRAME.search(t):
            return self._assess_send(t, ctx)
        # 5) draft / prepare (incl. drafting a message) — reversible
        if _DRAFT_FRAME.search(t):
            return HarmVerdict(False, "draft", "reversible:draft (not send) -> act")
        if _VAGUE_CART.search(t) and self._memory_has_cart_target(ctx, t):
            return HarmVerdict(False, "cart", "reversible:memory-resolved cart target -> act")
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
        hay = t
        if ctx and isinstance(ctx.get("context"), dict):
            hay += " " + " ".join(str(v) for v in ctx["context"].values())
        return any(re.search(r"\b" + re.escape(w) + r"\b", hay) for w in _CASUAL)

    @staticmethod
    def _memory_has_cart_target(ctx: Optional[dict], action_text: str = "") -> bool:
        mem = (ctx or {}).get("context") if isinstance(ctx, dict) else {}
        if not isinstance(mem, dict):
            return False
        vals = []
        for key in ("notes", "open_loops", "history", "profile", "derived"):
            value = mem.get(key)
            if isinstance(value, str):
                vals.extend(line.strip() for line in value.splitlines() if line.strip())
            elif isinstance(value, list):
                vals.extend(str(v) for v in value)
        candidates = [line for line in vals if _MEM_SITE.search(line) and _MEM_PRODUCT.search(line)]
        if not candidates:
            return False
        hints = {
            t for t in re.findall(r"[a-z0-9]+", (action_text or "").lower())
            if len(t) >= 3 and t not in _RESOLUTION_STOP
        }
        if hints and not any(hints & set(re.findall(r"[a-z0-9]+", line.lower())) for line in candidates):
            return False
        return True
