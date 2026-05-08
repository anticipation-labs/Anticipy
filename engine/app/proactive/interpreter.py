"""
Real-time interpreter — AI cascade. Layer 1 (salience) + Layer 2 (extraction).

NO regex. NO keyword tables. NO structural pattern matching. Per Omar's
directive 2026-05-01: every step that detects user intent is an AI call.

Layer 1: SALIENCE
  Cheap LLM (Groq Scout / on-device 1-3B) runs on EVERY chunk.
  Decides: is this utterance actionable? yes/no + confidence.
  Sub-200ms target. Fires on every chunk; no throttle.

Layer 2: INTENT EXTRACTION
  Slightly bigger LLM runs only on chunks where Layer 1 said yes.
  Extracts free-form action_verb, intent text, parameters, confidence.
  No canonical-verb constraint — the LLM invents the verb that fits.
  Throttled per-session (min_interval) so we don't fire on every salient
  chunk during a fast burst.

Both layers are LLM calls with structured-JSON output, timeouts, and a
graceful empty-result fallback if the model fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence

from app.models import effective_layer_timeout_seconds

from .context import ContextBuffer
from .types import Confidence, Intent, TranscriptChunk

logger = logging.getLogger("engine.proactive.interpreter")


# Base timeouts. Effective timeouts are computed dynamically — see donna.py
# for the rationale. Under the eval harness's parallel scenario fan-out these
# layers contend with other scenarios' calls on the same provider semaphore,
# so using concurrent_calls=3 keeps a uniform pad across all layers.
SALIENCE_TIMEOUT_SECONDS = 12.0  # tolerant of slower providers (Groq llama-70b ~2-3x Gemini Flash latency)
EXTRACT_TIMEOUT_SECONDS = 20.0
DEFAULT_MIN_EXTRACT_INTERVAL_SECONDS = 1.0  # was 4.0 — was throttling away genuine urgent follow-ups
DEFAULT_SALIENCE_CONFIDENCE_FLOOR = 0.35  # was 0.4 — let more borderline through; L2 is the real filter
LLM_CONTEXT_SECONDS = 240.0  # 4 minutes — wide enough to catch retractions, narrow enough to keep signal
SALIENCE_RECENT_CHARS = 600  # only feed the last ~600 chars to salience layer


LlmCall = Callable[[str, str], Awaitable[str]]


# --- Layer 1: salience ---------------------------------------------------------


@dataclass
class SalienceVerdict:
    """Output of the Layer-1 salience classifier."""

    actionable: bool
    confidence: float  # 0..1, the model's own confidence in its actionable y/n
    reasoning: str = ""


class SalienceClassifier:
    """Layer 1. AI 'is this worth attention?' filter.

    Wraps a cheap LLM. Output is YES/NO + confidence. The Interpreter uses
    `(actionable AND confidence >= floor)` as its wake gate. Tuning `floor`
    is the cost lever — lower floor = more wake-ups = more L2 calls.

    Bias: when in doubt, the model is told to lean YES (false positives are
    cheap — an extra L2 call). False negatives (silent miss) are the
    expensive failure mode.
    """

    def __init__(
        self,
        llm_call: LlmCall,
        confidence_floor: float = DEFAULT_SALIENCE_CONFIDENCE_FLOOR,
    ) -> None:
        self._llm_call = llm_call
        self._floor = confidence_floor

    @property
    def confidence_floor(self) -> float:
        return self._floor

    async def is_salient(
        self,
        chunk: TranscriptChunk,
        recent_text: str = "",
    ) -> SalienceVerdict:
        sys = _SALIENCE_SYSTEM_PROMPT
        user = _SALIENCE_USER_TEMPLATE.format(
            recent=(recent_text or "(no prior context)")[-SALIENCE_RECENT_CHARS:],
            latest=chunk.text or "",
            addressed=str(chunk.is_addressed_to_agent).lower(),
            self_talk=str(chunk.is_self_talk).lower(),
        )
        try:
            raw = await asyncio.wait_for(
                self._llm_call(sys, user),
                timeout=effective_layer_timeout_seconds(
                    SALIENCE_TIMEOUT_SECONDS, expected_concurrent_calls=3
                ),
            )
        except asyncio.TimeoutError:
            logger.warning("salience_llm_timeout", extra={"chunk_id": chunk.chunk_id})
            return SalienceVerdict(actionable=False, confidence=0.0, reasoning="salience timeout")
        except Exception:
            logger.exception("salience_llm_error")
            return SalienceVerdict(actionable=False, confidence=0.0, reasoning="salience error")
        return _parse_salience(raw)


_SALIENCE_SYSTEM_PROMPT = """You are the first-pass attention filter for a personal-assistant wearable. \
You read the LATEST utterance from the user (with recent context for disambiguation) and decide \
whether the deeper analysis layer should run.

