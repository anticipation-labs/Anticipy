# 07 Trivia Fire. Design.

Owner: Omar. Drafted 2026-05-29. Status: design, no code yet.

The smallest Anticipy moment. Omar and a friend debate when the Roman Empire fell. 1.2 seconds later his phone buzzes and his earbud reads "476 AD for the Western Roman Empire, 1453 for Constantinople." Conversation continues.

Constraints. 2 seconds end to end. 2 to 10 fires/day. Zero misfires in front of friends. Silent when wrong.

## 1. Trigger detection

Four-feature classifier on the rolling 8 second transcript plus prosody.

Lexical. Opener n-grams: "wait when was", "what year did", "who was the", "do you remember when", "is it true that", "I think it was X no it was Y", "actually wasn't it", "what's the name of that". Plus explicit triggers ("google it real quick", always fires). A 5 to 8 MB finetuned distilBERT on the phone emits an interrogative-factual probability per utterance.

Prosody. Rising F0 in the final 400 ms plus a 200 to 800 ms post-utterance pause. Computable from parakeet_mlx VAD. Without rising contour we downweight strong lexical matches: "what year did he do this, I cannot remember" is not a question.

Group context. Diarizer requires another speaker in the last 30 seconds for fire eligibility. Self-directed questions route to "look up later."

Recent answer. If any speaker produced a date, proper noun, or definition matching the question topic in the last 6 seconds, suppress (cosine-match the topic embedding against prior 6 seconds of token embeddings).

Rhetorical. (a) Self-talk ("why are we even doing this") filtered by diarizer + first-person + no second speaker. (b) Hyperbolic ("what year is it" at a slow webpage) gated by the confidence floor (Section 5) + a sarcasm head trained on Twitter corpora and labeled misfires. False-fire is embarrassing; false-miss is cheap. Target 90%+ precision, 50% recall.

Third-party. "Hey Jordan, when did you graduate" is a question to a person. Suppress if the utterance starts with a contact-graph name or has a vocative in the first 3 tokens.

## 2. Latency budget

2000 ms wall clock, speech-end to notification-delivered.

| Stage | Budget | Today | Gap |
|---|---|---|---|
| Audio to ASR partial | 0 ms | streaming | none |
| ASR finalize | 300 ms | 600 to 900 ms | streaming-finalize, not file-based |
| Intent classifier | 100 ms | n/a | new distilBERT 5 MB ONNX |
| Source dispatch | 20 ms | n/a | new, rule table |
| Answer fetch (Section 3) | 1000 ms | 2 to 4 s | streamed first-token + early-abort |
| Confidence + format | 100 ms | n/a | new |
| Notification delivery | 200 ms | 300 to 800 ms APNs | direct BLE + local notification, bypass APNs |
| Pendant haptic ack | 80 ms | n/a | parallel at t=0, off critical path |
| **Total** | **1720 ms, 280 ms slack** | | |

Engine changes. Engine today waits utterance-final via a file-based parakeet job adding ~500 ms. Switch to parakeet_mlx streaming, partial finals every 200 ms, 200 ms silence to commit. Intent classifier + dispatcher are new modules under `engine/app/trivia/`. Notification today is Mac engine → menubar → optional phone push via broker; for trivia route Mac engine → direct local BLE to earbuds + local APNs push (cached delegate token, no broker hop).

The 1000 ms answer fetch is the bulk and is fragile. Section 3 is how we hit it.

## 3. Answer source

Three lanes, classified at ~20 ms by the intent module.

Lane A, local cache. ~120 MB compressed SQLite of Wikidata's most-asked categories: historical dates, capitals, US presidents, sports champions, film release dates, definitions, atomic numbers, conversions. Hits in 5 to 15 ms. Estimated 35 to 45% coverage (AskReddit + r/NoStupidQuestions + trivia-podcast corpus). Killer for "when did the Roman Empire fall" because the fact + Constantinople nuance are pre-baked.

Lane B, grounded web LLM. On miss fire Perplexity Sonar Small Online (700 ms p50, `max_tokens=60`, first token ~250 ms). Primary because it returns a paragraph with citations and is the only endpoint we measured under 1 s for grounded recall. Brave + Sonnet-class is backup; ~900 ms, better on long-tail.

Lane C, no fire. Reject when (i) question requires user context, (ii) math (separate solver), (iii) current-events within 24 hours where cache is stale. Surfaces in the between-meeting digest.

Routing is rule-based; <20 ms. A miss falls through to B. Never run lanes in parallel: LLM cost on every A hit is a 10x bill multiplier. Lane A is the privacy-and-cost moat.

