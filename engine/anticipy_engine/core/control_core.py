"""ControlCore — assembles the whole brain and exposes a tiny driving surface.

One object that wires the bus, the model gateway, the glass-box, the scorecard,
the stub workers, the orchestrator, and the proactive engine together. The HTTP
layer and the tests drive it through `feed()` and `resume()`.
"""
from __future__ import annotations

import asyncio
import contextvars
import datetime as dt
import json
import os
import re
import hashlib
import urllib.parse
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .browser_link import BrowserLink
from .bus import Bus
from .env import load_local_env
from .envelopes import Event, EventSource, Goal, GoalState, Job, JobStatus
from .gateway import ModelGateway, PROVIDER_GEMINI, PROVIDER_OPENROUTER
from .glassbox import GlassBox
from .native_bridge_link import NativeBridgeLink
from .orchestrator import Approver, Orchestrator
from .proactive import ProactiveEngine
from .scorecard import Scorecard
from .store import GoalStore
from .workers import ChannelStub, ChannelWorker, MemoryWorker
from ..channels.call import CallChannel
from ..channels.text import TextChannel
from ..hands import ApiHand, BrowserHand, MODE_LIVE, MODE_MOCK
from ..hands.api_hand import INTENT_MAP
from ..hands.token_vault import TokenBroker, TokenVault
from ..live_memory.brain import LiveMemoryBrain
from ..memory.store import Memory, is_active_open_loop
from ..owner_mode import OwnerIngestResult, OwnerMode, OwnerObservedLine, OwnerTaskCard
from ..owner_onboarding import OwnerOnboardingIn, build_onboarding_plan
from ..proactive.gateway import ProactiveGatewayLedger
from ..proactive.harm import _MONEY_SIGNAL  # the money hard-stop signal (amount/account/transfer-to)

# The final/ area (the ONE clean home of each system) lives at the repo root, one level above
# the engine package dir, so it is not on the engine's import path by default. Add it, then pull
# in the Phase-3 learns-you context engine. Fail-open: if final/ is absent the engine still boots
# (self.context stays None and intake behaves exactly as before).
try:
    import sys as _sys, pathlib as _pathlib
    _REPO_ROOT = str(_pathlib.Path(__file__).resolve().parents[3])
    if _REPO_ROOT not in _sys.path:
        _sys.path.insert(0, _REPO_ROOT)
    from final.context import ContextEngine as _ContextEngine
except Exception:  # pragma: no cover - final/ missing or import error must never break the engine
    _ContextEngine = None


def _base(data_dir=None) -> Path:
    # ABSOLUTE at construction (cwd-frozen): routes that re-derive data_dir at request time (e.g.
    # GET /onboard/status) must not drift when the process cwd changes — a relative ".anticipy-data"
    # resolved per-request against a different cwd threw a completed owner back into setup (the
    # onboarding "split-brain"). os.path.abspath freezes it absolute WITHOUT resolving symlinks (so it
    # stays byte-equal to the configured path — /var vs /private/var etc. don't diverge).
    raw = Path(data_dir or os.environ.get("ANTICIPY_DATA_DIR", ".anticipy-data")).expanduser()
    return Path(os.path.abspath(raw))


# DETERMINISTIC ASIDE FLOOR (model-independent). A past/perfect interrogative directed at
# someone else — "Did you grab the dry cleaning on the way home?", "Have you emailed Sarah
# yet?", "Didn't you already call the dentist?" — is a CHECK on another person's action, never
# the owner's own new task. The MOAT model strips the "did you …?" wrapper and over-extracts a
# bare imperative ("grab the dry cleaning") that then reads as actionable, so the /owner/ingest
# split path turned a question into an ASK (the cardinal sin: a vent/aside must stay silent).
# The proactive path's deterministic triage already silences these; this makes the SAME guard a
# hard floor on the model path. Scoped to PAST/PERFECT auxiliaries only, so a present/future
# request to the assistant ("Can you remind me to call mom at 3?") is untouched. Fails to silence.
_INTERROGATIVE_ASIDE = re.compile(
    r"^\s*(did|didn'?t|do|does|doesn'?t|have|haven'?t|has|hasn'?t|had|hadn'?t|"
    r"were|weren'?t|was|wasn'?t|are|aren'?t|is|isn'?t)\s+"
    r"(you|we|they|he|she|it|u|your|the|anyone|someone|anybody|somebody)\b",
    re.I)

_GATEWAY_EVENT_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "anticipy_gateway_event_id", default=None)
# A PAST/PERFECT completion-check aimed at the listener — "did you ...", "have you ...",
# "didn't you ..." — anywhere in a question, so real-speech lead-ins ("hey did you ...?",
# "anyway, did you ...?", "um so have you ...?") and rambling multi-clause questions are caught
# too (the audit found "hey did you remind Jenny to send the slides at 4 like I asked" leaking a
# fabricated timed reminder). Present-tense requests to the assistant ("can you remind me ...?")
# do NOT match (no did/have/had), so they stay catchable.
_QUESTION_TO_OTHER = re.compile(
    r"\b(did|didn'?t|have|haven'?t|has|hasn'?t|had|hadn'?t|were|weren'?t|was|wasn'?t)\s+"
    r"(you|u|ya|anyone|someone|anybody|somebody)\b",
    re.I)
# A first-person COMPLETION CLAIM — "I sent mom the photos already, that's done", "I paid it,
# handled" — closes the matching still-open card instead of echoing it or opening a new one.
# Requires a past-tense first-person verb PLUS an explicit done marker (or a bare "that's done/
# handled") so a mere status mention ("I called the dentist and left a voicemail") never closes.
_COMPLETION_CLAIM = re.compile(
    r"(?:\bi (?:already )?(?:sent|did|called|paid|booked|emailed|texted|finished|handled|"
    r"cancell?ed|mailed|submitted|returned|signed|picked up|dropped off|took care of)\b"
    r".{0,80}?(?:\balready\b|\bthat'?s (?:done|handled|sorted)\b|\bit'?s done\b|\ball set\b|\bdone\b))"
    r"|(?:\b(?:that'?s|it'?s) (?:done|handled|sorted|taken care of)\b)",
    re.I | re.S)
# A LINGERING OBLIGATION voiced as self-reproach — "I keep forgetting to cancel the gym",
# "I've been meaning to renew my plates", "I never got around to booking it" — is a REAL task
# a person expects caught, but the phrasing reads as narration and gets dropped. Surfaced as a
# confirm-first ask (never auto-act), only when no surviving line already covers it.
_LINGERING_OBLIGATION = re.compile(
    r"\bi(?:'?ve)?\s+(?:keep\s+(?:forgetting|meaning)|been\s+meaning|"
    r"never\s+got\s+around|really\s+need)\s+to\s+\w+",
    re.I)
# An UPDATE to an existing task — "make it Thursday", "move it to next week", "actually
# Thursday works better" — should REVISE the tracked card, never sit beside it as a duplicate.
# Long words too generic to anchor a cross-card match on their own ("thing", "tomorrow").
_GENERIC_ANCHOR_WORDS = {
    "thing", "things", "stuff", "today", "tomorrow", "tonight", "morning", "evening",
    "please", "gonna", "going", "really", "actually", "checking", "check", "little",
    "about", "should", "would", "could", "still", "again", "later", "sometime", "maybe",
    "appointment", "reminder", "remind", "schedule", "reschedule", "instead", "better",
}
_TASK_UPDATE_MARKER = re.compile(
    r"\b(?:make (?:it|that)|move (?:it|that)|change (?:it|that) to|push (?:it|that) to|"
    r"reschedule|works better|instead of (?:that|tomorrow|today)|actually .{0,40}\b(?:better|instead)\b)",
    re.I)
# A QUESTION/REQUEST ADDRESSED TO A NAMED THIRD PARTY — "Jordan, can you pull the freight numbers?",
# "Mom, could you grab milk?", "Sam can you take the on-call handoff?" — is THEIR task, never the owner's.
# It opens with a proper-name vocative + a present/future request aux ("can/could/would/will/do/are you").
# The 20-life test exposed TWO holes in the first version of this guard:
#   1) it required a COMMA after the name, but real/transcribed speech routinely drops it ("Sam can you
#      take the handoff?") -> the engineer line was adopted as the owner's task;
#   2) it KEPT the line when the owner was a beneficiary ("Marcus, can you grab MY prescription",
#      "Tomas, can you grab milk and my prescription") -> but those are STILL the named person's errand,
#      and the engine adopted them (one even AUTO_DO). The "my X" is the OBJECT of THEIR action, not a
#      task for the assistant.
# Now: comma-form is case-insensitive (the comma is a strong vocative marker); no-comma form REQUIRES a
# Capitalized proper name (the capital replaces the missing comma) and is case-SENSITIVE. Both exclude
# sentence-opener fillers, weekday/time words, and the assistant's own name, so "Well, can you check X" /
# "Today can you ..." / "Anticipy, can you ..." / a bare "can you remind me ..." all stay catchable.
# The owner-beneficiary carve-out is REMOVED — a question to a named person is theirs regardless of "my".
_DAQ_FILLER = (r"well|so|ok|okay|hey|hi|yo|now|then|look|listen|please|right|sure|no|yes|yeah|nah|"
               r"maybe|also|and|but|oh|um|uh|hmm|wait|today|tomorrow|tonight|tonite|monday|tuesday|"
               r"wednesday|thursday|friday|saturday|sunday|anticipy")
_DIRECT_ADDRESS_Q_COMMA = re.compile(
    r"^\s*(?!(?:" + _DAQ_FILLER + r")\b)"
    r"[a-z][a-z'’.\-]*,\s+(?:can|could|would|will|won'?t|do|are|is)\s+(?:you|u|ya)\b",
    re.I,
)
_DIRECT_ADDRESS_Q_NOCOMMA = re.compile(
    r"^\s*(?!(?:Well|So|Ok|Okay|Hey|Hi|Yo|Now|Then|Look|Listen|Please|Right|Sure|No|Yes|Yeah|Nah|"
    r"Maybe|Also|And|But|Oh|Today|Tomorrow|Tonight|Tonite|Monday|Tuesday|Wednesday|Thursday|Friday|"
    r"Saturday|Sunday|Anticipy)\b)"
    r"[A-Z][a-z'’.\-]+\s+(?:can|could|would|will|won'?t|do|are|is)\s+(?:you|u|ya)\b",
    # NOT re.I — the capital is the proper-name signal that stands in for the missing comma.
)
# Name-vocative + a PAST/PERFECT or copular interrogative aimed at that person ("Alex, did the client
# call get rescheduled?", "Sarah, is the report done?", "Mom, have you eaten?") — a question ABOUT
# something put to a named third party, which the present/future REQUEST form above doesn't catch. The
# OWNER-INCLUSIVE guard (?! we|i|us) keeps "Frankly, can we move the meeting?" / "Honestly, do I need
# this?" as the owner's, and an owner-imperative "Mom, remind me ..." has no interrogative aux here.
_DAQ_OPENER_FILLER = (r"honestly|frankly|seriously|actually|basically|literally|truthfully|"
                      r"realistically|obviously|clearly|apparently")
_DIRECT_ADDRESS_Q_COMMA2 = re.compile(
    r"^\s*(?!(?:" + _DAQ_FILLER + r"|" + _DAQ_OPENER_FILLER + r")\b)"
    r"[a-z][a-z'’.\-]*,\s+(?:did|didn'?t|do|does|has|have|had|was|were|is|are|can|could|would|will|won'?t)\b"
    r"(?!\s+(?:we|i|us)\b)",
    re.I,
)
_INTIMATE_DIRECT_ADDRESS_Q = re.compile(
    r"^\s*(?:(?:hey|hi|yo|um|uh),?\s+|please\s+)?"
    r"(?:babe|baby|hon|honey|sweetie|sweetheart|love|dude|bro|buddy|man)\s*,?\s+"
    r"(?:can|could|would|will|won'?t|do|are|is)\s+(?:you|u|ya)\b",
    re.I,
)
# A request-to-you that ENDS with a name vocative ("Could you remind me what time the flight lands,
# James?") is that person's question, not the owner's. The trailing ", Name?" is the aside signal; a
# bare "could you remind me ...?" (no trailing name) stays a real request to the assistant.
_END_VOCATIVE_Q = re.compile(
    # request-to-you (case-insensitive) ... , Capitalized-Name? (name stays case-SENSITIVE — the
    # capital is the proper-name signal, so a trailing ", now?" / ", right?" does NOT match).
    r"(?i:\b(?:can|could|would|will|won'?t)\s+(?:you|u|ya)\b).*,\s*[A-Z][a-z'’\-]{1,}\s*\??\s*$",
)


def _is_directed_question_to_named_person(text: str) -> bool:
    """True for a present/future question addressed to a NAMED third party ("Jordan, can you pull the
    freight numbers?", "Sam can you take the handoff?", "Marcus, can you grab my prescription?") — their
    task, not the owner's, so it must stay silent. A bare request to the assistant ("can you remind me
    ...?") has no name vocative and never matches."""
    t = (text or "").strip()
    return (bool(_DIRECT_ADDRESS_Q_COMMA.match(t)) or bool(_DIRECT_ADDRESS_Q_NOCOMMA.match(t))
            or bool(_DIRECT_ADDRESS_Q_COMMA2.match(t)) or bool(_INTIMATE_DIRECT_ADDRESS_Q.match(t)))


# A vent-adjacent task survives the cardinal vent floor ONLY if the assistant can actually act on it:
# a delegatable/digital directed verb, a pickup/errand, or a money move (so money can still BLOCK). A
# physical chore or bare complaint-noun ("do three loads of laundry", "clean the house") has none and is
# dropped (silent). Bare "do"/"get" are deliberately excluded (too broad) to avoid keeping non-tasks.
_VENT_TASK_ACTIONABLE = re.compile(
    r"\b(send|sent|email|e-mail|text|call|phone|message|msg|ping|reach|contact|draft|write|reply|"
    r"respond|forward|book|schedule|reschedule|cancel|rebook|order|cart|buy|purchase|pay|wire|"
    r"transfer|refund|reimburse|venmo|zelle|remind|look\s*up|research|find|confirm|register|"
    r"sign\s*up|submit|file|renew|rsvp|invite|share|upload|download|set\s*up|"
    r"pick\s*up|pickup|drop\s*off|grab)\b", re.I)
_OVERWHELM_HEAT = re.compile(
    r"\b(?:my\s+brain\s+is\s+fried|brain'?s\s+fried|i'?m\s+fried|i\s+am\s+fried|"
    r"i'?m\s+(?:exhausted|spent|overwhelmed|drowning|running\s+on\s+(?:empty|fumes)|"
    r"losing\s+it|so\s+done)|i\s+can'?t\s+even)\b",
    re.I,
)
_BRAINSTORM_OR_OPTION_NOISE = re.compile(
    r"\b(?:what\s+if|we\s+could|could\s+also|or\s+maybe|maybe\s+we|one\s+way|"
    r"another\s+option|it'?s\s+an\s+option|just\s+(?:thinking|brainstorming|musing|riffing)|"
    r"throwing\s+ideas|lots\s+to\s+chew|noodle\s+on\s+it|need\s+to\s+noodle)\b"
    r"|\bschedule\s+(?:a\s+)?follow-?up\b[\w\s,.'’-]{0,80}?"
    r"\bdecide\s+on\s+(?:one\s+of\s+these|which\s+one|the\s+option|an\s+option|options?)\b",
    re.I,
)
_SOCIAL_PLEASANTRY_NOISE = re.compile(
    r"\bgrab\s+(?:coffee|lunch|dinner|drinks)\b[\w\s,.'’-]{0,80}?"
    r"\b(?:sometime|some\s+time|soon|one\s+day|when\s+things\s+calm\s+down)\b"
    r"|\bwe\s+should\s+totally\b[\w\s,.'’-]{0,80}?"
    r"\b(?:sometime|some\s+time|soon|one\s+day|when\s+things\s+calm\s+down)\b",
    re.I,
)
_LOOSE_PARENT_OUTING_NOISE = re.compile(
    r"\bwe\s+were\s+just\s+saying\b[\w\s,.'’-]{0,80}?"
    r"\bneed\s+to\s+get\s+(?:them|the\s+kids|kids|children)\b[\w\s,.'’-]{0,60}?"
    r"\b(?:park|outside|outdoors|out\s+of\s+the\s+house)\b[\w\s,.'’-]{0,40}?\blater\b",
    re.I,
)

# REVERSIBLE PREPARE tasks the moat under-extracts: "draft an email to X but don't send it", "compose
# a reply, hold it for me", "start a draft reminder", "get a cart together for 200 menus, don't order
# yet". The 20-life test caught 6 of these DROPPED entirely — the model returned actionable=[] (the
# "don't send/order" reads as no-action), the line fell to the thin-read fallback WITHOUT moat_task, so
# the moat-rescue never fired and the deterministic shaper inconsistently returned None. These are real,
# reversible owner deliverables (prepare a draft / a cart, never auto-send/buy). Recognizing them
# deterministically marks the line moat_task so it always surfaces as a confirm-first task, never lost.
_DRAFT_PREP = re.compile(
    r"\b(?:draft|compose|write\s*up|write|prepare|put\s*together|start|queue(?:\s*up)?)\b[^.;!?]{0,45}?"
    r"\b(?:email|e-mail|note|message|text|reply|letter|memo|response|draft|reminder|thank-?you)\b",
    re.I)
# READ-ONLY SAVE/CAPTURE — "save this article to read later", "bookmark the page", "save the recipe",
# "add this link to my reading list". A reversible, side-effect-free capture (like a lookup); a frequent
# silent drop. Tight: requires a save/bookmark/archive verb + a content/reference object or a save-later
# phrase, so ordinary "save me a seat" / "save money" (no content object) does NOT match.
_SAVE_CONTENT = re.compile(
    r"\b(?:save|bookmark|archive|clip)\b[^.;!?]{0,45}?"
    r"\b(?:article|link|page|video|post|recipe|thread|story|paper|pdf|read(?:ing)?\s*list|"
    r"to\s+read|for\s+later|to\s+my\s+(?:list|library|reading)|bookmarks?)\b"
    r"|\badd\b[^.;!?]{0,30}?\bto\s+(?:my\s+)?(?:reading\s*list|bookmarks?|saved|watch\s*list)\b",
    re.I)
_CART_PREP = re.compile(
    r"\b(?:start|set\s*up|get|build|fill|prep|line\s*up|put\s*together)\s+(?:a|an|the)\s+cart\b"
    r"|\badd\s+(?:.{0,30}?\s+)?to\s+(?:the\s+|my\s+)?cart\b"
    r"|\bput\s+[^.;!?]{0,30}?\b(?:in|into)\s+(?:the|my)\s+cart\b"
    r"|\b(?:order|reorder|add)\s+[^.;!?]{0,40}?\binto\s+(?:the|my)\s+cart\b"
    r"|\binto\s+(?:the|my)\s+cart\b"
    r"|\bcart\b[^.;!?]{0,45}?\b(?:do ?n'?t|do not)\s+(?:check\s*out|buy|order|purchase)\b"
    # "order/buy/reorder X ... don't (actually) check out / buy / pay yet" — a cart-without-checkout
    # even when the word 'cart' is absent ("order a replacement stand, but don't actually check out").
    r"|\b(?:order|reorder|buy|purchase|add)\b[^.;!?]{0,70}?\b(?:do ?n'?t|do not)\s+(?:actually\s+)?(?:check\s*out|buy|order|purchase|pay)\b"
    r"|\bline\s+up\s+an?\s+order\b|\bprep\s+an?\s+order\b",
    re.I)

# A "do X on a real logged-in SITE/account" task — the centerpiece browser action (e.g. "return that
# security camera on Amazon", "cancel my order on DoorDash", "go to my Amazon and start a return"). It
# MUST drive the BROWSER hand on the user's real Chrome (browser-only; never the API arm), and never get
# dropped. SAFETY ANCHOR: it only fires when an action verb is tied to a NAMED site/account — via a
# locative "on/at/in/from/through (my|the) <Capitalized-Site>" OR "go to (my) <Site> and ...". The site
# anchor is what stops vent over-match: "return to bed" / "cancel my plans, I'm exhausted" have NO site,
# so they never match. Money is still gated upstream (a buy/pay on a site stays blocked, never auto-driven).
_SITE_ACTION = re.compile(
    r"\b(?:return|cancel|reorder|re-?order|refund|exchange|track|manage|reschedule|rebook|"
    r"start\s+(?:a\s+)?return|get\s+(?:a\s+|the\s+)?(?:return\s+label|refund)|update|change|check\s+on|"
    r"find|look\s*up|reset|download|print|book|renew)\b"
    r"[^.;!?]{0,60}?\b(?:on|at|in|from|through)\s+(?:my\s+|the\s+|our\s+)?"
    r"([A-Z][A-Za-z]+|amazon|ebay|walmart|doordash|uber\s*eats|instacart|costco|target|"
    r"gmail|outlook|paypal|venmo|netflix|spotify|shopify|etsy|best\s*buy)\b"
    r"|\bgo\s+to\s+(?:my\s+|the\s+)?[A-Za-z][A-Za-z.\s]{0,20}?\b(?:and|,|to)\b",
    re.I)
# RETURN / RMA shape that _SITE_ACTION misses: the site name as a NOUN modifier ("get the AMAZON
# return", "deal with my AMAZON return") or a return/refund/exchange of a PURCHASED item ("return the
# cameras I BOUGHT"). Anchored on the SITE noun OR return+"I bought" — never a bare verb — so vents
# ("return to bed", "cancel my plans", "deal with my feelings") never match. Money stays gated by the
# chokepoint's _MONEY_SIGNAL guard.
_RETURN_TASK = re.compile(
    r"\b(?:amazon|walmart|ebay|best\s*buy|costco|target|etsy)\b[^.;!?]{0,40}?"
    r"\b(?:return|refund|exchange|replacement|order|package|delivery|shipment)\b"
    r"|\b(?:return|refund|exchange|replacement|order|package|delivery|shipment)\b[^.;!?]{0,40}?"
    r"\b(?:amazon|walmart|ebay|best\s*buy|costco|target|etsy)\b"
    r"|\b(?:return|refund|exchange|send\s+back)\b[^.;!?]{0,50}?\bI\s+(?:bought|ordered|purchased|got|received)\b",
    re.I)

# A "make a physical artifact and print it" task (a door sign, a notice, a label) — the CREATE + PRINT
# capability: generate the artifact -> prepare the print -> confirm before printing (physical action).
_SIGN_TASK = re.compile(
    r"\b(?:make|create|print|design|put\s*up|stick\s*up|post|hang|tape\s*up|whip\s*up|draw\s*up|"
    r"throw\s*(?:up|together)|need|want)\b"
    r"[^.;!?]{0,45}?\b(?:sign|notice|label|flyer|poster|placard|warning|out[- ]?of[- ]?order)\b",
    re.I)
# A DIGITAL-CHANNEL TARGET (overnight bug-hunt #1): "post a warning IN THE SLACK CHANNEL" / "create a
# label IN GMAIL" are digital requests, not physical signs — they must NOT reach the create+print
# (real-PDF) path. Match the medium ONLY as a LOCATIVE target (in/on/to/into <medium>, or "<app> channel/
# message/...") so a PHYSICAL sign that merely MENTIONS a medium ("put up a sign WITH my email on it")
# still prints. Narrow + additive; never widens what create+print catches.
_DIGITAL_MEDIUM = re.compile(
    r"\b(?:in|on|to|into)\s+(?:the\s+|my\s+|a\s+|our\s+)?"
    r"(?:slack|teams|discord|gmail|e-?mail|inbox|notion|figma|canva|google\s*doc(?:s)?|google\s*sheet(?:s)?|"
    r"web\s*page|web\s*site|website|online|chat|group\s*chat|whats\s*app|the\s+channel|messages?)\b"
    r"|\b(?:slack|teams|discord|gmail|notion|figma|canva)\s+(?:channel|message|post|thread|doc|dm)\b",
    re.I)


def _derive_sign_text(task: str) -> tuple[str, str]:
    """Deterministically derive a real sign headline+sub from the task — the robust fallback when the
    model inference is unreachable/empty/'Notice' (never ship the generic placeholder). Quoted/explicit
    text wins, then a keyword map for common sign types, then the object noun. Pure-local, no model."""
    low = re.sub(r"[-_]", " ", (task or "").lower())
    m = re.search(r"['\"“‘]([^'\"”’]{2,40})['\"”’]", task or "")
    if not m:
        m = re.search(r"\b(?:that\s+says|saying|that\s+reads|reads|says)\s+([A-Za-z0-9 ,'!?\-]{2,40})",
                      task or "", re.I)
    if m:
        return (m.group(1).strip().rstrip(".").title()[:40] or ""), ""
    for pat, head, sub in (
        (r"out[- ]?of[- ]?order|not working|out of service|\bbroken?\b|busted", "Out of Order", "Please use the other one"),
        (r"no\s*parking", "No Parking", "Thank you"),
        (r"wet\s*floor", "Caution: Wet Floor", "Watch your step"),
        (r"wet\s*paint", "Wet Paint", "Do not touch"),
        (r"beware.*dog|dog.*(?:loose|bite)", "Beware of Dog", ""),
        (r"do not disturb|quiet\s*please|keep\s*quiet|be\s*quiet", "Quiet Please", ""),
        (r"reserved\s*(?:parking|spot)", "Reserved Parking", ""),
        (r"garage\s*sale|yard\s*sale", "Garage Sale", ""),
        (r"bake\s*sale", "Bake Sale", ""),
        (r"lost\s*(?:cat|dog|pet)", "Lost Pet", "Please call if found"),
        (r"for\s*sale", "For Sale", ""),
        (r"\bclosed\b", "Closed", ""),
        (r"recycl", "Recycling", ""),
        (r"keep\s*(?:out|off)|do not enter|no entry", "Keep Out", ""),
    ):
        if re.search(pat, low):
            return head, sub
    mb = re.search(r"back in (\w+)\s*min", low)
    if mb:
        return f"Back in {mb.group(1).title()} Minutes", ""
    m = re.search(r"\b(?:sign|notice|label|flyer|poster)\s+(?:for|about|that says|saying|re)\s+"
                  r"(?:the\s+)?([a-z0-9 '\-]{2,30})", low)
    if m:
        return (m.group(1).strip().title()[:40] or ""), ""
    return "", ""


def _is_draft_or_cart_prep(text: str) -> bool:
    """A reversible PREPARE task (draft a message / build a cart) — must surface as a confirm-first
    card, never dropped. The 'don't send/order yet' clause is a constraint, not a cancellation."""
    t = text or ""
    return bool(_DRAFT_PREP.search(t)) or bool(_CART_PREP.search(t))


# EXPLICIT REMINDER / CALENDAR-HOLD shapes — "remind me to X", "set a reminder to X", "block my calendar
# Friday 9am", "block 2pm for the walkthrough", "hold time Saturday 2pm", "put it on my list", "don't let
# me forget X", "add X to my calendar". The 20-life re-run found ~40 of these DROPPED entirely (the moat /
# spine non-deterministically returned nothing for an explicit, unambiguous reversible reminder/hold —
# the worst kind of miss for a "never forget anything" assistant). These are the safest possible tasks
# (a calendar hold or a tracked reminder, always shown first), so an explicit one must ALWAYS surface —
# deterministically, never at the model's coin-flip. NOT a question to someone else (those are silenced
# upstream), NOT money. Tight enough that ordinary prose ("I blocked out some time to think") needs a
# real time/list/forget anchor to match.
# Optional time/when phrase that real speech wedges between the reminder verb and 'to' — "remind me
# SUNDAY NIGHT to ...", "set a reminder FOR FRIDAY to ...", "add a reminder AT 2PM to ...".
_RH_WHEN = (r"(?:\s+(?:for|at|on|by|this|next|tonight|tomorrow|today|in|sunday|monday|tuesday|wednesday|"
            r"thursday|friday|saturday|morning|afternoon|evening|night)[^,.;!?]{0,22}?)?")
_REMINDER_OR_HOLD = re.compile(
    r"(?:\bremind me" + _RH_WHEN + r"\s+(?:to|that|about|of)\b|"        # remind me [Sunday night] to ...
    r"\bpencil\s+in\b|\bpenciled\s+in\b|"                              # "pencil in the dentist next month"
    r"\b(?:set|add)\s+(?:a |an |myself a )?reminder" + _RH_WHEN + r"\s+(?:to|that|about|for)\b|"
    r"\breminder" + _RH_WHEN + r"\s+to\b|\bset (?:a |myself a )?reminder\b|"
    r"\b(?:do ?n'?t|do not) (?:let me )?forget\b|"                     # don't / do not (let me) forget
    r"\b(?:do ?n'?t|do not) (?:let me )?lose (?:track|sight)\b|"       # don't (let me) lose track/sight of
    r"\bkeep track of\b|\bnail (?:that|this|it|down)\b|"               # keep track of / nail that down
    r"\bput it on my (?:list|calendar)\b|\bput .{0,30}? on (?:my|the) (?:list|calendar)\b|"
    r"\badd .{0,40}? to (?:my |the )?calendar\b|"
    r"\bmake sure .{0,40}? on (?:my|the) calendar\b|"
    r"\b(?:set|put) (?:up )?a hold\b|"                                 # set/put a hold on the calendar
    r"\b(?:want|need|put) a (?:calendar )?hold\b|"                     # "want a calendar hold for Thursday 9am"
    r"\bblock (?:off )?(?:me |my |the )?(?:calendar|time|an? hour|"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|several|a couple of|a few)\s?(?:hours?|hrs?|min(?:ute)?s?))\b|"
    r"\bblock (?:off )?\d{1,2}(?::\d{2})?\s?(?:am|pm)?\b|"             # block 2pm
    r"\bhold (?:time|\d{1,2}(?::\d{2})?\s?(?:am|pm))\b)",              # hold 2pm / hold time
    re.I)
# Read-only LOOKUP imperatives — "pull (up) X", "look up X", "look into X", "find out X", "check
# whether/if X". Always safe to surface (no side effect), and a frequent drop in dense vent-heavy days.
_LOOKUP = re.compile(
    r"\b(?:look up|look into|find out|dig up|pull up)\b"                # unambiguous lookup phrasal verbs
    r"|\bpull\b[^.;!?]{0,30}?\b(?:numbers?|figures?|report|rate|rates|price|cost|data|stats?|"
    r"statement|statements|balance|invoice|status|breakdown|comps?|history|record|records|details?|"
    r"quarter|last\s+(?:quarter|month|year)|cap\s+table|metrics?|list)\b"  # bare "pull last quarter's numbers"
    r"|\bcheck\s+(?:whether|if|when|how|what)\b",                        # "check whether the deploy went green"
    re.I)


def _is_reminder_or_hold(text: str) -> bool:
    """An explicit reminder or calendar-hold the assistant must never silently drop — a reversible,
    always-shown-first task. "remind me to/that/about ...", "block my calendar", "block 2pm for ...",
    "hold time Sat 2pm", "put it on my list", "don't (let me) forget / lose track of ...", "nail that
    down", "set a hold", "make sure ... on my calendar", "add ... to calendar"."""
    return bool(_REMINDER_OR_HOLD.search(text or ""))


# A money ACTION = a real money signal (amount / account / transfer-to / debt noun) AND a spend/move
# VERB. This is STRICTER than the harm "money" CATEGORY (which also fires on bare money NOUNS like
# "invoice"/"payment"/"fee" that are benign in "log the payment in the CRM" / "review the invoice").
# The absolute spine money-block keys off THIS so it force-blocks real money moves (wire $400, pay
# $14,200) without over-blocking benign money-noun mentions (which keep their nuanced carve-outs:
# internal-note, cart-no-buy, invoice-draft).
_MONEY_ACTION_VERB = re.compile(
    r"\b(?:pay|paid|pays|paying|wire|wired|wiring|transfer|transferred|transferring|send|sent|sending|"
    r"refund|reimburse|credit|deposit|withdraw|venmo|zelle|cashapp|cash\s?app|paypal|charge|charged|"
    r"remit|buy|buying|bought|purchase|purchasing|spend|spending|renew|renewing)\b", re.I)


def _is_money_action(text: str) -> bool:
    """A real money MOVE — a money signal plus a spend/transfer verb — which must always be blocked."""
    t = text or ""
    return bool(_MONEY_SIGNAL.search(t)) and bool(_MONEY_ACTION_VERB.search(t))


_TASK_PREFIX = re.compile(
    r"^\s*(?:please\s+|just\s+|actually\s+|also\s+|oh\s+|and\s+)*"
    r"(?:"
    # reminder framings, allowing an optional time/when phrase before 'to' ("set a reminder for Friday
    # to ...", "remind me Sunday night to ...", "add a reminder for 2pm to ...")
    r"(?:(?:set|add)\s+(?:a |an |myself a )?reminder|reminder|remind me)"
    r"(?:\s+(?:for|at|on|by|this|next|tonight|tomorrow|today|in|sunday|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|morning|afternoon|evening|night)[^,.;!?]{0,22}?)?\s+(?:to|that|about)"
    r"|need(?:ing)? to remember to|need to remember to|remember to|need to|have to"
    r"|make sure to|don'?t forget to|i should(?: really)?|i gotta|i need to|gotta|i'?ll|i will"
    r")\s+",
    re.I)


