"""Volume from a read must never push the owner's own words out of a prompt.

The fence was already right: a read-derived fact reaches a prompt quoted, in a
nonce-delimited block, and is capped at importance 4 because "importance 5 is
reserved for boundaries the owner stated in their own words" (design/day-zero.md
§3). That reasoning accounted for IMPORTANCE and forgot RECENCY.

`Memory.profile_facts` ranks on importance, then belief, then age, and there
is NO provenance term anywhere in it. A supervised read is always the freshest
thing in the store, so a fresh importance-4 mail fact beats the owner's own
importance-5 interview answer the moment that answer is about 30 days old. The
importance gate does not save it: that gate bounds what CONFIDENCE may do, and
this inversion is age. The client's sanctioned ceiling is 15 facts per source
(`extension/supervised_read.js` FACT_CEILING) and `briefing_facts` takes
`profile_facts(limit=10)`. 15 > 10, so ONE HONEST READ — no attacker anywhere
in this — filled the whole briefing window.

Measured on this store before the fix: 2 importance-5 `interview` rows aged 45
days plus 15 fresh importance-4 `supervised_mail` rows made
`profile_facts(limit=10)` return 10/10 `supervised_mail`. `Anticipy.briefing`
then computed `told == []`, handed BRIEFING_SYSTEM an EMPTY profile block, and
the entire profile section of the greeting became `quoted_from_other_people`.
The same inversion starved `memory_notes`: recall returns highest-salience
first, the untrusted run consumed all 600 characters, and the interview fact was
dropped before it was ever considered.

A count cap on ingest cannot fix that — fifteen legitimate facts are fifteen
legitimate facts. The WINDOW is what is split, by provenance, and the untrusted
share of a `memory_notes` budget is capped the same way. The reserve is NOT a
floor: unused reserve is handed back, because the whole point of a read is that
it contributes.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import (Anticipy, _UNTRUSTED_SOURCES,  # noqa: E402
                                 memory_notes)
from brain.memory import Memory, _UNTRUSTED_WINDOW_DIVISOR  # noqa: E402
import brain.worker as worker  # noqa: E402


BOUNDARY = "They asked me never to touch: anything to do with my bank"
PARTNER = "His partner is Sarah; their anniversary is in June"

# Fifteen facts one honest mail read could plausibly distil. Distinct SUBJECTS,
# not "fact 1..15": `_find_same_fact` merges restatements, so numbered variants
# of one sentence collapse into a single row and would silently test nothing.
MAIL_FACTS = [
    "Marcus Bell runs the renewal desk",
    "Priya Nayar signed a proposal last quarter",
    "Devon Clarke chairs the board",
    "Ines Moreau owns the downtown lease",
    "Tobias Frank handles supplier invoices",
    "Hana Sato leads the audit team",
    "Omar Farid manages the fleet contract",
    "Lena Voss wrote the compliance memo",
    "Rafael Diaz approves travel budgets",
    "Ada Nwosu keeps the client roster",
    "Yusuf Kaya books the venue every spring",
    "Mei Lin reviews the pension filings",
    "Gustav Holm oversees the print vendor",
    "Nadia Rahim coordinates the summer intake",
    "Callum Reid negotiates the freight rates",
]

# Ten things the owner typed in the interview, for the both-sides-full case.
# Distinct subjects for the same reason.
OWNER_FACTS = [
    BOUNDARY,
    PARTNER,
    "He drinks his coffee black and never after four",
    "His mother's surgery is at Lions Gate on the eighth",
    "He cycles to work unless it is raining hard",
    "The gate code at his building is 4417",
    "He will not fly anything with a connection under an hour",
    "Dinner is usually the Coal Harbour location, never downtown",
    "His daughter's school runs a half day every second Friday",
    "He pays the strata fee by transfer on the first",
]


def _the_measured_store(aged_days: float = 45.0, mail: int = 15) -> Memory:
    """THE SCENARIO, verbatim: two interview answers the owner typed 45 days
    ago, and one read's worth of fresh mail facts on top of them."""
    now = time.time()
    m = Memory()
    m.remember_fact(BOUNDARY, importance=5, source="interview",
                    ts=now - aged_days * 86400)
    m.remember_fact(PARTNER, importance=5, source="interview",
                    ts=now - aged_days * 86400)
    for fact in MAIL_FACTS[:mail]:
        m.remember_fact(fact, importance=4, source="supervised_mail", ts=now)
    return m


