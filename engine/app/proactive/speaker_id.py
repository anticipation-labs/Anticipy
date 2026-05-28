"""
Layer 0: Speaker-ID classifier — AI call.

The Anticipy wearable is always-on audio. Every transcript chunk used to
be assumed to come from the wearer. That assumption breaks the moment a
bystander speaks: their words would be treated as wearer intent and the
agent could act on them.

L0 sits BEFORE L1 salience and answers a single question: is this chunk
from the WEARER, or from someone else in the room? If the model is
confident the speaker is not the wearer, the engine drops the chunk
before any downstream layer sees it.

Per Omar's directive 2026-05-01: NO keyword tables, NO regex, NO list of
"first-person markers". The MODEL reads the chunk and the recent buffer
(the wearer's voice prior) and decides. The phone-side diarization may
provide a soft prior via `chunk.diarization_hint` ("wearer" / "other" /
"unknown") — the model treats that as a hint, not a hard rule. The
phone diarizer can be wrong, and wearer-quoted speech ("she said 'X'")
must still be classified as wearer.

Failure mode preference: when uncertain, the model is told to lean
WEARER. False positives (non-wearer chunk treated as wearer) cost
nothing — downstream salience filters non-actionable chatter anyway.
False negatives (wearer chunk silently dropped as bystander) cost
silent loss of user intent. The asymmetry is the whole reason this
layer fails open.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.models import effective_layer_timeout_seconds

from .context import ContextBuffer
from .types import TranscriptChunk

logger = logging.getLogger("engine.proactive.speaker_id")


# Base timeout. Effective timeout is computed dynamically — see donna.py for
# the rationale. L0 fires sequentially per-chunk in a single scenario, but
# under the eval harness's parallel scenario fan-out (parallel>=2) it competes
# with other scenarios' calls on the same provider semaphore. Using
# concurrent_calls=3 keeps a uniform pad across all layers and stays correct
# under both the single-scenario and parallel-scenario regimes.
SPEAKER_ID_TIMEOUT_SECONDS = 8.0
DEFAULT_IS_WEARER_ON_FAILURE = True  # fail-open to wearer
SPEAKER_ID_RECENT_SECONDS = 120.0    # wearer-voice prior window


LlmCall = Callable[[str, str], Awaitable[str]]


@dataclass
class SpeakerVerdict:
    """Result of the L0 speaker-ID classifier.

    `is_wearer=True` means downstream layers should treat the chunk as
    wearer speech. `is_wearer=False` means the engine should drop the
    chunk (subject to a confidence floor enforced by the caller).
    """

    is_wearer: bool
    confidence: float = 0.0  # 0..1
    reasoning: str = ""


class SpeakerIDClassifier:
    """Layer 0 of the AI cascade. One LLM call per chunk.

    Mirrors the donna/reversibility/urgency pattern: dataclass + class +
    system prompt + strict-JSON parse. JSON mode is forced upstream by
    `make_json_llm_call`, so `_parse` does plain `json.loads` only.
    """

    def __init__(self, llm_call: LlmCall | None) -> None:
        self._llm_call = llm_call

    async def classify(
        self,
        chunk: TranscriptChunk,
        context: ContextBuffer | None = None,
    ) -> SpeakerVerdict:
        if self._llm_call is None:
            # No LLM → never drop. L0 is a defense layer; without a
            # working classifier we keep the wearer's voice flowing.
            return SpeakerVerdict(
                is_wearer=DEFAULT_IS_WEARER_ON_FAILURE,
                confidence=0.0,
                reasoning="no llm configured; defaulting to wearer",
            )

        recent = ""
        if context is not None:
            try:
                recent = await context.recent_text(seconds=SPEAKER_ID_RECENT_SECONDS)
            except Exception:
                recent = ""

        hint = (chunk.diarization_hint or "").strip().lower() or "unknown"
        user = _USER_TEMPLATE.format(
            text=chunk.text,
            hint=hint,
            self_talk=str(chunk.is_self_talk).lower(),
            addressed=str(chunk.is_addressed_to_agent).lower(),
            recent=(recent or "(none)")[-2000:],
        )

        try:
            raw = await asyncio.wait_for(
                self._llm_call(_SYSTEM_PROMPT, user),
                timeout=effective_layer_timeout_seconds(
                    SPEAKER_ID_TIMEOUT_SECONDS, expected_concurrent_calls=3
                ),
            )
        except asyncio.TimeoutError:
            logger.warning("speaker_id_llm_timeout", extra={"chunk_id": chunk.chunk_id})
            return SpeakerVerdict(
                is_wearer=DEFAULT_IS_WEARER_ON_FAILURE,
                confidence=0.0,
                reasoning="llm timeout; failed open to wearer",
            )
        except Exception:
            logger.exception("speaker_id_llm_error")
            return SpeakerVerdict(
                is_wearer=DEFAULT_IS_WEARER_ON_FAILURE,
                confidence=0.0,
                reasoning="llm error; failed open to wearer",
            )

        return _parse(raw)


_SYSTEM_PROMPT = """You are the speaker-ID layer of an always-on personal-assistant wearable. You \
read ONE transcript chunk and the recent transcript buffer, and decide whether the chunk was \
spoken by the WEARER (the user we serve) or by SOMEONE ELSE in the room. Downstream layers act \
on wearer speech only; non-wearer speech is dropped before it can be mistaken for user intent.

