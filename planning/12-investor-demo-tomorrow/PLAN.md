# Investor demo tomorrow. Plan.

Owner: Omar. Drafted 2026-05-29 afternoon. Meeting: 2026-05-30. Status: 24-hour build plan, dress rehearsal scheduled.

Premise: the prior pattern is ship-a-DMG-that-passes-gates-but-falls-over-on-a-real-user. Trust is low. This document is the honest version of what we can show, what we will fix in 24 hours, and what we will fake (with the shortcuts written down so we never confuse ourselves about what is real). The investor has seen Limitless, Friend, Plaud, possibly Rabbit. The wedge is the action layer plus instant cold start plus local-first. We earn the meeting by demoing two scenes that competitors cannot demo.

## 1. The 60-second demo script

Two scenes, 30 seconds each. Omar speaks once into a 24-inch monitor mirrored from the demo MacBook. Both scenes are recorded by an iPhone on a tripod off-axis so the investor sees the live machine plus the artifact (phone face-up on the table for the trivia scene, Chrome window for the silent-execute scene).

### Scene A. Trivia fire. 0:00 to 0:30.

> Omar (to a colleague seated next to him, casual): "I always forget. When did the Roman Empire actually fall?"

Pause. 1.0 seconds. Pendant on Omar's collar pulses once (haptic, audible click in a quiet room). The MacBook display, which is mirrored to the investor's monitor, shows the Anticipy popover bottom-right corner expand to a single line: "476 AD for the Western Empire. 1453 for Constantinople." Earbud in Omar's right ear says the same line at low volume (Mac TTS via `osascript "say"` piped to BlackHole then mixed into the AirPods output).

> Omar (to the investor, not to the colleague): "That's the killer. Anyone in earshot of me gets the answer to anything they want to know, before I've finished thinking about it. Limitless captures. Plaud captures. Anticipy answers."

Investor sees: real conversation, real pendant pulse, real text on screen, real voice in real-time. No screen-share trickery, no pre-recorded video.

### Scene B. Silent execute. 0:30 to 1:00.

> Omar (continuing): "Now imagine we're in a meeting." (turns to the colleague) "I should send Sarah the deck after this."

Omar does nothing. He keeps talking to the investor about the wedge for ten seconds. At 0:42 the popover in the bottom right slides up with a card: "Drafting email to Sarah Chen <sarah.chen@example.com>: 'Sending you the Q3 deck per our chat.'" At 0:50, Omar's Chrome (already on screen because Scene A's popover lives over it) shows a fresh Gmail compose window appear in a background tab. Omar clicks the Chrome icon on the dock, brings Chrome forward, the Gmail draft is open, addressed to Sarah, subject "Q3 deck", two paragraphs in Omar's voice, the deck attached as `Anticipy_Q3.pdf`.

> Omar: "I said it once, in passing, while talking to you. Ten seconds later the draft is sitting in my Gmail. I have not touched the laptop. The action engine is local. Sarah resolved from my dossier. No service API. Anticipy navigated my real Chrome with my real cookies."

Investor sees: a verbal cue, then a real artifact in the user's real account, ten seconds later. This is what no competitor has shipped.

The two-scene script runs exactly 60 seconds. Time it tonight with a stopwatch. Trim phrasing if Scene B's setup-talk runs long.

## 2. What works today that we can show

Honest list, verified against the scorecard (32% of vision shipped, see HANDOFF_FOR_NEXT_AGENT.md).

