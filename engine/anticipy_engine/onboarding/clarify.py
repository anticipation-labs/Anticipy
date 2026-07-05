"""Clarifying-call questions — the BRAIN of Anticipy's onboarding phone call.

Omar's onboarding line: "it jumps on a phone call to clarify — can I ask you a
couple of questions?" This module is that brain. Given a built `Profile`
(from profile_builder.py — facts carrying confidence + needs_cross_check +
trust, plus blockers and per-source read state), it produces the SHORT, ranked
list of clarifying questions Anticipy would actually ask, so the call stays a
"couple of questions," not an interrogation.

The actual phone delivery (Twilio voice) is LIVE-DEFERRED; this is the planner
that decides WHAT to ask and IN WHAT ORDER. It is deterministic and unit-testable
(no model, no network): the same profile always yields the same questions.

What earns a question (most-uncertain first):

  1. SOURCE DISAGREEMENT — two sources gave different values for the same field
     (e.g. two locations). The single most valuable thing to resolve on a call:
     Anticipy literally cannot pick, and a wrong pick poisons everything
     downstream. Surfaced with the conflicting `candidates` so the call can read
     them back ("I saw Austin and also Seattle — which is right?").
  2. LOW-CONFIDENCE / NEEDS-CROSS-CHECK fact — a value we have but only from a
     low-trust FINE pull (the browser arm grading its own homework). We ask the
     human to confirm it before trusting it as ground truth.
  3. BLOCKER — a source we could not read at all. We can't ask about a fact we
     never got, so we ask the human to fill the gap directly (or hand us a
     readable source).
  4. OBVIOUS GAP — a core field (role / org / location) no source yielded any
     value for. No value, no disagreement, just absent — ask plainly.

Honesty by construction: we ONLY ask about uncertainty the profile actually
records. We never invent a disagreement, never ask about a field that read clean
and high-confidence, and never ask a question we couldn't answer with the
candidates the profile carries. Cap at ~5, ordered most-uncertain first, so the
call is short.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# Core fields a useful profile should carry. An absent one (no value AND no
# disagreement) is an "obvious gap" worth a plain question.
_CORE_FIELDS = ("role", "org", "location")

# Human-friendly nouns for the core fields (used in question text).
_FIELD_NOUN = {
    "role": "role or title",
    "org": "main organization or company",
    "location": "location",
}

# Default cap — keep the call to "a couple of questions," not an interrogation.
DEFAULT_MAX_QUESTIONS = 5

# Priority rank per reason (lower = asked first). Disagreements are the single
# most valuable thing to resolve on a call; obvious gaps are the least urgent.
_REASON_RANK = {
    "disagreement": 0,
    "low_confidence": 1,
    "blocker": 2,
    "gap": 3,
}

# Confidence ordering, for ranking low-confidence facts among themselves.
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass
class ClarifyingQuestion:
    """One question Anticipy would ask on the clarifying call.

    field       : the profile field the question is about (role/org/location/
                  overview/<source-url> for a blocker).
    question_text: the spoken question.
    why         : the uncertainty that earned the question (for the glassbox /
                  so the call can explain itself).
    reason      : machine tag — disagreement | low_confidence | blocker | gap.
    candidates  : conflicting/known values to read back, if any (empty otherwise).
    """

    field: str
    question_text: str
    why: str
    reason: str
    candidates: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _fact_values_by_field(profile: Any) -> Dict[str, List[Any]]:
    """Group a profile's key_facts by field name, preserving order."""
    by_field: Dict[str, List[Any]] = {}
    for f in getattr(profile, "key_facts", []) or []:
        by_field.setdefault(f.field, []).append(f)
    return by_field


def _distinct_values(facts: List[Any]) -> List[str]:
    """Distinct fact values (case-insensitively), in first-seen order."""
    seen: set = set()
    out: List[str] = []
    for f in facts:
        v = (getattr(f, "value", "") or "").strip()
        if not v:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def _field_noun(field_name: str) -> str:
    return _FIELD_NOUN.get(field_name, field_name)


