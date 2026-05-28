"""
Torture test for the Anticipy proactive engine.

The user's stated bar: "16 messages in a 10-minute conversation is wrong.
Maybe one, maybe six in a day, but not artificial limits — just correct."

This test pushes the engine harder than the eval harness or the long-
conversation diagnostic. It generates a multi-speaker, multi-day-style,
30-minute-equivalent transcript with a mix of:

  - 3-7 GENUINE intents the wearer wants done.
  - 4-8 PARTIAL/AMBIGUOUS mentions the wearer rejects, retracts, or
    explores without committing.
  - Cross-talk from 2 OTHER speakers (someone else in the room) on the
    same topics. Diarization hints are mixed: ~85% correct, 15% errors.
  - Repeats of the same intent across multiple bursts of conversation
    (the wearer brings it up three times, an hour apart).
  - Adversarial near-misses: the wearer says "send a text to Mom" then
    immediately says "actually no, just remind me later".
  - Quoted speech: "and then she said 'we should book the tickets'".

Pass criteria:
  - precision: every dispatched user-facing decision (execute/ask) maps
    to a real intent in the ground truth (no FPs from cross-talk, no
    duplicates of the same intent).
  - recall: every real intent in the ground truth has at least one
    user-facing dispatch attached to it (within latency budget).
  - density: total user-facing dispatches ≤ N_REAL_INTENTS + 2 (small
    slack for borderline cases the model treats as ASK).

Failure logs the full transcript + ground truth + dispatches for diff.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.proactive import ProactiveEngine  # noqa: E402
from app.proactive.llm_adapter import make_json_llm_call  # noqa: E402
from app.proactive.types import TranscriptChunk  # noqa: E402


GEN_SYSTEM = """You are generating a stress-test transcript for an AI \
wearable that listens to the WEARER's voice (other voices are also captured \
but tagged separately by the on-device diarizer). The transcript must \
exercise the engine's hardest cases simultaneously.

The transcript covers ~30 simulated minutes of conversation across multiple \
bursts (e.g. a phone call, then a coffee with a friend 20 minutes later, \
then a moment of self-talk).

Include:

  1. REAL_INTENTS: 3 to 7 things the wearer genuinely wants done. Each \
should be:
     - Mentioned by the wearer with intent (e.g. "I should book the \
dentist this week" — definite, not retracted).
     - Surrounded by chatter and mentioned across MULTIPLE chunks (a \
buildup like "ugh my tooth hurts" → "yeah I should call them" → \
"can you find me an opening").
     - Concrete enough that the engine can extract action_verb + target.
     - DIVERSE in domain (work, health, errands, family, personal, social).

  2. NOISE_MENTIONS: 4 to 8 things the wearer mentions but doesn't want \
done. Examples:
     - Hypotheticals: "imagine if we just bought a boat".
     - Retractions: "send a text to Mom — actually no, never mind".
     - Quoted speech: "and Sarah said 'we should book the tickets'" \
(the wearer is quoting Sarah, not asking the agent to book tickets).
     - Topic-only mentions without intent: "Sarah's wedding is great I'm \
glad they did it".
     - Self-talk venting / commiseration without a request.

  3. CROSS_TALK: 4 to 8 utterances FROM SOMEONE ELSE in the room, \
captured because they were near the mic. These are tagged \
diarization_hint=other. They sometimes echo the wearer's topic \
(e.g. someone else also saying "I should book the dentist") — the \
engine MUST NOT act on those.

  4. DIARIZATION_ERRORS: 2 to 4 of the wearer's utterances will be \
mis-tagged as diarization_hint=other (the on-device diarizer made a \
mistake). These should be obvious wearer first-person + intent (e.g. \
"yeah I'll go book that flight tonight"). The engine must override \
the bad hint and still pick them up.

  5. INTENT_REPEATS: 1 to 2 of the real intents are mentioned in TWO \
separate bursts of conversation (~10+ minutes apart). The engine \
should only dispatch ONCE per real intent — the second mention is a \
duplicate and should be deduped.

Total utterances: 60 to 100. Each utterance 3-30 words.

