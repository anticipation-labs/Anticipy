"""NO VERDICT IS NOT AN EMPTY LINE — the honesty wall at the library door.

`Memory._extract` had four paths, not the two its shape suggested, and two of
them were silent:

    a  self.llm is None          -> the regex, for every line, forever, mute
    b  live model, JSON parses   -> the model's verdict
    c  live model RAISES         -> one print, then the regex
    d  an LLM object that is NOT live -> LLM.chat returns the TRIAGE
       heuristic's JSON (brain/llm.py:285). It is valid JSON from a different
       prompt, so json.loads succeeds, every key _extract wants is missing,
       and an empty Extraction came back as though a model had read the line
       and found nothing in it. No exception, no print, no fallback.

Path (a) is not a test rig, it is the deployed default when the key is
missing: brain/worker.py:3500 hands memory `llm if llm.live else None`, read
once at process start. A worker that boots keyless ran a regex over every line
of the owner's life and said nothing about it even once.

What the regex decided is HARNESS-LAW 1's forbidden question. A capitalised
word was a PERSON. An "I'll ..." clause was the PROMISE. And `people[0]` — the
first capitalised word in the sentence — was WHO IT HAD BEEN PROMISED TO. The
recorded failure this whole laws file exists for is "one invented human being"
(HARNESS-LAWS.md, the Tejas call); a guard whose failure mode is the product's
signature failure is not a stopgap, which is why this was fixed rather than
registered (spec section 2).

So: the extractor now returns a verdict or NO VERDICT, the way `_horizon`,
`_fact_kind` and `_speaker_verdict` already do in this same file. Minting a
commitment is what authorises the clock to raise an errand at the owner — a
FLOOR — and Law 1 says a floor must refuse without a verdict or it lifts
itself. No verdict therefore writes nothing.

Half of these tests are about the difference the whole thing turns on:
"the model read this line and found nothing in it" and "nobody looked at this
line" are different facts, they arrive as the same empty Extraction, and the
store has to keep them apart.

Spec: docs/superpowers/specs/2026-08-25-library-law-clean.md
Audit: research/2026-08-24-law1-audit.md item 43 (VIOLATION, severity H).
"""
import ast
from pathlib import Path

from brain import memory as memory_module
from brain.memory import Memory, _extractor_verdict

from llm_fakes import FakeExtractor

GUEST_LINE = "I'll send you the pitch deck tomorrow morning."
NAMED_LINE = "I'll send Sarah the pitch deck tomorrow."
OVERHEARD = "The reservation should be under the name Kowalski, obviously."


class _Answers:
    """A transport double: one canned reply, and the `mode` that says WHICH
    ENDPOINT produced it. Nothing here reads the owner's words."""

    def __init__(self, text: str, mode: str = "openrouter"):
        self.text, self.mode = text, mode
        self.used_model = "double"

    def chat(self, system, user, temperature=0.1, **kw):
        return self


class _Raises:
    def __init__(self, exc=None):
        self.exc = exc or RuntimeError("503 upstream")

    def chat(self, system, user, temperature=0.1, **kw):
        raise self.exc


# ------------------------------------------------------- the pattern is gone


def test_the_pattern_extractor_and_its_three_patterns_are_gone():
    """Deleted, not improved. A regex that is merely narrowed still answers
    the question Law 1 says a model owns."""
    for name in ("_rule_extract", "_COMMIT_RE", "_NAME_RE", "_NOT_NAMES"):
        assert not hasattr(memory_module, name), (
            f"brain/memory.py still carries {name}: the extraction question "
            f"is still being answered by a pattern when no model answers")


def test_brain_never_imports_the_test_double():
    """The named way this fix dies (spec section 9): the 39 fixture tests get
    "repaired" by a deterministic extractor that brain/ then imports back for
    convenience. Same decision, different name — and no gate can catch it,
    so this test is the gate."""
    brain = Path(__file__).resolve().parent.parent / "brain"
    offenders = []
    for path in sorted(brain.glob("*.py")):
        # Parsed, not grepped: memory.py's own comment explains where the
        # double went and why, and a substring check would convict it for
        # saying so. What is forbidden is the IMPORT.
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            if any("llm_fakes" in n or "FakeExtractor" in n for n in names):
                offenders.append(path.name)
    assert offenders == [], \
        f"the shipped tree imports the test extractor: {offenders}"


# ------------------------------------------------------- the verdict function


def test_only_a_live_endpoint_is_a_verdict():
    """`mode` is the transport's own report of which endpoint answered
    (brain/llm.py:149), set by which branch of `chat` returned. It is never
    read off the owner's words."""
    assert _extractor_verdict("gemini") == "model"
    assert _extractor_verdict("openrouter") == "model"


def test_the_keyless_heuristic_is_no_verdict():
    """brain/llm.py:285. With no key `chat` does not raise — it answers with
    the TRIAGE heuristic's JSON, from a different prompt entirely."""
    assert _extractor_verdict("heuristic") is None


def test_an_unknown_or_missing_mode_is_no_verdict():
    """A build nobody here has seen, or a double that never said. Neither is
    healthy, and neither may read as healthy."""
    assert _extractor_verdict(None) is None
    assert _extractor_verdict("") is None
    assert _extractor_verdict("some-future-transport") is None


# --------------------------------------------------- path (a): no llm at all


def test_a_promise_nobody_read_is_never_written():
    m = Memory(":memory:")
    mem = m.ingest(GUEST_LINE, speaker="other")
    assert mem["commitment"] is None
    assert mem["commitment_id"] is None
    assert m.open_loops() == [], \
        "a promise was minted that no model ever read"


def test_no_verdict_is_reported_as_no_verdict():
    m = Memory(":memory:")
    assert m.ingest(GUEST_LINE)["extracted_by"] is None