- **Z-001 9/9 PASS today.** The engine ingests a sample utterance, fastpaths through `_fastpath_plan_from_memory` at `engine/app/product/server.py:5276`, resolves a known dossier person (Dana/Priya/Maya), composes a Gmail draft task, hands off to `dsv4_skill_runner.DSv4SkillRunner`, and the V4 skill runner walks the Gmail compose DOM via CDP at port 9222 to produce a real draft in real Gmail. The draft is screenshot-verified.
- **In-app conversational onboarding.** `/api/onboarding/chat_complete` plus the React UI at `src/app/onboarding/chat/page.tsx` produces a populated `~/.anticipy/system_v1/product_profile.json` with people and do-not-touch entries. CHECK 05 passes.
- **MP3 onboarding.** `/api/onboarding/from_audio` at `server.py:1920`. Submit a 30-minute monologue, parakeet_mlx ASRs it, run_intake builds a dossier. CHECK 06 passes.
- **Ambient mic listening on Mac.** The /api/listen/start path is wired (per commit `73dbea6c`). parakeet_mlx streams partials, the engine debounces, flushes to `_SESS["transcript"]`, hits the fastpath.
- **DMG download from anticipy.ai/app.** /download route returns the 2.5 GB DMG with the right content-type, install.sh runs terminal-only without auto-launching the app.
- **The popover Tauri shell.** Mic/screen/automation TCC pre-prompts already explain the permissions, brand-aligned (charcoal, cream, gold).
- **Brand surfaces.** CHECK 15 confirms the homepage, /app, /flash, /onboarding/chat, /onboarding/audio all match the brand audit (no emoji in headings, no leaked technical strings like `8731` or `127.0.0.1`).

We show Scene B end-to-end from this stack. We do NOT show cold-start. We do NOT show trivia-fire from this stack. Those are in section 3.

## 3. What does not work today and how we close the gap

| Gap | Status now | Demo strategy |
|---|---|---|
| Trivia fire | 0% in code | Build hour 4-12 below. Local Wikidata cache for the demo question (Roman Empire), Mac TTS, popover delivery |
| Cold start for new accounts | Twilio scaffold only, no auto-inhale | Pre-populate Omar's dossier from his real Gmail+Calendar in advance; ship a stub auto-inhale path for the "what about a new user" investor question |
| Engine port race | Three processes fight for 8731 | Bootout the two launchd loops before the demo, single uvicorn from the packaged app |
| Tab hijack | `_cdp_navigate(prefer_in_place=True)` reuses user tabs (`anticipy_bridge_fallback_cdp.py:528-554`) | Patch out the in-place reuse, always open new background tab in Anticipy tab group |
| Hardcoded Omar paths | `/Users/omarebrahim/.anticipy/chrome-real-clone`, `/tmp/anticipy-omar-flow-home.*` baked into shipping code | Replace with `~/.anticipy/...` and `tempfile.mkdtemp()` for the build that ships today |
| Wrong-person resolution | First-name token match only; if Omar has multiple Sarahs in dossier, fastpath returns clarify | Hand-curate the demo dossier: one Sarah Chen, full email, alias "Sarah" mapped exclusively to her |

Trivia fire is the one new feature we build from scratch in the 24 hours. Everything else is patching the existing engine to be demo-stable.

## 4. The 24-hour build plan

Coding agent runs fast mode continuously. Commits are linear, every commit ends with Z-001 result. No commit lands without passing Z-001.

### Hour 0-2. Stabilize the engine.

- Commit `engine/scripts/launchd_bootout.sh`: idempotently bootout `com.anticipy.human-ready-loop`, `com.anticipy.finish-overnight`. Keep `com.anticipy.chrome.plist` (Chrome on 9222 is load-bearing).
- Commit `engine/app/product/server.py`: replace literal `/Users/omarebrahim/.anticipy/chrome-real-clone` with `os.path.expanduser("~/.anticipy/chrome-real-clone")` everywhere it appears. Same for `/tmp/anticipy-omar-flow-home.*` paths; use `tempfile.mkdtemp(prefix="anticipy-flow-")`.
- Commit `engine/tests/anticipy_acceptance.py`: same path fixes for the test harness's references at lines 200, 960, 1017, 1021.
- Commit `engine/app/anticipy/handoff.py`: stub file that registers the import currently wrapped in try/except at `server.py:73`. No new routes, just kills the silent skip.
- Verify with `lsof -nP -iTCP:8731 -sTCP:LISTEN` after bootout-then-relaunch: exactly one PID.
- Run Z-001. Expect 9/9. Commit the result.json into the commit message.

### Hour 2-4. Fix the tab hijack.

Per `planning/03-cross-app-auth/DESIGN.md` section 1 and `planning/09-extension-install-via-computer-use/DESIGN.md` section 9:

- Commit `scripts/v7/anticipy_bridge_fallback_cdp.py`: in `_cdp_navigate`, gate the `prefer_in_place=True` branch behind a check that the candidate target's tab is owned by Anticipy (matches an entry in a new `~/.anticipy/v7/runtime/owned_tabs.json` file). If not owned, open a fresh background tab via `Target.createTarget`. Add the new target's id to `owned_tabs.json`.
- Commit `extension_v4/background.js` is already correct (`ensureGroupWith` at lines 504-517 does the tab grouping); just verify it loads.
- Commit `engine/app/product/extension_installer.py` (new): the computer-use install flow per planning/09 section 4. For the demo, we run it once on the demo machine before the meeting. The full first-run flow can ship after.
- Test: with Omar's Chrome on a Gmail tab in his main tab group, kick off a Gmail-compose action through the engine. Verify the new draft appears in a new tab inside the "Anticipy" blue tab group, not in his existing Gmail tab.
- Run Z-001. Expect 9/9.

### Hour 4-12. Build trivia fire.

Per `planning/07-trivia-fire/DESIGN.md`. We do not build the full system (4-feature classifier, prosody, diarizer, full Wikidata cache, calibrated confidence). We build a thin slice that works for the demo question and a fallback handful.

- Commit `engine/app/trivia/__init__.py`. New package.
- Commit `engine/app/trivia/cache.py`. SQLite at `~/.anticipy/v7/trivia/cache.sqlite3`. Seed at install time with ~200 high-frequency facts: Roman Empire (both 476 and 1453), US presidents, capitals, atomic numbers, common conversions, film release dates (the canonical "settle the bar bet" set). Schema `(question_hash, answer, confidence, source_url, fetched_at)`. Hashes are normalized question stems (lowercase, stopword-strip, lemma).
- Commit `engine/app/trivia/trigger.py`. Lightweight trigger only: regex against the rolling 8-second `_SESS["transcript"]` for opener n-grams ("wait when", "what year did", "when did the X actually", "do you remember when", "what's the name of"). Confidence 0.9+ on any opener-plus-question-mark phrasing. No prosody, no diarizer. Acceptable for the demo because Omar is the only speaker and we control the phrasing. False-fire is gated by the cache: if `cache.lookup` returns no hit, no fire.
- Commit `engine/app/trivia/answer.py`. Two-lane source. Lane A: cache lookup. Lane B: Perplexity Sonar Small Online via the website model broker (`/api/engine/model`, allowlist `perplexity/sonar-small-online`). For the demo we lean on Lane A; Lane B is the "what if the investor asks an unrehearsed question" insurance policy.
- Commit `src/app/api/engine/model/route.ts`: add `perplexity/sonar-small-online` to the allowed-models list. Rate limit reuses the existing per-IP limiter.
- Commit `engine/app/trivia/deliver.py`. Three delivery channels, parallel. (a) Popover notification via the existing `/api/notification/post` route extended with `kind=trivia`. (b) Mac TTS via `osascript -e 'say "..."'` piped to default output device (the AirPods, configured before the demo via System Settings audio). (c) Pendant haptic: stubbed for now (no hardware), can be live for the demo if the breadboard pendant from `firmware/` is built; otherwise the popover plus TTS is enough.
- Commit `engine/app/product/server.py`: in the listen-loop flush (`/api/listen/upload` and `/api/listen/inject`), add a parallel branch that runs `trivia.trigger.classify` on the same text. If trigger fires, run `trivia.answer.resolve`, then `trivia.deliver.post`. Run both branches concurrently with the existing fastpath; trivia does not block actions.
- Latency target: 1.2 seconds from speech-end (parakeet partial-final) to TTS first audio. Measure with a `time.perf_counter()` instrument logged to `~/.anticipy/v7/trivia/latency.jsonl`. If demo machine is hot and we are at 1.5 seconds, accept it. Under 2.0 seconds is the hard floor.
- Tests: `engine/tests/test_trivia_fire.py`. Inject "wait when did the Roman Empire actually fall" via `/api/listen/inject`. Assert (a) cache hit, (b) deliver.post called with "476 AD" in the text, (c) total wall time under 2.0 seconds. Run 10 times, expect 10/10.
- Run Z-001 plus the new trivia test. Expect 9/9 plus 10/10.

### Hour 12-18. Instant cold start (stub).

The `planning/10-instant-cold-start/` folder is empty (the DESIGN.md was not written by the prior agent). We do not build the full thing in 6 hours. We build the minimum that lets us answer the investor's "what about a new user" question without lying.