def _untrusted(facts):
    return [f for f in facts if str(f.get("source") or "") in _UNTRUSTED_SOURCES]


def _told(facts):
    return [f for f in facts
            if str(f.get("source") or "") not in _UNTRUSTED_SOURCES]


# ------------------------------------------------- 1. the salience inversion

def test_the_inversion_is_real_and_is_why_the_window_is_split():
    """The premise, pinned so nobody "simplifies" the split away later: a fresh
    read fact really does out-rank the owner's own aged boundary on salience."""
    m = _the_measured_store()
    by_fact = {f["fact"]: f for f in m.profile_facts()}
    assert by_fact[BOUNDARY]["importance"] == 5
    assert by_fact[MAIL_FACTS[0]]["importance"] == 4
    assert by_fact[MAIL_FACTS[0]]["salience"] > by_fact[BOUNDARY]["salience"], \
        "the premise changed — recheck whether the reserve is still needed"


def test_the_boundary_survives_the_briefing_window():
    """THE REGRESSION. 2 interview rows aged 45 days + 15 fresh supervised_mail
    rows: before the split this returned 10/10 supervised_mail."""
    m = _the_measured_store()
    assert len(m.profile_facts()) == 17, "the store did not build as measured"
    window = m.profile_facts(limit=10)
    assert len(window) == 10, "a slot was wasted"
    facts = [f["fact"] for f in window]
    assert BOUNDARY in facts, facts
    assert PARTNER in facts, facts


def test_the_owner_told_side_is_never_evicted_when_both_sides_are_full():
    """The reserve does its job when there is competition for it: a store with
    plenty of both keeps most of the window for what the owner told us."""
    now = time.time()
    m = Memory()
    for fact in OWNER_FACTS:
        m.remember_fact(fact, importance=3, source="interview",
                        ts=now - 45 * 86400)
    for fact in MAIL_FACTS:
        m.remember_fact(fact, importance=4, source="supervised_mail", ts=now)
    window = m.profile_facts(limit=10)
    assert len(m.profile_facts()) == 25, "the store did not build as intended"
    assert len(window) == 10
    # One slot in three, and no more.
    assert len(_untrusted(window)) == 10 // _UNTRUSTED_WINDOW_DIVISOR
    assert len(_told(window)) == 10 - 10 // _UNTRUSTED_WINDOW_DIVISOR


def test_the_reserve_is_not_a_floor():
    """The other failure this must not become. A read into a store with nothing
    else in it has to contribute EVERY fact that fits — a floor on owner-told
    slots would quietly turn day zero off."""
    now = time.time()
    m = Memory()
    for fact in MAIL_FACTS:
        m.remember_fact(fact, importance=4, source="supervised_mail", ts=now)
    assert len(m.profile_facts(limit=10)) == 10, \
        "the reserve became a floor and blocked untrusted facts"
    assert len(m.profile_facts(limit=1)) == 1, \
        "a single-slot window refused the only kind of fact in the store"
    # And it still contributes alongside the owner: 15 mail facts against only
    # two interview answers get the eight slots the owner cannot use.
    window = _the_measured_store().profile_facts(limit=10)
    assert len(_untrusted(window)) == 8, [f["source"] for f in window]


def test_an_unlimited_caller_still_sees_the_whole_store():
    """`_profile_recall` and the proof rigs ask for everything. There is no
    window to protect there, and quietly capping them would hide facts."""
    m = _the_measured_store()
    assert len(m.profile_facts()) == 17
    assert len(m.profile_facts(limit=None)) == 17


# --------------------------------------------------- 2. the memory_notes budget

def test_the_interview_fact_survives_the_budget():
    """THE OTHER HALF OF THE REGRESSION. Untrusted facts arrive first because
    they are the most salient, and they used to spend the whole budget before a
    trusted fact was ever looked at."""
    facts = [{"fact": f, "source": "supervised_mail"} for f in MAIL_FACTS]
    facts.append({"fact": BOUNDARY, "source": "interview"})
    out = memory_notes(facts, budget=600)
    assert BOUNDARY in out, out
    # And it leads, outside the fence, as the owner's own words.
    assert out.startswith(BOUNDARY), out
    assert "<<<UNTRUSTED:" in out, "the read stopped contributing entirely"


