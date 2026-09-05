"""A second credential is a fallback, not a switch.

brain/llm.py chose its transport by which KEY existed: Gemini if
GEMINI_API_KEY, else OpenRouter if OPENROUTER_API_KEY, else the heuristic.
With both keys set, a Gemini 503 that survived _post_json's three attempts, a
timeout, or a reply with no text raised straight out of LLM.chat() while a
working OpenRouter credential idled. On the transcript loop that is a held
line, a climbing deaf streak, and after three lines a text to the owner saying
she "cannot reach the model" — sent while a model she could reach sat unused.
The empty-reply case was a tombstone: ValueError is not on the worker's
_UNREACHABLE list, so the spoken line was stamped "error" and never retried.

Now the keyed transports are ordered and the fallback carries the call when
the primary's machine is absent. Every case below drives the REAL LLM.chat(),
the real _post_json (its three attempts are counted), and the real
_gemini/_openrouter parsers, through an httpx.Client double that routes by
HOST and answers each host from a scripted list of (status, body).

Three things are pinned in BOTH directions, because each has a wrong side:

  * WHAT FALLS THROUGH versus WHAT IS REMEMBERED. Any exception from the
    primary falls through, but only a transport-typed one starts the
    one-minute cooldown. An empty Gemini reply is a SAFETY refusal or a
    thoughts-only answer — that one line's CONTENT — and letting it move the
    next minute of every call onto another model would be content steering
    the wire, the thing HARNESS-LAWS.md LAW 1 exists to keep out.
  * WHICH EXCEPTION LEAVES when both wires die. The transport-typed one, the
    primary's first, so brain/worker.py's hold-or-tombstone split still HOLDS
    a line the primary merely missed even when the fallback's reply was
    unparseable — and still tombstones a defect that is ours on both wires.
  * WHAT AN ORDINARY DAY PAYS. One credential: the identical path, no try,
    no clock, no print, no tally. Two credentials and a healthy primary: one
    clock read, no second request, no print.
"""
from urllib.parse import urlparse

import httpx
import pytest

import brain.llm as llm_mod
from brain.llm import LLM

GEMINI_HOST = "generativelanguage.googleapis.com"
OPENROUTER_HOST = "openrouter.ai"


def gemini_ok(text='{"decision":"ignore"}', reason="STOP"):
    return (200, {"candidates": [{"content": {"parts": [{"text": text}]},
                                  "finishReason": reason}]})


def openrouter_ok(text='{"decision":"ignore"}', reason="stop"):
    return (200, {"choices": [{"message": {"content": text},
                               "finish_reason": reason}], "usage": {}})


# A refusal: 200, a candidate, and not one character of text.
GEMINI_EMPTY = (200, {"candidates": [{"content": {"parts": []},
                                      "finishReason": "SAFETY"}]})
GEMINI_TRUNCATED = gemini_ok('{"decision":"ig', "MAX_TOKENS")
# OpenRouter really does answer 200 with an error body; our parser then
# raises KeyError("choices") — a defect-shaped exception for a dead model.
OPENROUTER_GARBAGE = (200, {"error": {"message": "model not found"}})
DOWN = (503, {"error": "overloaded"})


class _Wire:
    """One host's script. Each post answers the next (status, body); the last
    one repeats forever, so a wire scripted [DOWN] is down for good."""

    def __init__(self, *script):
        assert script, "a wire needs at least one answer"
        self.script = list(script)
        self.posts = 0
        self.payloads: list = []

    def answer(self, url, payload):
        self.posts += 1
        self.payloads.append(payload)
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, BaseException):
            raise step
        status, body = step
        # A REAL httpx.Response, so raise_for_status raises the real
        # HTTPStatusError the worker classifies, not a stand-in.
        return httpx.Response(status, json=body,
                              request=httpx.Request("POST", url))