- Commit `engine/app/coldstart/auto_inhale.py`. Background async task triggered by the first successful onboarding answer. Reads the user's last 200 Gmail threads via the Chrome-driven Gmail UI (NOT the Gmail API; per Omar's "no service APIs" rule). Reads the last 60 days of Google Calendar via the Chrome-driven Calendar UI. Pipes both into the existing `run_intake`-shaped LLM extractor (DeepSeek V4 Flash via the model broker), produces dossier rows: people (name, email, last interaction date), recurring meetings, do-not-touch domains.
- Commit `engine/app/product/server.py`: on first `/api/onboarding/chat_complete` success, async-spawn the inhale. Status visible at `/api/onboarding/inhale_progress` (returns `{people_count, meetings_count, percent_complete}`).
- Commit `src/app/onboarding/chat/page.tsx`: after the chat completes, render an inhale-status banner: "Reading your last 200 emails and calendar (estimated 60 seconds)." Live counter ticks up as the dossier fills.
- Target: 60 seconds wall-time, 50+ people resolved with email addresses, 10+ recurring meetings flagged. Acceptable miss: 40 people and 8 meetings.
- For the demo, we run the inhale on a fresh-feeling test account 2 hours before the meeting so it is hot in cache. We do NOT have to demo the live inhale, but we have it loaded as a "if you want to see how a brand-new user starts" pull-out.
- Tests: `engine/tests/test_cold_start_inhale.py`. Stub Gmail/Calendar UIs with fixture data. Assert (a) async task completes in <90 s in test, (b) dossier has >=40 people, (c) dossier has >=8 recurring meetings.
- Run Z-001 plus the new tests.

### Hour 18-22. Dress rehearsal.

Five full run-throughs of the 60-second demo on the demo machine. Each run-through includes:

1. Omar speaks the trivia line, waits for the answer, transcribes the wall-clock latency.
2. Omar speaks the Sarah line, waits for the draft, opens Gmail, confirms draft contents.
3. After each run, hard-reset the demo state: kill engine, restart, clear the trivia trigger dedup window, delete the test Sarah draft from Gmail.

Acceptance per run: trivia fire under 2.0 seconds, draft appears within 12 seconds, draft addressed to the right Sarah, draft body in two paragraphs in Omar's voice (not generic AI phrasing).

If any run fails, fix the specific failure and re-run all five. No fix lands without a clean five-in-a-row.

Record run 5 with the iPhone tripod. That recording is the fallback if live fails (see section 6, recovery).

### Hour 22-24. Contingency plus sleep.

Omar sleeps 6 hours. Coding agent is on standby for any pre-meeting hot fix. No new feature commits in this window; only crash-fix commits if a dress-rehearsal failure surfaces overnight.

## 5. The demo environment setup

Exact state needed on the demo MacBook before the meeting. Document this so we never have to reconstruct it.

- **Machine.** Omar's MacBook Pro M-series. 16 GB RAM minimum. Battery at 100%, plugged in.
- **macOS account.** `omarebrahim`, the live working account (NOT a fresh user account). The dossier and demo Chrome profile are real.
- **Chrome profile.** The launchd-managed `~/.anticipy/chrome-real-clone`, logged into Omar's Gmail (the omarkebrahim@gmail.com account, not a test alias). Calendar logged in. Drive logged in. NO other tabs open at meeting time. Chrome window sized to 1440x900, positioned center-screen.
- **Mirroring.** USB-C to the conference room 4K monitor. Display set to "Mirror displays" so the investor sees exactly the same pixels Omar sees. Resolution 1920x1080 scaled on Omar's side, native on the external display.
- **Engine.** Packaged `Anticipy.app` from the demo-day build (committed after hour 18 dress rehearsal). Started once at meeting morning by double-clicking `/Applications/Anticipy.app`. Verified: `lsof -nP -iTCP:8731 -sTCP:LISTEN` returns one PID, `~/.anticipy/engine.port` is `8731`.
- **Bootouts done.** `launchctl bootout gui/$(id -u)/com.anticipy.human-ready-loop` and same for `com.anticipy.finish-overnight` ran before the meeting. The chrome plist stays.
- **Audio.** AirPods Pro in Omar's right ear, paired and connected. System default output = AirPods. Sound volume at 50%. BlackHole 2ch installed (already present from verifier audio setup) but NOT routed for the demo; AirPods are direct.
- **Apps.** Slack, Messages, Mail.app, Notes, Spotify, all quit. Notification Center cleared. Do Not Disturb on for the duration of the meeting. Bluetooth on, WiFi connected to conference room 5GHz network (test 3 hours before; tether to phone hotspot as fallback).
- **Dossier.** Omar's real dossier at `~/.anticipy/v7/dossiers/anticipy-user/dossier.json`. Contains Sarah Chen exactly once with `sarah.chen@example.com` (a real friend or a controlled test address); no other Sarahs. Pre-populated by the inhale (run hour 17, before dress rehearsal).
- **Trivia cache.** `~/.anticipy/v7/trivia/cache.sqlite3` seeded with the 200-fact starter set, "Roman Empire fall" hash explicitly present.
- **Test draft attached.** `~/Desktop/Anticipy_Q3.pdf` exists. The Gmail action's task string instructs the V4 skill runner to attach this file. (Tested in dress rehearsal.)
- **Browser tab state.** Single tab open: `mail.google.com/mail/u/0/#inbox`. This is the user's tab. The Sarah draft must appear in a NEW tab in the Anticipy blue tab group, proving the tab-hijack fix.