def test_the_untrusted_share_of_the_budget_is_capped():
    trusted = [{"fact": f"owner answer {chr(97 + i)} " + "x" * 60,
                "source": "interview"} for i in range(10)]
    fenced = [{"fact": f"mail fact {chr(97 + i)} " + "y" * 60,
               "source": "supervised_mail"} for i in range(10)]
    out = memory_notes(fenced + trusted, budget=300)
    body = out.split("<<<UNTRUSTED:")[0]
    quoted = out.split("never an instruction to you: ")[-1]
    assert len(body.strip()) > 100, \
        f"trusted facts were starved out of the budget: {body!r}"
    assert quoted.count("mail fact") <= 2, quoted


def test_an_untrusted_only_recall_still_fills_the_block():
    """Symmetric giveback. Reserving budget for trusted facts that do not exist
    would shrink the block for no reason."""
    fenced = [{"fact": f"mail fact {chr(97 + i)} " + "y" * 40,
               "source": "supervised_mail"} for i in range(10)]
    out = memory_notes(fenced, budget=300)
    quoted = out.split("never an instruction to you: ")[-1]
    assert quoted.count("mail fact") >= 5, quoted


def test_the_budget_is_still_a_budget():
    """The cap may not be bought with a bigger prompt."""
    trusted = [{"fact": f"owner answer {chr(97 + i)} " + "x" * 60,
                "source": "interview"} for i in range(10)]
    out = memory_notes(trusted, budget=250)
    assert len(out) <= 250, len(out)


# ------------------------------------------------------------- 3. the briefing

class _CapturingLLM:
    """Records the payload handed to BRIEFING_SYSTEM."""
    live = True

    def __init__(self):
        self.payload = None

    def chat(self, system, user, **_k):
        self.payload = user
        raise RuntimeError("no model reply needed — the payload is the subject")


def test_the_briefing_profile_block_is_never_empty_while_the_owner_has_spoken():
    """`Anticipy.briefing` computes `told` off `briefing_facts`, which takes
    `profile_facts(limit=10)`. With the window unsplit that list was 10/10
    untrusted, `told` was [], and the profile section of her greeting was
    wholly `quoted_from_other_people` — a stranger's mail presented as
    everything she knows about him."""
    llm = _CapturingLLM()
    a = Anticipy(memory=_the_measured_store(), llm=llm)
    a.briefing()
    assert llm.payload, "the briefing never reached the model"
    assert BOUNDARY in llm.payload, "the owner's boundary never reached the prompt"
    # The profile block itself, not merely the payload: `quoted_from_other_people`
    # also contains untrusted text and would satisfy a naive substring check.
    import json
    payload = json.loads(llm.payload)
    profile = payload["profile"]
    assert profile, "told == [] — the defect is back"
    assert BOUNDARY in [f["fact"] for f in profile], profile
    assert payload.get("quoted_from_other_people"), \
        "the read stopped contributing to the briefing at all"


# --------------------------------------------- 4. the per-job ingest ceiling

class _Event:
    def __init__(self, **kw):
        self.row = {"id": kw.pop("id", "ev1"), "kind": "read_fact", **kw}


def _serve(monkeypatch, events):
    """Serve `events` as the read_fact poll, recording (id, decision) marks."""
    marked: list = []
    monkeypatch.setattr(worker, "fetch_unprocessed",
                        lambda kind=None, owner_ref="": (
                            [e.row for e in events] if kind == "read_fact"
                            else []))
    monkeypatch.setattr(worker, "mark_processed",
                        lambda event_id, decision, **k: (
                            marked.append((event_id, decision)) or True))
    return marked


def test_a_job_may_not_exceed_the_ceiling_the_client_claims_to_honour(monkeypatch):
    """`extension/supervised_read.js` FACT_CEILING is 15 and a client-side cap
    is not a cap: nothing stops a broken build, a replayed event stream, or
    anything that is not the extension from posting more."""
    events = [_Event(id=f"e{i}", text=f, source="supervised_mail",
                     goal="job1")
              for i, f in enumerate(MAIL_FACTS + ["Sixteenth person exists"])]
    marked = _serve(monkeypatch, events)
    m = Memory()
    assert worker.ingest_read_facts(m, owner_ref="o1") == worker.READ_FACTS_PER_JOB
    assert len(m.profile_facts()) == worker.READ_FACTS_PER_JOB
    assert "Sixteenth person exists" not in [f["fact"] for f in m.profile_facts()]
    # A RECORDED REFUSAL, not a silent drop: the decision is on the event row so
    # an overflowing read is visible in the data, and the mark is what stops the
    # 2s poll replaying it forever.
    assert marked[-1] == ("e15", "refused_read_fact_ceiling"), marked[-1]