## 4. Surface

Three surfaces fire in parallel, gated by what's connected.

Pendant haptic. Single 80 ms pulse at t=0 (we accepted the trigger), before the answer is ready. Tells Omar "I heard you, I'm answering." Without it Omar repeats and we fire twice. Distinct rhythm from the "task done" pulse.

Earbud TTS. If AirPods or any BLE earbud is connected, answer streams as TTS. On-device voice (Apple synthesizer with custom profile), sub-100 ms text-to-first-audio. Ducks current audio 60%, restores after. Max 8 second read; longer truncates to "476 AD for the Western Empire. Tap for more."

Phone notification. Always fires. Title IS the answer, not "Anticipy answered your question." Lock-screen visible. Tap opens full answer + citation. Silent sound (haptic is the audible cue). Category `trivia` so Omar can mute it independently from actions.

Mac menubar. If pendant is paired to a Mac and no phone is reachable, menubar shows a one-line answer for 12 seconds, collapses to a counter. Click reveals last 10. No popup, no sound.

## 5. Confidence and restraint

Single confidence number 0 to 1 gates fire.

Computation. Lane A returns lexical-match plus freshness (cache age decayed). Lane B returns model self-reported confidence (Perplexity citation count + reasoning effort) plus cross-source agreement. Combine via a learned linear weight calibrated on 500 labeled questions.

Threshold. Fire at >= 0.85. Below, silent suppress, log to "look up later." Start at 0.85; ratchet toward 0.80 as calibration tightens.

What 0.85 buys. ~1 misfire per 100 fires at 0.85, against 5 fires/day: 1 misfire every 20 days per user. At 0.70 it's 1 in 10, unacceptable in a group.

Wrong-fire recovery. If Omar says "no that's wrong" within 8 seconds, log a negative label, re-search with a different source, and (only if sources disagree) fire the corrected answer once. If sources agree, stay silent. Either way the wrong-fire becomes a training example.

## 6. Anti-spam

Dedup. Hash the topic embedding. Same hash within 30 seconds in the same conversation: no second fire. Paraphrases hash the same.

Rate limit. Hard cap 1 fire per 60 seconds. Burst of 2 in 90 seconds if second is a follow-up at confidence >= 0.95. Daily soft cap 20; above, downgrade to "look up later" and digest at next conversation break.

Friend-group calibration. Diarizer assigns stable speaker IDs across conversations (voice-print hash, no name). For each (user, speaker-set) tuple, learn a topic-bias prior. Omar + Jordan = sports-bias-high, threshold drops to 0.78 on sports. Omar + parents = avoid-political, threshold rises to 0.95. Trained from thumbs-down + "dismissed immediately" signal.

Quiet. No fires during detected phone calls. No fires when calendar shows an "external" meeting unless explicitly enabled.

## 7. The killer demo

30 second product film, single take, handheld. Omar and a friend on a couch.

> Friend: "...and then the Roman Empire fell, what, 500 AD?"
> Omar: "I think it was earlier. Wait, when did Rome actually fall?"
> [1.2 seconds. Phone buzzes face-down on the table. Omar's earbud, just audible: "476 AD for the Western Roman Empire, 1453 for Constantinople."]
> Omar: "476. Western side. Constantinople held until 1453."
> Friend: "How do you know that?"
> Omar (taps the pendant): "I just do."

End card: "Anticipy. The answer arrives before you can pick up your phone."

No app, no wake word. Omar talks like a human; the device acts as memory. Friend never sees the tech. Single take.

## 8. Open problems

- Parakeet_mlx streaming finalize. We claim 300 ms; today is 600 to 900 ms file-based. Confirm MLX streaming hits target on M-series and phone-class chip.
- Perplexity p99 spikes to 3 s under load. Need hedged-request (fire Brave + cheap LLM after 800 ms of silence).
- Stale cache. Pre-baked Wikidata wrong on changed facts (Pluto, world records, country names). Freshness-tag + auto-invalidate.
- Sarcasm. The "what year is it" rant case. Mine from labeled misfires post-1000 users.
- Multilingual. v1 English-only. Out of scope.
- Group privacy. Voice-prints hashed; no raw audio or named identities stored. Needs disclosure + purge tool. Legal review before launch.
- Group consent. Pendant listens to people who didn't opt in. Two-party-consent states (CA, FL, MA) need counsel. Mitigation: visible LED when fire-eligible + "guest mode" suspends classification.
- Lecture misfire. Professor asks "what year was the Magna Carta signed" as a teaching prompt; earbud answers mid-lecture, classroom hears. Need lecture-mode (silent queue only).
