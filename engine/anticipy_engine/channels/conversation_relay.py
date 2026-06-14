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

from dataclasses import dataclass

from ..proactive.decider import ACT, ASK, SILENT, UNAVAILABLE, Decider

# Spoken renderings of each verdict. Short, plain sentences — they are read aloud by
# Twilio TTS, so no markup, no lists, no jargon. Each maps 1:1 to a decider verdict so
# the voice can never say something the brain did not decide.
_REPLY = {
    ACT: "Got it — I'll take care of that and keep a record for you.",
    ASK: "I can line that up, but since it touches someone or money I'll hold it "
         "until you say go.",
    SILENT: "Okay, I'll just keep that in mind.",
    UNAVAILABLE: "I didn't quite catch the intent there — I'll set it aside rather "
                 "than guess. Can you say it once more?",
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
        """Judge one owner utterance with the proactive decider and render the reply."""
        verdict = await self.decider.decide(voice_prompt or "")
        return RelayTurn(prompt=voice_prompt or "", verdict=verdict, reply=self.render(verdict))


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