def _disagreement_questions(by_field: Dict[str, List[Any]]) -> List[ClarifyingQuestion]:
    """Two+ sources gave DIFFERENT values for one field -> ask which is right.

    Only core, human-meaningful fields are surfaced as disagreements (we don't
    quiz the human on prose-overview wording differences).
    """
    questions: List[ClarifyingQuestion] = []
    for fld in _CORE_FIELDS:
        facts = by_field.get(fld, [])
        values = _distinct_values(facts)
        if len(values) < 2:
            continue
        joined = " or ".join(values)
        questions.append(
            ClarifyingQuestion(
                field=fld,
                question_text=(
                    f"Different sources gave different answers for your "
                    f"{_field_noun(fld)} — I saw {joined}. Which is right?"
                ),
                why=(
                    f"sources disagree on {fld}: "
                    + ", ".join(repr(v) for v in values)
                ),
                reason="disagreement",
                candidates=values,
            )
        )
    return questions


def _low_confidence_questions(
    by_field: Dict[str, List[Any]],
    skip_fields: set,
) -> List[ClarifyingQuestion]:
    """A value we have but only from a low-trust / needs_cross_check pull -> ask
    the human to confirm it. Skips fields already covered by a disagreement
    (that question already surfaces the value).
    """
    questions: List[ClarifyingQuestion] = []
    for fld, facts in by_field.items():
        if fld in skip_fields or fld == "overview":
            continue
        # Best (lowest-confidence-but-present) shaky fact for this field.
        shaky = [
            f
            for f in facts
            if getattr(f, "needs_cross_check", False)
            and (getattr(f, "value", "") or "").strip()
        ]
        if not shaky:
            continue
        # Rank shaky facts by confidence (lowest first); take the value to confirm.
        shaky.sort(key=lambda f: _CONFIDENCE_RANK.get(getattr(f, "confidence", "low"), 0))
        value = shaky[0].value.strip()
        conf = getattr(shaky[0], "confidence", "low")
        questions.append(
            ClarifyingQuestion(
                field=fld,
                question_text=(
                    f"I think your {_field_noun(fld)} is {value} — did I get that right?"
                ),
                why=(
                    f"{fld} came from a low-trust read "
                    f"(confidence={conf}, needs_cross_check) and should be confirmed"
                ),
                reason="low_confidence",
                candidates=[value],
            )
        )
    return questions


def _blocker_questions(profile: Any) -> List[ClarifyingQuestion]:
    """A source we could not read at all -> ask the human to fill the gap.

    We can't ask about a specific fact we never got, so we ask broadly and name
    the source we couldn't open, honestly.
    """
    questions: List[ClarifyingQuestion] = []
    # Prefer the structured per-source read state (carries the url); fall back to
    # the blocker strings if sources aren't populated.
    blocked_urls: List[str] = []
    for s in getattr(profile, "sources", []) or []:
        if not getattr(s, "read_ok", False):
            url = getattr(s, "url", None)
            if url:
                blocked_urls.append(url)
    if not blocked_urls:
        for b in getattr(profile, "blockers", []) or []:
            blocked_urls.append(str(b))

    for url in blocked_urls:
        questions.append(
            ClarifyingQuestion(
                field=url,
                question_text=(
                    "I couldn't read one of the sources you gave me, so I might be "
                    "missing something. Is there anything important about you I "
                    "should know?"
                ),
                why=f"could not read source: {url}",
                reason="blocker",
                candidates=[],
            )
        )
    return questions


