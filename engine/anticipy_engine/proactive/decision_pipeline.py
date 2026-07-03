"""Canonical proactive decision pipeline.

This is the live-repo version of the strongest older DEV-FINAL idea: make one
wearer-aware structured judgment before card shaping. The rest of the owner path
still owns routing, memory writes, approvals, browser proof, and follow-up, but
this module decides the first-order question that kept causing 90%-done loops:

    who owns the task, is it real, and what should the system do with it?
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..core.gateway import ModelGateway, PROVIDER_GEMINI, PROVIDER_OPENROUTER, SMART

Actor = Literal["owner", "assistant", "listener", "third_party", "unknown"]
Realness = Literal[
    "real",
    "vent",
    "sarcasm",
    "hypothetical",
    "brainstorm",
    "pleasantry",
    "stale_conditional",
    "retracted",
    "already_done",
    "status_question",
    "physical_only",
    "ambient",
    "ambiguous",
]
Decision = Literal["ignore", "remember", "ask", "act", "block", "follow_up"]

DEFAULT_DECISION_MODEL = "google/gemini-2.5-flash"

_PHYSICAL_OR_SOCIAL_NON_TASK = re.compile(
    r"\b(?:get|take|bring)\s+(?:them|kids?|children|the\s+kids)\s+(?:out\s+)?"
    r"(?:to\s+)?(?:the\s+)?(?:park|outside|outdoors|out\s+of\s+the\s+house)\b"
    r"[\w\s,.'-]{0,60}?\b(?:later|sometime|soon|maybe|if\s+)"
    r"|\b(?:grab|get|do)\s+(?:coffee|lunch|dinner|drinks)\b"
    r"[\w\s,.'-]{0,80}?\b(?:sometime|soon|when\s+things\s+calm\s+down|one\s+day)\b",
    re.I,
)
_HEDGED_LATENT_REPLY = re.compile(
    r"\bI\s+should\s+probably\s+(?:text|call|email|reply\s+to|get\s+back\s+to)\b"
    r"(?![^.?!]{0,90}\b(?:by|before|at|today|tomorrow|tonight|this\s+(?:morning|afternoon|evening)|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b)",
    re.I,
)
_SARCASTIC_AVERSION = re.compile(
    r"(?:^\s*(?:great|awesome|perfect|fantastic),?\s+)?another\b[\w\s,.'-]{0,80}?\bI\s+get\s+to\b",
    re.I,
)
_CONDITIONAL_WEATHER_CONTEXT = re.compile(
    r"\bif\s+(?:it\s+)?rains?\b|\bwashout\b|\brain\s+is\s+the\s+hard\s+stop\b|\bcancel\s+the\s+picnic\b",
    re.I,
)
_WEATHER_CHECK = re.compile(r"\b(?:check|look(?:ing)?|take\s+a\s+look)\b[\w\s,.'-]{0,50}?\b(?:weather|forecast)\b", re.I)
_REVIEW_NEED = re.compile(
    r"\bI\s+(?:really\s+)?need\s+to\s+review\s+(?:the\s+)?([^.\n?!]{5,120}?)(?:\s+before\b|[.?!\n]|$)",
    re.I,
)
# A first-person plan to go out (meal/drinks) at a CONCRETE time but with an UNSPECIFIED venue is not a
# vague pleasantry — it is the owner's own plan missing one slot (which place). Anticipy should ASK which
# spot / offer to pick or book one, not silently ignore it. Requires all four signals so "grab coffee
# sometime" (no concrete time) and "dinner at Nobu at 7" (venue already specified) do NOT trigger it.
_MEAL_SOCIAL = re.compile(r"\b(?:dinner|lunch|breakfast|brunch|drinks|coffee|a\s+meal|a\s+bite)\b", re.I)
_CONCRETE_TIME = re.compile(
    r"\b(?:tonight|today|tomorrow|this\s+(?:morning|afternoon|evening|weekend)|later\s+today|"
    r"at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", re.I)
_UNSPECIFIED_VENUE = re.compile(
    r"\b(?:a\s+(?:nice|good|new|cool|fancy|great)\s+(?:place|spot|restaurant)|"
    r"a\s+(?:place|spot|restaurant)|somewhere(?:\s+nice)?|some\s*place)\b", re.I)
_FIRST_PERSON_PLAN = re.compile(
    r"\b(?:let'?s|we\b|i\s+(?:want|wanna|feel\s+like|should|need)|wanna|gonna|"
    r"thinking\s+(?:of|about))\b", re.I)


class ProactiveCandidateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    speaker: str = ""
    addressee: str = ""
    actor: Actor = "unknown"
    realness: Realness = "ambiguous"
    decision: Decision = "ignore"
    task_text: str = ""
    evidence_span: str = ""
    confidence: float = 0.0
    reason: str = ""
    source_truth_case_id: str | None = None


class ProactiveDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool = False
    wearer: str = "the wearer"
    is_pure_brainstorm: bool = False
    wearer_has_own_task: bool = False
    decisions: list[ProactiveCandidateDecision] = Field(default_factory=list)
    raw_response: str = ""
    error: str = ""
    reuse_refs: list[str] = Field(default_factory=lambda: ["Anticipy-DEV-FINAL/product/multi_intent.py"])

    def actionable(self) -> list[ProactiveCandidateDecision]:
        return [d for d in self.decisions if d.decision in {"ask", "act", "block", "follow_up"}]

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


_PROMPT = """You are Anticipy's proactive decision pipeline.

