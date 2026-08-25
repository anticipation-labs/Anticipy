"""MUTATION TESTS FOR THE TAPE GATE (overnight/tape_gate.py).

A gate leg nobody has watched fail is not a gate leg. This repo has shipped
three that pass by matching nothing, and the leg this gate replaces —
tejas_gate leg 2 — read 8/8 green with five pieces of undeclared tape in the
tree. So every leg here is driven to RED on purpose, against a synthetic tree
built in a tmpdir, and then driven back to green.

These tests assert the MECHANISM, never the repo's current state: the real
tree is red today and should be, and a test that pinned that would go red the
day somebody actually deletes a piece of tape — punishing the fix.

Run:  python3 -m pytest -q tests/test_tape_gate.py
"""
from __future__ import annotations

import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load():
    spec = importlib.util.spec_from_file_location(
        "tape_gate", os.path.join(ROOT, "overnight", "tape_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tg = _load()


# --------------------------------------------------------------------------
# A synthetic tree: one shipped organ, one file, one piece of tape.
# --------------------------------------------------------------------------
CLEAN = '''\
import re

_FOO_RE = re.compile(r"cancel|abort")


def decide(line):
    """TAPE (HARNESS-LAWS.md Law 2): a word list is standing in for the
    model here. Expiry: the model declares the channel. Tracked by
    overnight/tape_gate.py."""
    return bool(_FOO_RE.search(line))
'''

LEDGER = """\
# THE HARNESS LAWS

## Known standing tape (legacy)

Tracked by overnight/tape_gate.py.

- `[tape:foo]` the `_FOO_RE` word list in brain/organ.py.

## The map
"""


def _tree(tmp_path, body=CLEAN, ledger=LEDGER):
    (tmp_path / "brain").mkdir()
    (tmp_path / "brain" / "organ.py").write_text(body, encoding="utf-8")
    (tmp_path / "HARNESS-LAWS.md").write_text(ledger, encoding="utf-8")
    return str(tmp_path)


def _entry(**over):
    kw = dict(tid="foo", rel="brain/organ.py", find='_FOO_RE = re.compile(',
              what="a word list stands in for the model",
              real_fix="the model declares the channel; then _FOO_RE is deleted",
              marker_home="decide", audit_item=99,
              ledger_needle="[tape:foo]")
    kw.update(over)
    return tg.Tape(**kw)


ONLY = ("brain",)


# --------------------------------------------------------------------------
# The marker regex has to catch every form the real tree actually uses. If it
# misses one, undeclared tape is invisible and the whole gate is theatre.
# --------------------------------------------------------------------------
@pytest.mark.parametrize("line", [
    "        TAPE: the prose fallback below is for rows minted before",
    "    TAPE (HARNESS-LAWS.md Law 2): this degraded-path drop expires when",
    '    """TAPE (HARNESS-LAWS.md Law 2). Expiry: segment-granularity triage',
    "// TAPE: emergency patch, no expiry",
])
def test_marker_regex_catches_every_house_form(line):
    assert tg.MARKER_RE.search(line), f"marker form went unseen: {line!r}"


@pytest.mark.parametrize("line", [
    "    # this leg fails if the shard floor lost its TAPE marking",
    '    if "TAPE" not in core.split("def shard_too_thin", 1)[-1][:900]:',
    "    # duct tape and prayer",
])
def test_marker_regex_does_not_fire_on_prose_about_tape(line):
    assert not tg.MARKER_RE.search(line), f"false marker on: {line!r}"


# --------------------------------------------------------------------------
# LEG 1 — the anti-silence leg. Both directions.
# --------------------------------------------------------------------------
def test_leg1_passes_when_the_only_marker_is_registered(tmp_path):
    root = _tree(tmp_path)
    detail = tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    assert "1 marker" in detail and "1 registered" in detail


def test_leg1_goes_red_on_an_unregistered_marker(tmp_path):
    """The mutation: someone ships a string patch with a TAPE: comment and
    never registers it. Before this leg existed that was invisible."""
    body = CLEAN + '\n\n# TAPE: emergency patch, nothing tracks this.\nX = 1\n'
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    assert "never heard of" in str(e.value)
    assert "brain/organ.py:" in str(e.value)


def test_leg1_sees_a_second_marker_hiding_in_a_declared_function(tmp_path):
    """The hole this leg's own first draft had: it claimed markers by FILE, so
    a second undeclared marker inside an already-declared file rode through on
    the first one's declaration. brain/anticipy_core.py is 4000 lines and holds
    two declared markers, which made this the likeliest way to hide tape."""
    body = CLEAN.replace(
        "    return bool(_FOO_RE.search(line))",
        "    # TAPE: second patch, same function, nobody registered it.\n"
        "    return bool(_FOO_RE.search(line))")
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    assert "never heard of" in str(e.value)
    assert "second patch" in str(e.value)


def test_leg1_goes_red_when_registered_tape_is_gone_but_the_entry_stays(tmp_path):
    """Law 2: tape whose leg went green gets DELETED, not kept. A registry
    that outlives its tape is the next false 'tracked by leg 4'."""
    root = _tree(tmp_path, body="X = 1\n")
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    assert "no longer in the tree" in str(e.value)


def test_leg1_cannot_be_tested_counts_as_failing(tmp_path):
    root = _tree(tmp_path)
    gone = _entry(rel="brain/moved_away.py")
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [gone], dirs=ONLY)
    assert "does not exist" in str(e.value)


# --------------------------------------------------------------------------
# LEG 2 — the polarity fix: RED while the tape lives, green when it is gone.
# This is the direction tejas_gate leg 2 does not have.
# --------------------------------------------------------------------------
def test_leg2_is_red_while_the_tape_is_present(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_2_tape_expires(root, [_entry()])
    msg = str(e.value)
    assert "still load-bearing" in msg
    assert "the model declares the channel" in msg, "the message must name the real fix"


def test_leg2_goes_green_only_when_the_tape_is_deleted(tmp_path):
    root = _tree(tmp_path, body="def decide(line):\n    return False\n")
    detail = tg.leg_2_tape_expires(root, [_entry()])
    assert "no tape is left" in detail


def test_leg2_expiry_can_be_a_branch_inside_a_surviving_function(tmp_path):
    """#19 and #21 are fallback BRANCHES, not whole symbols: the function
    stays, the prose fallback inside it goes. The expiry has to see that."""
    withtape = "def decide(g):\n    if sniff(g):\n        return False\n    return True\n"
    entry = _entry(find="if sniff(g):",
                   expired=tg._fallback_gone("brain/organ.py", "decide",
                                             "if sniff(g):"))
    root = _tree(tmp_path, body=withtape)
    with pytest.raises(tg.LegFailed):
        tg.leg_2_tape_expires(root, [entry])

    (tmp_path / "brain" / "organ.py").write_text(
        "def decide(g):\n    return True\n", encoding="utf-8")
    # the branch is gone, so it has expired — even though decide() survives
    assert entry.expired(root) is True


# --------------------------------------------------------------------------
# LEG 3 — the census leg. Declared means marker + registry + the marker
# naming THIS gate. A comment naming a leg that tracks something else is
# audit item #21, and it read as compliant for months.
# --------------------------------------------------------------------------
def test_leg3_accepts_a_marker_that_names_this_gate(tmp_path):
    root = _tree(tmp_path)
    detail = tg.leg_3_audited_five(root, [_entry()], census_ids=(99,))
    assert "accounted for" in detail


def test_leg3_goes_red_when_the_marker_is_missing_entirely(tmp_path):
    body = CLEAN.replace("TAPE (HARNESS-LAWS.md Law 2):", "NOTE:")
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_3_audited_five(root, [_entry()], census_ids=(99,))
    assert "NO `TAPE:` comment at all" in str(e.value)


def test_leg3_goes_red_when_the_marker_names_the_wrong_leg(tmp_path):
    """audit item #21, made mechanical: a TAPE: comment naming 'the same leg
    that tracks _READ_ONLY_RE's removal' where that leg tests neither."""
    body = CLEAN.replace("overnight/tape_gate.py",
                         "the same leg that tracks _READ_ONLY_RE's removal")
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_3_audited_five(root, [_entry()], census_ids=(99,))
    assert "does not name" in str(e.value)


def test_leg3_is_satisfied_when_the_tape_is_gone_instead(tmp_path):
    root = _tree(tmp_path, body="X = 1\n")
    detail = tg.leg_3_audited_five(root, [_entry()], census_ids=(99,))
    assert "gone from the tree: foo" in detail


def test_leg3_cannot_be_satisfied_by_an_empty_registry(tmp_path):
    """The whole point. If leg 3 could pass because nothing declared itself,
    it would be the same nothing the audit found — five pieces deep."""
    root = _tree(tmp_path)
    with pytest.raises(tg.LegFailed):
        tg.leg_4_census_intact(root, [])


# --------------------------------------------------------------------------
# LEG 4 — the tripwire on shortening the census to quiet leg 3.
# --------------------------------------------------------------------------
def test_leg4_goes_red_when_a_census_entry_is_dropped(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root, [t for t in tg.KNOWN_TAPE
                                      if t.audit_item != 22])
    assert "was dropped or renumbered" in str(e.value)


def test_leg4_passes_on_the_real_registry():
    detail = tg.leg_4_census_intact(ROOT)
    assert "census intact" in detail


def test_leg4_count_constant_is_the_tripwire():
    """AUDIT_UNDECLARED_COUNT is declared apart from the list on purpose:
    deleting an item then has to be a deliberate edit to a number."""
    assert len(tg.AUDIT_UNDECLARED) == tg.AUDIT_UNDECLARED_COUNT == 5
    assert tg.AUDIT_DECLARED_COUNT == 0


# --------------------------------------------------------------------------
# LEG 5 — the third book. The law file and the registry have to agree.
# --------------------------------------------------------------------------
def test_leg5_passes_when_the_ledger_names_the_entry(tmp_path):
    root = _tree(tmp_path)
    detail = tg.leg_5_ledger_agrees(root, [_entry()])
    assert "ledger names every one" in detail


def test_leg5_goes_red_when_the_ledger_never_heard_of_it(tmp_path):
    root = _tree(tmp_path, ledger=LEDGER.replace("`[tape:foo]`", "`[tape:bar]`"))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [_entry()])
    assert "never mentions" in str(e.value)


def test_leg5_goes_red_when_the_ledger_section_is_deleted(tmp_path):
    root = _tree(tmp_path, ledger="# THE HARNESS LAWS\n\n## The map\n")
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [_entry()])
    assert "no \"Known standing tape\" section" in str(e.value)