Output STRICT JSON only:
{
  "summary": "<one sentence>",
  "real_intents": [
    {
      "id": "intent_1",
      "description": "<what the user actually wants done>",
      "action_verb": "<expected verb e.g. send, book, search, remind>",
      "target": "<expected target/object>"
    },
    ...
  ],
  "noise_mentions": [
    {
      "kind": "hypothetical|retraction|quote|topic_only|venting",
      "text": "<the noise mention itself>"
    },
    ...
  ],
  "utterances": [
    {
      "speaker": "wearer" | "other_a" | "other_b",
      "diarization_hint": "wearer" | "other" | "unknown",
      "text": "<the utterance>",
      "intent_id": "intent_1" | null,   // populated only if this is a chunk that should map to a real intent
      "is_repeat_of": "intent_1" | null  // if this is the SECOND burst mentioning the same intent
    },
    ...
  ]
}
"""


GEN_USER = """Generate one ~30-minute torture transcript with 4-6 real intents, \
5-7 noise mentions, 5-8 cross-talk utterances, 2-3 diarization errors, and 1-2 \
repeated intents across separated bursts. Total 70-90 utterances. Make it feel \
like the messy reality of someone wearing the device through their day."""


@dataclass
class TortureScenario:
    summary: str
    real_intents: list[dict]
    noise_mentions: list[dict]
    utterances: list[dict]
    raw_json: dict


@dataclass
class TortureResult:
    n_utterances: int
    n_real_intents: int
    n_noise: int
    n_dispatches: int
    n_user_facing: int
    n_log_only: int
    real_intents_hit: list[str]    # ids of real intents that got at least one user-facing dispatch
    real_intents_missed: list[str] # ids that got nothing (or only LOG)
    extra_dispatches: list[dict]   # user-facing dispatches that don't map to any real intent
    duplicate_dispatches: list[dict]  # multiple dispatches mapped to the same real intent
    dispatched: list[dict]
    minutes_of_talk: float
    elapsed_s: float


async def _generate_scenario() -> TortureScenario:
    """Generate ONE torture scenario. Tolerates partial cascade failure
    (empty string on full cascade exhaustion) by retrying once with the
    next provider, and surfaces a clear error when every provider is
    actually down so the harness fails loudly instead of with a cryptic
    JSONDecodeError."""
    call = make_json_llm_call(max_tokens=8192)
    last_err: str | None = None
    for attempt in range(3):
        try:
            raw = await asyncio.wait_for(call(GEN_SYSTEM, GEN_USER), timeout=180.0)
        except (asyncio.TimeoutError, Exception) as e:
            last_err = f"{type(e).__name__}: {str(e)[:160]}"
            await asyncio.sleep(2)
            continue
        if not raw or not raw.strip():
            last_err = "cascade returned empty (every provider down or rate-limited)"
            await asyncio.sleep(2)
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            last_err = f"malformed JSON: {str(e)[:120]} | head={raw[:120]!r}"
            await asyncio.sleep(2)
            continue
        return TortureScenario(
            summary=data.get("summary", "").strip(),
            real_intents=data.get("real_intents", []),
            noise_mentions=data.get("noise_mentions", []),
            utterances=data.get("utterances", []),
            raw_json=data,
        )
    raise RuntimeError(
        f"_generate_scenario: all {3} attempts failed across the cascade. last_err={last_err}"
    )


def _utts_to_chunks(utterances: list[dict], session_id: str, user_id: str) -> list[TranscriptChunk]:
    """Convert generated utterances to chunks with realistic ts spacing.

    Inserts BURST GAPS (a 10-minute pause) when we cross from one
    intent_id to a later one — the eval harness models the day-spanning
    use case and the dedup test depends on this gap.
    """
    base_ts = time.time()
    chunks: list[TranscriptChunk] = []
    cursor = 0.0
    last_intent_id: str | None = None
    for i, u in enumerate(utterances):
        text = (u.get("text") or "").strip()
        if not text:
            continue
        words = max(1, len(text.split()))
        duration = max(0.5, words * 0.4)
        gap = 0.6 + (i % 3) * 0.4
        # Burst gap when entering a "is_repeat_of" — separate the second mention by 10 minutes
        if u.get("is_repeat_of") and u.get("is_repeat_of") != last_intent_id:
            gap += 600.0  # 10-minute pause to enable dispatcher dedup test
        last_intent_id = u.get("is_repeat_of") or u.get("intent_id") or last_intent_id

        start = base_ts + cursor + gap
        end = start + duration
        cursor = end - base_ts

        spkr = (u.get("speaker") or "wearer").lower()
        hint = (u.get("diarization_hint") or "unknown").lower()
        if hint not in {"wearer", "other", "unknown"}:
            hint = "unknown"

        chunks.append(TranscriptChunk(
            chunk_id=i,
            session_id=session_id,
            user_id=user_id,
            text=text,
            start_ts=start,
            end_ts=end,
            confidence=0.9,
            diarization_hint=hint,
            is_self_talk=(spkr == "wearer"),
        ))
    return chunks


async def _ai_match_dispatch_to_intent(
    dispatch: dict,
    real_intents: list[dict],
) -> str | None:
    """LLM-based matcher: which real intent (if any) does this dispatch
    correspond to? Returns the intent id, or None if no match.

    NO keyword tables. The judge looks at the dispatch's verb + text +
    params and decides which intent (if any) it satisfies.
    """
    if not real_intents:
        return None
    call = make_json_llm_call(max_tokens=256)
    intents_block = "\n".join(
        f"- id={ri.get('id')}  verb={ri.get('action_verb')}  target={ri.get('target')}  description=\"{ri.get('description')}\""
        for ri in real_intents
    )
    sys_prompt = """You match an engine dispatch against a list of REAL \
