"""A fact that changes only in its NUMBER must update, not silently merge.

The failure: the candidate sift (now _relate_fact) dropped every token
of two characters or fewer
before comparing, so "dinner with Sarah at 6" and "dinner with Sarah at 8"
compared as identical (overlap 1.00) and merged. _merge_fact deliberately
keeps the original wording, so the 8 was discarded and the profile went on
saying 6. Times, party sizes and counts are exactly the details worth
updating, and they were the only kind guaranteed to be lost.
"""
import tempfile, os, pytest
from brain.memory import Memory, _fact_numbers


@pytest.fixture
def mem():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    m = Memory(path=path, llm=None)
    yield m
    try: os.unlink(path)
    except OSError: pass


def _facts(m):
    return [r[0] for r in m.db.execute("SELECT fact FROM profile_facts").fetchall()]


def test_numbers_are_never_dropped_from_comparison():
    assert _fact_numbers("dinner with Sarah at 6") == {"6"}
    assert _fact_numbers("dinner with Sarah at 6") != _fact_numbers("dinner with Sarah at 8")
    assert _fact_numbers("table for 2 at 7:30") == {"2", "7:30"}


def test_a_moved_dinner_updates_the_time(mem):
    mem.remember_fact("dinner with Sarah at 6", importance=3)
    mem.remember_fact("dinner with Sarah at 8", importance=3)
    facts = _facts(mem)
    assert len(facts) == 1, f"should stay one fact, got {facts}"
    assert "8" in facts[0], f"the NEW time must win, profile says: {facts[0]!r}"
    assert "6" not in facts[0], f"the stale time must be gone, profile says: {facts[0]!r}"


def test_a_plain_restatement_still_merges_without_churn(mem):
    mem.remember_fact("dinner with Sarah at 8", importance=3)
    mem.remember_fact("dinner with Sarah at 8", importance=3)
    assert len(_facts(mem)) == 1


def test_genuinely_different_facts_stay_separate(mem):
    mem.remember_fact("dinner with Sarah at 8", importance=3)
    mem.remember_fact("dentist appointment on the 12th", importance=3)
    assert len(_facts(mem)) == 2


def test_party_size_change_is_kept(mem):
    mem.remember_fact("table for 2 at Earls", importance=3)
    mem.remember_fact("table for 4 at Earls", importance=3)
    facts = _facts(mem)
    assert len(facts) == 1 and "4" in facts[0], facts


# --- consolidation must never be wedged permanently by one bad batch --------

class _BadLLM:
    """A model that cannot produce usable output for this batch, ever."""
    def __init__(self): self.calls = 0
    def chat(self, *a, **k):
        self.calls += 1
        class R: text = "I'm sorry, I can't summarise those."
        return R()


def test_one_poisonous_batch_does_not_freeze_the_profile_forever(mem):
    """Cursor only advanced on success, so a batch the model could never
    parse was re-read every night and NOTHING after it was ever consolidated.
    Three strikes and the batch is stepped over, loudly."""
    mem.llm = _BadLLM()
    for i in range(5):
        mem.ingest(f"episode number {i}")

    start = int(mem._state_get("last_episode_id", "0") or 0)
    r1 = mem.consolidate(now=1000.0)
    r2 = mem.consolidate(now=1001.0)
    assert r1["ran"] is False and r2["ran"] is False
    assert int(mem._state_get("last_episode_id", "0") or 0) == start, \
        "must not skip before three strikes"

    r3 = mem.consolidate(now=1002.0)
    assert r3["ran"] is True, "the third failure must step over the batch"
    assert "skipped_batch" in r3
    moved = int(mem._state_get("last_episode_id", "0") or 0)
    assert moved > start, "the cursor must advance past the poisonous batch"


def test_a_batch_that_succeeds_clears_its_strikes(mem):
    mem.llm = _BadLLM()
    for i in range(3):
        mem.ingest(f"episode {i}")
    last = int(mem._state_get("last_episode_id", "0") or 0)
    mem.consolidate(now=1000.0)
    assert mem._state_get(f"consolidate_fail_{last}") == "1"

    class _GoodLLM:
        def chat(self, *a, **k):
            class R: text = '{"facts": [{"fact": "he runs in the morning", "importance": 3, "episode_ids": []}]}'
            return R()
    mem.llm = _GoodLLM()
    out = mem.consolidate(now=1003.0)
    assert out["ran"] is True
    assert mem._state_get(f"consolidate_fail_{last}") == "0"


# --- the model's "completed" verdict must actually be read -----------------

def test_completed_is_carried_from_the_model(mem):
    """EXTRACT_SYSTEM asks for `completed`, the dataclass declares it and
    ingest acts on it — but the LLM branch built Extraction without it, so
    with a live model it was always None and loop-closing fell back to a
    fixed verb list."""
    class _LLM:
        def chat(self, *a, **k):
            class R:
                # `mode` is what says an endpoint actually ANSWERED. A double
                # that omits it is standing in for a transport that never
                # looked, and _extract now reads it before parsing a byte.
                mode = "openrouter"
                text = ('{"people":["Priya"],"places":[],"topics":["launch"],'
                        '"commitment":null,"commitment_to":null,'
                        '"completed":"sent Priya the launch plan"}')
            return R()
    mem.llm = _LLM()
    ex, by = mem._extract("just sent Priya the launch plan")
    assert by == "model"
    assert ex.completed == "sent Priya the launch plan", \
        f"the model's completed verdict was dropped: {ex!r}"


def test_a_broken_extraction_model_is_reported_not_silent(mem, capsys):
    """It used to say "falling back to rules", and it did fall back to one:
    a capitalisation regex that decided who a person was and who a promise
    was made to. The rules are deleted, so the report can no longer name
    them — but it must still be a report. Silence here is the whole disease:
    a degraded brain looked exactly like a quiet day."""
    class _Boom:
        def chat(self, *a, **k):
            raise RuntimeError("upstream 502")
    mem.llm = _Boom()
    ex, by = mem._extract("dinner with Sarah at 8")
    out = capsys.readouterr().out
    assert "extraction model unusable" in out, \
        "a degraded brain must not look identical to a quiet day"
    assert by is None, "a model that raised has said nothing about this line"
    assert (ex.people, ex.commitment, ex.commitment_to) == ([], None, None), \
        "no verdict must write no people and no promise"
