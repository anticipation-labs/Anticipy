"""
Multi-speaker live diagnostic for the L0 SpeakerID layer.

Generates a realistic conversation involving the wearer + 1-2 other people
(e.g., a meeting, a call, a chat with a friend), labels which utterances
belong to which speaker, then pumps the WHOLE transcript (mixed speakers)
through ProactiveEngine. The L0 layer must drop non-wearer chunks before
they reach L1; we verify against the ground truth.

This catches the failure mode where the wearable would treat overheard speech
as user intent — silent-fail in any group setting.

Reports:
  - L0 wearer-classification accuracy (truth vs L0 verdict)
  - dispatched-decision accuracy (we should ONLY act on real wearer intents)
  - false positives: actions taken on overheard speech
  - false negatives: missed real wearer intents
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.proactive import ProactiveEngine  # noqa: E402
from app.proactive.llm_adapter import make_json_llm_call  # noqa: E402
from app.proactive.types import TranscriptChunk  # noqa: E402


GEN_SYSTEM = """You are creating a realistic transcript of a conversation that an \
AI assistant wearable hears in a group setting (a meeting, a phone call on speaker, \
a chat with friends in a cafe). The wearable has a diarization step upstream that \
TRIES to filter to the wearer's voice, but it is imperfect — sometimes a coworker's \
or friend's voice slips through. The L0 layer must catch these and drop them.

Generate a 30-60-utterance conversation with TWO OR THREE distinct speakers:
  - "wearer": the person wearing the assistant. Speaks ~50-65% of the lines.
  - "other_1", "other_2", etc.: the other participants. The wearer's responses \
mention or address them sometimes.

Some real-life specifics to vary:
  - The wearer should genuinely WANT 2-4 actionable things done (book, send email, \
search, schedule, etc.).
  - The OTHER speakers should mention things they want, but those are NOT wearer \
intents and the assistant must not act on them.
  - Include 1-2 cases of cross-talk: the wearer agreeing or responding to what \
another said, which is wearer-speech but contains the OTHER's words. Easy to confuse.
  - Include 1 quoted-speech case: the wearer says \"and then he said 'X'\" — the \
quoted X is wearer-speech (still the wearer's voice), it's the wearer telling a \
story, NOT another speaker.

Output STRICT JSON only:
{
  "summary": "<one sentence on the situation>",
  "wearer_real_intents": [
    "<one sentence per intent the wearer actually wants done>",
    ...
  ],
  "other_mentions_we_should_not_act_on": [
    "<one sentence per non-wearer goal mentioned>",
    ...
  ],
  "utterances": [
    {"speaker": "wearer" | "other_1" | "other_2", "text": "<utterance>", "diarization_hint": "wearer" | "other" | null},
    ...
  ]
}

Set "diarization_hint" to whatever the on-device diarizer would have guessed:
  - usually correct (wearer→"wearer", other→"other")
  - 10-20% of the time WRONG (label flipped) — this simulates a diarizer error \
that L0 must override using semantic context.
  - leave it null on a few (the diarizer was unsure).