Read the transcript and output one strict JSON object. Anticipy acts only for the WEARER, the device-owner.

Your job:
1. Identify the wearer speaker label.
2. List every candidate task/fact/open loop mentioned by anyone.
3. For each candidate, decide who owns it, whether it is real, and what Anticipy should do.

Actor rules:
- actor=owner when the wearer personally committed, was assigned, needs a reminder, asks the assistant to help them, or has a standing obligation.
- actor=assistant when the wearer is directly asking Anticipy/the assistant to do something for the wearer.
- actor=listener or third_party when the wearer asks another person to do something ("babe can you grab milk", "Sam can you take the handoff") or asks if they already did it.
- actor=unknown only when ownership is genuinely unclear.

Realness rules:
- real: concrete decided task, obligation, reminder, lookup, draft, cart prep, browser action, money action, follow-up, or durable fact.
- vent: emotional complaint or overwhelm with no real action.
- sarcasm: joking/not meant literally.
- hypothetical or brainstorm: option being floated with no commitment.
- pleasantry: vague social nicety ("we should grab coffee sometime") with no concrete deliverable.
- stale_conditional: only if an unconfirmed condition happens.
- retracted: "never mind", "don't send", "forget it" when it cancels the task.
- already_done: completed in the past.
- status_question: checking whether someone else did something.
- physical_only: a purely physical chore Anticipy cannot digitally help with.
- ambient: context about someone else's need/state with no request to the wearer.
- ambiguous: unclear enough that Anticipy should ask instead of guessing.

Decision rules:
- ignore: not the wearer's/assistant's task, not real, pure vent, sarcasm, brainstorm, pleasantry, status question, already done, retracted, stale conditional, or physical-only without a digital handle.
- remember: stable preference/fact/context about the wearer that should become memory, not a card.
- ask: real owner/assistant task that needs approval, clarification, touches another person, is irreversible-ish, or is voiced inside emotion.
- act: clean reversible task such as reminder, calendar hold, read-only lookup, draft/cart prep, or safe browser research.
- block: money movement, purchase/checkout/payment, legal/medical/financial irreversible action, or anything that must not run without a hard stop.
- follow_up: a real loop that should be checked later because outcome depends on time/another person.

Critical failures:
- False-fire is worse than missing: never convert listener/third-party work into the owner's task.
- But do not drop buried real owner commitments, vague references, accepted delegated tasks, or money actions; money actions must be emitted with decision=block.
- If a real task is inside overwhelm ("my brain is fried, call the dentist"), emit it as ask, not ignore.
- If a line contains several real tasks, emit one decision per task.
- evidence_span must quote the smallest exact transcript span that justifies the decision.