@pytest.fixture
def wires(monkeypatch):
    """Both keys set, today's default order, fast retries, and an
    httpx.Client that routes each POST to the wire scripted for its host."""
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-secret-either")
    monkeypatch.setattr(llm_mod, "_RETRY_BASE_SECONDS", 0.001)
    monkeypatch.setattr(llm_mod, "_TRANSPORT_ORDER", ("gemini", "openrouter"))
    table: dict = {}

    class _Client:
        def __init__(self, timeout):
            assert timeout == 60

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, headers=None, json=None):
            host = urlparse(url).hostname
            assert host in table, f"nothing scripted for {host}"
            return table[host].answer(url, json)

    monkeypatch.setattr(llm_mod.httpx, "Client", _Client)

    def script(gemini=None, openrouter=None):
        if gemini is not None:
            table[GEMINI_HOST] = _Wire(*gemini)
        if openrouter is not None:
            table[OPENROUTER_HOST] = _Wire(*openrouter)
        return table

    return script


def _stamps(monkeypatch):
    """tests/test_outage_holds_the_line.py's fixture: drive the REAL
    record_failure and watch what it stamps."""
    import brain.worker as W
    marked: list = []
    monkeypatch.setattr(W, "mark_processed",
                        lambda event_id, decision, **k:
                        marked.append((event_id, decision)) or True)
    monkeypatch.setattr(W, "DEAF_STREAK", 0)
    return W, marked


# ------------------------------------------------------- the fall-through

def test_a_dead_primary_is_rescued_by_the_second_credential(wires, capsys):
    """THE mutation: a bare `raise` in _fall_through's first except lets the
    HTTPStatusError escape where mode=="openrouter" is asserted."""
    t = wires(gemini=[DOWN], openrouter=[openrouter_ok()])

    res = LLM().chat("Return JSON.", "hello", temperature=0)

    assert res.mode == "openrouter"
    assert res.fell_through_from == "gemini"
    assert res.text == '{"decision":"ignore"}'
    assert t[GEMINI_HOST].posts == 3, (
        "retry stays INSIDE the transport: the primary gets its three "
        "attempts before anything falls through")
    assert t[OPENROUTER_HOST].posts == 1
    out = capsys.readouterr().out
    assert "llm: gateway gemini HTTPStatusError -> trying openrouter" in out
    assert "llm: gateway openrouter answered for gemini" in out


def test_a_gemini_reply_with_no_text_is_rescued(wires):
    """The tombstone case. ValueError("Gemini returned no text") used to
    reach record_failure, which is not an outage type, so the line died."""
    t = wires(gemini=[GEMINI_EMPTY], openrouter=[openrouter_ok()])

    res = LLM().chat("Return JSON.", "hello")

    assert res.mode == "openrouter" and res.fell_through_from == "gemini"
    assert t[GEMINI_HOST].posts == 1, "an answered 200 is not retried"


def test_an_empty_reply_does_not_start_the_cooldown(wires):
    """Attack case (b). A refusal is that one line's content. Remembering it
    as "the primary is down" would move the next minute of every call onto
    another model because of what one sentence said."""
    t = wires(gemini=[GEMINI_EMPTY, gemini_ok()], openrouter=[openrouter_ok()])
    llm = LLM()

    first = llm.chat("Return JSON.", "hello")
    assert first.mode == "openrouter"
    assert llm._primary_down_until == 0.0

    second = llm.chat("Return JSON.", "hello again")
    assert second.mode == "gemini" and second.fell_through_from == ""
    assert t[GEMINI_HOST].posts == 2, "the primary is asked again at once"
    assert t[OPENROUTER_HOST].posts == 1


