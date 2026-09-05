"""The gateway leg must grade the brain that is actually serving people.
Audit F25, F32, F33, F34.

WHAT WAS MEASURED, 2026-09-05:

  * `overnight/is_the_gateway_live.py` shelled `railway logs -s worker` and
    reported `[FAIL] THE BANNER — the newest banner carries no fallback=
    field`. That banner belonged to a Railway worker whose own line read
    `pb=…up.railway.app`: a retired machine on a retired backend. Production
    had moved to Cloudflare. A confident verdict about the wrong computer is
    worse than no verdict, because somebody acts on it.

  * The Cloudflare container's stdout is unreachable from a terminal:
    `wrangler tail anticipy-brain` for 150 s, nine live instances, 13 events,
    ZERO lines containing "worker up", "sms=" or "gateway tally" — the tail
    carries the Durable Object's RPC events, not the container's stdout;
    `wrangler containers` has no logs command; the observability telemetry API
    answers 403 with a developer's OAuth token.

So the brain now writes its boot line to a `worker_status` events row and this
leg reads that. These tests hold both ends of that contract: what the worker
writes, what the gate makes of it, and the fact that the gate no longer
reaches for Railway unless asked.
"""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402
from overnight import is_the_gateway_live as G  # noqa: E402


NOW = dt.datetime(2026, 9, 5, 17, 0, tzinfo=dt.timezone.utc)