You return STRICT JSON only:
{
  "actionable": <true|false>,
  "confidence": <float 0..1>,
  "reasoning": "<one short sentence>"
}

Mark ACTIONABLE = TRUE when ANY of these apply:
  - direct commands or requests addressed to anyone
  - the user says they "should", "need to", "have to", "keep meaning to" do something concrete
  - the user announces a plan, decision, commitment, or appointment
  - the user mentions they forgot or are about to forget something with a concrete object
  - the user names a person + task, a date + task, an amount + task, or a location + task
  - the user enumerates 2+ concrete items as part of an errand or commitment ("organic milk, \
eggs, Fuji apples"), even if they're confirming/responding rather than initiating — \
the wearable's job is to retain commitments the user makes, regardless of who they're talking to
  - the user asks ANY information-seeking question that has a definite answer (price, time, \
fastest route, store hours, who/what/when/where)
  - the user is TRYING TO REMEMBER something specific (a movie title, an actor's name, a song, \
a person's name) and is providing concrete clues — that is a search/lookup intent, even if \
phrased as self-talk
  - the user expresses time pressure ("right now", "immediately", "I'm late", "ASAP")
  - the user dictates the body of a message, document, or content to be produced
  - earlier context contains a buildup AND the latest utterance resolves into a concrete request
  - the user retracts or contradicts something — the retraction itself is actionable signal for L2

Mark ACTIONABLE = FALSE only when ALL of these apply:
  - the latest utterance contains no concrete object, person, time, place, or amount
  - it is purely smalltalk, weather chatter, jokes, song lyrics, recited media, or pure venting
  - the surrounding context also contains no actionable buildup that the latest utterance resolves
  - the user is musing aloud with no commitment or question that has a definite answer

When the latest chunk on its own looks vague but the recent context shows the user has been \
building toward a concrete task (gift idea for Sarah, package shipping, flight prices) — say YES. \
The L2 layer needs the chance to look at the full context.

Confidence is your own certainty: 1.0 = obvious, 0.5 = a hunch, 0.0 = no idea.

Bias HARD toward ACTIONABLE when uncertain. The L2 layer can still decide to extract zero \
intents. False negatives at this layer are silent and expensive.

Rules:
1. STRICT JSON, no markdown.
2. Reasoning is one sentence.
"""


_SALIENCE_USER_TEMPLATE = """Recent context (oldest first):
\"\"\"
{recent}
\"\"\"

Latest utterance from the user:
\"\"\"
{latest}
\"\"\"

Phone-side hints:
  is_addressed_to_agent: {addressed}
  is_self_talk: {self_talk}

