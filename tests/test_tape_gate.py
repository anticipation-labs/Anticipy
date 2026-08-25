"""MUTATION TESTS FOR THE TAPE GATE (overnight/tape_gate.py).

A gate leg nobody has watched fail is not a gate leg. This repo has shipped
three that pass by matching nothing, and the leg this gate replaces —
tejas_gate leg 2 — read 8/8 green with five pieces of undeclared tape in the
tree. So every leg here is driven to RED on purpose, against a synthetic tree
built in a tmpdir, and then driven back to green.

These tests assert the MECHANISM, never the repo's current state: the real
tree is red today and should be, and a test that pinned that would go red the
day somebody actually deletes a piece of tape — punishing the fix. The one
exception is deliberate and marked: test_the_real_tree_red_legs_are_the_known
pins WHICH legs are red, not that tape exists, because "which legs are red" is
the only thing that can tell the steady state from a new failure.

The 2026-08-24 review found four more holes in the gate and they all have a
test here:
  * C1  an extract-method refactor retired live tape from leg 2 AND leg 3.
  * I2  leg 4 printed "the audit agrees" when its regex matched nothing.
  * I3  CODE_EXTS had `.h` and not `.c`, so 142 firmware files were invisible.
  * I4  a real failure printed as one lowercase line under a by-design red.
  * M5  a marker split across two comment lines was invisible to the gate and
        visible to a human grepping TAPE.

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
    # parents=True so a test can build two trees side by side under one
    # tmp_path and compare the gate's answer before and after a closure.
    (tmp_path / "brain").mkdir(parents=True, exist_ok=True)
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
    # M5: the split form. A human greps TAPE, finds this, and reads it as
    # declared; the gate has to see what the human sees.
    "# TAPE",
    "    // TAPE  ",
])
def test_marker_regex_catches_every_house_form(line):
    assert tg.MARKER_RE.search(line.rstrip()), f"marker form went unseen: {line!r}"


@pytest.mark.parametrize("line", [
    "    # this leg fails if the shard floor lost its TAPE marking",
    '    if "TAPE" not in core.split("def shard_too_thin", 1)[-1][:900]:',
    "    # duct tape and prayer",
    "    label = TAPE_KINDS[0]",
])
def test_marker_regex_does_not_fire_on_prose_about_tape(line):
    assert not tg.MARKER_RE.search(line.rstrip()), f"false marker on: {line!r}"


def test_m5_a_marker_split_across_two_comment_lines_is_not_invisible(tmp_path):
    """M5, reproduced: before 2026-08-24 the marker regex needed `:` or `.` on
    the same line as TAPE, so this shipped as `[1] PASS ... none orphaned`
    while `grep -rn TAPE` found it and a reader called it declared. That is
    audit item #21's shape — a declaration that reads compliant and enforces
    nothing — recreated inside the enforcement."""
    body = (CLEAN + "\n\n# TAPE\n# (HARNESS-LAWS.md Law 2): urgency by word "
            "list. Tracked by overnight/tape_gate.py.\n_URGENT = ('asap',)\n")
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    assert "never heard of" in str(e.value)


# --------------------------------------------------------------------------
# LEG 1 (a) — CAN THE LEG READ WHAT THE HEADER SAYS IT SCANS?
#
# I3: CODE_EXTS held `.h` and not `.c`, so leg 1 could not read 142 of the 235
# files in firmware/ — a directory its own header named. Undeclared tape in the
# pendant firmware was a rejected diff under Law 2 and a PASS under the leg
# that enforces it. The fix is not "add .c"; it is that every file has to be
# classified, and unclassified is red.
# --------------------------------------------------------------------------
def test_leg1_reads_c_files(tmp_path):
    """The exact I3 mutation: undeclared tape in firmware C."""
    (tmp_path / "brain").mkdir()
    (tmp_path / "brain" / "led.c").write_text(
        "/* TAPE: clamp the duty cycle by hand. */\n#define X 42\n",
        encoding="utf-8")
    (tmp_path / "HARNESS-LAWS.md").write_text(LEDGER, encoding="utf-8")
    markers = tg.find_markers(str(tmp_path), ONLY)
    assert markers and markers[0][0] == "brain/led.c"


def test_leg1_goes_red_on_a_file_type_it_cannot_classify(tmp_path):
    """A new language lands in a shipped organ. The gate must not quietly
    stop covering it — the whole I3 failure was silence about reach."""
    root = _tree(tmp_path)
    (tmp_path / "brain" / "decide.rrr").write_text("x", encoding="utf-8")
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    assert "neither read for" in str(e.value)
    assert "brain/decide.rrr" in str(e.value)


def test_leg1_goes_red_on_a_shipped_organ_it_can_read_nothing_out_of(tmp_path):
    """`chrome/` was in SHIPPED_DIRS holding one .metadata file, so the header
    printed a scan scope the leg did not have."""
    root = _tree(tmp_path)
    (tmp_path / "chrome").mkdir()
    (tmp_path / "chrome" / ".metadata").write_text("{}", encoding="utf-8")
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()],
                                        dirs=("brain", "chrome"))
    assert "can read nothing at all" in str(e.value)


def test_leg1_goes_red_when_a_named_shipped_organ_is_not_there(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()],
                                        dirs=("brain", "firmware"))
    assert "no such directory" in str(e.value)


def test_leg1_detail_states_its_actual_reach(tmp_path):
    root = _tree(tmp_path)
    detail = tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    assert "read 1 of 1 files" in detail


@pytest.mark.parametrize("ext", [".py", ".js", ".mjs", ".swift", ".sh",
                                 ".c", ".h", ".html"])
def test_the_languages_this_repo_actually_ships_are_read(ext):
    """The other way to reopen I3 is quieter than deleting an extension: move
    one from CODE_EXTS into NOT_CODE_EXTS and the reach check goes on passing
    while the files stop being read. These are the languages the shipped
    organs are written in, so demoting one has to break a named test."""
    assert ext in tg.CODE_EXTS, f"{ext} stopped being read for TAPE: markers"
    assert ext not in tg.NOT_CODE_EXTS


def test_declared_data_and_code_do_not_overlap():
    """One file, one answer. An extension in both lists would make the reach
    number a fiction."""
    both = set(tg.CODE_EXTS) & set(tg.NOT_CODE_EXTS)
    assert not both, f"extension classified twice: {both}"
    assert tg.is_code("led.c") and not tg.is_declared_data("led.c")
    assert tg.is_declared_data(".DS_Store") and not tg.is_code(".DS_Store")


# --------------------------------------------------------------------------
# LEG 1 (b) — the anti-silence leg. Every direction.
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
# C1 — ONE SCOPE, THREE STATES.
#
# The Critical. `present()` searched the whole file and `expired()` searched
# only the enclosing def, so tape that MOVED was "expired" while it was still
# in the tree and still running. An ordinary extract-method refactor retired
# live tape from BOTH leg 2 and leg 3 at once. Nobody softened a predicate —
# the predicate's scope was wrong, which is the subtler failure.
# --------------------------------------------------------------------------
MOVABLE = '''\
def decide(g):
    # TAPE (HARNESS-LAWS.md Law 2): the undeclared-goal default.
    # Tracked by overnight/tape_gate.py.
    if sniff(g):
        return False
    return True
'''

REFACTORED = '''\
def decide(g):
    # TAPE (HARNESS-LAWS.md Law 2): the undeclared-goal default.
    # Tracked by overnight/tape_gate.py.
    return _undeclared_default(g)


def _undeclared_default(g):
    if sniff(g):
        return False
    return True
'''


def _branch_entry(**over):
    kw = dict(find="if sniff(g):", home="decide", marker_home="decide")
    kw.update(over)
    return _entry(**kw)


def test_a_branch_inside_a_surviving_function_is_live(tmp_path):
    """#19 and #21 are fallback BRANCHES, not whole symbols: the function
    stays, the prose fallback inside it goes. The scope has to see that."""
    root = _tree(tmp_path, body=MOVABLE)
    assert _branch_entry().state(root, ONLY)[0] == tg.LIVE
    with pytest.raises(tg.LegFailed):
        tg.leg_2_tape_expires(root, [_branch_entry()], dirs=ONLY)


def test_a_branch_that_is_deleted_has_expired(tmp_path):
    root = _tree(tmp_path, body="def decide(g):\n    return True\n")
    assert _branch_entry().expired(root, ONLY) is True
    assert "no live tape is left" in tg.leg_2_tape_expires(
        root, [_branch_entry()], dirs=ONLY)


def test_c1_an_extract_method_refactor_cannot_retire_live_tape(tmp_path):
    """THE mutation. Move the taped branch into a helper, leave the marker at
    the old site. Before the fix: leg 2 dropped the entry and leg 3 called it
    "gone from the tree" while `grep sniff` still found it running."""
    root = _tree(tmp_path, body=REFACTORED)
    entry = _branch_entry()
    state, where = entry.state(root, ONLY)
    assert state == tg.MOVED, "moved tape must not read as expired"
    assert where and "brain/organ.py:" in where[0]
    assert entry.expired(root, ONLY) is False

    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [entry], dirs=ONLY)
    assert "MOVED out from under" in str(e.value)

    with pytest.raises(tg.LegFailed) as e2:
        tg.leg_2_tape_expires(root, [entry], dirs=ONLY)
    assert "1 piece(s) of tape are still load-bearing" in str(e2.value)

    detail = tg.leg_3_audited_five(root, [entry], census_ids=(99,), dirs=ONLY)
    assert "gone from the tree" not in detail, (
        "leg 3 called still-running tape 'gone' — that was half of C1")


def test_c1_tape_that_moves_to_another_file_is_not_gone(tmp_path):
    """Moving a FILE is a refactor too. Before reaching GONE — which retires
    the entry and lets leg 2 go green — the rest of the shipped organs are
    searched."""
    root = _tree(tmp_path, body="def decide(g):\n    return True\n")
    (tmp_path / "brain" / "shards.py").write_text(
        "def decide(g):\n    if sniff(g):\n        return False\n",
        encoding="utf-8")
    entry = _branch_entry()
    state, where = entry.state(root, ONLY)
    assert state == tg.MOVED
    assert any("brain/shards.py:" in w for w in where)


def test_c1_a_home_that_no_longer_exists_is_moved_not_gone(tmp_path):
    """Rename the enclosing def and the registry's map goes stale. That is the
    registry lying, not the tape expiring."""
    root = _tree(tmp_path, body=MOVABLE.replace("def decide(", "def judge("))
    state, _where = _branch_entry().state(root, ONLY)
    assert state == tg.MOVED


def test_c1_an_identical_line_elsewhere_does_not_keep_a_dead_entry_alive(tmp_path):
    """The other half of C1: `if compute_answer(g):` occurs twice in
    anticipy_core.py, the second in an unrelated browser-arm router. With a
    whole-file present(), deleting the real tape left the entry looking alive
    and leg 1 never prompted anyone to retire it. `home` tells them apart."""
    body = ("def decide(g):\n    return True\n\n\n"
            "def job_lane(g):\n    if sniff(g):\n        return 'research'\n")
    root = _tree(tmp_path, body=body)
    entry = _branch_entry()
    state, where = entry.state(root, ONLY)
    assert state == tg.MOVED, "the gate must not guess which site was the tape"
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [entry], dirs=ONLY)
    assert "CLOSE the entry" in str(e.value)


def test_present_and_expired_are_the_same_question(tmp_path):
    """The invariant C1 broke. Whatever the tree looks like, these two can
    never both be true and can never both be false."""
    bodies = (CLEAN, MOVABLE, REFACTORED, "X = 1\n",
              MOVABLE.replace("def decide(", "def judge("))
    for n, body in enumerate(bodies):
        d = tmp_path / f"tree{n}"
        d.mkdir()
        root = _tree(d, body=body)
        for entry in (_entry(), _branch_entry()):
            assert entry.present(root, ONLY) != entry.expired(root, ONLY)


# --------------------------------------------------------------------------
# LEG 2 — the polarity fix: RED while the tape lives, green when it is gone.
# This is the direction tejas_gate leg 2 does not have.
# --------------------------------------------------------------------------
def test_leg2_is_red_while_the_tape_is_present(tmp_path):
    root = _tree(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_2_tape_expires(root, [_entry()], dirs=ONLY)
    msg = str(e.value)
    assert "still load-bearing" in msg
    assert "the model declares the channel" in msg, "the message must name the real fix"


def test_leg2_goes_green_only_when_the_tape_is_deleted(tmp_path):
    root = _tree(tmp_path, body="def decide(line):\n    return False\n")
    detail = tg.leg_2_tape_expires(root, [_entry()], dirs=ONLY)
    assert "no live tape is left" in detail


def test_leg2_says_when_a_live_piece_has_moved(tmp_path):
    root = _tree(tmp_path, body=REFACTORED)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_2_tape_expires(root, [_branch_entry()], dirs=ONLY)
    assert "MOVED" in str(e.value)


def test_no_entry_carries_its_own_expiry_predicate():
    """The `expired=` hook is how the two scopes came to disagree. It is gone,
    and this is the leg that keeps it gone: a future entry that re-introduces a
    per-entry predicate has to delete this test to do it."""
    assert not hasattr(tg, "_fallback_gone")
    with pytest.raises(TypeError):
        _entry(expired=lambda root: True)


# --------------------------------------------------------------------------
# LEG 3 — the census leg. Declared means marker + registry + the marker
# naming THIS gate. A comment naming a leg that tracks something else is
# audit item #21, and it read as compliant for months.
# --------------------------------------------------------------------------
def test_leg3_accepts_a_marker_that_names_this_gate(tmp_path):
    root = _tree(tmp_path)
    detail = tg.leg_3_audited_five(root, [_entry()], census_ids=(99,), dirs=ONLY)
    assert "accounted for" in detail


def test_leg3_goes_red_when_the_marker_is_missing_entirely(tmp_path):
    body = CLEAN.replace("TAPE (HARNESS-LAWS.md Law 2):", "NOTE:")
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_3_audited_five(root, [_entry()], census_ids=(99,), dirs=ONLY)
    assert "NO `TAPE:` comment at all" in str(e.value)


def test_leg3_goes_red_when_the_marker_names_the_wrong_leg(tmp_path):
    """audit item #21, made mechanical: a TAPE: comment naming 'the same leg
    that tracks _READ_ONLY_RE's removal' where that leg tests neither."""
    body = CLEAN.replace("overnight/tape_gate.py",
                         "the same leg that tracks _READ_ONLY_RE's removal")
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_3_audited_five(root, [_entry()], census_ids=(99,), dirs=ONLY)
    assert "does not name" in str(e.value)


def test_leg3_is_satisfied_when_the_tape_is_gone_instead(tmp_path):
    root = _tree(tmp_path, body="X = 1\n")
    detail = tg.leg_3_audited_five(root, [_entry()], census_ids=(99,), dirs=ONLY)
    assert "gone from the tree: foo" in detail


def test_leg3_cannot_be_satisfied_by_an_empty_registry(tmp_path):
    """The whole point. If leg 3 could pass because nothing declared itself,
    it would be the same nothing the audit found — five pieces deep."""
    root = _tree(tmp_path)
    with pytest.raises(tg.LegFailed):
        tg.leg_4_census_intact(root, [])


# --------------------------------------------------------------------------
# LEG 4 — the tripwire on shortening the census to quiet leg 3, and on the
# third book going offline.
# --------------------------------------------------------------------------
AUDIT_ROWS = """\
| **VIOLATION** (pattern decides meaning) | **61** |
| **TAPE, UNDECLARED** (no `TAPE:` comment, **or** one with no leg) | **5** |
| **TAPE, properly declared** (comment **and** a leg) | **0** |
"""


def _audit(tmp_path, text=AUDIT_ROWS):
    (tmp_path / "research").mkdir(exist_ok=True)
    (tmp_path / "research" / "2026-08-24-law1-audit.md").write_text(
        text, encoding="utf-8")


def test_leg4_goes_red_when_a_census_entry_is_dropped(tmp_path):
    root = _tree(tmp_path)
    _audit(tmp_path)
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


def test_leg4_reads_the_audit_doc_and_agrees_with_it(tmp_path):
    root = _tree(tmp_path)
    _audit(tmp_path)
    detail = tg.leg_4_census_intact(root)
    assert "5 undeclared" in detail and "0 properly declared" in detail


def test_leg4_goes_red_when_the_audit_doc_disagrees(tmp_path):
    root = _tree(tmp_path)
    _audit(tmp_path, AUDIT_ROWS.replace("| **5** |", "| **1** |"))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root)
    assert "now reports 1" in str(e.value)


def test_i2_leg4_cannot_claim_the_audit_agrees_when_it_read_nothing(tmp_path):
    """I2, the exact mutation: rename ONE heading in the audit doc — a
    formatting edit, no number touched — and the old leg skipped the check and
    STILL PRINTED "the audit doc agrees: 5 undeclared". The third book went
    silently offline inside the one leg built to be the tripwire, and the doc
    could then be edited down to any census."""
    root = _tree(tmp_path)
    _audit(tmp_path, AUDIT_ROWS.replace("**TAPE, UNDECLARED**",
                                        "**TAPE (undeclared)**")
                               .replace("| **5** |", "| **1** |"))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root)
    msg = str(e.value)
    assert "can no longer find" in msg and "undeclared" in msg
    assert "agrees: " not in msg, (
        "a message must never assert what it did not check — the old leg "
        "printed the PASS phrase 'agrees: 5 undeclared' having matched nothing")


def test_i2_the_declared_count_row_is_read_too(tmp_path):
    """AUDIT_DECLARED_COUNT was a constant no leg ever looked at — its own way
    of looking thorough while checking nothing."""
    root = _tree(tmp_path)
    _audit(tmp_path, AUDIT_ROWS.replace("**TAPE, properly declared**",
                                        "**TAPE, declared**"))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root)
    assert "properly declared" in str(e.value)


def test_leg4_goes_red_when_the_audit_doc_is_deleted(tmp_path):
    """Deleting the third book must not be cheaper than editing it."""
    root = _tree(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root)
    assert "not in this tree" in str(e.value)


def test_leg4_row_regex_cannot_wander_into_another_table(tmp_path):
    """The old pattern spanned the whole document with `.*?` under re.S, so a
    reformatted row let the match slide forward onto some unrelated bolded
    number and vouch for that instead."""
    root = _tree(tmp_path)
    _audit(tmp_path,
           "| **TAPE, UNDECLARED** (row lost its bold count) | 5 |\n"
           "| something else entirely | **5** |\n"
           "| **TAPE, properly declared** (comment and a leg) | **0** |\n")
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root)
    assert "can no longer find" in str(e.value)


# --------------------------------------------------------------------------
# LEG 5 — the third book. The law file and the registry have to agree, both
# ways: the docstring said "and vice versa" from day one and only one
# direction was implemented.
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


def test_leg5_goes_red_when_the_ledger_carries_a_bullet_with_no_entry(tmp_path):
    """The reverse direction. A `[tape:…]` bullet whose registry entry was
    deleted reads as compliant to a human and runs no predicate at all — the
    same shape as leg 4's shrinking census, one file over."""
    root = _tree(tmp_path,
                 ledger=LEDGER.replace("## The map",
                                       "- `[tape:ghost]` something nobody "
                                       "registered.\n\n## The map"))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [_entry()])
    assert "[tape:ghost]" in str(e.value)


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
# I4 — THE VERDICT ITSELF. A by-design-red gate still has to be able to raise
# an alarm.
#
# Leg 2 is red permanently and runs early, so before 2026-08-24 a census
# shrink printed as `[4] fail` in lowercase, buried under leg 2's twenty-line
# block, with the footer still reading "first failing leg: 2" and the exit code
# still 1. Nothing distinguished the expected steady state from somebody
# shrinking the census. Three things do now, and each is tested here: a
# separate exit code, a one-line fingerprint, and the message reprinted in the
# footer instead of buried.
# --------------------------------------------------------------------------
def _res(*legs):
    """(num, name, by_design_red, ok, detail)"""
    return [(n, f"LEG {n}", by, ok, f"message {n}") for n, by, ok in legs]


