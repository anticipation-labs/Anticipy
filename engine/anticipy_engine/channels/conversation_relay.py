"""Two-way voice brain bridge for Twilio ConversationRelay.

The 2:45-call test is two-way: the owner speaks, Anticipy answers, in one live call.
Twilio's ConversationRelay does the speech<->text plumbing (ASR + TTS) and hands the
engine *text*: each owner utterance arrives as a {type:"prompt", voicePrompt} WS frame,
and the engine streams the spoken reply back as {type:"text", token} frames, closing the
turn with {type:"end", handoffData}.

This module is the small seam between that text transport and the SAME brain the proactive
engine already runs: the Room 1.5 ``Decider`` (proactive/decider.py). We do NOT fork the
decider — ``turn`` calls ``Decider.decide(voicePrompt)`` (the exact ACT/ASK/SILENT
commitment judgment the always-listening loop uses) and only *renders* that one verdict
into a short, spoken-friendly sentence plus structured ``handoffData``. The judgment is the
decider's; this file just gives it a voice.

Safety carries straight through the decider's contract:
  - money / binding steps land on ASK ("I'll hold that until you confirm"), never ACT;
  - a vent / narration lands on SILENT ("I'll just keep that in mind"), never an action;
  - UNAVAILABLE (a starved/keyless brain that never read the line) is spoken honestly as a
    deferral, never as a judged silence — an unread line still never acts.
Nothing here sends, books, pays, or executes; the spoken reply is words only. The real
act/ask still flows through the proactive spine on the ambient transcript, exactly as today.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..core.gateway import PROVIDER_OPENROUTER, SMART
from ..proactive.agent_reply import _FALLBACK as _REPLY_FALLBACK
from ..proactive.agent_reply import agent_reply
from ..proactive.decider import ACT, ASK, SILENT, UNAVAILABLE, Decider


def voice_execute_enabled() -> bool:
    """Config-ready gate: does a spoken /cr utterance ALSO run through the owner action spine?

    The spoken reply above is words only. When this is on, the /cr handler ADDITIONALLY feeds
    each owner utterance into ``ControlCore.owner_ingest(execute_actions=True)`` — the exact same
    door as typed/MP3/SMS intake — so a spoken task actually creates a card/errand. Safety is the
    spine's, unchanged: no new gate is added here; owner_ingest holds money/irreversible as an ASK
    and a vent stays SILENT, exactly as the typed path already does.

    OFF by default (mirrors ``InboundPoller.live_ready()``): the dev-proven words-only voice path is
    untouched unless the operator opts in with ``ANTICIPY_VOICE_EXECUTE`` truthy, so the suite and
    every existing call flow are unaffected until voice→act is deliberately turned on."""
    return (os.environ.get("ANTICIPY_VOICE_EXECUTE", "") or "").strip().lower() in {"1", "true", "yes", "on"}

# Spoken renderings of each verdict. Short, plain sentences — they are read aloud by
# Twilio TTS, so no markup, no lists, no jargon. Each maps 1:1 to a decider verdict so
# the voice can never say something the brain did not decide. These are the DETERMINISTIC
# FALLBACK: a stub/keyless brain, or a model error, speaks these instead of guessing. When a
# real model is behind the line, ``turn`` speaks a live, natural reply instead (Omar's ask:
# "an AI agent behind the voice", not a canned line) — grounded in this same verdict so it can
# never claim more than the brain decided.
_REPLY = {
    ACT: "Got it — I'll take care of that and keep a record for you.",
    ASK: "I can line that up, but since it touches someone or money I'll hold it "
         "until you say go.",
    SILENT: "Okay, I'll just keep that in mind.",
    UNAVAILABLE: "I didn't quite catch the intent there — I'll set it aside rather "
                 "than guess. Can you say it once more?",
}

# Verdict -> GROUND TRUTH for the live spoken reply: what the brain is allowed to say it did.
# On the voice line NOTHING executes inline (the real act/ask flows through the proactive spine
# on the ambient transcript), so ACT is a COMMITMENT ("I've got it"), never a claim of completion;
# money/another person is HELD; a vent is nothing. agent_reply is told never to exceed this.
_GROUND = {
    ACT: ("WHAT HAPPENED: this is a small, self-contained, reversible task — you've noted it "
          "and will take care of it. Nothing irreversible happened and no money was spent."),
    ASK: ("WHAT HAPPENED: this touches money or another person, so NOTHING was done — it's being "
          "held until the owner gives the go-ahead."),
    SILENT: ("WHAT HAPPENED: this read as a vent or narration, not a task — there is nothing to "
             "do and nothing was done."),
    UNAVAILABLE: ("WHAT HAPPENED: the intent wasn't clear, so nothing was assumed and nothing "
                  "was done."),
}


@dataclass
class RelayTurn:
    """One owner utterance, judged and rendered for the voice line."""
    prompt: str
    verdict: str
    reply: str

    def handoff_data(self) -> dict:
        """Structured trailer for the {type:"end", handoffData} frame — what the brain
        decided this turn, so a downstream Twilio Function (or the call log) can see it."""
        return {"verdict": self.verdict, "prompt": self.prompt}


class ConversationRelayBrain:
    """Renders the SAME proactive ``Decider`` for the two-way voice line.

    Construct it around the live engine's decider when there is one
    (``ConversationRelayBrain(core.proactive.decider)``); when the engine runs in stub mode
    it has no decider, so pass a gateway and this builds the very same ``Decider`` class on
    it (``ConversationRelayBrain.from_gateway(core.gateway, glassbox=...)``) — a construction
    detail, not a second brain: identical prompt, identical parse, identical verdicts.
    """

    def __init__(self, decider: Decider) -> None:
        if decider is None:
            raise ValueError("ConversationRelayBrain needs a Decider (the proactive brain)")
        self.decider = decider

    @classmethod
    def from_gateway(cls, gateway, glassbox=None) -> "ConversationRelayBrain":
        return cls(Decider(gateway, glassbox=glassbox))

    @staticmethod
    def render(verdict: str) -> str:
        """The spoken sentence for a verdict (fail-safe to the SILENT phrasing)."""
        return _REPLY.get(verdict, _REPLY[SILENT])

    async def turn(self, voice_prompt: str) -> RelayTurn:
        """Judge one owner utterance with the proactive decider, then SPEAK.

        Two separable jobs: the decider makes the safety judgment (ACT/ASK/SILENT — temp-0,
        fail-SILENT, the gate on what may be claimed), and the spoken sentence is generated by
        the SAME brain (agent_reply, warm + conversational) GROUNDED in that verdict — so Omar
        hears a real assistant, never a canned line, yet the words can never exceed what the
        decider allowed. With a stub/keyless brain (or any model error) it falls back to the
        deterministic verdict phrasing, so the dev path and the safety floor are unchanged."""
        prompt = voice_prompt or ""
        verdict = await self.decider.decide(prompt)
        reply = await self._speak(prompt, verdict)
        return RelayTurn(prompt=prompt, verdict=verdict, reply=reply)

    async def _speak(self, prompt: str, verdict: str) -> str:
        """The spoken reply: a live, natural sentence from the model when a real brain is behind
        the line; the deterministic verdict phrasing otherwise (stub/keyless/error)."""
        gateway = getattr(self.decider, "gateway", None)
        if getattr(gateway, "provider", None) != PROVIDER_OPENROUTER:
            return self.render(verdict)   # stub/dev/keyless: deterministic, no model call
        reply = await agent_reply(gateway, prompt, ground=_GROUND.get(verdict, _GROUND[SILENT]),
                                  caller="agent")
        # agent_reply self-falls-back to a generic hiccup line on any model error; for the voice
        # line the verdict-specific phrasing is more useful, so prefer it over the generic line.
        return self.render(verdict) if (not reply or reply == _REPLY_FALLBACK) else reply


_ONBOARD_SYS = (
    "You are Anticipy, on a warm, real phone call with your owner to get set up so you can run their life "
    "well. You sound like a sharp, friendly human assistant — natural and brief (1-2 spoken sentences), "
    "never robotic, never a survey. Drive the conversation: react to what they just said like a person "
    "would (a quick, genuine reflection), then ask ONE good next question — their work and what a normal "
    "week looks like, the people who matter (family, clients, team), what they keep forgetting or dread, "
    "and how hands-on they want you to be. Be genuinely curious and a little warm. NEVER dismiss them or "
    "say there's nothing to talk about — there is always a next thing to learn. If they ask what you can "
    "do, answer concretely and warmly. If they ask you to spend money or do anything irreversible, say "
    "you'll set it up and hold it for their go-ahead — you never spend or send without a clear yes. This "
    "is a flowing conversation, not an interview. Output ONLY the words you'd say out loud, nothing else."
)


class OnboardingCallBrain:
    """The warm two-way brain for an onboarding/setup CALL (Omar's ask: a call you can't tell is AI).

    Unlike the ambient ``ConversationRelayBrain`` (which judges each line ACT/ASK/SILENT and can sound
    dismissive on a casual turn), this DRIVES a real conversation: it remembers the call so far and asks
    good setup questions. Words only — it executes nothing; money/irreversible are spoken as 'I'll hold
    that for your go-ahead', never as done. Falls back to a warm deterministic line on a stub/keyless brain
    or any model error, so the call is never silent and never canned-dismissive."""

    def __init__(self, gateway, glassbox=None) -> None:
        self.gateway = gateway
        self.glassbox = glassbox
        self.history: list = []  # [(speaker, text)] — the call so far

    async def turn(self, voice_prompt: str) -> "RelayTurn":
        prompt = (voice_prompt or "").strip()
        if prompt:
            self.history.append(("owner", prompt))
        reply = await self._generate()
        self.history.append(("anticipy", reply))
        if self.glassbox:
            self.glassbox.log("onboarding_call_turn", {"owner": prompt[:120], "reply": reply[:120]})
        return RelayTurn(prompt=prompt, verdict="converse", reply=reply)

    async def _generate(self) -> str:
        # stub/keyless: a warm, non-dismissive deterministic opener/continuation (never "nothing to chat about")
        if getattr(self.gateway, "provider", None) != PROVIDER_OPENROUTER:
            n = len([1 for s, _ in self.history if s == "owner"])
            return ("Tell me a bit about what a normal week looks like for you." if n <= 1
                    else "Got it — and who are the people I should know about in your day-to-day?")
        convo = "\n".join(f"{'You' if s == 'owner' else 'Anticipy'}: {t}" for s, t in self.history[-12:])
        full = f"{_ONBOARD_SYS}\n\nThe call so far:\n{convo}\n\nAnticipy:"
        try:
            reply = await self.gateway.think(full, tier=SMART, caller="agent", temperature=0.6, max_tokens=110)
            reply = (reply or "").strip().strip('"')
            return reply or "I'm right here with you — tell me more."
        except Exception:
            return "I'm here with you — what's the part of your week you'd most want off your plate?"


def stream_tokens(text: str):
    """Chunk a reply the way ConversationRelay expects it: a sequence of small text
    tokens that Twilio speaks as they arrive (low latency). We keep the trailing
    whitespace on each token so the concatenation reconstructs the sentence exactly.

    This mirrors how an LLM streams — word-ish chunks — without needing a real streaming
    provider, so the dev-proven path and the live path emit the same frame shape.
    """
    if not text:
        return
    word = ""
    for ch in text:
        word += ch
        if ch == " ":
            yield word
            word = ""
    if word:
        yield word
