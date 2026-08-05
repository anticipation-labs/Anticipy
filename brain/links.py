"""A conversation is a connected component, not a span of time.

Every version of this system so far asked "has enough silence passed that the
conversation is over?" — and Jones & Klinkner (CIKM 2008) swept that question
across every possible timeout length on hand-labelled data and found it caps
out at 70% precision. Not "45s is wrong": no number exists. They also measured
17% of tasks interleaved and 20% nested, which is the owner's "two people back
to back" and his "a quadrillion other scenarios".

So this module never asks it. Each line answers one question instead —

    which earlier line, if any, am I a continuation of?

— and a conversation is whatever falls out. Same shape as JWZ email threading
(1997, in every mail client: In-Reply-To edges, thread = connected component),
Kummerfeld et al. ACL 2019 for chat, and the EMNLP 2020 pointer-network model
for the streaming case.

A line that starts something new points at ITSELF. That convention is from the
zero-shot disentanglement work and it matters: there is no null, no "is this
new?" side-channel, and no special case. One question, always one answer.

WHAT THIS BUYS, structurally rather than by tuning:

  * There is no clock in this file. Not a threshold, not a gap, not a
    timestamp comparison anywhere in the grouping. Silence CANNOT split a
    conversation because silence is not an input.
  * Adding a line can only ever MERGE components, never split one. That is
    the owner's ruling ("better it overreacts than underreacts") as an
    algebraic property of union-find, not a knob someone can turn the wrong
    way later.
  * Late audio is not a special case. A turn that arrives hours after it was
    spoken just contributes its edge. Nothing is re-cut, so `dirty`,
    settle-timers and supersedes-pointers have nothing to do.
  * Arrival order cannot change the answer, because components are a set.
    Omi shipped exactly this bug (their #6551: backlog syncs in chunks and
    each chunk becomes its own conversation) and fixed it by serialising
    their writes. Here it cannot happen: there is no order to get wrong.

THE HONESTY WALL. A missing parent, an unknown id, a pointer into the future
and a cycle all resolve to "this line starts its own conversation" — which is
precisely what the system did before links existed. A model that answers
nothing, or answers garbage, can never do worse than today.
"""
from __future__ import annotations

from typing import Iterable, Optional

# A line may only ever point BACKWARD. Anything else is dropped rather than
# trusted: a forward pointer is either a garbled model or a clock that lied,
# and neither is a reason to invent structure.
__all__ = ["resolve_parents", "conversations", "conversation_of", "Line"]

Line = dict          # {"id": str, "parent": str|None, "spoken_at": float|None}


def _key(line: Line) -> str:
    return str(line.get("id") or "")


def _spoken(line: Line) -> Optional[float]:
    """Capture time if we have it. Used ONLY to reject impossible edges — a
    line cannot continue something that had not been said yet — never to
    decide whether two lines belong together. Absent stamps disable the
    check rather than guessing, because older app builds wrote none."""
    for field in ("spoken_at", "capture_started_at"):
        v = line.get(field)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def resolve_parents(lines: Iterable[Line]) -> dict[str, str]:
    """Map each line id to the id it actually continues, after refusing every
    edge we cannot justify. A line that continues nothing maps to itself.

    The returned map is guaranteed ACYCLIC — following parents from any line
    reaches a self-linked root in finite steps. That guarantee is the contract
    callers rely on to walk reply structure (rendering a thread, finding the
    line a conversation started from) without a visited-set of their own.

    Rejected edges, each falling back to self:
      * no parent given at all
      * a parent id we have never seen
      * a parent that is the line itself (already self — kept, it IS the
        "new conversation" answer)
      * a parent spoken AFTER this line, where both stamps exist
      * any edge that would close a loop (JWZ's rule)
    """
    rows = [ln for ln in lines if _key(ln)]
    known = {_key(ln): ln for ln in rows}
    parent: dict[str, str] = {}

    for ln in rows:
        me = _key(ln)
        claimed = ln.get("parent")
        claimed = str(claimed) if claimed not in (None, "") else me

        if claimed not in known:
            parent[me] = me                     # unknown id -> stands alone
            continue

        mine, theirs = _spoken(ln), _spoken(known[claimed])
        if mine is not None and theirs is not None and theirs > mine:
            parent[me] = me                     # cannot continue the future
            continue

        parent[me] = claimed

    return _break_cycles(parent)


def _break_cycles(parent: dict[str, str]) -> dict[str, str]:
    """JWZ's rule: if following parents from a line leads back to that line,
    the edge that closed the loop is dropped and its owner becomes a root.

    Note on why this is applied inside resolve_parents rather than only before
    grouping: for GROUPING it is genuinely unnecessary — union-find merges a
    cycle's members into one component whether or not the loop is cut, so a
    version of this function that did nothing at all would pass every
    conversation test. It was dead code the first time it was written, which
    is the same shape of mistake as a ceiling with no callers: it reads as
    protection in review and provides none. It earns its place by making
    resolve_parents' output acyclic, which is a contract callers can walk.
    test_LAW_walking_parents_always_terminates is what holds it honest."""
    fixed = dict(parent)
    for start in list(fixed):
        seen = {start}
        node = fixed[start]
        while node != fixed[node]:              # not yet at a root
            if node in seen:
                fixed[node] = node              # cut the loop here
                break
            seen.add(node)
            node = fixed[node]
    return fixed


def conversations(lines: Iterable[Line]) -> list[list[str]]:
    """Group line ids into conversations.

    Returns a list of id-lists. Both the groups and the ids inside them are
    ordered deterministically — by capture time where known, then by id — so
    the same input always renders identically, and so a caller can diff two
    runs meaningfully. Deterministic ordering is presentation only; membership
    never depends on it.
    """
    rows = [ln for ln in lines if _key(ln)]
    if not rows:
        return []

    parent = _break_cycles(resolve_parents(rows))

    # Union-find. Path-compressed, so a long chain of "and then he said" costs
    # nothing on the second read.
    up: dict[str, str] = {i: i for i in parent}

    def find(x: str) -> str:
        root = x
        while up[root] != root:
            root = up[root]
        while up[x] != root:
            up[x], x = root, up[x]
        return root

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            up[rb] = ra

    for child, par in parent.items():
        if child != par:
            union(par, child)

    order = {_key(ln): i for i, ln in enumerate(rows)}
    stamp = {_key(ln): _spoken(ln) for ln in rows}

    def sort_key(i: str):
        s = stamp.get(i)
        # Unstamped lines sort after stamped ones rather than before: an
        # absent stamp is unknown, and unknown must never be mistaken for
        # "earliest" and drag a group's start time backwards.
        return (0, s, order[i]) if s is not None else (1, 0.0, order[i])

    groups: dict[str, list[str]] = {}
    for i in parent:
        groups.setdefault(find(i), []).append(i)

    out = [sorted(g, key=sort_key) for g in groups.values()]
    out.sort(key=lambda g: sort_key(g[0]))
    return out


def conversation_of(line_id: str, lines: Iterable[Line]) -> list[str]:
    """The conversation containing one line, or [] if it is not among them."""
    for group in conversations(lines):
        if line_id in group:
            return group
    return []