def test_i4_the_steady_state_and_a_new_failure_have_different_exit_codes():
    steady = _res((1, False, True), (2, True, False), (3, False, True),
                  (4, False, True), (5, False, True))
    shrunk = _res((1, False, True), (2, True, False), (3, False, True),
                  (4, False, False), (5, False, True))
    assert tg.verdict(steady) == 1
    assert tg.verdict(shrunk) == 2, (
        "a census shrink must not exit the same as the expected steady state")


def test_i4_clean_is_still_zero():
    assert tg.verdict(_res((1, False, True), (2, True, True))) == 0


def test_i4_the_fingerprint_names_which_legs_are_red():
    steady = _res((1, False, True), (2, True, False), (4, False, True))
    shrunk = _res((1, False, True), (2, True, False), (4, False, False))
    assert tg.fingerprint(steady) == "RED LEGS: 2 (by design)"
    assert tg.fingerprint(shrunk) == "RED LEGS: 2 (by design), 4"
    assert tg.fingerprint(steady) != tg.fingerprint(shrunk)


def test_i4_only_leg_2_is_red_by_design():
    """The by-design set is the definition of "normal". Widening it is how a
    gate stops being able to surprise anyone, so it is pinned."""
    assert tg.BY_DESIGN_RED == (2,)


def test_i4_the_footer_reprints_an_unexpected_failure(tmp_path, capsys):
    """Buried is the same as missing. An unexpected red has to be readable
    BELOW leg 2's twenty-line block, not swallowed by it."""
    root = _tree(tmp_path)          # the real registry points at files that
    _audit(tmp_path)                # are not in this tree, so leg 1 goes red
    code = tg.main(root)
    out = capsys.readouterr().out
    assert code == 2
    footer = out.split("-" * 62)[-1]
    assert "THE BOOKS DISAGREE" in footer
    assert "[1] EVERY MARKER IS REGISTERED" in footer
    assert "does not exist" in footer, "the message itself has to be reprinted"
    assert "RED LEGS:" in footer


