# LISTENING DATA — the real captured days (handed to Omar, 2026-06-17)

This is the real listening corpus that exists in the repo — actual day recordings + transcripts, the
processed real-day, and the persona transcript banks. NOT training data; it is ours, used here as
listening/test data. Locations are absolute under `/Users/omarebrahim/Anticipy`.

## A. Real day RECORDINGS (audio) — ~220 MB, `realdays/`
| File | Size | Status |
|---|---|---|
| realdays/raw/2026-05-20_07_34_11.mp3 | 54 MB | TRANSCRIBED → realdays/raw/2026-05-20_07_34_11.transcript (    3228 timestamped lines; real morning, starts "Mama? … but i was going to shower") |
| realdays/holdout/2026-05-20_17_34_13 2.mp3 | 52 MB | transcribing → sidecar .transcript |
| realdays/holdout/2026-05-21_08_11_04 2.mp3 | 40 MB | transcribing → sidecar .transcript |
| realdays/holdout/2026-05-21_12_19_20.mp3 | 25 MB | transcribing → sidecar .transcript |
| realdays/holdout/2026-05-21_17_30_23.mp3 | 50 MB | transcribing → sidecar .transcript |

These are timestamped, diarized-ish transcripts (local Whisper, `engine/anticipy_engine/capture/transcribe.py`).
The same path the product uses for MP3 upload + always-on mic.

## B. Processed real day — `logs/last_realday.json` (44 KB)
A full real-day run already through the engine: decisions, events, glassbox tail, scorecard, line_count.

## C. Persona transcript banks — `factory/personas/` (23 day-files)
- `factory/personas/dev/*` — readable dev personas (founder_jin, teacher_rob, doctor_amara, …), day01/day02.
- `factory/personas/holdout/*` — honesty holdout (gradta_ming, retiree_frank, nurse_helen, chef_rosa) — day01.

## D. Live captured history (the running listening stream)
The running engine's memory holds the cumulative captured observations (history). Export any time:
`curl -s localhost:8787/memory/history` (the durable listening ledger the brain has heard).

## E. Synthetic 20-life × 5-day corpus (generated this session for testing)
`/tmp/life_*.json` (inputs) + `/tmp/life_*_out.json` (engine outputs) — 20 diverse lives, 5 days each,
run through the real engine. See `docs/e2e/twenty_lives/` for the scored bundle.

## How it is used for testing
- The real transcripts (A/B) are replayed through `ControlCore.owner_ingest` (the same brain the app calls).
- The personas (C) feed the cert + persona-life harnesses.
- The 20-life corpus (E) is the proactive 5-day-in-the-life gauntlet.