Return the JSON."""


# --- Layer 2: extraction -------------------------------------------------------


@dataclass
class ExtractedIntent:
    intent: Intent
    confidence: Confidence


class Interpreter:
    """Layer 1 + Layer 2 wrapper.

    on every chunk → SalienceClassifier (Layer 1)
    on salient chunk → free-form intent extraction (Layer 2)
    """

    def __init__(
        self,
        llm_call: LlmCall,
        salience_classifier: SalienceClassifier | None = None,
        min_interval_seconds: float = DEFAULT_MIN_EXTRACT_INTERVAL_SECONDS,
    ) -> None:
        self._llm_call = llm_call
        self._salience = salience_classifier or SalienceClassifier(llm_call)
        self._min_interval = min_interval_seconds
        self._last_extract_ts: dict[str, float] = {}

    async def should_wake(
        self,
        chunk: TranscriptChunk,
        recent_text: str = "",
    ) -> tuple[bool, SalienceVerdict]:
        """Layer 1 + throttle. Returns (wake_now, salience_verdict)."""
        verdict = await self._salience.is_salient(chunk, recent_text)
        if not verdict.actionable:
            return False, verdict
        if verdict.confidence < self._salience.confidence_floor:
            return False, verdict
        last = self._last_extract_ts.get(chunk.session_id, 0.0)
        if time.time() - last < self._min_interval:
            return False, verdict
        return True, verdict

    async def extract(
        self,
        triggering_chunk: TranscriptChunk,
        context: ContextBuffer,
        related_memories: Sequence[str] = (),
    ) -> list[ExtractedIntent]:
        """Layer 2. Runs only after should_wake() returned True."""
        self._last_extract_ts[triggering_chunk.session_id] = time.time()

        recent = await context.recent_text(LLM_CONTEXT_SECONDS)
        sys, user = _build_extract_prompts(
            triggering_chunk=triggering_chunk,
            recent_transcript=recent,
            related_memories=related_memories,
        )

        try:
            raw = await asyncio.wait_for(
                self._llm_call(sys, user),
                timeout=effective_layer_timeout_seconds(
                    EXTRACT_TIMEOUT_SECONDS, expected_concurrent_calls=3
                ),
            )
        except asyncio.TimeoutError:
            logger.warning("interpreter_extract_timeout", extra={
                "session_id": triggering_chunk.session_id,
            })
            return []
        except Exception:
            logger.exception("interpreter_extract_error")
            return []

        return _parse_extract(raw, user_id=triggering_chunk.user_id)


_EXTRACT_SYSTEM_PROMPT = """You are the intent-extraction layer of a personal-assistant wearable. \
You read the recent transcript (multiple utterances) and the latest triggering chunk from ONE \
user. Decide what the user ULTIMATELY wants by the end of the recent transcript, after weighing \
their full conversation arc, including any retractions or changes of mind they have expressed.

You behave like a great chief of staff who has been listening the whole time. You act on \
resolved commitments. You ask when stakes are real. You stay silent when the user is still \
exploring, ruminating, or has retracted.

═══ TOP RULE — READ THIS FIRST AND APPLY BEFORE ANYTHING ELSE ═══

FINAL-POSITION DETECTION. Before extracting ANY intent, read the LAST 3-5 utterances in the \
recent transcript and ask: did the user retract, contradict, supersede, or pivot away from \
the action they were about to commit to?

  Examples of retraction/contradiction language: "actually, no", "never mind", "wait, that's \
a terrible idea", "scratch that", "on second thought", "I changed my mind", "I shouldn't", \
"forget it", "skip it", "no point in", "I'm not sure I'm even going", "actually let me just".

  Pivot to a different action: "Yeah I'll just X instead", "let me do Y instead", "actually \
I think I'll Y" — the user superseded the original action with Y. Extract Y, NOT the original.

  If the LATEST position is "no" / "skip" / "different action" — extract zero intents for the \
ORIGINAL action. If the latest position is the new action, extract THAT (with its own slots).

  This applies even if the original action was the bulk of the conversation — a wearable that \
acts on what the user said 30 seconds ago instead of what they said 5 seconds ago is exactly \
the failure mode we refuse to ship.

═══ END TOP RULE ═══


You return STRICT JSON only.

Output schema:
{
  "intents": [
    {
      "text": "<one short sentence rephrasing what the user wants done, in your own words, \
including ALL the specific slot fills the user mentioned (people, items, amounts, times, places)>",
      "action_verb": "<short snake_case verb that captures the action; free-form; invent it>",
      "parameters": {
        "<key>": "<value>"
      },
      "evidence_chunk_ids": [<int>, ...],
      "confidence": <float 0..1>,
      "confidence_reasoning": "<one sentence>"
    }
  ]
}

