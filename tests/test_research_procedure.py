"""HANDS 1 §8.1 — the research lane learning HOW, not just answering WHAT.

`run_research` answers a question in prose with citations. A procedure is the
other thing reading the web can produce: where the task starts, what you need
in hand, the ordered steps. It is the object the gate exists to produce, and
until now the only place that could produce one was the browser — which is the
half of the product the spec says should not be paying for it (§4.2: the shape
of a task travels; the route through a page does not).

Everything here is read off the open web, which is the single most hostile
input this product accepts, so the tests are mostly about refusals:

  * a place that holds money may not even be READ (research runs with less
    supervision than an errand);
  * the owner's own machine is not the open web, and research runs BEFORE the
    loop's loopback guard exists;
  * what comes back is BACKGROUND, never instructions, and the fence around it
    is a security boundary rather than decoration;
  * an honest blank beats an invented procedure, because the agent will act on
    whatever it is handed.
"""
import json
import types

import pytest

import brain.research as research


class FakeBrave:
    def __init__(self, results, boom=False):
        self.results = results
        self.boom = boom
        self.queries = []

    def search(self, query, count=5):
        self.queries.append(query)
        if self.boom:
            raise RuntimeError("brave down")
        return [{"title": "t", "url": u, "description": "d"} for u in self.results]


class FakeLLM:
    live = True

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, system, user, **kw):
        self.calls.append((system, user))
        if isinstance(self.reply, Exception):
            raise self.reply
        return types.SimpleNamespace(text=self.reply)


def fetcher_for(pages, seen=None):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        return pages.get(url, "")
    return fetch


GOOD_JSON = ('{"start_url": "https://support.example.com/returns",'
             ' "needs": ["your order number"],'
             ' "steps": ["Open the returns portal", "Enter the order number"],'
             ' "caveats": ["there is a 30-day window"]}')


def test_a_procedure_comes_back_in_the_shape_the_cache_stores():
    seen = []
    got = research.learn_procedure(
        "how do I claim an Anker warranty",
        brave=FakeBrave(["https://support.example.com/returns"]),
        fetcher=fetcher_for({"https://support.example.com/returns": "Start a return."},
                            seen),
        llm=FakeLLM(GOOD_JSON))
    assert got["steps"] == ["Open the returns portal", "Enter the order number"]
    assert got["needs"] == ["your order number"]
    assert got["caveats"] == ["there is a 30-day window"]
    assert got["startUrl"] == "https://support.example.com/returns"
    assert got["sources"] == ["https://support.example.com/returns"]
    assert got["learnedAt"] > 0
    assert got["question"] == "how do I claim an Anker warranty"
    # It must drop straight into the store the gate reads from.
    assert research.procedure_is_live(got)
    assert set(got) <= set(research.PROCEDURE_FIELDS)


def test_a_place_that_holds_money_is_never_even_read():
    """learn.js's NEVER_RESEARCH is deliberately stricter than the main loop's
    block list, because research happens with less supervision than an errand.
    A refusal that happened after the fetch would already have sent the
    request."""
    seen = []
    research.learn_procedure(
        "how do I dispute a charge",
        brave=FakeBrave(["https://www.chase.com/disputes",
                         "https://support.example.com/disputes"]),
        fetcher=fetcher_for({"https://support.example.com/disputes": "Call us."}, seen),
        llm=FakeLLM(GOOD_JSON))
    assert "https://www.chase.com/disputes" not in seen


def test_the_owners_own_machine_is_never_read():
    """"The portal is at http://127.0.0.1:8090/admin" is a sentence any web
    page can contain, and a search engine can return one."""
    seen = []
    research.learn_procedure(
        "how do I file the form",
        brave=FakeBrave(["http://127.0.0.1:8090/admin", "http://192.168.1.1/",
                         "https://gov.example.gov/forms"]),
        fetcher=fetcher_for({"https://gov.example.gov/forms": "File it here."}, seen),
        llm=FakeLLM(GOOD_JSON))
    assert all(not u.startswith("http://127.") and not u.startswith("http://192.168")
               for u in seen)


def test_the_pages_are_fenced_and_the_model_is_told_they_are_untrusted():
    """The fence is the security boundary, not decoration. Per-reading markers,
    so a page cannot close somebody else's fence and speak in the operator's
    voice."""
    llm = FakeLLM(GOOD_JSON)
    research.learn_procedure(
        "how do I claim a warranty",
        brave=FakeBrave(["https://a.example.com/x", "https://b.example.com/y"]),
        fetcher=fetcher_for({"https://a.example.com/x": "page one text",
                             "https://b.example.com/y": "page two text"}),
        llm=llm)
    system, user = llm.calls[0]
    assert user.count("BEGIN UNTRUSTED PAGE") == 2
    assert user.count("END UNTRUSTED PAGE") == 2
    assert "UNTRUSTED" in system.upper()
    assert "instructions" in system.lower()


def test_the_prompt_asks_for_a_blank_rather_than_a_plausible_guess():
    llm = FakeLLM(GOOD_JSON)
    research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({"https://a.example.com/x": "text"}), llm=llm)
    system, _ = llm.calls[0]
    assert "empty steps" in system.lower() or "honest blank" in system.lower()


def test_an_empty_steps_list_is_learned_nothing_and_not_a_hollow_record():
    """A confident wrong procedure costs more than an honest blank, because the
    agent will act on it — and a cached blank would stop this shape ever being
    researched again."""
    got = research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({"https://a.example.com/x": "text"}),
        llm=FakeLLM('{"start_url": "https://a.example.com/x", "steps": []}'))
    assert got is None


