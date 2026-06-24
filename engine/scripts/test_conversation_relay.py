"""Two-way voice transport — Twilio ConversationRelay over the /cr websocket.

The 2:45 call is two-way: the owner speaks, Anticipy answers, on one live call. Twilio's
ConversationRelay carries the speech<->text; the engine answers with the SAME Room 1.5
decider the always-listening loop runs. This test proves that loop end-to-end with a
SIMULATED ConversationRelay exchange — a TestClient websocket plays Twilio, sends prompt
frames, and asserts the brain's reply streams back token-by-token. NO real Twilio call:
this is dev-proven; live needs Twilio + Omar's phone.

What it pins:
  - TwiML: the outbound call uses <Connect><ConversationRelay url=wss://...> (two-way) when
    a public wss URL is configured, and keeps the one-shot <Say> as the no-LLM fallback;
    attributes are XML-escaped and bounded under Twilio's 4000-char cap.
  - Brain reuse: the /cr handler answers with the SAME Decider (ACT/ASK/SILENT), never a
    fork — money/contact streams the ASK reply, a safe task the ACT reply, a vent the
    SILENT reply, and the {type:"end"} frame carries the brain's verdict in handoffData.
  - Streaming: the reply arrives as a sequence of {type:"text", token} frames whose
    concatenation reconstructs the spoken sentence exactly, closed by a last:true frame.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_conversation_relay.py
"""
import asyncio
import os
import tempfile

# Force the free, deterministic stub brain + mock hands (no Twilio, no model spend).
os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_CR_BRAIN", "decider")  # this test asserts the decider verdict brain; the warm OnboardingCallBrain is the /cr default
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")
os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy-cr-")
os.environ.pop("ANTICIPY_CHANNELS_MODE", None)  # never construct a live Twilio transport

from anticipy_engine.channels.call import CallChannel  # noqa: E402
from anticipy_engine.channels.conversation_relay import (  # noqa: E402
    ConversationRelayBrain,
    RelayTurn,
    stream_tokens,
)
from anticipy_engine.proactive.decider import ACT, ASK, SILENT  # noqa: E402


# ----------------------------------------------------------------------------------
# 1) TwiML: two-way ConversationRelay vs the one-shot <Say> fallback.
# ----------------------------------------------------------------------------------
def test_twiml():
    ch = CallChannel()

    # Fallback: no public wss URL -> the no-LLM one-shot <Say>.
    os.environ.pop("ANTICIPY_CR_WSS_URL", None)
    fb = ch.call_twiml("calendar event made; I'll call you at 2:45")
    assert fb.startswith("<Response><Say") and fb.endswith("</Say></Response>"), fb  # <Say voice=...>

    assert "ConversationRelay" not in fb, fb

    # Two-way: a wss URL configured -> <Connect><ConversationRelay url=...>.
    os.environ["ANTICIPY_CR_WSS_URL"] = "wss://anticipy.example.com/cr"
    try:
        two = ch.call_twiml('Hi Omar — say "go" & I\'ll handle it')
        assert "<Connect>" in two and "<ConversationRelay" in two, two
        assert 'url="wss://anticipy.example.com/cr"' in two, two
        assert "welcomeGreeting=" in two, two
        # XML-safe inside the double-quoted attributes (& and the inner quote escaped).
        assert "&amp;" in two and "&quot;" in two and '& I' not in two, two
        # Bounded well under Twilio's 4000-char Twiml cap even for a long greeting.
        assert len(CallChannel.conversation_relay_twiml(
            "wss://x/cr", "x" * 9000)) < 4000, "Twiml parameter bound violated"
    finally:
        os.environ.pop("ANTICIPY_CR_WSS_URL", None)

    # A non-wss (http) URL is rejected as a public relay target -> fallback stands.
    os.environ["ANTICIPY_CR_WSS_URL"] = "https://not-secure/cr"
    try:
        assert "ConversationRelay" not in ch.call_twiml("hi"), "http URL must not attach a relay"
    finally:
        os.environ.pop("ANTICIPY_CR_WSS_URL", None)
    print("PASS twiml: two-way ConversationRelay when wss configured, <Say> fallback otherwise")


# ----------------------------------------------------------------------------------
# 2) stream_tokens: chunks reassemble to the exact sentence.
# ----------------------------------------------------------------------------------
def test_stream_tokens():
    text = "Got it — I'll take care of that."
    toks = list(stream_tokens(text))
    assert len(toks) > 1, "a sentence must stream as multiple tokens"
    assert "".join(toks) == text, ("token concat must reconstruct the reply exactly", toks)
    assert list(stream_tokens("")) == [], "empty reply streams nothing"
    print("PASS stream_tokens: word-ish tokens reassemble to the exact reply")