def test_i4_the_steady_state_footer_does_not_cry_wolf(tmp_path, capsys):
    """The other direction, and the one that keeps the alarm meaningful: when
    only the by-design leg is red, the footer must not say the books disagree.
    An alarm that fires every run is the noise I4 was about."""
    results = _res((1, False, True), (2, True, False), (3, False, True),
                   (4, False, True), (5, False, True))
    assert tg.verdict(results) == 1
    assert tg.fingerprint(results) == "RED LEGS: 2 (by design)"


def test_i4_run_returns_every_leg_even_after_the_first_failure(tmp_path):
    """Legs run in order and the FIRST failure sets the verdict; later legs
    still run, so the whole picture is visible in one screen."""
    root = _tree(tmp_path)
    _audit(tmp_path)
    results = tg.run(root)
    assert [r[0] for r in results] == [1, 2, 3, 4, 5, 6]


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
        assert t.state(ROOT)[0] == tg.LIVE, (
            f"{t.id}: not where the registry says it is — see leg 1")


def test_every_leg_message_says_what_to_do():
    """Law-2 legs are read by whoever is blocked. Every failure here has to end
    in an instruction, not an assertion."""
    fails = 0
    for _num, _name, fn, _by_design in tg.LEGS:
        try:
            fn(ROOT)
        except tg.LegFailed as e:
            fails += 1
            msg = str(e)
            assert len(msg) > 120, f"terse failure message: {msg}"
    assert fails >= 1, ("the tape gate is entirely green against the real "
                        "tree — either the tape is gone, or a leg stopped "
                        "matching anything")


