"""A rate-limit blip must not make her ignore a spoken line.

Both providers were called with raise_for_status() and no retry. On the
decision path that exception reaches triage's handler, which tries once more
and then files the line as "ignore" — so a 429 lasting one second silently
discarded an errand the owner had said out loud, and nothing recorded it.

The polarity is the whole test. Retrying everything is how a wallet empties:
overnight/MORNING.md records the night this system went silent because
OpenRouter credits hit 160/160 and every model returned 402. Retrying that
spends the same nothing three times as fast. So transients retry and refusals
do not, and both directions are pinned.
"""

import pytest

import brain.llm as llm


class _Resp:
    def __init__(self, code):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"ok": True, "code": self.status_code}


class _Client:
    """Answers with the given codes in order, then 200 forever."""

    def __init__(self, codes, counter):
        # NOT copied. httpx.Client() is constructed fresh for every attempt, so
        # a per-instance copy would replay the first code forever and the test
        # would never observe a retry succeeding.
        self._codes = codes
        self._counter = counter

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def post(self, *_a, **_k):
        self._counter["n"] += 1
        code = self._codes.pop(0) if self._codes else 200
        return _Resp(code)


@pytest.fixture
def fast_retries(monkeypatch):
    monkeypatch.setattr(llm, "_RETRY_BASE_SECONDS", 0.001)


def _run(codes, counter):
    original = llm.httpx.Client
    llm.httpx.Client = lambda *a, **k: _Client(codes, counter)
    try:
        return llm._post_json("http://x", {}, {})
    finally:
        llm.httpx.Client = original


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_transient_codes_are_retried_and_succeed(code, fast_retries):
    counter = {"n": 0}
    out = _run([code, code], counter)
    assert out["ok"] is True
    assert counter["n"] == 3, "should be the first try plus two retries"


@pytest.mark.parametrize("code", [400, 401, 403, 404, 402])
def test_refusals_are_not_retried(code, fast_retries):
    """402 especially. Out of credit is not a transient condition."""
    counter = {"n": 0}
    with pytest.raises(RuntimeError):
        _run([code, code, code], counter)
    assert counter["n"] == 1, (
        f"HTTP {code} was retried; only transports and 5xx/429 may be")


def test_retries_are_bounded(fast_retries):
    """A provider that is down stays down. Three attempts, then it raises."""
    counter = {"n": 0}
    with pytest.raises(RuntimeError):
        _run([503] * 20, counter)
    assert counter["n"] == llm._RETRY_ATTEMPTS, (
        "the loop must stop at its ceiling; the last attempt stops "
        "short-circuiting and lets the provider's real status propagate")


def test_a_timeout_is_retried(fast_retries):
    counter = {"n": 0}

    class _Timeout:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, *_a, **_k):
            counter["n"] += 1
            if counter["n"] < 3:
                raise llm.httpx.TimeoutException("slow")
            return _Resp(200)

    original = llm.httpx.Client
    llm.httpx.Client = lambda *a, **k: _Timeout()
    try:
        assert llm._post_json("http://x", {}, {})["ok"] is True
    finally:
        llm.httpx.Client = original
    assert counter["n"] == 3


def test_the_first_call_is_not_delayed(fast_retries):
    """The happy path pays nothing. A retry policy that sleeps before its
    first attempt would add latency to every judgement she ever makes."""
    counter = {"n": 0}
    assert _run([], counter)["ok"] is True
    assert counter["n"] == 1