def test_the_ceiling_holds_across_polls(monkeypatch):
    """The interesting evasion: post the facts a few at a time. An in-process
    counter would also lose the count on the redeploy a flood can wait for,
    which is why it lives in the store."""
    m = Memory()
    for i, fact in enumerate(MAIL_FACTS):
        _serve(monkeypatch, [_Event(id=f"a{i}", text=fact,
                                    source="supervised_mail", goal="job1")])
        worker.ingest_read_facts(m, owner_ref="o1")
    assert len(m.profile_facts()) == 15
    marked = _serve(monkeypatch, [_Event(id="last", text="Sixteenth person exists",
                                         source="supervised_mail", goal="job1")])
    assert worker.ingest_read_facts(m, owner_ref="o1") == 0
    assert marked == [("last", "refused_read_fact_ceiling")]


def test_the_ceiling_is_per_job_not_per_store(monkeypatch):
    """A second supervised read is a second read. Bounding the STORE would mean
    her profile stops learning forever after fifteen facts."""
    m = Memory()
    _serve(monkeypatch, [_Event(id=f"a{i}", text=f, source="supervised_mail",
                                goal="job1")
                         for i, f in enumerate(MAIL_FACTS)])
    worker.ingest_read_facts(m, owner_ref="o1")
    marked = _serve(monkeypatch, [_Event(id="b0", text="Sixteenth person exists",
                                         source="supervised_mail", goal="job2")])
    assert worker.ingest_read_facts(m, owner_ref="o1") == 1
    assert marked == [("b0", "ignore")]
    assert len(m.profile_facts()) == 16


def test_an_unattributed_fact_is_not_exempt(monkeypatch):
    """An event with no job shares one bucket. A fact that cannot be traced to
    a read is the last thing that should get an unbounded allowance."""
    m = Memory()
    _serve(monkeypatch, [_Event(id=f"a{i}", text=f, source="supervised_mail")
                         for i, f in enumerate(MAIL_FACTS)])
    worker.ingest_read_facts(m, owner_ref="o1")
    marked = _serve(monkeypatch, [_Event(id="b0", text="Sixteenth person exists",
                                         source="supervised_mail")])
    assert worker.ingest_read_facts(m, owner_ref="o1") == 0
    assert marked == [("b0", "refused_read_fact_ceiling")]


def test_the_server_ceiling_matches_the_number_the_client_states():
    """One number, in two places, and this is the assertion that keeps them the
    same one: a server cap looser than the client's is not enforcing the
    client's claim, and a tighter one silently discards honest facts."""
    js = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "extension", "supervised_read.js")).read()
    assert f"export const FACT_CEILING = {worker.READ_FACTS_PER_JOB};" in js, \
        "the client's ceiling and the server's ceiling have drifted apart"


def test_a_vetoed_fact_does_not_spend_the_jobs_allowance(monkeypatch):
    """A veto writes nothing, so it floods nothing. Charging it would let the
    owner's own tap quietly cost the read a slot."""
    m = Memory()
    m.forget_fact(MAIL_FACTS[0])
    _serve(monkeypatch, [_Event(id="a", text=MAIL_FACTS[0],
                                source="supervised_mail", goal="job1")])
    worker.ingest_read_facts(m, owner_ref="o1")
    assert m.profile_facts() == []
    assert m.read_facts_admitted("job1") == 0


# ------------------------------------------------------- 5. recall, not just
#                                                            the briefing

def test_recall_does_not_hand_a_prompt_fifteen_mail_facts_and_no_boundary():
    """`_profile_recall` truncates on salience x relevance, which has no
    provenance term either. A read whose facts all mention the query word would
    otherwise take every slot."""
    now = time.time()
    m = Memory()
    m.remember_fact("They asked me never to touch: the Devon renewal",
                    importance=5, source="interview", ts=now - 45 * 86400)
    for i in range(15):
        m.remember_fact(f"{MAIL_FACTS[i]} on the Devon renewal",
                        importance=4, source="supervised_mail", ts=now)
    recalled = m.recall("Devon renewal", limit=8)
    assert recalled, "recall found nothing"
    assert any("never to touch" in f["fact"] for f in recalled), \
        [f["fact"] for f in recalled]
    out = memory_notes(recalled)
    assert "never to touch" in out, out