EXPECTED_RED_LEGS = "RED LEGS: 2 (by design)"


def test_the_real_tree_red_legs_are_the_known_ones():
    """The one test here that pins the repo's state, and it pins the only thing
    worth pinning: WHICH legs are red.

    Leg 2 is red by design and is the only red left. Any OTHER leg going red is
    news, and this test is how it reaches somebody who is not reading the gate's
    output today.

    LEG 3 CLOSED on 2026-08-25 in commit 108dbf0b, "The audited five are
    declared, and two of them were pointing at the wrong thing" — the five
    pieces the law-1 audit found undeclared now carry `TAPE:` comments naming
    this gate, and two that already had comments were pointing at a leg tracking
    something else (audit item #21's failure: a comment that names the wrong leg
    reads as compliant and enforces nothing).

    DECLARING IS NOT FIXING, and the fingerprint above is the proof: leg 2 is
    still red, because the tape itself is all still there. What changed is that
    every piece of it is now tracked by name. Do not read this line as the tape
    being gone.

    (Recorded here a commit late. 108dbf0b closed the leg without updating this
    constant, so the suite ran red for everyone in between — which is exactly
    the "same diff" this docstring asks for, and the reason it asks.)"""
    got = tg.fingerprint(tg.run(ROOT))
    assert got == EXPECTED_RED_LEGS, (
        f"the tape gate's red legs changed: {got!r}, expected "
        f"{EXPECTED_RED_LEGS!r}. If a leg went GREEN, say which and update "
        "this constant in the same diff. If a leg went RED, something broke "
        "the books — run `python3 overnight/tape_gate.py` and read the "
        "THE BOOKS DISAGREE block at the bottom.")


