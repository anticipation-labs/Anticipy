"""The laws a link graph must obey, written as tests that can actually fail.

Omar's objection to scenario lists is the reason this file is laws and not
examples: "There's a million and one different scenarios. Just because I name
it doesn't mean that that's it." So these are quantified over inputs — most of
them run against thousands of randomly generated link structures — rather than
over the handful of situations anyone thought to write down.

Several of them are true BY CONSTRUCTION under links and were merely hoped for
under a timer. Those are marked. That difference is the whole argument for the
change: they stop being properties we defend and become properties we have.
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.links import conversations, conversation_of, resolve_parents  # noqa: E402


def L(i, parent=None, at=None):
    return {"id": i, "parent": parent, "spoken_at": at}


def groups(lines):
    """Comparable form: a set of frozensets. Membership, not presentation."""
    return {frozenset(g) for g in conversations(lines)}


# ---------------------------------------------------------------- the shape

def test_a_chain_is_one_conversation():
    """Omar's phone call. Six lines, each continuing the last, 20-25s apart —
    the exact shape that the timer cut into three."""
    lines = [
        L("a", "a", 0),          # self-link: this starts it
        L("b", "a", 20),
        L("c", "b", 45),
        L("d", "c", 70),
        L("e", "d", 95),
        L("f", "e", 120),
    ]
    assert groups(lines) == {frozenset("abcdef")}


def test_two_people_back_to_back_with_no_gap_at_all():
    """The case a clock can never get right: he turns from one person to
    another with zero pause. There is no silence to detect, and links do not
    need any."""
    lines = [
        L("a", "a", 0), L("b", "a", 3), L("c", "b", 6),
        L("x", "x", 7), L("y", "x", 10), L("z", "y", 13),
    ]
    assert groups(lines) == {frozenset("abc"), frozenset("xyz")}


def test_a_three_hour_pause_does_not_end_anything():
    """The inverse case, equally impossible for a clock."""
    lines = [L("a", "a", 0), L("b", "a", 10_800)]
    assert groups(lines) == {frozenset("ab")}


def test_every_line_lands_in_exactly_one_conversation():
    lines = [L("a", "a", 0), L("b", "a", 1), L("c", "c", 2), L("d", None, 3)]
    seen = [i for g in conversations(lines) for i in g]
    assert sorted(seen) == ["a", "b", "c", "d"]
    assert len(seen) == len(set(seen))


# ------------------------------------------------------- the honesty wall

def test_no_links_at_all_is_exactly_todays_behaviour():
    """If the model never answers, every line stands alone — which is what the
    feed does today. The wall is that a silent model cannot make her worse."""
    lines = [L(i, None, n) for n, i in enumerate("abcdef")]
    assert groups(lines) == {frozenset(i) for i in "abcdef"}


def test_an_unknown_parent_id_stands_alone():
    """A hallucinated id must not invent a conversation, and must not crash."""
    lines = [L("a", "a", 0), L("b", "ZZZ-not-a-line", 5)]
    assert groups(lines) == {frozenset("a"), frozenset("b")}


def test_garbage_parent_types_do_not_crash():
    for junk in (0, 1.5, True, [], {}, "  ", "null", "None"):
        out = conversations([L("a", "a", 0), L("b", junk, 5)])
        assert sum(len(g) for g in out) == 2


def test_a_line_cannot_continue_something_said_later():
    """A pointer into the future is a lying clock or a confused model. Refuse
    it rather than build structure on it."""
    lines = [L("a", "b", 0), L("b", "b", 500)]
    assert groups(lines) == {frozenset("a"), frozenset("b")}


def test_missing_timestamps_disable_the_check_rather_than_guess():
    """Old app builds wrote no capture stamp. Absent must mean 'do not check',
    never 'treat as zero' — the second silently drops the oldest lines."""
    lines = [L("a", "a", None), L("b", "a", None)]
    assert groups(lines) == {frozenset("ab")}


def test_a_cycle_is_broken_and_does_not_hang():
    lines = [L("a", "b", 0), L("b", "a", 1)]
    out = conversations(lines)
    assert sum(len(g) for g in out) == 2


def test_a_long_cycle_is_broken():
    lines = [L("a", "c", 0), L("b", "a", 1), L("c", "b", 2)]
    out = conversations(lines)
    assert sum(len(g) for g in out) == 3


def test_empty_and_idless_input():
    assert conversations([]) == []
    assert conversations([{"parent": "x"}]) == []
    assert conversation_of("nope", [L("a", "a", 0)]) == []


# ------------------------------------------------------------------ LAWS

def _random_lines(rng, n):
    ids = [f"l{i}" for i in range(n)]
    lines = []
    for i, lid in enumerate(ids):
        at = float(i * rng.choice([1, 5, 60, 400, 5000]))
        roll = rng.random()
        if i == 0 or roll < 0.35:
            parent = lid                       # starts something
        elif roll < 0.85:
            parent = ids[rng.randrange(0, i)]  # continues something earlier
        elif roll < 0.93:
            parent = None                      # model said nothing
        else:
            parent = f"ghost{i}"               # model hallucinated
        lines.append(L(lid, parent, at))
    return lines


def test_LAW_order_independence():
    """Delivering the same speech in a different order MUST give the same
    conversations. This is the Omi bug (#6551) as a law. Under a timer it was
    violated 20 times out of 20 on Omar's own data; here it is structural —
    a component is a set, and this module never reads arrival order."""
    rng = random.Random(20260805)
    for _ in range(400):
        lines = _random_lines(rng, rng.randint(2, 30))
        shuffled = lines[:]
        rng.shuffle(shuffled)
        assert groups(lines) == groups(shuffled)


def test_LAW_silence_is_not_an_input():
    """Stretching every gap by an arbitrary amount cannot change anything,
    because no threshold exists to cross. Under the timer this was the entire
    failure mode."""
    rng = random.Random(11)
    for _ in range(400):
        lines = _random_lines(rng, rng.randint(2, 25))
        stretched = [dict(ln, spoken_at=(ln["spoken_at"] or 0) * 1000)
                     for ln in lines]
        assert groups(lines) == groups(stretched)


def test_LAW_adding_a_line_never_splits_an_existing_conversation():
    """Omar's ruling — 'better it overreacts than underreacts' — as an
    algebraic property rather than a setting. Union-find can only ever merge,
    so a late-arriving line can join two groups but can never tear one apart.
    Nobody can tune this the wrong way later."""
    rng = random.Random(7)
    for _ in range(400):
        lines = _random_lines(rng, rng.randint(2, 25))
        before = groups(lines)
        extra = L("late", rng.choice([l["id"] for l in lines] + ["late"]),
                  rng.choice([-9999.0, 0.5, 99999.0]))
        after = groups(lines + [extra])
        for old in before:
            covering = [new for new in after if old & new]
            assert len(covering) == 1, "an existing conversation was split"
            assert old <= covering[0], "members were taken out of a conversation"


def test_LAW_idempotent():
    rng = random.Random(3)
    for _ in range(200):
        lines = _random_lines(rng, rng.randint(1, 20))
        assert groups(lines) == groups(lines)


def test_LAW_it_is_always_a_partition():
    rng = random.Random(99)
    for _ in range(400):
        lines = _random_lines(rng, rng.randint(1, 30))
        out = conversations(lines)
        flat = [i for g in out for i in g]
        assert sorted(flat) == sorted(l["id"] for l in lines)
        assert len(flat) == len(set(flat))


def test_LAW_self_link_and_no_link_are_the_same_answer():
    """"I start something new" and "I could not tell" must land in the same
    place, or the model is punished for admitting uncertainty."""
    rng = random.Random(5)
    for _ in range(200):
        n = rng.randint(2, 15)
        lines = _random_lines(rng, n)
        selfed = [dict(ln, parent=ln["id"]) for ln in lines]
        nulled = [dict(ln, parent=None) for ln in lines]
        assert groups(selfed) == groups(nulled)


def test_LAW_presentation_order_is_deterministic_but_membership_is_not_ordered():
    rng = random.Random(4242)
    for _ in range(200):
        lines = _random_lines(rng, rng.randint(2, 20))
        shuffled = lines[:]
        rng.shuffle(shuffled)
        assert conversations(lines) == conversations(lines)      # stable
        assert groups(lines) == groups(shuffled)                 # order-free


def test_LAW_walking_parents_always_terminates():
    """resolve_parents promises an acyclic map, and callers walk it to render
    a thread or find where a conversation began. If a model answers "A
    continues B" and "B continues A", a caller without its own visited-set
    spins forever. Written after a mutation test showed cycle-breaking could
    be deleted with every other test still green — grouping does not need it,
    so nothing was holding it up."""
    rng = random.Random(31337)
    for _ in range(400):
        lines = _random_lines(rng, rng.randint(2, 25))
        # Force loops in, of every length, including ones the model could
        # plausibly emit by simply being confused about two similar lines.
        ids = [l["id"] for l in lines]
        if len(ids) >= 2:
            k = rng.randint(2, min(6, len(ids)))
            ring = rng.sample(ids, k)
            by_id = {l["id"]: l for l in lines}
            for n, rid in enumerate(ring):
                by_id[rid]["parent"] = ring[(n - 1) % k]
                by_id[rid]["spoken_at"] = None      # no clock to reject it
        parent = resolve_parents(lines)
        for start in parent:
            node, steps = start, 0
            while parent[node] != node:
                node = parent[node]
                steps += 1
                assert steps <= len(parent), f"cycle reachable from {start}"
        # And grouping must still be sane despite the ring.
        flat = [i for g in conversations(lines) for i in g]
        assert sorted(flat) == sorted(ids)


def test_resolve_parents_never_points_outside_the_input():
    rng = random.Random(1234)
    for _ in range(200):
        lines = _random_lines(rng, rng.randint(1, 20))
        ids = {l["id"] for l in lines}
        for child, par in resolve_parents(lines).items():
            assert child in ids and par in ids


def test_deep_chains_do_not_blow_the_stack():
    lines = [L("l0", "l0", 0.0)]
    lines += [L(f"l{i}", f"l{i-1}", float(i)) for i in range(1, 5000)]
    assert groups(lines) == {frozenset(l["id"] for l in lines)}
