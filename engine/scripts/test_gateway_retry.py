"""Gateway 429 retry-hint honoring (ledger F7 residual) — deterministic, zero network.

The live brain is Gemini free tier: per-minute quota 429s are a when-not-if, and the
server states its own wait (RetryInfo retryDelay in the body, "Please retry in Ns" in
the message on the OpenAI-compat endpoint, Retry-After header on OpenRouter). Pins:
  - _retry_hint_seconds reads header > RetryInfo (string or {seconds,nanos}) > message
    phrase; handles the array-wrapped compat body; malformed/absent -> None, never raises.
  - A short hint (<= inline cap) is slept inline (+margin) and the call recovers.
  - A LONG hint fails fast: ONE request, no blind hammering of a closed quota window,
    "" returned so the decider's UNAVAILABLE -> defer path owns the wait (F7 contract).
  - No hint -> the blind backoff is byte-identical to the pre-change behavior.
  - 5xx never consults hints (429-only scope).
  - Short hints cannot unbound the loop: 4 attempts max, then "".
  - End-to-end: a long-hint 429 storm reaches the Decider as UNAVAILABLE after a
    single request — deafness detected fast and cheap, never read as judgment.

All HTTP goes through httpx.MockTransport; asyncio.sleep is recorded, not awaited.
Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_gateway_retry.py
"""
import asyncio
import os

# deterministic standalone: dummy key (never sent anywhere — MockTransport intercepts
# every request), unroutable base URL, stub provider for anything constructed bare
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_MODEL_API_KEY"] = "test-key-not-real"
os.environ["ANTICIPY_OPENAI_BASE_URL"] = "https://mock.invalid/chat/completions"

import httpx

import anticipy_engine.core.gateway as gw_mod
from anticipy_engine.core.gateway import (
    CHEAP,
    RETRY_HINT_INLINE_CAP_S,
    RETRY_HINT_MARGIN_S,
    ModelGateway,
    _retry_hint_seconds,
)
from anticipy_engine.proactive.decider import UNAVAILABLE, Decider

OK_BODY = {"choices": [{"message": {"content": "SILENT"}}]}

GEMINI_429_WITH_RETRYINFO = {  # native shape observed on the free tier
    "error": {
        "code": 429,
        "message": "You exceeded your current quota.",
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": []},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "21s"},
        ],
    }
}
GEMINI_429_DETAILLESS = {  # second observed variant: no details[] at all
    "error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota).",
              "status": "RESOURCE_EXHAUSTED"}
}
COMPAT_429_ARRAY_MSG_ONLY = [  # OpenAI-compat endpoint: array-wrapped, hint only in message
    {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
               "message": "Quota exceeded ... Please retry in 17.646654881s."}}
]


def gemini_429(delay: str) -> dict:
    return {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "quota",
                      "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo",
                                   "retryDelay": delay}]}}