# --------------------------------------------------------------------------
# THE FOURTH STATE — CLOSED.
#
# The gap, in one sentence: this gate could record tape, and absent tape, and
# never CLOSED tape. Reproduced on 2026-08-25 against a mirror of the real tree
# with `shard_too_thin` actually deleted — every road out of leg 1's "now
# retire it" instruction was red, including the instruction leg 1 itself gave.
# The three reds are pinned below so the hole cannot reopen, and the fourth
# test is the road that now exists.
#
# Everything here is driven BOTH ways: a genuinely closed piece goes green, a
# resurrected one goes red. A closure that only goes one way is a list somebody
# wrote a name on.
# --------------------------------------------------------------------------
GONE_BODY = "def decide(line):\n    return False\n"

LEDGER_RETIRED = """\
# THE HARNESS LAWS

## Known standing tape (legacy)

Tracked by overnight/tape_gate.py.

## Retired tape

- `[tape:foo]` the `_FOO_RE` word list in brain/organ.py — DELETED in `abc1234`
  when the model came to own the channel. Behaviour pinned by
  overnight/replacement_gate.py.

## The map
"""

CLOSED_AUDIT = """\
| **TAPE, UNDECLARED** (no `TAPE:` comment, **or** one with no leg) | **1** |
| **TAPE, properly declared** (comment **and** a leg) | **0** |
"""


def _replacement(tmp_path, body="def leg_2_shard_guard():\n    return True\n"):
    (tmp_path / "overnight").mkdir(exist_ok=True)
    (tmp_path / "overnight" / "replacement_gate.py").write_text(
        body, encoding="utf-8")


def _closed(**over):
    """A ClosedTape wrapping the same synthetic entry the live tests use."""
    kw = dict(closed_by="abc1234", replaced_by="overnight/replacement_gate.py",
              proves="leg_2_shard_guard", note="the model owns the channel now")
    tape_over = {k: over.pop(k) for k in list(over)
                 if k not in ("closed_by", "replaced_by", "proves", "note")}
    kw.update(over)
    return tg.ClosedTape(_entry(**tape_over), **kw)


def _pin_census(monkeypatch, ids=(99,), n=1):
    """Point the census constants at the synthetic tree's one item, keeping
    the row regexes byte-identical to the real ones."""
    monkeypatch.setattr(tg, "AUDIT_UNDECLARED", ids)
    monkeypatch.setattr(tg, "AUDIT_UNDECLARED_COUNT", n)
    monkeypatch.setattr(tg, "CENSUS_ROWS", (
        ("undeclared", n, tg.CENSUS_ROWS[0][2]),
        ("properly declared", tg.AUDIT_DECLARED_COUNT, tg.CENSUS_ROWS[1][2]),
    ))


# --- the gap, reproduced --------------------------------------------------
def test_gap_dropping_the_entry_alone_is_red(tmp_path, monkeypatch):
    """Way 1, as leg 1 used to instruct: the tape is gone, so drop the entry.
    Leg 4 fires, because the census now covers one item fewer than the dated
    audit recorded."""
    root = _tree(tmp_path, body=GONE_BODY)
    _audit(tmp_path, CLOSED_AUDIT)
    _pin_census(monkeypatch)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root, registry=[], closed=[])
    assert "dropped or renumbered" in str(e.value)


def test_gap_lowering_the_count_alone_is_red(tmp_path, monkeypatch):
    """Way 2: keep the entry, shrink the census. Same leg, opposite direction
    — the registers now cover an item the census constants do not."""
    root = _tree(tmp_path, body=GONE_BODY)
    _audit(tmp_path, CLOSED_AUDIT)
    _pin_census(monkeypatch, ids=(), n=0)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root, registry=[_entry()], closed=[])
    assert "dropped or renumbered" in str(e.value)


def test_gap_doing_both_is_red_against_the_dated_document(tmp_path,
                                                          monkeypatch):
    """Way 3: drop the entry AND lower the count, which is internally
    consistent and still red — because the third book, a dated measurement
    nobody may edit, still says the original number."""
    root = _tree(tmp_path, body=GONE_BODY)
    _audit(tmp_path, CLOSED_AUDIT)          # the doc still says 1
    _pin_census(monkeypatch, ids=(), n=0)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root, registry=[], closed=[])
    assert "now reports 1" in str(e.value)


def test_gap_closing_the_entry_is_the_road_that_now_exists(tmp_path,
                                                           monkeypatch):
    """The fourth way, and the point of the whole diff: MOVE the entry. Every
    leg green, the census untouched, the dated document never edited."""
    root = _tree(tmp_path, body=GONE_BODY, ledger=LEDGER_RETIRED)
    _audit(tmp_path, CLOSED_AUDIT)
    _replacement(tmp_path)
    _pin_census(monkeypatch)
    shut = [_closed()]
    assert "0 registered, 1 closed" in tg.leg_1_markers_are_registered(
        root, [], dirs=ONLY, closed=shut)
    assert "no live tape is left" in tg.leg_2_tape_expires(root, [], dirs=ONLY)
    assert "all 1 audited pieces accounted for" in tg.leg_3_audited_five(
        root, [], census_ids=(99,), dirs=ONLY, closed=shut)
    detail = tg.leg_4_census_intact(root, registry=[], closed=shut)
    assert "1 audited items: 0 open, 1 closed" in detail
    assert "agrees: 1 undeclared" in detail
    assert "1 retired" in tg.leg_5_ledger_agrees(root, [], closed=shut)
    assert "still gone from" in tg.leg_6_closed_tape_stays_closed(
        root, [], shut, dirs=ONLY)