def test_a_transport_fault_is_remembered_for_a_minute_then_probed(
        wires, monkeypatch):
    """The other polarity of the same check: a machine-absent failure IS
    remembered, and the memory is bounded by the clock, not by the reply."""
    clock = {"t": 1000.0}
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: clock["t"])
    t = wires(gemini=[DOWN, DOWN, DOWN, gemini_ok()],
              openrouter=[openrouter_ok()])
    llm = LLM()

    one = llm.chat("Return JSON.", "one")
    assert one.mode == "openrouter" and t[GEMINI_HOST].posts == 3

    clock["t"] += 10
    two = llm.chat("Return JSON.", "two")
    assert two.mode == "openrouter" and two.fell_through_from == "gemini"
    assert t[GEMINI_HOST].posts == 3, "inside the minute the primary is skipped"
    assert t[OPENROUTER_HOST].posts == 2
    assert llm.gateway_tally["skipped"] == 1

    clock["t"] += 51          # 61s after the fault
    three = llm.chat("Return JSON.", "three")
    assert three.mode == "gemini" and three.fell_through_from == ""
    assert t[GEMINI_HOST].posts == 4, "at the minute the primary is probed"


def test_a_fallback_failure_during_cooldown_probes_the_primary_in_the_same_call(
        wires):
    """Attack case (c). The safe side is "forget what you knew when both are
    down" — probe now, in this call, rather than raise with the primary
    untried and then wait out the minute."""
    t = wires(gemini=[gemini_ok()], openrouter=[DOWN])
    llm = LLM()
    llm._primary_down_until = llm_mod.time.monotonic() + 60

    res = llm.chat("Return JSON.", "hello")

    assert res.mode == "gemini" and res.fell_through_from == ""
    assert llm._primary_down_until == 0.0
    assert t[OPENROUTER_HOST].posts == 3 and t[GEMINI_HOST].posts == 1
    assert llm.gateway_tally == {"primary_ok": 1, "rescued": 0, "skipped": 1,
                                 "reissued": 0, "both_dead": 0}


# ----------------------------------------------------------- truncation

def test_a_truncated_primary_is_reissued_once_on_the_fallback(wires, capsys):
    """MAX_TOKENS is the provider's own enum about its output LENGTH — a
    positive signal, and the second trigger. Attack case (e): the re-issue
    changes which model composes prose for his phone, so it says so."""
    t = wires(gemini=[GEMINI_TRUNCATED], openrouter=[openrouter_ok()])
    llm = LLM()

    res = llm.chat("Return JSON.", "hello")

    assert res.mode == "openrouter" and res.fell_through_from == "gemini"
    assert res.truncated is False
    assert t[GEMINI_HOST].posts == 1 and t[OPENROUTER_HOST].posts == 1
    assert llm.gateway_tally["reissued"] == 1
    assert llm._primary_down_until == 0.0, (
        "the primary ANSWERED; truncation never starts the cooldown")
    out = capsys.readouterr().out
    assert "llm: gateway gemini truncated -> reissuing on openrouter" in out
    assert "llm: gateway openrouter answered for gemini (truncation)" in out


def test_a_truncated_primary_whose_fallback_dies_is_returned_with_the_flag(
        wires):
    """An answer with an honest flag beats no answer; _voice and triage
    already handle the flag."""
    wires(gemini=[GEMINI_TRUNCATED], openrouter=[DOWN])
    llm = LLM()

    res = llm.chat("Return JSON.", "hello")

    assert res.mode == "gemini" and res.truncated is True
    assert res.fell_through_from == ""
    assert llm._primary_down_until == 0.0


# ------------------------------------------- both dead: what leaves chat()

def test_both_dead_hands_the_worker_the_primarys_transport_fault(
        wires, monkeypatch):
    """Rule R when both are transport-typed: the primary's, chained from the
    fallback's. The worker holds the line — and now "cannot reach the model"
    is TRUE when it is eventually said."""
    wires(gemini=[DOWN], openrouter=[DOWN])

    with pytest.raises(httpx.HTTPStatusError) as caught:
        LLM().chat("Return JSON.", "hello")

    exc = caught.value
    assert GEMINI_HOST in str(exc.request.url), "the primary's is preferred"
    assert isinstance(exc.__cause__, httpx.HTTPStatusError)
    assert OPENROUTER_HOST in str(exc.__cause__.request.url)
    W, marked = _stamps(monkeypatch)
    assert W.unreachable_model(exc) is True
    assert W.record_failure("ev1", "book dinner thursday", exc) == "held"
    assert marked == []