# ----------------------------------------------------------------------------------
# 3) The brain reuse: the SAME Decider drives ACT/ASK/SILENT replies.
# ----------------------------------------------------------------------------------
def test_brain_reuse():
    from anticipy_engine.core.gateway import ModelGateway
    from anticipy_engine.proactive.decider import Decider

    gw = ModelGateway(provider="stub")
    brain = ConversationRelayBrain.from_gateway(gw)
    # It holds a real Decider (the proactive brain), not a private copy of the logic.
    assert isinstance(brain.decider, Decider), "the relay must reuse the Decider class"

    async def verdict_of(line):
        turn = await brain.turn(line)
        assert isinstance(turn, RelayTurn)
        assert turn.reply == ConversationRelayBrain.render(turn.verdict), "reply must match verdict"
        assert turn.handoff_data()["verdict"] == turn.verdict
        return turn

    act = asyncio.run(verdict_of("remind me to grab milk on the way home"))
    assert act.verdict == ACT and "take care of that" in act.reply, act

    ask = asyncio.run(verdict_of("pay the babysitter 40 bucks tonight"))
    assert ask.verdict == ASK and ("hold it" in ask.reply or "say go" in ask.reply), ask

    silent = asyncio.run(verdict_of("ugh this traffic is unbelievable today"))
    assert silent.verdict == SILENT and "keep that in mind" in silent.reply, silent
    print("PASS brain_reuse: the relay answers with the SAME decider verdicts (ACT/ASK/SILENT)")


# ----------------------------------------------------------------------------------
# 3b) The LIVE brain SPEAKS: with a real model behind the line the spoken reply is a
#     natural model sentence (Omar's ask), GROUNDED in the verdict, never the canned line.
#     Stub/keyless/error still falls back to the deterministic verdict phrasing.
# ----------------------------------------------------------------------------------
def test_live_brain_speaks():
    class FakeLiveGateway:
        """A 'real' provider: the decider's think (caller=decider) returns the verdict word;
        the reply's think (caller=agent) returns a live, natural sentence + records its prompt."""
        provider = "openrouter"

        def __init__(self):
            self.reply_prompt = None

        async def think(self, task, tier, caller, **k):
            if caller == "decider":
                return ASK if "pay" in task.lower() or "transfer" in task.lower() else ACT
            self.reply_prompt = task
            return "Sure thing — I'll hold the landlord transfer until you give me the word."

    from anticipy_engine.proactive.decider import Decider

    gw = FakeLiveGateway()
    brain = ConversationRelayBrain(Decider(gw))
    turn = asyncio.run(brain.turn("transfer $200 to my landlord"))
    # Money is still ASK (the safety gate is unchanged); but the SPOKEN words are the live
    # model sentence, NOT the canned ASK render — a real AI behind the voice.
    assert turn.verdict == ASK, turn
    assert turn.reply == "Sure thing — I'll hold the landlord transfer until you give me the word."
    assert turn.reply != ConversationRelayBrain.render(ASK), "live reply must not be the canned line"
    # The reply was grounded in the ASK verdict (held for money), so it can't over-claim.
    assert "held until the owner" in gw.reply_prompt and "transfer $200 to my landlord" in gw.reply_prompt

    # A model error on the reply -> deterministic verdict fallback (owner never hears a hiccup).
    class FlakyGateway(FakeLiveGateway):
        async def think(self, task, tier, caller, **k):
            if caller == "decider":
                return SILENT
            raise RuntimeError("brain down")

    brain2 = ConversationRelayBrain(Decider(FlakyGateway()))
    t2 = asyncio.run(brain2.turn("ugh what a week"))
    assert t2.verdict == SILENT and t2.reply == ConversationRelayBrain.render(SILENT), t2
    print("PASS live_brain_speaks: a real model speaks a natural, verdict-grounded reply; "
          "money stays ASK; stub/error falls back to the deterministic phrasing")


# ----------------------------------------------------------------------------------
# 4) END TO END: a SIMULATED ConversationRelay websocket exchange (no real Twilio).
# ----------------------------------------------------------------------------------
def test_cr_websocket_end_to_end(client):
    def reply_for(ws):
        """Read streamed {type:"text", token} frames until last:true; return the sentence."""
        parts = []
        while True:
            frame = ws.receive_json()
            assert frame["type"] == "text", frame
            parts.append(frame["token"])
            if frame.get("last"):
                break
        return "".join(parts)

    # ONE TestClient is shared across every WS test (the engine's `core` is a module
    # singleton; a second TestClient would rebind the bus to a new event loop). Multiple
    # websocket connections within it are fine.
    if True:
        with client.websocket_connect("/cr") as ws:
            # Twilio opens with a setup control frame — acknowledged, no reply expected.
            ws.send_json({"type": "setup", "callSid": "CAtest", "from": "+15555550123"})

            # Turn 1 — a safe handed-off task: the brain ACTs, streams the ACT reply.
            ws.send_json({"type": "prompt", "voicePrompt": "remind me to call the dentist tomorrow"})
            r1 = reply_for(ws)
            assert "take care of that" in r1, ("expected ACT reply", r1)

            # Turn 2 — money: the brain ASKs (money is always a hard ASK, never auto-acted).
            ws.send_json({"type": "prompt", "voicePrompt": "transfer $200 to my landlord"})
            r2 = reply_for(ws)
            assert ("hold it" in r2 or "say go" in r2), ("expected ASK reply", r2)

            # A barge-in / control frame mid-call: acknowledged, never answered.
            ws.send_json({"type": "interrupt"})

            # Turn 3 — a vent: the brain stays SILENT (acting on a vent is the cardinal sin).
            ws.send_json({"type": "prompt", "voicePrompt": "I am so done with this week honestly"})
            r3 = reply_for(ws)
            assert "keep that in mind" in r3, ("expected SILENT reply", r3)

        # On hang-up (the context-exit closes the socket) the server closes the turn with
        # {type:"end", handoffData} carrying the LAST verdict — here Turn 3's SILENT.
        with client.websocket_connect("/cr") as ws2:
            ws2.send_json({"type": "prompt", "voicePrompt": "pay the gym membership"})
            while True:
                f = ws2.receive_json()
                if f.get("type") == "text" and f.get("last"):
                    break
            ws2.close()
            end = ws2.receive_json()
            assert end["type"] == "end", end
            assert end["handoffData"]["verdict"] == ASK, end
    print("PASS cr_websocket: simulated ConversationRelay exchange streams the brain's reply, "
          "end-frame carries the verdict (NO real Twilio)")