def test_gap_the_dated_document_is_never_edited_to_close_a_piece():
    """The real constants, pinned. Closing tape must never move these: they
    are a copy of a measurement of 2026-08-24, and closure changes the
    PARTITION of that fixed set, not the set."""
    assert tg.AUDIT_UNDECLARED == (19, 20, 21, 22, 50)
    assert tg.AUDIT_UNDECLARED_COUNT == 5
    assert tg.AUDIT_DECLARED_COUNT == 0
    covered = sorted([t.audit_item for t in tg.KNOWN_TAPE]
                     + [c.audit_item for c in tg.CLOSED_TAPE])
    assert tuple(covered) == tg.AUDIT_UNDECLARED, (
        "the two registers together are the census; if this fails an item was "
        "dropped from both instead of moved between them")


# --- leg 6, both directions ----------------------------------------------
def test_leg6_is_green_when_the_tape_is_really_gone(tmp_path):
    root = _tree(tmp_path, body=GONE_BODY)
    _replacement(tmp_path)
    detail = tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)
    assert "still gone from" in detail and "closed by abc1234" in detail


def test_leg6_goes_red_when_closed_tape_comes_back(tmp_path):
    """RESURRECTION — the whole reason a closed entry keeps a live predicate.
    A revert, a rebase, or a merge taking the older file puts the text back
    while every book still says closed. Two worktrees on divergent lineages
    makes this the ordinary case, not the exotic one."""
    root = _tree(tmp_path, body=CLEAN)      # the tape is back
    _replacement(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)
    msg = str(e.value)
    assert "RESURRECTION" in msg
    assert "brain/organ.py:3" in msg, "the message must name where it came back"
    assert "Do NOT resolve this by editing `find`" in msg


def test_leg6_goes_red_when_a_closure_never_happened(tmp_path):
    """The declaration attack, one state on: move an entry into CLOSED_TAPE to
    quiet leg 2 without deleting anything. Same red, and it is the same
    predicate that used to prove the entry LIVE."""
    root = _tree(tmp_path)                  # the tape never left
    _replacement(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)
    assert "RESURRECTION" in str(e.value)


def test_leg6_catches_a_resurrection_that_lands_in_another_file(tmp_path):
    """A cherry-pick or a partial revert can put the tape back somewhere else.
    `sites_anywhere` is deliberately not written in terms of a home path."""
    root = _tree(tmp_path, body=GONE_BODY)
    (tmp_path / "brain" / "other.py").write_text(
        'import re\n_FOO_RE = re.compile(r"cancel")\n', encoding="utf-8")
    _replacement(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)
    assert "brain/other.py:2" in str(e.value)


def test_leg6_survives_the_closed_entrys_whole_file_disappearing(tmp_path):
    """A closed entry's `rel` may itself be deleted later — that is a normal
    refactor, not a resurrection, and it must not turn the leg red with
    "cannot be tested"."""
    root = _tree(tmp_path, body=GONE_BODY)
    (tmp_path / "brain" / "organ.py").unlink()
    (tmp_path / "brain" / "keep.py").write_text("X = 1\n", encoding="utf-8")
    _replacement(tmp_path)
    assert "still gone from" in tg.leg_6_closed_tape_stays_closed(
        root, [], [_closed()], dirs=ONLY)


def test_leg6_does_not_fire_on_prose_that_merely_names_the_tape(tmp_path):
    """The wrong-fire direction. proof/outcome_rate.py in the real tree names
    `shard_too_thin` in five comments and a dict key; the needle is the tape's
    own TEXT, and a gate that fired on the name would be un-closeable."""
    root = _tree(tmp_path, body=(
        "# _FOO_RE used to live here; see research/2026-08-24-law1-audit.md\n"
        "def decide(line):\n    return False\n"))
    _replacement(tmp_path)
    assert "still gone from" in tg.leg_6_closed_tape_stays_closed(
        root, [], [_closed()], dirs=ONLY)


def test_leg6_vouches_for_nothing_when_the_register_is_empty(tmp_path):
    """I2's lesson, applied before it can happen: a leg that reports "all
    closed tape is still closed" having looked at an empty list is the
    sentence leg 4 used to print about an audit row it never read."""
    root = _tree(tmp_path)
    detail = tg.leg_6_closed_tape_stays_closed(root, [], [], dirs=ONLY)
    assert "is empty" in detail and "vouching for nothing" in detail
    assert "still gone" not in detail
    assert "closed" in detail


def test_leg6_refuses_to_vouch_when_the_scan_is_not_intact(tmp_path):
    """I3, applied to the new leg. "The text is nowhere in the shipped organs"
    is a statement about files that were OPENED. If leg 1 cannot classify the
    tree, this leg must not report a green it did not earn."""
    root = _tree(tmp_path, body=GONE_BODY)
    (tmp_path / "brain" / "thing.qqq").write_text("x", encoding="utf-8")
    _replacement(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)
    msg = str(e.value)
    assert "cannot say that closed tape stayed closed" in msg
    assert "neither read nor" in msg


def test_leg6_does_not_double_leg1s_reach_complaint_when_nothing_is_closed(
        tmp_path):
    """The other direction, and it is what keeps the alarm meaningful: with an
    empty register there is nothing to vouch for, so an unclassified file is
    leg 1's news alone and does not fire two legs for one cause."""
    root = _tree(tmp_path)
    (tmp_path / "brain" / "thing.qqq").write_text("x", encoding="utf-8")
    assert "is empty" in tg.leg_6_closed_tape_stays_closed(
        root, [], [], dirs=ONLY)


@pytest.mark.parametrize("sha", ["", "todo", "TBD", "pending", "zzzz", "abc",
                                 "0000000"])
def test_leg6_goes_red_on_a_closure_with_no_commit_behind_it(tmp_path, sha):
    root = _tree(tmp_path, body=GONE_BODY)
    _replacement(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(
            root, [], [_closed(closed_by=sha)], dirs=ONLY)
    assert "is not a commit id" in str(e.value)


def test_leg6_goes_red_when_the_replacement_leg_is_not_in_the_tree(tmp_path):
    root = _tree(tmp_path, body=GONE_BODY)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)
    assert "is not in this tree" in str(e.value)


def test_leg6_goes_red_when_the_replacement_leg_lacks_the_symbol(tmp_path):
    """A path that exists is not a leg. The named symbol has to be in it —
    which proves the leg EXISTS, and the message says plainly that it does not
    prove the leg tests the right thing."""
    root = _tree(tmp_path, body=GONE_BODY)
    _replacement(tmp_path, body="# nothing here yet\n")
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)
    msg = str(e.value)
    assert "does not contain `leg_2_shard_guard`" in msg
    assert "cannot check" in msg, (
        "the leg must state its own limit rather than imply it verified the "
        "replacement works")


