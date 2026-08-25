"""WHO A PROMISE WAS MADE TO COMES FROM THE MODEL, OR FROM NOBODY.

Audit item 43's worst line was `commitment_to = people[0]` — the first
capitalised word in the sentence became the person a promise had been made to.
It was deleted from `_extract` on 2026-08-25, and an adversarial pass put it
straight back ONE LAYER UP, in `ingest`, on the live path:

    _to = ex.commitment_to or (ex.people[0] if ex.people else None)

The whole suite stayed green. Every test that pins the deleted line runs with
NO llm at all (`tests/test_library_nobody_looked_is_not_nothing_here.py`), so
`ex.people` is empty, and a fabrication that only fires when a model DID
answer is invisible to all of them.

So this file pins the CLASS, not the instance. With a real model verdict in
hand and `commitment_to` null, nothing else the model returned may become the
promisee: not the first person, not the last, not a place, not a topic, not
the commitment's own words. Every one of those is the same fabrication with a
different index.

And a test that merely NOTICES the fabrication is one refactor behind the next
one, so the fence is a type. `Promisee` has exactly one door — `_promisee`,
called on the model's own `commitment_to` field and nowhere else. `Extraction`
refuses to carry a promisee that did not come through it, and `_add_edge`
refuses to write an attribution edge without one. Deriving a promisee from
anything else is not a silently wrong graph any more; it raises.

Law 1 (meaning belongs to a model), Law 6 (the surviving mutation that got
this file written). Audit: research/2026-08-24-law1-audit.md item 43.
"""
import pytest

from brain.memory import Extraction, Memory, Promisee, _promisee

from llm_fakes import FakeExtractor

LINE = "I'll send Sarah the pitch deck tomorrow."


def _attributions(m: Memory) -> list:
    return list(m.db.execute(
        "SELECT n.name FROM edges e JOIN nodes n ON n.id = e.dst "
        "WHERE e.rel = 'committed_to'").fetchall())


# ------------------------------- the class: a promisee the model did not name


# Every shape of "the model answered, and named nobody". The fabrication that
# survived used people[0]; these are its siblings, and one test per index is
# how the next reviewer wins.
NAMED_NOBODY = [
    ("one person", dict(people=["Sarah"])),
    ("several people", dict(people=["Sarah", "Tom"])),
    ("a place", dict(places=["the Ritz"])),
    ("a topic", dict(topics=["pitch deck"])),
    ("everything at once", dict(people=["Sarah", "Tom"], places=["the Ritz"],
                                topics=["pitch deck", "launch"])),
]


@pytest.mark.parametrize("shape,payload",
                         NAMED_NOBODY, ids=[s for s, _ in NAMED_NOBODY])
def test_a_model_that_named_nobody_attributes_the_promise_to_nobody(shape,
                                                                    payload):
    llm = FakeExtractor(commitment="send the pitch deck",
                        commitment_to=None, **payload)
    m = Memory(":memory:", llm=llm)
    mem = m.ingest(LINE, speaker="owner")
    assert mem["extracted_by"] == "model", "the fixture must reach path (b)"
    assert mem["commitment"] == "send the pitch deck"
    assert _attributions(m) == [], (
        f"a promise was attributed to somebody the model never named "
        f"({shape}): {_attributions(m)}")


def test_the_promise_still_involves_everyone_the_model_did_name():
    """The refusal above must cost the graph nothing else — an unattributed
    promise still records who and what it was mentioned with."""
    llm = FakeExtractor(people=["Sarah", "Tom"], topics=["pitch deck"],
                        commitment="send the pitch deck", commitment_to=None)
    m = Memory(":memory:", llm=llm)
    m.ingest(LINE, speaker="owner")
    involves = sorted(r[0] for r in m.db.execute(
        "SELECT n.name FROM edges e JOIN nodes n ON n.id = e.dst "
        "WHERE e.rel = 'involves'").fetchall())
    assert involves == ["Sarah", "Tom", "pitch deck"]


def test_the_model_naming_the_promisee_writes_exactly_one_attribution():
    llm = FakeExtractor(people=["Sarah", "Tom"], topics=["pitch deck"],
                        commitment="send Sarah the pitch deck",
                        commitment_to="Sarah")
    m = Memory(":memory:", llm=llm)
    m.ingest(LINE, speaker="owner")
    assert [r[0] for r in _attributions(m)] == ["Sarah"]


def test_a_promisee_the_model_named_but_never_listed_writes_no_edge():
    """`commitment_to` naming somebody who is in no other field has no node to
    point at. Minting one here would be the graph inventing a person out of a
    single field — the same fabrication, one field over."""
    llm = FakeExtractor(people=["Tom"], commitment="send the deck",
                        commitment_to="Sarah")
    m = Memory(":memory:", llm=llm)
    m.ingest(LINE, speaker="owner")
    assert _attributions(m) == []
    assert sorted(r[0] for r in m.db.execute(
        "SELECT name FROM nodes WHERE type = 'person'").fetchall()) == ["Tom"]


# --------------------------------------------------- the fence is a type


def test_the_only_door_into_promisee_is_the_models_own_field():
    assert _promisee(None) is None
    assert _promisee("") is None
    assert _promisee("   ") is None
    assert _promisee(["Sarah"]) is None, "a list is not a name"
    made = _promisee("Sarah")
    assert isinstance(made, Promisee) and made == "Sarah"


def test_an_extraction_cannot_carry_a_promisee_the_model_did_not_name():
    """A plain string is what every derivation produces — `people[0]`,
    `text.split()[0]`, a cached name. The dataclass will not hold one."""
    with pytest.raises(TypeError):
        Extraction(people=["Sarah"], commitment="send the deck",
                   commitment_to="Sarah")
    ok = Extraction(people=["Sarah"], commitment="send the deck",
                    commitment_to=_promisee("Sarah"))
    assert ok.commitment_to == "Sarah"
    assert Extraction().commitment_to is None


def test_an_attribution_edge_cannot_be_written_without_a_promisee():
    """The lowest writer refuses too, so routing around `_attribute_promise`
    is not an escape either."""
    m = Memory(":memory:")
    with pytest.raises(TypeError):
        m._add_edge(1, "committed_to", 2, 1, 0.0)
    with pytest.raises(TypeError):
        m._add_edge(1, "committed_to", 2, 1, 0.0, promisee="Sarah")
    # Every other relation is unaffected.
    m._add_edge(1, "involves", 2, 1, 0.0)


def test_attributing_a_promise_to_a_derived_name_raises():
    """The exact surviving mutation, at the exact layer it survived at."""
    m = Memory(":memory:")
    with pytest.raises(TypeError):
        m._attribute_promise(1, "Sarah", {"Sarah": 2}, 1, 0.0)
    assert m._attribute_promise(1, None, {"Sarah": 2}, 1, 0.0) is None


def test_a_model_verdict_carries_the_type_all_the_way_through_extract():
    llm = FakeExtractor(people=["Sarah"], commitment="send the deck",
                        commitment_to="Sarah")
    ex, by = Memory(":memory:", llm=llm)._extract(LINE)
    assert by == "model"
    assert isinstance(ex.commitment_to, Promisee)
    ex_none, _ = Memory(":memory:", llm=FakeExtractor(
        people=["Sarah"], commitment="send the deck"))._extract(LINE)
    assert ex_none.commitment_to is None