def _task_key(text: str) -> frozenset:
    """A normalized identity for a task: strip reminder/intention PREFIXES ('remind me to', 'need to
    remember to', 'set a reminder to', "I'll") then take the salient tokens. So "update the cap table",
    "remind me to update the cap table", and "Need to remember to update the cap table" all share ONE
    key — killing the duplicate-spam where the whole-day model emits both the reminder and its action."""
    t = text or ""
    for _ in range(4):     # peel stacked prefixes ("need to remember to ...")
        nt = _TASK_PREFIX.sub("", t, count=1)
        if nt == t:
            break
        t = nt
    return frozenset(w for w in re.findall(r"[a-z0-9]+", t.lower())
                     if len(w) > 2 and w not in _TASK_STOPWORDS)


_TASK_STOPWORDS = frozenset({
    "the", "and", "for", "you", "your", "this", "that", "with", "out", "off", "get", "got", "have",
    "her", "his", "him", "them", "they", "she", "are", "was", "were", "but", "not", "any", "all",
    "before", "after", "today", "tomorrow", "tonight", "week", "month", "morning", "night", "soon",
})


def _is_explicit_reversible_task(text: str) -> bool:
    """The union of high-confidence, reversible task imperatives that must NEVER be silently dropped,
    even when a nearby vent line contaminates the model's per-line read: reminders/holds, read-only
    lookups, and draft/cart prep. Surfacing one is at worst a benign confirm-first ask; dropping it is
    the cardinal 'you keep dropping my tasks' failure. (Money is still blocked at the spine; genuine
    third-party questions are silenced upstream before this is reached.)"""
    t = text or ""
    return (_is_reminder_or_hold(t) or _is_draft_or_cart_prep(t) or bool(_LOOKUP.search(t))
            or bool(_SAVE_CONTENT.search(t)))


def _is_interrogative_aside(text: str) -> bool:
    # A "did/have you ..." completion-check aimed at the listener is silent whether or not the
    # spoken line kept its question mark ("hey did you remind Jenny to send the slides at 4 like
    # I asked" has none) — plus any start-anchored interrogative, plus a present/future question
    # addressed to a NAMED third party ("Jordan, can you ...?"). Present-tense requests to the
    # assistant ("can you remind me ...") never match (no name vocative / owner is beneficiary).
    t = (text or "").strip()
    return (bool(_INTERROGATIVE_ASIDE.match(t)) or bool(_QUESTION_TO_OTHER.search(t))
            or bool(_END_VOCATIVE_Q.search(t))
            or _is_directed_question_to_named_person(t))


def _deterministic_vent_adjacent_tasks(text: str) -> list[str]:
    """No-model fallback for the source-of-truth rule:

    Pure vent/sarcasm stays silent; a concrete assistant-doable task voiced
    inside emotion is held as confirm-first work. This only runs when the model
    extractor is unavailable, so it is deliberately narrow and action-verb based.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        from ..live_memory.review_infer import is_vent, is_vent_shape
        if not (is_vent(raw) or is_vent_shape(raw) or _OVERWHELM_HEAT.search(raw)):
            return []
    except Exception:
        if not _OVERWHELM_HEAT.search(raw):
            return []
    if _is_interrogative_aside(raw) or _is_directed_question_to_named_person(raw):
        return []
    try:
        from ..owner_mode import _split_multi_action
    except Exception:
        _split_multi_action = lambda s: [s]  # type: ignore[assignment]
    # RETRACTION FLOOR (clause-scoped): a task the owner took back in the same breath
    # ("schedule the meeting... no, hold off on that", "book the flight, scratch that") must
    # never be resurrected as a held task here — the vent-split would otherwise keep the
    # pre-retraction command and drop the retraction. clause_is_retracted silences ONLY the
    # cancelled clause, so a sibling command survives.
    try:
        from ..live_memory.review_infer import clause_is_retracted
    except Exception:
        clause_is_retracted = lambda task, full: False  # type: ignore[assignment]

    chunks = [c.strip(" \t,;:-") for c in re.split(r"[.;!?]+|,", raw) if c.strip(" \t,;:-")]
    out: list[str] = []
    for chunk in chunks:
        if not _VENT_TASK_ACTIONABLE.search(chunk):
            continue
        if _is_interrogative_aside(chunk) or _is_directed_question_to_named_person(chunk):
            continue
        if clause_is_retracted(chunk, raw):
            continue
        for clause in _split_multi_action(chunk):
            task = str(clause or "").strip(" \t,;:-")
            if task and _VENT_TASK_ACTIONABLE.search(task) and not clause_is_retracted(task, raw):
                out.append(task)
    deduped: list[str] = []
    for task in out:
        key = re.sub(r"\s+", " ", task.lower())
        if key not in {re.sub(r"\s+", " ", x.lower()) for x in deduped}:
            deduped.append(task)
    return deduped[:6]


def _is_noncommittal_noise(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    return bool(
        _BRAINSTORM_OR_OPTION_NOISE.search(raw)
        or _SOCIAL_PLEASANTRY_NOISE.search(raw)
        or _LOOSE_PARENT_OUTING_NOISE.search(raw)
    )


def _parse_iso_dt_local(value):
    """Parse an RFC3339/ISO-8601 datetime to a tz-aware UTC datetime; None if unparseable.

    Used to time-window a real calendar read for the onboarding profile. A naive value is
    treated as UTC. Anything that isn't a parseable string yields None (and so is dropped, not
    guessed) — the anti-fabrication discipline applies even to a single bad timestamp."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _iter_message_lists(value):
    """Yield each list-of-messages found one level into a Gmail read result.

    Gmail.ListThreads / ListEmails wrap their rows under a key like 'threads' / 'emails' /
    'messages'. We yield any top-level list value so the parser stays robust to the exact key
    without inventing structure. Non-dict input yields nothing."""
    if not isinstance(value, dict):
        return
    for v in value.values():
        if isinstance(v, list):
            yield v


def _gmail_counterparty(item) -> str:
    """Best-effort sender/correspondent address from a Gmail thread/email row, or "" if absent.

    Reads only fields Gmail actually returns ('from'/'sender'/'from_email'); never fabricates a
    name. Empty string when the row carries no usable address — that row then contributes no
    correspondent fact."""
    if not isinstance(item, dict):
        return ""
    for key in ("from", "sender", "from_email", "fromAddress", "from_address"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, dict):
            addr = val.get("email") or val.get("address")
            if isinstance(addr, str) and addr.strip():
                return addr.strip()
    return ""


def _split_addr(raw):
    """Split a 'Display Name <email>' (or a bare email) into (display, email_lower). Best-effort;
    NEVER fabricates — returns ('', '') for anything without a usable address."""
    if not isinstance(raw, str):
        return "", ""
    s = raw.strip()
    m = re.search(r"<([^>]+)>", s)
    if m:
        email = m.group(1).strip().lower()
        disp = s[: m.start()].strip().strip('"').strip()
        return disp, email
    if "@" in s:
        return "", s.strip().lower()
    return s.strip(), ""


def _name_from_email(email: str) -> str:
    """A human-ish name from an email local part ('jane.doe@x' -> 'Jane Doe'), falling back to the
    raw email. Only title-cases what the owner can see and edit — invents no identity."""
    if not isinstance(email, str) or "@" not in email:
        return email or ""
    local = email.split("@", 1)[0]
    parts = [p for p in re.split(r"[._\-]+", local) if p]
    pretty = " ".join(p.capitalize() for p in parts)
    return pretty or email


def _card_step_receipts(steps: list[dict]) -> list[dict]:
    """Human-readable receipts extracted from executed goal steps."""
    receipts: list[dict] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        args = step.get("args") or {}
        if not isinstance(args, dict):
            continue
        resolution = args.get("memory_resolution")
        if isinstance(resolution, dict):
            receipts.append({
                "type": "memory_resolution",
                "site": resolution.get("site"),
                "item": resolution.get("item"),
                "source_ref": resolution.get("source_ref"),
                "matched_hints": resolution.get("matched_hints") or [],
            })
        if step.get("intent") == "browse_task":
            result = step.get("result") or {}
            proof = result.get("proof") or {}
            output = result.get("output") or {}
            if isinstance(result, dict) and result.get("status") == "success" and isinstance(proof, dict):
                receipts.append({
                    "type": "browser_receipt",
                    "url": output.get("final_url") or proof.get("url") or args.get("url"),
                    "answer": output.get("answer") or "",
                    "screenshot": bool(proof.get("screenshot")),
                })
    return receipts


def _steps_create_open_loop(steps: list[dict]) -> bool:
    for step in steps:
        if not isinstance(step, dict) or step.get("intent") != "write_memory":
            continue
        args = step.get("args") or {}
        if isinstance(args, dict) and args.get("kind") == "open_loop":
            return True
    return False


def _status_for_open_loop(state: str) -> str:
    return "waiting" if state == "waiting" else "open" if state == "open" else state