"""


GEN_USER = """Generate one realistic 30-60-utterance multi-speaker conversation \
with the structure described."""


async def generate_multi_speaker_convo() -> dict:
    call = make_json_llm_call(max_tokens=4096)
    raw = await asyncio.wait_for(call(GEN_SYSTEM, GEN_USER), timeout=120.0)
    return json.loads(raw)


def utterance_to_chunk(idx: int, u: dict, base_ts: float, cursor_holder: list) -> TranscriptChunk:
    text = u["text"]
    words = max(1, len(text.split()))
    duration = max(0.5, words * 0.4)
    gap = 0.6 + (idx % 3) * 0.4
    start = base_ts + cursor_holder[0] + gap
    end = start + duration
    cursor_holder[0] = end - base_ts
    return TranscriptChunk(
        chunk_id=idx,
        session_id="multi-speaker-diag",
        user_id="diag-user",
        text=text,
        start_ts=start,
        end_ts=end,
        confidence=0.9,
        diarization_hint=u.get("diarization_hint"),
    )


async def run_diagnostic() -> None:
    print("=" * 70)
    print("MULTI-SPEAKER L0 DIAGNOSTIC")
    print("=" * 70)
    print()

    print("Generating multi-speaker conversation transcript...")
    convo = await generate_multi_speaker_convo()

    utterances = convo.get("utterances", [])
    print(f"Generated {len(utterances)} utterances")
    by_speaker: dict[str, int] = {}
    for u in utterances:
        spk = u.get("speaker", "?")
        by_speaker[spk] = by_speaker.get(spk, 0) + 1
    print(f"Speaker distribution: {by_speaker}")
    print(f"Real wearer intents ({len(convo.get('wearer_real_intents', []))}):")
    for x in convo.get("wearer_real_intents", []):
        print(f"   - {x}")
    print(f"Non-wearer mentions to ignore ({len(convo.get('other_mentions_we_should_not_act_on', []))}):")
    for x in convo.get("other_mentions_we_should_not_act_on", []):
        print(f"   - {x}")
    print()

    cascade_call = make_json_llm_call(max_tokens=1024)
    engine = ProactiveEngine(
        user_id="diag-user",
        llm_call=cascade_call,
        settle_chunks=3,
    )

    # Stream and collect L0 verdicts via the chunks' is_wearer field.
    base_ts = time.time()
    cursor = [0.0]
    dispatched: list[dict] = []
    l0_verdicts: list[dict] = []  # {chunk_id, true_speaker, l0_is_wearer, text}

    print(f"Streaming {len(utterances)} chunks through engine + L0...")
    t0 = time.time()
    for i, u in enumerate(utterances):
        chunk = utterance_to_chunk(i, u, base_ts, cursor)
        true_speaker = u.get("speaker", "?")
        decisions = await engine.on_transcript_chunk(chunk)
        # The engine sets chunk.is_wearer in-place after L0
        l0_verdicts.append({
            "chunk_id": chunk.chunk_id,
            "true_speaker": true_speaker,
            "l0_is_wearer": chunk.is_wearer,
            "diarization_hint": chunk.diarization_hint,
            "text": u["text"][:100],
        })
        for d in decisions:
            dispatched.append({
                "kind": d.kind.value,
                "verb": d.intent.action_verb,
                "text": d.intent.text,
                "channel": d.urgency.channel.value,
            })

    final = await engine.flush_pending()
    for d in final:
        dispatched.append({
            "kind": d.kind.value,
            "verb": d.intent.action_verb,
            "text": d.intent.text,
            "channel": d.urgency.channel.value,
        })
    elapsed = time.time() - t0

    # --- L0 accuracy ---
    n_wearer_truth = sum(1 for v in l0_verdicts if v["true_speaker"] == "wearer")
    n_other_truth = sum(1 for v in l0_verdicts if v["true_speaker"] != "wearer")

    correct_wearer = sum(
        1 for v in l0_verdicts
        if v["true_speaker"] == "wearer" and v["l0_is_wearer"] is True
    )
    correct_other = sum(
        1 for v in l0_verdicts
        if v["true_speaker"] != "wearer" and v["l0_is_wearer"] is False
    )
    missed_wearer = sum(
        1 for v in l0_verdicts
        if v["true_speaker"] == "wearer" and v["l0_is_wearer"] is False
    )
    false_dropped_wearer = missed_wearer  # L0 incorrectly dropped wearer
    leaked_other = sum(
        1 for v in l0_verdicts
        if v["true_speaker"] != "wearer" and v["l0_is_wearer"] is True
    )  # L0 admitted a non-wearer chunk into the cascade

    print(f"L0 elapsed wall-clock: {elapsed:.1f}s")
    print()
    print("=" * 70)
    print("L0 SPEAKER-ID ACCURACY")
    print("=" * 70)
    print(f"  Wearer truth count:       {n_wearer_truth}")
    print(f"  Other-speaker truth count: {n_other_truth}")
    if n_wearer_truth:
        print(f"  Wearer recall:  {correct_wearer}/{n_wearer_truth} = {correct_wearer/n_wearer_truth:.1%}")
    if n_other_truth:
        print(f"  Other precision (correctly DROPPED): {correct_other}/{n_other_truth} = {correct_other/n_other_truth:.1%}")
    print(f"  False drops (wearer treated as other): {false_dropped_wearer}")
    print(f"  Leaks   (other admitted as wearer):    {leaked_other}")
    print()
    print("=" * 70)
    print(f"DISPATCHED DECISIONS: {len(dispatched)}  (vs {len(convo.get('wearer_real_intents', []))} real wearer intents)")
    print("=" * 70)
    for i, d in enumerate(dispatched, 1):
        chan = d["channel"]
        kind = d["kind"]
        verb = d["verb"]
        text = d["text"][:80]
        print(f"  {i:2d}. [{kind:7s} {chan:6s}]  {verb:30s}  {text}")
    print("=" * 70)

    out = {
        "summary": convo.get("summary", ""),
        "wearer_real_intents": convo.get("wearer_real_intents", []),
        "other_mentions_we_should_not_act_on": convo.get("other_mentions_we_should_not_act_on", []),
        "speaker_distribution": by_speaker,
        "n_utterances": len(utterances),
        "l0_verdicts": l0_verdicts,
        "dispatched": dispatched,
        "n_dispatched": len(dispatched),
        "false_dropped_wearer": false_dropped_wearer,
        "leaked_other": leaked_other,
        "wearer_recall": (correct_wearer / n_wearer_truth) if n_wearer_truth else 0.0,
        "other_precision": (correct_other / n_other_truth) if n_other_truth else 0.0,
        "elapsed_seconds": elapsed,
    }
    out_path = "/tmp/multi_speaker_diagnostic.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print()
    print(f"Detailed result saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