def _stamp(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%d %H:%M:%S.000Z")


def _just_now():
    """A stamp the gate's OWN clock reads as fresh — main() uses real time,
    so the pure verdicts get the pinned NOW above and the end-to-end runs get
    this."""
    return (dt.datetime.now(dt.timezone.utc)
            - dt.timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M:%S.000Z")


LIVE_TEXT = ("worker up · llm=live:deepseek/deepseek-v3.2 · sms=twilio · "
             "pb=https://api.anticipy.ai · primary=openrouter:deepseek/deepseek-v3.2 "
             "fallback=gemini:gemini-2.5-flash · brain=5909f7f6aa11 · "
             "llm: gateway tally primary_ok=40 rescued=2 skipped=0 reissued=0 "
             "both_dead=0")


# ------------------------------------------------- the gate's own verdicts

def test_a_backend_that_cannot_be_read_is_never_a_verdict():
    code, _, sentence, texts = G.status_verdict(None, now=NOW)
    assert (code, texts) == (2, [])
    assert "could not be read" in sentence


def test_no_status_row_says_so_instead_of_grading_something_else():
    """Today's honest answer: the container that is running predates the row."""
    code, _, sentence, texts = G.status_verdict([], now=NOW)
    assert (code, texts) == (2, [])
    assert "no `worker_status` row" in sentence


def test_a_stale_row_is_unproven_not_a_pass():
    """A row nobody refreshed is a container that is gone. It must not be
    graded as the running brain — in either direction."""
    rows = [{"text": LIVE_TEXT, "updated": _stamp(60)}]

    code, _, sentence, texts = G.status_verdict(rows, now=NOW)

    assert (code, texts) == (2, [])
    assert "stale" in sentence


def test_a_freshly_refreshed_row_is_the_thing_to_grade():
    rows = [{"text": LIVE_TEXT, "updated": _stamp(4)},
            {"text": "worker up · primary=x:y fallback=none", "updated": _stamp(2000)}]

    code, _, _, texts = G.status_verdict(rows, now=NOW)

    assert code == 0
    assert texts == [LIVE_TEXT], "only the fresh brain is graded"


# ------------------------------------------------- the machine it reaches for

def test_the_default_run_never_shells_railway(monkeypatch, capsys):
    """The finding itself. Production is Cloudflare; the Railway worker is a
    different machine and grading it was the defect."""
    called = []
    monkeypatch.setattr(G, "fetch_messages",
                        lambda *a, **k: called.append(a) or [])
    monkeypatch.setattr(G, "fetch_status_rows", lambda *a, **k: [])
    monkeypatch.setattr(G._env, "load_and_announce", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["is_the_gateway_live.py"])

    code = G.main()

    assert called == [], "the Cloudflare path must not read Railway's logs"
    assert code == 2
    out = capsys.readouterr().out
    assert "api.anticipy.ai" in out
    assert "0 THE RUNNING BRAIN" in out


def test_railway_is_still_available_but_only_when_asked(monkeypatch, capsys):
    """It is not deleted — it is demoted to the thing it is honest about."""
    monkeypatch.setattr(G, "fetch_messages", lambda *a, **k: [LIVE_TEXT])
    monkeypatch.setattr(G, "fetch_status_rows", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("the railway path must not read the status row")))
    monkeypatch.setattr(G._env, "load_and_announce", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["is_the_gateway_live.py", "--source", "railway"])

    G.main()

    assert "railway service" in capsys.readouterr().out


def test_a_live_row_is_graded_exactly_as_a_log_line_was(monkeypatch, capsys):
    """The verdicts did not change; only where their input comes from."""
    monkeypatch.setattr(G, "fetch_status_rows",
                        lambda *a, **k: [{"text": LIVE_TEXT,
                                          "updated": _just_now()}])
    monkeypatch.setattr(G._env, "load_and_announce", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["is_the_gateway_live.py"])

    code = G.main()

    out = capsys.readouterr().out
    assert "1 THE BANNER" in out and "fallback=gemini:gemini-2.5-flash" in out
    assert "2 THE BEHAVIOUR" in out
    assert code == 0


def test_one_credential_is_still_red_through_the_new_door(monkeypatch, capsys):
    """`fallback=none` is the live shape today (no GEMINI_API_KEY on the
    brain Worker, audit F32) and it must stay a FAIL, not become invisible
    because the source moved."""
    inert = ("worker up · llm=live:deepseek/deepseek-v3.2 · sms=twilio · "
             "primary=openrouter:deepseek/deepseek-v3.2 fallback=none · brain=x")
    monkeypatch.setattr(G, "fetch_status_rows",
                        lambda *a, **k: [{"text": inert, "updated": _just_now()}])
    monkeypatch.setattr(G._env, "load_and_announce", lambda *a, **k: [])
    monkeypatch.setattr(sys, "argv", ["is_the_gateway_live.py"])

    assert G.main() == 1
    assert "deployed, and inert" in capsys.readouterr().out


# ------------------------------------------------- what the worker writes

class _Reply:
    def __init__(self, payload=None, ok=True, status=200):
        self._payload, self.ok, self.status_code = payload or {}, ok, status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeBackend:
    def __init__(self):
        self.rows = []
        self.patches = []

    def get(self, _url, params=None, timeout=None, **_kw):
        filt = (params or {}).get("filter", "")
        items = [r for r in self.rows
                 if r["external_event_id"] in filt or not filt]
        return _Reply({"items": items})

    def post(self, _url, json=None, timeout=None, **_kw):
        row = dict(json or {})
        row["id"] = f"row{len(self.rows) + 1}"
        self.rows.append(row)
        return _Reply({"id": row["id"]})

    def patch(self, url, json=None, timeout=None, **_kw):
        self.patches.append((url.rsplit("/", 1)[-1], dict(json or {})))
        for row in self.rows:
            if row["id"] == url.rsplit("/", 1)[-1]:
                row.update(json or {})
        return _Reply({"id": url.rsplit("/", 1)[-1]})


@pytest.fixture
def backend(monkeypatch):
    fake = FakeBackend()
    monkeypatch.setattr(W, "ACTIVE_OWNER_REF", "qeuy6sv1raof9rw")
    monkeypatch.setattr(W, "ACTIVE_OWNER_ID", "")
    monkeypatch.setattr(W.pb, "get", fake.get)
    monkeypatch.setattr(W.pb, "post", fake.post)
    monkeypatch.setattr(W.pb, "patch", fake.patch)
    monkeypatch.setattr(W, "_GATEWAY_TOTALS",
                        dict.fromkeys(W._GATEWAY_TALLY_KEYS, 0))
    return fake


def test_the_brain_writes_one_status_row_and_then_refreshes_it(backend):
    """One row per owner, ever. Appending a row per beat would flood the
    control half of are_the_ears_live.py and make a silent day look busy."""
    banner = "worker up · primary=openrouter:m fallback=gemini:g · brain=abc"

    assert W.publish_worker_status(banner, "qeuy6sv1raof9rw") is True
    assert W.publish_worker_status(banner, "qeuy6sv1raof9rw") is True
    assert W.publish_worker_status(banner, "qeuy6sv1raof9rw") is True

    assert len(backend.rows) == 1, "the row is refreshed, never re-created"
    assert len(backend.patches) == 2
    row = backend.rows[0]
    assert row["kind"] == "worker_status"
    assert row["external_event_id"] == "worker-status:qeuy6sv1raof9rw"
    assert row["owner_ref"] == "qeuy6sv1raof9rw"
    assert "owner" not in row, "audit F04: events has no owner column"


def test_the_row_carries_what_the_gate_needs_to_read(backend):
    """The contract, both ends in one assertion: what the worker writes must
    satisfy the verdicts the leg runs. A rename on either side fails here."""
    W.publish_worker_status(
        "worker up · llm=live:deepseek/deepseek-v3.2 · sms=twilio · "
        "primary=openrouter:deepseek/deepseek-v3.2 fallback=gemini:gemini-2.5-flash "
        "· brain=5909f7f6aa11", "qeuy6sv1raof9rw")

    text = backend.rows[0]["text"]
    assert G.banner_verdict([text])[0] == 0
    # No calls yet, so the behaviour leg is honestly unproven rather than green.
    assert G.tally_verdict([text])[0] == 2


def test_the_running_totals_reach_the_row(backend):
    """report_gateway resets the per-tick tally, so the row needs its own
    accumulator or the leg's denominator is always zero."""
    class _LLM:
        gateway_tally = {"primary_ok": 3, "rescued": 1, "skipped": 0,
                         "reissued": 0, "both_dead": 0}

    llm = _LLM()
    W.report_gateway(llm)
    llm.gateway_tally.update({"primary_ok": 5, "rescued": 0})
    W.report_gateway(llm)

    W.publish_worker_status("worker up · primary=a:b fallback=c:d", "qeuy6sv1raof9rw")

    text = backend.rows[0]["text"]
    assert "primary_ok=8 rescued=1" in text
    assert G.tally_verdict([text])[0] == 0, "a rescue with a denominator is PROVEN"


def test_a_backend_that_refuses_the_row_never_stops_the_brain(backend, monkeypatch,
                                                              capsys):
    """Bookkeeping must never cost her hearing. A failure is logged, not
    raised, and the worker goes on."""
    monkeypatch.setattr(W.pb, "post", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("backend down")))

    assert W.publish_worker_status("worker up · primary=a:b fallback=c:d",
                                   "qeuy6sv1raof9rw") is False
    assert "worker status row not written" in capsys.readouterr().out


def test_an_unscoped_worker_writes_nothing(backend):
    """No owner_ref, no row: an unscoped row could not be attributed to a
    brain and main() refuses to run unscoped anyway."""
    W.ACTIVE_OWNER_REF = ""
    try:
        assert W.publish_worker_status("worker up · x", "") is False
    finally:
        W.ACTIVE_OWNER_REF = "qeuy6sv1raof9rw"
    assert backend.rows == []