def _owner_card_dedupe_key(card: OwnerTaskCard) -> str:
    """Stable replay key for the same owner utterance and shaped action.

    Pressing Go twice, replaying a listening transcript, or uploading the same
    transcript must not create a second external action or approval ask. Exact
    source text is deliberately part of the key: a materially different phrasing
    gets a fresh card, while an accidental replay lands on the durable record.
    """
    raw = "|".join([
        re.sub(r"\s+", " ", (card.source_text or "").strip().lower()),
        card.route,
        card.action,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


# --- Semantic obligation consolidation (F-012: one real-world obligation = one card) -------------
# The moat can extract the SAME obligation from several lines — a relayed request ("Mom: call Amazon
# about the plant") plus the speaker's confirmation ("Yeah, I'll handle it" -> "handle the Amazon
# plant order") plus a reworded variant. Exact-text dedupe (_owner_card_dedupe_key) can't see these
# as the same. We collapse on an OBJECT SIGNATURE: drop filler + pronouns + time + generic light
# verbs, keep the entity/object tokens (crudely singularized). Two tasks are the same obligation when
# one object-signature CONTAINS the other (so "amazon plant" == "amazon plant order"), which merges
# the dup forms WITHOUT merging genuinely different objects ("Sarah budget" vs "Sarah deck").
_OBLIGATION_STOP = {
    # articles / pronouns / determiners
    "a", "an", "the", "this", "that", "these", "those", "it", "its", "i", "im", "me", "my", "mine",
    "you", "your", "yours", "he", "him", "his", "she", "her", "hers", "they", "them", "their",
    "we", "us", "our", "one", "some", "any",
    # prepositions / conjunctions
    "to", "for", "of", "on", "in", "at", "by", "with", "about", "from", "into", "over", "before",
    "after", "and", "or", "but", "so", "as", "up", "out", "off", "down", "re",
    # auxiliaries / modals / politeness / filler
    "is", "are", "was", "were", "be", "been", "am", "do", "does", "did", "will", "would", "can",
    "could", "should", "shall", "may", "might", "must", "please", "yeah", "yes", "yep", "ok", "okay",
    "sure", "just", "really", "gotta", "gonna", "wanna", "need", "needs", "got", "get", "gets",
    "getting", "let", "lets", "make", "makes", "making", "want", "wants", "okayy", "hey", "hi",
    "thanks", "pls", "confirm", "task", "owner",
    # generic light action verbs (the OBJECT identifies the obligation, not the verb)
    "handle", "handled", "deal", "dealt", "sort", "sorted", "take", "takes", "taking", "care",
    "look", "looks", "looking", "manage", "managed", "remember", "remind", "reminded", "set", "put",
    "go", "going", "keep", "kept", "ensure", "check",
    # time words
    "today", "tomorrow", "tonight", "now", "later", "soon", "morning", "afternoon", "evening",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "week", "weekend",
    "am", "pm",
}


def _obligation_sig(text: str) -> frozenset:
    """Object signature of a task: the entity/object tokens, filler+verbs+time stripped, crudely
    singularized. Empty when the task is too thin to key on (then it is never auto-merged)."""
    sig = set()
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if tok in _OBLIGATION_STOP:
            continue
        if len(tok) <= 2 and not tok.isdigit():
            continue
        if len(tok) > 4:  # crude stem so plurals/tenses match: ordered->order, plants->plant
            tok = re.sub(r"(ings|ing|ed|es|s)$", "", tok)
        sig.add(tok)
    return frozenset(sig)


# Generic verbs/nouns that name HOW (communication channel) or a vague WHAT, never the obligation's
# identity. Two obligations that differ ONLY by these tokens are the SAME real obligation: the moat
# rewords a backchannel confirmation ("yeah, I'll handle it") into a synonym of the original task
# ("call Amazon about the monitor" -> "handle the Amazon monitor issue"); the identity that survives is
# the salient entity+object {amazon, monitor}, so {amazon,call,monitor} and {amazon,issue,monitor} must
# collapse to one card (anti-spam, Omar's #1). Stored in STEMMED form (matching _obligation_sig's stem)
# and kept DELIBERATELY small + concrete so genuinely different objects (monitor vs desk) never merge.
_OBLIGATION_GENERIC = {
    "call", "email", "text", "contact", "ping", "reach", "phone", "ring",
    "message", "messag", "msg", "send", "sent", "deliver", "share",
    "issue", "problem", "matter", "regard", "situation", "stuff",
}


def _obligation_core(sig: frozenset) -> frozenset:
    """The identity tokens of an obligation: salient entity/object only, with generic communication
    verbs + filler problem-nouns removed. {amazon,call,monitor} and {amazon,issue,monitor} both -> {amazon,monitor}."""
    return frozenset(t for t in sig if t not in _OBLIGATION_GENERIC)


def _same_obligation(a: frozenset, b: frozenset) -> bool:
    """Same real-world obligation when both signatures are non-empty and ANY of:
    - one SIGNATURE contains the other ("amazon plant" == "amazon plant order"); OR
    - their identity CORES are equal ("call Amazon about the monitor" == "handle the Amazon monitor
      issue" -> both core {amazon, monitor}); OR
    - the smaller core (an OBJECT-bearing core, >=2 salient tokens) is fully contained in the other —
      a reminder/followup about the SAME deliverable folds into its thread ("get Sam the revised deck"
      core {sam,revised,deck} swallows "remind me before I send the revised deck" core {revised,deck}).
      The >=2 floor stops a bare person-only core ({sam}) from over-merging two distinct tasks."""
    if not a or not b:
        return False
    if a <= b or b <= a:
        return True
    ca, cb = _obligation_core(a), _obligation_core(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    small, big = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    return len(small) >= 2 and small <= big


class GatedApprover(Approver):
    """Human-path stub that also propagates the gate's approval flag onto the
    step args only after the owner has approved. Product core uses this as a
    lower safety rail: a planner-level high-risk step cannot auto-approve itself
    just because the top-level proactive gate thought the request was safe."""

    def __init__(self, approve: bool = False) -> None:
        self._approve = approve

    async def approve(self, goal, step) -> bool:
        if step.args.get("approved") is True:
            return True
        if (goal.proof or {}).get("owner_approved") is True:
            step.args["approved"] = True
            return True
        if self._approve:
            step.args["approved"] = True
        return self._approve


class ControlCore:
    def __init__(self, data_dir=None, user_id=None) -> None:
        load_local_env()  # make .env.local keys (Arcade, etc.) available
        base = _base(data_dir)
        self.data_dir = base
        # WHO this core belongs to. The registry injects the signed-in Supabase user id for a
        # per-user core; the DEFAULT/owner core is built with no user_id (-> None here), keeping
        # the owner's action identity on the ARCADE_USER_ID/ADMIN_EMAIL fallback below.
        self.user_id = (user_id or "").strip() or None
        # M3: the user-facing autonomy DIAL (Full-Send/Regular/Limited) + per-task-type trust ledger.
        from ..proactive.autonomy_mode import TrustLedger, DEFAULT_MODE
        self.trust_ledger = TrustLedger(base / "trust_ledger.json")
        from ..onboarding.permissions import Permissions as _OnbPerms
        self.onboard_permissions = _OnbPerms(base / "onboard_permissions.json")
        from ..agent.resume_store import ResumeStore as _ResumeStore
        self.resume_store = _ResumeStore(base / "resume_state.json")
        self._autonomy_mode_path = base / "autonomy_mode.txt"
        try:
            self._autonomy_mode = (self._autonomy_mode_path.read_text(encoding="utf-8").strip()
                                   or DEFAULT_MODE)
        except Exception:
            self._autonomy_mode = DEFAULT_MODE
        self.browser_link = BrowserLink()
        # The WS token must survive an engine restart/redeploy: the extension stores it at
        # pair time and reconnects with it forever after. A fresh random token on every boot
        # silently unpaired every Chrome (403 storm) until the user clicked Pair again.
        try:
            _tok_path = base / "browser_link_token"
            _tok_path.parent.mkdir(parents=True, exist_ok=True)
            if _tok_path.exists():
                _saved = _tok_path.read_text().strip()
                if _saved:
                    self.browser_link.token = _saved
            else:
                _tok_path.write_text(self.browser_link.token)
        except Exception:
            pass
        self.glassbox = GlassBox(base / "glassbox.jsonl")
        self.scorecard = Scorecard(base / "scorecard.jsonl")
        self.bus = Bus(glassbox=self.glassbox)
        self.gateway = ModelGateway(endpoint=os.environ.get("ANTICIPY_MODEL_ENDPOINT"))

        # REAL memory: four drawers + the live memory agent, on the frozen contract.
        self.memory = Memory(data_dir=base)
        self.live_memory = LiveMemoryBrain(self.memory, gateway=self.gateway, scorecard=self.scorecard)
        # PHASE 3 (learns-you): the context engine sits behind the live_memory facade and wires into
        # intake at two seams — observe() captures stated anchors/people/retractions BEFORE the brain,
        # and resolve_observed() rewrites task lines with what we already know AFTER intent-resolve, so
        # the assistant resolves "my usual"/the right Sam and never re-asks a known fact.
        self.context = _ContextEngine(self.memory, self.gateway) if _ContextEngine is not None else None
        self.owner_mode = OwnerMode()
        self.memory_worker = MemoryWorker(self.live_memory)
        self.gateway_ledger = ProactiveGatewayLedger(base, glassbox=self.glassbox)

        # REAL hands replace connector_stub + browser_stub on the frozen contract.
        # channel_stub (reaching the user: call/text) stays (later chunk).
        hands_mode = os.environ.get("ANTICIPY_HANDS_MODE", MODE_MOCK)
        # ACTION IDENTITY: a per-user core acts under ITS OWN user's identity, so a user's
        # real-systems actions never run as the owner. The DEFAULT/owner core (self.user_id is
        # None) falls back to the signed-in Arcade.dev account ("users only" mode), unchanged.
        user_id = self.user_id or os.environ.get("ARCADE_USER_ID") or os.environ.get("ADMIN_EMAIL", "omar@anticipy.ai")
        # Per-person API mesh (hands/token_vault.py): back the hand with the encrypted
        # per-user token vault so a user who connected their OWN app (Gmail, a niche CRM
        # like Cosmolex) authenticates with THEIR short-lived token, not the shared
        # ARCADE_API_KEY. No connected app / absent ANTICIPY_VAULT_KEY -> safe fallback to
        # the shared key (back-compat), never a fake token. The broker is plain Python the
        # model cannot reach into; SecretToken redacts the plaintext on every leak path.
        self.token_vault = TokenVault(data_dir=base)
        self.api_hand = ApiHand(user_id=user_id, mode=hands_mode,
                                broker=TokenBroker(self.token_vault))
        agent_gateway = self.gateway if self.gateway.provider == PROVIDER_OPENROUTER else None
        native_bridge = None
        if (os.environ.get("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "1") or "").strip().lower() not in {"0", "false", "no", "off"}:
            native_bridge = NativeBridgeLink()
        self.native_bridge_link = native_bridge
        self.browser_hand = BrowserHand(
            self.browser_link,
            timeout=float(os.environ.get("ANTICIPY_BROWSE_TIMEOUT", "30")),
            gateway=agent_gateway,
            max_steps=int(os.environ.get("ANTICIPY_AGENT_MAX_STEPS", "18")),
            agent_timeout=float(os.environ.get("ANTICIPY_AGENT_TIMEOUT", "240")),
            notifier=self.notify_user,
            fallback_link=native_bridge,
            # Same env discipline as ApiHand: mock default, live only explicit.
            # ANTICIPY_BROWSER_HAND_MODE narrows the knob for integrations that
            # need the real-WS browser leg while the API hand stays mock
            # (scripts/hands_loop.sh); it never widens a live default.
            mode=os.environ.get("ANTICIPY_BROWSER_HAND_MODE") or hands_mode,
        )
        self.channel = ChannelStub()  # send_email only — the real ChannelWorker owns text/call
        # Real channels (mock by default; live only with ANTICIPY_CHANNELS_MODE=live +
        # Twilio env). ONE TextChannel instance shared with the proactive ask path so
        # there is a single .sent audit trail.
        self.text_channel = TextChannel()
        self.call_channel = CallChannel()
        self.channel_worker = ChannelWorker(text=self.text_channel, call=self.call_channel,
                                            contact=self._user_contact)
        # Real workers register LAST so they own any intent a stub also claims; the real
        # MemoryWorker takes over read_context + write_memory, ChannelWorker send_text/call.
        for w in (self.channel, self.api_hand, self.browser_hand, self.memory_worker,
                  self.channel_worker):
            self.bus.register_worker(w)

        self.store = GoalStore(data_dir=base)
        # No-API app intents reroute to the browser hand via the orchestrator's
        # EXISTING reroute path (config, not a code change).
        alternates = {"post_to_x": "browse_task", "create_event": "browse_task", "message": "browse_task"}
        self.orchestrator = Orchestrator(
            self.bus, self.gateway, self.store, glassbox=self.glassbox, scorecard=self.scorecard,
            alternates=alternates, approver=GatedApprover(False), memory_context=self._mem_ctx,
        )
        self.proactive = ProactiveEngine(
            self.bus, self.gateway, self.orchestrator, glassbox=self.glassbox, scorecard=self.scorecard,
            channel=self.text_channel, call_channel=self.call_channel, user_contact=self._user_contact(),
            deferred_path=base / "decider_deferred.json",
            pending_path=base / "pending_asks.json",
        )
        # Owner cards awaiting a YES/NO: goal_id -> {record_path, card_id}, so resolve()
        # can write the resolved goal's outcome back onto the durable card record.
        # In-memory by design — the durable linkage survives in the record's
        # execution.goal_id field and resolve() falls back to scanning for it (F18).
        self._owner_card_goals: dict = {}
        # Per-line press-go locks: approve_remembered's load-check-build-drive must be
        # ATOMIC per line so two concurrent presses of the SAME line cannot both pass the
        # "prior goal not done yet" check and double-fire a real write. Keyed on the stable
        # goal_id derived from line_id; created under _press_go_locks_guard so the registry
        # itself is race-free.
        self._press_go_locks: dict[str, asyncio.Lock] = {}
        self._press_go_locks_guard = asyncio.Lock()

    async def start(self) -> None:
        await self.bus.start()

    async def stop(self) -> None:
        await self.bus.stop()

    def _mem_ctx(self, about: str, purpose: str = "act") -> dict:
        """INJECT seam for the orchestrator's plan: relevant memory for `about`, via the
        ONE ContextPack builder (default purpose 'act' — this feeds the hands' plan)."""
        return self.live_memory.build_context(about, purpose=purpose).as_ctx_dict()

    def _owner_timezone(self) -> tuple[dt.tzinfo, str | None]:
        """Read the owner's onboarded timezone from the PROFILE drawer (the owner_identity
        item carries ``fields['timezone']``, e.g. 'America/New_York').

        Returns (tzinfo, name). When the owner has not onboarded a timezone (or it is not a
        resolvable zone), falls back to the server-local tz so grounding still works — but a
        real onboarded zone makes a press-go calendar hold carry the OWNER's offset, not the
        server's. Read-only; never writes.
        """
        for item in self.memory.profile.all():
            tz_name = str((item.fields or {}).get("timezone") or "").strip()
            if not tz_name:
                continue
            try:
                return ZoneInfo(tz_name), tz_name
            except (ZoneInfoNotFoundError, ValueError, KeyError):
                continue  # malformed onboarded zone -> fall through to server-local
        local = dt.datetime.now().astimezone().tzinfo
        return local, None

    @staticmethod
    def _user_contact() -> str:
        """The owner's reachable number — ONLY in live channel mode. Everywhere else
        (suite, stub/mock persona runs) the placeholder stands, so run artifacts and
        glassbox dumps never carry the real number (B8 fixed engine-side, scoped)."""
        if os.environ.get("ANTICIPY_CHANNELS_MODE") == "live":
            return (os.environ.get("OWNER_PHONE") or os.environ.get("ALERT_PHONE")
                    or os.environ.get("TWILIO_TO") or "+10000000000")
        return "+10000000000"

    @staticmethod
    def _owner_event_enabled() -> bool:
        return (os.environ.get("ANTICIPY_OWNER_INGEST", "") or "").strip().lower() in {"1", "true", "yes", "on"}

    def channel_status(self) -> dict:
        """Public-safe readiness for owner text/call channels.

        This exposes mode and missing setup only; never the phone number or Twilio
        secrets. The send path itself still decides live/mock at call time.
        """
        mode = (os.environ.get("ANTICIPY_CHANNELS_MODE") or "mock").strip().lower()
        twilio_configured = self.text_channel.configured() and self.call_channel.configured()
        owner_contact_configured = bool(
            os.environ.get("OWNER_PHONE") or os.environ.get("ALERT_PHONE") or os.environ.get("TWILIO_TO")
        )
        try:
            inbound_poll_seconds = float(os.environ.get("ANTICIPY_INBOUND_POLL_SECONDS", "15") or 0)
        except ValueError:
            inbound_poll_seconds = 0.0
        if mode != "live":
            status = "ready_to_enable" if twilio_configured and owner_contact_configured else "mock"
            label = (
                "Twilio and owner phone configured; live mode is off"
                if status == "ready_to_enable"
                else "mock"
            )
        elif not twilio_configured:
            status = "missing_twilio"
            label = "missing Twilio credentials"
        elif not owner_contact_configured:
            status = "missing_owner_contact"
            label = "missing owner phone"
        else:
            status = "live_ready"
            label = "live text/call ready"
        if mode != "live":
            inbound_status = status
            inbound_label = label
        elif not twilio_configured:
            inbound_status = "missing_twilio"
            inbound_label = "missing Twilio credentials"
        elif not owner_contact_configured:
            inbound_status = "missing_owner_contact"
            inbound_label = "missing owner phone"
        elif inbound_poll_seconds <= 0:
            inbound_status = "disabled"
            inbound_label = "inbound reply polling disabled"
        else:
            inbound_status = "live_ready"
            inbound_label = "inbound YES/NO replies active"
        if status == "live_ready" and inbound_status != "live_ready":
            label = f"{label}; {inbound_label}"
        return {
            "mode": "live" if mode == "live" else "mock",
            "status": status,
            "label": label,
            "twilio_configured": twilio_configured,
            "owner_contact_configured": owner_contact_configured,
            "text": status,
            "call": status,
            "inbound": {
                "status": inbound_status,
                "label": inbound_label,
                "poll_seconds": inbound_poll_seconds if inbound_poll_seconds > 0 else 0,
            },
        }

    def _sync_owner_loop_status(self, card_id: str, state: str) -> None:
        """Keep the memory ledger aligned with the visible owner card state."""
        status = _status_for_open_loop(state)
        for item in self.memory.open_loops.all():
            if item.fields.get("owner_card_id") != card_id:
                continue
            if item.status == status and item.fields.get("owner_card_state") == state:
                return
            item.status = status
            item.fields = {**item.fields, "owner_card_state": state}
            self.memory.open_loops.update(item)
            return

    def _sync_open_loop_item_status(self, item_id: str, state: str, *, card_id: str | None = None) -> bool:
        item = self.memory.open_loops.get(item_id)
        if item is None:
            return False
        status = _status_for_open_loop(state)
        if item.status == status and item.fields.get("owner_card_state") == state:
            return True
        fields = {**item.fields, "owner_card_state": state}
        if card_id:
            fields["resolved_by_owner_card_id"] = card_id
        item.status = status
        item.fields = fields
        self.memory.open_loops.update(item)
        return True

    def _follow_up_loop_id(self, card) -> str:
        """CONTENT-stable id for the follow-up fire-site loop, so re-ingesting the same obligation
        rewrites the SAME row (INSERT OR REPLACE) — never a duplicate, never a second trigger. Keyed
        on the card's CONTENT (source_text+route+action), NOT the random per-ingest card.id (audit fix:
        the random id made every re-ingest create a fresh 'followup:' row)."""
        if isinstance(card, dict):
            raw = "|".join([
                re.sub(r"\s+", " ", (card.get("source_text") or "").strip().lower()),
                str(card.get("route") or ""), str(card.get("action") or ""),
            ])
            key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
        else:
            key = str(card)   # back-compat: a bare string is used as-is
        return f"followup:{key}"

    def _schedule_follow_up(self, card: dict, plan: dict, now: float) -> dict:
        """FIRE-SITE for follow-ups: turn the computed plan into a durable, fireable open_loop
        carrying remind_ts == when_ts, linked to the originating card id + its proof. The
        existing trigger system (proactive.trigger_tick -> _fire_reminder) then delivers the
        nudge at when_ts over the SAME TextChannel reminders use — no parallel scheduler.

        Returns the (possibly time-corrected) plan to surface on the card so the card and the
        ledger agree. IDEMPOTENT: if a follow-up loop already exists for this card, its
        already-scheduled when_ts is preserved (re-ingest never churns the time), and it is
        only re-armed if it has not yet fired.
        """
        card_id = card.get("id") or ""
        if not card_id:
            return plan
        loop_id = self._follow_up_loop_id(card)
        existing = self.memory.open_loops.get(loop_id)
        if existing is not None:
            # Already scheduled. Preserve the original when_ts (no churn). If it has already
            # fired, do NOT re-arm it — fire-once holds across re-ingests too.
            kept_when = existing.fields.get("remind_ts", plan["when_ts"])
            plan = {**plan, "when_ts": kept_when,
                    "in_days": max(0, round((kept_when - now) / (24 * 3600)))}
            return plan
        task = plan.get("note") or (card.get("source_text") or "Follow up")
        # carry the originating card's proof + id so the fired nudge is provably LINKED to the
        # exact obligation it is chasing (not a free-floating reminder).
        self.memory.open_loops.write_text(
            task,
            id=loop_id,
            fields={
                "task": task,
                "kind": "follow_up",
                "remind_ts": float(plan["when_ts"]),   # the trigger's due condition
                "follow_up_for_card_id": card_id,
                "follow_up_for_source_text": card.get("source_text") or "",
                "follow_up_reason": plan.get("reason") or "",
                "origin_proof": card.get("proof") or [],
            },
            provenance="follow_up_schedule",
            importance=0.6,
            status="open",          # active + fireable until the trigger fires it
        )
        self.glassbox.log("follow_up_scheduled",
                          {"loop_id": loop_id, "card_id": card_id,
                           "when_ts": plan["when_ts"], "in_days": plan.get("in_days"),
                           "task": task[:120]})
        return plan

    def _sync_captured_loop_from_record(self, record: dict, state: str) -> None:
        owner_card = record.get("owner_card") if isinstance(record, dict) else None
        if not isinstance(owner_card, dict):
            return
        for proof in owner_card.get("proof") or []:
            if not isinstance(proof, dict) or proof.get("type") != "capture_memory_status":
                continue
            memory_id = proof.get("memory_id")
            if memory_id and self._sync_open_loop_item_status(memory_id, state, card_id=record.get("id")):
                proof["status"] = _status_for_open_loop(state)

    def _sync_capture_result_status(self, capture_result: dict | None, state: str,
                                    *, card_id: str | None = None) -> None:
        item = (capture_result or {}).get("item")
        if getattr(item, "kind", None) == "open_loop":
            self._sync_open_loop_item_status(item.id, state, card_id=card_id)

    @staticmethod
    def _has_external_context(ctx_output: dict | None, source_text: str) -> bool:
        """True when memory has context beyond the line just captured."""
        context = (ctx_output or {}).get("context") or {}
        source = (source_text or "").strip().lower()
        stop = {
            "that", "this", "thing", "things", "one", "item", "product",
            "cart", "buy", "buying", "checkout", "find", "found", "put",
            "add", "grab", "same", "still", "later", "dont", "don't",
            "with", "from", "into", "onto", "please", "before", "after",
        }
        source_terms = {t for t in re.findall(r"[a-z0-9]+", source)
                        if len(t) > 3 and t not in stop}
        for key in ("profile", "history", "derived", "open_loops"):
            for item in context.get(key, []) or []:
                text = str(item).strip().lower()
                if not text or text == source:
                    continue
                item_terms = {t for t in re.findall(r"[a-z0-9]+", text)
                              if len(t) > 3 and t not in stop}
                if len(source_terms & item_terms) >= 2:
                    return True
        return False

    async def feed(self, source: str, text: str, meta: dict | None = None) -> dict:
        meta = meta or {}
        # Owner-lane honesty seam: with ANTICIPY_OWNER_INGEST=1 the same /event pipe the
        # persona runner already drives goes through the owner card path instead, so the
        # unchanged runner+scorer measure owner cards with worst-persona honesty. The
        # owner_ingest_execute guard keeps execute_actions card feeds on the proactive
        # path (no recursion back into the owner lane).
        if self._owner_event_enabled() and not meta.get("owner_ingest_execute"):
            return await self.owner_event(source, text, meta)
        if not meta.get("owner_ingest_execute"):
            # owner-lane lines were already captured (with owner metadata) by
            # owner_ingest before the spine ran them (F17) — never capture twice
            self.live_memory.capturer.capture(text, source=source, meta=meta)  # CAPTURE before anything acts
        ev = Event(source=EventSource(source), text=text, meta=meta)
        await self.bus.publish(ev)                 # log the event to the glass-box
        return await self.proactive.on_event(ev)   # triage -> gate -> act/ask (gate reads memory)

    async def owner_event(self, source: str, text: str, meta: dict | None = None) -> dict:
        """One observed line through the owner card path, answered in the same shape as
        the proactive path ({decision, goal_id, ask_id, ...}) so realday.sh and
        persona_score.py grade owner cards without modification.

        F17 'one brain': the decision reported is the SPINE's verdict verbatim for
        spine-judged cards (act / ask / held / ignore — never a paper act or ask),
        "ask" for pre-gated blocked money cards (which never execute and never enter
        /pending), and "remember" for silent memory cards. No card means silence.
        """
        out = await self.owner_ingest(source, text, meta, execute_actions=True)
        rank = {"ask": 3, "blocked": 3, "do": 2, "remember": 1}
        top = None
        for card in out.get("cards", []):
            if top is None or rank.get(card.get("disposition"), 0) > rank.get(top.get("disposition"), 0):
                top = card
        execution = (top or {}).get("execution") or {}
        if top is None:
            decision, goal_id, reason, category, ask_id = (
                "ignore", None, "owner: no actionable card in line", "noise", None)
        elif top["disposition"] == "blocked":
            decision, goal_id, reason, category, ask_id = (
                "ask", top["id"], top.get("reason", ""), "blocked", None)
        elif top["disposition"] == "remember":
            decision, goal_id, reason, category, ask_id = (
                "remember", top["id"], top.get("reason", ""), "remember", None)
        else:
            # do/ask cards carry the spine's verdict — a card whose execution the
            # spine refused reports that refusal, never a paper act/ask (F17)
            decision = execution.get("decision") or "ignore"
            goal_id, reason = top["id"], top.get("reason", "")
            category, ask_id = top["disposition"], execution.get("ask_id")
        return {"decision": decision, "category": category, "reason": reason,
                "goal_id": goal_id, "ask_id": ask_id, "owner_lane": True,
                "cards": out.get("cards", [])}

    def _apply_force_ask(self, card: "OwnerTaskCard | None",
                         line: OwnerObservedLine) -> "OwnerTaskCard | None":
        """The cardinal-sin lever for a vent-adjacent real task (line.force_ask). Such a task is
        CAUGHT (the product is the inference) but may NEVER auto-act in the heat. Coerce any card
        into a confirm-first ASK with NO execution: a 'do' becomes 'ask', a 'blocked' money card
        stays a hard stop (money is the only line we never cross — it must not relax to a fireable
        ask), a 'remember' stays silent memory. Execution is stripped so nothing fires. A non-
        force_ask card is returned unchanged."""
        if card is None or not getattr(line, "force_ask", False):
            return card
        if card.disposition == "blocked":
            # money/wall: the hard stop is stronger than ask — keep it blocked (never executes).
            return card
        if card.disposition == "remember":
            return card   # silent durable memory only — never an act
        card.disposition = "ask"
        card.reason = card.reason or "real task voiced inside a vent — confirm before acting"
        card.execution = None   # strip any spine verdict; a vent-adjacent task never executes
        return card

    def _generic_force_ask_card(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """A confirm-first ASK card for a vent-adjacent real task the regex preview didn't shape
        (a bare task like "call the dentist"). Shared by the execute spine AND the preview path so
        a preview never shows FEWER tasks than the real run catches.

        Deliberately display-only (no backing goal / no ask_id): a task voiced inside a VENT is
        HELD per the mission ("a real task voiced inside emotion is held/asked, never auto-acted in
        the heat") — surfaced so the owner sees it, but never wired to auto-execute, which keeps the
        cardinal-sin floor (safety_mega_eval: a vent must produce nothing actionable). Clean
        (non-vent) model-caught tasks get a real executable goal via the moat_task rescue instead."""
        return OwnerTaskCard(
            source=source, line_no=line.line_no, source_text=line.text,
            title=f"Confirm task: {line.text[:80]}", disposition="ask", route="voice_text",
            action="confirm_owner_task", args={"task_text": line.text}, confidence=0.7,
            reason="real task voiced inside a vent — confirm before acting",
        )

    def _confirm_task_goal(self, line: OwnerObservedLine, goal_id: str | None = None) -> tuple[str, str, str]:
        """Build a PAUSED, resolvable goal for a model-caught task so the app's YES actually
        EXECUTES it — instead of a dead display card that does nothing on press (the "where's the
        action engine / I press yes and nothing happens" bug). Mirrors approve_remembered's proven
        funnel but leaves the goal WAITING: it is NEVER driven here (no auto-act — the cardinal-sin
        guard holds for vent-adjacent tasks), only /resolve (an explicit human YES) drives it.

        Maps the task the same way press-go does: a concrete calendar hold -> create_event (real,
        read-back-verified on YES); everything else (a call, a vague to-do) -> a write_memory
        open-loop so YES at least puts it on the durable list. Money/vent never reach here — money
        is pre-gated to a blocked card and a pure vent yields no task. Returns (ask_id, goal_id,
        would_do)."""
        import datetime as dt
        from ..live_memory.press_go import map_inferred_to_step, WHITELIST
        from .envelopes import Goal, GoalState, Step, Risk
        task = (line.text or "").strip()
        tz, _name = self._owner_timezone()
        owner_now = dt.datetime.now(tz)
        inferred = {"task": task, "people": [], "due_phrase": "", "confidence": "high"}
        mapped = map_inferred_to_step(inferred, raw_text=task, now=owner_now, tz=tz)
        intent = mapped.get("intent")
        step = mapped.get("step")
        would = mapped.get("would_do") or f"Do: {task}"
        if intent not in WHITELIST or step is None:
            # not auto-executable (a call, a message, a vague to-do) -> on YES record it as a
            # durable tracked commitment so it shows on the list; honest (we can't place the call).
            step = Step(intent="write_memory",
                        args={"kind": "open_loop", "text": task, "approved": True}, risk=Risk.low)
            would = f"Keep this on your list: {task}"
        _gkwargs = {"intent": task, "description": would, "steps": [step], "state": GoalState.waiting}
        if goal_id:
            _gkwargs["id"] = goal_id   # deterministic id -> idempotent ask (re-ingest reuses it)
        goal = Goal(**_gkwargs)
        self.store.save(goal)
        ask_id = self.proactive._send_ask(goal, task, "confirm before I act", category="")
        return ask_id, goal.id, would

    @staticmethod
    def _web_start_url(task: str) -> str:
        """Pick a START url for a web task with ZERO per-site knowledge (fully horizontal):
          1. If the task names an explicit URL, go straight there.
          2. If it names a bare domain (e.g. "amazon.ca", "opentable.com"), open that.
          3. Otherwise begin at a web search for the task and let the agent navigate from there.
        No keyword->site lookup table, no owner-TLD baking, no site-specific funnel routing — the
        agent reasons its way to the right page the same way on every site, new or known. Runs on
        the owner's real (logged-in) Chrome via the extension."""
        t = (task or "").strip()
        m = re.search(r"https?://[^\s\"'<>]+", t)
        if m:
            return m.group(0).rstrip(".,)")
        # a bare domain token like "amazon.ca" / "opentable.com" / "site.co.uk"
        m = re.search(
            r"\b([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:com|net|org|io|co|ca|us|uk|de|fr|au|"
            r"shop|store|app|ai|dev|gov|edu)(?:\.[a-z]{2})?)\b",
            t, re.I)
        if m:
            return "https://www." + m.group(1).lstrip("www.")
        return "https://www.google.com/search?q=" + urllib.parse.quote_plus(t)

    def _browser_action_ask(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """THE BROWSER ACTION ROUND-TRIP (Omar's centerpiece): a web task ("find me a standing desk
        on Amazon") is surfaced as a TEXTED, plain-English ask the owner answers by SMS — "Hey, I
        heard you want to … — want me to take a look? Reply YES." On YES (core.resolve) the working
        browser agent runs on the real site and the result is TEXTED back. Never auto-runs (confirm
        first); the runner's money/checkout/login guard means it can find/read but never buys."""
        # Use the owner's ORIGINAL words, not the moat's rephrase — the rephrase strips "return"/"amazon"
        # and breaks both the browser routing and the return-recipe gate (nondeterministic failures).
        task = (getattr(line, "original_text", None) or line.text or "").strip()
        url = self._web_start_url(task)
        # Deterministic ask id: re-ingesting the same web task reuses the SAME pending ask (and the
        # same card id), so a replayed transcript never spawns duplicate browser asks (idempotent
        # round-trip — guards the re-ingest-spam regression; see docs/agent_os/FAILURES.md F-011).
        ask_id = self._browser_action_ask_id(task, source)
        # Register the pending ask directly (resolvable by the app YES button AND by an SMS "YES");
        # category=browser_action routes the YES to the browser agent in core.resolve.
        self.proactive.pending[ask_id] = {
            "goal_id": ask_id, "action": task, "reason": "browser task — confirm before I look",
            "category": "browser_action", "browser_task": task, "browser_url": url}
        self.proactive._persist_pending()
        # Text the owner the plain-English ask NOW (bypasses the in-app suppression — for a web
        # action the owner wants the text). One ask at a time -> a bare "YES" resolves it.
        msg = (f"Hey — I heard you want to {task}. Want me to take a look and report back? "
               f"Just reply YES or NO.")
        try:
            self.text_channel.send(self._user_contact(), msg)
            self.glassbox.log("browser_ask_sent", {"ask_id": ask_id, "task": task, "url": url})
        except Exception as exc:
            self.glassbox.log("browser_ask_send_error", {"ask_id": ask_id, "error": str(exc)})
        _title = f"Look this up for you: {task[:70]}"
        return OwnerTaskCard(
            id=ask_id,
            source=source, line_no=line.line_no, source_text=line.text,
            title=_title, disposition="ask", route="browser",
            action="browser_action", args={"task_text": task, "start_url": url}, confidence=0.8,
            reason="I'll handle this on the web once you accept",
            execution={"decision": "ask", "goal_id": ask_id, "ask_id": ask_id, "goal_state": "waiting"})

    async def _create_and_print_ask(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """THE CREATE + PRINT ROUND-TRIP (the 'make the actual thing + do it' capability): a task like
        'make a sign for the broken door' -> the product GENERATES the real printable artifact NOW, then
        asks before the physical action. On YES (core.resolve) it actually prints to the default printer.
        Mirrors the browser round-trip: confirm-first, NEVER auto-prints (a physical real-world action),
        money never reaches here. The artifact is created up front so the ask can show the real thing."""
        from ..hands.make_artifact import make_sign, prepare_print
        task = (line.text or "").strip()
        # Derive the sign wording from the ORIGINAL words when we have them — the moat sometimes rephrases
        # the line and strips quoted/keyword content; fall back to the (possibly reworded) task text.
        derive_src = (getattr(line, "original_text", None) or task).strip()
        # DETERMINISTIC FIRST: a strong signal (the person's quoted words / a known sign type / the object
        # noun) is authoritative + robust — not subject to model flakiness. Model only for novel phrasings.
        headline, sub = _derive_sign_text(derive_src)
        if not headline:
            try:
                raw = await self.gateway.think(
                    "A person wants a physical SIGN made and printed. Their words: \"%s\". Reply ONLY a "
                    "compact JSON object {\"headline\":\"<the big line; use the person's own words; NEVER "
                    "the word 'Notice'>\",\"sub\":\"<one short supporting line, or empty>\"}." % derive_src,
                    tier="smart", caller="make_sign", temperature=0)
                m = re.search(r"\{.*\}", raw or "", re.S)
                if m:
                    d = json.loads(m.group(0))
                    headline = (d.get("headline") or "").strip()[:40]
                    sub = (d.get("sub") or "").strip()[:80]
            except Exception as exc:
                self.glassbox.log("sign_infer_error", {"error": str(exc)})
        if not headline or headline.lower() == "notice":
            headline = "Notice"
        ask_id = "cp_" + hashlib.sha256(f"create_and_print|{source}|{task}".encode("utf-8")).hexdigest()[:18]
        # GENERATE the artifact + prepare the printer. NEVER silently drop the task or fake a printer: on a
        # real failure (PDF render error) hand back an honest card; if there is NO printer, say so plainly.
        try:
            slug = "sign_" + hashlib.sha256(f"{source}|{task}".encode("utf-8")).hexdigest()[:12]
            artifact = make_sign(headline, sub, slug=slug)
            prep = prepare_print(artifact)
        except Exception as exc:
            self.glassbox.log("create_print_make_error", {"error": str(exc), "task": task[:80]})
            return OwnerTaskCard(
                source=source, line_no=line.line_no, source_text=line.text,
                title=f"Couldn't make the “{headline}” sign", disposition="ask", route="create_print",
                action="confirm_owner_task", args={"task_text": task, "error": str(exc)[:120]},
                confidence=0.5, reason="I hit an error generating the sign — want me to try again?")
        printer = prep.get("printer") or ""
        short = printer.split("_")[0] if printer else ""
        ready = bool(prep.get("ready"))
        self.proactive.pending[ask_id] = {
            "goal_id": ask_id, "action": task, "category": "create_and_print",
            "reason": "made the artifact — confirm before printing (physical action)", "headline": headline,
            "artifact": artifact, "printer": prep.get("printer"), "print_command": prep.get("command")}
        self.proactive._persist_pending()
        if ready:
            msg = (f"Heard about the {'door' if 'door' in task.lower() else 'sign'} — I made a "
                   f"“{headline}” sign. Okay to print it on {short}? Reply YES or NO.")
            reason, title = ("I made the sign — I'll send it to print once you say yes",
                             f"Made a “{headline}” sign — print it?")
        else:
            msg = (f"I made a “{headline}” sign, but I don't see a printer connected. Reply YES and I'll "
                   f"send it the moment one's set up.")
            reason, title = ("I made the sign — no printer found yet; YES queues it for when one's ready",
                             f"Made a “{headline}” sign — no printer found")
        try:
            self.text_channel.send(self._user_contact(), msg)
            self.glassbox.log("create_print_ask_sent",
                              {"ask_id": ask_id, "artifact": artifact, "headline": headline, "ready": ready})
        except Exception as exc:
            self.glassbox.log("create_print_ask_send_error", {"ask_id": ask_id, "error": str(exc)})
        return OwnerTaskCard(
            id=ask_id, source=source, line_no=line.line_no, source_text=line.text,
            title=title, disposition="ask", route="create_print", action="create_and_print",
            args={"task_text": task, "artifact": artifact, "headline": headline, "sub": sub,
                  "printer": prep.get("printer"), "print_command": prep.get("command"), "printer_ready": ready},
            confidence=0.85, reason=reason,
            execution={"decision": "ask", "goal_id": ask_id, "ask_id": ask_id, "goal_state": "waiting"})

    def _support_chore_opt_out(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """THE AUTONOMY LAW (AUTO_DO_WITH_OPT_OUT): a reversible external-service chore — contact a
        company / support about an order/refund/return/delivery/cancellation/issue ("call Amazon
        about that plant I ordered") — must START, not wait for a yes. This is the ANTI-approval-
        machine path: disposition=do (started), route=browser, action=browser_action (autonomy.py
        maps browser_action -> AUTO_DO_WITH_OPT_OUT), so the card shows "I'm on it … — tell me to
        stop", never a Yes/Not-now approval. A STOP control is registered (proactive.pending keyed
        by the card id, category=opt_out_stop) so /owner/stop can halt it.

        It still hard-stops at the true irreversible boundary: match_support_chore excludes any
        spend verb, money still blocks, and a third-party SEND to a person is a different class.
        In MOCK hands it prepares (shows "I'm on it (preparing) — tell me to stop"); in LIVE hands
        it drives the support/browser arm on the real site and texts the result back."""
        task = (line.text or "").strip()
        url = self._web_start_url(task)
        # Deterministic id so a replay of the same chore reuses the same card / running job.
        card_id = "oc_" + hashlib.sha256(f"opt_out|{source}|{task}".encode("utf-8")).hexdigest()[:18]
        live = self.browser_hand.mode == MODE_LIVE
        # Register the STOP control. opt_out chores run unless the owner stops them; this is what
        # /owner/stop cancels (and what the UI's STOP button hits).
        self.proactive.pending[card_id] = {
            "goal_id": card_id, "action": task, "reason": "reversible chore — started, stop me if you want",
            "category": "opt_out_stop", "browser_task": task, "browser_url": url, "stopped": False}
        self.proactive._persist_pending()
        msg = (f"On it — I'm handling \"{task}\" for you now. Tell me to stop if you'd rather I didn't.")
        try:
            self.text_channel.send(self._user_contact(), msg)
            self.glassbox.log("opt_out_started", {"card_id": card_id, "task": task, "url": url,
                                                  "live": live})
        except Exception as exc:
            self.glassbox.log("opt_out_send_error", {"card_id": card_id, "error": str(exc)})
        if live:
            # LIVE: drive the support/browser arm now (async, so it never blocks the ingest reply).
            # The result is texted back and landed on the card, exactly like the confirm-first arm.
            state = "running"
            reason = "I'm on it — tell me to stop"
            try:
                asyncio.create_task(self._run_browser_and_confirm(task, url, card_id))
            except RuntimeError:
                # no running loop (unit/preview) -> stay prepared; nothing fires
                state = "preparing"
                reason = "I'm on it (preparing) — tell me to stop"
        else:
            # MOCK hands: prepare only (no real site drive). Honest copy: preparing, opt-out open.
            state = "preparing"
            reason = "I'm on it (preparing) — tell me to stop"
        return OwnerTaskCard(
            id=card_id,
            source=source, line_no=line.line_no, source_text=line.text,
            title=f"On it: {task[:70]}", disposition="do", route="browser",
            action="browser_action",
            args={"task_text": task, "start_url": url, "opt_out": True, "stop_id": card_id},
            confidence=0.8, status=state,
            reason=reason,
            execution={"decision": "act", "goal_id": card_id, "ask_id": None,
                       "goal_state": state, "opt_out": True})

    def _complete_owner_card(self, card_id: str, state: str = "done",
                             reason: str = "", spoken: str = "") -> bool:
        """Flip a durable owner card record (and its synced loop) to a terminal closed state —
        'done' when the owner said the task is finished, 'superseded' when a newer card revises
        it. Mirrors stop_owner_card's record surgery so the board and the trigger ledger agree."""
        path = self.data_dir / "owner_cards" / f"{card_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            record = None
        if not isinstance(record, dict):
            return False
        record["state"] = state
        if isinstance(record.get("owner_card"), dict):
            record["owner_card"]["status"] = state
            ex = record["owner_card"].get("execution")
            if isinstance(ex, dict):
                ex["goal_state"] = state
                ex["ask_id"] = None
        try:
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return False
        self._sync_owner_loop_status(card_id, state)
        self.glassbox.log("owner_card_closed",
                          {"card_id": card_id, "state": state, "reason": reason,
                           "spoken": (spoken or "")[:160]})
        return True

    def stop_owner_card(self, card_id: str) -> dict:
        """STOP control for an AUTO_DO_WITH_OPT_OUT chore: the owner said 'stop'. Marks the pending
        opt-out stopped (so any in-flight/queued work halts) and flips the durable card record to
        'stopped' so the board reflects it. Reversible chores are the ONLY thing this touches."""
        p = self.proactive.pending.get(card_id)
        if isinstance(p, dict) and p.get("category") == "opt_out_stop":
            p["stopped"] = True
            self.proactive.pending.pop(card_id, None)
            self.proactive._persist_pending()
        path = self.data_dir / "owner_cards" / f"{card_id}.json"
        stopped = False
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            record = None
        if isinstance(record, dict):
            record["state"] = "stopped"
            if isinstance(record.get("owner_card"), dict):
                record["owner_card"]["status"] = "stopped"
                ex = record["owner_card"].get("execution")
                if isinstance(ex, dict):
                    ex["goal_state"] = "stopped"
            try:
                path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
                stopped = True
            except Exception:
                stopped = False
            self._sync_owner_loop_status(card_id, "stopped")
        self.glassbox.log("opt_out_stopped", {"card_id": card_id, "stopped": stopped})
        return {"card_id": card_id, "stopped": stopped}

    async def _run_browser_and_confirm(self, task: str, url: str, ask_id: str) -> None:
        """Run the browser agent on the real site and TEXT the owner the result (the confirmation
        leg of the round-trip). Kicked from core.resolve on a YES so it never blocks the reply."""
        from ..hands.browser_use_link import browse_act
        self.glassbox.log("browser_action_start", {"ask_id": ask_id, "task": task, "url": url})
        # BEFORE text: tell the owner it's starting (Omar wants a message right before AND after).
        try:
            self.text_channel.send(self._user_contact(), f"On it — I'm looking into \"{task}\" on the web now. I'll text you what I find.")
        except Exception:
            pass
        # PHASE 1 — THE SPINE: act in the user's OWN connected Chrome (real, logged-in session) via the
        # extension when it is attached; only fall back to the throwaway browser-use when no extension is
        # connected. The throwaway can never reach the user's real accounts — driving the connected hand
        # IS the product. Both paths feed the SAME judge + card-landing below (one motion, no fork).
        res = None            # browse_act result object (throwaway fallback)
        run_result = None     # WebVoyagerAgent dict result (connected real-Chrome path)
        ok = False
        answer = ""
        # Multi-step real-world tasks (return/refund/exchange, booking, checkout) need more steps than
        # a quick lookup — a generic signal, not a per-site rule (works for ANY site, not just Amazon).
        multistep_task = bool(re.search(
            r"\b(return|refund|exchange|replace|cancel|book|reserve|order|buy|purchase|checkout|"
            r"schedule|apply|sign\s*up|subscribe)\b", task or "", re.I))
        try:
            if self.browser_link.connected:
                from ..agent.webvoyager import WebVoyagerAgent
                self.glassbox.log("browser_action_hand", {"ask_id": ask_id, "hand": "connected_extension"})
                run_result = await WebVoyagerAgent(
                    self.browser_link, self.gateway, max_steps=(24 if multistep_task else 16)).run(task, url)
                answer = (run_result.get("answer") or "").strip()
                # a wall / safety-stop / pause is NOT a success — hand back, never claim done
                blocked = bool(run_result.get("needs_human") or run_result.get("stopped_for_safety")
                               or run_result.get("paused"))
                ok = bool(answer) and not blocked
            else:
                self.glassbox.log("browser_action_hand", {"ask_id": ask_id, "hand": "throwaway"})
                res = await asyncio.to_thread(browse_act, task, url=url, max_steps=16)
                ok = bool(getattr(res, "success", False))
                answer = (getattr(res, "result", "") or "").strip()
        except Exception as exc:
            ok, answer = False, ""
            self.glassbox.log("browser_action_error", {"ask_id": ask_id, "error": str(exc)})
        # Normalize the outcome across both hands (connected agent -> dict; browse_act -> object).
        if run_result is not None:
            final_url = run_result.get("final_url") or url
            screenshot = bool(run_result.get("final_shot"))
            screenshot_path = None
        elif res is not None:
            final_url = getattr(res, "url", None) or url
            screenshot = bool(getattr(res, "screenshot", False))
            screenshot_path = getattr(res, "screenshot_path", None)
        else:
            final_url, screenshot, screenshot_path = url, False, None
        trace = None
        if isinstance(run_result, dict):
            trace = {
                "history": (run_result.get("history") or [])[-40:],
                "page_states": (run_result.get("page_states") or [])[-12:],
            }
        # M4 HONESTY (never fake done): the answer is the agent's RAW self-report. Before we text the owner
        # "Done — ...", a JUDGE must verify it on the real model; an unverified result is NOT claimed done
        # (the owner is asked to retry / take over). Stub/mock keeps prior behavior.
        if ok and answer and getattr(self.gateway, "provider", None) == PROVIDER_OPENROUTER:
            try:
                from ..agent.webvoyager import judge as _judge
                _v = await _judge(self.gateway, task, {"answer": answer, "final_url": final_url})
                if not _v.get("success"):
                    ok = False
                    self.glassbox.log("browser_action_unverified", {"ask_id": ask_id, "reason": _v.get("reason")})
            except Exception:
                ok = False  # couldn't verify -> don't claim done (honest over convenient)
                self.glassbox.log("browser_action_unverified", {"ask_id": ask_id, "reason": "judge unavailable"})
        # LAND THE RESULT ON THE DURABLE CARD (parity with the API arm's read-back proof): the card was
        # flipped to 'running' on YES; write the resolved browser receipt back so the board shows the
        # OUTCOME, not a stranded 'running'.
        self._land_browser_result_on_card(
            ask_id, success=ok, answer=answer, url=final_url,
            screenshot=screenshot, screenshot_path=screenshot_path, trace=trace)
        if ok and answer:
            msg = f"Done — {answer[:500]}"
        else:
            msg = (f"I tried to {task} but couldn't finish it on the site. Want me to try again "
                   f"or hand it to you?")
        try:
            self.text_channel.send(self._user_contact(), msg)
        except Exception:
            pass
        self.glassbox.log("browser_action_done", {"ask_id": ask_id, "success": ok,
                                                  "result": (answer[:200] if answer else None)})

    @staticmethod
    def _browser_action_ask_id(task: str, source: str) -> str:
        return "br_" + hashlib.sha256(f"browser_action|{source}|{task}".encode("utf-8")).hexdigest()[:18]

    def _land_browser_result_on_card(self, ask_id: str, *, success: bool, answer: str,
                                     url: str | None, screenshot: bool,
                                     screenshot_path: str | None = None,
                                     trace: dict | None = None) -> None:
        """Write the resolved BROWSER RECEIPT onto the durable owner card record (card.id == ask_id):
        a `proof` (url + screenshot flag/path) plus a `browser_result` block (answer + success) and the
        final state (done on a real answer, else failed). This is the browser arm's equivalent of the
        API arm's `record['proof'] = goal.proof` write-back — without it the card stays at 'running'
        forever and the found result/screenshot/URL never land where the board reads them. Persists the
        record (the centerpiece path previously skipped this), and syncs the owner-loop status."""
        path = self.data_dir / "owner_cards" / f"{ask_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self.glassbox.log("browser_result_card_missing", {"card_id": ask_id})
            return
        state = "done" if (success and (answer or "").strip()) else "failed"
        proof = {
            "type": "browser_receipt",
            "url": url,
            "screenshot": bool(screenshot),
            "answer": (answer or "")[:1000],
        }
        if screenshot_path:
            proof["screenshot_path"] = screenshot_path
        if trace:
            proof["trace"] = trace
        source_gateway_event_id = record.get("gateway_event_id")
        task_text = (
            ((record.get("owner_card") or {}).get("source_text") if isinstance(record.get("owner_card"), dict) else None)
            or record.get("description")
            or ask_id
        )
        record["state"] = state
        record["proof"] = proof
        record["browser_result"] = {
            "success": bool(success),
            "answer": (answer or "")[:1000],
            "url": url,
            "screenshot": bool(screenshot),
            "screenshot_path": screenshot_path,
        }
        if trace:
            record["browser_result"]["trace"] = trace
        if isinstance(record.get("owner_card"), dict):
            record["owner_card"]["status"] = state
            # Mirror the receipt onto the card body so owner_cards() surfaces it on the board.
            self._set_card_execution_proof(record["owner_card"], proof, state)
        try:
            browser_event = self.gateway_ledger.record_browser_result(
                ask_id=ask_id,
                task=task_text,
                success=success,
                answer=answer,
                url=url,
                screenshot=screenshot,
                screenshot_path=screenshot_path,
                trace=trace,
                source_event_id=source_gateway_event_id,
            )
            record["browser_gateway_event_id"] = browser_event.get("event_id")
            if isinstance(record.get("owner_card"), dict):
                record["owner_card"]["browser_gateway_event_id"] = browser_event.get("event_id")
        except Exception as _gateway_exc:
            self.glassbox.log("proactive_gateway_browser_result_error",
                              {"error": str(_gateway_exc)[:240]})
        try:
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return
        self._sync_owner_loop_status(ask_id, state)
        self.glassbox.log("browser_result_on_card",
                          {"card_id": ask_id, "state": state, "success": bool(success),
                           "url": url, "screenshot": bool(screenshot)})

    @staticmethod
    def _set_card_execution_proof(owner_card: dict, proof: dict, state: str) -> None:
        """Attach the browser receipt to the card's execution block so the durable
        card carries proof (mirrors how the API arm's proof rides the card)."""
        execution = owner_card.get("execution")
        if not isinstance(execution, dict):
            execution = {}
            owner_card["execution"] = execution
        execution["proof"] = proof
        execution["goal_state"] = state

    @staticmethod
    def _timed_reminder_card(line: OwnerObservedLine, source: str,
                             capture_result: dict | None) -> OwnerTaskCard | None:
        """A self-reminder the spine has nothing to DO about right now ("take my meds at 9pm",
        "set a focus block at 2pm") is still a REAL timed reminder: the capture grounded a
        remind_ts and the trigger fires it at the due time (the 2:45-call use case). The caller
        previously marked such a line 'ignored', which DEACTIVATED its loop -> the reminder
        silently never fired. Surface it as a Ready card ('I'll remind you when it's due') and —
        critically — keep its loop ACTIVE (the caller skips the ignored-sync when this returns a
        card). Money/vent never reach here: a money line is a blocked card, a vent never captures
        an open_loop (capture's vent guard), so only a clean reversible timed task qualifies."""
        item = (capture_result or {}).get("item")
        if getattr(item, "kind", None) != "open_loop":
            return None
        fields = getattr(item, "fields", None) or {}
        if not fields.get("remind_ts"):
            return None
        return OwnerTaskCard(
            source=source, line_no=line.line_no, source_text=line.text,
            title=f"Reminder set: {line.text[:80]}", disposition="do", route="api",
            action="timed_reminder", args={"task_text": line.text,
                                            "remind_ts": fields.get("remind_ts")},
            confidence=0.8, reason="timed action — I'll remind you when it's due",
            status="open",
        )

    def _money_blocked_card(self, line: OwnerObservedLine, source: str) -> OwnerTaskCard:
        """The absolute money hard-stop card — visible ("Left for you"), never executes."""
        return OwnerTaskCard(
            source=source, line_no=line.line_no, source_text=line.text,
            title="Left for you (money)", disposition="blocked",
            route="browser", action="prepare_purchase_path_without_payment",
            args={"task_text": line.text, "payment_allowed": False}, confidence=0.85,
            reason="money or checkout is a hard stop; prepare but do not pay")

    async def _spine_card(self, line: OwnerObservedLine, source: str, meta: dict) -> OwnerTaskCard | None:
        """F17 'one brain': the proven spine (triage -> decider -> harm-line ->
        orchestrator/hands) is the ONLY act/ask/silent decision-maker for owner
        lines. The regex classifier only shapes the durable card (title/route/args)
        and adds silent memory; it can no longer act or ask on its own. Money-shaped
        browser lines stay pre-gated blocked: never the spine's execution path,
        never /pending, never executed (the harm-line stance is final) — but a
        money-flavored line the spine's OWN triage confidently vents stays silent
        exactly as it would on the default path (F23)."""
        # ABSOLUTE MONEY HARD-STOP (deterministic, beats EVERY model/decider/shaper path): a line the
        # harm-line categorizes as a money ACTION is ALWAYS a blocked PREPARE_THEN_STOP card — it can
        # never be routed to remember/ask/do or silently dropped. The 20-life run caught a $400
        # wire-to-a-person landing as REMEMBER_ONLY and a $14,200 tax payment DROPPED ENTIRELY; this is
        # the one gate the product exists to enforce, so it runs first and unconditionally. (Pure
        # money-VENTS never reach here — the moat's vent guard drops them upstream.) Keyed on a money
        # ACTION (signal + spend verb), NOT the broad harm money-CATEGORY, so benign money-noun lines
        # ("log the payment in the CRM", "review the invoice") keep their nuanced carve-outs.
        if _is_money_action(line.text) or getattr(line, "money_src", False):
            blk = self.owner_mode.card_for_line(line, source)
            if blk is not None and blk.disposition == "blocked":
                return blk
            return self._money_blocked_card(line, source)
        # EXPLICIT REVERSIBLE TASK (reminder / hold / lookup / draft / cart-no-buy) with NO real money
        # signal: ALWAYS a confirm-first ask, never dropped. harm broadly tags cart/checkout tokens as
        # the "money" CATEGORY, so the decider below would BLOCK then drop "set up a cart, don't check
        # out" (no blocked card shapes -> None -> lost). But a cart-no-buy / reminder / lookup is
        # reversible prep, not a money MOVE (the absolute money-action block above already owns real
        # money). Surface it here, before the decider can lose it. Vents never match this detector and
        # third-party requests are silenced upstream, so this only ever rescues genuine catches.
        if (getattr(line, "moat_task", False) and not getattr(line, "force_ask", False)
                and _is_explicit_reversible_task(line.text)
                and not _is_money_action(line.text) and not getattr(line, "money_src", False)):
            shaped = self.owner_mode.card_for_line(line, source)
            # Real money already blocked above; a "blocked" here is a FALSE money-block on a non-money
            # reversible (e.g. "look up the CHECKOUT-service runbook" tripping the checkout keyword) -> do
            # NOT return it; surface the lookup/reminder as an ask instead so it isn't money-refused.
            if shaped is not None and shaped.disposition in ("ask", "remember"):
                return shaped
            return self._generic_force_ask_card(line, source)
        # VENT-ADJACENT REAL TASK (force_ask): the model pulled this real task out of a vented
        # breath. It must be SURFACED as a confirm-first ask, but the spine must NEVER EXECUTE it
        # in the heat (that is the exact path a prior attempt used to re-introduce the cardinal
        # sin). So we DO NOT run the executing spine here at all: shape a durable ask card from the
        # regex preview (or a generic ask) and return it un-executed. Money still pre-gates blocked.
        if getattr(line, "force_ask", False):
            shaped = self.owner_mode.card_for_line(line, source)
            if shaped is not None and shaped.disposition == "blocked":
                return shaped   # money hard stop owns it; never executes
            if shaped is not None and shaped.disposition == "remember":
                return shaped   # silent memory only
            if shaped is not None:
                shaped.disposition = "ask"
                shaped.reason = "real task voiced inside a vent — confirm before acting"
                shaped.execution = None   # vent-adjacent task is HELD (display-only), never auto-acts
                return shaped
            return self._generic_force_ask_card(line, source)
        shaped = self.owner_mode.card_for_line(line, source)
        if shaped is not None and shaped.disposition == "blocked":
            # A real MONEY line must ALWAYS surface as blocked ("Left for you") — money is the hard
            # stop and must be VISIBLE, never silently dropped. card_for_line's is_vent guard already
            # drops money-FLAVORED VENTS before they ever become a blocked card; the old
            # triage.actionable() gate here ADDITIONALLY dropped REAL money lines that triage
            # misjudged as not-actionable, so "refund the customer $50" / "reimburse the client 1100"
            # VANISHED on the execute path while preview correctly blocked them (relentless bug-hunt).
            # Keep only the vent-shape belt-and-suspenders: a genuine vent shape stays silent, every
            # real money line surfaces as a non-executing blocked card. Money never executes either way.
            from ..live_memory.review_infer import is_vent_shape as _ivs2
            if _ivs2(line.text):
                return None
            return shaped
        # THE AUTONOMY LAW (SEAM 1): a reversible external-service chore — contact a company /
        # support about an order/refund/return/delivery/cancellation/issue ("call Amazon about that
        # plant I ordered") — must START, not wait for a yes. It is NOT an approval ask: route it to
        # the support/browser arm as AUTO_DO_WITH_OPT_OUT ("I'm on it — tell me to stop"). Checked
        # AFTER the money pre-gate so money/pay/checkout still BLOCKS first; match_support_chore
        # itself excludes any spend verb, and a third-party SEND to a person is a different class
        # (it carries no company+issue pair). Runs only on the executing spine path (not preview).
        from ..shared.support_chore import match_support_chore
        if match_support_chore(line.text) is not None:
            # VENT FLOOR (sweep r2 #21): a service chore voiced inside a vent ("ugh I should just call
            # them and scream about it") must NEVER AUTO-START — that is the cardinal sin. If the line
            # reads as a vent shape, force it confirm-first instead of AUTO_DO_WITH_OPT_OUT.
            from ..live_memory.review_infer import is_vent_shape as _ivs_sc
            if _ivs_sc(line.text):
                self.glassbox.log("support_chore_vent_held", {"line": line.text[:140]})
                return self._generic_force_ask_card(line, source)
            self.glassbox.log("support_chore_opt_out",
                              {"line": line.text[:140], "reason": "reversible service chore -> AUTO_DO_WITH_OPT_OUT"})
            return self._support_chore_opt_out(line, source)
        # INTERNAL NOTE (SEAM 3): "the retainer note is in the CRM" is reversible internal admin, not
        # money. owner_mode shaped it as a confident do (prepare_internal_note). There is no generic
        # CRM/notes arm wired yet, so the honest AUTO_DO is to PREPARE the note (capture what we'd
        # write) and surface it as a do-card — never a money block, never a dead clarify. Handled
        # directly (not via the decider, which silences this loose admin phrasing -> the moat_task
        # rescue then mislabels it a clarify). The capture path already wrote the line as durable
        # memory; _persist_card records the prep with read-back proof.
        if shaped is not None and shaped.action == "prepare_internal_note":
            self.glassbox.log("internal_note_prepared",
                              {"line": line.text[:140],
                               "reason": "internal note/record -> reversible admin (no money)"})
            shaped.disposition = "do"
            shaped.reason = ("CRM/notes not connected — I've kept the note text ready; "
                             "I'd write this in the record")
            shaped.execution = {"decision": "act", "goal_id": None, "ask_id": None,
                                "goal_state": "open", "internal_note": True}
            return shaped
        if shaped is not None and shaped.action == "research_or_find_item":
            # MERGE FIX (2026-06-23): a general web lookup/admin task ("look up the gallery hours",
            # "find Nicki's email") is the confirm-first browser round-trip, exactly like an unresolved
            # cart — register it as an approvable ask so YES (app button / SMS) runs the browser arm.
            # Without this it dead-ended as a do/browser card that never executed (the merge gap).
            # Money/vent are already handled above; this only routes genuine reversible lookups.
            return self._browser_action_ask(line, source)
        if shaped is not None and shaped.action == "find_or_cart_without_purchase":
            # PREPARE WHEN CONFIDENT (Omar's law, 2026-06-16 decision): if memory/onboarding resolves
            # the exact item + store, auto-prepare the cart — it falls through to execute as a
            # browse_task in a THROWAWAY browser (the runner's money/checkout guard means it can
            # find/cart but NEVER buys) and carries a memory_resolution receipt. When the item/source
            # is NOT resolvable, fall back to the confirm-first browser round-trip (Omar's centerpiece):
            # ONE deterministic texted ask, answered by YES — no duplicate ask, no stray goal (F-011).
            ctx = await self.bus.submit_job(Job(intent="read_context", args={"about": line.text, "purpose": "act"}))
            if not self._has_external_context(ctx.output, line.text):
                return self._browser_action_ask(line, source)
            # Resolved -> mark so the confirm-first gate SKIPS it; fall through to auto-execute below.
            shaped.args["resolved_cart"] = True
        execution_text = (
            self.owner_mode.execution_text_for_card(shaped)
            if shaped is not None else line.text
        )
        out = await self.feed("app", execution_text,
                              {**meta, "owner_source": source,
                               "owner_ingest_execute": True,
                               "owner_source_text": line.text})
        decision = out.get("decision") or "ignore"
        execution = {"decision": decision, "goal_id": out.get("goal_id"),
                     "ask_id": out.get("ask_id"), "goal_state": None}
        if decision == "act" or decision in ("ask", "held") or out.get("ask_id"):
            if shaped is not None and shaped.disposition in ("do", "ask"):
                card = shaped
            else:
                # the spine caught a line the regex could not shape: the card
                # mirrors the spine's verdict with a generic shape
                card = OwnerTaskCard(
                    source=source,
                    line_no=line.line_no,
                    source_text=line.text,
                    title=f"Owner task: {line.text[:80]}",
                    disposition="do",
                    route="api",
                    action="execute_owner_task",
                    args={"task_text": line.text},
                    confidence=0.8,
                )
            card.disposition = "do" if decision == "act" else "ask"
            card.reason = out.get("reason") or card.reason or "proven spine verdict"
            card.execution = execution
            return card
        # THE MODEL DRIVES (Omar's core directive): the MOAT confidently extracted this as a clean
        # real task, but the deterministic regex triage just voted SILENT because the phrasing is
        # loose ("call mom", "do that email of the thing next weekend"). A regex must NEVER silently
        # VETO a model-caught task into nothing — that is the exact failure ("you keep dropping the
        # real tasks because they aren't phrased like a command"). Surface the model's catch as a
        # confirm-first ASK. The ONLY hard overrides stay: the spine BLOCKED it (money/wall ->
        # decision != ignore, handled above) or the deterministic vent/harm floor flags it a vent or
        # money/detrimental line — those stay silent. Never an auto-act.
        # Rescue on ANY silent outcome (ignore / suppressed / deferred), not just "ignore": the
        # decider model returns these intermittently for the same loose self-commitment, which made
        # a real task drop ~1-in-5 runs (audit gap). "blocked" is the money/wall hard-stop and is
        # the ONE silent-branch decision we never rescue (handled by the category!=money guard too).
        if getattr(line, "moat_task", False) and decision != "blocked":
            from ..live_memory.review_infer import is_vent_shape
            if not is_vent_shape(line.text):
                verdict = self.proactive.harm.assess(line.text, {})
                # MONEY is the only hard-stop that must never surface as an actionable ask
                # (it stays blocked/Left-for-you). Every other harm category (binding_send=email,
                # casual_send, auth_wall, unclassified=call/book/sort-out) is exactly a
                # confirm-first ASK — surface it, don't drop it. (detrimental=True covers ALL of
                # these, which is why gating on it wrongly suppressed real tasks.)
                # An explicit REMINDER/HOLD ("remind me the wire needs to go to Jordan, don't move
                # anything yet") brushes a money WORD but carries no real money SIGNAL (no amount/account/
                # transfer-to) — surface it (confirm-first) rather than drop it. A reminder WITH a real
                # money signal ("wire $5k to escrow") is NOT excepted here: it stays category==money and
                # the deterministic money backstop renders it blocked-visible (never an ask, never dropped).
                # An explicit reversible task (reminder/hold/lookup/draft/cart-no-buy) that harm broadly
                # tags "money" on a surface token (cart/checkout) but carries NO real money SIGNAL
                # (amount/account) is reversible prep, not a money move — surface it (confirm-first) rather
                # than drop it. A real money signal still blocks via the absolute money-block above.
                _rev_not_money = _is_explicit_reversible_task(line.text) and not _MONEY_SIGNAL.search(line.text)
                if getattr(verdict, "category", None) != "money" or _rev_not_money:
                    self.glassbox.log("moat_task_rescued",
                                      {"line": line.text[:140],
                                       "reason": "model caught a real task the triage silenced"})
                    # ROUTING CONSISTENCY (loop must close): a web-resolvable lookup ("look up/find/
                    # research X", "what time does Y", "how much is Z") that fell into the moat-rescue must
                    # reach the HAND, not a generic confirm that never executes — otherwise the SAME
                    # "look up X" sometimes runs and sometimes dead-ends (the routing nondeterminism that
                    # keeps the loop from closing). Money/vent are already excluded above; the money SIGNAL
                    # guard here is belt-and-suspenders so a spend never routes to the browser arm.
                    from ..owner_mode import _BROWSER as _OB, _WEB_LOOKUP as _OWL
                    if (_OB.search(line.text) or _OWL.search(line.text)) and not _MONEY_SIGNAL.search(line.text):
                        self.glassbox.log("moat_task_to_browser",
                                          {"line": line.text[:120], "reason": "web-resolvable -> the hand, not a dead confirm"})
                        return self._browser_action_ask(line, source)
                    # back it with a PAUSED resolvable goal so the app's YES actually executes it
                    # (real calendar hold / tracked commitment) — never a dead display card.
                    ask_id, goal_id, _w = self._confirm_task_goal(line)
                    return OwnerTaskCard(
                        source=source, line_no=line.line_no, source_text=line.text,
                        title=f"Confirm task: {line.text[:80]}", disposition="ask",
                        route="voice_text", action="confirm_owner_task",
                        args={"task_text": line.text}, confidence=0.7,
                        reason="caught this from how you said it — confirm before I act",
                        execution={"decision": "ask", "goal_id": goal_id,
                                   "ask_id": ask_id, "goal_state": "waiting"})
        # spine says silent: regex shaping may still add SILENT memory (a remember
        # card or a durable open-loop record) — never a paper act or ask
        if shaped is None:
            return None
        if shaped.disposition != "remember":
            shaped.execution = execution
        return shaped

    def _deterministic_expand(self, observed):
        """The model-independent expansion floor (factored 2026-07-02, byte-identical behavior).

        Used whenever the ONE extractor (decision_pipeline) can't run: the stub provider, the
        real 429 "starved brain" degraded mode, an env-disabled pipeline, or a live pipeline
        outage. We can't split multi-task lines, but the deterministic THIRD-PARTY
        SILENCE floor MUST still hold — a question aimed at someone else ("Did you grab the dry
        cleaning on the way home?") is never the owner's task and must stay silent even when the
        model can't run. Without this, an aside reaches the spine, which (memory-state-dependent)
        can surface it as a lookup ASK on the /owner/ingest path — a cardinal-sin cold-start
        breach the safety eval caught."""
        kept = []
        for l in observed:
            if _is_interrogative_aside(l.text) or _is_directed_question_to_named_person(l.text):
                self.glassbox.log("aside_silenced_no_model", {"line": (l.text or "")[:140]})
                continue
            if _is_noncommittal_noise(l.text):
                self.glassbox.log("noncommittal_noise_silenced_no_model", {
                    "line": (l.text or "")[:140],
                })
                continue
            vent_tasks = _deterministic_vent_adjacent_tasks(l.text)
            if vent_tasks:
                for task in vent_tasks:
                    held = OwnerObservedLine(line_no=l.line_no, text=task, force_ask=True)
                    held.original_text = l.text
                    held.money_src = _is_money_action(task)
                    kept.append(held)
                self.glassbox.log("vent_tasks_held_no_model", {
                    "line": (l.text or "")[:140],
                    "tasks": vent_tasks,
                })
                continue
            # NOTE: do NOT force moat_task on reversible lines here — that routes them through the
            # confirm-first rescue and DOWNGRADES spine AUTO_DO tasks (reminders/carts) into asks
            # (over-caution + regression). Stub/no-model surfacing of spine-dropped reversibles
            # (draft/save/cart) is a known degraded-mode gap; the proper fix is native recognition
            # in owner_mode._card_for_line, not the heavier moat_task flag. Backlogged.
            kept.append(l)
        return kept

    # (THE MOAT was retired 2026-07-02, FIX-01 step 2c: the second model brain — extract.py
    #  whole-day + per-line extraction — duplicated the decision pipeline. The pipeline is the
    #  ONE extractor now; when it cannot run, _deterministic_expand holds the floors.)

    async def owner_ingest(self, source: str, text: str, meta: dict | None = None,
                           execute_actions: bool = False) -> dict:
        """Shared owner path for transcript/MP3/listening/pay-to-try.

        It records the whole observed stream, extracts durable task cards, and writes
        those cards into the real memory drawers. With execute_actions, the cards are
        REAL: do cards run through the proven proactive spine (orchestrator + hands)
        with the outcome and proof mirrored onto the durable card record; ask cards
        become pending asks resolved by the existing YES/NO flow; money/blocked cards
        can never execute (the harm-line is final); remember cards carry read-back
        proof of their memory write.
        """
        meta = meta or {}
        gateway_event_id = str(meta.get("gateway_event_id") or f"gw_{hashlib.sha256(f'{source}:{text}:{dt.datetime.now(dt.timezone.utc).timestamp()}'.encode()).hexdigest()[:24]}")
        meta = {**meta, "gateway_event_id": gateway_event_id}
        gateway_token = _GATEWAY_EVENT_ID.set(gateway_event_id)
        # Asks caught from THIS app paste show in-app ("Waiting for your yes"); they must NOT also
        # SMS the owner (that is the banned spam — every task buzzing the phone). Suppress ask
        # delivery for the duration of the ingest; time-due reminders (trigger_tick) still text.
        self.proactive._suppress_ask_delivery = True
        try:
            out = await self._owner_ingest_inner(
                source, text, meta, execute_actions, observed=None)
        finally:
            self.proactive._suppress_ask_delivery = False
            _GATEWAY_EVENT_ID.reset(gateway_token)
        # PROACTIVE FIND-NOTIFICATION (owner directive): when the engine FINDS something it can't act
        # on without the owner's okay — money (the hard stop), a send to a person, anything
        # irreversible — it must IDENTIFY it and TELL the owner over text, in real human words (never
        # a canned script), and it CANNOT act without their explicit approval. ONE consolidated heads-
        # up (no per-item flood). Words only — nothing is executed here. Only for AMBIENT capture
        # (mic / audio / listening / pendant) where the owner isn't already watching the app; a typed
        # in-app paste shows the same finds in the UI, so we don't double-buzz the phone. Best-effort:
        # a notify failure never breaks ingest.
        _AMBIENT = {"mac_mic", "start_listening", "audio_upload", "mp3", "pendant_phone"}
        if execute_actions and source in _AMBIENT:
            try:
                from ..proactive.agent_reply import notify_finds
                msg = await notify_finds(self.gateway, out.get("cards") or [])
                if msg and self.text_channel.configured():
                    sent = self.text_channel.send(self._user_contact(), msg)
                    self.glassbox.log("finds_notified",
                                      {"to": self._user_contact(), "text": msg,
                                       "live": (sent or {}).get("mock") is False})
            except Exception as e:  # pragma: no cover - never let a notify break ingest
                self.glassbox.log("finds_notify_failed", {"error": str(e)})
        try:
            event = self.gateway_ledger.record_owner_ingest(
                event_id=gateway_event_id,
                source=source,
                text=text,
                meta=meta,
                result=out,
                execute_actions=execute_actions,
            )
            out["gateway_event"] = event
            out["gateway_events"] = [event]
        except Exception as e:  # pragma: no cover - observability must not break intake
            self.glassbox.log("proactive_gateway_owner_ingest_error", {"error": str(e)[:240]})
        return out

    def _intent_resolve(self, observed, raw_lines):
        """GATE MIDDLE-1: intent-shaped memory handoff. Build ranked INTENT THREADS from the raw
        transcript, resolve each task's VAGUE reference against them ("that desk thing" -> the Jarvis
        standing desk, not Mia pickup; "send it" -> the Sam deck), and drop preference/referent
        statements from the action path (remembered, never a card). An ambiguous reference is left
        un-resolved so the downstream asks the smallest clarification — never a wrong guess.
        Returns (filtered_observed, middle_trace) with the seven proof fields per resolution."""
        from ..proactive.intent_threads import (
            build_threads, classify, resolve_reference, _head_noun, _is_bare_ref,
        )
        threads = build_threads(raw_lines)
        captured = [{"text": t.text, "kind": t.kind} for t in threads]
        resolutions, kept = [], []
        for line in observed:
            text = getattr(line, "text", "") or ""
            # A "preference" classification REMEMBERS the line and drops it from the action path. But it
            # must NOT veto a confident actionable task: the 20-life test caught "get a cart together for
            # 200 menus, don't order yet" and "draft an email ... don't send it" classified as preference
            # (the leading noun-phrase / "don't ..." fooled it) and DROPPED entirely. A moat-caught task
            # or a draft/cart-prep line is a real reversible deliverable — never silence it as a preference.
            if (classify(text) == "preference"
                    and not getattr(line, "moat_task", False)
                    and not _is_draft_or_cart_prep(text)):
                resolutions.append({"line": text, "kind": "preference",
                                    "decision": "remembered as referent — no card"})
                continue
            if _head_noun(text) or _is_bare_ref(text):
                self_idx = next((t.idx for t in threads if t.text == text), len(threads))
                resolved, tr = resolve_reference(text, threads, self_idx)
                if resolved != text:
                    line.text = resolved
                resolutions.append({
                    "line": text, "resolved_to": resolved, "head": tr.get("head"),
                    "ranked_candidates": tr.get("candidates"), "chosen_referent": tr.get("chosen"),
                    "rejected_referents": tr.get("rejected"),
                    "decision": "resolved" if resolved != text else "ambiguous — ask smallest clarification",
                })
            kept.append(line)
        trace = {"captured_memories": captured, "resolutions": resolutions}
        try:
            self.glassbox.log("intent_middle_trace", trace)
        except Exception:
            pass
        return kept, trace

    @staticmethod
    def _consolidate_obligations(observed):
        """F-012 anti-spam: collapse moat-expanded lines that name the SAME real-world obligation so
        one obligation yields one card. "Mom: call Amazon about the plant" + "Yeah, I'll handle it"
        (-> "handle the Amazon plant order") + a reworded variant all share the object signature
        {amazon, plant} and collapse to ONE line (the earliest/original wording kept). Genuinely
        different objects never merge. Safety is preserved: if ANY clustered line is vent-adjacent
        (force_ask), the kept line stays force_ask (the vent guard can only get stricter, never lost).
        Thin/empty-signature lines are never auto-merged (kept as-is)."""
        kept = []          # list of [line, sig]
        for line in observed:
            sig = _obligation_sig(getattr(line, "text", ""))
            merged = False
            if sig:
                for entry in kept:
                    if _same_obligation(sig, entry[1]):
                        # fold into the existing obligation; propagate the stricter guards
                        if getattr(line, "force_ask", False):
                            entry[0].force_ask = True
                        if getattr(line, "confirm_ask", False):
                            entry[0].confirm_ask = True
                        if getattr(line, "moat_task", False):
                            entry[0].moat_task = True
                        # keep the broader signature so further variants still match
                        entry[1] = entry[1] | sig
                        merged = True
                        break
            if not merged:
                kept.append([line, sig])
        return [entry[0] for entry in kept]

    async def _semantic_dedup_same_source(self, observed):
        """LLM semantic dedup (anti-spam, Omar's #1 ban) over ALL the day's tasks at once. The whole-day
        extractor sometimes emits the SAME obligation twice — a reminder and its action ('invoice
        Brightwave' + 'set a reminder Friday to invoice Brightwave'), the same thing reworded ('get back
        to Okafor' + 'get back to him'), a means and its goal ('renew the cert' + 'sign up for the recert
        course'), or a sentence-tail fragment ('...so I don't lose track of it'). Token/signature dedup
        cannot catch near-duplicates; ONE bounded SMART call clusters same-obligation tasks. SAFE: the
        prompt + keep-longest never merge genuinely-different tasks; stub/error/non-confident reply -> NO
        merge (a real task is never dropped on a guess); guards (force_ask/money_src) propagate to the kept."""
        if self.gateway.provider != PROVIDER_OPENROUTER:
            return observed
        import json as _json
        cand = [m for m in observed if getattr(m, "moat_task", False)]
        if len(cand) < 2:
            return observed
        listing = "\n".join(f"{i}. {m.text}" for i, m in enumerate(cand))
        prompt = (
            "Below are tasks an assistant extracted from ONE person's day. Some are DUPLICATES — the SAME "
            "single obligation surfaced twice: a reminder and its action ('invoice Brightwave' & 'set a "
            "reminder Friday to invoice Brightwave'), the same thing reworded ('get back to Okafor' & 'get "
            "back to him'), a means and its goal ('renew the cert' & 'sign up for the recert course'), or a "
            "sentence fragment of another ('...so I don't lose track of it'). Group items that are the SAME "
            "obligation. GENUINELY DIFFERENT tasks ('call mom' & 'call the dentist'; 'invoice Acme' & "
            "'invoice Brightwave') must EACH be their own group. Reply with ONLY a JSON list of lists of "
            "item numbers, e.g. [[0,3],[1],[2,4]]; every number 0..N-1 appears exactly once.\n"
            f"Tasks:\n{listing}"
        )
        try:
            raw = await self.gateway.think(prompt, tier="smart", caller="gate")
            m = re.search(r"\[.*\]", raw or "", re.S)
            clusters = _json.loads(m.group(0)) if m else []
        except Exception:
            return observed
        if not isinstance(clusters, list):
            return observed
        drop_ids: set = set()
        for cluster in clusters:
            if not isinstance(cluster, list):
                continue
            idxs = [c for c in cluster if isinstance(c, int) and 0 <= c < len(cand)]
            if len(idxs) < 2:
                continue
            keep = max((cand[i] for i in idxs), key=lambda mm: len(mm.text or ""))
            for i in idxs:
                mm = cand[i]
                if mm is keep:
                    continue
                if getattr(mm, "force_ask", False):
                    keep.force_ask = True
                if getattr(mm, "confirm_ask", False):
                    keep.confirm_ask = True
                if getattr(mm, "money_src", False):
                    keep.money_src = True
                drop_ids.add(id(mm))
        if drop_ids:
            self.glassbox.log("semantic_dedup_merged", {"dropped": len(drop_ids), "kept": len(cand) - len(drop_ids)})
        return [ln for ln in observed if id(ln) not in drop_ids]

    def _build_from_proactive_decisions(self, decision_result):
        """Convert the canonical proactive decision pass into owner-observed lines.

        The decision pipeline owns "who/real/what now"; the existing owner path
        still owns routing, card persistence, memory proof, browser proof, and
        follow-up. Ignored decisions stay visible in the gateway trace but never
        become candidate cards.
        """
        out: list[OwnerObservedLine] = []
        n = 0
        for decision in getattr(decision_result, "decisions", []) or []:
            if decision.decision == "ignore":
                continue
            task = (decision.task_text or decision.evidence_span or "").strip()
            if not task:
                continue
            n += 1
            line = OwnerObservedLine(line_no=n, text=task)
            line.original_text = (decision.evidence_span or task).strip() or task
            if decision.decision in {"ask", "follow_up"}:
                line.force_ask = True
            # A brain "ask" is a real confirm-first task (a send/booking/lookup that needs the owner's
            # okay), NOT a vent — it is force_ask ONLY to block auto-act. Mark it confirm_ask so the
            # ask gets a resolvable ask_id + pending entry (tapping "Go ahead" runs it), instead of
            # inheriting the vent-adjacent held-display floor and dead-ending on approve. (follow_up is
            # a scheduled nudge, NOT a tap-YES ask, so it is deliberately NOT marked confirm_ask.)
            if decision.decision == "ask":
                line.confirm_ask = True
            if decision.decision in {"act", "ask", "block", "follow_up"}:
                line.moat_task = True
            if decision.decision == "block" or _is_money_action(task) or _is_money_action(line.original_text or ""):
                line.money_src = True
            out.append(line)
        return out

    async def _completeness_sweep(self, text: str, observed: list, raw_lines: list):
        """MODEL-LAYER completeness backstop — the real fix for the catch-rate long tail. Five rounds of
        the 20-life gauntlet proved the per-line moat drops a chunk of CLEAN reversible tasks inside dense
        multi-line days (rolling vent context contaminates a line's read), and no finite set of regexes
        can cover the infinite phrasings ('block two hours Thursday', 'hold the 9:40am flight', 'pull
        their cap table', 'set up a cart'). So after the per-line pass, ONE model call reads the WHOLE
        transcript and lists the EXPLICIT reversible tasks we MISSED. Recovered tasks re-enter as moat_task
        lines and STILL pass every floor downstream (vent guard, money hard-stop, third-party silence), so
        this only ever ADDS genuine catches — never weakens safety. Multi-line only (single-line/proactive
        and the safety eval stay byte-identical). Stub/error/hallucination-guard -> no-op."""
        if self.gateway.provider != PROVIDER_OPENROUTER or len(raw_lines) < 2:
            return observed
        import json as _json
        caught = [getattr(o, "text", "") for o in observed]
        prompt = (
            "Below is a person's spoken day, then the tasks an assistant already caught. List every "
            "EXPLICIT, reversible task the person clearly asked for that is MISSING from the caught list:\n"
            "- reminders ('remind me to X', 'don't let me forget X'), calendar holds ('block/hold time "
            "for X', 'lock X on my calendar'), lookups ('pull up / look up / find out / check X'), "
            "drafts ('draft an email/note to X, don't send'), cart-prep ('cart X, don't buy').\n"
            "EXCLUDE: vents/jokes/sarcasm/figures of speech; questions directed AT another named person "
            "(their task, e.g. 'Sam, can you...'); and money transfers/payments ('wire/pay/refund $X') — "
            "those are handled separately. Quote each missed task in the person's own words (a short "
            "phrase). Reply with ONLY a JSON array of strings; [] if nothing was missed.\n\n"
            f"DAY:\n{text}\n\nALREADY CAUGHT:\n" + "\n".join(f"- {c}" for c in caught)
        )
        try:
            raw = await self.gateway.think(prompt, tier="smart", caller="gate")
            m = re.search(r"\[.*\]", raw or "", re.S)
            missed = _json.loads(m.group(0)) if m else []
        except Exception:
            return observed
        if not isinstance(missed, list):
            return observed
        low_text = (text or "").lower()
        caught_toks = {w for c in caught for w in re.findall(r"[a-z0-9]+", c.lower()) if len(w) > 2}
        from ..live_memory.review_infer import is_vent_shape as _ivs
        added = 0
        n = max([getattr(o, "line_no", 0) for o in observed], default=0)
        for cand in missed:
            if not isinstance(cand, str) or not cand.strip() or added >= 8:
                continue
            ctoks = {w for w in re.findall(r"[a-z0-9]+", cand.lower()) if len(w) > 2}
            if not ctoks:
                continue
            # ANTI-HALLUCINATION: most of the candidate's salient words must actually appear in the day.
            if len(ctoks & set(re.findall(r"[a-z0-9]+", low_text))) < max(1, len(ctoks) // 2):
                continue
            # already covered by a caught task (token overlap) -> skip (no dup)
            if len(ctoks & caught_toks) >= max(2, len(ctoks) - 1):
                continue
            # the downstream floors still gate it, but cheaply skip an obvious vent / third-party here
            if _ivs(cand) or _is_directed_question_to_named_person(cand):
                continue
            n += 1
            _o = OwnerObservedLine(line_no=n, text=cand.strip(), moat_task=True)
            observed.append(_o)
            caught_toks |= ctoks
            added += 1
        if added:
            self.glassbox.log("completeness_sweep_recovered", {"count": added})
        return observed

    def _resync_card_copy(self, cards) -> None:
        """M2: after humanize_cards rewrote each card's title/reason in the product voice, mirror
        that onto the durable owner-card record so GET /owner/cards shows the same human copy."""
        for c in cards:
            try:
                p = self.data_dir / "owner_cards" / f"{getattr(c, 'id', '')}.json"
                if not p.exists():
                    continue
                rec = json.loads(p.read_text(encoding="utf-8"))
                oc = rec.get("owner_card")
                if isinstance(oc, dict):
                    oc["title"] = c.title
                    oc["reason"] = c.reason
                    p.write_text(json.dumps(rec, indent=2, sort_keys=True), encoding="utf-8")
            except Exception:
                pass

    def set_autonomy_mode(self, mode: str) -> dict:
        """M3: set the global autonomy dial (full_send / regular / limited). Persisted across restarts."""
        from ..proactive.autonomy_mode import MODES as _M, DEFAULT_MODE as _D
        mode = mode if mode in _M else _D
        self._autonomy_mode = mode
        try:
            self._autonomy_mode_path.write_text(mode, encoding="utf-8")
        except Exception:
            pass
        return {"mode": mode}

    def get_autonomy_mode(self) -> dict:
        from ..proactive.autonomy_mode import MODES as _M, DEFAULT_MODE as _D
        return {"mode": getattr(self, "_autonomy_mode", _D), "modes": list(_M)}

    def _apply_autonomy_dial(self, card, line):
        """M3: adjust the brain's safe decision to the user's mode + earned trust, under the hard
        invariants (money/send/irreversible always confirm; low confidence drops a level). Money/send
        cards are invariant-locked inside autonomy_mode.adjust(), so they pass through unchanged here."""
        from ..proactive.autonomy_mode import adjust as _adj, task_type as _tt
        mode = getattr(self, "_autonomy_mode", "regular")
        cdict = {"disposition": getattr(card, "disposition", None),
                 "action": getattr(card, "action", None), "route": getattr(card, "route", None)}
        trust_tier = self.trust_ledger.tier(_tt(cdict))
        conf = getattr(card, "confidence", None)
        conf = 1.0 if conf is None else conf
        r = _adj(cdict, mode, trust_tier=trust_tier, confidence=conf)
        card.autonomy_mode = mode
        if r.get("changed") and r.get("disposition") != getattr(card, "disposition", None):
            nd = r["disposition"]
            if nd == "ask":
                # downgrade (Limited / low-confidence): become confirm-first, never auto-act
                card.disposition = "ask"
                card.execution = None
                card.reason = r.get("why") or card.reason
            elif nd == "do":
                # upgrade (Full-Send, or Regular with earned trust): flag for auto-run; the executor
                # block runs it and flips the disposition to do once it's actually executing.
                card.reason = r.get("why") or card.reason
                card.args = dict(getattr(card, "args", None) or {})
                card.args["autonomy_auto_run"] = True
        return card

    def _ensure_resolvable_ask(self, card, line, source):
        """WIRING CONTRACT (APPROVE->ACT): every confirm-first ASK the engine emits on the owner
        lane MUST carry a REAL resolvable ask_id at card.execution.ask_id AND be registered in
        proactive.pending — so POST /resolve FINDS it, resumes the paused goal, and actually runs
        it, exactly like the moat-rescue 'waiting' ask that already resolves.

        Without this, three shapes reached the board with execution=None and DEAD-ENDED on approve:
          1. an autonomy-dial DOWNGRADE (do -> ask): _apply_autonomy_dial strips execution but never
             registers a pending ask, so the ask had no id;
          2. the spine's reversible-task rescue (_generic_force_ask_card, action=confirm_owner_task);
          3. a routing chokepoint that nondeterministically left a site/web action as a generic
             confirm_owner_task instead of the browser round-trip.
        Route ALL of them through the SAME _confirm_task_goal funnel the moat rescue uses (a PAUSED,
        whitelisted goal + proactive._send_ask registration) and stamp the resolvable execution back
        onto the card.

        Scope is surgical + safety-preserving:
          * A GENUINE vent-adjacent (force_ask) card stays HELD display-only (the cardinal-sin floor);
            making a vent resolvable is out of scope and unsafe. BUT a brain "ask" decision (a real
            send/booking/lookup — action=draft_or_confirm_message et al.) is force_ask ONLY to block
            auto-act; it is flagged line.confirm_ask and IS a legitimate confirm-first ask that must
            resolve on an explicit YES. So the exclusion is: force_ask AND NOT confirm_ask. Defense in
            depth: a confirm_ask line whose text still reads as a vent shape is left held anyway.
          * NEVER money/blocked/remember — money is a hard wall (no pending, ask_id None; the safety
            corpus + test_public_backend_path/test_pending_persistence enforce it), remember writes
            memory not an ask.
          * A card that ALREADY carries a resolvable ask_id (the spine send/ask path, the moat
            rescue, browser_action, create_and_print) is left untouched — no double goal.
        """
        if card is None:
            return card
        if getattr(line, "force_ask", False) and not getattr(line, "confirm_ask", False):
            return card
        if getattr(line, "confirm_ask", False):
            from ..live_memory.review_infer import is_vent_shape as _ivs
            if _ivs(getattr(line, "text", "") or ""):
                return card   # defense in depth: never wire a vent-shape line, even if mis-flagged
        if getattr(card, "disposition", None) != "ask":
            return card
        # MODEL-AGNOSTIC: a real ask is defined by its FINAL disposition being "ask" (already filtered
        # to non-vent, non-money/blocked, non-remember above) — NOT by which label the model happened
        # to emit. "Already resolvable" means the ask_id is truthy AND actually registered in the
        # pending store; an ask_id that the spine feed set WITHOUT registering a pending entry (some
        # gemini/act classifications gate an ask but return no pending id), or a stale id from a
        # popped/resolved ask, is NOT resolvable and must be re-wired. So EVERY ask that isn't
        # genuinely resolvable gets a real ask_id + pending entry here, regardless of confirm_ask.
        execu = card.execution or {}
        _aid = execu.get("ask_id")
        if _aid and _aid in self.proactive.pending:
            return card
        # DETERMINISTIC + IDEMPOTENT ask id: keyed on (source, task text) so re-ingesting the SAME
        # line — or the PREVIEW (execute_actions=False) pass followed by the execute pass, or a
        # repeated preview as the composer re-sends — reuses the SAME pending ask instead of spawning
        # a duplicate goal/ask each time. If a prior pass already prepared it, just point the card at
        # that pending entry; otherwise prepare it once via the proven _confirm_task_goal funnel.
        _task = (getattr(card, "source_text", None) or getattr(line, "text", "") or "").strip()
        det_id = "ca_" + hashlib.sha256(f"confirm_ask|{source}|{_task}".encode("utf-8")).hexdigest()[:20]
        _p = self.proactive.pending.get(det_id)
        if isinstance(_p, dict):
            card.execution = {"decision": "ask", "goal_id": _p.get("goal_id") or det_id,
                              "ask_id": det_id, "goal_state": "waiting"}
            card.reason = card.reason or "confirm before I act"
            return card
        try:
            ask_id, goal_id, would = self._confirm_task_goal(line, goal_id=det_id)
        except Exception as exc:
            self.glassbox.log("ensure_resolvable_ask_error",
                              {"line": (getattr(line, "text", "") or "")[:140],
                               "error": str(exc)[:200]})
            return card
        card.execution = {"decision": "ask", "goal_id": goal_id, "ask_id": ask_id,
                          "goal_state": "waiting"}
        card.reason = card.reason or would or "confirm before I act"
        self.glassbox.log("ask_made_resolvable",
                          {"card_id": card.id, "ask_id": ask_id,
                           "action": getattr(card, "action", None),
                           "route": getattr(card, "route", None),
                           "line": (getattr(line, "text", "") or "")[:140]})
        return card

    async def _owner_ingest_inner(self, source, text, meta, execute_actions, observed=None):
        # PHASE 3 seam 1 (learns-you, before the brain): capture the wearer's stated anchors /
        # people / preferences (the decision pipeline drops pure facts as "ignore", so they'd be
        # lost) and apply retractions — a "never mind X" DELETEs the matching open loop instead of
        # letting a cancelled task linger. Best-effort: a memory hiccup must never break intake.
        if execute_actions and getattr(self, "context", None) is not None:
            try:
                ctx_trace = self.context.observe(text)
                if ctx_trace.get("captured") or ctx_trace.get("retraction"):
                    self.glassbox.log("context_observe", ctx_trace)
            except Exception as _cexc:
                self.glassbox.log("context_observe_error", {"error": str(_cexc)[:200]})
        raw_observed = self.owner_mode.observe(text)
        raw_lines = [l.text for l in raw_observed]
        self._silenced_count = 0   # M1d: vent/sarcasm/aside lines dropped during expansion -> counted in ignored_line_count
        self._already_open_spans = []   # re-mentioned tasks whose loop is still open -> echoed, not silenced
        decision_result = None
        use_decision_pipeline = (
            self.gateway.provider in {PROVIDER_OPENROUTER, PROVIDER_GEMINI}
            and (os.environ.get("ANTICIPY_PROACTIVE_DECISION_PIPELINE", "1") or "").strip().lower()
            not in {"0", "false", "no", "off"}
        )
        owner_context = None
        if use_decision_pipeline:
            # PHASE 2: read memory BEFORE the decision. Assemble the ONE ContextPack (loops first,
            # then the query-relevant standing facts/preferences), already char-budgeted to ~1600
            # for `decide`, and hand its budget-fit block to the brain so it decides WITH what it
            # already knows about the owner. Best-effort: a memory hiccup must never break ingest,
            # and an empty pack leaves the prompt byte-identical to the memory-blind path.
            try:
                pack = self.live_memory.build_context(text, purpose="decide")
                ctx_text = (getattr(pack, "text", "") or "").strip()
                if ctx_text:
                    owner_context = ctx_text[:1600]
            except Exception as exc:
                owner_context = None
                self.glassbox.log("proactive_decision_context_error", {"error": str(exc)[:240]})
            try:
                from ..proactive.decision_pipeline import decide_transcript
                decision_result = await decide_transcript(
                    self.gateway,
                    text,
                    source_truth_case_id=str((meta or {}).get("source_case") or "") or None,
                    owner_context=owner_context,
                )
            except Exception as exc:
                decision_result = None
                self.glassbox.log("proactive_decision_pipeline_error", {"error": str(exc)[:240]})
        if decision_result is not None and getattr(decision_result, "available", False):
            observed = self._build_from_proactive_decisions(decision_result)
            # CARDINAL-SIN FLOOR beats the pipeline: if the raw breath is a VENT ("ugh I'm fried,
            # but remind me to send Sarah the budget"), EVERY task pulled from it is vent-adjacent
            # and must stay HELD (surfaced, NEVER a tap-YES ask) — regardless of the per-task label
            # the (non-deterministic) brain returned (sometimes "ask", sometimes "act"). Force the
            # vent-held lever on and clear confirm_ask so _apply_force_ask coerces each to a held
            # display card and _ensure_resolvable_ask never wires it. Money stays blocked and
            # remember stays silent (the _apply_force_ask guards). This completes the existing
            # vent-adjacent backstop, which misses tasks the model already stripped of their vent
            # words. A CLEAN (non-vent) breath is untouched, so a real send still resolves. Erring
            # toward held is the safe, mission-#1 direction; the stub suite never runs this branch.
            from ..live_memory.review_infer import is_vent as _is_vent_src
            if _is_vent_src(text or ""):
                for _o in observed:
                    _o.force_ask = True
                    _o.confirm_ask = False
            self._silenced_count = sum(
                1 for d in (decision_result.decisions or []) if getattr(d, "decision", None) == "ignore"
            )
            # A repeat mention of a tracked task reads as "already_done" to the brain because the
            # open loop sits in its memory context — but if that loop is STILL OPEN, silence is
            # wrong: the owner should get the existing card back ("already on it"), never nothing.
            # A first-person completion CLAIM ("I sent mom the photos already, that's done") is
            # the owner CLOSING the loop, not re-mentioning it — route it to the closure pass
            # below instead of the already-on-it echo.
            self._already_open_spans = [
                span for span in (
                    (getattr(d, "evidence_span", "") or getattr(d, "task_text", "") or "").strip()
                    for d in (decision_result.decisions or [])
                    if getattr(d, "decision", None) == "ignore"
                    and getattr(d, "realness", "") in {"already_done", "real", "ambiguous",
                                                       "physical_only", "status_question"}
                ) if not _COMPLETION_CLAIM.search(span)
            ]
            # Per-decision drop trace: when a span the owner spoke produces no card, the
            # WHY must be reconstructable from glassbox alone (the summary counters above
            # cannot distinguish a vent from a mislabeled real task).
            self.glassbox.log("proactive_decisions_detail", {
                "decisions": [
                    {"decision": getattr(d, "decision", None),
                     "realness": getattr(d, "realness", None),
                     "span": ((getattr(d, "evidence_span", "") or getattr(d, "task_text", "") or "")[:120]),
                     "reason": (getattr(d, "reason", "") or "")[:160]}
                    for d in (decision_result.decisions or [])
                ],
            })
            self.glassbox.log("proactive_decision_pipeline", {
                "decisions": len(decision_result.decisions or []),
                "kept": len(observed),
                "wearer": decision_result.wearer,
                "source_case": (meta or {}).get("source_case"),
                "memory_ctx_chars": len(owner_context or ""),
            })
        else:
            # ONE extractor (FIX-01 step 2c, 2026-07-02): decision_pipeline is the only model brain.
            # When it can't run — stub provider, pipeline env-disabled, a live 429/outage — we degrade
            # to the DETERMINISTIC expansion, never to a second model. The floors (third-party silence,
            # vent-adjacent hold, noise drop) are model-independent by construction. (The old fallback,
            # extract.py "the MOAT", was deleted; A/B'd first: M1 6/6, M2 PASS, M3 ALL PASS with it off.)
            observed = self._deterministic_expand(raw_observed)
            self.glassbox.log("deterministic_expand", {
                "lines": len(raw_observed),
                "reason": "pipeline_unavailable" if use_decision_pipeline else "pipeline_disabled_or_stub",
            })
        decision_pipeline_owned = bool(decision_result is not None and getattr(decision_result, "available", False))
        # DETERMINISTIC VENT-ADJACENT BACKSTOP: when the moat fails to split a vent-prefixed line
        # ("ugh my brain is fried, but remind me to send Maya the email before Friday") into its
        # embedded obligation, the cardinal-sin guard would drop the whole line and the real task
        # is lost (the lone 'mixed' miss in the 10k cert). If a vented line carries a CONCRETE
        # directed task (a send to a NAMED person, or a pickup with a time), mark it force_ask so
        # the proven held-ask path surfaces it as a confirm-first ASK — never an auto-act, so the
        # vent floor is preserved. Tight signal: a pure emotional vent never qualifies.
        from ..live_memory.review_infer import is_vent as _is_vent
        from ..owner_mode import vent_adjacent_directed_task as _vent_adj
        from ..owner_mode import _split_multi_action as _split_actions
        # SPLIT-BEFORE-MERGE (audit fix): a vent-prefixed line carrying MULTIPLE tasks ("my day is
        # insane, remind me to call the dentist AND send Priya the deck") used to be marked force_ask as
        # ONE line — so the second task was buried and lost. Disaggregate first: if it splits into >=2
        # action clauses, surface each as its OWN confirm-first card (force_ask preserves the vent floor —
        # nothing auto-acts). Single-task vent lines keep the old behavior.
        _next_no = max([getattr(l, "line_no", 0) for l in observed], default=0)
        _rebuilt = []
        for _ln in observed:
            if (not getattr(_ln, "force_ask", False)
                    and _is_vent(_ln.text) and _vent_adj(_ln.text)):
                _parts = _split_actions(_ln.text)
                if len(_parts) >= 2:
                    for _p in _parts:
                        _next_no += 1
                        _nl = OwnerObservedLine(line_no=_next_no, text=_p)
                        _nl.force_ask = True
                        if getattr(_ln, "src_idx", None) is not None:
                            _nl.src_idx = _ln.src_idx
                        _rebuilt.append(_nl)
                    continue
                _ln.force_ask = True
            _rebuilt.append(_ln)
        observed = _rebuilt
        # RETRACTION FLOOR (clause-scoped, model-independent): drop any observed line the owner
        # took back in the same breath — "book the flight, actually scratch that", "confirm the
        # reservation... we might cancel". The whole-line vent guard (card_for_line's is_vent)
        # already catches a bare retraction, but a bundled/expanded line can carry the command
        # WITHOUT the retraction marker (the marker rode a sibling clause), so this floor checks
        # each line against its own source utterance. clause_is_retracted silences ONLY the
        # cancelled clause, so a sibling command ("email Priya the deck") still surfaces. Covers
        # both the deterministic held tasks and the live decision-pipeline decisions.
        from ..live_memory.review_infer import clause_is_retracted as _clause_retracted
        _kept_after_retraction = []
        for _ln in observed:
            _ctx = getattr(_ln, "original_text", None) or getattr(_ln, "text", "") or ""
            if _clause_retracted(getattr(_ln, "text", "") or "", _ctx):
                self._silenced_count += 1
                self.glassbox.log("retraction_silenced", {"line": (getattr(_ln, "text", "") or "")[:140],
                                                           "source": _ctx[:160]})
                continue
            _kept_after_retraction.append(_ln)
        observed = _kept_after_retraction
        # DETERMINISTIC MONEY BACKSTOP — money is the ONLY hard stop, so a directed money action must
        # NEVER be dropped or amount-stripped past the floor. The 20-life test caught the moat DROPPING
        # "Transfer 1.2 million ... to the new SPV ... do it now" ENTIRELY (no card at all — the worst
        # possible money outcome). If a RAW line carries a money SIGNAL + a transaction VERB and NO
        # surviving observed line still carries a money signal overlapping it (>=2 shared tokens), the
        # money line was dropped/stripped -> re-inject the RAW line so the spine's harm-line blocks it
        # (money can never auto-execute). Skips lines the moat already kept a money version of (no dup).
        from ..proactive.harm import _MONEY_SIGNAL as _MONEY_RE
        _MONEY_VERB_RE = re.compile(
            r"\b(?:pay|paid|pays|wire|wired|transfer|transferred|transferring|send|sent|sending|"
            r"refund|reimburse|credit|deposit|withdraw|venmo|zelle|paypal|charge|charged|remit|move|"
            r"moved|renew|renewing|spend|spending)\b", re.I)

        def _mtok(s):
            return {w for w in re.findall(r"[a-z0-9]+", (s or "").lower()) if len(w) > 2}

        if not decision_pipeline_owned:
            for _raw in raw_lines:
                if not (_MONEY_RE.search(_raw) and _MONEY_VERB_RE.search(_raw)):
                    continue
                _rtok = _mtok(_raw)
                _covered = any(_MONEY_RE.search(l.text) and len(_rtok & _mtok(l.text)) >= 2
                               for l in observed)
                if not _covered:
                    _n = max([getattr(l, "line_no", 0) for l in observed], default=0) + 1
                    observed.append(OwnerObservedLine(line_no=_n, text=_raw))
                    self.glassbox.log("money_backstop_reinjected", {"line": _raw[:160]})
        # COMPLETION-CLAIM CLOSURE (deterministic, both pipelines): the owner saying a tracked
        # task IS done — "I sent mom the photos already, that's done" — must CLOSE its card, not
        # echo it and never re-open it. Collected here from the RAW lines; the closure itself
        # (flip the durable record + its loop to done) runs after cards are built, where the
        # still-open record can be looked up.
        self._completion_claim_lines = [r for r in raw_lines if _COMPLETION_CLAIM.search(r)]
        if self._completion_claim_lines:
            _claim_toks = [_mtok(r) for r in self._completion_claim_lines]
            observed = [l for l in observed
                        if not any(len(_mtok(l.text) & ct) >= 2 for ct in _claim_toks)]
        # LINGERING-OBLIGATION BACKSTOP (deterministic, both pipelines): a real task voiced as
        # self-reproach — "I keep forgetting to cancel that gym membership" — reads as narration
        # to the model and gets silently dropped. If a raw line carries the lingering shape, is
        # not a vent-retraction, and no surviving line covers it (>=2 shared tokens), surface it
        # as a confirm-first ASK. Erring toward a benign ask is the safe direction; dropping the
        # owner's task is the cardinal 'you keep dropping my tasks' failure.
        for _raw in raw_lines:
            if not _LINGERING_OBLIGATION.search(_raw) or _COMPLETION_CLAIM.search(_raw):
                continue
            if _is_vent(_raw):
                continue
            _rtok = _mtok(_raw)
            if any(len(_rtok & _mtok(l.text)) >= 2 for l in observed):
                continue
            _n = max([getattr(l, "line_no", 0) for l in observed], default=0) + 1
            _nl = OwnerObservedLine(line_no=_n, text=_raw)
            _nl.force_ask = True
            observed.append(_nl)
            self.glassbox.log("lingering_obligation_rescued", {"line": _raw[:160]})
        # PRESERVE THE NO-BUY BOUND THROUGH THE MOAT (narrow + safe): the owner's explicit "...put it in
        # the cart, DON'T buy it" is a deliberate purchase ceiling that should keep a money-flavored
        # shopping line as a reversible CART-PREP, not the money wall. The moat sometimes rewords the
        # line and DROPS "don't buy it" -> it wrongly becomes BLOCKED/Left-for-you (surfaced by GUI
        # testing of "standing desk under $400 ... don't buy it"). ONLY when the whole day is a SINGLE
        # shopping line that lost a stated no-buy bound do we re-attach it (the unambiguous case);
        # multi-line days are left untouched so a no-buy on one item never leaks onto an unrelated
        # shopping/order line. Conservative: can only ever push toward NO-purchase, never toward buying.
        from ..owner_mode import _BROWSER as _BROWSER_RE, _NO_BUY as _NO_BUY_RE
        _shop = [l for l in observed if _BROWSER_RE.search(l.text)]
        if (len(observed) == 1 and len(_shop) == 1
                and _NO_BUY_RE.search("\n".join(raw_lines)) and not _NO_BUY_RE.search(_shop[0].text)):
            _shop[0].text = _shop[0].text.rstrip(". ") + " — don't buy it"
        observed, middle_trace = self._intent_resolve(observed, raw_lines)  # GATE MIDDLE-1: ranked recall
        # PHASE 3 seam 2 (learns-you, after transcript-scoped resolve): rewrite each task line with
        # what memory already knows — resolve a vague reference ("my usual" -> the stored oat latte),
        # disambiguate a person against the dossier (two Sams -> ask which / qualify the one), and
        # fill any slot we were already told (never re-ask). The transcript resolve only sees THIS
        # utterance; this reaches back into stored memory. Best-effort; empty context = no change.
        if getattr(self, "context", None) is not None:
            try:
                observed = self.context.resolve_observed(observed)
            except Exception as _rexc:
                self.glassbox.log("context_resolve_error", {"error": str(_rexc)[:200]})
        observed = self._consolidate_obligations(observed)   # F-012: one real obligation = one card
        observed = await self._semantic_dedup_same_source(observed)  # anti-spam: one obligation -> one card
        # NOTE: the old _completeness_sweep is retired — whole-day extraction (_expand_tasks_with_model)
        # is now the PRIMARY recall pass, so a second "what did we miss" pass only RE-ADDED the reminder
        # form of an already-caught task (duplicate-spam) after the dedup had run.
        captured_by_line: dict[int, dict] = {}
        for line in observed:
            captured_by_line[line.line_no] = self.live_memory.capturer.capture(
                line.text,
                source=source,
                meta={**meta, "owner_ingest": True, "line_no": line.line_no},
            )
        # MEMORY COMPLETENESS: a raw line the brain ignored for the ACTION path ("My landlord is
        # named Priya") is still knowledge the owner expects remembered — capture it into the
        # drawers too. capture() carries its own noise/vent/dedupe gates, so a vent or filler
        # line never becomes durable memory and an already-captured line never doubles.
        _kept_norm = {re.sub(r"\s+", " ", (l.text or "").strip().lower()) for l in observed}
        for _raw in raw_lines:
            if re.sub(r"\s+", " ", (_raw or "").strip().lower()) in _kept_norm:
                continue
            try:
                self.live_memory.capturer.capture(
                    _raw, source=source, meta={**meta, "owner_ingest": True, "dropped_line": True})
            except Exception as _cap_exc:  # pragma: no cover - memory must never break intake
                self.glassbox.log("raw_line_capture_error", {"error": str(_cap_exc)[:160]})

        cards: list[OwnerTaskCard] = []
        ignored = 0
        ignored_captures: list[tuple[dict | None, int]] = []
        for line in observed:
            preview = self.owner_mode.card_for_line(line, source)
            if preview is not None:
                existing = self._existing_owner_card(preview)
                if existing is not None:
                    cards.append(self._apply_force_ask(existing, line))
                    continue
            if execute_actions:
                card = await self._spine_card(line, source, meta)
            else:
                card = preview
                # PREVIEW == REALITY for the MONEY hard-stop: a money ACTION must show BLOCKED in preview
                # too, never remember/None/dropped (mirrors _spine_card's absolute money-block).
                if (_is_money_action(line.text) or getattr(line, "money_src", False)) and (
                        card is None or card.disposition != "blocked"):
                    card = self._money_blocked_card(line, source)
                # PREVIEW == REALITY: a vent-adjacent real task whose regex preview is empty (a bare
                # "call the dentist") still surfaces as a confirm-first ask, exactly as the execute
                # spine catches it — so a preview never shows FEWER tasks than the real run would.
                if card is None and getattr(line, "force_ask", False):
                    card = self._generic_force_ask_card(line, source)
                # PREVIEW == REALITY (moat_task): the model CONFIDENTLY caught a real task the regex
                # didn't shape ("remind me to refill the inhaler", "send the deck to Sequoia by EOD",
                # "cancel the WeWork"). On the EXECUTE path _spine_card's moat-task rescue surfaces it
                # as a confirm-first ask; PREVIEW must do the SAME or it silently DROPS real tasks and
                # shows fewer than the live run (the 'you keep dropping my tasks' bug, found by the
                # relentless bug-hunt: ~half of moat_task lines vanished in preview). Mirror the execute
                # conditions exactly: not a vent shape, and not the money wall (money stays blocked via
                # card_for_line's interlock above / handled below; never auto-acted).
                elif card is None and getattr(line, "moat_task", False):
                    from ..live_memory.review_infer import is_vent_shape as _ivs
                    if not _ivs(line.text):
                        _verdict = self.proactive.harm.assess(line.text, {})
                        _rev_ok = _is_explicit_reversible_task(line.text) and not _MONEY_SIGNAL.search(line.text)
                        if getattr(_verdict, "category", None) != "money" or _rev_ok:
                            card = self._generic_force_ask_card(line, source)
            # A vent-adjacent real task (force_ask) may be CAUGHT but NEVER auto-act in the heat:
            # downgrade any do/blocked-money to a confirm-first ASK and strip any execution. This
            # is the absolute lever that keeps a vent from ever producing an act (the cardinal sin).
            card = self._apply_force_ask(card, line)
            # CREATE + PRINT CHOKEPOINT: a 'make/print a sign' task -> GENERATE the real artifact and ask
            # before printing (a physical action). Runs on the line regardless of how the brain shaped it,
            # so a sign task the router would drop to a do-nothing confirm still reaches the create+print
            # round-trip. Excludes money (never) and vents (force_ask: held, not proactively executed).
            _sign_txt = getattr(line, "text", "") or ""
            if (execute_actions and not getattr(line, "force_ask", False)
                    and _SIGN_TASK.search(_sign_txt)
                    and not _DIGITAL_MEDIUM.search(_sign_txt)   # a digital-channel target -> not a physical sign
                    and not _MONEY_SIGNAL.search(_sign_txt)):
                self.glassbox.log("create_print_chokepoint", {"line": _sign_txt[:120]})
                card = await self._create_and_print_ask(line, source)
            # SITE-ACTION CHOKEPOINT (browser-only, 2026-06-26): "return that security camera on Amazon" /
            # "cancel my order on DoorDash" / "go to my Amazon and start a return" is a real action on a
            # logged-in SITE -> it MUST drive the BROWSER hand (the API arm is deleted; never route here to
            # api/execute_owner_task). _SITE_ACTION is site-anchored ("on/at <Site>" or "go to my <Site>"),
            # so vents ("return to bed", "cancel my plans") never match; money is still blocked. Fires only
            # when the line isn't already a good shape (None / generic confirm / the old api execute task).
            _act_txt = getattr(line, "original_text", None) or getattr(line, "text", "") or ""
            if (execute_actions and not getattr(line, "force_ask", False)
                    and (card is None or getattr(card, "action", None) in ("confirm_owner_task", "execute_owner_task"))
                    and (_SITE_ACTION.search(_act_txt) or _RETURN_TASK.search(_act_txt))
                    and not _MONEY_SIGNAL.search(_act_txt)):
                self.glassbox.log("site_action_chokepoint", {"line": _act_txt[:120]})
                card = self._browser_action_ask(line, source)
            # ROUTING CHOKEPOINT (reliability): a web-resolvable lookup that ANY internal path shaped as a
            # generic confirm (route=voice_text / action=confirm_owner_task) should still reach the HAND —
            # reroute it to the browser ask. A single catch-all so a web task can't dead-end as a
            # do-nothing confirm, regardless of which router produced it. Excluded by construction: vents
            # (force_ask), money (the _MONEY_SIGNAL guard + the absolute money-block upstream), and sends
            # (those are draft_or_confirm_message, not confirm_owner_task) — so this never routes a
            # vent/money/send to the browser arm. The safety corpus + done-gate guard it.
            if (execute_actions and card is not None
                    and getattr(card, "action", None) == "confirm_owner_task"
                    and not getattr(line, "force_ask", False)):
                from ..owner_mode import _BROWSER as _CB, _WEB_LOOKUP as _CWL
                _ctxt = (getattr(card, "source_text", None) or getattr(line, "text", "") or "")
                if (_CB.search(_ctxt) or _CWL.search(_ctxt)) and not _MONEY_SIGNAL.search(_ctxt):
                    self.glassbox.log("confirm_to_browser_chokepoint", {"line": _ctxt[:120]})
                    card = self._browser_action_ask(line, source)
            # M3: apply the user's autonomy DIAL (Full-Send/Regular/Limited) + earned trust — but NEVER
            # on a vent-adjacent (force_ask) card (acting on a vent is the cardinal sin). Money/send are
            # invariant-locked inside the dial, so they pass through unchanged (always confirm).
            if execute_actions and card is not None and not getattr(line, "force_ask", False):
                card = self._apply_autonomy_dial(card, line)
            # M3 EXECUTOR: a card the dial pre-approved (Full-Send, or Regular with earned trust) auto-runs
            # now — for a reversible web ask that means running the browser + texting the result, exactly
            # like a YES. Money/send are invariant-locked and never carry the auto_run flag.
            if (execute_actions and card is not None
                    and (getattr(card, "args", None) or {}).get("autonomy_auto_run")
                    and getattr(card, "action", None) == "browser_action"
                    and getattr(card, "disposition", None) == "ask"
                    and not getattr(line, "force_ask", False)):
                p = self.proactive.pending.pop(card.id, None)
                self.proactive._persist_pending()
                card.disposition = "do"
                card.reason = card.reason or "I'm handling this for you (reversible, no money)"
                # PERSIST the record BEFORE dispatching the async hand, so _land_browser_result_on_card
                # has a record to write the outcome onto. (Bug: this branch's `continue` skipped
                # _persist_card, so owner web-task results landed nowhere and the card stayed a stub —
                # the rung-A "owner-flow drives the hand but nothing shows" gap.)
                self._persist_card(card, source, execute_actions, captured_by_line.get(line.line_no))
                self._resolve_browser_card_record(card.id, True)
                asyncio.create_task(self._run_browser_and_confirm(
                    (p or {}).get("browser_task") or (p or {}).get("action") or line.text,
                    (p or {}).get("browser_url") or "https://www.google.com", card.id))
                self.glassbox.log("autonomy_auto_run",
                                  {"card_id": card.id, "mode": getattr(self, "_autonomy_mode", "regular")})
                cards.append(card)
                continue
            # BROWSER ACTION (Omar's centerpiece): a web task ("find me a standing desk on Amazon")
            # becomes a TEXTED plain-English ask; on YES (app or SMS) the browser agent runs on the
            # real site and texts the result. Money browser cards stay blocked (never reach here as
            # a do/ask). Only on the real execute path; not for a vent-adjacent held card.
            if (execute_actions and card is not None
                    and getattr(card, "route", None) == "browser"
                    and getattr(card, "disposition", None) not in ("blocked", "remember")
                    and getattr(card, "action", None) != "browser_action"
                    and not (getattr(card, "args", None) or {}).get("resolved_cart")
                    and not getattr(line, "force_ask", False)):
                # An UNRESOLVED web task (no confident item/store) becomes ONE deterministic
                # confirm-first browser ask. A RESOLVED cart (args.resolved_cart) skips this and
                # auto-prepares the cart (Omar's "prepare when confident"). One web task -> one ask;
                # the deterministic ask id keeps re-ingest idempotent. See docs/agent_os/FAILURES.md F-011.
                card = self._browser_action_ask(line, source)
                # Persist the ask record so a later resolve(YES) -> _run_browser_and_confirm ->
                # _land_browser_result_on_card has a durable record to write the outcome onto.
                self._persist_card(card, source, execute_actions, captured_by_line.get(line.line_no))
                cards.append(card)
                continue
            if card is None:
                # A self-reminder the spine silences NOW ("take my meds at 9pm") is still a real
                # TIMED reminder when the capture grounded a remind_ts: show it as Ready and KEEP
                # its loop active so the trigger fires it — never deactivate it (that silently
                # killed the 2:45-call use case). Only fires on execute (preview has no capture).
                if execute_actions:
                    rcard = self._timed_reminder_card(
                        line, source, captured_by_line.get(line.line_no))
                    if rcard is not None:
                        self.glassbox.log("timed_reminder_kept",
                                          {"line": line.text[:140],
                                           "remind_ts": rcard.args.get("remind_ts")})
                        cards.append(rcard)
                        continue
                ignored += 1
                if execute_actions:
                    ignored_captures.append((captured_by_line.get(line.line_no), line.line_no))
                continue
            # WIRING CONTRACT (APPROVE->ACT): before we persist, guarantee that every confirm-first
            # ASK carries a REAL resolvable ask_id + a registered pending entry, so the app's YES
            # actually runs it. Autonomy-dial downgrades and generic confirm_owner_task cards
            # otherwise reach the board with execution=None and dead-end on approve. Money/blocked/
            # remember + vent-adjacent (force_ask) cards are deliberately excluded (hard wall / held).
            # WIRING CONTRACT runs in BOTH preview and execute: the composer's typed send AND the
            # preview both render a "Go ahead" chip on every ask card, and the app resolves it off
            # card.execution.ask_id — so a preview ask with execution=None dead-ends exactly like an
            # execute one did. The prepared ask is idempotent (deterministic id) and NEVER auto-acts;
            # only an explicit /resolve drives it. (Money/blocked, remember, and vent-adjacent
            # force_ask cards are excluded inside _ensure_resolvable_ask.)
            existing = self._existing_owner_card(card)
            if existing is not None:
                # A dedupe HIT (a prior preview / re-ingest of the same line) must NOT return a stale,
                # non-resolvable ask: re-wire the RETURNED card so the app's YES resolves it too.
                existing = self._ensure_resolvable_ask(existing, line, source)
                cards.append(existing)
                continue
            card = self._ensure_resolvable_ask(card, line, source)
            persisted = self._persist_card(card, source, execute_actions,
                                           captured_by_line.get(line.line_no))
            if not persisted:
                # vent caught by the persist-side cardinal-sin guard: nothing durable was
                # written, so it is not a card — treat it as ignored (no active memory).
                ignored += 1
                if execute_actions:
                    ignored_captures.append((captured_by_line.get(line.line_no), line.line_no))
                continue
            cards.append(card)

        # Do not close "ignored" captures while later lines in the same messy
        # transcript may still need them as memory context. A line like "I was
        # looking at X" is not a card by itself, but it can be the grounding for
        # "cart that thing" ten seconds later.
        if execute_actions:
            for capture_result, _line_no in ignored_captures:
                self._sync_capture_result_status(capture_result, "ignored")

        # "Already on it" echo: a task the brain ignored as already_done whose durable loop is
        # still open surfaces its EXISTING card, so a repeat mention never returns silence.
        _echo_ids = {getattr(c, "id", None) for c in cards}
        for _span in getattr(self, "_already_open_spans", []) or []:
            _echo = self._open_card_for_text(_span)
            if _echo is not None and _echo.id not in _echo_ids:
                cards.append(_echo)
                _echo_ids.add(_echo.id)
                self.glassbox.log("owner_card_already_open_echo",
                                  {"span": _span[:120], "card_id": _echo.id})

        # COMPLETION-CLAIM CLOSURE: the owner said a tracked task IS done ("I sent mom the photos
        # already, that's done") — close the matching still-open card + its loop, and hand the
        # closed card back so the surface can acknowledge instead of going silent or re-nagging.
        # UPDATE-SUPERSEDE: a card born from an UPDATE line ("make it Thursday") replaces the
        # older open card it revises — the old one flips to superseded, never a duplicate pair.
        for _claim in getattr(self, "_completion_claim_lines", []) or []:
            _open = self._open_card_for_text(_claim)
            if _open is None:
                self.glassbox.log("completion_claim_no_match", {"line": _claim[:160]})
                continue
            if self._complete_owner_card(_open.id, reason="owner_said_done", spoken=_claim):
                if _open.id not in _echo_ids:
                    _open.status = "done"
                    _ex = getattr(_open, "execution", None)
                    if isinstance(_ex, dict):
                        _ex["goal_state"] = "done"
                        _ex["ask_id"] = None
                    elif _ex is not None:
                        _ex.goal_state = "done"
                        _ex.ask_id = None
                    cards.append(_open)
                    _echo_ids.add(_open.id)
        for _line in observed:
            _lt = " ".join(filter(None, [getattr(_line, "text", "") or "",
                                         getattr(_line, "original_text", "") or ""]))
            if not _TASK_UPDATE_MARKER.search(_lt):
                self.glassbox.log("update_supersede_skip", {"line": _lt[:160]})
                continue
            _new = next((c for c in cards
                         if getattr(c, "source_text", "") == _line.text
                         or len({w for w in re.findall(r"[a-z0-9]+", (getattr(c, 'source_text', '') or getattr(c, 'title', '') or '').lower()) if len(w) > 2}
                                & {w for w in re.findall(r"[a-z0-9]+", _line.text.lower()) if len(w) > 2}) >= 2), None)
            if _new is None:
                self.glassbox.log("update_supersede_no_new", {"line": _lt[:160]})
                continue
            _span = " ".join(filter(None, [
                _line.text, getattr(_line, "original_text", "") or "",
                getattr(_new, "title", "") or "", getattr(_new, "source_text", "") or ""]))
            _old = self._open_card_for_text(_span, exclude_id=getattr(_new, "id", ""),
                                            anchor_ok=True)
            if _old is not None and _old.id != _new.id:
                self._complete_owner_card(_old.id, state="superseded",
                                          reason="revised_by_newer_card", spoken=_line.text)
            else:
                self.glassbox.log("update_supersede_no_old", {"line": _lt[:160]})

        self.glassbox.log(
            "owner_ingest",
            {"source": source, "lines": len(observed), "cards": len(cards),
             "ignored": ignored, "execute_actions": execute_actions},
        )
        ignored += getattr(self, "_silenced_count", 0)   # M1d: include vent/sarcasm/aside lines dropped during expansion
        # M2: render every card in the product voice — no engine template/ID/arrow reaches the user,
        # on BOTH this response AND the durable board (GET /owner/cards reads the persisted records).
        try:
            from . import voice as _voice
            await _voice.humanize_cards(self.gateway, cards)
            self._resync_card_copy(cards)
        except Exception as _copy_exc:
            self.glassbox.log("humanize_cards_error", {"error": str(_copy_exc)})
        result = OwnerIngestResult(source=source, observed_lines=observed, cards=cards,
                                   ignored_line_count=ignored)
        out = result.model_dump(mode="json")
        out["middle_trace"] = middle_trace   # GATE MIDDLE-1 proof (captured memories + resolutions)
        if decision_result is not None and getattr(decision_result, "available", False):
            out["brain_decisions"] = decision_result.to_wire()
        # Autonomy mode per card (packet 02): the chosen mode + why, for product + certification.
        from ..proactive.autonomy import classify_autonomy
        from ..proactive.autonomy_mode import adjust as _dial_adjust, task_type as _dial_task_type
        from ..proactive.follow_up import plan_follow_up
        import time as _time
        _now = _time.time()
        # FOLLOW-UP SCHEDULING (packet 06): an obligation whose outcome depends on someone else gets a
        # follow-up check, surfaced on the card AND scheduled as a durable, fireable open_loop so the
        # SAME trigger system that fires reminders delivers the nudge at when_ts. Conservative —
        # never for vents/prefs/money. Idempotent: a re-ingest of the same line reuses the existing
        # scheduled when_ts (no churn) and never double-schedules (stable loop id per card).
        for c in out.get("cards", []):
            fu = plan_follow_up(c, _now)
            if fu:
                # write/refresh the fire-site loop FIRST so the persisted (preserved) when_ts is
                # the one surfaced on the card — the card and the ledger never disagree.
                fu = self._schedule_follow_up(c, fu, _now)
                c["follow_up"] = fu
        # NO-SELF-ATTESTATION INVARIANT (cert floor): a card may NOT be 'done'/auto-acted without
        # independent read-back proof. If an action path emitted a do-card with empty proof (a rare
        # nondeterministic slip), it is NOT done — downgrade to a confirm-first ask so "done" always
        # means proven. Structurally prevents the "auto-done with no proof" critical.
        for c in out.get("cards", []):
            # ONLY a card that CLAIMS it executed (decision==act) without proof is a violation.
            # A held/vent-adjacent card (execution None / decision != act) is legitimately proof-less
            # and must NOT be touched (flipping it would make a vent produce an ask — a cardinal breach).
            # An AUTO_DO_WITH_OPT_OUT chore is legitimately IN FLIGHT (started, not done) — it is not
            # claiming a verified 'done', so it is exempt (flipping it back to an ask is the exact
            # approval-machine bug the autonomy law forbids).
            if (c.get("execution") or {}).get("opt_out"):
                continue
            # A card the OWNER just closed ("I sent it already, that's done") is done on their
            # say-so — it is their own task, not the agent attesting to its own work.
            if c.get("status") in ("done", "superseded", "stopped", "declined"):
                continue
            if (c.get("execution") or {}).get("decision") == "act" and not c.get("proof"):
                c["disposition"] = "ask"
                ex = dict(c.get("execution") or {})
                ex["decision"] = "ask"
                c["execution"] = ex
                c["status"] = "open"
                c["reason"] = "prepared, but I couldn't verify it was done — confirm before relying on it"
        autonomy = []
        for c in out.get("cards", []):
            a = classify_autonomy(c)
            c["autonomy_mode"] = a["mode"]
            c["autonomy_why"] = a["why"]
            # SEAM 2: PERSIST autonomy_mode (+ why) onto the DURABLE card record. classify_autonomy
            # runs here, AFTER _persist_card wrote the record — so the record (what GET /owner/cards
            # returns, which the UI board reads) carried autonomy_mode=None. Stamp it onto the record
            # now so the board can pick the lane/verb (the "On it — you can stop me" vs Yes/Not-now
            # split). Best-effort: a missing record (preview / replay) is simply skipped.
            if execute_actions:
                self._stamp_autonomy_on_record(c.get("id"), a["mode"], a["why"])
            # full classification proof (packet 02): input span, chosen mode, REJECTED modes,
            # action plan, result, proof types.
            autonomy.append({
                "input_span": (c.get("source_text") or "")[:120],
                "chosen_mode": a["mode"], "why": a["why"], "rejected_modes": a["rejected"],
                "action_plan": {"route": c.get("route"), "action": c.get("action")},
                "result": c.get("disposition"),
                "proof": [p.get("type") for p in (c.get("proof") or []) if isinstance(p, dict)],
            })
        out["middle_trace"]["autonomy"] = autonomy
        return out

    def _stamp_autonomy_on_record(self, card_id: str | None, mode: str, why: str) -> None:
        """Write the classified autonomy mode (+why) onto the durable owner-card record so
        GET /owner/cards (the board source of truth) carries it. Idempotent; best-effort."""
        if not card_id:
            return
        path = self.data_dir / "owner_cards" / f"{card_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(record, dict):
            return
        record["autonomy_mode"] = mode
        if isinstance(record.get("owner_card"), dict):
            record["owner_card"]["autonomy_mode"] = mode
            record["owner_card"]["autonomy_why"] = why
        try:
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return

    def _persist_card(self, card: OwnerTaskCard, source: str, execute_actions: bool,
                      capture_result: dict | None = None) -> bool:
        """Write one card into the real memory drawers and its durable goal-shaped
        record, mirroring REAL execution: done requires a goal that finished with
        proof (or a read-back memory write) — a card that never ran stays open.

        Returns False (and persists NOTHING durable) when the card is a vent that
        slipped through as a 'remember' shape — the cardinal-sin guard, defense in depth.
        """
        from ..live_memory.review_infer import is_vent_shape

        # CARDINAL-SIN GUARD (defense in depth): a 'remember' card writes the spoken line
        # into the ACTIVE profile drawer unconditionally. A vent ("I hate this", "kill me",
        # "I could scream", "I should just move to a beach") must NEVER become a durable
        # active profile memory — even in preview, persisting it is the cardinal-sin echo.
        # _card_for_line already drops vents, so this only fires if a remember card reaches
        # here some other way; it then persists nothing (no profile write, no record). Uses
        # the _VENT-family shape (not the countermand) so a genuine preference phrased with
        # "don't" ("I prefer you don't call after 9") is still remembered.
        if card.disposition == "remember" and is_vent_shape(card.source_text):
            self.glassbox.log("vent_not_persisted",
                              {"owner_card_id": card.id, "source": source,
                               "source_text": card.source_text})
            return False
        gateway_event_id = _GATEWAY_EVENT_ID.get()
        fields = {
            "owner_card_id": card.id,
            "owner_card_dedupe_key": _owner_card_dedupe_key(card),
            "source": source,
            "line_no": card.line_no,
            "source_text": card.source_text,
            "disposition": card.disposition,
            "route": card.route,
            "action": card.action,
            "args": card.args,
            "reason": card.reason,
        }
        if gateway_event_id:
            fields["gateway_event_id"] = gateway_event_id
        if card.disposition == "remember":
            item = self.memory.profile.write_text(
                card.source_text,
                fields=fields,
                provenance=f"owner:{source}",
                confidence=card.confidence,
                importance=0.7,
                status="active",
            )
            drawer = self.memory.profile
            drawer_name = "profile"
        else:
            # the drawer remembers the person's actual words — synthetic card titles
            # ("Owner task: ...") in open loops polluted the planner's inject context
            # with tokens the speaker never said (browse steps grew on unrelated goals)
            captured_loop = (capture_result or {}).get("item")
            loop_fields = {**fields, "title": card.title}
            # Spine-only "call me at 2:45": when capture did NOT shape this line into a
            # commitment loop, THIS owner-card loop is the only fireable row — carry the
            # call-escalation so it RINGS, not texts. (On the deduped-echo branch below the
            # loop is stamped fired_at and never fires, so this is a harmless no-op there.)
            from ..live_memory.capture import wants_call
            if wants_call(card.source_text or ""):
                loop_fields["channel_pref"] = "call"
            # DEDUPE — one dictated task -> exactly ONE active+fireable open_loop.
            # The capture path (capturer.capture, run first in owner_ingest) already wrote
            # a RAW open_loop for this same line whenever the line is a commitment shape; it
            # carries the spoken due/remind grounding and is the live reminder. This
            # card-persist path also writes an open_loop (the card-board record). With BOTH
            # active for the same task the backlog showed it twice and the trigger (which
            # scans every active loop) could fire two reminders. FIX: when a raw capture
            # loop already exists for this line, designate IT as the single authoritative
            # active+fireable row and mark THIS owner-card loop a dedupe echo of it — kept
            # for the card board + status sync, but suppressed from the backlog and stamped
            # fired_at so it can never double-fire the trigger. When no raw capture loop
            # exists (a line the spine caught that capture did not shape as a commitment),
            # this owner-card loop is the only row and surfaces/fires normally.
            has_capture_loop = getattr(captured_loop, "kind", None) == "open_loop"
            if has_capture_loop:
                # explicit linkage via the capture path's stable content key (capture.py),
                # not just text equality — the two writers now coordinate on a shared key
                loop_fields["deduped_by_capture_loop"] = captured_loop.id
                loop_fields["capture_key"] = (captured_loop.fields or {}).get("capture_key")
                loop_fields.setdefault("fired_at",
                                       dt.datetime.now(dt.timezone.utc).timestamp())
            item = self.memory.open_loops.write_text(
                card.source_text,
                # CONTENT-STABLE id (audit fix): re-ingesting the same utterance+action upserts THIS row
                # instead of minting a new one — the cause of "send sarah the deck" piling up 36x.
                id="ownerloop:" + _owner_card_dedupe_key(card),
                fields=loop_fields,
                provenance=f"owner:{source}",
                confidence=card.confidence,
                importance=0.85,
                status=("open" if card.disposition == "do" else "waiting"),
            )
            drawer = self.memory.open_loops
            drawer_name = "open_loops"
        card.proof.append({"type": "memory_write", "drawer": drawer_name, "memory_id": item.id})
        # read-back: a write only counts once the drawer returns it by id
        back = drawer.get(item.id)
        if back is not None:
            card.proof.append({"type": "memory_read_back", "memory_id": back.id, "text": back.text})

        record_path = self.data_dir / "owner_cards" / f"{card.id}.json"
        state, steps, goal_proof = "open", [], {}
        execution = card.execution or {}

        if card.disposition == "remember" and back is not None:
            # the card's action IS the memory write; the read-back makes it
            # executed-with-proof (no orchestrator involved, nothing external)
            state = "done"
            goal_proof = {"memory_id": item.id, "read_back": back.text}
        elif card.disposition == "blocked":
            # money/wall: NEVER executes — and never enters proactive.pending,
            # where a YES would start_goal it. The harm-line is final; the card
            # stays a ledgered open loop prepared up to the wall.
            card.execution = {"decision": "blocked", "goal_id": None, "ask_id": None,
                              "reason": "hard stop: money/wall cards never execute"}
            state = "blocked" if execute_actions else "open"
            if execute_actions:
                self.glassbox.log("blocked", {"goal_id": card.id, "category": "money",
                                              "reason": card.reason, "action": card.source_text})
        elif execution.get("opt_out"):
            # AUTO_DO_WITH_OPT_OUT (SEAM 1): a reversible external-service chore that STARTED (not an
            # approval ask). There is no paused goal — the work is in flight (live) or prepared
            # (mock); the card carries its own preparing/running state. Honor it and record a START
            # receipt so the no-self-attestation invariant (which flips a proof-less act->ask) does
            # NOT mistake an in-flight chore for an unproven 'done'. The browser arm lands the real
            # receipt on the record when it finishes (live), exactly like the confirm-first arm.
            state = card.status or execution.get("goal_state") or "preparing"
            card.proof.append({"type": "opt_out_started",
                               "goal_id": execution.get("goal_id"),
                               "state": state, "stop_id": (card.args or {}).get("stop_id")})
            card.proof.append({"type": "engine_execution", **execution})
        elif execution:
            # the spine already ran this line (F17 one brain, _spine_card): the
            # record mirrors what it actually DID. Spine refusal (ignore/suppressed/
            # deferred) has no goal -> the card stays a durable open loop and the
            # instrument shows no act.
            goal = self.store.load(execution["goal_id"]) if execution.get("goal_id") else None
            if goal is not None:
                execution["goal_state"] = goal.state.value
                steps = [s.model_dump(mode="json") for s in goal.steps]
                goal_proof = goal.proof or {}
                state = goal.state.value  # done only when every step carried proof
                card.proof.extend(_card_step_receipts(steps))
                if execution.get("ask_id") or execution.get("decision") in ("ask", "held"):
                    state = "waiting"
                    self._owner_card_goals[goal.id] = {"record_path": record_path,
                                                       "card_id": card.id}
            card.proof.append({"type": "engine_execution", **execution})

        card.status = state
        if drawer_name == "open_loops":
            self._sync_owner_loop_status(card.id, state)
        captured_item = (capture_result or {}).get("item")
        if getattr(captured_item, "kind", None) == "open_loop":
            status = _status_for_open_loop(state)
            should_sync_capture = state != "done" or not _steps_create_open_loop(steps)
            if should_sync_capture and self._sync_open_loop_item_status(captured_item.id, state, card_id=card.id):
                card.proof.append({
                    "type": "capture_memory_status",
                    "memory_id": captured_item.id,
                    "status": status,
                })
        # Durable card record, shaped like a goal (id/intent/steps/state) so the
        # factory's existing run collector and scorer read owner cards unchanged.
        card.proof.append({"type": "card_record", "path": str(record_path)})
        owner_card_payload = card.model_dump(mode="json")
        if gateway_event_id:
            owner_card_payload["gateway_event_id"] = gateway_event_id
        record = {
            "id": card.id,
            "dedupe_key": _owner_card_dedupe_key(card),
            "gateway_event_id": gateway_event_id,
            "intent": card.action,
            "description": f"{card.title} — {card.source_text}",
            "state": state,
            "steps": steps,
            "proof": goal_proof,
            "owner_card": owner_card_payload,
        }
        record_path.parent.mkdir(parents=True, exist_ok=True)
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        return True

    def _open_card_for_text(self, span: str, exclude_id: str = "",
                            anchor_ok: bool = False) -> OwnerTaskCard | None:
        """Newest STILL-OPEN durable card matching a re-mentioned task span (token overlap).
        With anchor_ok, one shared DISTINCTIVE token (a long content word like 'dentist') is
        enough — an update line often shares only the subject noun with the card it revises."""
        toks = {w for w in re.findall(r"[a-z0-9]+", (span or "").lower()) if len(w) > 2}
        if not toks:
            return None
        need = 2 if len(toks) >= 2 else 1
        cards_dir = self.data_dir / "owner_cards"
        if not cards_dir.is_dir():
            return None
        for path in sorted(cards_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(record, dict):
                continue
            if exclude_id and path.stem == exclude_id:
                continue
            state = str(record.get("state") or "").lower()
            if state not in {"open", "waiting", "pending", "ask"}:
                continue
            record_card = record.get("owner_card")
            if not isinstance(record_card, dict):
                continue
            hay = f"{record_card.get('title', '')} {record_card.get('source_text', '')}".lower()
            card_toks = {w for w in re.findall(r"[a-z0-9]+", hay) if len(w) > 2}
            shared = toks & card_toks
            if len(shared) < need and not (
                anchor_ok and any(len(w) >= 5 and w not in _GENERIC_ANCHOR_WORDS for w in shared)
            ):
                continue
            try:
                card_data = {**record_card, "status": state}
                execution = card_data.get("execution")
                if isinstance(execution, dict):
                    card_data["execution"] = {
                        **execution,
                        "goal_state": state,
                        "ask_id": execution.get("ask_id") if state == "waiting" else None,
                    }
                return OwnerTaskCard.model_validate(card_data)
            except Exception:
                continue
        return None

    def _existing_owner_card(self, card: OwnerTaskCard) -> OwnerTaskCard | None:
        """Return the durable card for an accidental replay, before re-executing."""
        key = _owner_card_dedupe_key(card)
        cards_dir = self.data_dir / "owner_cards"
        if not cards_dir.is_dir():
            return None
        for path in sorted(cards_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            record_card = record.get("owner_card") if isinstance(record, dict) else None
            if not isinstance(record_card, dict):
                continue
            record_key = record.get("dedupe_key")
            if not record_key:
                try:
                    record_key = _owner_card_dedupe_key(OwnerTaskCard.model_validate(record_card))
                except Exception:
                    continue
            if record_key != key:
                continue
            card_data = {**record_card, "status": record.get("state") or record_card.get("status") or "open"}
            execution = card_data.get("execution")
            if isinstance(execution, dict):
                card_data["execution"] = {
                    **execution,
                    "goal_state": card_data["status"],
                    "ask_id": execution.get("ask_id") if card_data["status"] == "waiting" else None,
                }
            return OwnerTaskCard.model_validate(card_data)
        return None

    async def owner_onboard(self, body: OwnerOnboardingIn) -> dict:
        """Write first-run onboarding into the same memory ledger the engine uses."""
        plan = build_onboarding_plan(body)
        written = []
        for mem in plan.memories:
            item = self._upsert_onboarding_memory(mem, plan.source)
            written.append({"drawer": mem.drawer, "memory_id": item.id, "text": item.text,
                            "status": item.status, "fields": item.fields})
        self._close_connected_setup_loops(plan.memories)

        self.glassbox.log(
            "owner_onboarding",
            {"source": plan.source, "written": len(written),
             "missing_connections": plan.missing_connections},
        )
        return {"source": plan.source, "written": written,
                "missing_connections": plan.missing_connections}

    async def run_onboarding_call(self, dossier: dict, *, to: str | None = None,
                                  max_questions: int = 5, answers: dict | None = None) -> dict:
        """Initiate the outbound onboarding/gap-filling CALL for a built inhale dossier and close
        the scrape<->call loop: plan the ranked gap-questions (clarify, over the OWNER dossier),
        DIAL the owner (CallChannel.send — mock records / live places a real Twilio call), run the
        warm OnboardingCallBrain over those questions, and write the answers back so the dossier and
        first cards are re-aimed. Mock-safe + deterministic; live is a one-flag flip
        (ANTICIPY_CHANNELS_MODE=live). Delegates to onboarding.call_out."""
        from ..onboarding.call_out import run_onboarding_call as _run_onboarding_call
        result = await _run_onboarding_call(self, dossier, to=to, max_questions=max_questions,
                                            answers=answers)
        # CLOSE THE ONBOARDING->BOARD LOOP: the deep flow (inhale + dossier + call answers) wrote only
        # to the memory DRAWERS — owner_cards stayed empty, so a fresh user who finished onboarding saw
        # a blank action board. Derive the FIRST cards from what was actually learned (the concrete
        # people + systems in the dossier) and route them through the SAME durable CARD path
        # (_persist_card) the ambient lane uses, so GET /owner/cards returns them. Honest by
        # construction: cards are grounded ONLY in learned nouns — nothing readable -> no cards, never a
        # fabricated one. Best-effort: a hiccup here never breaks a call that already succeeded.
        if result.get("initiated") or result.get("answers"):
            try:
                first = self._emit_onboarding_first_cards(dossier, result)
                if first:
                    result["first_cards"] = first
            except Exception as _fc_exc:
                self.glassbox.log("onboarding_first_cards_error", {"error": str(_fc_exc)[:200]})
        return result

    def _emit_onboarding_first_cards(self, dossier: dict, call_result: dict) -> list[dict]:
        """Derive a fresh user's FIRST action-board cards from what onboarding actually LEARNED and
        persist them through the durable card path so GET /owner/cards returns them.

        HONEST + MINIMAL: each card is grounded in a concrete learned NOUN — an important person or a
        real system (act_on_site) the inhale/dossier surfaced. A dossier with no such nouns yields ZERO
        cards (never a fabricated one). Each card is a confirm-first ASK made resolvable (via the same
        _confirm_task_goal funnel), so a YES on the board actually tracks it — no dead first cards."""
        inner = dossier.get("dossier") if isinstance(dossier, dict) and isinstance(dossier.get("dossier"), dict) else (
            dossier if isinstance(dossier, dict) else {})
        if not isinstance(inner, dict):
            return []
        source = "onboarding_first_card"
        candidates: list[str] = []
        seen: set[str] = set()

        def _add(task: str) -> None:
            key = " ".join((task or "").lower().split())
            if task and key not in seen:
                seen.add(key)
                candidates.append(task)

        for person in (inner.get("people") or []):
            name = (person.get("name") if isinstance(person, dict) else str(person or "")).strip()
            if name:
                _add(f"help you keep up with {name}")
        for site in (inner.get("act_on_sites") or []):
            name = (site.get("name") if isinstance(site, dict) else str(site or "")).strip()
            if name:
                _add(f"take a first look at {name} and flag what needs your attention")

        emitted: list[dict] = []
        for i, task in enumerate(candidates[:5]):
            line = OwnerObservedLine(line_no=i + 1, text=task)
            card = OwnerTaskCard(
                source=source, line_no=line.line_no, source_text=task,
                title=f"Want me to {task}?", disposition="ask", route="voice_text",
                action="confirm_owner_task", args={"task_text": task, "from_onboarding": True},
                confidence=0.7,
                reason="a first thing I can start on from your setup — confirm and I'll track it")
            card = self._ensure_resolvable_ask(card, line, source)
            if self._persist_card(card, source, True, None):
                emitted.append({"id": card.id, "title": card.title,
                                "ask_id": (card.execution or {}).get("ask_id")})
        self.glassbox.log("onboarding_first_cards",
                          {"emitted": len(emitted), "candidates": len(candidates)})
        return emitted

    # ---- STATED onboarding basics (name / summary / phone / timezone / trust dial / always-ask) ----
    # The onboarding form's basics live in the DURABLE profile memory drawer — the same drawer the
    # brain reads — not an ephemeral local file. Before this, the hosted app saved them to a per-
    # request JSON store that Vercel serverless throws away, so a fresh user's basics vanished and
    # the assistant never learned them. One idempotent "owner_basics" record round-trips exactly and
    # carries a plain-language line so the facts are brain-visible; `fields['timezone']` also feeds
    # the owner-timezone reader.
    _OWNER_BASICS_KEY = "phase_zero:owner_basics"

    def _owner_basics_item(self):
        """The single durable 'stated basics' record in the profile drawer, or None."""
        for item in reversed(self.memory.profile.all()):
            if str((item.fields or {}).get("kind") or "") == "owner_basics":
                return item
        return None

    def owner_profile_basics(self) -> dict:
        """Read the owner's STATED basics from the durable profile drawer. Empty strings when
        nothing has been stated yet — a brand-new user sees no invented facts (honesty)."""
        item = self._owner_basics_item()
        if item is not None:
            f = item.fields or {}
            return {
                "name": str(f.get("name") or ""),
                "summary": str(f.get("summary") or ""),
                "phone": str(f.get("phone") or ""),
                "timezone": str(f.get("timezone") or ""),
                "trust_dial": str(f.get("trust_dial") or ""),
                "always_ask": str(f.get("always_ask") or ""),
                "last_clarification": str(f.get("last_clarification") or ""),
            }
        # Backward-read: reconstruct from an earlier owner_onboard identity write (pre-owner_basics)
        # so a profile onboarded the old way still shows up. Read-only; invents nothing.
        out = {"name": "", "summary": "", "phone": "", "timezone": "",
               "trust_dial": "", "always_ask": "", "last_clarification": ""}
        for p in self.memory.profile.all():
            f = p.fields or {}
            kind = str(f.get("kind") or "")
            if kind == "owner_identity":
                out["name"] = str(f.get("owner_name") or out["name"])
                out["phone"] = str(f.get("phone") or out["phone"])
                out["timezone"] = str(f.get("timezone") or out["timezone"])
            elif kind == "preference":
                pref = str(f.get("preference") or "")
                if pref.startswith("Trust dial: "):
                    out["trust_dial"] = pref[len("Trust dial: "):].strip()
                elif pref.startswith("Always ask before: "):
                    out["always_ask"] = pref[len("Always ask before: "):].strip()
            elif kind == "raw_onboarding_notes":
                text = str(p.text or "")
                if text.startswith("Onboarding notes: "):
                    out["summary"] = text[len("Onboarding notes: "):].strip()
        return out

    def set_owner_profile_basics(self, basics: dict) -> dict:
        """Persist the owner's STATED basics durably into the profile memory drawer (the same drawer
        the brain reads) and return the stored record. Idempotent: upserts the single 'owner_basics'
        record in place so re-saving the onboarding form never piles duplicates."""
        def clean(key: str) -> str:
            return " ".join(str(basics.get(key) or "").split())
        name, summary, phone = clean("name"), clean("summary"), clean("phone")
        timezone, trust_dial = clean("timezone"), clean("trust_dial")
        always_ask, last_clarification = clean("always_ask"), clean("last_clarification")
        fields = {
            "source": "phase_zero_basics",
            "kind": "owner_basics",
            "onboarding_key": self._OWNER_BASICS_KEY,
            "name": name, "summary": summary, "phone": phone, "timezone": timezone,
            "trust_dial": trust_dial, "always_ask": always_ask,
            "last_clarification": last_clarification,
        }
        bits = [b for b in (name, summary) if b]
        text = "You: " + (" — ".join(bits) if bits else "(stated basics)")
        tail = []
        if timezone:
            tail.append(f"timezone {timezone}")
        if trust_dial:
            tail.append(f"trust dial {trust_dial}")
        if always_ask:
            tail.append(f"always ask before {always_ask}")
        if tail:
            text += ". " + "; ".join(tail) + "."
        item = self._owner_basics_item()
        if item is None:
            self.memory.profile.write_text(
                text, fields=fields, provenance="owner:phase_zero_basics",
                confidence=1.0, importance=0.95, status="active")
        else:
            item.text = text
            item.fields = fields
            item.provenance = "owner:phase_zero_basics"
            item.confidence = 1.0
            item.importance = 0.95
            item.status = "active"
            self.memory.profile.update(item)
        self.glassbox.log("owner_profile_basics_set",
                          {"has_name": bool(name), "has_summary": bool(summary),
                           "timezone": timezone or None})
        return self.owner_profile_basics()

    async def onboard_scan_api(self) -> dict:
        """SERVER-SIDE onboarding — the reliable 'it knows you' step, no Chrome-extension round-trip.
        Discovers the user's CONNECTED accounts straight from the live API mesh (the vault holds
        their real OAuth tokens) and feeds them to the per-person mesh via the same onboard_discover
        path (source 'api_scan'). A connected account is real and provable — Anticipy already acts
        through it — so this is honest onboarding, not a Chrome scrape pretending to be one."""
        uid = self.api_hand.user_id
        # service label -> a representative Arcade tool whose authorization == the account being
        # connected. (Live API runs through Arcade's managed OAuth, not the local vault, so the
        # vault can be empty while the account is fully connected — authorize is the real signal.)
        PROBE = {"Google Calendar": "GoogleCalendar.ListEvents", "Gmail": "Gmail.ListEmails",
                 "Slack": "Slack.SendMessageToChannel", "Notion": "Notion.GetPageContentById"}
        discovered = []
        if self.api_hand.mode == MODE_LIVE:
            try:
                client = self.api_hand._client_or_build()
            except Exception as exc:
                client = None
                self.glassbox.log("onboard_scan_api_error", {"error": f"{type(exc).__name__}: {exc}"})
            if client is not None:
                for label, tool in PROBE.items():
                    try:
                        auth = client.tools.authorize(tool_name=tool, user_id=uid)
                        if getattr(auth, "status", None) == "completed":
                            # Arcade CONFIRMED connected -> mark connected (the local vault is empty
                            # in managed-OAuth mode, so 'connected' tells the mesh the truth).
                            discovered.append({"service": label, "logged_in": True, "connected": True})
                    except Exception:
                        continue   # a single service probe failing must never abort onboarding
        # fall back to any locally-vaulted services too (covers a vault-backed deployment)
        for key, label in {"gmail": "Gmail", "googlecalendar": "Google Calendar",
                           "slack": "Slack", "notion": "Notion"}.items():
            if self.token_vault.has(uid, key) and not any(d["service"] == label for d in discovered):
                discovered.append({"service": label, "logged_in": True})
        result = await self.onboard_discover(discovered, source="api_scan")
        # Now that the CONNECTED accounts are known, actually READ them and derive honest
        # profile facts so the brain knows the user from day one (the North Star). Best-effort:
        # a read failure must never crash onboarding. Each fact traces to a real read — if the
        # reads come back thin, we invent NOTHING and say so verbatim (the cardinal-sin guard).
        discovered_people: list = []
        try:
            profile_facts, discovered_people = await self._read_onboarding_profile()
        except Exception as exc:  # noqa: BLE001 — onboarding must survive any read failure
            self.glassbox.log("onboard_scan_api_profile_error",
                              {"error": f"{type(exc).__name__}: {exc}"})
            profile_facts = []
            discovered_people = []
        result["profile_facts"] = profile_facts
        # People read straight from connected accounts, for the owner to confirm in the recap.
        result["auto_discovered_people"] = discovered_people
        if not profile_facts:
            # Thin-data: surface the exact honest line. NOTHING was invented.
            result["profile_summary"] = "No facts assembled. Nothing was invented."
        self.glassbox.log("onboard_scan_api", {"connected": len(discovered),
                          "services": [d["service"] for d in discovered], "mode": self.api_hand.mode,
                          "profile_facts": len(profile_facts),
                          "discovered_people": len(discovered_people)})
        result["scan"] = "api"
        return result

    async def _read_onboarding_profile(self) -> list:
        """READ the user's real connected accounts through the live api_hand and derive a few
        HONEST profile facts so the brain knows the user from day one. The onboarding cardinal
        sin is fabricating a fact: every fact returned here traces to real read data — we derive
        NOTHING from nothing. If the reads are empty/error/not-connected, we return [] and invent
        nothing (the caller then surfaces "No facts assembled. Nothing was invented.").

        Reads (via api_hand): read_calendar -> GoogleCalendar.ListEvents,
        read_contacts -> Gmail.ListThreads, read_email -> Gmail.ListEmails. Each read returns its
        artifact in Result.output['value']; a not-connected account comes back needs_human and is
        simply skipped (no fact, no crash). The derived facts are WRITTEN to the profile drawer
        (the same path owner onboarding uses) and the list is returned."""
        facts: list[dict] = []

        cal_value = await self._onboarding_read_value("read_calendar")
        facts.extend(self._calendar_profile_facts(cal_value))

        contacts_value = await self._onboarding_read_value("read_contacts")
        email_value = await self._onboarding_read_value("read_email")
        facts.extend(self._correspondent_profile_facts(contacts_value, email_value))

        written = [self._write_profile_fact(f) for f in facts]
        # Read-derived PEOPLE the owner genuinely recurs with — surfaced for them to CONFIRM in
        # the recap. We never auto-write a person to the mesh; the owner accepts/edits/deletes
        # first (the "I invented nothing" rule applied to people, not just facts).
        people = self._extract_discovered_people(cal_value, contacts_value, email_value)
        return [w for w in written if w is not None], people

    def _extract_discovered_people(self, cal_value, contacts_value, email_value) -> list:
        """People the owner TRULY recurs with, read straight from already-connected accounts —
        never fabricated. A person is surfaced only when they appear >= 2 times across real
        calendar attendees and email counterparties (one shared meeting is not a relationship).
        Deduped by email, most-frequent first, capped. Returned for the owner to confirm — nothing
        is written to the per-person mesh until they say so."""
        import collections
        counts: "collections.Counter" = collections.Counter()
        names: dict = {}
        channels: dict = {}

        def _note(email, disp):
            email = (email or "").strip().lower()
            if not email or "@" not in email:
                return
            counts[email] += 1
            if disp and email not in names:
                names[email] = disp
            channels.setdefault(email, set()).add("email")

        if isinstance(cal_value, dict):
            for ev in (cal_value.get("events") or []):
                if not isinstance(ev, dict):
                    continue
                for att in (ev.get("attendees") or []):
                    if not isinstance(att, dict) or att.get("self"):
                        continue
                    _note(att.get("email"), (att.get("displayName") or "").strip())
        for value in (contacts_value, email_value):
            if not isinstance(value, dict):
                continue
            for items in _iter_message_lists(value):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    disp, email = _split_addr(_gmail_counterparty(item))
                    _note(email, disp)

        people: list = []
        for email, n in counts.most_common():
            if n < 2:
                continue  # one contact event/thread is not a relationship — invent nothing
            people.append({
                "name": names.get(email) or _name_from_email(email),
                "email": email,
                "count": n,
                "channels": sorted(channels.get(email, {"email"})),
                "source": "api_scan",
            })
            if len(people) >= 8:
                break
        return people

    async def _onboarding_read_value(self, intent: str):
        """Run ONE real read via the live api_hand and return its artifact value, or None.

        None means: the read failed, the account is not connected (needs_human / connect), or the
        artifact was empty. A None never becomes a fact — that is the anti-fabrication guard. Never
        raises (best-effort): any exception degrades to None so onboarding can't crash on a read."""
        try:
            job = Job(intent=intent)
            result = await self.api_hand.handle(job)
        except Exception as exc:  # noqa: BLE001 — a single read must never abort onboarding
            self.glassbox.log("onboard_profile_read_error",
                              {"intent": intent, "error": f"{type(exc).__name__}: {exc}"})
            return None
        # Only a real success carries an artifact. needs_human (account not connected) /failed
        # carry no value, so they contribute no facts — exactly the thin-data path.
        if result.status != JobStatus.success:
            return None
        value = (result.output or {}).get("value")
        if isinstance(value, str):
            # Reads normally return a dict; a stringified value is unparseable structure -> no fact.
            try:
                value = json.loads(value)
            except (ValueError, TypeError):
                return None
        return value if isinstance(value, dict) else None

    def _calendar_profile_facts(self, value) -> list:
        """Honest facts from a REAL GoogleCalendar.ListEvents read. Empty/missing -> no facts.

        We count events in the NEXT TWO WEEKS (a claim we can stand behind), name the busiest
        weekday in that window, and — only when someone genuinely RECURS (appears as a non-self
        attendee on >= 2 events) — name the most frequent contact. Each fact carries its own
        evidence count so it can never outrun the data."""
        if not isinstance(value, dict):
            return []
        events = value.get("events")
        if not isinstance(events, list) or not events:
            return []
        import collections
        now = dt.datetime.now(dt.timezone.utc)
        horizon = now + dt.timedelta(days=14)
        in_window = 0
        weekday = collections.Counter()
        attendees: "collections.Counter" = collections.Counter()
        for ev in events:
            if not isinstance(ev, dict):
                continue
            start = ev.get("start") or {}
            raw = start.get("dateTime") or start.get("date") if isinstance(start, dict) else None
            when = _parse_iso_dt_local(raw)
            if when is not None and now <= when <= horizon:
                in_window += 1
                weekday[when.strftime("%A")] += 1
            for att in (ev.get("attendees") or []):
                if not isinstance(att, dict):
                    continue
                email = att.get("email")
                # the user themselves is not a "contact"; skip self + the organizer-is-self rows
                if email and not att.get("self"):
                    attendees[email] += 1
        facts: list[dict] = []
        if in_window > 0:
            facts.append({
                "key": "calendar:upcoming_events",
                "text": f"You have {in_window} event{'s' if in_window != 1 else ''} "
                        f"in the next two weeks.",
                "evidence": {"source": "GoogleCalendar.ListEvents", "count": in_window,
                             "window_days": 14},
            })
            top_day, top_n = weekday.most_common(1)[0]
            if top_n >= 1:
                facts.append({
                    "key": "calendar:busiest_weekday",
                    "text": f"Your busiest day in the next two weeks is {top_day} "
                            f"({top_n} event{'s' if top_n != 1 else ''}).",
                    "evidence": {"source": "GoogleCalendar.ListEvents", "weekday": top_day,
                                 "count": top_n},
                })
        # Only claim "frequent contact" when someone TRULY recurs (>= 2 events). One shared event
        # is not a relationship — claiming it would be the fabrication that ends trust.
        if attendees:
            name, n = attendees.most_common(1)[0]
            if n >= 2:
                facts.append({
                    "key": "calendar:frequent_contact",
                    "text": f"You're in frequent contact with {name} "
                            f"({n} shared events).",
                    "evidence": {"source": "GoogleCalendar.ListEvents", "contact": name,
                                 "count": n},
                })
        return facts

    def _correspondent_profile_facts(self, contacts_value, email_value) -> list:
        """Honest facts from REAL Gmail reads (ListThreads / ListEmails). When Gmail is not
        connected both values are None and this returns [] — no fact, no fabrication. When
        connected, name the most frequent correspondent only if they genuinely recur (>= 2)."""
        import collections
        senders: "collections.Counter" = collections.Counter()
        total = 0
        for value in (contacts_value, email_value):
            if not isinstance(value, dict):
                continue
            for items in _iter_message_lists(value):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    total += 1
                    addr = _gmail_counterparty(item)
                    if addr:
                        senders[addr] += 1
        facts: list[dict] = []
        if total > 0:
            facts.append({
                "key": "email:recent_volume",
                "text": f"You have {total} recent email thread{'s' if total != 1 else ''} "
                        f"in your inbox.",
                "evidence": {"source": "Gmail", "count": total},
            })
        if senders:
            name, n = senders.most_common(1)[0]
            if n >= 2:
                facts.append({
                    "key": "email:frequent_correspondent",
                    "text": f"You're in frequent email contact with {name} "
                            f"({n} recent threads).",
                    "evidence": {"source": "Gmail", "correspondent": name, "count": n},
                })
        return facts

    def _write_profile_fact(self, fact: dict):
        """Upsert ONE derived profile fact into the profile drawer (the same drawer owner
        onboarding writes to, so the brain reads it through the normal inject path). Keyed by a
        stable onboarding_key so re-running the scan updates rather than duplicates. Returns the
        fact text on success, None on a write failure (best-effort; never crashes onboarding)."""
        text = fact.get("text")
        if not text:
            return None
        key = f"onboarding_profile:{fact.get('key')}"
        fields = {
            "kind": "onboarding_profile_fact",
            "onboarding_key": key,
            "source": "api_scan",
            "derived_from": "live_account_read",
            "evidence": fact.get("evidence", {}),
        }
        try:
            drawer = self.memory.profile
            existing = None
            for item in drawer.all():
                if (item.fields or {}).get("onboarding_key") == key:
                    existing = item
                    break
            if existing is None:
                drawer.write_text(text, fields=fields, provenance="owner:api_scan",
                                  confidence=1.0, importance=0.7, status="active")
            else:
                existing.text = text
                existing.fields = fields
                existing.provenance = "owner:api_scan"
                existing.confidence = 1.0
                existing.importance = 0.7
                existing.status = "active"
                drawer.update(existing)
        except Exception as exc:  # noqa: BLE001 — a write failure must not crash onboarding
            self.glassbox.log("onboard_profile_write_error",
                              {"key": key, "error": f"{type(exc).__name__}: {exc}"})
            return None
        return text

    async def onboard_discover(self, discovered, source: str = "chrome_scrape") -> dict:
        """Ingest a logged-in-Chrome connection SCAN (the extension's discover_connections
        intent) into the per-person mesh, via the SAME path typed onboarding uses. A discovered
        service Anticipy already holds a vault token for is marked connected; the rest become
        'Connect X' open-loops (api route for known services, browser for niche CRMs). Discovery
        only — NO credentials/tokens are entered here."""
        from ..onboarding.connection_scan import scan_to_onboarding
        # Bound the work: a real person is logged into a handful of services, not hundreds.
        # Non-list input -> empty (never crash); the cap also protects owner_onboard's per-item
        # drawer rescans from an O(n^2) blowup on a pathological payload (skeptic-found).
        if not isinstance(discovered, (list, tuple)):
            discovered = []
        items = [x for x in discovered if isinstance(x, dict)][:100]
        # OBSERVABILITY (ALWAYS — even on an all-logged-out scan): record the EXACT per-service verdict
        # + reason the extension reported. Without this a "not logged in for an account I AM in" is
        # silently swallowed and impossible to debug (the long-standing scrape complaint). This is the
        # truth a test / the reality gate reads back; it never fakes a result.
        scan_raw = [
            {"service": x.get("service"), "logged_in": bool(x.get("logged_in")),
             "reason": x.get("reason") or x.get("error") or "", "url": x.get("url")}
            for x in items
        ]
        self.glassbox.log("onboard_scan_result", {"source": source, "raw": scan_raw})
        uid = self.api_hand.user_id
        onb = scan_to_onboarding(
            items, source=source,
            vault_has=lambda key: self.token_vault.has(uid, key),
        )
        result = await self.owner_onboard(onb)
        result["connections"] = [c.model_dump() for c in onb.connections]
        result["discovered_count"] = len(items)
        result["scan_raw"] = scan_raw   # exact per-service verdict+reason (testability/observability)
        # Glass-box the real scrape so it is PROVABLE the onboarding "scrapes you" step fired
        # and fed the per-person mesh. Emit ONLY when the scan actually ingested connections —
        # an empty/no-op scan is not an onboarding event and must never look like one (honesty:
        # the reality gate reads this back, so it can only ever say REAL when a real scan landed).
        if onb.connections:
            self.glassbox.log("onboard_discover", {
                "source": source,
                "discovered_count": len(items),
                "connected_count": sum(1 for c in onb.connections if c.status == "connected"),
                "connections": [
                    {"name": c.name, "status": c.status, "route": c.route}
                    for c in onb.connections
                ],
            })
        return result

    async def ingest_deep_scrape(self, scraped, source: str = "chrome_deep_scrape") -> dict:
        """Ingest a CONTENT deep-scrape from the user's OWN logged-in Chrome (the extension's
        deep_scrape intent: real Gmail subjects/senders, calendar events, Drive files, LinkedIn, ...)
        -> synthesize a graded dossier -> write it to memory. THIS is the 'scrapes you' step that
        actually LEARNS about the owner, run through their real Chrome (the extension), not a CDP debug
        browser. Honest by construction: a signed-out / empty surface contributes nothing and is never
        invented; with nothing readable the dossier is empty + carries a clarifying question."""
        from ..onboarding import dossier as _dossier
        if not isinstance(scraped, (list, tuple)):
            scraped = []
        items = [x for x in scraped if isinstance(x, dict)][:50]

        def _render(it: dict) -> str:
            ex = it.get("extracted") if isinstance(it.get("extracted"), dict) else {}
            lines: list[str] = []
            for em in (ex.get("emails") or [])[:20]:
                if isinstance(em, dict):
                    frm = str(em.get("from") or "").strip()
                    subj = str(em.get("subject") or "").strip()
                    if frm or subj:
                        lines.append(f"Email — from {frm}: {subj}")
                elif isinstance(em, str) and em.strip():
                    lines.append("Email — " + em.strip())
            for ev in (ex.get("events") or [])[:15]:
                if str(ev).strip():
                    lines.append("Calendar — " + str(ev).strip())
            for f in (ex.get("recent_files") or [])[:15]:
                if str(f).strip():
                    lines.append("File — " + str(f).strip())
            for ch in (ex.get("channels") or [])[:15]:
                if str(ch).strip():
                    lines.append("Slack channel — " + str(ch).strip())
            if str(ex.get("profile_name") or "").strip():
                lines.append("LinkedIn profile name: " + str(ex["profile_name"]).strip())
            if str(ex.get("username") or "").strip():
                lines.append("GitHub username: " + str(ex["username"]).strip())
            # GENERIC deep-read content (hand-driven scrape of any surface — the horizontal path):
            # facts the live hand read deep off a page, not tied to a known account schema.
            for nt in (ex.get("notes") or [])[:25]:
                if str(nt).strip():
                    lines.append(str(nt).strip())
            if str(ex.get("text") or "").strip():
                lines.append(str(ex["text"]).strip()[:1500])
            return "\n".join(lines)

        surfaces: list[dict] = []
        for it in items:
            svc = str(it.get("service") or "").strip()
            if not svc:
                continue
            key = svc.lower()
            if it.get("error") or it.get("signed_in") is False:
                surfaces.append({"key": key, "label": svc, "status": "needs_login",
                                 "needs_login": it.get("signed_in") is False, "text": ""})
                continue
            text = _render(it)
            surfaces.append({"key": key, "label": svc,
                             "status": "ok" if text else "empty",
                             "needs_login": False, "text": text})

        signals = {
            "surfaces": surfaces,
            "logged_in": [s["key"] for s in surfaces if s["status"] == "ok"],
            "needs_login": [s["key"] for s in surfaces if s.get("needs_login")],
        }
        doss = await _dossier.synthesize_dossier(signals, self.gateway)
        counts = _dossier.write_dossier_to_memory(doss, self.memory)
        summary = [{"key": s["key"], "status": s["status"], "chars": len(s["text"])} for s in surfaces]
        self.glassbox.log("onboard_deep_scrape", {"source": source, "surfaces": summary, "wrote": counts})
        return {"dossier": doss, "surfaces": summary, "memory_written": counts}

    async def onboard_deep_read_via_hand(self, targets: list, source: str = "hand_deep_read",
                                         scroll_rounds: int = 0) -> dict:
        """ONBOARDING via the LIVE hands (Step 3): for each {url,label}, drive the connected Chrome to
        OPEN the page and READ its real content — the observe primitive returns the page text PLUS the
        visible items/sections (the inbox's emails, the calendar's events, the article's headings) —
        then land it in memory via ingest_deep_scrape (the dossier synthesizer extracts the facts). This
        is the real-content read, NOT the old screenshot-the-first-screen. A sign-in surface yields a
        needs_login surface (never types credentials). Uses observe (reliable), not the agent's flaky
        inline synthesis. Provable on any public page; reused as-is for real accounts (read-only)."""
        from .envelopes import new_id
        _LOGIN_MARKERS = ("sign in", "log in", "enter your password", "use your google account",
                          "couldn't sign you in", "to continue to", "forgot email")
        scraped: list[dict] = []
        for t in (targets or [])[:8]:
            url = str((t or {}).get("url") or "").strip()
            label = str((t or {}).get("label") or url).strip()
            if not url:
                continue
            try:
                r = await self.browser_link.send_browse(new_id(), "observe", {"url": url}, timeout=60.0)
            except Exception as exc:
                self.glassbox.log("hand_deep_read_error", {"url": url, "error": f"{type(exc).__name__}: {exc}"})
                scraped.append({"service": label, "url": url, "error": True})
                continue
            o = r.get("output") or {}
            text = (o.get("text") or "").strip()
            elements = o.get("elements") or []
            low = text.lower()
            if r.get("status") == "needs_human" or (
                    text and len(text) < 1200 and sum(m in low for m in _LOGIN_MARKERS) >= 2):
                scraped.append({"service": label, "url": url, "signed_in": False})
                self.glassbox.log("hand_deep_read", {"url": url, "label": label, "result": "needs_login"})
                continue
            if not text and not elements:
                scraped.append({"service": label, "url": url, "signed_in": True, "extracted": {}})
                continue
            # the visible ITEMS/sections the hand opened onto (emails, events, headings, links)
            items = [str(e.get("name")).strip() for e in elements
                     if isinstance(e, dict) and str(e.get("name") or "").strip() and e.get("inView")][:20]
            # DEEPER layers SCROLL: each round scrolls the page and re-reads, unioning in the
            # content below the fold (older emails, further events) — a real scroll-through,
            # not the first screen only. New text/items only; a round that adds nothing stops.
            seen_text = {text}
            for _round in range(max(0, int(scroll_rounds))):
                try:
                    await self.browser_link.send_browse(new_id(), "act", {"action": "scroll"}, timeout=30.0)
                    r2 = await self.browser_link.send_browse(new_id(), "observe", {}, timeout=30.0)
                except Exception:
                    break
                o2 = r2.get("output") or {}
                t2 = (o2.get("text") or "").strip()
                if not t2 or t2 in seen_text:
                    break
                seen_text.add(t2)
                text = (text + "\n" + t2)
                items += [str(e.get("name")).strip() for e in (o2.get("elements") or [])
                          if isinstance(e, dict) and str(e.get("name") or "").strip()
                          and e.get("inView") and str(e.get("name")).strip() not in items][:10]
            scraped.append({"service": label, "url": url, "signed_in": True,
                            "extracted": {"text": text[:1800 + 1200 * max(0, int(scroll_rounds))],
                                          "notes": items[:40]}})
            self.glassbox.log("hand_deep_read", {"url": url, "label": label, "chars": len(text),
                                                 "items": len(items), "final_url": o.get("url")})
        return await self.ingest_deep_scrape(scraped, source=source)

    @staticmethod
    def _onboarding_key(fields: dict) -> str:
        kind = str(fields.get("kind") or "").strip().lower()
        source = "owner_onboarding"
        if kind == "owner_identity":
            return f"{source}:owner_identity"
        if kind == "preference":
            return f"{source}:preference:{str(fields.get('preference') or '').strip().lower()}"
        if kind == "person":
            return f"{source}:person:{str(fields.get('name') or '').strip().lower()}"
        if kind == "app_connection":
            identifier = str(fields.get("identifier") or "").strip().lower()
            name = str(fields.get("name") or "").strip().lower()
            return f"{source}:app_connection:{identifier or name}"
        if kind == "store_account":
            url = str(fields.get("url") or "").strip().lower()
            # Normalize equivalent URLs to ONE key so "costco.com" / "https://costco.com" / "www.costco.com/"
            # upsert in place instead of writing duplicate store cards (overnight bug-hunt #3). Purely
            # additive URL canonicalization (scheme + leading www + trailing slash); never merges by name.
            url = re.sub(r"^https?://", "", url)
            url = re.sub(r"^www\.", "", url).rstrip("/")
            name = str(fields.get("name") or "").strip().lower()
            return f"{source}:store_account:{url or name}"
        if kind == "raw_onboarding_notes":
            return f"{source}:raw_notes"
        return f"{source}:{kind}:{str(fields).strip().lower()}"

    def _find_onboarding_item(self, drawer, key: str, fields: dict):
        new_kind = str(fields.get("kind") or "").strip().lower()
        new_name = str(fields.get("name") or "").strip().lower()
        new_ident = str(fields.get("identifier") or "").strip().lower()
        for item in drawer.all():
            item_key = item.fields.get("onboarding_key") or self._onboarding_key(item.fields)
            if item_key == key:
                return item
            if fields.get("action") == "connect_account" and item.fields.get("action") == "connect_account":
                if str(item.fields.get("name") or "").strip().lower() == new_name:
                    return item
            # app_connection profile card: a varying/appearing identifier for the SAME service name must
            # UPSERT in place, not spawn a duplicate (overnight bug-hunt #2: typed Gmail w/ no id, then
            # the Chrome scan w/ the email id wrote two "App connection: Gmail" cards). Bounded: only when
            # ONE side lacks an identifier — two genuinely distinct same-service accounts (each with its
            # own identifier) stay separate. Never name-only.
            if new_kind == "app_connection" and str(item.fields.get("kind") or "").strip().lower() == "app_connection":
                it_name = str(item.fields.get("name") or "").strip().lower()
                it_ident = str(item.fields.get("identifier") or "").strip().lower()
                if it_name == new_name and (not new_ident or not it_ident):
                    return item
        return None

    def _upsert_onboarding_memory(self, mem, source: str):
        drawer = self.memory.profile if mem.drawer == "profile" else self.memory.open_loops
        key = self._onboarding_key(mem.fields)
        fields = {**mem.fields, "onboarding_key": key}
        item = self._find_onboarding_item(drawer, key, fields)
        if item is None:
            return drawer.write_text(
                mem.text,
                fields=fields,
                provenance=f"owner:{source}",
                confidence=mem.confidence,
                importance=mem.importance,
                status=mem.status,
            )
        item.text = mem.text
        item.fields = fields
        item.provenance = f"owner:{source}"
        item.confidence = mem.confidence
        item.importance = mem.importance
        item.status = mem.status
        return drawer.update(item)

    def _close_connected_setup_loops(self, memories) -> None:
        active_missing = {
            self._onboarding_key(mem.fields)
            for mem in memories
            if mem.drawer == "open_loops" and mem.fields.get("action") == "connect_account"
        }
        connection_keys = {
            self._onboarding_key(mem.fields): mem
            for mem in memories
            if mem.drawer == "profile" and mem.fields.get("kind") == "app_connection"
        }
        # NAMES of services that are actually CONNECTED — from this batch AND the durable profile
        # drawer. A connect-loop is keyed on the service's identifier, but a service often connects
        # under a CHANGED identifier (typed "Gmail" with no email, then the scan reads you@gmail.com),
        # so the loop's old key no longer matches the connected card's new key and the stale
        # "Connect Gmail" nag never closes (overnight bug-hunt finding #3). The name fallback below
        # closes it — bounded: only ever closes a loop when a card with that name is truly connected.
        connected_names = {
            str(mem.fields.get("name") or "").strip().lower()
            for mem in memories
            if mem.drawer == "profile" and mem.fields.get("kind") == "app_connection"
            and mem.fields.get("status") == "connected"
        }
        for p in self.memory.profile.all():
            if (p.fields.get("kind") == "app_connection"
                    and p.fields.get("status") == "connected"):
                connected_names.add(str(p.fields.get("name") or "").strip().lower())
        for item in self.memory.open_loops.all():
            if item.fields.get("action") != "connect_account":
                continue
            key = item.fields.get("onboarding_key") or self._onboarding_key(item.fields)
            if key in active_missing:
                continue
            conn = connection_keys.get(key)
            connected_by_key = conn is not None and conn.fields.get("status") == "connected"
            loop_name = str(item.fields.get("name") or "").strip().lower()
            connected_by_name = bool(loop_name) and loop_name in connected_names
            if not (connected_by_key or connected_by_name):
                continue
            item.status = "done"
            item.fields = {**item.fields, "onboarding_key": key,
                           "resolved_from": "owner_onboarding_connected" if connected_by_key
                           else "owner_onboarding_connected_by_name"}
            self.memory.open_loops.update(item)

    async def derive_tick(self) -> dict:
        """TRUE PROACTIVITY (FIX-07, 2026-07-02): anticipate → research → act → tell the owner.

        One tick: build a WorldSnapshot from what the engine already knows → derive at most 2
        UNSPOKEN needs (proactive/derive.py, floored: safe kinds only, money impossible,
        confidence ≥ 0.6) → dedupe against open loops / recent cards / the fire-once ledger
        (mark BEFORE act, like trigger_tick's D16 stamp) → research the real world browser-only
        (proactive/world_research.py) → compose ONE plain-English action sentence and submit it
        through the ONE front door (owner_ingest — same extractor, same harm-line, same autonomy
        dial as everything else; no new decision engine) → if it ACTED, ONE text to the owner;
        if it ASKED, the pending-ask SMS already covers the outreach (never double-text).

        Fail-closed everywhere: a stub/starved model derives nothing; a research wall is an
        honest miss carried into the message; an error returns {"derived": []} and never
        crashes the scheduler."""
        import time as time  # house style: scoped import (module has no top-level time)
        from ..proactive.derive import WorldSnapshot, derive_needs
        from ..proactive import world_research

        out: list[dict] = []
        try:
            now = time.time()
            tz, tz_name = self._owner_timezone()
            profile_facts = [str(getattr(i, "text", "") or "") for i in self.memory.profile.all()][:20]
            open_loops = [{"text": str(getattr(i, "text", "") or "")}
                          for i in self.memory.open_loops.all()
                          if str(getattr(i, "status", "")) not in {"done", "closed", "stopped"}][:15]
            try:
                recent_cards = (self.owner_cards(limit=12) or {}).get("cards") or []
            except Exception:
                recent_cards = []
            calendar_events: list[dict] = []
            try:
                cal_value = await self._onboarding_read_value("read_calendar")
                if isinstance(cal_value, list):
                    calendar_events = [e for e in cal_value if isinstance(e, dict)][:12]
            except Exception:
                pass
            snapshot = WorldSnapshot(now=now, tz_name=tz_name or "",
                                     profile_facts=profile_facts, open_loops=open_loops,
                                     recent_cards=recent_cards, calendar_events=calendar_events)
            needs = await derive_needs(self.gateway, snapshot)
        except Exception as exc:
            self.glassbox.log("derive_tick_error", {"error": f"{type(exc).__name__}: {exc}"})
            return {"derived": []}

        if not needs:
            return {"derived": []}

        # Fire-once ledger: one firing per (local day, obligation signature). Mark BEFORE acting
        # so a crash mid-flight can never double-fire. A daily need (school pickup) correctly
        # re-derives tomorrow; the same need never fires twice today.
        ledger_path = self.data_dir / "derived_needs.json"
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception:
            ledger = {}
        import datetime as _dt
        today = _dt.datetime.now(tz).strftime("%Y-%m-%d") if tz else _dt.datetime.now().strftime("%Y-%m-%d")

        known_sigs = [_obligation_sig(str(l.get("text") or "")) for l in open_loops]
        known_sigs += [_obligation_sig(str(c.get("title") or c.get("source_text") or "")) for c in recent_cards]

        for need in needs:
            sig = _obligation_sig(need.need)
            key = f"{today}:{'|'.join(sorted(sig))}"
            if key in ledger:
                continue
            if any(_same_obligation(sig, k) for k in known_sigs if k):
                self.glassbox.log("derive_deduped", {"need": need.need[:120]})
                continue
            ledger[key] = {"date": today, "need": need.need[:200], "kind": need.action_kind}
            try:
                ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")  # mark BEFORE act
            except Exception:
                pass

            findings = await world_research.research(self.bus, need.research_questions)
            research_lines = [f"{f['answer']}" for f in findings if f.get("ok")]
            misses = [f["question"] for f in findings if not f.get("ok")]

            # PHASE 5 — the browser writes back what it learns. The researched answers (and the
            # agent's cross-page notes) and any people this need names get resolved AGAINST what
            # memory already knows (finally feeding resolve_person its remembered_items, so the
            # memory arm actually fires) — then both are persisted as durable memory through the
            # SAME gated capture path (redact secrets + should_keep + vent-safe). Fail-closed:
            # any error here is logged and never disturbs the tick's act/ask/notify flow.
            try:
                await self._persist_browser_learning(need, findings)
            except Exception as exc:
                self.glassbox.log("derive_persist_error", {"error": f"{type(exc).__name__}: {exc}"})

            # Compose the ONE action sentence and submit through the ONE front door.
            args = need.action_args or {}
            if need.action_kind == "calendar_hold":
                title = str(args.get("title") or need.need)
                when = str(args.get("start_local") or "").strip()
                sentence = f"Put a hold on my calendar{(' at ' + when) if when else ''}: {title}."
            elif need.action_kind == "reminder":
                text_ = str(args.get("text") or need.need)
                when = str(args.get("when_local") or "").strip()
                sentence = f"Remind me{(' at ' + when) if when else ''}: {text_}."
            else:  # heads_up_text — no action, just the message
                sentence = ""
            if research_lines and sentence:
                sentence += " (" + "; ".join(research_lines[:2]) + ")"

            entry: dict = {"need": need.need, "kind": need.action_kind, "why": need.why,
                           "evidence": need.evidence, "research": findings}
            acted = False
            if sentence:
                try:
                    res = await self.owner_ingest("derived", sentence,
                                                  {"derived": True, "derived_need": need.need[:200]},
                                                  execute_actions=True)
                    cards = res.get("cards") or []
                    entry["cards"] = [{"disposition": c.get("disposition"),
                                       "title": (c.get("title") or "")[:120]} for c in cards]
                    acted = any(c.get("disposition") == "do" for c in cards)
                    entry["decision"] = ("act" if acted else
                                         ("ask" if any(c.get("disposition") == "ask" for c in cards)
                                          else "silent"))
                except Exception as exc:
                    entry["decision"] = "error"
                    entry["error"] = f"{type(exc).__name__}: {exc}"
            else:
                entry["decision"] = "heads_up"

            # The proactive text: heads-up needs always tell the owner; acted needs confirm what
            # was done. An ASK already texts through the pending path — never double-text.
            if entry["decision"] in {"act", "heads_up"}:
                msg = str((args.get("text") if need.action_kind == "heads_up_text" else "") or "")
                if not msg:
                    done_bit = "I put it on your calendar" if need.action_kind == "calendar_hold" \
                        else "I set the reminder"
                    detail = ("; ".join(research_lines[:2]) + " — ") if research_lines else ""
                    msg = f"Heads up: {need.need}. {detail}{done_bit if acted else ''}".strip()
                    if acted:
                        msg += " — I've got it, or you this time?"
                if misses:
                    msg += f" (couldn't verify: {misses[0][:80]})"
                try:
                    await self.notify_user(msg)
                    self.proactive.budget.record_interruption(time.time())
                    self.glassbox.log("derived_notified", {"need": need.need[:120],
                                                           "decision": entry["decision"],
                                                           "message": msg[:200]})
                    entry["notified"] = True
                except Exception:
                    entry["notified"] = False
            out.append(entry)
        return {"derived": out}

    def _remembered_items(self, limit: int = 200) -> list[dict]:
        """What memory already knows, shaped as resolve_person's remembered_items.

        A flat [{text, people}] list drawn from the active drawers (profile / history /
        open_loops) plus the inert pull-only remember-list — the exact shape
        anticipate.search_memory_for_person scans. This is what finally FEEDS the memory arm
        of resolve_person: before Phase 5 it was always called with an empty list, so the arm
        the module was built for could never fire. Superseded/archived facts are skipped so a
        stale answer is never re-surfaced. Fail-closed: returns [] on any error."""
        items: list[dict] = []
        try:
            for drawer in (self.memory.profile, self.memory.history, self.memory.open_loops):
                for it in drawer.all():
                    if str(getattr(it, "status", "")) in {"superseded", "archived"}:
                        continue
                    items.append({"text": str(getattr(it, "text", "") or ""),
                                  "people": list(getattr(it, "people", []) or [])})
        except Exception:
            pass
        try:
            for row in self.live_memory.capturer.remember.recent(limit):
                items.append({"text": str(row.get("text") or ""),
                              "people": list(row.get("people") or [])})
        except Exception:
            pass
        return items[:limit]

    async def _persist_browser_learning(self, need, findings: list[dict]) -> None:
        """Phase 5 write-back: turn what the browser learned this tick into durable memory.

        Two sources, both formerly discarded:
          (a) researched ANSWERS + the agent's cross-page NOTES (world_research findings) →
              persisted verbatim as inert episodic facts;
          (b) the PEOPLE this need names → resolved via resolve_person, FED remembered_items so
              its memory arm fires, and any dossier with real evidence persisted as a fact.
        Everything goes through capturer.capture_fact — the SAME gate as ordinary capture
        (redact secrets, drop noise, vent-safe), pinned to history so nothing here can ever
        become a fireable reminder. Bounded (≤2 people, ≤5 notes/finding) and best-effort."""
        cap = self.live_memory.capturer
        learned = 0

        # (a) researched answers + cross-page notes
        for f in (findings or []):
            if not f.get("ok"):
                continue
            ans = str(f.get("answer") or "").strip()
            if ans:
                res = cap.capture_fact(ans, source="browser_research")
                learned += 1 if res.get("kept") else 0
            for note in (f.get("notes") or [])[:5]:
                n = str(note or "").strip()
                if n:
                    res = cap.capture_fact(n, source="browser_research")
                    learned += 1 if res.get("kept") else 0

        # (b) resolve people the need names, feeding the memory arm, then persist real dossiers
        try:
            from ..proactive.anticipate import extract_people_from_task
            from ..proactive.world_research import resolve_person
            remembered = self._remembered_items()
            for name in extract_people_from_task(str(getattr(need, "need", "") or ""))[:2]:
                try:
                    dossier = await resolve_person(name, str(getattr(need, "need", "") or ""),
                                                   self.gateway, remembered_items=remembered)
                except Exception:
                    dossier = None
                if not dossier:
                    continue
                # Persist ONLY a dossier grounded in real evidence (a memory hit or a found
                # email) — a "no prior history found" guess is noise and is never written.
                has_evidence = bool(dossier.get("memory_hits") or dossier.get("email"))
                if has_evidence and float(dossier.get("confidence") or 0.0) >= 0.3:
                    rel = str(dossier.get("relationship") or dossier.get("summary") or "").strip()
                    if rel and rel.lower() != "mentioned in conversation, no prior history found":
                        res = cap.capture_fact(f"{name}: {rel}", source="browser_person")
                        learned += 1 if res.get("kept") else 0
        except Exception as exc:
            self.glassbox.log("derive_person_resolve_error",
                              {"error": f"{type(exc).__name__}: {exc}"})

        if learned:
            self.glassbox.log("browser_learning_persisted",
                              {"need": str(getattr(need, "need", ""))[:120], "facts": learned})

    async def notify_user(self, text: str, recipient: str | None = None) -> dict:
        """Text the user — the 'ask' half of a wall handoff (pause -> ask -> resume).
        Routes through the REAL send_text worker (mock by default, Twilio when the
        channel env is live); the seam + glass-box trail are the same either way."""
        from .envelopes import Job

        to = (recipient or os.environ.get("ALERT_PHONE") or os.environ.get("TWILIO_TO")
              or self._user_contact())
        self.glassbox.log("handoff", {"event": "notify_user", "to": to, "text": text})
        try:
            res = await self.channel_worker.handle(Job(intent="send_text", args={"recipient": to, "body": text}))
            return res.model_dump(mode="json")
        except Exception as e:  # a notify failure must never crash the agent run
            self.glassbox.log("handoff", {"event": "notify_failed", "error": str(e)})
            return {"error": str(e)}

    async def resume(self) -> list:
        return await self.orchestrator.resume_waiting()

    # ---- Room 6: the "needs you" surface (decisions flow brain -> app -> back) ----
    def pending_asks(self) -> list:
        """Detrimental actions paused awaiting the user's yes/no — what the app surfaces.

        Excludes opt_out_stop entries: an AUTO_DO_WITH_OPT_OUT chore is STARTED, not awaiting a
        yes — its pending entry is only the STOP handle (resolved by /owner/stop). Surfacing it
        here would wrongly render it as a Yes/Not-now approval (the approval-machine bug)."""
        # Render the app surface in the product voice: the raw reason is internal shorthand
        # ("send to a real person; memory low-confidence on recipient -> fail-safe ask") and the
        # action can carry the third-person "wearer" framing — neither may reach the user.
        from . import voice as _voice
        return [{"ask_id": aid,
                 "action": _voice.humanize_person_framing(p["action"]),
                 "reason": _voice.humanize_reason(p.get("reason", ""), p.get("category", "")),
                 "category": p.get("category", ""), "goal_id": p["goal_id"]}
                for aid, p in self.proactive.pending.items()
                if p.get("category") != "opt_out_stop"]

    def memory_open_loops(self, limit: int = 50) -> dict:
        """Visible memory backlog: open/waiting loops the owner should be able to inspect."""
        import time as _t
        _now = _t.time()

        def _surfaced(i) -> bool:
            if not is_active_open_loop(i):
                return False
            # A SCHEDULED, not-yet-due follow-up is not ACTIVE work yet: it surfaces as a NUDGE
            # when it fires (proactive._fire_reminder at remind_ts), and the owner sees the
            # planned check-in on the card itself (card.follow_up). Showing it now would make a
            # done/parked task look open again and echo its raw source_text into the active list.
            if i.fields.get("kind") == "follow_up" and not i.fields.get("fired_at"):
                rt = i.fields.get("remind_ts")
                if rt is not None and float(rt) > _now:
                    return False
            return True

        active = [i for i in self.memory.open_loops.all() if _surfaced(i)]
        # DEDUPE — one dictated task -> exactly ONE backlog row. The owner-ingest path
        # writes two open_loops for one commitment: a RAW capture loop (the speaker's words,
        # the live reminder grounding) and an OWNER-CARD loop (the card-board record). When
        # BOTH are active for the same task the backlog showed it twice. Collapse same-text
        # active loops to one, PREFERRING the owner-card loop — it carries the card linkage,
        # so the surfaced row is the protected one (resolve must go through the card). A raw
        # loop with no active owner-card sibling (e.g. a do-card reminder whose card already
        # finished) still surfaces; a loop the spine caught with no raw sibling is untouched.
        by_task: dict = {}
        for i in active:
            # group same-task rows on the shared capture content key when present
            # (the two writers stamp the same capture_key), else normalized text
            key = i.fields.get("capture_key") or " ".join((i.text or "").split()).lower()
            kept = by_task.get(key)
            if kept is None:
                by_task[key] = i
                continue
            # prefer the owner-card loop; otherwise keep the most recently updated
            i_card = bool(i.fields.get("owner_card_id"))
            kept_card = bool(kept.fields.get("owner_card_id"))
            if i_card and not kept_card:
                by_task[key] = i
            elif i_card == kept_card and (i.updated_at or i.timestamp) > (kept.updated_at or kept.timestamp):
                by_task[key] = i
        deduped = list(by_task.values())
        deduped.sort(key=lambda i: i.updated_at or i.timestamp, reverse=True)
        loops = [i.model_dump(mode="json") for i in deduped[:max(0, limit)]]
        return {"loops": loops, "count": len(deduped)}

    def proactive_gateway_recent(self, limit: int = 50) -> dict:
        """Recent Plan Baby Steps gateway events for app, tests, and audits."""
        return self.gateway_ledger.recent(limit=limit)

    def resolve_memory_loop(self, loop_id: str, status: str = "done") -> dict:
        """Owner closes a memory/setup loop. Owner-card loops must resolve through cards."""
        if status not in {"done", "blocked", "waiting", "open"}:
            return {"resolved": False, "reason": f"unsupported status: {status}"}
        item = self.memory.open_loops.get(loop_id)
        if item is None:
            return {"resolved": False, "reason": "unknown open loop"}
        if item.fields.get("owner_card_id"):
            return {
                "resolved": False,
                "reason": "owner-card loops must be resolved from the task card",
                "id": item.id,
                "status": item.status,
            }
        before = item.status
        item.status = status
        item.fields = {**item.fields, "resolved_from": "owner_mode", "previous_status": before}
        self.memory.open_loops.update(item)
        self.glassbox.log(
            "memory_loop_resolved",
            {"loop_id": item.id, "status": status, "previous_status": before, "text": item.text},
        )
        return {
            "resolved": True,
            "id": item.id,
            "status": item.status,
            "previous_status": before,
            "text": item.text,
        }

    def owner_cards(self, limit: int = 50) -> dict:
        """Return recent durable owner cards for the app board.

        The UI is allowed to reload or reconnect without losing the visible work
        surface. The source of truth is the card record written beside each goal,
        not React state from the last ingest response.
        """
        cards_dir = self.data_dir / "owner_cards"
        if not cards_dir.is_dir():
            return {"cards": [], "count": 0}
        cards = []
        paths = sorted(cards_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in paths[:max(0, limit)]:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            card = record.get("owner_card") or {}
            if not isinstance(card, dict):
                continue
            state = record.get("state") or card.get("status") or "open"
            card = {**card, "status": state}
            # SEAM 2: surface the persisted autonomy mode so the board can pick the lane/verb.
            if not card.get("autonomy_mode") and record.get("autonomy_mode"):
                card["autonomy_mode"] = record.get("autonomy_mode")
            if record.get("gateway_event_id"):
                card["gateway_event_id"] = record.get("gateway_event_id")
            if record.get("browser_gateway_event_id"):
                card["browser_gateway_event_id"] = record.get("browser_gateway_event_id")
            execution = card.get("execution")
            if isinstance(execution, dict):
                card["execution"] = {
                    **execution,
                    "goal_state": state,
                    "ask_id": execution.get("ask_id") if state == "waiting" else None,
                }
            resolution = record.get("resolution")
            if isinstance(resolution, dict):
                proof = list(card.get("proof") or [])
                if not any(p.get("type") == "resolution" for p in proof if isinstance(p, dict)):
                    proof.append({
                        "type": "resolution",
                        "decision": "approved" if resolution.get("approved") else "declined",
                        "goal_state": state,
                    })
                card["proof"] = proof
            cards.append(card)
        return {"cards": cards, "count": len(cards)}

    def _resolve_browser_card_record(self, ask_id: str, approved: bool) -> None:
        """Write a browser round-trip resolution onto its durable owner card (card.id == ask_id):
        YES -> 'running' (the agent runs async + texts the result), NO -> 'declined'. owner_cards()
        derives status / execution.goal_state / the resolution proof from record state+resolution,
        so a declined web task shows 'declined' on the board, not a stranded 'open' (F-011)."""
        path = self.data_dir / "owner_cards" / f"{ask_id}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return
        state = "running" if approved else "declined"
        record["state"] = state
        record["resolution"] = {"ask_id": ask_id, "approved": approved}
        if isinstance(record.get("owner_card"), dict):
            record["owner_card"]["status"] = state
        try:
            path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        except Exception:
            return
        if not approved:
            self._sync_owner_loop_status(ask_id, "declined")

    def _find_card_record(self, goal_id: str) -> dict | None:
        """Scan the durable owner card records for one whose execution targeted
        goal_id (ledger F18 fallback; only runs when the in-memory map missed)."""
        cards_dir = self.data_dir / "owner_cards"
        if not cards_dir.is_dir():
            return None
        for path in cards_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            execution = ((record.get("owner_card") or {}).get("execution") or {})
            if execution.get("goal_id") == goal_id:
                return {"record_path": str(path), "card_id": record.get("id")}
        return None

    async def resolve(self, ask_id: str, approved: bool) -> dict:
        """The app's approve/deny -> resolves the REAL paused goal (mirrors the text/call round-trip).
        If the goal came from an owner card, the resolution outcome (state + proof on
        YES, declined on NO) is written back onto the durable card record."""
        # BROWSER-ACTION round-trip: a YES (from the app OR an SMS "YES") kicks the browser agent on
        # the real site and texts the result back. Handled here, before the goal funnel, because it
        # runs async (1-3 min) and must not block the reply.
        p = self.proactive.pending.get(ask_id)
        if isinstance(p, dict) and p.get("category") == "browser_action":
            self.proactive.pending.pop(ask_id, None)
            self.proactive._persist_pending()
            # Reflect the resolution on the durable owner card (card.id == ask_id) so the board shows
            # the outcome: YES -> running (the agent runs async + texts back), NO -> declined (F-011).
            self._resolve_browser_card_record(ask_id, approved)
            # M3: a clean YES on a reversible web task BUILDS trust for that kind of task (promotes it
            # toward auto under Regular/Full-Send); a NO demotes it. Money/send never reach here.
            (self.trust_ledger.record_clean("browser") if approved
             else self.trust_ledger.record_rejection("browser"))
            if approved:
                _btask = p.get("browser_task") or p.get("action") or ""
                try:
                    self.text_channel.send(
                        self._user_contact(),
                        f"On it - starting the browser task now: {_btask[:160]}. I'll report back with proof.",
                    )
                except Exception as _exc:
                    self.glassbox.log("browser_action_start_text_error", {"error": str(_exc)})
                asyncio.create_task(self._run_browser_and_confirm(
                    _btask,
                    p.get("browser_url") or "https://www.google.com", ask_id))
                self.glassbox.log("browser_action_approved", {"ask_id": ask_id})
                out = {"ask_id": ask_id, "approved": True, "browser_action": True,
                       "state": "running", "goal_id": ask_id}
                try:
                    out["gateway_event"] = self.gateway_ledger.record_approval(
                        ask_id=ask_id, approved=True, source="app", result=out,
                        action=p.get("action") or "browser_action")
                except Exception as _gateway_exc:
                    self.glassbox.log("proactive_gateway_approval_error",
                                      {"error": str(_gateway_exc)[:240]})
                return out
            self.glassbox.log("browser_action_declined", {"ask_id": ask_id})
            out = {"ask_id": ask_id, "approved": False, "declined_action": p.get("action"),
                   "goal_id": ask_id}
            try:
                out["gateway_event"] = self.gateway_ledger.record_approval(
                    ask_id=ask_id, approved=False, source="app", result=out,
                    action=p.get("action") or "browser_action")
            except Exception as _gateway_exc:
                self.glassbox.log("proactive_gateway_approval_error",
                                  {"error": str(_gateway_exc)[:240]})
            return out
        # CREATE + PRINT round-trip: a YES actually prints the generated artifact (the physical action,
        # gated behind explicit consent); a NO leaves it made-but-unprinted. The artifact already exists
        # (created at ask-time), so YES is just the print. Reuses the card-landing helper -> state=done.
        if isinstance(p, dict) and p.get("category") == "create_and_print":
            self.proactive.pending.pop(ask_id, None)
            self.proactive._persist_pending()
            printer = (p.get("printer") or "")
            short = printer.split("_")[0] if printer else "the printer"
            head = p.get("headline") or "the"
            if approved:
                from ..hands.make_artifact import send_to_print
                res = send_to_print(p.get("artifact"), p.get("printer"))
                ok = bool(res.get("ok"))
                # HONEST: `lp` returning 0 means the job was ACCEPTED into the print queue — not that paper
                # came out (we can't see the physical device). Say "sent to <printer>'s queue", never the
                # unverifiable "Printed". A real lp failure -> honest, actionable error, state=failed.
                self._land_browser_result_on_card(
                    ask_id, success=ok,
                    answer=(f"Sent the “{head}” sign to {short}'s print queue" if ok
                            else f"Couldn't reach the printer ({(res.get('stderr') or 'no printer').strip()[:90]}) — the sign is saved"),
                    url=None, screenshot=False)
                self._sync_owner_loop_status(ask_id, "done" if ok else "failed")
                self.glassbox.log("create_print_approved", {"ask_id": ask_id, "ok": ok, "stderr": (res.get("stderr") or "")[:200]})
                out = {"ask_id": ask_id, "approved": True, "create_and_print": True,
                       "state": "done" if ok else "failed", "goal_id": ask_id,
                       "queued": ok, "artifact": p.get("artifact")}
                try:
                    out["gateway_event"] = self.gateway_ledger.record_approval(
                        ask_id=ask_id, approved=True, source="app", result=out,
                        action=p.get("action") or "create_and_print")
                except Exception as _gateway_exc:
                    self.glassbox.log("proactive_gateway_approval_error",
                                      {"error": str(_gateway_exc)[:240]})
                return out
            # NO: record a clean proof that the sign was MADE but not printed (never lose the artifact).
            self._land_browser_result_on_card(
                ask_id, success=False,
                answer=f"Not printed (you said no) — the “{head}” sign is saved if you want it later",
                url=None, screenshot=False)
            self._sync_owner_loop_status(ask_id, "declined")
            self.glassbox.log("create_print_declined", {"ask_id": ask_id, "artifact": p.get("artifact")})
            out = {"ask_id": ask_id, "approved": False, "declined_action": p.get("action"),
                   "goal_id": ask_id, "artifact": p.get("artifact")}
            try:
                out["gateway_event"] = self.gateway_ledger.record_approval(
                    ask_id=ask_id, approved=False, source="app", result=out,
                    action=p.get("action") or "create_and_print")
            except Exception as _gateway_exc:
                self.glassbox.log("proactive_gateway_approval_error",
                                  {"error": str(_gateway_exc)[:240]})
            return out
        out = await self.proactive.resolve_ask(ask_id, approved)
        link = self._owner_card_goals.pop(out.get("goal_id"), None) if isinstance(out, dict) else None
        if link is None and isinstance(out, dict) and out.get("goal_id"):
            # F18 durable linkage: the in-memory map can be gone (restart, desync)
            # while the card record's execution.goal_id survives on disk — derive
            # the write-back from the record itself so a resolution NEVER strands
            # an owner card at "waiting".
            link = self._find_card_record(out["goal_id"])
        if link is not None:
            goal = self.store.load(out["goal_id"])
            try:
                record = json.loads(Path(link["record_path"]).read_text(encoding="utf-8"))
            except Exception:
                record = None
            if record is not None and goal is not None:
                if approved:
                    record["state"] = goal.state.value
                    record["steps"] = [s.model_dump(mode="json") for s in goal.steps]
                    record["proof"] = goal.proof or {}
                else:
                    record["state"] = "declined"
                if isinstance(record.get("owner_card"), dict):
                    record["owner_card"]["status"] = record["state"]
                record["resolution"] = {"ask_id": ask_id, "approved": approved}
                self._sync_captured_loop_from_record(record, record["state"])
                Path(link["record_path"]).write_text(
                    json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
                self._sync_owner_loop_status(link["card_id"], record["state"])
                self.glassbox.log("owner_card_resolved",
                                  {"card_id": link["card_id"], "ask_id": ask_id,
                                   "approved": approved, "state": record["state"]})
        # HONESTY GATE (no fabricated receipts): record_approval unconditionally writes an
        # "Approved"/should_act=true/status='working' success envelope. resolve_ask returns
        # {resolved: False} when the ask is unknown or already-resolved — the action did NOTHING,
        # so writing that success receipt is a FABRICATED proof (bug: a no-op logged as a done
        # action). Only ledger the approval when the resolve GENUINELY resolved (a real approve/
        # decline/held); on a failed/unknown resolve, write NOTHING and log the honest no-op.
        if isinstance(out, dict) and out.get("resolved") is False:
            self.glassbox.log("resolve_no_pending_no_receipt",
                              {"ask_id": ask_id, "approved": approved,
                               "reason": out.get("reason")})
            return out
        try:
            out["gateway_event"] = self.gateway_ledger.record_approval(
                ask_id=ask_id,
                approved=approved,
                source="app",
                result=out,
                action=out.get("action") if isinstance(out, dict) else None,
            )
        except Exception as _gateway_exc:
            self.glassbox.log("proactive_gateway_approval_error",
                              {"error": str(_gateway_exc)[:240]})
        return out

    async def approve_remembered(self, line_id: str) -> dict:
        """DEFAULT-DENY press-go: the owner presses go on ONE remembered line.

        This is the ONLY execution trigger for a remembered/inferred item, and only for the
        whitelisted reversible intents that can be independently read back (create_event,
        write_memory). It is ADDITIVE: it reuses the review inference (display-only), the
        orchestrator funnel + GatedApprover (owner_approved), and the Slice-0 read-back gate
        verbatim. It touches no decision/trigger/harm code.

        STEP A INFER (reuse, read-only): pull the inert row by id and enrich it with the
        SAME ReviewEnricher.infer_line used by the read-only review. A vent yields an empty
        task here -> {approved:false} with NO goal, NO orchestrator call (the vent stop).

        STEP B MAP -> ONE intent + a pre-built Step (deterministic, conservative).

        STEP C WHITELIST GATE (default-deny, structural): execute ONLY if intent in
        WHITELIST; everything else is prepared-and-handed-back, never executed. Money/send/
        message land in handback because no such intent is in the set.

        CONCURRENCY: the whole load-check-build-drive runs under a per-line lock so two
        concurrent presses of the SAME line serialize. The second press, once it acquires
        the lock, finds the first press's goal already done and returns its receipt
        (idempotent) — exactly ONE real write. The lock is keyed on the stable goal_id
        derived from line_id, so different lines never block each other.
        """
        goal_id = "rmb-" + hashlib.sha256(line_id.encode()).hexdigest()[:24]
        lock = await self._press_go_lock_for(goal_id)
        async with lock:
            return await self._approve_remembered_locked(line_id, goal_id)

    async def _press_go_lock_for(self, goal_id: str) -> asyncio.Lock:
        async with self._press_go_locks_guard:
            lock = self._press_go_locks.get(goal_id)
            if lock is None:
                lock = asyncio.Lock()
                self._press_go_locks[goal_id] = lock
            return lock

    async def _approve_remembered_locked(self, line_id: str, goal_id: str) -> dict:
        from ..live_memory.review_infer import infer_line
        from ..live_memory.press_go import (WHITELIST, action_content_key,
                                            map_inferred_to_step)

        cap = self.live_memory.capturer
        row = next((r for r in cap.remember.all() if r.get("id") == line_id), None)
        if row is None:
            return {"approved": False, "line_id": line_id, "reason": "unknown remembered line"}

        # STEP A — INFER (reuse the display-only review inference, read-only).
        inferred = infer_line(str(row.get("text") or ""), people_hint=row.get("people"))
        task = str(inferred.get("task") or "").strip()
        if not task:
            # vent / narration: refuse — no goal, no orchestrator, no pending entry.
            self.glassbox.log("press_go_vent", {"line_id": line_id})
            return {"approved": False, "line_id": line_id, "inferred": inferred,
                    "reason": "no confident inferred task (vent/narration)"}

        # STEP B — MAP inferred task -> a single intent + pre-built Step (or handback).
        # The raw spoken line grounds a concrete event time (the review's due_phrase is
        # lossy); the whitelist DECISION is keyed off the inferred shape. TIMEZONE: ground
        # the calendar hold in the OWNER's onboarded zone (profile drawer) so start/end ISO
        # carry the owner's offset, not the server's — pass the owner tz-aware now + tz.
        tz, _tz_name = self._owner_timezone()
        owner_now = dt.datetime.now(tz)
        mapped = map_inferred_to_step(inferred, raw_text=str(row.get("text") or ""),
                                      now=owner_now, tz=tz)
        intent = mapped.get("intent")
        step = mapped.get("step")

        # STEP C — WHITELIST GATE. Default-deny: execute ONLY if the intent is in the set.
        if intent not in WHITELIST or step is None:
            # NON-WHITELIST branch: prepared-handback. NO Goal saved, orchestrator NEVER
            # called, nothing enters proactive.pending. Money/send/message land here.
            self.glassbox.log("press_go_handback",
                              {"line_id": line_id, "intent": intent or "(unmapped)",
                               "reason": mapped.get("non_whitelist_reason")})
            return {"approved": False, "prepared": True, "line_id": line_id,
                    "inferred_action": task, "intent": intent,
                    "would_do": mapped.get("would_do"),
                    "why_handback": (mapped.get("non_whitelist_reason")
                                     or "not a provably-safe reversible intent")}

        # Defense in depth: the produced step intent MUST be in WHITELIST before we drive.
        if step.intent not in WHITELIST:
            self.glassbox.log("press_go_handback",
                              {"line_id": line_id, "intent": step.intent,
                               "reason": "produced step intent not whitelisted"})
            return {"approved": False, "prepared": True, "line_id": line_id,
                    "inferred_action": task, "intent": step.intent,
                    "would_do": mapped.get("would_do"),
                    "why_handback": "produced step intent not whitelisted"}

        # WHITELIST branch — execute via the EXISTING funnel. Build a goal with ONE
        # pre-built whitelisted step + owner_approved proof, then drive it through the
        # orchestrator (GatedApprover reads owner_approved; the api_hand read-back gate
        # still independently confirms the artifact — Law 4). Same reuse pattern as
        # resolve_ask's already-stepped (_approve_waiting_goal + _drive) path, so no
        # planner can widen the single step into a non-whitelisted write.
        #
        # Line-level idempotency: ``goal_id`` is a STABLE id derived from the line_id (by
        # the locking wrapper) so re-pressing the same line reuses the same goal. If that
        # goal already ran to done, return its receipt without re-driving — the endpoint is
        # safe to re-press (no double-create of a calendar hold / draft). The per-line lock
        # held by the wrapper makes this load-check-build-drive atomic, so a CONCURRENT
        # second press also lands here only after the first completed and finds it done.
        prior = self.store.load(goal_id)
        if prior is not None and prior.state == GoalState.done:
            self.glassbox.log("press_go_idempotent",
                              {"line_id": line_id, "goal_id": goal_id})
            return {"approved": True, "executed": True, "idempotent": True,
                    "line_id": line_id, "intent": prior.intent, "goal_id": prior.id,
                    "state": prior.state.value, "would_do": mapped.get("would_do"),
                    "receipt": prior.proof or {}}

        # CONTENT-level idempotency: the same task captured TWICE arrives as two DIFFERENT
        # remembered lines -> two different line_ids -> two different goal_ids, so the
        # line-keyed check above would miss them and a second real calendar hold would form.
        # Dedupe on the ACTION CONTENT instead (intent + normalized summary + grounded
        # start). If a DONE goal already carries this content_key, short-circuit to ITS
        # receipt — exactly ONE real write for the same action, however many lines say it.
        # Held under the same per-line lock as everything else here; a same-content goal
        # from a DIFFERENT line is found by scanning the store (its own line's lock does not
        # gate this one, but the first writer's goal is already done by the time we scan).
        content_key = action_content_key(intent, step)
        if content_key:
            for g in self.store.all():
                if (g.id != goal_id and g.state == GoalState.done
                        and (g.proof or {}).get("content_key") == content_key):
                    self.glassbox.log("press_go_content_idempotent",
                                      {"line_id": line_id, "goal_id": g.id,
                                       "content_key": content_key})
                    return {"approved": True, "executed": True, "idempotent": True,
                            "line_id": line_id, "intent": g.intent, "goal_id": g.id,
                            "state": g.state.value, "would_do": mapped.get("would_do"),
                            "receipt": g.proof or {}}

        goal = Goal(id=goal_id, intent=intent, description=mapped.get("would_do") or task,
                    steps=[step])
        goal.proof = {"owner_approved": True, "approved_from": "remembered",
                      "line_id": line_id, "content_key": content_key}
        goal.state = GoalState.running
        self.store.save(goal)
        self.glassbox.log("press_go_execute",
                          {"line_id": line_id, "intent": intent, "goal_id": goal.id})
        goal = await self.orchestrator._drive(goal)

        # Re-stamp the content_key onto the finished goal: _drive replaces goal.proof with
        # the step read-back receipts (Law 4), which would drop the key and defeat the
        # content-dedup scan above. Persist it back into the proof so the NEXT same-content
        # press finds this done goal and returns its receipt (one real write per action).
        if content_key and goal.state == GoalState.done:
            goal.proof = {**(goal.proof or {}), "content_key": content_key}
            self.store.save(goal)

        receipt = goal.proof or {}
        return {"approved": True, "executed": True, "line_id": line_id, "intent": intent,
                "goal_id": goal.id, "state": goal.state.value,
                "would_do": mapped.get("would_do"), "receipt": receipt}

    # The human-readable tool each AUTO-EXECUTABLE (whitelisted) intent WOULD call live.
    # create_event routes through the Arcade api_hand (authoritative INTENT_MAP) and is read
    # back via ListEvents; write_memory is a LOCAL standing note (no external tool, never
    # leaves the device). send_email_draft is NOT here — a draft is a prepared-handback (no
    # wired drafts read-back yet), so it never reaches this whitelist preview branch.
    _DRYRUN_TOOL = {
        "create_event": "GoogleCalendar.CreateEvent",
        "write_memory": "Anticipy.Memory (local note — no external account)",
    }

    def dryrun_remembered(self, line_id: str) -> dict:
        """LIVE DRY-RUN PREVIEW: show EXACTLY what press-go WOULD do, WITHOUT doing it.

        Trust-before-connect. This runs the SAME default-deny press-go mapping as
        ``approve_remembered`` (the SAME review inference + the SAME ``map_inferred_to_step``
        + the SAME WHITELIST gate) but STOPS before execution: it NEVER builds or saves a
        Goal, NEVER calls ``orchestrator.start_goal`` / ``orchestrator._drive``, NEVER
        writes a memory note, and NEVER touches the api/browser hands. It only PLANS and
        SHOWS, so the owner can see his whole day's planned real actions before connecting
        any account.

        Returns a preview dict:
          whitelisted line ->
            {would_execute: True, line_id, intent,
             tool (e.g. GoogleCalendar.CreateEvent / Gmail.WriteDraftEmail),
             args (the EXACT args press-go would send), would_do,
             note: "This runs for real once you connect Google"}
          non-whitelisted line ->
            {would_execute: False, line_id, intent: None, handback: <human description>,
             why: <reason>}
          vent / narration ->
            {would_execute: False, line_id, intent: None, why: <vent stop>}
        """
        from ..live_memory.review_infer import infer_line
        from ..live_memory.press_go import WHITELIST, map_inferred_to_step

        cap = self.live_memory.capturer
        row = next((r for r in cap.remember.all() if r.get("id") == line_id), None)
        if row is None:
            return {"would_execute": False, "line_id": line_id, "intent": None,
                    "why": "unknown remembered line"}

        raw_text = str(row.get("text") or "")

        # STEP A — INFER (reuse the display-only review inference, read-only). A vent yields
        # an empty task -> preview says nothing would execute (the vent stop, surfaced).
        inferred = infer_line(raw_text, people_hint=row.get("people"))
        task = str(inferred.get("task") or "").strip()
        if not task:
            self.glassbox.log("dryrun_vent", {"line_id": line_id})
            return {"would_execute": False, "line_id": line_id, "intent": None,
                    "inferred": inferred,
                    "why": "no confident inferred task (vent/narration)"}

        # STEP B — MAP inferred task -> a single intent + pre-built Step (or handback). This
        # is the IDENTICAL call approve_remembered makes (SAME owner timezone grounding, so
        # the preview's start/end ISO carry the owner's offset — the preview must match what
        # approve would really do). The raw line grounds a concrete event time. We read the
        # plan but DO NOT drive it.
        tz, _tz_name = self._owner_timezone()
        owner_now = dt.datetime.now(tz)
        mapped = map_inferred_to_step(inferred, raw_text=raw_text,
                                      now=owner_now, tz=tz)
        intent = mapped.get("intent")
        step = mapped.get("step")

        # STEP C — WHITELIST GATE preview. Default-deny: only an intent in the set WOULD
        # execute. Everything else is shown as handback — exactly what approve would return,
        # minus any execution.
        if intent not in WHITELIST or step is None:
            self.glassbox.log("dryrun_handback",
                              {"line_id": line_id, "intent": intent or "(unmapped)"})
            return {"would_execute": False, "line_id": line_id, "intent": intent,
                    "inferred_action": task,
                    "handback": mapped.get("would_do"),
                    "why": (mapped.get("non_whitelist_reason")
                            or "not a provably-safe reversible intent")}

        # WHITELIST branch — show the concrete planned action. We surface the EXACT args the
        # whitelisted Step carries (the same args approve_remembered would send through the
        # orchestrator), the tool it WOULD call, and the connect-first note. NOTHING is
        # executed: no Goal is built or saved, the orchestrator is never invoked.
        args = dict(step.args)
        self.glassbox.log("dryrun_preview",
                          {"line_id": line_id, "intent": intent})
        return {"would_execute": True, "line_id": line_id, "intent": intent,
                "tool": self._DRYRUN_TOOL.get(intent, intent),
                "args": args, "would_do": mapped.get("would_do"),
                "note": ("This runs for real once you connect Google"
                         if intent == "create_event"
                         else "This saves a local note when you press go (no account needed)")}