def test_leg6_goes_red_when_an_entry_is_open_and_closed_at_once(tmp_path):
    root = _tree(tmp_path)
    _replacement(tmp_path)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(
            root, [_entry()], [_closed()], dirs=ONLY)
    assert "at the same time" in str(e.value)


def test_a_resurrection_is_not_hidden_under_the_by_design_red(tmp_path):
    """Why resurrection lives in leg 6 and not leg 2. Leg 2 is red by design;
    a real failure arriving inside a permanent red is the I4 hole. With the
    entry closed, leg 2 is GREEN for it — so if leg 2 owned this check, a
    revert would be invisible."""
    root = _tree(tmp_path, body=CLEAN)      # the tape is back
    _replacement(tmp_path)
    assert "no live tape is left" in tg.leg_2_tape_expires(root, [], dirs=ONLY)
    with pytest.raises(tg.LegFailed):
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=ONLY)


def test_i4_a_resurrection_is_exit_2_and_named_in_the_fingerprint():
    res = _res((1, False, True), (2, True, False), (3, False, True),
               (4, False, True), (5, False, True), (6, False, False))
    assert tg.verdict(res) == 2, "a resurrection must not exit as the steady state"
    assert tg.fingerprint(res) == "RED LEGS: 2 (by design), 6"


# --- leg 1: a closed entry claims no marker line --------------------------
def test_a_left_behind_tape_comment_is_an_orphan_after_closure(tmp_path):
    """The second half of "what proves a piece of tape is closed": the text
    gone AND the marker gone. A closed entry claims NO marker line, so a
    comment left at the old site lands as an unregistered marker — the same
    red as tape that shipped with no expiry at all."""
    body = ('def decide(line):\n'
            '    """TAPE (HARNESS-LAWS.md Law 2): tracked by '
            'overnight/tape_gate.py."""\n    return False\n')
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [], dirs=ONLY,
                                        closed=[_closed()])
    assert "has never heard of" in str(e.value)


def test_leg1_stale_message_now_names_a_road_that_exists(tmp_path):
    """The finding this diff is for. Leg 1's instruction used to end in "lower
    AUDIT_UNDECLARED_COUNT", which leg 4 made impossible — every road red. It
    has to name CLOSED_TAPE, and it has to say the count stays put."""
    root = _tree(tmp_path, body=GONE_BODY)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [_entry()], dirs=ONLY)
    msg = str(e.value)
    assert "CLOSED_TAPE" in msg
    assert "leave AUDIT_UNDECLARED" in msg
    assert "lower AUDIT_UNDECLARED_COUNT" not in msg.replace(
        '"lower AUDIT_UNDECLARED_COUNT"', "")


# --- leg 3: the named census survives closure -----------------------------
def test_leg3_still_knows_a_closed_item_by_name(tmp_path):
    """The property that makes leg 3 unsatisfiable by silence is that the
    audited symbols are written down. Closing one must not delete the name —
    it must move it."""
    root = _tree(tmp_path, body=GONE_BODY)
    detail = tg.leg_3_audited_five(root, [], census_ids=(99,), dirs=ONLY,
                                   closed=[_closed()])
    assert "all 1 audited pieces accounted for" in detail
    assert "gone from the tree: foo" in detail


def test_leg3_demands_a_marker_again_when_a_closed_item_resurrects(tmp_path):
    """The second, independent catch on a revert: a resurrected entry is no
    longer GONE, so leg 3 asks for its `TAPE:` comment back."""
    body = CLEAN.replace("TAPE (HARNESS-LAWS.md Law 2):", "NOTE:")
    root = _tree(tmp_path, body=body)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_3_audited_five(root, [], census_ids=(99,), dirs=ONLY,
                              closed=[_closed()])
    assert "NO `TAPE:` comment at all" in str(e.value)


def test_closing_cannot_shrink_the_named_census(tmp_path):
    """Directly: the count leg 3 prints is the same before and after."""
    a, b = tmp_path / "a", tmp_path / "b"
    live = tg.leg_3_audited_five(_tree(a, body=CLEAN), [_entry()],
                                 census_ids=(99,), dirs=ONLY, closed=[])
    shut = tg.leg_3_audited_five(_tree(b, body=GONE_BODY), [],
                                 census_ids=(99,), dirs=ONLY,
                                 closed=[_closed()])
    assert "all 1 audited pieces" in live and "all 1 audited pieces" in shut


# --- leg 4: the partition -------------------------------------------------
def test_leg4_counts_both_registers_against_the_dated_number(tmp_path,
                                                             monkeypatch):
    root = _tree(tmp_path)
    _audit(tmp_path, CLOSED_AUDIT.replace("| **1** |", "| **2** |"))
    _pin_census(monkeypatch, ids=(98, 99), n=2)
    detail = tg.leg_4_census_intact(
        root, registry=[_entry(audit_item=98)], closed=[_closed(audit_item=99)])
    assert "2 audited items: 1 open, 1 closed" in detail


def test_leg4_goes_red_when_an_item_is_in_both_registers(tmp_path,
                                                         monkeypatch):
    """Closing is a MOVE, not a copy. A copy is red in leg 2 and green in
    leg 6 at the same time, and counted twice by the census."""
    root = _tree(tmp_path)
    _audit(tmp_path, CLOSED_AUDIT)
    _pin_census(monkeypatch)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root, registry=[_entry()], closed=[_closed()])
    msg = str(e.value)
    assert "in BOTH" in msg
    assert "dropped or renumbered" not in msg, (
        "a duplicate must not print the diagnosis for the opposite mistake")


def test_leg4_message_points_at_the_closed_register(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    _audit(tmp_path, CLOSED_AUDIT)
    _pin_census(monkeypatch)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_4_census_intact(root, registry=[], closed=[])
    assert "CLOSED_TAPE" in str(e.value)


# --- leg 5: the human book records the closure ---------------------------
def test_leg5_goes_red_when_a_closed_bullet_is_still_standing(tmp_path):
    """The machine book says gone, the human book says standing. The next
    agent believes the human book — that is how "tracked by leg 4" survived
    four months."""
    root = _tree(tmp_path, ledger=LEDGER)   # bullet never moved
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [], closed=[_closed()])
    assert "still listed as standing" in str(e.value)