Default rule: the on-device DIARIZATION HINT is the authoritative prior. If the hint says \
"wearer", treat the chunk as wearer unless the textual evidence STRONGLY contradicts. If the \
hint says "other", treat the chunk as non-wearer unless the textual evidence STRONGLY \
contradicts. If the hint is "unknown" or missing, fall back to textual reasoning.

The phone-side diarizer is hardware-level acoustic signal — it knows the wearer's voiceprint. \
Overriding it requires strong textual evidence, not hunches. Examples that JUSTIFY override:

  - hint=other, but the chunk is unmistakably first-person wearer narration that includes a \
quote of another speaker (\"and then she said 'we should buy them'\") — the wearer is quoting; \
this is wearer speech. Override to wearer.

  - hint=wearer, but the chunk is unmistakably someone addressing the wearer in second person \
(\"hey {wearer-name}, can you do X?\") and the recent buffer shows the wearer responding to it. \
Cross-talk leaked through; override to other.

Examples that DO NOT justify override:

  - hint=other, chunk says \"I think we should...\" — first-person doesn't override the \
hardware signal; another person can also say \"I think\".

  - hint=other, chunk is on the same topic the wearer was discussing — topic continuity is not \
voice identity. Multiple people in a meeting talk about the same topic.

  - hint=wearer, chunk uses the second-person \"you\" — the wearer can address themselves or \
narrate dialogue. Don't override on \"you\" alone.

Reason about, in order:

  DIARIZATION HINT — the chunk's `diarization_hint` is your starting prior. Anchor here.

  CONVERSATIONAL ROLE — does this utterance fit the rhythm of someone responding TO the wearer \
(a question or directive aimed at them) or someone speaking AS the wearer (first-person plans, \
self-talk, narration)? Use this to decide whether textual evidence agrees or disagrees with the \
hint.

  QUOTED SPEECH — when a chunk is the wearer REPEATING what someone else said (\"she said 'X'\", \
\"my boss told me 'Y'\"), the chunk is still from the WEARER. The wearer is the narrator. Do \
not let the quoted second person flip you off the wearer hint.

  CROSS-TALK PATTERNS — meetings, calls, restaurants. When the recent buffer shows the wearer \
in a multi-party conversation, the diarization hint becomes MORE reliable, not less — the \
hardware diarizer is the only signal that knows whose voice this actually is. Do not override \
"other" toward "wearer" just because the topic is shared.

  is_self_talk and is_addressed_to_agent — environmental hints. is_self_talk=true and \
is_addressed_to_agent=true are weak nudges toward wearer; they don't override an "other" hint.

Bias / failure-mode preference: trust the diarization hint when it's present. When the hint is \
"unknown" or missing AND the textual evidence is genuinely ambiguous, return is_wearer=true \
(the wearer's intent is the cost-asymmetric direction to fail). But never use that fallback as \
an excuse to ignore an "other" hint that the textual evidence does not clearly contradict.

You return STRICT JSON only:
{
  "is_wearer": <true|false>,
  "confidence": <float 0..1>,
  "reasoning": "<one short sentence>"
}

Rules:
1. STRICT JSON, no markdown.
2. The diarization hint is your default prior. Override only on STRONG textual evidence.
3. Confidence reflects YOUR certainty in the is_wearer call. When you're following a clear \
hint with no contradicting evidence, confidence should be high (0.8+).
4. When you call is_wearer=false on a clearly-other chunk (hint=other + addressed-to-wearer \
second person + non-first-person framing), return confidence >= 0.7 so the engine drops it.
5. Wearer-narrator-quoting-other ("she said 'X'") stays wearer regardless of any quoted phrasing.
"""


_USER_TEMPLATE = """Chunk under consideration:
  text: {text}
  diarization_hint: {hint}
  is_self_talk: {self_talk}
  is_addressed_to_agent: {addressed}

Recent transcript (last 120s, mostly wearer-voice prior):
\"\"\"
{recent}
\"\"\"

Return the speaker-ID JSON."""


def _parse(raw: str) -> SpeakerVerdict:
    """Strict JSON parser. JSON mode is forced upstream so `raw` is either
    a clean JSON object or empty (full-cascade failure). On any malformed
    output we fail OPEN to wearer=True — losing wearer intent silently is
    the failure mode we refuse to ship."""
    raw = (raw or "").strip()
    if not raw:
        return SpeakerVerdict(
            is_wearer=DEFAULT_IS_WEARER_ON_FAILURE,
            confidence=0.0,
            reasoning="empty response; failed open to wearer",
        )
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return SpeakerVerdict(
            is_wearer=DEFAULT_IS_WEARER_ON_FAILURE,
            confidence=0.0,
            reasoning="unparseable response; failed open to wearer",
        )
    if not isinstance(data, dict):
        return SpeakerVerdict(
            is_wearer=DEFAULT_IS_WEARER_ON_FAILURE,
            confidence=0.0,
            reasoning="non-object response; failed open to wearer",
        )

    is_wearer = bool(data.get("is_wearer", DEFAULT_IS_WEARER_ON_FAILURE))
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    reasoning = str(data.get("reasoning") or "").strip()
    return SpeakerVerdict(is_wearer=is_wearer, confidence=confidence, reasoning=reasoning)
