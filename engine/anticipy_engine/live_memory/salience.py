"""SALIENCE — the cheap, local hot-path gate deciding what becomes DURABLE memory
versus what lives briefly in a rolling RAW BUFFER that auto-expires (M4).

An always-listening device hears hours of transcript a day, >99% of it worthless. We must
NOT store/embed everything: cost and recall both die if we do. Nothing kept is ever silently
lost — every kept line still lands somewhere — but only *salient* lines become durable memory;
low-signal episodic chatter goes to the raw buffer with a short validity window and expires via
the same M3 bi-temporal filter (is_valid_at) unless something reinforces it.

Commitments (open_loops) and stated facts (profile) already survived classify(), so they are
salient by construction — this gate ONLY grades episodic `history` lines. Deterministic + free;
the live-model seam (M6) can replace `score()` without changing the tiering contract.
"""
from __future__ import annotations

import re

# a low-salience episodic line lives this long in the raw buffer, then expires.
RAW_BUFFER_HOURS = 12.0
# episodic history at/above this score is worth keeping durably; below it → raw buffer.
DURABLE_THRESHOLD = 0.5

_NUM = re.compile(r"\d")                       # a code, date, amount, address — worth keeping
_DATE = re.compile(
    r"\b(today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"next week|this week|this weekend|\d{1,2}(:\d\d)?\s*(am|pm)|noon|anniversary|birthday)\b",
    re.I)
_FACTISH = re.compile(
    r"\b(is|are|was|were|has|have|lives?|works?|named|called|located|code|number|address|"
    r"password|allergic|prefers?|always|usually|every)\b", re.I)
# durable REFERENCE facts — a thing you will need to look up later (a code/key/login/where a
# thing is kept). These are worth keeping even when short, so they don't wash out in the buffer.
_REFERENCE = re.compile(
    r"\b(code|key|password|passcode|pin|wifi|login|combination|account|policy|serial|"
    r"under the|behind the|in the (?:drawer|closet|garage|cabinet|glovebox))\b", re.I)
# pure narration / observation with no durable content — the firehose we don't keep.
_OBSERVATION = re.compile(
    r"\b(weather|nice|tired|hungry|bored|walk|coffee|lunch|dinner|traffic|whatever|anyway|"
    r"honestly|kinda|sorta|i guess|i feel|feeling|so annoying|ugh|meh)\b", re.I)


def score(text: str, kind: str, people: list | None = None) -> float:
    """0..1 salience for a kept line. open_loop/profile are salient by construction (1.0);
    episodic history is graded on durable-signal features (names, numbers/dates, factual
    statements) minus pure-observation noise. Deterministic; no model call."""
    if kind in ("open_loop", "profile_fact"):
        return 1.0
    t = (text or "").strip()
    if not t:
        return 0.0
    s = 0.0
    if people:
        s += 0.35                                  # references a real person
    if _NUM.search(t):
        s += 0.4                                   # a code/amount/address/date digit
    if _DATE.search(t):
        s += 0.25
    if _FACTISH.search(t):
        s += 0.3                                   # a durable-shaped statement
    if _REFERENCE.search(t):
        s += 0.5                                   # a look-it-up-later reference fact
    words = t.split()
    if len(words) >= 12:
        s += 0.1                                   # a longer, content-bearing line
    if _OBSERVATION.search(t):
        s -= 0.45                                  # pure narration/observation → firehose
    return max(0.0, min(1.0, s))


def is_durable(text: str, kind: str, people: list | None = None) -> bool:
    return score(text, kind, people) >= DURABLE_THRESHOLD