def _gap_questions(
    profile: Any,
    by_field: Dict[str, List[Any]],
    skip_fields: set,
) -> List[ClarifyingQuestion]:
    """A core field no source yielded any value for -> ask plainly."""
    questions: List[ClarifyingQuestion] = []
    for fld in _CORE_FIELDS:
        if fld in skip_fields:
            continue
        # Has a top-level hoisted value OR any non-empty fact? Then not a gap.
        top = getattr(profile, fld, None)
        has_value = bool(top and str(top).strip()) or bool(
            _distinct_values(by_field.get(fld, []))
        )
        if has_value:
            continue
        questions.append(
            ClarifyingQuestion(
                field=fld,
                question_text=f"What's your {_field_noun(fld)}?",
                why=f"no source provided a {fld}",
                reason="gap",
                candidates=[],
            )
        )
    return questions


def clarifying_questions(
    profile: Any,
    *,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
) -> List[ClarifyingQuestion]:
    """Plan the clarifying call for a built `Profile`.

    Returns the ranked, capped list of questions, most-uncertain first:
    disagreements -> low-confidence confirmations -> blockers -> obvious gaps.
    Deterministic; no model or network. Only asks about uncertainty the profile
    actually records (never invents a disagreement or quizzes a clean field).
    """
    by_field = _fact_values_by_field(profile)

    disagreements = _disagreement_questions(by_field)
    disagreement_fields = {q.field for q in disagreements}

    low_conf = _low_confidence_questions(by_field, skip_fields=disagreement_fields)
    covered = disagreement_fields | {q.field for q in low_conf}

    blockers = _blocker_questions(profile)
    gaps = _gap_questions(profile, by_field, skip_fields=covered)

    # Stable order: by reason rank, preserving discovery order within a reason.
    ordered = disagreements + low_conf + blockers + gaps
    ordered.sort(key=lambda q: _REASON_RANK.get(q.reason, 99))

    if max_questions is not None and max_questions >= 0:
        ordered = ordered[:max_questions]
    return ordered


def clarify_payload(
    profile: Any,
    *,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
) -> Dict[str, Any]:
    """Serializable clarifying-call plan for the HTTP surface / glassbox.

    Carries the questions plus an honesty summary so the caller can see WHY the
    call is (or isn't) needed without re-deriving it.
    """
    questions = clarifying_questions(profile, max_questions=max_questions)
    by_reason: Dict[str, int] = {}
    for q in questions:
        by_reason[q.reason] = by_reason.get(q.reason, 0) + 1
    return {
        "name": getattr(profile, "name", None),
        "questions": [q.as_dict() for q in questions],
        "summary": {
            "count": len(questions),
            "by_reason": by_reason,
            "needs_call": bool(questions),
            "delivery": "live-deferred (Twilio voice)",
        },
    }


# ---------------------------------------------------------------------------
# OWNER INHALE DOSSIER path — the clarify planner FED BY THE SCRAPE it follows.
#
# The functions above plan a call over a public-web ``Profile`` (profile_builder.py). But the
# onboarding scrape<->call loop follows a DIFFERENT input: the owner's own inhaled accounts,
# synthesized by dossier.py into a dossier that itself lists the ``gaps`` a short call should
# fill. THIS is the input the outbound onboarding call must follow up on. The functions below
# read that owner inhale dossier (the dict returned by dossier.synthesize_dossier / loop.run_loop)
# and rank its gaps into the same ``ClarifyingQuestion`` shape, so the call arm (call_out.py) can
# ask exactly what the inhale left open — never a public-web profile it never scraped.
# ---------------------------------------------------------------------------

# Core identity fields a useful owner dossier should carry; an absent one is a plain gap to ask.
_DOSSIER_CORE_FIELDS = ("role", "location")

# Keyword -> core field, so a free-text model gap ("your role or title") is tagged to a field
# instead of a generic bucket (lets the call arm re-aim identity when the owner answers).
_GAP_FIELD_HINTS = (
    ("role", ("role", "title", "job", "what you do", "position")),
    ("org", ("org", "company", "startup", "employer", "business", "team you")),
    ("location", ("location", "based", "where you", "city", "timezone", "time zone")),
)


