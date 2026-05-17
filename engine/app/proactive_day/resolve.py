"""Layer A: the resolution engine, the cap on everything.

A real utterance is full of unresolved variables: "send IT to THEM
when you get a chance", "move THAT to Thursday", "the usual". This
resolves each load-bearing reference against the wearer's life (the
day's conversation memory, contacts, calendar, files) and returns a
typed action with a per-reference confidence.

HARD rule (the safe asymmetric direction): an action proceeds only
if EVERY load-bearing reference resolves above threshold. If any is
ambiguous or absent it routes to CONFIRM with a one-line question
naming the unresolved reference. Over-action is the disaster; an
unresolved reference is NEVER guessed. Deterministic and honest:
recency + account match, not an LLM hallucinating a referent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.proactive_day.world import SimWorld

RESOLVE_BAR = 0.70

_PRONOUN_OBJ = re.compile(r"\b(it|that|this|those|these)\b", re.I)
_PRONOUN_PER = re.compile(r"\b(them|him|her|they)\b", re.I)
_USUAL = re.compile(r"\b(the usual|my usual|the regular|the same as)\b", re.I)
_VERBS = ("send", "forward", "email", "book", "wire", "remind", "reply",
          "move", "schedule", "tell", "flag", "set", "put", "handle", "do")
_TIME_REF = re.compile(
    r"\b(when you get a chance|after the meeting|after standup|tonight|"
    r"later|once .* ready|thursday|monday|tomorrow|next week)\b", re.I)


@dataclass
class Ref:
    kind: str          # object | person | usual
    surface: str       # the words in the utterance
    value: Optional[str]
    confidence: float


@dataclass
class ResolvedAction:
    kind: str                       # send_email | calendar | reply | generic
    verb: str
    object: Optional[str]
    target: Optional[str]
    refs: list = field(default_factory=list)     # [Ref]
    time_ref: Optional[str] = None
    all_confident: bool = False
    unresolved: Optional[str] = None  # the ref to ask about, if any


def _recent_things(world: SimWorld) -> list[str]:
    """Concrete objects recently mentioned in the day, newest first."""
    out: list[str] = []
    for turn in reversed(world.conversation):
        for f in world.files:
            if f in turn["text"].lower() and f not in out:
                out.append(f)
    return out


def _recent_people(world: SimWorld) -> list[str]:
    out: list[str] = []
    for turn in reversed(world.conversation):
        low = turn["text"].lower()
        for name in world.contacts:
            if name in low and name not in out:
                out.append(name)
    return out


def _verb_of(text: str) -> Optional[str]:
    w = re.findall(r"[a-z']+", text.lower())
    for tok in w[:3]:
        if tok in _VERBS:
            return tok
    for tok in w:
        if tok in _VERBS:
            return tok
    return None


def resolve(text: str, world: SimWorld,
            named_thing: Optional[str] = None,
            named_person: Optional[str] = None) -> ResolvedAction:
    """Resolve the load-bearing references in `text` against the
    world. named_thing/named_person are the frozen reasoning engine's
    extracted slots when present (read-only inputs); recency fills
    the gaps. Ambiguity or absence -> low confidence -> CONFIRM.
    """
    low = text.lower()
    verb = _verb_of(text)
    refs: list[Ref] = []

    # object reference
    obj_val, obj_conf, obj_surface = None, 1.0, ""
    explicit_thing = named_thing
    if not explicit_thing:
        for f in world.files:
            if f in low:
                explicit_thing = f
                break
    if explicit_thing:
        obj_val, obj_conf, obj_surface = explicit_thing, 0.95, explicit_thing
    elif _USUAL.search(low):
        key = "usual"
        learned = world.facts.get(key)
        obj_val = learned
        obj_conf = 0.9 if learned else 0.2     # unknown shorthand -> ask
        obj_surface = _USUAL.search(low).group(0)
    elif _PRONOUN_OBJ.search(low):
        cands = _recent_things(world)
        obj_surface = _PRONOUN_OBJ.search(low).group(0)
        if len(cands) == 1:
            obj_val, obj_conf = cands[0], 0.85
        elif len(cands) > 1:
            obj_val, obj_conf = cands[0], 0.45   # ambiguous -> ask
        else:
            obj_val, obj_conf = None, 0.2
    if obj_surface:
        refs.append(Ref("object", obj_surface, obj_val, round(obj_conf, 3)))

    # person reference
    per_val, per_conf, per_surface = None, 1.0, ""
    explicit_person = named_person
    if not explicit_person:
        for nm in world.contacts:
            if nm in low:
                explicit_person = nm
                break
    if explicit_person:
        per_val, per_conf, per_surface = explicit_person, 0.95, explicit_person
    elif _PRONOUN_PER.search(low):
        cands = _recent_people(world)
        per_surface = _PRONOUN_PER.search(low).group(0)
        if len(cands) == 1:
            per_val, per_conf = cands[0], 0.85
        elif len(cands) > 1:
            per_val, per_conf = cands[0], 0.45   # ambiguous -> ask
        else:
            per_val, per_conf = None, 0.2
    if per_surface:
        refs.append(Ref("person", per_surface, per_val, round(per_conf, 3)))

    tref = None
    m = _TIME_REF.search(low)
    if m:
        tref = m.group(0)

    kind = "generic"
    if verb in ("send", "forward", "email", "reply"):
        kind = "send_email"
    elif verb in ("book", "schedule", "move", "put"):
        kind = "calendar"

    # the safe asymmetric rule: every load-bearing ref must clear the
    # bar; otherwise name the weakest and CONFIRM.
    weak = None
    weak_c = 1.0
    for r in refs:
        if r.confidence < weak_c:
            weak_c, weak = r.confidence, r
    all_conf = bool(refs) and weak_c >= RESOLVE_BAR and verb is not None
    return ResolvedAction(
        kind=kind, verb=verb or "", object=obj_val, target=per_val,
        refs=refs, time_ref=tref, all_confident=all_conf,
        unresolved=(None if all_conf else
                    (weak.surface if weak else
                     ("the action" if verb is None else "the reference"))))