def test_leg5_goes_red_when_there_is_no_retired_section(tmp_path):
    root = _tree(tmp_path, ledger=LEDGER.replace(
        "- `[tape:foo]` the `_FOO_RE` word list in brain/organ.py.\n", ""))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [], closed=[_closed()])
    assert "no `## Retired tape` section" in str(e.value)


def test_leg5_goes_red_when_the_retired_bullet_omits_the_commit(tmp_path):
    root = _tree(tmp_path, ledger=LEDGER_RETIRED.replace("`abc1234`", "a diff"))
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [], closed=[_closed()])
    assert "does not name the closing commit" in str(e.value)


def test_leg5_goes_red_on_a_retired_bullet_with_no_entry(tmp_path):
    """Both directions here too. A bullet claiming retirement with nothing
    checking it is the standing-ledger bug one section down."""
    root = _tree(tmp_path, ledger=LEDGER_RETIRED)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [], closed=[])
    assert "has never heard of" in str(e.value)


def test_leg5_retired_must_be_a_top_level_section(tmp_path):
    """A "Retired tape" written as a SUBSECTION leaves every retired bullet
    inside the standing section, so the human book still reads "standing" for
    something the machine book calls gone. One level, one section."""
    nested = LEDGER_RETIRED.replace("## Retired tape", "### Retired tape")
    root = _tree(tmp_path, ledger=nested)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_5_ledger_agrees(root, [], closed=[_closed()])
    assert "still listed as standing" in str(e.value)


def test_leg5_is_green_when_the_bullet_actually_moved(tmp_path):
    root = _tree(tmp_path, ledger=LEDGER_RETIRED)
    detail = tg.leg_5_ledger_agrees(root, [], closed=[_closed()])
    assert "0 standing and 1 retired" in detail


# --- structure ------------------------------------------------------------
def test_a_closed_entry_carries_the_live_entry_verbatim():
    """The closure cannot quietly carry a different needle than the entry it
    replaced, because there is only one needle: ClosedTape wraps the Tape and
    delegates. Retyping an entry into a new shape is the softened predicate
    this whole file exists to make expensive."""
    live = _entry()
    shut = tg.ClosedTape(live, closed_by="abc1234",
                         replaced_by="x", proves="y", note="z")
    for attr in ("id", "rel", "find", "home", "marker_home", "audit_item",
                 "ledger_needle"):
        assert getattr(shut, attr) == getattr(live, attr)
    assert shut.tape is live


def test_the_real_closed_register_holds_up():
    """Empty today. This is written so it keeps working the day it is not:
    every real closure must pass its own leg against the real tree."""
    detail = tg.leg_6_closed_tape_stays_closed(ROOT)
    assert detail
    assert not (set(t.id for t in tg.KNOWN_TAPE)
                & set(c.id for c in tg.CLOSED_TAPE))


def test_a_closed_entry_is_still_red_in_leg_2_if_it_is_put_back(tmp_path):
    """Moving an entry BACK to KNOWN_TAPE after a resurrection has to restore
    the original polarity — leg 6's message tells you to, so the road it names
    must work."""
    root = _tree(tmp_path, body=CLEAN)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_2_tape_expires(root, [_entry()], dirs=ONLY)
    assert "still load-bearing" in str(e.value)


def test_leg6_is_the_only_watcher_of_a_closure_outside_the_audited_five(
        tmp_path):
    """Legs 3 and 4 only know the audited five. A piece of tape registered
    later — not one of the 2026-08-24 items — has `audit_item=None`, and then
    leg 6 is the ONLY thing standing between a revert and silence. Driven both
    ways so the leg is not load-bearing on paper only."""
    shut = [_closed(audit_item=None)]

    ok = _tree(tmp_path / "gone", body=GONE_BODY)
    _replacement(tmp_path / "gone")
    assert "still gone from" in tg.leg_6_closed_tape_stays_closed(
        ok, [], shut, dirs=ONLY)
    assert "accounted for" in tg.leg_3_audited_five(
        ok, [], census_ids=(99,), dirs=ONLY, closed=shut)

    back = _tree(tmp_path / "back", body=CLEAN)
    _replacement(tmp_path / "back")
    # leg 3 has nothing to say: the item is not in the census.
    assert "accounted for" in tg.leg_3_audited_five(
        back, [], census_ids=(99,), dirs=ONLY, closed=shut)
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(back, [], shut, dirs=ONLY)
    assert "RESURRECTION" in str(e.value)


def test_softening_a_needle_at_closure_still_orphans_the_marker(tmp_path):
    """The residual attack, and the half of it that IS caught. Close the entry
    with a `find` the tree never held — leg 6 reads GONE — and the `TAPE:`
    comment left in the code has nobody claiming it, so leg 1 reports it as a
    marker with no expiry. Evading BOTH means deleting a Law-2 marker from
    shipped code in the same diff, which reduces to the blind spot this gate
    already states out loud: tape nobody marked."""
    root = _tree(tmp_path, body=CLEAN)              # the tape never left
    _replacement(tmp_path)
    weak = _closed(find="_FOO_RE = re.compile_NOTHING(")
    assert "still gone from" in tg.leg_6_closed_tape_stays_closed(
        root, [], [weak], dirs=ONLY), "the softened needle does match nothing"
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_1_markers_are_registered(root, [], dirs=ONLY, closed=[weak])
    assert "has never heard of" in str(e.value)


def test_leg6_refuses_an_empty_scan_scope(tmp_path):
    """The fail-open in my own leg, found before it shipped: `sites_anywhere`
    over no organs returns nothing, nothing reads as GONE, and every closed
    entry goes green having opened zero files. scan_reach() does not catch it —
    an empty scope has no missing organ, no hollow one and no unclassified
    file. Twenty fail-open rules were found in this repo the night this was
    written, several inside gates built to catch exactly that."""
    root = _tree(tmp_path, body=CLEAN)          # the tape is right there
    _replacement(tmp_path)
    assert tg.sites_anywhere(root, "_FOO_RE = re.compile(", ()) == []
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_6_closed_tape_stays_closed(root, [], [_closed()], dirs=())
    assert "EMPTY set of shipped organs" in str(e.value)