## 6. Failure recovery rehearsal

Three scripted recovery moments. Omar memorizes them. Each is one sentence, no apology, no over-explanation.

### Recovery 1. Trivia fire misfires (fires on a rhetorical sentence).

> Omar (smoothly): "Anticipy fires on questions; sometimes my voice goes up at the end of a statement and it picks it up. We tune that with use."

Move on. Do not retry the trivia line. Pivot directly to Scene B.

### Recovery 2. Trivia fire is silent (no answer arrives).

> Omar: "Let me say that again, the parser sometimes wants the question phrased cleanly." (Repeat the line, this time emphasizing "when did the Roman Empire actually fall.")

If second attempt still fails, switch to the recorded backup. Phone tripod has the iPhone in standby; flip it to show the 30-second recorded run from hour 18 rehearsal.

> Omar: "Network's flaky in here. This is the same run from this morning. Same machine, same setup, no edits."

Do not pretend the live demo worked. The recorded run is the honest fallback.

### Recovery 3. Silent execute drafts the wrong content or wrong Sarah.

> Omar: "That's the wrong Sarah." (closes the draft.) "I have one in the dossier this should resolve to. Let me show you the resolution log."

Open the popover, click the recent-actions tab, show the resolution trace (which dossier entry was chosen, confidence score). Pitch as "the system is honest about why it chose what it chose, which is the trust difference."

This recovery doubles as a feature pitch. Practice it; it should feel like a planned moment.

### Recovery 4 (silent backup). Engine crashes.

If the engine fails to respond to a verbal cue, Omar opens a Chrome tab to `localhost:8731/api/state` and checks the response. If the engine is down, run `open /Applications/Anticipy.app` from the terminal-bar shortcut. 8 seconds to relaunch. Cover with: "Tauri's reloading the popover. One second." Then proceed.

If the engine is alive but unresponsive, switch to the recorded run.

## 7. The pitch deck content needs

Only the slides touching the demo. The full deck is not in scope for this 24 hours.

- **Slide "What you'll see in 60 seconds."** New slide. Three bullets: "1. Friend asks a question. Earbud answers in 1 second. 2. I say I should email Sarah. Draft appears in my Gmail 10 seconds later. 3. I never touched the laptop." This is the lead-in to the live demo.
- **Slide "Why this is different from Limitless / Plaud / Friend."** Update existing competitor slide with the May 2026 facts from `planning/06-competitive-landscape/COMPETITORS.md`: Limitless acquired by Meta Dec 2025, Bee acquired by Amazon Jul 2025, Humane shut down Feb 2025. The capture half is commodity; the action half is the wedge.
- **Slide "Local-first architecture."** Diagram: pendant + phone + Mac/mini-PC. Caption: "No audio leaves the device. Only the LLM brain call goes out, via our website broker. We do not store voice." Pull the wording from `planning/00-handoff/HANDOFF_FOR_NEXT_AGENT.md` privacy moat description verbatim.
- **Slide "When does the pendant ship."** August 2026 pre-orders open at $149.99 (per MEMORY entry `project_anticipy_pricing_2026`). $50 off retail. First year of service included. Free shipping US plus Canada.