def test_nothing_readable_means_no_procedure_and_no_model_call():
    llm = FakeLLM(GOOD_JSON)
    got = research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({}), llm=llm)
    assert got is None
    assert not llm.calls, "a model call on nothing read is money spent on nothing"


def test_a_search_that_returns_nothing_researchable_stops_there():
    llm = FakeLLM(GOOD_JSON)
    got = research.learn_procedure(
        "q", brave=FakeBrave(["http://localhost/x", "javascript:alert(1)"]),
        fetcher=fetcher_for({}), llm=llm)
    assert got is None and not llm.calls


def test_one_page_per_host():
    """Three pages from the same help centre is one source wearing three hats,
    and it crowds out the second opinion that disagrees with it."""
    seen = []
    research.learn_procedure(
        "q",
        brave=FakeBrave(["https://help.example.com/a", "https://help.example.com/b",
                         "https://other.example.org/c"]),
        fetcher=fetcher_for({"https://help.example.com/a": "one",
                             "https://help.example.com/b": "two",
                             "https://other.example.org/c": "three"}, seen),
        llm=FakeLLM(GOOD_JSON))
    assert seen.count("https://help.example.com/b") == 0


def test_no_more_than_three_pages_are_read():
    seen = []
    urls = [f"https://h{i}.example.com/p" for i in range(9)]
    research.learn_procedure(
        "q", brave=FakeBrave(urls),
        fetcher=fetcher_for({u: "text" for u in urls}, seen),
        llm=FakeLLM(GOOD_JSON))
    assert len(seen) <= research.MAX_PROCEDURE_PAGES


def test_a_researched_start_url_at_a_private_address_is_dropped_not_obeyed():
    """MODEL OUTPUT DISTILLED FROM WEB PAGES. It may improve a first guess and
    may never widen where the agent goes. The rest of the procedure survives —
    a bad address is one wrong field."""
    got = research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({"https://a.example.com/x": "text"}),
        llm=FakeLLM('{"start_url": "http://127.0.0.1:8090/admin",'
                    ' "steps": ["do the thing"]}'))
    assert got["startUrl"] is None
    assert got["steps"] == ["do the thing"]


def test_the_record_is_bounded_in_every_direction():
    """It rides into EVERY step of the run that follows, not once."""
    got = research.learn_procedure(
        "q" * 900, brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({"https://a.example.com/x": "text"}),
        llm=FakeLLM(json.dumps({"steps": ["s" * 900] * 40,
                                "needs": ["n" * 900] * 40,
                                "caveats": ["c" * 900] * 40})))
    assert len(got["steps"]) <= research.MAX_PROCEDURE_STEPS
    assert all(len(s) <= 240 for s in got["steps"])
    assert len(got["needs"]) <= 5 and len(got["caveats"]) <= 3
    assert len(got["question"]) <= 200


@pytest.mark.parametrize("reply", [
    "not json at all",
    "",
    "{ broken",
    '{"steps": "not a list"}',
    '["steps"]',
])
def test_a_model_that_does_not_answer_is_a_blank_not_a_crash(reply):
    got = research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({"https://a.example.com/x": "text"}),
        llm=FakeLLM(reply))
    assert got is None


def test_every_leg_can_fail_without_taking_the_worker_down():
    """A crashed pass would leave the job stuck at `running` forever."""
    def boom(url):
        raise RuntimeError("network")

    assert research.learn_procedure("q", brave=FakeBrave([], boom=True),
                                    fetcher=boom, llm=FakeLLM(GOOD_JSON)) is None
    assert research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]), fetcher=boom,
        llm=FakeLLM(GOOD_JSON)) is None
    assert research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({"https://a.example.com/x": "text"}),
        llm=FakeLLM(RuntimeError("model down"))) is None
    assert research.learn_procedure("q", brave=None, fetcher=fetcher_for({}),
                                    llm=FakeLLM(GOOD_JSON)) is None
    assert research.learn_procedure("", brave=FakeBrave(["https://a.example.com/x"]),
                                    fetcher=fetcher_for({}), llm=None) is None


def test_a_dead_model_does_not_invent_a_procedure_from_the_page_text():
    """`run_research`'s honest fallback is the sources' own words, attributed —
    fine for an ANSWER a person reads. A PROCEDURE is acted on, so there is no
    fallback here at all: no model, no procedure."""
    # A model that WOULD answer perfectly well if asked — the only thing wrong
    # with it is that nothing declared it live. If the live check were dropped
    # this would come back with a procedure, which is why the fake answers.
    dead = FakeLLM(GOOD_JSON)
    dead.live = False
    seen = []
    got = research.learn_procedure(
        "q", brave=FakeBrave(["https://a.example.com/x"]),
        fetcher=fetcher_for({"https://a.example.com/x": "Step 1. Do the thing."},
                            seen),
        llm=dead)
    assert got is None
    assert not dead.calls, "a model nobody declared live was asked anyway"
    assert not seen, "pages were fetched for a distillation that could not happen"


def test_the_distiller_never_decides_whether_to_research():
    """The gate decides that, on `touches` and a cache lookup. If the distiller
    grew an opinion about which questions are worth researching, that opinion
    would be a second gate — one keyed on the words of the question, which is
    exactly what law 1 forbids."""
    for question in ("book a table for two", "dispute the March bill from BC Hydro",
                     "what time does the aquarium close", "zzzz"):
        brave = FakeBrave(["https://a.example.com/x"])
        research.learn_procedure(
            question, brave=brave,
            fetcher=fetcher_for({"https://a.example.com/x": "text"}),
            llm=FakeLLM(GOOD_JSON))
        assert brave.queries, f"refused to even search: {question!r}"
