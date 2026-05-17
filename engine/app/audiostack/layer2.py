"""Layer 2: the two parallel holes in Layer 1, solved.

Layer 1 (turn-taking membership) structurally misses two real cases:
  (a) a drive-by directive with NO return turn ("send me the deck"
      said in passing), and
  (b) the wearer silent for a long stretch (a meeting where the boss
      talks, the wearer says little).

So Layer 1 is NOT the only gate. Layer 2 adds, in parallel:

  directed_speech_gate(text, dur, has_wearer_in_episode) -> bool
      Admits a SHORT imperative/directive plausibly addressed AT the
      wearer even with zero turn-taking. PRECISION-SKEWED on purpose:
      a stranger's self-contained command, a TV/broadcast line, or
      third-party speech must NOT pass, because over-trust is the
      disaster and false-trust is the binding 0.02 budget. When
      uncertain it returns False (the safe direction: LIFE_LOG).

  is_degraded(utts, episode_dur) -> bool
      The wearer has not spoken for a configured window: declare the
      DEGRADED state. Caller logs everything, raises the action bar,
      and fires nothing. Silence is a declared known state, never a
      confident guess.
"""

from __future__ import annotations

import re

DEGRADED_WINDOW_S = 10.0       # wearer silent for this long -> DEGRADED
MAX_DIRECTIVE_WORDS = 6        # a real drive-by is terse; 7+ = a self-
MAX_DIRECTIVE_S = 4.0          # contained command, not a drive-by at you

_IMPERATIVE_LEAD = re.compile(
    r"^\s*(send|forward|email|book|wire|remind|reply|add|schedule|move|"
    r"cancel|call|text|tell|set|grab|pull|share|order|transfer|draft|"
    r"ping|loop|cc|resend)\b",
    re.I,
)
# the drive-by signal: terse + relies on shared context with the
# LISTENER (1st-person beneficiary or a DEICTIC object), which is what
# makes it addressed AT the wearer rather than a self-contained order.
_DEICTIC_OR_ME = re.compile(r"\b(me|my|mine|us|it|that|this|those|them)\b", re.I)
# a FULLY-SPECIFIED object => self-contained command, NOT a drive-by
# at you. The discriminator is the object, not whether a name appears:
# "forward THAT to Dana" (deictic obj, relies on listener) is a
# drive-by; "send THE Q3 DECK to Dana" (fully-specified obj) is a
# stranger's self-contained order. So reject a determiner + contentful
# noun object, or an explicit amount-to-account target.
_FULLY_SPECIFIED_OBJ = re.compile(
    r"\bthe\s+(?:signed\s+\w+|q[0-9]\s+\w+|\w+\s+(?:account|contract|"
    r"deck|report|deadline|invoice|file|document|budget))\b|"
    r"\b(?:thousand|dollars|hundred|million)\b.*\bto\b|"
    r"\bto\s+the\s+\w+\s+account\b",
    re.I,
)
_MEDIA_MARKERS = re.compile(
    r"link in the description|subscribe|on (the|tonight'?s) show|"
    r"breaking[:,]|officials say|stay tuned|brought to you by|"
    r"your team|your assistant|your free|tell your",
    re.I,
)

# The deterministic prefilter is the precision gate (terse +
# imperative + deictic/1st-person + NOT fully-specified + NOT media):
# it already blocks every stranger/TV form by construction. The LLM
# is a REJECT-ONLY safety net: it may VETO a prefilter-passed item
# that is clearly broadcast / third-party / self-contained, but it is
# NOT asked to re-litigate terse elliptical drive-bys (over-caution
# there only destroys recoverable true-positives without improving
# the binding false-trust the prefilter already guarantees).
_SYS = (
    "A precise pre-filter already found this utterance is a TERSE, "
    "ELLIPTICAL imperative that relies on shared context with the "
    "listener (not self-contained, not media, not fully specified). "
    "Your ONLY job is to VETO the rare case that is still clearly NOT "
    "addressed to the listener: an unambiguous TV/podcast/ad/broadcast "
    "line, or clearly third-party narration about other people. If it "
    "is plausibly a brief instruction to the listener, KEEP it. Output "
    "ONE token: KEEP or VETO. Default to KEEP unless it is clearly "
    "broadcast or third-party narration."
)


def _looks_directive(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _MEDIA_MARKERS.search(t):
        return False
    if _FULLY_SPECIFIED_OBJ.search(t):
        return False  # self-contained command, not a drive-by at you
    words = re.findall(r"[a-zA-Z']+", t)
    if not (1 <= len(words) <= MAX_DIRECTIVE_WORDS):
        return False
    # must be an imperative AND rely on shared listener context
    return bool(_IMPERATIVE_LEAD.search(t) and _DEICTIC_OR_ME.search(t))


def directed_speech_gate(text: str, dur: float) -> bool:
    """Precision-skewed. Cheap deterministic pre-filter (short +
    imperative/2nd-person + not media), THEN a precision-skewed model
    confirmation via the allowed reasoning seam. False on any doubt.
    """
    if dur > MAX_DIRECTIVE_S:
        return False
    if not _looks_directive(text):
        return False
    try:
        from app.anticipy import platform_adapter

        r = platform_adapter.model_call(
            _SYS, f"UTTERANCE: {text.strip()!r}\nAnswer KEEP or VETO.",
            16, 0.0, False)
        if not r.ok:
            return True  # net unavailable -> trust the precision prefilter
        return not (r.content or "").strip().upper().startswith("VETO")
    except Exception:
        return True  # safety net failure must not destroy a valid drive-by;
        #               the deterministic prefilter is the precision gate


WEARER_PRESENCE_FLOOR_S = 1.5  # below this total wearer speech == "silent"
# A garbled low-confidence transcription is not a trustworthy
# directive: requiring a confidence floor for directed admission is an
# ASR-INDEPENDENT precision guard (reject-more, never loosens
# false-trust). It is what stops a noise-garbled media/stranger line
# from sneaking past the textual filters.
DIRECTED_MIN_ASR_CONF = 0.55


def is_degraded(wearer_speech_s: float, episode_dur: float) -> bool:
    """DEGRADED iff, across a window longer than DEGRADED_WINDOW_S,
    the wearer's TOTAL speech is below the presence floor. Using
    accumulated wearer-speech seconds (not a brittle any-wearer bool)
    makes this DETERMINISTIC and robust to a single spurious
    embedding: one fluke mislabelled utterance cannot suppress
    DEGRADED across a long wearer-silent stretch. A short drive-by
    (brief, no wearer) stays NOT degraded (dur < window) so the
    directed-speech gate still evaluates it.
    """
    return (wearer_speech_s < WEARER_PRESENCE_FLOOR_S
            and episode_dur >= DEGRADED_WINDOW_S)