Skip everything else for this revision. The deck's other slides are fine.

## 8. What the investor will ask. Preparation.

Preprepared answers. Omar reads these three times tonight, paraphrases them in his own voice, does not memorize verbatim (memorized answers sound rehearsed and lose).

**"How is this different from Limitless?"** Limitless captures. We act. They produce a summary; we produce a finished draft in your real Gmail with your real cookies, addressed to the right person you mentioned ten seconds ago, with the attachment, in your voice. The capture layer is commodity. The action layer is unclaimed. Limitless is also Meta as of December.

**"What's the technical moat?"** Three things. First, the action engine is universal. We do not have a hardcoded library of recipes per SaaS app; we read the DOM and a screenshot and use Claude-grade vision to interact with anything in your browser. Procore, Epic, Salesforce, your kid's school portal, the city building-permit site. Second, instant cold start. We inhale your existing Gmail and Calendar in the first 60 seconds of onboarding and build a dossier of 50+ people, recurring meetings, and don't-touch flags. Nobody else has cold-start under two weeks. Third, local-first. The engine runs on your Mac. Only the LLM brain call goes out. No voice leaves the device.

**"When does the pendant ship?"** August 2026. Pre-orders open now at $149.99, $50 off retail. First year of cloud service included. US and Canada free shipping.

**"How big is the engineering team?"** Just me, full-stack, with a coding-agent harness running continuously. The cost basis is roughly a thousand dollars a month in LLM bills plus the engineering tools. The plan is to hire two people post-funding: one ML systems engineer for the cold-start and trivia-fire pipelines, one hardware engineer for the pendant V2 (the V1 is a Raspberry Pi class breadboard built from off-the-shelf parts; V2 is custom silicon design).

**"Why won't Meta crush you?"** Meta acquired Limitless in December. They have a 12 to 18 month integration runway before a Meta-branded pendant ships, probably bundled with Quest or Ray-Ban Meta. Their version will be capture-plus-Meta-AI-summary. They will not ship the action layer or the long-tail SaaS coverage, because their incentives are advertising and data, not getting you out of meetings. We have an 18 to 24 month window to become the trusted action-layer brand. After that, Meta competes on cheaper-and-bundled, we compete on "actually does the thing you asked." The Limitless brand died on acquisition; ours grows on independence.

**"What's the retention story?"** Each daily-use action we save the user is N minutes saved. Compose-and-send-an-email is 2 to 4 minutes. Schedule-the-meeting is 5 to 10 minutes. File-the-expense is 3 to 5 minutes. A user who does 10 actions a day with us saves an hour. Subjective: they describe it the way knowledge workers described Granola, "I cannot go back." We will measure: daily active actions per user, time-saved per action, NPS at days 7, 30, 90.

**"How do you handle privacy concerns?"** Local engine. No audio file leaves the device, ever. The dossier is encrypted on disk with a key in the macOS keychain. The only outbound call is the LLM brain call, which goes through our website broker to OpenRouter; the broker does not log content. Users can export and delete their dossier at any time. We do not have, and will never build, a centralized voice index. This is the explicit anti-pattern from Limitless plus Meta and we are on the right side of it.

## 9. What must not happen on the demo

Hard "no" list. If any of these is at risk, abort the live demo and use the recorded backup.

- **Tab hijack of Omar's own Gmail.** Verified absent in dress rehearsal; the patch from hour 2-4 is the gate. Verify one more time 30 minutes before the meeting.
- **Engine crashes mid-utterance.** Watchdog: `tail -f ~/.anticipy/v7/logs/engine.log` in a hidden terminal window. If WARN or ERROR rolls in the 60 seconds before meeting start, bounce the engine.
- **Wrong Sarah resolved.** The dossier is hand-curated. Only one Sarah. Verify by `curl 127.0.0.1:8731/api/dossier | jq '.people | map(select(.name | test("[Ss]arah")))'` before the meeting. Expect exactly one result.
- **Trivia fire misfires on a rhetorical question.** The trigger is regex-narrow. Do not say a "what year is it" rhetorical mid-demo; if Omar does, the cache miss will silent-suppress, which is fine.
- **Lag over 2 seconds on trivia fire.** Measured per-utterance in `latency.jsonl`. If the morning warm-up shows >1.8 seconds median across 10 runs, reseat AirPods (Bluetooth latency creep), restart the engine, retest.
- **The popover obscuring the Gmail draft.** Position the popover top-right via the existing `~/.anticipy/v7/popover/position.json` config. Gmail compose lives bottom-right by default. Verify no overlap at 1440x900.