def test_a_fallback_that_answered_garbage_does_not_bury_a_line_the_primary_only_missed(
        wires, monkeypatch):
    """Attack case (a), the worst new outcome the first design allowed:
    primary 503 (held today) plus a fallback answering 200 with an error
    body (KeyError in our parser, a tombstone) must leave as the 503. The
    mutation `raise second from first` turns this red."""
    wires(gemini=[DOWN], openrouter=[OPENROUTER_GARBAGE])

    with pytest.raises(httpx.HTTPStatusError) as caught:
        LLM().chat("Return JSON.", "hello")

    assert isinstance(caught.value.__cause__, KeyError)
    W, marked = _stamps(monkeypatch)
    assert W.record_failure("ev1", "book dinner thursday", caught.value) == "held"
    assert marked == [], "the line WAITED before this port; it must not DIE"


def test_a_garbage_fallback_during_cooldown_still_surfaces_the_primarys_fault(
        wires, monkeypatch):
    """Same rule on the cooldown path: the fallback's KeyError is not the
    verdict when the probe finds the primary's machine still absent."""
    wires(gemini=[DOWN], openrouter=[OPENROUTER_GARBAGE])
    llm = LLM()
    llm._primary_down_until = llm_mod.time.monotonic() + 60

    with pytest.raises(httpx.HTTPStatusError) as caught:
        llm.chat("Return JSON.", "hello")

    assert isinstance(caught.value.__cause__, KeyError)
    assert llm._primary_down_until == 0.0
    W, marked = _stamps(monkeypatch)
    assert W.record_failure("ev1", "book dinner thursday", caught.value) == "held"
    assert marked == []


def test_when_the_defect_is_ours_on_both_wires_the_tombstone_survives(
        wires, monkeypatch):
    """Attack case (e). A refusal on one wire and our parser on the other:
    identical input through identical code cannot come out differently, and
    holding it would park a poisoned line at the head of the queue forever."""
    wires(gemini=[GEMINI_EMPTY], openrouter=[OPENROUTER_GARBAGE])

    with pytest.raises(KeyError) as caught:
        LLM().chat("Return JSON.", "hello")

    assert isinstance(caught.value.__cause__, ValueError)
    W, marked = _stamps(monkeypatch)
    assert W.unreachable_model(caught.value) is False
    assert W.record_failure("ev2", "book dinner thursday", caught.value) == "error"
    assert marked == [("ev2", "error")]


# ------------------------------------------------- an ordinary day pays nothing