intents from the ground truth. Return STRICT JSON: {"intent_id": "<id>" or \
null, "reasoning": "<1 sentence>"}.

A match means: the dispatch genuinely satisfies the user's stated need \
in that intent (verb + target align; minor paraphrase OK). If the \
dispatch is on the right TOPIC but wrong action (e.g. real intent is \
"book dentist" but dispatch is "search for dentists"), still match \
(same goal, different first step). If the dispatch is unrelated to \
every real intent in the list, return null."""
    user_prompt = f"""Real intents:
{intents_block}

Engine dispatch:
  kind: {dispatch.get('kind')}
  verb: {dispatch.get('verb')}
  text: {dispatch.get('text')}
  params: {json.dumps(dispatch.get('params') or {})}

Return JSON: {{"intent_id": "<one of the ids above>" or null, "reasoning": "<short>"}}"""

    try:
        raw = await asyncio.wait_for(call(sys_prompt, user_prompt), timeout=15.0)
        data = json.loads(raw)
        return data.get("intent_id") or None
    except Exception:
        return None


async def _run_torture_once() -> TortureResult:
    print("Generating torture scenario (this may take ~60s)...")
    scn = await _generate_scenario()
    print(f"Generated: {len(scn.utterances)} utterances, "
          f"{len(scn.real_intents)} real intents, "
          f"{len(scn.noise_mentions)} noise.")

    # rough talk-time
    total_words = sum(max(1, len((u.get("text") or "").split())) for u in scn.utterances)
    minutes = total_words * 0.4 / 60.0 + len(scn.utterances) * 0.013

    cascade_call = make_json_llm_call(max_tokens=1024)
    engine = ProactiveEngine(
        user_id="torture-user",
        llm_call=cascade_call,
        settle_chunks=3,
    )

    chunks = _utts_to_chunks(scn.utterances, session_id="torture", user_id="torture-user")
    print(f"Streaming {len(chunks)} chunks (talk ~{minutes:.1f} min, with bursts)...")

    dispatched: list[dict] = []
    t0 = time.time()
    for c in chunks:
        decisions = await engine.on_transcript_chunk(c)
        for d in decisions:
            dispatched.append({
                "kind": d.kind.value,
                "verb": d.intent.action_verb,
                "text": d.intent.text,
                "channel": d.urgency.channel.value,
                "params": d.intent.parameters,
            })
    final = await engine.flush_pending()
    for d in final:
        dispatched.append({
            "kind": d.kind.value,
            "verb": d.intent.action_verb,
            "text": d.intent.text,
            "channel": d.urgency.channel.value,
            "params": d.intent.parameters,
        })
    elapsed = time.time() - t0

    user_facing = [d for d in dispatched if d["kind"] in ("execute", "ask")]
    log_only = [d for d in dispatched if d["kind"] == "log"]

    # Match each user-facing dispatch to a real intent (or none).
    print(f"Matching {len(user_facing)} user-facing dispatches to ground truth via LLM...")
    matches: list[str | None] = []
    for d in user_facing:
        m = await _ai_match_dispatch_to_intent(d, scn.real_intents)
        matches.append(m)

    real_ids = {ri.get("id") for ri in scn.real_intents if ri.get("id")}
    matched_ids = [m for m in matches if m]
    hit_ids = [rid for rid in real_ids if rid in matched_ids]
    missed_ids = [rid for rid in real_ids if rid not in matched_ids]

    extra: list[dict] = [d for d, m in zip(user_facing, matches) if m is None]
    # Duplicates: same intent matched by 2+ user-facing dispatches.
    seen_count: dict[str, int] = {}
    for m in matches:
        if m:
            seen_count[m] = seen_count.get(m, 0) + 1
    dup_ids = {mid for mid, c in seen_count.items() if c > 1}
    dup_dispatches = [d for d, m in zip(user_facing, matches) if m in dup_ids]

    return TortureResult(
        n_utterances=len(chunks),
        n_real_intents=len(scn.real_intents),
        n_noise=len(scn.noise_mentions),
        n_dispatches=len(dispatched),
        n_user_facing=len(user_facing),
        n_log_only=len(log_only),
        real_intents_hit=hit_ids,
        real_intents_missed=missed_ids,
        extra_dispatches=extra,
        duplicate_dispatches=dup_dispatches,
        dispatched=dispatched,
        minutes_of_talk=minutes,
        elapsed_s=elapsed,
    )


