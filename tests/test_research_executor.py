"""Brief 01, the executor: Brave search (mocked) + page fetch + summary with
citations. Failure of any leg is a failed job, never a crash — and the API
key never appears anywhere a human or a log would see it."""
import types

import brain.research as research

RESULTS = [
    {"title": "Vancouver Aquarium — Hours", "url": "https://vanaqua.org/hours",
     "description": "Open daily 9:30am to 5:30pm."},
    {"title": "Vancouver Aquarium — Visit", "url": "https://vanaqua.org/visit",
     "description": "Plan your visit to the aquarium."},
]


class FakeBrave:
    def __init__(self, results=None, boom=False):
        self.results = RESULTS if results is None else results
        self.boom = boom
        self.queries = []

    def search(self, query, count=5):
        self.queries.append(query)
        if self.boom:
            raise RuntimeError("brave down")
        return self.results


def fake_fetch(url):
    return f"Fetched text for {url}: open 9:30 to 5:30 daily."


class FakeLLM:
    live = True

    def __init__(self):
        self.calls = []

    def chat(self, system, user, temperature=0.1, **kw):
        self.calls.append((system, user))
        return types.SimpleNamespace(text="Open daily 9:30am-5:30pm [1].")


def test_summarizes_with_citations_via_the_llm():
    llm = FakeLLM()
    brave = FakeBrave()
    out = research.run_research(
        "research: opening hours of the Vancouver aquarium", {},
        llm=llm, brave=brave, fetcher=fake_fetch)
    assert out["ok"]
    assert "[1]" in out["result"]
    assert "Sources:" in out["result"]
    assert "https://vanaqua.org/hours" in out["result"]
    # The query the model saw lost its instruction prefix.
    assert brave.queries == ["opening hours of the Vancouver aquarium"]
    assert "opening hours" in llm.calls[0][1]


def test_without_a_model_the_sources_own_words_are_the_answer():
    out = research.run_research("look up aquarium hours", {}, llm=None,
                                brave=FakeBrave(), fetcher=fake_fetch)
    assert out["ok"]
    assert "Sources:" in out["result"]
    assert "9:30" in out["result"]           # the snippet, never an invention
    assert "[1]" in out["result"]


def test_a_broken_model_still_produces_a_cited_answer():
    class Broken:
        live = True

        def chat(self, *a, **k):
            raise RuntimeError("model down")

    out = research.run_research("look up aquarium hours", {}, llm=Broken(),
                                brave=FakeBrave(), fetcher=fake_fetch)
    assert out["ok"]
    assert "Sources:" in out["result"]


def test_search_failure_is_a_failed_job_not_a_crash():
    out = research.run_research("research: anything", {},
                                brave=FakeBrave(boom=True))
    assert not out["ok"]
    assert out["result"]


def test_no_results_is_a_failed_job():
    out = research.run_research("research: anything", {},
                                brave=FakeBrave(results=[]))
    assert not out["ok"]


def test_no_client_and_no_key_never_crashes():
    out = research.run_research("research: anything", {})
    assert not out["ok"]


def test_a_dead_page_is_a_missing_source_not_a_crash():
    out = research.run_research("look up aquarium hours", {},
                                brave=FakeBrave(),
                                fetcher=lambda url: "")
    assert out["ok"]                          # descriptions still carry it
    assert "Sources:" in out["result"]


def test_the_key_never_appears_in_result_or_repr(monkeypatch):
    seen = {}

    def fake_get(url, **kw):
        seen["headers"] = kw.get("headers") or {}

        class R:
            ok = True

            def raise_for_status(self):
                pass

            def json(self):
                return {"web": {"results": []}}
        return R()

    monkeypatch.setattr(research.requests, "get", fake_get)
    out = research.run_research("research: anything", {}, api_key="sk-SECRET")
    assert "sk-SECRET" not in out["result"]
    assert "sk-SECRET" not in repr(research.BraveClient("sk-SECRET"))
    # The key goes where Brave expects it — a header, never the URL.
    assert seen["headers"].get("X-Subscription-Token") == "sk-SECRET"


def test_query_strips_a_labelled_prefix_only():
    """This test used to assert "look up ferry times" -> "ferry times", and that
    assertion was pinning a HARNESS-LAWS Law 1 violation in place: the strip was
    a verb list deciding which words of a sentence were instruction and which
    were subject. Measured, it lost the request outright — "Compare the two
    quotes from the movers" searched for "the two quotes from the movers", and
    the Brief's own moment 29 searched for "me a dentist open Saturdays".

    The rule is now the separator, which is punctuation rather than meaning.
    THE TRADE IS REAL AND IS NOT HIDDEN: an unlabelled "look up ferry times" now
    searches whole, which is a marginally worse query than "ferry times". That is
    the price of not guessing, and a slightly long query returns the ferry
    timetable while a query missing "compare" answers a different question.
    See tests/test_research_query_is_not_a_verb_list.py."""
    assert research.query_from_goal(
        "research: opening hours of the Vancouver aquarium") \
        == "opening hours of the Vancouver aquarium"
    # No separator, so no strip — the verb may be load-bearing and only a model
    # could tell. The whole phrase goes to the search engine.
    assert research.query_from_goal("look up ferry times") == "look up ferry times"
    # A goal that IS the query already passes through whole.
    assert research.query_from_goal("Vancouver aquarium hours") \
        == "Vancouver aquarium hours"