def _dossier_inner(dossier: Any) -> Dict[str, Any]:
    """The inner profile dict, accepting either the synthesize RESULT ({"dossier": {...}, "gaps":..})
    or a bare inner dossier ({"identity":.., "gaps":..})."""
    if not isinstance(dossier, dict):
        return {}
    inner = dossier.get("dossier")
    if isinstance(inner, dict):
        return inner
    return dossier


def _dossier_gaps(dossier: Any) -> List[str]:
    """The dossier's own list of still-unknown gaps (top-level or inner), cleaned of blanks."""
    if not isinstance(dossier, dict):
        return []
    gaps = dossier.get("gaps")
    if gaps is None:
        gaps = _dossier_inner(dossier).get("gaps")
    out: List[str] = []
    seen: set = set()
    for g in (gaps or []):
        if not isinstance(g, str):
            continue
        g = g.strip()
        if not g or g.lower() in seen:
            continue
        seen.add(g.lower())
        out.append(g)
    return out


def _dossier_identity(dossier: Any) -> Dict[str, Any]:
    ident = _dossier_inner(dossier).get("identity")
    return ident if isinstance(ident, dict) else {}


def _gap_field(gap: str) -> str:
    low = gap.lower()
    for fld, kws in _GAP_FIELD_HINTS:
        if any(kw in low for kw in kws):
            return fld
    return "profile"


def _gap_as_question(gap: str) -> str:
    """Phrase a free-text gap as a spoken question, deterministically."""
    g = gap.strip()
    if g.endswith("?"):
        return g[0].upper() + g[1:]
    lead = g[0].lower() + g[1:] if g else g
    return f"Can you tell me about {lead}?"


def clarifying_questions_from_dossier(
    dossier: Any,
    *,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
) -> List[ClarifyingQuestion]:
    """Rank the OWNER INHALE DOSSIER's gaps into the couple of questions the setup call should ask.

    Reads the dict dossier.synthesize_dossier / loop.run_loop produce (never a public-web Profile):
      1. the dossier's OWN ``gaps`` — the model-flagged still-unknowns, most-useful first (order kept);
      2. any CORE identity field (role / location) still empty and not already covered by a gap.
    Honest by construction: it only asks about what the inhale actually left open — an empty ``gaps``
    on a confident dossier yields NO questions (no call needed). Deterministic; no model, no network.
    """
    questions: List[ClarifyingQuestion] = []
    covered: set = set()

    for gap in _dossier_gaps(dossier):
        fld = _gap_field(gap)
        questions.append(
            ClarifyingQuestion(
                field=fld,
                question_text=_gap_as_question(gap),
                why=f"the inhale dossier flagged this as still unknown: {gap}",
                reason="gap",
                candidates=[],
            )
        )
        covered.add(fld)

    identity = _dossier_identity(dossier)
    for fld in _DOSSIER_CORE_FIELDS:
        if fld in covered:
            continue
        val = identity.get(fld)
        if isinstance(val, str) and val.strip():
            continue
        questions.append(
            ClarifyingQuestion(
                field=fld,
                question_text=f"What's your {_field_noun(fld)}?",
                why=f"the inhale produced no {fld} for the owner",
                reason="gap",
                candidates=[],
            )
        )
        covered.add(fld)

    if max_questions is not None and max_questions >= 0:
        questions = questions[:max_questions]
    return questions


def clarify_dossier_payload(
    dossier: Any,
    *,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
) -> Dict[str, Any]:
    """Serializable clarify plan for the OWNER INHALE DOSSIER (the call arm's agenda)."""
    questions = clarifying_questions_from_dossier(dossier, max_questions=max_questions)
    by_reason: Dict[str, int] = {}
    for q in questions:
        by_reason[q.reason] = by_reason.get(q.reason, 0) + 1
    return {
        "name": _dossier_identity(dossier).get("name"),
        "questions": [q.as_dict() for q in questions],
        "summary": {
            "count": len(questions),
            "by_reason": by_reason,
            "needs_call": bool(questions),
            "delivery": "outbound onboarding call (Twilio; live-gated, mock-simulated)",
            "source": "owner_inhale_dossier",
        },
    }