Rules:
1. Output STRICT JSON, no markdown, no preamble.
2. action_verb is FREE-FORM. Invent whatever snake_case phrase fits.
3. parameters MUST include EVERY concrete slot the user mentioned ACROSS the entire recent \
transcript — not just the triggering chunk. If the user said "organic milk" in an earlier chunk \
and "Fuji apples" in a later chunk, BOTH go into parameters as a list under a key like "items". \
Read the FULL recent transcript and pull every slot the user attached to this intent: every \
named person, every time, every amount, every place, every item, every detail of message body \
they dictated. The text field must reflect ALL the accumulated slots, not just the last chunk's \
fragment.
4. evidence_chunk_ids reference the chunk_ids in the transcript that support this intent.
5. The "text" field should be self-contained: someone reading just the text should know exactly \
what the user wants, with all the specific details.
6. NEVER emit an intent whose parameters dict is EMPTY or whose text is generic ("user wants \
to Google something", "user wants to look something up", "do the thing"). If you cannot fill \
at least one concrete slot (named person, item, place, time, amount, source, recipient, \
subject, body, or named target) from the recent transcript, the chunk is too vague to act \
on — return zero intents. Vague candidates with empty params are the spammy failure mode; \
silence is correct here.

THE RESOLUTION TEST — apply before extracting any intent:
  Has the user actually RESOLVED on this action by the end of the recent transcript?
  Resolved = clear forward commitment, OR a definite information-seeking question, OR a direct \
request addressed to anyone.
  Not resolved = still asking themselves options ("hmm, what's the best way", "or maybe X"), \
weighing alternatives, ruminating, exploring without a decision.

  EXPLORATION-MODE detection — critical: when the user states a goal AND immediately starts \
self-questioning the approach ("I need to send this package today" followed by "what's the best \
way?", "I wonder if the post office is open?", "or maybe a courier?"), the user is in \
EXPLORATION MODE. They have not yet RESOLVED on a specific action. Return zero intents during \
exploration. Only extract the FINAL specific action they land on at the end of the buildup.

  DICTATION IS NOT EXPLORATION — when the user is mid-dictation of a message body, document \
content, email body, post, or review (signaled by phrases like "Body:", "Subject:", \
"Dear X,", "Hi,", or simply continuing prose after a "draft an email" / "write a post" / \
"send a message" command), DO extract / re-extract the intent on each new dictation chunk. \
Each dictation chunk is detail-accumulation, not exploration. The action_verb is the same \
across chunks (e.g. `draft_email`); the body parameter grows. The latest extraction with \
the FULL accumulated body supersedes earlier ones — so the engine acts on the complete \
composition, not a half-typed subject.

  If the user asks a series of questions and lands on a specific request at the end, that final \
request IS the resolution — extract IT, not the earlier exploratory fragments. The text and \
parameters should reflect the final committed action only.

  If the recent transcript shows the user weighing options and then RETRACTING or CHANGING \
their mind ("never mind", "actually no", "I shouldn't", "maybe I'll skip it"), the LATEST \
position wins. If the latest position is "no" or "different action", return zero intents for \
the original or extract the new action only.

  If the user is mid-buildup and has not landed on a specific request yet, return zero intents.

  When the user across multiple chunks PROGRESSIVELY ADDS DETAILS to the same action (e.g., \
"buy concert tickets" → "Friday show, section B, two seats" → "credit card 4567"), this is \
NOT exploration — it is detail-accumulation. Extract ONE intent with ALL the accumulated slot \
fills. Do NOT extract the early-chunk version with empty parameters and then re-extract; the \
latest extraction with full parameters supersedes earlier ones.

  IRREVERSIBLE-PLUS-CONFIRMATION extraction: when the user states an irreversible action (buy, \
purchase, send, post, schedule, transfer, fire, terminate) AND adds a meta-step \
("confirm once it's done", "let me know when complete", "double-check first", "verify before"), \
extract the IRREVERSIBLE action_verb (e.g. `buy_concert_tickets`, `send_email`), NOT the \
meta-step. The confirmation is part of the irreversible action, not a separate reversible step. \
Mis-extracting the confirmation as the action_verb makes the downstream reversibility \
classifier mark a real purchase as reversible, which is wrong.

  ERRAND ITEM LISTS: when the user commits to an errand and enumerates concrete items they \
need ("I'll swing by the store, you need organic milk, dozen eggs, Fuji apples"), extract ONE \
intent capturing the errand with parameters["items"] as the list. The action_verb should reflect \
the errand (`save_shopping_list`, `set_reminder_with_list`, `pickup_items`). The user benefits \
from a saved list or reminder even if they didn't explicitly ask for one — that's the \
implicit-but-committal contract.

  This rule fires REGARDLESS of who the user is talking to. If the user is responding to \
