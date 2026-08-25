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
import json
from pathlib import Path

import pytest

from brain import memory as memory_module
from brain.memory import Memory, _DONE_RE, _extractor_verdict

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


# The payload that makes the guard OBSERVABLE. The test above cannot see it:
# its reply carries none of the extraction keys, so deleting `if by is None:
# return` changes nothing about the result and the check passes either way —
# caught by mutation, Law 6. What a non-live transport can actually put on the
# wire is anything at all, this included, and a body this rich is exactly what
# a "heuristic" mode must still not be allowed to write.
FULL_EXTRACTION = json.dumps({
    "people": ["Kowalski", "Sarah"], "places": ["the Ritz"],
    "topics": ["reservation"], "commitment": "send the deck",
    "commitment_to": "Sarah", "completed": None})

# Every mode that is not a live endpoint, not just the one in the field
# report. "heuristic" is llm.py's keyless engine; "" and None are a transport
# that never said; the last is a build nobody here has seen. The class is
# "nobody looked", and closing one instance of it is how the next one ships.
NO_VERDICT_MODES = ["heuristic", "", "some-future-transport"]


@pytest.mark.parametrize("mode", NO_VERDICT_MODES)
def test_no_endpoint_that_never_looked_may_write_the_graph(mode):
    m = Memory(":memory:", llm=_Answers(FULL_EXTRACTION, mode=mode))
    mem = m.ingest(GUEST_LINE, speaker="owner")
    assert mem["extracted_by"] is None, \
        f"mode {mode!r} is being reported as a model verdict"
    assert mem["commitment"] is None
    assert mem["commitment_id"] is None
    assert mem["entities"] == []
    assert list(m.db.execute("SELECT type, name FROM nodes")) == [], \
        f"mode {mode!r} minted graph nodes nobody read the line for"
    assert list(m.db.execute("SELECT rel FROM edges")) == []
    assert m.open_loops() == []


def test_a_transport_that_never_said_which_endpoint_answered_writes_nothing():
    """`mode` missing entirely — a double, an old build, a stubbed client.
    `getattr(res, "mode", None)` is what reads it, so absence must land in the
    same no-verdict state as a wrong value."""
    class _Mute:
        text = FULL_EXTRACTION

        def chat(self, system, user, temperature=0.1, **kw):
            return self

    m = Memory(":memory:", llm=_Mute())
    mem = m.ingest(GUEST_LINE, speaker="owner")
    assert mem["extracted_by"] is None
    assert mem["entities"] == []
    assert list(m.db.execute("SELECT type, name FROM nodes")) == []


def test_a_refusal_under_a_live_mode_is_not_an_empty_line(capsys):
    """`_extract_json` SYNTHESISES the literal "{}" when a reply has no braces
    in it, and "{}" parses. So a refusal or an outage page arrived as "nothing
    in this line" — with a live key, and stamped as a real verdict."""
    llm = _Answers("I'm sorry, I can't help with that.", mode="openrouter")
    mem = Memory(":memory:", llm=llm).ingest(GUEST_LINE)
    assert mem["extracted_by"] is None, \
        "a provider refusal is being reported as a model verdict"
    # The print was unpinned until 2026-08-25 — deleting it left the suite
    # green, and with `extracted_by` not yet read by anything it is the ONLY
    # live evidence that a provider is refusing or serving an outage page.
    assert "answered with no JSON" in capsys.readouterr().out, \
        "a week of provider refusals must not look like a week of quiet days"


def test_a_reply_that_is_not_readable_json_is_reported(capsys):
    """Braces present, JSON invalid — a truncated stream, a proxy's error
    body. It reports, like every other path that writes nothing."""
    mem = Memory(":memory:", llm=_Answers("{oops}", mode="openrouter")).ingest(
        GUEST_LINE)
    assert mem["extracted_by"] is None
    assert "unreadable" in capsys.readouterr().out


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


# ----------------------- the half that stayed silent is the half that fires


# Every transport that produces NO VERDICT, and the words its report must
# carry. Two of these said nothing at all until 2026-08-25 — `not self.llm`,
# which is the DEPLOYED DEFAULT on a keyless worker, and a non-live `mode`,
# which is what an eval built without a key gets — so the two paths that
# actually run were the two that could not be told from a quiet day. The
# stamp alone does not close that: `extracted_by` has no consumer in the tree
# yet, so until the worker half lands the log IS the evidence.
NO_VERDICT_TRANSPORTS = [
    ("no model at all", lambda: None, "no extraction model configured"),
    ("a keyless transport", lambda: _Answers(FULL_EXTRACTION, mode="heuristic"),
     "not a live extraction model"),
    ("an endpoint nobody here has seen",
     lambda: _Answers(FULL_EXTRACTION, mode="some-future-transport"),
     "not a live extraction model"),
    ("a model that raises", _Raises, "extraction model unusable"),
    ("a refusal in prose",
     lambda: _Answers("I'm sorry, I can't help with that.", mode="openrouter"),
     "answered with no JSON"),
    ("an unreadable reply", lambda: _Answers("{oops}", mode="openrouter"),
     "unreadable"),
]