def test_one_credential_pays_nothing_new_and_raises_exactly_as_before(
        wires, monkeypatch, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY")
    t = wires(gemini=[DOWN], openrouter=[openrouter_ok()])
    llm = LLM()
    assert llm.transport_names() == ["gemini"]

    with pytest.raises(httpx.HTTPStatusError):
        llm.chat("Return JSON.", "hello")

    assert t[GEMINI_HOST].posts == 3 and t[OPENROUTER_HOST].posts == 0
    assert "llm: gateway" not in capsys.readouterr().out
    assert llm._primary_down_until == 0.0
    assert not any(llm.gateway_tally.values())


def test_a_healthy_primary_pays_nothing_new(wires, capsys):
    t = wires(gemini=[gemini_ok()], openrouter=[openrouter_ok()])
    llm = LLM()

    res = llm.chat("Return JSON.", "hello")

    assert res.mode == "gemini" and res.fell_through_from == ""
    assert t[OPENROUTER_HOST].posts == 0, "the fallback is never even built into a request"
    assert "llm: gateway" not in capsys.readouterr().out
    assert llm.gateway_tally == {"primary_ok": 1, "rescued": 0, "skipped": 0,
                                 "reissued": 0, "both_dead": 0}


# ------------------------------------------------------------- the order

def test_the_order_variable_makes_openrouter_primary_and_gemini_its_fallback(
        wires, monkeypatch):
    """The live precondition: ANTICIPY_LLM_ORDER=openrouter,gemini keeps the
    Railway primary where it is and makes Gemini-direct the backup."""
    monkeypatch.setattr(llm_mod, "_TRANSPORT_ORDER", ("openrouter", "gemini"))
    t = wires(gemini=[gemini_ok()], openrouter=[DOWN])

    res = LLM().chat("Return JSON.", "hello")

    assert res.mode == "gemini" and res.fell_through_from == "openrouter"
    assert t[OPENROUTER_HOST].posts == 3 and t[GEMINI_HOST].posts == 1


@pytest.mark.parametrize("order, expected", [
    (("openrouter",), ["openrouter", "gemini"]),
    (("bogus", "gemini"), ["gemini", "openrouter"]),
    ((), ["gemini", "openrouter"]),
    (("gemini", "gemini", "openrouter"), ["gemini", "openrouter"]),
])
def test_a_typo_in_the_order_can_silence_nothing(wires, monkeypatch,
                                                  order, expected):
    monkeypatch.setattr(llm_mod, "_TRANSPORT_ORDER", order)
    wires(gemini=[gemini_ok()], openrouter=[openrouter_ok()])
    assert LLM().transport_names() == expected


# ----------------------------------------------------- the aux split holds

def test_the_aux_split_does_not_move_when_the_wire_does(wires, monkeypatch):
    """A mechanical call that falls through lands on the fallback's aux
    model; a judgement call — even one skipped straight to the fallback by
    the cooldown — never lands on an aux model on any wire."""
    monkeypatch.setattr(llm_mod, "AUX_MODEL", "google/gemini-2.5-flash-lite")
    t = wires(gemini=[DOWN], openrouter=[openrouter_ok()])
    llm = LLM()

    mechanical = llm.chat("Extract facts.", "hello", aux=True)
    assert mechanical.mode == "openrouter"
    assert mechanical.used_model == "google/gemini-2.5-flash-lite"
    assert t[OPENROUTER_HOST].payloads[-1]["model"] == "google/gemini-2.5-flash-lite"

    judged = llm.chat("Decide.", "hello")     # cooldown: straight to the fallback
    assert judged.mode == "openrouter" and judged.fell_through_from == "gemini"
    assert judged.used_model == llm.model
    assert t[OPENROUTER_HOST].payloads[-1]["model"] == llm.model


# ------------------------------------------------------------- the tally

def test_the_tally_says_what_carried_each_call(wires):
    """Attack case (d). Without primary_ok, "the primary answered 900 and
    the fallback 3" and "the primary answered nothing" are the same log."""
    wires(gemini=[DOWN, DOWN, DOWN, gemini_ok()], openrouter=[openrouter_ok()])
    llm = LLM()

    llm.chat("Return JSON.", "one")            # rescued
    llm._primary_down_until = 0.0              # forget, so the primary is asked
    llm.chat("Return JSON.", "two")            # primary_ok

    assert llm.gateway_tally == {"primary_ok": 1, "rescued": 1, "skipped": 0,
                                 "reissued": 0, "both_dead": 0}


def test_the_worker_prints_the_tally_once_and_resets_it(wires, capsys):
    import brain.worker as W
    wires(gemini=[DOWN], openrouter=[openrouter_ok()])
    llm = LLM()
    llm.chat("Return JSON.", "one")
    capsys.readouterr()

    line = W.report_gateway(llm)

    assert line == ("llm: gateway tally primary_ok=0 rescued=1 skipped=0 "
                    "reissued=0 both_dead=0")
    assert line in capsys.readouterr().out
    assert not any(llm.gateway_tally.values())
    assert W.report_gateway(llm) == "", "a tick with nothing to say prints nothing"
    assert "tally" not in capsys.readouterr().out


def test_the_boot_banner_names_the_primary_and_the_fallback(wires, monkeypatch):
    import brain.worker as W
    wires(gemini=[gemini_ok()], openrouter=[openrouter_ok()])
    assert W.gateway_banner(LLM()) == (
        f"primary=gemini:gemini-2.5-flash fallback=openrouter:{llm_mod.DEFAULT_MODEL}")
    monkeypatch.delenv("GEMINI_API_KEY")
    assert W.gateway_banner(LLM()) == (
        f"primary=openrouter:{llm_mod.DEFAULT_MODEL} fallback=none")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert W.gateway_banner(LLM()) == "primary=heuristic fallback=none"


def test_the_loop_prints_both():
    """A tested line main() does not print is a comment.

    The banner is now built into `boot_banner` before it is printed, because
    on Cloudflare printing it is not enough to make it readable (audit F34):
    the same string is also written to the worker_status row. Same two
    assertions as before, plus the row, at the new anchor.
    """
    import brain.worker as W
    source = open(W.__file__, encoding="utf-8").read()
    banner = source[source.index("boot_banner = ("):]
    banner = banner[:banner.index("_brain_fingerprint()")]
    assert "gateway_banner(llm)" in banner
    loop = source[source.index("report_deafness(anticipy)\n"):]
    loop = loop[:loop.index("run_nightly_consolidation(memory)")]
    assert "report_gateway(llm)" in loop
    # And the CLI-readable copy: written at boot and refreshed on the beat.
    boot = source[source.index("print(boot_banner)"):]
    assert "publish_worker_status(boot_banner" in boot[:800]
    assert "publish_worker_status(boot_banner" in loop


# ------------------------------------------------ the live leg's verdicts

def _tally(**counts) -> str:
    keys = ("primary_ok", "rescued", "skipped", "reissued", "both_dead")
    return "llm: gateway tally " + " ".join(f"{k}={counts.get(k, 0)}" for k in keys)


def test_the_live_leg_reads_the_banner():
    from overnight import is_the_gateway_live as G
    assert G.banner_verdict([])[0] == 2
    assert G.banner_verdict(["worker up · llm=live:x · sms=mock · brain=abc"])[0] == 1
    assert G.banner_verdict([
        "worker up · llm=live:x · primary=openrouter:x fallback=none · brain=abc",
    ])[0] == 1, "deployed and inert is not done"
    assert G.banner_verdict([
        "worker up · llm=live:x · primary=openrouter:x fallback=none · brain=abc",
        "heard: 'a line' -> ignore",
        "worker up · llm=live:x · primary=openrouter:x fallback=gemini:y · brain=def",
    ])[0] == 0, "the NEWEST banner decides"


def test_the_live_leg_needs_a_denominator():
    from overnight import is_the_gateway_live as G
    assert G.tally_verdict(["heard: 'a line' -> ignore"])[0] == 2
    assert G.tally_verdict([_tally(primary_ok=40)])[0] == 2, "healthy proves nothing about the fallback"
    assert G.tally_verdict([_tally(primary_ok=40), _tally(rescued=2)])[0] == 0
    assert G.tally_verdict([_tally(rescued=3), _tally(skipped=9, rescued=9)])[0] == 1, (
        "the primary answered nothing all window")
    assert G.tally_verdict([_tally(both_dead=4)])[0] == 1
    assert G.tally_verdict([
        _tally(primary_ok=5),
        "llm: gateway openrouter HTTPStatusError -> trying gemini",
        "llm: gateway gemini answered for openrouter",
        _tally(rescued=1),
    ])[0] == 0
    assert G.tally_verdict([
        _tally(primary_ok=5),
        "llm: gateway openrouter HTTPStatusError -> trying gemini",
        _tally(rescued=1),
        "heard: 'a line' -> ignore",
        "llm: gateway openrouter HTTPStatusError -> trying gemini",
        _tally(primary_ok=2),
    ])[0] == 1, "a fall-through that started and never finished"
