# Proactive Engine

A five-layer AI cascade. Every layer that detects user intent is an LLM call — no regex, no keyword tables, no structural-pattern matchers. Per Omar's directive 2026-05-01.

## The cascade

```
TranscriptChunk
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ L1  SalienceClassifier   AI: actionable y/n, confidence    │
└─────────────────────────────────────────────────────────────┘
   │ (if salient AND throttle clear)
   ▼
┌─────────────────────────────────────────────────────────────┐
│ L2  Interpreter (extract) AI: free-form verb + intent text │
│                              + parameters + confidence      │
└─────────────────────────────────────────────────────────────┘
   │ for each extracted intent
   ▼ in parallel via asyncio.gather:
┌────────────────────┐ ┌─────────────────┐ ┌───────────────┐
│ L3 Reversibility   │ │ L4 UrgencyScorer│ │ L5 DonnaPass  │
│ AI: rev/irr/unknown│ │ AI: 1..5        │ │ AI: refuse y/n │
└────────────────────┘ └─────────────────┘ └───────────────┘
   │ all three feed into:
   ▼
┌─────────────────────────────────────────────────────────────┐
│ Decider._route()  pure function over AI signals → kind      │
│   donna.refuse        → REFUSE                              │
│   irreversible/unknown → ASK                                │
│   confidence ≥ 0.85   → EXECUTE                             │
│   confidence ≥ 0.50   → ASK                                 │
│   else                → LOG                                 │
└─────────────────────────────────────────────────────────────┘
   │
   ▼
Notifier (channel by urgency)  +  Executor (browser agent on EXECUTE)
```

## Why no rules

Per Omar's directive on 2026-05-01: "no hardcoding ... no keywords ... no structural cues — it has to be done by an AI model. Many layers of intent detection. Free AI models for most things unless it's very complicated."

The cascade is the answer. Five small AI calls beat one big rule table because:

- The cheapest layer (salience) runs on every chunk and drops ~95% — saving the four expensive layers from running on smalltalk and silence.
- The expensive layers (extraction, reversibility, urgency, Donna) run only on the salient ~5% of chunks, in parallel, costing maybe a half-cent total per actionable utterance.
- New behaviors don't need code changes. The LLM generalizes.
- Adversarial scenarios (the user contradicts themselves; quotes a movie line; vents without committing) are handled by *context-aware models*, not rules that miss the obvious cases.

## What runs where

**Server-side reference implementation** (this package, in Python): every layer is an LLM call to a cheap chat model. Fine for development and the existing engine deployment.

**Phone-side native port** (eventual; Swift / Kotlin): L1 ideally runs on a 1-3B on-device NPU model (sub-100ms, free). L2-L5 can run on-device with 3-7B models, OR stream to server depending on phone capability and battery state. The boundary is the `Executor` protocol in `engine.py` — that's the only thing that has to round-trip to a server, because the browser agent itself isn't viable on a phone.

## Layer-by-layer cost / latency budgets

| Layer | Fires | Model class | Budget |
|---|---|---|---|
| L1 Salience | every chunk | tiny (1-3B / Groq Scout) | <200 ms |
| L2 Extract | ~5% of chunks | small (Haiku 4.5 / Gemini Flash) | <3 s |
| L3 Reversibility | per intent | small | <2 s, parallel with L4/L5 |
| L4 Urgency | per intent | small | <2 s, parallel with L3/L5 |
| L5 Donna | per intent | small | <2 s, parallel with L3/L4 |

Total wall-clock from chunk arriving to decision: under 5 s p95. Cost: **<$0.001 per actionable utterance** with cached prompts on Anthropic, lower on Groq free tier.

## What the engine doesn't do

- Capture audio. (Wearable does.)
- Transcribe. (Phone does, on-device: Silero VAD → Sortformer diarization → Parakeet V3 ASR on the NPU.)
- Store raw audio. Ever. Anywhere.
- Act on speech that isn't from the user's diarized voice cluster. The diarization gate is upstream of this package.
- Decide what an action *does* — that's `engine/app/agent.py` (Browser Use).
- Bypass `engine/app/safety.py`. Hard safety blocks (delete-account, wire-transfer, etc.) are still the deterministic guard. They don't detect intent — they refuse specific actions outright.

## Module structure

```
engine/app/proactive/
├── README.md           this file
├── types.py            data classes
├── context.py          sliding-window buffer + semantic memory
├── interpreter.py      L1 SalienceClassifier + L2 Interpreter (extract)
├── reversibility.py    L3 ReversibilityClassifier (AI)
├── urgency.py          L4 UrgencyScorer (AI)
├── donna.py            L5 DonnaPass (AI)
├── decider.py          combines L3-L5 + confidence into DecisionKind
├── notifier.py         escalating channel selector (NOTED→IN_APP→PUSH→SMS→VOICE)
├── notes.py            always-on notes recorder (LLM compaction)
├── engine.py           top-level facade
└── eval/
    ├── harness.py      runs N synthetic scenarios, scores with judge
    ├── scenarios.py    LLM-generated synthetic conversations
    └── judge.py        LLM-as-judge for outcome correctness
```

## API surface

```python
engine = ProactiveEngine(
    user_id="...",
    llm_call=...,                # cheap chat model for L2-L5
    salience_llm_call=...,       # optional: even cheaper / on-device for L1
    executor=...,                # browser agent (engine/app/agent.py)
)

await engine.on_transcript_chunk(chunk)         # phone calls per diarized chunk
await engine.on_confirmation(decision_id, "yes") # user replied to ASK
engine.set_notes_mode(enabled=True)              # privacy toggle
```

## Testing

**Adversarial eval harness** in `eval/harness.py` is the primary regression guard. It:

1. Generates `N` synthetic conversations using an LLM, drawn from 15 scenario categories (direct command, implicit intent, multi-turn buildup, user changes mind, self-talk venting, distractor, urgent, quoted speech, question to self, ambiguous, contradicts recent intent, emotional Donna-refuse, reversible low-stakes, etc.). The LLM gets only the *shape* of the scenario; it fills in everything else.
2. Streams each scenario through `ProactiveEngine.on_transcript_chunk` chunk by chunk.
3. Captures the cascade's actions, questions, notes.
4. LLM-as-judge scores every scenario on four axes (acted-when-should-have, silent-when-should-have, channel-appropriate, refusal-appropriate) — never told the expected answer in advance.

Targets: correctness > 0.85, FP < 0.1, FN < 0.15, channel-appropriate > 0.8.

This is the only acceptable way to test "works on everything." Hardcoded fixtures pass tests but don't generalize. Synthetic + judge generalizes by construction. New scenario categories are a one-line addition; no other code changes.

**Deterministic unit tests** in `engine/test_proactive.py` cover only the AI-output-combining layer:
- decider routing (pure function over AI signals)
- urgency-to-channel mapping
- channel ladder fall-down
- context buffer time-windowing
- end-to-end engine wiring with all five LLMs mocked

Run: `cd engine && python test_proactive.py`. No pytest required.
