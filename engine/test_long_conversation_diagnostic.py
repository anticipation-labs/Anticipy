"""
Long-conversation spam diagnostic for the proactive engine.

Generates a realistic 8-12 minute conversation (50-100 user utterances) with
multiple distinct threads of intent and many incidental mentions, then pumps
it through ProactiveEngine and counts dispatched decisions.

Targets:
  - density < 1.5 dispatched decisions per minute of talk
  - duplicate-theme rate < 20%
  - no more than 8 dispatched decisions for one conversation regardless of length

If the engine is spammy, this will show it. The conversation is LLM-generated,
not hardcoded — anything we measure here applies to arbitrary real conversations.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass

# Ensure we can import the engine app modules
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from app.proactive import ProactiveEngine  # noqa: E402
from app.proactive.llm_adapter import make_json_llm_call  # noqa: E402
from app.proactive.types import TranscriptChunk  # noqa: E402


GEN_SYSTEM = """You are generating a realistic transcript of one person's spoken \
voice over an 8-12 minute span. They are wearing an AI assistant that hears \
their own voice (other people's voices have already been filtered out, so the \
transcript captures only their utterances). The conversation has:

- 3 to 5 DIFFERENT real intents the person genuinely wants done (book a doctor, \
buy a gift, send an email, search for something, etc.). Each intent should be \
mentioned across MULTIPLE utterances (a buildup, a clarification, sometimes a \
retraction).
- 2 to 4 things the person mentions but doesn't really want done — venting, \
hypotheticals, what-ifs, song-lyric quotes, things they're reading aloud.
- Lots of normal conversational filler: replies to other people (whose voices \
were filtered), small talk, thinking aloud, restarts, ums.

The transcript is 50-80 utterances total. Each utterance 3-25 words.

Output STRICT JSON only:
{
  "summary": "<one sentence describing what's going on>",
  "real_intents": [
    "<one sentence per intent the person actually wants done>",
    ...
  ],
  "noise_mentions": [
    "<one sentence per thing they mention but don't want done>",
    ...
  ],
  "utterances": [
    "<utterance 1>",
    "<utterance 2>",
    ...
  ]
}
"""


GEN_USER = """Generate one realistic 8-12 minute transcript with 3-5 real intents, \
2-4 noise mentions, and 50-80 total utterances.

Make it feel real. Don't make every intent obvious. Some real intents should be \
mentioned only once or twice in passing among the conversational filler. \
Different domains (work, health, family, errands, social).
"""


@dataclass
class GeneratedConvo:
    summary: str
    real_intents: list[str]
    noise_mentions: list[str]
    utterances: list[str]


async def generate_long_conversation() -> GeneratedConvo:
    call = make_json_llm_call(max_tokens=4096)
    raw = await asyncio.wait_for(call(GEN_SYSTEM, GEN_USER), timeout=120.0)
    data = json.loads(raw)
    return GeneratedConvo(
        summary=data.get("summary", "").strip(),
        real_intents=[s.strip() for s in data.get("real_intents", []) if s.strip()],
        noise_mentions=[s.strip() for s in data.get("noise_mentions", []) if s.strip()],
        utterances=[s.strip() for s in data.get("utterances", []) if s.strip()],
    )


def utterances_to_chunks(utterances: list[str], session_id: str, user_id: str) -> list[TranscriptChunk]:
    base_ts = time.time()
    chunks: list[TranscriptChunk] = []
    cursor = 0.0
    for i, u in enumerate(utterances):
        words = max(1, len(u.split()))
        # ~150 wpm spoken: 0.4s/word
        duration = max(0.5, words * 0.4)
        gap = 0.6 + (i % 3) * 0.4
        start = base_ts + cursor + gap
        end = start + duration
        cursor = end - base_ts
        chunks.append(TranscriptChunk(
            chunk_id=i,
            session_id=session_id,
            user_id=user_id,
            text=u,
            start_ts=start,
            end_ts=end,
            confidence=0.9,
        ))
    return chunks


async def run_diagnostic() -> None:
    print("=" * 70)
    print("LONG-CONVERSATION SPAM DIAGNOSTIC")
    print("=" * 70)
    print()

    print("Generating ~8-12 minute conversation transcript...")
    convo = await generate_long_conversation()

    total_seconds = 0.0
    if convo.utterances:
        # Approximate by word count at 150 wpm + gaps
        total_words = sum(max(1, len(u.split())) for u in convo.utterances)
        total_seconds = total_words * 0.4 + len(convo.utterances) * 0.8
    minutes = total_seconds / 60.0

    print(f"Generated {len(convo.utterances)} utterances (~{minutes:.1f} min of talk)")
    print(f"Real intents the user wants done ({len(convo.real_intents)}):")
    for i in convo.real_intents:
        print(f"   - {i}")
    print(f"Noise mentions ({len(convo.noise_mentions)}):")
    for n in convo.noise_mentions:
        print(f"   - {n}")
    print()

    cascade_call = make_json_llm_call(max_tokens=1024)
    engine = ProactiveEngine(
        user_id="diag-user",
        llm_call=cascade_call,
        # Use a short settle_chunks so dispatches happen mid-stream like prod.
        settle_chunks=3,
    )

    chunks = utterances_to_chunks(convo.utterances, session_id="diag-session", user_id="diag-user")

    dispatched: list[dict] = []
    print(f"Streaming {len(chunks)} chunks through engine...")
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

    print(f"Streaming finished in {elapsed:.1f}s wall-clock")
    print()
    print("=" * 70)
    print(f"DISPATCHED DECISIONS: {len(dispatched)}  (vs {len(convo.real_intents)} real intents)")
    print(f"Notification density: {len(dispatched) / max(0.1, minutes):.2f} per minute")
    print("=" * 70)
    for i, d in enumerate(dispatched, 1):
        chan = d["channel"]
        kind = d["kind"]
        verb = d["verb"]
        text = d["text"][:80]
        print(f"  {i:2d}. [{kind:7s} {chan:6s}]  {verb:30s}  {text}")
    print("=" * 70)
    print()

    user_facing = [d for d in dispatched if d["kind"] in ("execute", "ask", "refuse")]
    log_only = [d for d in dispatched if d["kind"] == "log"]
    print(f"User-facing (execute/ask/refuse): {len(user_facing)}")
    print(f"Silent log-only:                  {len(log_only)}")
    print()

    out = {
        "summary": convo.summary,
        "real_intents": convo.real_intents,
        "noise_mentions": convo.noise_mentions,
        "utterances": convo.utterances,
        "minutes_of_talk": minutes,
        "n_dispatched": len(dispatched),
        "density_per_minute": len(dispatched) / max(0.1, minutes),
        "n_user_facing": len(user_facing),
        "n_log_only": len(log_only),
        "dispatched": dispatched,
        "elapsed_seconds": elapsed,
    }
    out_path = "/tmp/long_conversation_diagnostic.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"Detailed result saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(run_diagnostic())