@pytest.mark.parametrize("shape,build,expected", NO_VERDICT_TRANSPORTS,
                         ids=[s for s, _, _ in NO_VERDICT_TRANSPORTS])
def test_no_path_that_writes_nothing_stays_quiet_about_it(shape, build,
                                                          expected, capsys):
    mem = Memory(":memory:", llm=build()).ingest(GUEST_LINE, speaker="owner")
    assert mem["extracted_by"] is None
    out = capsys.readouterr().out
    assert expected in out, f"{shape} wrote nothing and said nothing: {out!r}"
    assert "unread" in out


def test_a_configuration_fact_is_said_once_per_librarian(capsys):
    """`self.llm is None` is fixed at construction — it cannot change while
    this Memory lives, so reporting it per line would be log spam, and log
    spam is what gets "cleaned up" the week before it was needed. Once per
    store, and a new store says it again."""
    m = Memory(":memory:")
    m.ingest(GUEST_LINE)
    assert "no extraction model configured" in capsys.readouterr().out
    m.ingest(NAMED_LINE)
    assert capsys.readouterr().out == "", "the same fixed fact, said twice"
    Memory(":memory:").ingest(GUEST_LINE)
    assert "no extraction model configured" in capsys.readouterr().out


def test_a_transport_failure_is_said_every_time(capsys):
    """The opposite call, for the opposite kind of fact: a raise, a refusal or
    an unreadable reply is a per-reply EVENT, and three outages in a day must
    read as three, not as one."""
    m = Memory(":memory:", llm=_Raises())
    m.ingest(GUEST_LINE)
    assert "extraction model unusable" in capsys.readouterr().out
    m.ingest(NAMED_LINE)
    assert "extraction model unusable" in capsys.readouterr().out


def test_every_no_verdict_exit_goes_through_the_reporting_door():
    """The class, not the six instances above: a no-verdict path added
    tomorrow must not be able to be silent. `return Extraction(), None`
    written by hand is exactly how the two silent ones got there, so it is
    the shape that is banned — `_unread()` is the only door out."""
    src = (Path(__file__).resolve().parent.parent / "brain"
           / "memory.py").read_text()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "_extract")
    bare = [ast.unparse(n) for n in ast.walk(fn)
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)
            and len(n.value.elts) == 2
            and isinstance(n.value.elts[1], ast.Constant)
            and n.value.elts[1].value is None]
    assert bare == [], \
        f"a no-verdict exit that reports nothing: {bare}"


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


# ------------------------------- a verdict returned is not a verdict USED


PROMISE = "I'll send Sarah the pitch deck tomorrow."
# Deliberately outside _DONE_RE: no "already/just <verb>", no "<verb> it/that",
# no "that's done", no "I sent". The verb list cannot close a loop on this
# sentence, so if the loop closes, the MODEL closed it.
REPORT = "Sarah has the pitch deck now, so that whole thread is behind us."


def test_the_report_line_is_beyond_the_verb_list():
    """Guards the guard: the moment _DONE_RE could match this sentence, the
    test below would pass without the model verdict ever being read."""
    assert not _DONE_RE.search(REPORT)


def test_the_models_completed_verdict_is_used_at_the_ingest_layer():
    """`ingest` passes `ex.completed` into close_from_speech. Dropping that
    argument left the whole suite green (mutation, 2026-08-25) — and it
    silently reverts loop-closing to the _DONE_RE verb list alone, which is
    the regression the code's own comment says was fixed: anything the owner
    finished in words that list does not contain stays open forever, and the
    clock nags him about work that is done."""
    llm = FakeExtractor(per_line={
        PROMISE: {"people": ["Sarah"], "commitment": "send Sarah the deck"},
        REPORT: {"completed": "sent Sarah the deck"},
    })
    m = Memory(":memory:", llm=llm)
    m.ingest(PROMISE, speaker="owner")
    assert [loop["what"] for loop in m.open_loops()] == ["send Sarah the deck"]

    mem = m.ingest(REPORT, speaker="owner")
    assert mem["closed"] == ["send Sarah the deck"], \
        "the model said he finished it and the promise stayed open"
    assert m.open_loops() == []


def test_no_verdict_does_not_close_a_promise_by_itself():
    """The other half: with nobody reading the line, `completed` is None and
    the sentence above closes nothing. (What _DONE_RE can still do on its own
    is audit item 41, a separate site with the opposite polarity — closing
    suppresses an action rather than authorising one.)"""
    llm = FakeExtractor(per_line={
        PROMISE: {"people": ["Sarah"], "commitment": "send Sarah the deck"}})
    m = Memory(":memory:", llm=llm)
    m.ingest(PROMISE, speaker="owner")
    m.llm = None  # the key expired mid-day; the promise outlives it
    mem = m.ingest(REPORT, speaker="owner")
    assert mem["closed"] == []
    assert [loop["what"] for loop in m.open_loops()] == ["send Sarah the deck"]