def test_a_capitalised_word_does_not_become_a_person():
    """`_NAME_RE` made "Kowalski" a permanent person node off one overheard
    booking line."""
    m = Memory(":memory:")
    mem = m.ingest(OVERHEARD, speaker="other")
    assert mem["entities"] == [], \
        f"a pattern is still minting graph nodes: {mem['entities']}"
    rows = m.db.execute("SELECT type, name FROM nodes").fetchall()
    assert list(rows) == [], f"nodes written with no verdict behind them: {rows}"


def test_the_first_capitalised_word_is_not_who_a_promise_was_made_to():
    """`commitment_to = people[0]` — the worst line of the four. It did not
    degrade the graph, it FABRICATED in it: a promise attributed to whichever
    capitalised word came first."""
    m = Memory(":memory:")
    m.ingest(NAMED_LINE, speaker="owner")
    edges = m.db.execute(
        "SELECT rel FROM edges WHERE rel = 'committed_to'").fetchall()
    assert list(edges) == [], \
        "a promise is still being attributed to a person by capitalisation"


# ------------------------------------- path (d): a transport that never looked


def test_the_triage_heuristics_reply_is_not_an_extraction():
    """The silent path. Valid JSON, from the wrong prompt, parsed as though a
    model had read the line and found it empty."""
    llm = _Answers('{"decision": "ignore", "goal": null, "reason": "..."}',
                   mode="heuristic")
    mem = Memory(":memory:", llm=llm).ingest(GUEST_LINE)
    assert mem["extracted_by"] is None
    assert mem["commitment"] is None
    assert mem["entities"] == []


def test_a_refusal_under_a_live_mode_is_not_an_empty_line():
    """`_extract_json` SYNTHESISES the literal "{}" when a reply has no braces
    in it, and "{}" parses. So a refusal or an outage page arrived as "nothing
    in this line" — with a live key, and stamped as a real verdict."""
    llm = _Answers("I'm sorry, I can't help with that.", mode="openrouter")
    mem = Memory(":memory:", llm=llm).ingest(GUEST_LINE)
    assert mem["extracted_by"] is None, \
        "a provider refusal is being reported as a model verdict"


# ------------------------------------------------- path (c): a raising model


def test_a_model_that_raises_leaves_no_verdict_and_no_promise(capsys):
    m = Memory(":memory:", llm=_Raises())
    mem = m.ingest(GUEST_LINE, speaker="owner")
    assert mem["extracted_by"] is None
    assert m.open_loops() == []
    assert "extraction model unusable" in capsys.readouterr().out, \
        "the one path that used to report itself must keep reporting itself"


def test_the_report_no_longer_claims_a_fallback_that_does_not_exist(capsys):
    """It used to end "falling back to rules". There are no rules to fall back
    to, and a log line that names a mechanism the tree does not have is how
    the last agent's comment excused a live regression."""
    Memory(":memory:", llm=_Raises()).ingest(GUEST_LINE)
    assert "falling back to rules" not in capsys.readouterr().out


# --------------------------------------------------- path (b): a real verdict


def test_a_model_that_read_the_line_and_found_nothing_IS_a_verdict():
    """The distinction the stamp exists for. Same empty Extraction as every
    test above; a completely different fact about the day."""
    llm = _Answers("{}", mode="openrouter")
    mem = Memory(":memory:", llm=llm).ingest(GUEST_LINE)
    assert mem["extracted_by"] == "model", \
        "a model DID read this line; 'quiet' and 'degraded' just collapsed"
    assert mem["commitment"] is None
    assert mem["entities"] == []


def test_a_model_verdict_writes_the_graph_exactly_as_before():
    llm = FakeExtractor(people=["Sarah"], topics=["pitch deck"],
                        commitment="send Sarah the pitch deck tomorrow",
                        commitment_to="Sarah")
    m = Memory(":memory:", llm=llm)
    mem = m.ingest(NAMED_LINE, speaker="owner")
    assert mem["extracted_by"] == "model"
    assert mem["commitment"] == "send Sarah the pitch deck tomorrow"
    assert sorted(mem["entities"]) == ["Sarah", "pitch deck"]
    loop = m.open_loops()[0]
    assert loop["what"] == "send Sarah the pitch deck tomorrow"
    assert loop["speaker"] == "owner"


def test_a_gemini_verdict_counts_too():
    llm = _Answers('{"commitment": "book the table"}', mode="gemini")
    assert Memory(":memory:", llm=llm).ingest(
        GUEST_LINE)["extracted_by"] == "model"


# ------------------------------------------------------- what is NOT lost


def test_an_extraction_outage_never_costs_the_words():
    """The episode is inserted BEFORE _extract runs and the FTS trigger fires
    on that insert, so recall over what was actually said keeps working
    through a total extraction outage. What is lost is the derived graph, and
    that loss is the point: an edge is a claim, and a claim with no verdict
    behind it is what Law 1 forbids."""
    m = Memory(":memory:")
    mem = m.ingest(NAMED_LINE, speaker="owner")
    assert mem["episode_id"] is not None
    stored = m.db.execute("SELECT text FROM episodes").fetchall()
    assert [r[0] for r in stored] == [NAMED_LINE]
    assert any(NAMED_LINE in (f.get("quote") or f.get("fact") or "")
               for f in m.recall("pitch deck")), \
        "the words themselves must survive a degraded librarian"


def test_ingest_keeps_every_key_it_ever_returned():
    """Nothing is removed, so no caller breaks on a missing key."""
    mem = Memory(":memory:").ingest(GUEST_LINE)
    assert set(mem) == {"episode_id", "entities", "commitment",
                        "commitment_id", "closed", "extracted_by"}