def test_leg5_goes_red_when_the_ledger_names_no_leg(tmp_path):
    root = _tree(tmp_path,
                 ledger=LEDGER.replace("Tracked by overnight/tape_gate.py.", ""))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [_entry()])
    assert "does not name" in str(e.value)


# --------------------------------------------------------------------------
# The real tree, as of the 2026-08-24 audit: this gate must be RED. If it ever
# goes green, either every piece of tape is gone (celebrate, then delete this
# test) or a predicate got softened (do not).
# --------------------------------------------------------------------------
def test_the_real_registry_still_points_at_real_code():
    """Line numbers move — three agents were editing brain/ during the audit.
    The registry finds tape by SYMBOL for exactly that reason, and this asserts
    every symbol still resolves. A registry that has silently stopped matching
    is a registry that passes by matching nothing."""
    for t in tg.KNOWN_TAPE:
        src = tg.read(ROOT, t.rel)
        assert t.find in src, f"{t.id}: registry needle no longer in {t.rel}"
        assert t.marker_text(ROOT), f"{t.id}: marker home resolves to nothing"


def test_every_leg_message_says_what_to_do():
    """Law-2 legs are read by whoever is blocked. Every failure here has to end
    in an instruction, not an assertion."""
    fails = 0
    for _num, _name, fn in tg.LEGS:
        try:
            fn(ROOT)
        except tg.LegFailed as e:
            fails += 1
            msg = str(e)
            assert len(msg) > 120, f"terse failure message: {msg}"
    assert fails >= 1, ("the tape gate is entirely green against the real "
                        "tree — either the tape is gone, or a leg stopped "
                        "matching anything")