Output ONLY this JSON object:
{
  "wearer": "<speaker label or the wearer>",
  "is_pure_brainstorm": true|false,
  "wearer_has_own_task": true|false,
  "decisions": [
    {
      "speaker": "...",
      "addressee": "...",
      "actor": "owner|assistant|listener|third_party|unknown",
      "realness": "real|vent|sarcasm|hypothetical|brainstorm|pleasantry|stale_conditional|retracted|already_done|status_question|physical_only|ambient|ambiguous",
      "decision": "ignore|remember|ask|act|block|follow_up",
      "task_text": "<short owner-facing wording, blank only for pure ignored noise>",
      "evidence_span": "<exact transcript words>",
      "confidence": 0.0,
      "reason": "<brief technical reason>"
    }
  ]
}
%s
Transcript:
%s
JSON:
"""

# Memory INTO the decider (Phase 2). When the owner path can assemble a ContextPack, we prepend a
# tight "what you already know about the owner" block so the brain decides WITH standing memory —
# it can apply a standing preference, resolve "the usual"/"my dentist"/a first name, and never
# re-ask a fact it already holds. Framed as background truth so a memory line is NEVER re-extracted
# as its own new task. Empty string when there is no relevant memory -> the prompt is byte-identical
# to the memory-blind version (no behavior change on a cold store).
_KNOWN_TEMPLATE = """
What you already know about the owner (durable memory — standing preferences, known people, \
addresses/facts, and the owner's open loops). Use this as BACKGROUND TRUTH about the owner: apply \
their standing preferences to their own tasks, resolve references like "the usual", "my dentist", \
or a bare first name from it, and do NOT ask the owner for a fact that already appears here. This is \
context only — it is NOT a list of new tasks; never emit one of these memory lines as its own decision.
%s
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _norm_conf(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _normalize_decision(raw: dict[str, Any], *, source_truth_case_id: str | None) -> ProactiveCandidateDecision | None:
    if not isinstance(raw, dict):
        return None
    actor = str(raw.get("actor") or "unknown").strip().lower()
    realness = str(raw.get("realness") or "ambiguous").strip().lower()
    decision = str(raw.get("decision") or "ignore").strip().lower()

    actor = actor if actor in {"owner", "assistant", "listener", "third_party", "unknown"} else "unknown"
    realness = realness if realness in {
        "real", "vent", "sarcasm", "hypothetical", "brainstorm", "pleasantry",
        "stale_conditional", "retracted", "already_done", "status_question",
        "physical_only", "ambient", "ambiguous",
    } else "ambiguous"
    decision = decision if decision in {"ignore", "remember", "ask", "act", "block", "follow_up"} else "ignore"

    task_text = str(raw.get("task_text") or raw.get("task") or "").strip()
    evidence = str(raw.get("evidence_span") or raw.get("evidence") or task_text).strip()
    reason = str(raw.get("reason") or "").strip()
    combined = f"{task_text} {evidence}"

    if _PHYSICAL_OR_SOCIAL_NON_TASK.search(combined):
        decision = "ignore"
        realness = "pleasantry" if re.search(r"\bcoffee|lunch|dinner|drinks\b", combined, re.I) else "physical_only"
        if not reason:
            reason = "vague physical/social statement, not a concrete digital deliverable"
    if _HEDGED_LATENT_REPLY.search(combined):
        decision = "ignore"
        realness = "ambiguous"
        if not reason:
            reason = "hedged latent reply with no time, content, or concrete commitment"
    if _SARCASTIC_AVERSION.search(combined):
        decision = "ignore"
        realness = "sarcasm"
        if not reason:
            reason = "sarcastic aversion, not a fresh request to act"

    # Missing-slot -> ask: a first-person plan with a set time but no specific place is the owner's own
    # intent missing one slot (which venue). Ask which spot / offer to pick one — never silently ignore.
    # Overrides a model that mislabels it a listener pleasantry. Guarded to NOT fire on vague-time social
    # mentions (no _CONCRETE_TIME) or plans that already name the place (no _UNSPECIFIED_VENUE).
    if (_MEAL_SOCIAL.search(combined) and _CONCRETE_TIME.search(combined)
            and _UNSPECIFIED_VENUE.search(combined) and _FIRST_PERSON_PLAN.search(combined)
            and not _SARCASTIC_AVERSION.search(combined)):
        actor = "owner"
        realness = "ambiguous"
        decision = "ask"
        reason = "a plan with a set time but no specific place — worth asking which spot (or offering to find one)"
        if not task_text:
            task_text = evidence

    # Deterministic floor around the model: only owner/assistant-owned real or
    # ambiguous items may produce work. Third-party/listener/hypothetical output
    # cannot sneak through as a card even if the model's decision field disagrees.
    if actor not in {"owner", "assistant"} and decision in {"ask", "act", "block", "follow_up"}:
        decision = "ignore"
        if not reason:
            reason = "actor is not the owner or assistant"
    if realness not in {"real", "ambiguous"} and decision in {"ask", "act", "block", "follow_up", "remember"}:
        decision = "ignore"
        if not reason:
            reason = f"not a real owner task: {realness}"
    if realness == "ambiguous" and decision == "act":
        decision = "ask"
        if not reason:
            reason = "ambiguous task requires clarification"

    if not task_text and decision != "ignore":
        task_text = evidence
    if not evidence and not task_text:
        return None

    return ProactiveCandidateDecision(
        speaker=str(raw.get("speaker") or "").strip(),
        addressee=str(raw.get("addressee") or "").strip(),
        actor=actor,  # type: ignore[arg-type]
        realness=realness,  # type: ignore[arg-type]
        decision=decision,  # type: ignore[arg-type]
        task_text=task_text,
        evidence_span=evidence,
        confidence=_norm_conf(raw.get("confidence", 0.0)),
        reason=reason,
        source_truth_case_id=source_truth_case_id,
    )


def _apply_transcript_floors(
    decisions: list[ProactiveCandidateDecision],
    transcript: str,
    *,
    source_truth_case_id: str | None,
) -> list[ProactiveCandidateDecision]:
    text = transcript or ""
    out: list[ProactiveCandidateDecision] = []
    conditional_weather = bool(_CONDITIONAL_WEATHER_CONTEXT.search(text))
    for decision in decisions:
        if conditional_weather and _WEATHER_CHECK.search(f"{decision.task_text} {decision.evidence_span}"):
            decision = decision.model_copy(update={
                "decision": "ignore",
                "realness": "stale_conditional",
                "reason": decision.reason or "weather check only serves an unresolved conditional plan",
            })
        out.append(decision)

    existing_blob = " ".join(d.task_text for d in out).lower()
    for match in _REVIEW_NEED.finditer(text):
        item = re.sub(r"\s+", " ", match.group(1)).strip(" ,*-")
        if not item:
            continue
        words = {w for w in re.findall(r"[a-z0-9]+", item.lower()) if len(w) > 3}
        if words and len(words & set(re.findall(r"[a-z0-9]+", existing_blob))) >= min(2, len(words)):
            continue
        out.append(ProactiveCandidateDecision(
            speaker="",
            addressee="",
            actor="owner",
            realness="real",
            decision="act",
            task_text=f"Review {item}",
            evidence_span=match.group(0).strip(),
            confidence=0.86,
            reason="first-person need-to-review commitment recovered by transcript recall floor",
            source_truth_case_id=source_truth_case_id,
        ))
    return out


async def decide_transcript(
    gateway: ModelGateway,
    transcript: str,
    *,
    source_truth_case_id: str | None = None,
    owner_context: str | None = None,
) -> ProactiveDecisionResult:
    """Run the wearer-aware structured decision pass.

    Returns available=False when the configured model path cannot run. Callers
    should then use existing deterministic/model fallbacks.

    `owner_context` (Phase 2) is a tight, already-budgeted summary of what the
    system knows about the owner (standing preferences, known people/addresses,
    open loops), assembled by live_memory at the call site. When present it is
    prepended to the prompt so the brain decides WITH memory; when None/blank the
    prompt is byte-identical to the memory-blind path.
    """
    text = str(transcript or "").strip()
    if not text:
        return ProactiveDecisionResult(available=True, wearer_has_own_task=False)
    provider = getattr(gateway, "provider", None)
    if provider not in {PROVIDER_OPENROUTER, PROVIDER_GEMINI}:
        return ProactiveDecisionResult(available=False, error="model_provider_not_available")

    model = (os.environ.get("ANTICIPY_PROACTIVE_DECISION_MODEL") or DEFAULT_DECISION_MODEL).strip()
    decision_gateway = gateway
    if model and model not in {getattr(gateway, "cheap_model", ""), getattr(gateway, "smart_model", "")}:
        decision_gateway = ModelGateway(
            provider=provider,
            cheap_model=model,
            smart_model=model,
            timeout=float(os.environ.get("ANTICIPY_PROACTIVE_DECISION_TIMEOUT", "60")),
        )

    # Respect the decide budget: the memory summary is already ~<=1600 chars from the
    # context builder; cap defensively so a runaway pack can never crowd out the transcript.
    known_block = ""
    ctx = (owner_context or "").strip()
    if ctx:
        known_block = _KNOWN_TEMPLATE % ctx[:1600]

    try:
        raw = await decision_gateway.think(
            _PROMPT % (known_block, text[:7000]),
            tier=SMART,
            caller="gate",
            json_mode=True,
            temperature=0,
            max_tokens=int(os.environ.get("ANTICIPY_PROACTIVE_DECISION_MAX_TOKENS", "2200")),
        )
    except Exception as exc:
        return ProactiveDecisionResult(available=False, error=str(exc)[:240])

    data = _extract_json_object(raw)
    if not data:
        return ProactiveDecisionResult(available=False, raw_response=(raw or "")[:2000], error="unparseable_json")

    decisions: list[ProactiveCandidateDecision] = []
    for item in (data.get("decisions") or data.get("tasks") or [])[:60]:
        decision = _normalize_decision(item, source_truth_case_id=source_truth_case_id)
        if decision is not None:
            decisions.append(decision)
    decisions = _apply_transcript_floors(
        decisions,
        text,
        source_truth_case_id=source_truth_case_id,
    )

    is_brainstorm = bool(data.get("is_pure_brainstorm", False))
    # A deterministically-promoted owner/assistant task (the missing-slot guard, the review-need floor,
    # or any decision the floors in _normalize_decision graduated to ask/act/block/follow_up) IS the
    # wearer owning a task — the model's wearer_has_own_task=False must not veto it back to ignore.
    has_owner_actionable = any(
        d.actor in {"owner", "assistant"} and d.decision in {"ask", "act", "block", "follow_up"}
        for d in decisions
    )
    wearer_has_own_task = bool(
        data.get("wearer_has_own_task", any(d.decision != "ignore" for d in decisions))
    ) or has_owner_actionable
    if is_brainstorm or not wearer_has_own_task:
        decisions = [
            d.model_copy(update={
                "decision": "ignore",
                "reason": d.reason or ("pure brainstorm" if is_brainstorm else "wearer owns no task"),
            })
            for d in decisions
        ]

    return ProactiveDecisionResult(
        available=True,
        wearer=str(data.get("wearer") or "the wearer").strip() or "the wearer",
        is_pure_brainstorm=is_brainstorm,
        wearer_has_own_task=wearer_has_own_task,
        decisions=decisions,
        raw_response=(raw or "")[:4000],
    )


async def decide_line(gateway: ModelGateway, line: str) -> str:
    """Room-1.5 adapter (FIX-01 step 2d, 2026-07-02): one line -> "ACT" | "ASK" | "SILENT" | "UNAVAILABLE".

    Maps this pipeline's transcript decision onto the Decider's verdict vocabulary so the
    spine's commitment judge can (eventually) share the ONE extractor brain. One-way-safe
    by construction: block/follow_up/ask -> ASK (never ACT), ignore/remember/empty -> SILENT,
    and only an owner/assistant actionable "act" -> ACT. available=False -> UNAVAILABLE
    (no judgment happened; the caller's defer/retry machinery owns it).

    NOT the default brain yet: the legacy Decider prompt encodes years of single-line
    narration-vs-handoff distinctions that were tuned against a live probe bank which no
    longer exists in-repo. Until a replacement probe bank validates this adapter on that
    distribution, it runs only behind ANTICIPY_DECIDER_BRAIN=pipeline.
    """
    text = str(line or "").strip()
    if not text:
        return "SILENT"
    try:
        result = await decide_transcript(gateway, text)
    except Exception:
        return "UNAVAILABLE"
    if not getattr(result, "available", False):
        return "UNAVAILABLE"
    verdicts = []
    for d in result.decisions or []:
        actor = getattr(d, "actor", "") or ""
        decision = getattr(d, "decision", "") or ""
        if actor not in {"owner", "assistant"}:
            continue
        if decision == "act":
            verdicts.append("ACT")
        elif decision in {"ask", "block", "follow_up"}:
            verdicts.append("ASK")
    if not verdicts:
        return "SILENT"
    # Safest verdict wins when candidates disagree (mirrors decider.parse_verdict's order).
    return "ASK" if "ASK" in verdicts else "ACT"
