# LOCAL-FIRST — the architecture law (Omar, 2026-08-05)

"Everything must be local-first architecture." This is not a feature
request; it is the ruling every design decision gets judged against, on
par with the paradox principle. Devices are the home of his life; the
cloud is a courier and a pair of hands, never the archive of who he is.

## The law, in one sentence

Understanding happens on the device; only CONCLUSIONS and OUTWARD ACTIONS
travel — and anything that must travel is the smallest word that works.

## The scoreboard today (be honest, keep it current)

| Component | Today | Local-first target | Status |
|---|---|---|---|
| Transcription (phone) | Apple on-device recognizer | stays local; improve locally (better local models), NEVER route audio to a cloud STT | ALREADY LAW-ABIDING — the earlier idea of moving phone STT to Deepgram is DEAD on this law |
| Speaker recognition | models proven local (Mac PoC); brain accepts the tag | voiceprint enrolled + matched ON DEVICE; only "owner/other" travels | designed law-abiding from day one (brief 09); iOS half = next build |
| Pendant audio | streams to phone over BLE | phone does ALL processing (STT + speaker), pendant is a microphone | law-abiding by design |
| Triage (the brain's judgment) | cloud LLM via OpenRouter on Railway | staged: (1) today cloud judges TEXT ONLY (never audio), (2) on-device small-model triage for the common case with cloud fallback for hard calls, (3) fully local judgment | CLOUD TODAY — the biggest open gap; fleet research item |
| Memory (the graph of his life) | lives in the worker container + PocketBase | primary copy ON DEVICE; server holds an ENCRYPTED sync/backup he holds keys to (roadmap §10) | CLOUD TODAY — second biggest gap; pairs with §10 privacy work |
| Research arm | server-side Brave + fetch | fine in the cloud FOREVER: it reads the public web, not him. Only the QUESTION travels, phrased as a goal, not his transcript | law-abiding (goals only) — audit that raw transcript lines stop riding in job params |
| Browser hands | his own Chrome on his own Mac | already the most local-first part of the system | law-abiding |
| SMS | Twilio | inherently a carrier service; message content is already the conclusion, not the raw life | acceptable; app-native delivery (push) reduces reliance later |

## Rules that bind every future change

1. RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone. If a
   capability needs better ears, find a better local model.
2. Voiceprints, embeddings, biometrics: computed on device, stored on
   device, never synced, never in git, never in PocketBase.
3. What travels is the smallest conclusion that works: a tag ("owner"),
   a goal ("book Earls Saturday 1pm for 4"), a decision — never the
   stream it came from, wherever we can help it. Work toward transcripts
   themselves becoming device-primary with encrypted sync (§10).
4. Cloud components must degrade gracefully when unreachable AND devices
   must keep capturing when offline (store-and-forward already exists;
   protect it).
5. Any new feature PR/brief states its local-first posture explicitly.
   "We'll localize it later" requires naming the later.

## The build order this implies (for the fleet)

1. Brief 09 iOS half — on-device speaker tagging (already specified).
2. Job-params audit: stop raw transcript lines riding to the cloud where
   a distilled goal suffices.
3. On-device triage pilot: measure a small local model against
   gemini-2.5-flash on the proof transcripts (dinner, Earls, speaker
   gate are the benchmark set — they already exist and are objective).
4. Memory-on-device design doc (pairs with §10 encryption/delete-my-day).
