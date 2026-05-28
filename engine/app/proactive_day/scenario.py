"""The scripted ordinary day. FIXED here, anti-gaming:

- the category set, minimum counts and difficulty FLOORS are
  constants in this file, not tunable at run time;
- every label (expected outcome) is written at scenario-build time
  from the script, never judged after the fact by any model;
- self_check FAILS the build if the realized day is softer than the
  spec (too few distractors, references not vague enough, loud tier
  not loud enough), so an accidentally easy day cannot inflate a
  pass.

Expected outcomes (the label vocabulary):
  ACTION    a real action that must resolve + proceed (true-pass)
  CONFIRM   a load-bearing reference/slot is uncertain -> ask once
  LIFE_LOG  chatter / about-someone-else -> recorded, never actioned
  DEFER     real action, time-conditioned -> scheduled, not now
  KILL      a pending action already satisfied by other means
  CANCEL    a live queued action retracted by an ambient cancel
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

PLACES = ["home", "car", "restaurant", "office"]


@dataclass(frozen=True)
class CatSpec:
    name: str
    min_count: int
    label: str
    note: str = ""


CATEGORY_SPEC: list[CatSpec] = [
    CatSpec("VERBAL_PROMISE", 12, "ACTION",
            "wearer says I'll send/book/get-back; resolve + queue"),
    CatSpec("INSTRUCTION_TO_WEARER", 12, "ACTION",
            "someone tells the wearer to do something"),
    CatSpec("VAGUE_VARIABLE", 12, "ACTION",
            "unresolved refs it/them/that/the-usual; resolve or CONFIRM"),
    CatSpec("WHEN_DEFERRED", 8, "DEFER",
            "real but time-conditioned; schedule, never now, never drop"),
    CatSpec("ALREADY_DONE", 8, "KILL",
            "world shows task done by other means; kill pending (HARD)"),
    CatSpec("AMBIENT_CANCEL", 8, "CANCEL",
            "queued action retracted by ambient cancel (HARD)"),
    CatSpec("SURFACING_JUDGMENT", 10, "ACTION",
            "mixed urgency + reachability; right channel/timing, no flood"),
    CatSpec("CHATTER", 20, "LIFE_LOG",
            "sounds actionable but storytelling/hypothetical/3rd-party"),
    CatSpec("PERSONAL_SHORTHAND", 8, "CONFIRM",
            "wearer shorthand; first CONFIRM, later resolve from memory"),
    CatSpec("LOUD_RESTAURANT", 10, "ACTION",
            "promise/vague at loud-restaurant SNR tier, end to end"),
]
SPEC_BY_NAME = {c.name: c for c in CATEGORY_SPEC}

_NAMES = ["Dana", "Priya", "Sean", "Marcus", "the contractor"]
_THINGS = ["the Q3 deck", "the signed contract", "the budget"]
_WHENS = ["when you get a chance", "after the meeting", "tonight",
          "once the build is ready", "after standup"]

_PROMISE = [
    "I'll send {name} {thing}",
    "let me check and get back to {name}",
    "I'll book the table for dinner",
    "I'll forward {thing} to {name}",
]
_INSTRUCT = [
    "can you send {name} {thing} today",
    "please put the review on the calendar",
    "email {name} about the schedule change",
    "reply to {name} that it works",
]
_VAGUE = [
    "send it to them when you can",
    "move that to Thursday",
    "forward the usual to {name}",
    "tell them I'll be late",
]
_DEFER = [
    "send {thing} to {name} {when}",
    "book the table {when}",
    "remind {name} {when}",
]
_CHATTER = [
    "remember when we almost sent the whole deck to the wrong client",
    "if I were you I'd just cancel the meeting and rebook",
    "Sean said he might email Dana about it later",
    "we should probably get someone to handle Q3 someday",
    "my friend booked a table at that place once, it was great",
    "imagine if we wired the whole budget by accident",
]
_SHORTHAND = [
    "handle the Thursday thing",
    "do my usual for {name}",
    "set up the regular sync",
]


def _fill(t: str, rng: random.Random) -> tuple[str, dict]:
    s, slots = t, {}
    if "{name}" in s:
        slots["name"] = rng.choice(_NAMES); s = s.replace("{name}", slots["name"])
    if "{thing}" in s:
        slots["thing"] = rng.choice(_THINGS); s = s.replace("{thing}", slots["thing"])
    if "{when}" in s:
        slots["when"] = rng.choice(_WHENS); s = s.replace("{when}", slots["when"])
    return s, slots


@dataclass
class DayEvent:
    ev_id: str
    category: str
    label: str                 # mix-time truth
    ts: float                  # sim clock (hours)
    place: str
    speaker: str               # WEARER | other
    text: str = ""
    slots: dict = field(default_factory=dict)
    snr_tier: str = "clean"    # clean | loud
    reach: str = "free"        # free | mid_conversation | do_not_interrupt
    urgency: str = "hours"     # seconds | minutes | hours | never
    # world hooks (applied by the harness at the right sim time):
    world_done_at: Optional[float] = None      # ALREADY_DONE: world satisfies it
    world_done: Optional[dict] = None
    cancels_ev: Optional[str] = None           # AMBIENT_CANCEL: which ev it kills
    defer_until: Optional[str] = None          # WHEN_DEFERRED condition
    shorthand_key: Optional[str] = None        # PERSONAL_SHORTHAND learn key
    expansion: Optional[str] = None            # the concrete meaning learned
    first_occurrence: bool = False


def assemble(scale: float = 1.0, seed: int = 20260516) -> dict:
    rng = random.Random(seed)
    events: list[DayEvent] = []
    t = 8.0  # day starts 08:00
    for spec in CATEGORY_SPEC:
        n = max(3, int(round(spec.min_count * scale)))
        for i in range(n):
            t += rng.uniform(0.05, 0.30)
            place = rng.choice(PLACES)
            eid = f"{spec.name}-{i:03d}"
            ev = DayEvent(ev_id=eid, category=spec.name, label=spec.label,
                          ts=round(t, 3), place=place, speaker="WEARER")
            if spec.name == "VERBAL_PROMISE":
                txt, sl = _fill(rng.choice(_PROMISE), rng)
                ev.text, ev.slots = txt, sl
            elif spec.name == "INSTRUCTION_TO_WEARER":
                txt, sl = _fill(rng.choice(_INSTRUCT), rng)
                ev.text, ev.slots, ev.speaker = txt, sl, "S1"
            elif spec.name == "VAGUE_VARIABLE":
                txt, sl = _fill(rng.choice(_VAGUE), rng)
                ev.text, ev.slots = txt, sl
            elif spec.name == "WHEN_DEFERRED":
                txt, sl = _fill(rng.choice(_DEFER), rng)
                ev.text, ev.slots = txt, sl
                ev.defer_until = sl.get("when", "later")
            elif spec.name == "ALREADY_DONE":
                nm = rng.choice(_NAMES); th = rng.choice(_THINGS)
                ev.text = f"I'll send {nm} {th}"
                ev.slots = {"name": nm, "thing": th}
                ev.world_done_at = round(t + rng.uniform(0.2, 0.6), 3)
                ev.world_done = {"kind": "email_sent", "to": nm.lower(),
                                 "subject": th.lower()}
            elif spec.name == "AMBIENT_CANCEL":
                nm = rng.choice(_NAMES); th = rng.choice(_THINGS)
                ev.text = f"I'll send {nm} {th}"
                ev.slots = {"name": nm, "thing": th}
                ev.label = "ACTION"   # a real promise that must be RETRACTED
                cev = DayEvent(
                    ev_id=f"{eid}-cancel", category=spec.name,
                    label="CANCEL", ts=round(t + rng.uniform(0.15, 0.45), 3),
                    place=place, speaker="WEARER",
                    text="actually never mind, do that Monday instead",
                    cancels_ev=eid)
                events.append(ev)
                events.append(cev)
                continue
            elif spec.name == "SURFACING_JUDGMENT":
                nm = rng.choice(_NAMES)
                ev.text = f"flag {nm} that the numbers moved"
                ev.slots = {"name": nm}
                ev.urgency = rng.choice(["seconds", "minutes", "hours",
                                         "never"])
                ev.reach = rng.choice(["free", "mid_conversation",
                                       "do_not_interrupt"])
            elif spec.name == "CHATTER":
                ev.text = rng.choice(_CHATTER)
                ev.speaker = rng.choice(["WEARER", "S1", "S2"])
            elif spec.name == "PERSONAL_SHORTHAND":
                # ONE fixed wearer shorthand repeated through the day:
                # the FIRST occurrence is ambiguous (no learned
                # mapping) -> CONFIRM, and the wearer's reply teaches
                # the expansion; every LATER occurrence of the SAME
                # shorthand must resolve from learned memory WITHOUT
                # asking again.
                ev.text = "handle the thursday thing"
                ev.shorthand_key = "the_thursday_thing"
                ev.expansion = "send Dana the budget before the Thursday review"
                ev.first_occurrence = (i == 0)
                ev.label = "CONFIRM" if i == 0 else "ACTION"
            elif spec.name == "LOUD_RESTAURANT":
                base = rng.choice(_PROMISE + _VAGUE)
                txt, sl = _fill(base, rng)
                ev.text, ev.slots = txt, sl
                ev.snr_tier, ev.place = "loud", "restaurant"
            events.append(ev)

    events.sort(key=lambda e: e.ts)
    manifest = {
        "seed": seed, "scale": scale, "n": len(events),
        "spec": {c.name: vars(c) for c in CATEGORY_SPEC},
        "events": [vars(e) for e in events],
    }
    return manifest


def self_check(manifest: dict) -> tuple[bool, list[str]]:
    """FAIL if the realized day is softer than spec."""
    rep: list[str] = []
    ok = True
    evs = manifest["events"]
    by = {}
    for e in evs:
        by.setdefault(e["category"], []).append(e)

    for spec in CATEGORY_SPEC:
        got = by.get(spec.name, [])
        need = max(3, int(round(spec.min_count * manifest["scale"])))
        eff = len([e for e in got if e["label"] != "CANCEL"])
        if eff < need:
            ok = False
            rep.append(f"{spec.name}: {eff} < required {need}")
        else:
            rep.append(f"{spec.name}: n={len(got)} ok")

    # distractor density: CHATTER must be a real share of the day
    chat = len(by.get("CHATTER", []))
    frac = chat / max(1, len(evs))
    if frac < 0.15:
        ok = False
        rep.append(f"distractor density {frac:.2f} < 0.15 (too easy)")
    else:
        rep.append(f"distractor density {frac:.2f} ok")

    # reference vagueness: VAGUE_VARIABLE must actually be vague
    vague = by.get("VAGUE_VARIABLE", [])
    vg = sum(1 for e in vague
             if any(w in e["text"].lower()
                    for w in ("it", "them", "that", "the usual")))
    if vague and vg < int(0.9 * len(vague)):
        ok = False
        rep.append(f"vague refs only {vg}/{len(vague)} (too explicit)")
    else:
        rep.append(f"vague refs {vg}/{len(vague)} ok")

    # loud tier present and marked
    loud = by.get("LOUD_RESTAURANT", [])
    if loud and not all(e["snr_tier"] == "loud" for e in loud):
        ok = False
        rep.append("LOUD_RESTAURANT not all loud-tier")
    else:
        rep.append(f"loud tier n={len(loud)} ok")

    # safety-critical pairs present
    if not by.get("ALREADY_DONE"):
        ok = False; rep.append("ALREADY_DONE missing")
    if not [e for e in by.get("AMBIENT_CANCEL", []) if e["label"] == "CANCEL"]:
        ok = False; rep.append("AMBIENT_CANCEL cancel events missing")
    return ok, rep