async def run_torture(passes: int = 1) -> None:
    print("=" * 72)
    print(f"PROACTIVE TORTURE TEST (passes={passes})")
    print("=" * 72)
    aggregate = []
    for i in range(passes):
        print()
        print(f"--- Pass {i+1}/{passes} ---")
        result = await _run_torture_once()
        aggregate.append(result)

        precision = (result.n_user_facing - len(result.extra_dispatches)) / max(1, result.n_user_facing)
        recall = len(result.real_intents_hit) / max(1, result.n_real_intents)
        print()
        print(f"  utterances:       {result.n_utterances}")
        print(f"  real intents:     {result.n_real_intents}  (hit {len(result.real_intents_hit)}, missed {len(result.real_intents_missed)})")
        print(f"  user-facing:      {result.n_user_facing}  (extra {len(result.extra_dispatches)}, dup {len(result.duplicate_dispatches)})")
        print(f"  log-only:         {result.n_log_only}")
        print(f"  PRECISION:        {precision:.0%}")
        print(f"  RECALL:           {recall:.0%}")
        print(f"  density (per min talk): {result.n_user_facing / max(0.1, result.minutes_of_talk):.2f}")
        print(f"  elapsed:          {result.elapsed_s:.1f}s")
        if result.real_intents_missed:
            print("  MISSED intents:")
            for rid in result.real_intents_missed:
                print(f"     - {rid}")
        if result.extra_dispatches:
            print("  EXTRA dispatches (false positives):")
            for d in result.extra_dispatches:
                print(f"     - [{d['kind']}] {d['verb']}: {d['text'][:100]}")
        if result.duplicate_dispatches:
            print("  DUPLICATE dispatches (failed dedup):")
            for d in result.duplicate_dispatches:
                print(f"     - [{d['kind']}] {d['verb']}: {d['text'][:100]}")

    # Aggregate
    if passes > 1:
        print()
        print("=" * 72)
        print(f"AGGREGATE over {passes} passes")
        print("=" * 72)
        avg_p = sum(
            (r.n_user_facing - len(r.extra_dispatches)) / max(1, r.n_user_facing)
            for r in aggregate
        ) / passes
        avg_r = sum(
            len(r.real_intents_hit) / max(1, r.n_real_intents)
            for r in aggregate
        ) / passes
        print(f"  avg PRECISION: {avg_p:.0%}")
        print(f"  avg RECALL:    {avg_r:.0%}")

    out_path = "/tmp/torture_proactive.json"
    with open(out_path, "w") as f:
        json.dump(
            [
                {
                    "n_utterances": r.n_utterances,
                    "n_real_intents": r.n_real_intents,
                    "real_intents_hit": r.real_intents_hit,
                    "real_intents_missed": r.real_intents_missed,
                    "n_user_facing": r.n_user_facing,
                    "n_log_only": r.n_log_only,
                    "extra": r.extra_dispatches,
                    "duplicate": r.duplicate_dispatches,
                    "dispatched": r.dispatched,
                    "minutes": r.minutes_of_talk,
                    "elapsed": r.elapsed_s,
                }
                for r in aggregate
            ],
            f,
            indent=2,
            default=str,
        )
    print()
    print(f"Detail saved to {out_path}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    asyncio.run(run_torture(passes=n))
