"""Track A — the FRESH-REQUEST generator (a new, never-seen calendar-hold ask each lap).

LAW #8: fresh task every lap. This composes a natural-language scheduling request from randomized
slots (purpose x relative-day x time x duration x phrasing) — thousands of distinct combinations, so
no lap can be memorized and nothing downstream can be tuned to one task. It emits ONLY natural
language (what a person would say); the worker must parse it itself. It carries NO answer, NO event
id, NO structured fields the worker could shortcut on.
"""
from __future__ import annotations

import random

# general, everyday holds — none special-cased downstream
_PURPOSES = [
    "deep work", "focus time", "a workout", "a dentist appointment", "a budget review",
    "lunch with a friend", "a haircut", "a 1:1 with Alex", "planning the week", "a coffee chat",
    "reading time", "a doctor's checkup", "a project sync", "a walk", "meal prep",
    "a call with the accountant", "studying", "a quick standup", "a design review", "errands",
]
_DAYS = ["tomorrow", "the day after tomorrow", "this Friday", "next Monday", "next Tuesday",
         "this Saturday", "next Thursday", "in three days", "this Wednesday", "next weekend"]
_TIMES = ["8am", "9:30am", "10am", "11am", "1pm", "2:30pm", "3pm", "4pm", "5:30pm", "6pm", "noon"]
_DURATIONS = ["30 minutes", "45 minutes", "an hour", "half an hour", "90 minutes"]
_TEMPLATES = [
    "Hold {dur} {day} at {time} for {purpose}.",
    "Block {time} {day} for {purpose}.",
    "Put {purpose} on my calendar {day} at {time}.",
    "Schedule {purpose} {day} at {time}, about {dur}.",
    "Can you set aside {dur} {day} at {time} for {purpose}?",
    "Pencil in {purpose} {day} {time}.",
]


def fresh_request(rng: random.Random) -> dict:
    """Return one fresh ask: {ask, kind}. `ask` is plain language; nothing else leaks."""
    purpose = rng.choice(_PURPOSES)
    day = rng.choice(_DAYS)
    time = rng.choice(_TIMES)
    dur = rng.choice(_DURATIONS)
    ask = rng.choice(_TEMPLATES).format(dur=dur, day=day, time=time, purpose=purpose)
    return {"ask": ask, "kind": "calendar_hold"}


if __name__ == "__main__":  # eyeball the variety
    r = random.Random(1)
    for _ in range(8):
        print("  ", fresh_request(r)["ask"])