# ----------------------------------------------------------------------------------
# 5) AUTH: when the owner token is configured the /cr WS demands it on the handshake.
# ----------------------------------------------------------------------------------
def test_cr_websocket_owner_token_gate(client):
    """The /cr socket is an owner route; the HTTP owner-token middleware never runs for
    a WS handshake, so /cr must authenticate itself (like /ws/extension) BEFORE accept().

    Twilio ConversationRelay can't set custom headers, so the token rides as ?token=.
    Pins: no token configured -> open (dev); token configured -> a connect WITHOUT it is
    rejected (closed, no brain turn) and a connect WITH it works; a wrong token is rejected."""
    from starlette.websockets import WebSocketDisconnect

    TOKEN = "owner-cr-token-abcde"

    def turn_ok(ws):
        """Drive one ACT turn and confirm the brain actually replied (auth let us in)."""
        ws.send_json({"type": "prompt", "voicePrompt": "remind me to call the dentist tomorrow"})
        parts = []
        while True:
            f = ws.receive_json()
            assert f["type"] == "text", f
            parts.append(f["token"])
            if f.get("last"):
                break
        assert "take care of that" in "".join(parts), ("expected ACT reply", parts)

    old = os.environ.get("ANTICIPY_OWNER_API_TOKEN")
    try:
        # (a) No token configured -> dev path: /cr stays open with no ?token=.
        os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
        with client.websocket_connect("/cr") as ws:
            turn_ok(ws)

        # Token configured for the rest.
        os.environ["ANTICIPY_OWNER_API_TOKEN"] = TOKEN

        # (b) No token on the handshake -> rejected before accept(): the connect itself
        # raises WebSocketDisconnect (server closed; the brain never ran a turn).
        rejected = False
        try:
            with client.websocket_connect("/cr") as ws:
                ws.send_json({"type": "prompt", "voicePrompt": "remind me to call the dentist"})
                ws.receive_json()  # should never arrive — the socket was closed pre-accept
        except WebSocketDisconnect:
            rejected = True
        assert rejected, "an unauthenticated /cr connect (token configured) must be rejected"

        # (c) Wrong token -> also rejected.
        rejected_wrong = False
        try:
            with client.websocket_connect("/cr?token=not-the-token") as ws:
                ws.send_json({"type": "prompt", "voicePrompt": "hello"})
                ws.receive_json()
        except WebSocketDisconnect:
            rejected_wrong = True
        assert rejected_wrong, "a wrong-token /cr connect must be rejected"

        # (d) Correct token on the ?token= query param -> the socket works (Twilio path).
        with client.websocket_connect(f"/cr?token={TOKEN}") as ws:
            turn_ok(ws)
    finally:
        if old is None:
            os.environ.pop("ANTICIPY_OWNER_API_TOKEN", None)
        else:
            os.environ["ANTICIPY_OWNER_API_TOKEN"] = old
    print("PASS cr_websocket_auth: /cr demands the owner token on the handshake when configured "
          "(reject w/o it, reject wrong, accept with ?token=), open in dev (no token set)")


def main():
    from fastapi.testclient import TestClient

    from anticipy_engine.main import app

    test_twiml()
    test_stream_tokens()
    test_brain_reuse()
    test_live_brain_speaks()
    # ONE shared TestClient for every WS test: the engine's `core` is a module singleton,
    # so a second TestClient would rebind its bus to a different event loop and crash.
    with TestClient(app) as client:
        test_cr_websocket_owner_token_gate(client)
        test_cr_websocket_end_to_end(client)
    print("PASS conversation_relay: two-way voice transport (ConversationRelay) dev-proven, "
          "same decider, money=ASK, vent=SILENT")


if __name__ == "__main__":
    main()