someone else who asked them to pick up groceries ("Yeah I can swing by the store. So you need \
organic milk, eggs, Fuji apples? I'll text when I leave"), the user is COMMITTING to an errand \
with a specific item list. That's actionable for the assistant — save the list so the user \
doesn't have to remember it. Don't dismiss it as "they're talking to a friend, not me". The \
wearable's job is to retain commitments the user makes, regardless of the conversational \
counterparty.

  META-INTENT SUPPRESSION (CRITICAL — read this carefully): when the user is RECITING or \
REVIEWING tasks they have already been talking about earlier in the recent transcript — i.e. \
mentally rehearsing their own to-do list out loud ("OK, so I need to call the dentist, send \
Mark the project update, order cat food, and pick up the recipe — that's a lot today") — \
do NOT extract a "remember_to_do_list", "prioritize_tasks", "save_to_do_list", \
"organize_my_day", "track_my_tasks", or any other meta-intent whose ITEMS are themselves \
intents the user has already individually expressed elsewhere in the recent transcript. \
The cascade has already extracted (or will extract) those individual intents on their own \
chunks; firing a separate meta-intent on top is duplicate noise to the user. Return zero \
intents for the meta-recital. This rule applies whenever the listed items would each be \
extractable as their own intent — distinct people / errands / appointments / messages / \
information-lookups the user already mentioned. It does NOT suppress a fresh errand item \
list (organic milk + eggs + apples) where the items are slot-fills of a single errand, \
not separate intents.

  An errand item list is one shopping trip with multiple physical items. A meta-intent \
recital is a list of separate tasks across separate domains (call X, email Y, order Z, find W) \
that the user is just summarizing aloud. Extract the errand list. Suppress the meta recital.

What counts as actionable, given resolution:
  EXPLICIT REQUEST — direct command or question to the agent, or present-tense commitment.
  IMPLICIT BUT COMMITTAL — the user mentions a task they've been meaning to do, or just \
committed to, with at least ONE concrete slot in their words (person, place, time, item, \
amount). This includes things like "I should look into a gift for Sarah's birthday next week" \
where Sarah and birthday and next-week ARE the concrete slots.
  INFORMATION-SEEKING — the user wants a piece of info that has a definite answer (lookup, \
search, price, weather, route, hours, fastest way). Extract as reversible, confidence 0.85+. \
This INCLUDES the user trying to remember something concrete ("what was that movie about a \
future-seer", "what was the actor's name in the magician movie") even when phrased as \
self-questioning, AS LONG AS they have provided enough concrete clues that a search is likely \
to find the answer. Extract a "search" or "lookup" intent.
  NOT ACTIONABLE — pure venting, smalltalk, quoted material, questions to oneself with no \
definite answer, or vague self-improvement with no concrete slot ("I should be more productive").

Quoted / self-talk filters: do NOT extract from movie lines, lyrics, recitations, or pure \
venting without a commit.

Emotional / harsh-content state:
  Set parameters["emotional_state"] when ANY of:
    - the user's tone in the recent context shows anger, exhaustion, panic, jealousy, grief, \
intoxication
    - the BODY of a message the user is dictating contains hostile, dismissive, contemptuous, \
or harsh language about another person ("completely unsuitable", "their cover letter was a \
joke", "irrelevant", "incompetent", "fucking", insulting characterizations)
  Use a short descriptive value: "angry_late_night", "tired_2am", "harsh_feedback_about_person", \
"panicked_running_late". Donna downstream uses this to decide refusal.

  When the user is dictating the body of a message, email, post, review, or document, \
ALWAYS capture the dictated body verbatim under parameters["body"]. Do NOT summarize. The \
exact body text is what Donna must see to evaluate harshness — a summary loses the very tone \
that makes refusal correct.

  CRITICAL: a single composition (email / text / review / document) is ONE intent, not two. If \