class ScriptedTransport:
    """MockTransport handler walking a response script (last entry repeats)."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = 0

    def __call__(self, request) -> httpx.Response:
        self.requests += 1
        spec = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        status, headers, body = spec
        return httpx.Response(status, headers=headers, json=body)


class SleepRecorder:
    def __init__(self): self.sleeps = []
    async def __call__(self, seconds): self.sleeps.append(round(seconds, 6))


def make_gw(script):
    transport = ScriptedTransport(script)
    gw = ModelGateway(provider="openrouter",
                      transport=httpx.MockTransport(transport))
    return gw, transport


async def main():
    # ---- 1) _retry_hint_seconds: every observed shape, malformed -> None ----
    r = lambda **kw: httpx.Response(429, **kw)
    assert _retry_hint_seconds(r(headers={"Retry-After": "3"})) == 3.0
    assert _retry_hint_seconds(r(headers={"Retry-After": "1.5"})) == 1.5
    assert _retry_hint_seconds(  # HTTP-date form: no wall clock here -> no hint
        r(headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})) is None
    assert _retry_hint_seconds(r(json=GEMINI_429_WITH_RETRYINFO)) == 21.0
    got = _retry_hint_seconds(r(json=gemini_429("15.002899939s")))
    assert got is not None and abs(got - 15.002899939) < 1e-6
    assert _retry_hint_seconds(r(json=gemini_429("1s"))) == 1.0  # per-day tiny hint: fine, loop is bounded
    obj = {"error": {"code": 429, "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo",
         "retryDelay": {"seconds": 3, "nanos": 500000000}}]}}
    assert _retry_hint_seconds(r(json=obj)) == 3.5
    got = _retry_hint_seconds(r(json=COMPAT_429_ARRAY_MSG_ONLY))
    assert got is not None and abs(got - 17.646654881) < 1e-6
    assert _retry_hint_seconds(r(json=GEMINI_429_DETAILLESS)) is None
    assert _retry_hint_seconds(r(content=b"upstream choked, not json")) is None
    # header is most authoritative: wins over a body hint
    assert _retry_hint_seconds(
        r(headers={"Retry-After": "2"}, json=GEMINI_429_WITH_RETRYINFO)) == 2.0
    print("PASS hint parse: header > RetryInfo (str+obj) > message; array wrap; "
          "detail-less/garbage -> None")

    real_sleep = asyncio.sleep
    rec = SleepRecorder()
    gw_mod.asyncio.sleep = rec
    try:
        # ---- 2) short hint: slept inline (+margin), call recovers ----
        gw, t = make_gw([(429, {}, gemini_429("2s")), (200, {}, OK_BODY)])
        out = await gw.think("line", tier=CHEAP, caller="decider")
        assert out == "SILENT" and t.requests == 2
        assert rec.sleeps == [2 + RETRY_HINT_MARGIN_S]
        assert gw.calls[-1]["retry_hint_s"] == 2.0  # postmortem breadcrumb
        print("PASS short hint: one inline sleep at the server's number, recovered")

        # ---- 3) long hint: ONE request, zero sleeps, "" -> the defer path owns it ----
        rec.sleeps.clear()
        gw, t = make_gw([(429, {}, GEMINI_429_WITH_RETRYINFO)])
        out = await gw.think("line", tier=CHEAP, caller="decider")
        assert out == "" and t.requests == 1 and rec.sleeps == []
        assert gw.calls[-1]["retry_hint_s"] == 21.0
        assert 21.0 > RETRY_HINT_INLINE_CAP_S  # the pin only means something above the cap
        print("PASS long hint: fast-fail after a single request, no window hammering")

        # ---- 4) compat array body, hint only in the message text: same fast-fail ----
        rec.sleeps.clear()
        gw, t = make_gw([(429, {}, COMPAT_429_ARRAY_MSG_ONLY)])
        out = await gw.think("line", tier=CHEAP, caller="decider")
        assert out == "" and t.requests == 1 and rec.sleeps == []
        assert abs(gw.calls[-1]["retry_hint_s"] - 17.646654881) < 1e-6
        print("PASS compat shape: array-wrapped, message-phrase hint honored")

        # ---- 5) no hint: blind backoff byte-identical to pre-change behavior ----
        rec.sleeps.clear()
        gw, t = make_gw([(429, {}, GEMINI_429_DETAILLESS)])
        out = await gw.think("line", tier=CHEAP, caller="decider")
        assert out == "" and t.requests == 4
        assert rec.sleeps == [1.5, 3.0, 4.5, 6.0]
        print("PASS no hint: unchanged 4-attempt blind backoff")

        # ---- 6) sustained outage with short hints stays bounded: 4 attempts max ----
        rec.sleeps.clear()
        gw, t = make_gw([(429, {}, gemini_429("2s"))])
        out = await gw.think("line", tier=CHEAP, caller="decider")
        assert out == "" and t.requests == 4
        assert rec.sleeps == [2 + RETRY_HINT_MARGIN_S] * 4
        print("PASS bounded: short hints cannot unbound the retry loop")

        # ---- 7) 5xx never consults hints (429-only scope) ----
        rec.sleeps.clear()
        gw, t = make_gw([(503, {"Retry-After": "30"}, None), (200, {}, OK_BODY)])
        out = await gw.think("line", tier=CHEAP, caller="decider")
        assert out == "SILENT" and t.requests == 2
        assert rec.sleeps == [1.5], "5xx must keep blind backoff, never a 30s hint sleep"
        print("PASS 5xx: hint ignored, blind backoff unchanged")

        # ---- 8) OpenRouter style: Retry-After header, short -> inline recovery ----
        rec.sleeps.clear()
        gw, t = make_gw([(429, {"Retry-After": "1"}, GEMINI_429_DETAILLESS),
                         (200, {}, OK_BODY)])
        out = await gw.think("line", tier=CHEAP, caller="decider")
        assert out == "SILENT" and t.requests == 2
        assert rec.sleeps == [1 + RETRY_HINT_MARGIN_S]
        print("PASS Retry-After header: honored inline")

        # ---- 9) F7 end-to-end: a long-hint 429 storm is UNAVAILABLE after ONE call ----
        rec.sleeps.clear()
        gw, t = make_gw([(429, {}, GEMINI_429_WITH_RETRYINFO)])
        word = await Decider(gw).decide("Remind me to stretch at six tomorrow")
        assert word == UNAVAILABLE and t.requests == 1
        print("PASS F7 e2e: quota storm -> single request -> UNAVAILABLE (defer path), "
              "never read as judgment")
    finally:
        gw_mod.asyncio.sleep = real_sleep

    print("ALL GATEWAY RETRY TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