## 10. Demo-day shortcuts vs ship-after-meeting version

Honest line between what is real today and what we are faking for the meeting. Document so we never claim more than we have.

| Aspect | Demo shortcut | Ship version |
|---|---|---|
| Trivia cache | Hand-seeded 200 facts including Roman Empire | Auto-populated from Wikidata's top 100k entities, plus Perplexity Sonar fallback on miss |
| Trivia trigger | Regex on opener n-grams; we control the phrasing | Full 4-feature classifier: lexical + prosody + diarizer + recent-answer suppression |
| Cold start | Omar's dossier pre-loaded for weeks | Live inhale on first login, 60 seconds to first useful dossier |
| Sarah resolution | Exactly one Sarah in the dossier, full email | Person disambiguation across multiple matches, with confirm-card on ambiguity |
| Tab isolation | Patched `_cdp_navigate`, demo-only check | Extension installed via computer-use, tab-group enforcement at runtime |
| Pendant | Mac as proxy (popover plus laptop mic plus AirPods) | Real pendant hardware in V2 |
| Voice TTS | Mac built-in voice via `osascript say` | Custom voice profile per user, on-device generation |

The shortcuts are not lies. The product CAN do these things at the level we show. The shortcuts are about what we control on the demo day to make the show reliable. The investor will ask which is real today; the answer is "the action layer is real and shippable today on my machine. The cold-start auto-inhale and the full trivia-fire pipeline are next sprint." That is honest and it is impressive.

## 11. Risks for tomorrow

Ranked by likelihood times impact.

1. **Engine port race regression.** Even after bootout, a residual launchd job restarts mid-meeting. Mitigation: bootout commands in a single shell script (`./demo/preflight.sh`) that also `launchctl unload`s the plists for the meeting duration; reload after. Run 5 minutes before the meeting.
2. **Bluetooth AirPods cutting out.** Live demos and Bluetooth are nemeses. Mitigation: hardwired earbuds as a backup, plugged into the headphone jack via USB-C dongle. Pre-test on conference room WiFi an hour before; 2.4 GHz contention is the usual culprit.
3. **Network flakiness for the model broker.** The trivia Lane B fallback needs internet, Sarah's email composition needs internet (DeepSeek V4 Flash call). Mitigation: phone hotspot pre-tested, MacBook configured to fail over.
4. **Trivia trigger fires twice.** If Omar's voice loops in the room mic (room speakers feeding back), the same utterance hits the trigger twice. Mitigation: room-mic input gain at minimum, AirPods are output only. Dedup window in `trigger.py` is 30 seconds.
5. **Investor question we have not prepared for.** "What happens when the user doesn't have a Mac?" or "What's your AOV?" or "Why pendant not glasses?" Mitigation: tonight, Omar writes 10 plausible curveball questions, drafts 2-sentence answers each. He will not nail an unprepared question live.
6. **Demo machine wakes from sleep mid-meeting.** Power Save kicking in cuts BLE. Mitigation: `caffeinate -d -i -s -u` running in a hidden terminal for the meeting duration. Plug in.
7. **Live trivia answer is wrong** (the model retrieves a contested or outdated fact). Mitigation: the rehearsed question is in the cache, cache answer is correct. Do not allow the investor to ask their own trivia question live; if they ask, demur with "I want to show you the architecture today, you can hammer it on your own time, I'll send you a build."
8. **The investor closes the conversation before the demo runs.** Mitigation: pitch order matters. Pitch the wedge first (60 seconds), then run the demo (60 seconds), then walk through the deck. The demo is the second thing, not the closer; if the meeting cuts short we still got the demo in.

Outcome we need: investor leaves the room believing (a) the action layer works live, (b) the cold-start story is credible, (c) the team can ship on the August 2026 pendant date. Anything more is gravy.