the user says "draft an email to X. Subject: Y. Body: Z (and more harsh body)", extract ONE \
intent with action_verb=`draft_email` and parameters={"recipient": X, "subject": Y, "body": \
"Z and more"}. Do NOT extract a separate "send_message" intent from the body — there is no \
separate send action; the user only requested a draft. Splitting the composition into multiple \
intents lets a benign-looking subject pass while the harsh body is refused — both halves are \
the same action, and Donna must evaluate the WHOLE thing.

Urgency hint:
  If the user's words convey time pressure (right now, immediately, ASAP, I'm late, in 5 \
minutes), set parameters["urgency_signal"] to a short string like "immediate" or "within_hour".

Confidence guidance:
  0.85-1.00: clearly resolved + specific slots → act unprompted.
  0.65-0.84: strongly implied resolution + slots present → reversible auto, irreversible ask.
  0.50-0.64: implicit-committal with at least one concrete slot → always ask.
  0.30-0.49: mentioned in passing, slot light → LOG silently. Do NOT bother user.
  0.00-0.29: not actionable.

Bias: extract when there is BOTH a resolution signal AND a concrete slot. Don't extract when \
either is missing, or when later utterances retract it.
"""


_EXTRACT_USER_TEMPLATE = """Recent transcript (oldest first, user voice only):
\"\"\"
{recent}
\"\"\"

Most recent chunk that triggered extraction (chunk_id={chunk_id}):
\"\"\"
{trigger}
\"\"\"

Related past memories that may give context:
\"\"\"
{memories}
\"\"\"

Extract any new actionable intents and return JSON."""


def _build_extract_prompts(
    triggering_chunk: TranscriptChunk,
    recent_transcript: str,
    related_memories: Sequence[str],
) -> tuple[str, str]:
    user = _EXTRACT_USER_TEMPLATE.format(
        recent=recent_transcript or "(empty)",
        chunk_id=triggering_chunk.chunk_id,
        trigger=triggering_chunk.text,
        memories="\n".join(f"  - {m}" for m in related_memories) or "(none)",
    )
    return _EXTRACT_SYSTEM_PROMPT, user


# --- JSON parsing helpers ------------------------------------------------------


def _try_json(raw: str) -> dict | None:
    """Strict JSON parse. Provider-native JSON mode is forced upstream, so the
    response is either a clean JSON object or empty. No fence stripping, no
    regex recovery — if it doesn't parse, the model failed and we fall safe."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_salience(raw: str) -> SalienceVerdict:
    data = _try_json(raw)
    if not data:
        return SalienceVerdict(actionable=False, confidence=0.0, reasoning="unparseable salience")
    try:
        actionable = bool(data.get("actionable", False))
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        return SalienceVerdict(actionable=False, confidence=0.0, reasoning="malformed salience")
    confidence = max(0.0, min(1.0, confidence))
    reasoning = str(data.get("reasoning") or "").strip()
    return SalienceVerdict(actionable=actionable, confidence=confidence, reasoning=reasoning)


def _parse_extract(raw: str, user_id: str) -> list[ExtractedIntent]:
    data = _try_json(raw)
    if not data:
        return []
    items = data.get("intents") or []
    out: list[ExtractedIntent] = []
    for item in items:
        try:
            verb_raw = (item.get("action_verb") or "").strip()
            text = (item.get("text") or "").strip()
            if not verb_raw or not text:
                continue
            # Whitespace/dash → underscore is a string transform, not pattern
            # matching — it normalizes any free-form verb the LLM produced.
            verb = "_".join(verb_raw.lower().replace("-", " ").split())
            confidence_score = float(item.get("confidence", 0.0))
            confidence_score = max(0.0, min(1.0, confidence_score))
            intent = Intent.new(
                user_id=user_id,
                text=text,
                action_verb=verb,
                parameters=item.get("parameters") or {},
                evidence_chunk_ids=[int(x) for x in item.get("evidence_chunk_ids") or []],
            )
            confidence = Confidence(
                score=confidence_score,
                reasoning=str(item.get("confidence_reasoning") or "").strip(),
            )
            out.append(ExtractedIntent(intent=intent, confidence=confidence))
        except (TypeError, ValueError, KeyError):
            logger.warning("interpreter_skipped_malformed_intent", extra={"item": str(item)[:200]})
            continue
    return out
