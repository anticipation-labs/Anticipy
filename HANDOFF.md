# ANTICIPY — COMPLETE HANDOFF DOCUMENT

**Written by:** Devin (Cognition), session ending 2026-07-21
**Written for:** the next agent — expected to be Claude (Opus/“Fable 5”) running LOCALLY on Omar's MacBook Air
**Owner:** Omar Ebrahim — okebrahim@icloud.com — phone +1 604 724 5161 — GitHub `omize10`
**This repo:** everything the previous agent built. Read this file FIRST, top to bottom, before touching anything.

---

## 0. HOW TO USE THIS DOCUMENT (next agent, start here)

You are inheriting a working, partially-proven system. Nothing here is hypothetical unless it is
explicitly marked NOT PROVEN. The single most important thing Omar cares about is that you
**do all of it, end to end, with proof** — he has repeatedly been burned by agents doing 1 of the
10 things he asked. His words, verbatim, are in §2. Read them. They ARE the spec.

You are running locally on his Mac, which changes everything for the better:
- No SSH tunnels needed (the previous agent worked over expiring 60-min Pinggy tunnels).
- Xcode, the signing certs, provisioning profile, and App Store Connect API key are ALREADY on this Mac (§8).
- His real Chrome is right there — load the extension from `extension/` directly (§7).
- The pendant can be plugged into this Mac for flashing (§9).

Priorities in order (his explicit ranking):
1. Software must be 100% before firmware is flashed ("It better be 1 trillion percent before even thinking about firmware").
2. Research deeply before building — web search, primary sources, not skimming ("I cannot stress to you the importance of research").
3. Prove everything with real runs and recordings. Never claim done from source code alone.
4. Text-before-browser: for ambiguous/consequential things, Anticipy texts the owner FIRST, acts after the reply.
5. Confirmation for anything irreversible lives OUTSIDE the model (in the job queue), always.

---

## 1. WHAT ANTICIPY IS

A premium wearable pendant + proactive personal assistant. The pendant hears your day; Anticipy
(she has a name, a warm first-person voice) extracts commitments and intents from the transcript,
remembers them in a temporal knowledge graph, and proactively acts: research and actions in the
owner's own Chrome via a browser extension, texts and phone calls via Twilio, all orchestrated by
one central brain, with the owner's confirmation gating anything irreversible.

End state (the full vision, all user-mandated):
- Jewelry-grade pendant: Seeed XIAO nRF52840 Sense, onboard PDM mic, Opus @16 kHz mono over BLE,
  ~500 mAh LiPo, magnetic charging, necklace attachment, rounded premium enclosure, 3D-printed
  prototypes → ~100 identical units via contract manufacturing.
- Custom iOS app (real Anticipy brand), BLE state restoration + auto-reconnect forever, local
  (on-device) or cloud transcription, proactive feed, in-app confirms, TestFlight → App Store.
- Chrome extension in the USER'S real Chrome (Claude-in-Chrome architecture: `debugger` +
  `scripting` + `tabGroups`, LLM click-loop, background collapsed tab group) + a cloud executor
  (browser-use/Playwright) for when the computer is off. Same job queue, same confirm gate.
- Voice arm: SMS + real phone calls (Twilio), to the owner and (later, with policy) others.
- Temporal memory graph (better than RAG): entities, commitments with open/done lifecycle, timestamped
  edges, provenance quotes, graph-walk recall.
- One orchestrator responsible for everything. Cheap-model triage with escalation, caching, verification.
- Future: offline recording + delayed transfer, haptics.

### Architecture (data flow)

```
pendant firmware (XIAO nRF52840 Sense, Opus 16 kHz mono)
   → BLE (custom service 19B10000-E8F2-537E-4F6C-D104768A1214)
   → iOS app (PendantManager.swift; state restoration; auto-reconnect)
   → transcription (LocalTranscriber = Apple on-device SFSpeechRecognizer, or Deepgram cloud)
   → Anticipy orchestrator (brain/anticipy_core.py, class Anticipy)
        ├─ Memory graph  (brain/memory.py — SQLite episodes/nodes/edges)
        ├─ LLM triage    (brain/llm.py + brain/orchestrator.py Brain.triage → OpenRouter)
        ├─ Voice arm     (brain/voice_arm.py — Twilio SMS + calls; text-before-browser)
        └─ Job queue     (PocketBase `jobs` collection; awaiting_confirm gate)
   → Chrome extension (extension/ — MV3, chrome.debugger LLM click-loop, owner-scoped claim,
                        heartbeat, pair code)  OR  cloud executor (agent/browser_agent.py, browser-use)
   → results PATCHed back → app feed + Anticipy closes memory loop (review_loops → memory.resolve)
```

BLE UUIDs (identical in firmware and app — do not change one without the other):
- Service `19B10000-E8F2-537E-4F6C-D104768A1214`, audio char `...0001...` (notify; byte[2]=intra-frame
  counter, payload from byte 3; new frame when counter==0), codec char `...0002...`,
  Battery Service `180F` / level `2A19` (voltage-derived, EMA-smoothed).

### Pairing model (all proven live)
- Pendant↔app: pendant row in `pendants` with `pair_code`; app claims → `owner`.
- App↔browser: extension registers in `agents` with a random 6-digit `pair_code` shown in its popup;
  user types it in the app (onboarding step 4 or Settings); app PATCHes `owner`+`paired`. From then on
  the extension only claims jobs with its owner (or legacy unowned), heartbeats `last_seen` every 10 s
  (app shows "Agent live · seen 4s ago"), subscribes to job creations over SSE (~0 s pickup, 5 s poll
  alarm as safety net), stamps claims (`claimed_by`/`claimed_at`), and requeues any `running` job whose
  claim is older than 2 min (dead-Chrome recovery). Proof: `proof/test_pairing_live.py` — 6/6 passed.

---

## 2. THE OWNER'S REQUIREMENTS, VERBATIM (this is the spec)

- "do it all end to end." / "I need you to finish the job here." / "Just get it all done."
- "The biggest thing is research and research the hell out of everything."
- "Make it stupidly easy for me to do it and handle this." / "I'm a first-timer, but it better be literally two-year-old-proof."
- "Please do what is hardest, but do it the best way." / "I need perfection."
- "What's your name? She'd say your name. She'd be like, 'How goes it today? I overheard this, this, and this. I'm going to handle this.'"
- "The big picture is the proactive engine and system … to memory and actually good memory. Not just a JSON file, but some kind of linear graph better than a RAG."
- "Plus: The action arm — The voice arm, where it can text and call you and others — The orchestration model: the single guy who's responsible for everything — The plumbing — The onboarding — And so on and so forth. Build it all 1 billion percent, prove it all to me."
- "It should be called Anticipy" (she was briefly "Annie" — fully renamed).
- "Hey, would you use the browser before I'm texting you just to confirm a couple details?" → text-before-browse behavior.
- "I'm not ready to flash the firmware because the software better be good … It better be 1 trillion percent before even thinking about firmware."
- "All of this only works if the whole flow is there" + his checklist: proactive system in app, in-app messaging surface, browser-agent prep visible in app, extension auto-update, GUI onboarding, understandable state language ("I'm handling something", "to-do"), real anticipy.ai brand/logo/colors, stable BLE auto-reconnect.
- "prove that I can fill forms and actually navigate not open sites" — proven (SauceDemo full checkout, recorded).
- "and it works in the background of the users real chrome like in the background in a tab group" — implemented (collapsed yellow "Anticipy" tab group, active:false tabs).
- "Can we please do web searches, not a browser? For research at least" — design decision: search API for research, browser only for actions. NOT yet implemented (§10 gap G7).
- Cost control: he stopped a big LLM test run because "it's costing way too much money" — use cheap models for triage, cache, escalate only when needed.
- Latest instruction set (this handoff): produce this document, commit everything to git, deliver firmware + flash walkthrough, optimize handoff for Claude working locally on his Mac. "Context is mostly important. Biggest priorities context."

---

## 3. REPOSITORY MAP (every file that matters)

```
anticipy_app/
├── HANDOFF.md                  ← this file
├── PROOF_REPORT.md             ← earlier consolidated proof report
├── README.md
├── brain/                      ← the mind (Python 3, stdlib + requests only)
│   ├── anticipy_core.py        ← THE orchestrator. class Anticipy. NAME="Anticipy".
│   │                              hear(line) → memory.ingest → _decide (LLM triage w/ memory
│   │                              context, else deterministic commitment fallback) → _queue_job
│   │                              (status awaiting_confirm if hold OR goal in IRREVERSIBLE,
│   │                              stamped with owner_id) → notify_owner SMS ("Reply YES…").
│   │                              briefing() → first-person greeting. review_loops() closes
│   │                              loops + memory.resolve when jobs finish.
│   ├── memory.py               ← temporal knowledge graph on SQLite. Tables episodes/nodes/edges.
│   │                              Node types person/place/thing/topic/commitment (status
│   │                              open/done/cancelled). Edges said_to/committed_to/about/at/involves,
│   │                              timestamped, episode provenance. ingest() (LLM extractor or
│   │                              regex fallback _COMMIT_RE), recall() = 2-hop graph walk newest-first
│   │                              with original quotes, open_loops(), resolve(), briefing_facts().
│   ├── orchestrator.py         ← Brain.triage(line) → Decision{decision: ignore|ask|act, goal,
│   │                              needs_confirmation, reason}; also extraction prompts.
│   ├── llm.py                  ← OpenRouter client. Reads OPENROUTER_API_KEY from env/.env.
│   ├── voice_arm.py            ← Twilio. text(to, body), call(to, say) w/ inline TwiML <Say>.
│   │                              Creds from env (TWILIO_ACCOUNT_SID/TWILIO_AUTH_TOKEN/TWILIO_FROM).
│   └── __init__.py
├── backend/
│   ├── pocketbase (binary, v0.30.4) + pb_data/ (untracked)
│   ├── pb_migrations/1700000000_anticipy.js   ← pendants + events collections
│   ├── pb_migrations/1700000001_jobs.js       ← jobs (goal, params JSON, status, result, device_id)
│   ├── pb_migrations/1700000002_agents.js     ← agents (agent_id, pair_code, owner, paired,
│   │                                             last_seen, browser) + jobs.owner/claimed_by/claimed_at
│   └── sms_server.py           ← Twilio inbound webhook: signature-validated; "YES" reply flips the
│                                  oldest awaiting_confirm job → queued. Run behind a public HTTPS URL,
│                                  set as the number's SMS webhook.
├── extension/                  ← the action arm, Claude-in-Chrome grade. MV3.
│   ├── manifest.json           ← permissions: debugger, scripting, tabs, tabGroups, alarms,
│   │                              notifications, storage. Service worker background.js (module).
│   ├── background.js           ← registration+pair code, 10 s heartbeat, SSE realtime, 5 s poll alarm,
│   │                              owner-scoped claim, claim stamping, 2-min stale-job requeue,
│   │                              ACTIONS templates (gmail/calendar prefill, research, form demo),
│   │                              agent_goal → runAgentGoal LLM loop. BASE = http://127.0.0.1:8090.
│   ├── agent_loop.js           ← the autonomous loop: page_map → LLM chooses action → trusted
│   │                              execution via chrome.debugger (Input.dispatchMouseEvent /
│   │                              Input.insertText). Background collapsed "Anticipy" tab group.
│   │                              Login/CAPTCHA/irreversible → needs_user → awaiting_confirm.
│   ├── page_map.js             ← DOM walker: indexes interactive elements; REDACTS password/OTP/
│   │                              credit-card fields before anything reaches the model.
│   ├── popup.html/js           ← status dot, PAIR CODE display, OpenRouter key entry.
│   └── onboarding.html/js      ← branded guided setup (opens on install), pair code display,
│                                  honest "unpacked builds don't auto-update" note.
├── agent/browser_agent.py      ← cloud executor: browser-use + Playwright Chromium. Same job model.
├── app/ios/                    ← the iPhone app (SwiftUI, iOS 16+)
│   ├── project.yml             ← XcodeGen spec. bundleIdPrefix ai.anticipy. MARKETING_VERSION 0.2.0,
│   │                              CURRENT_PROJECT_VERSION 5 (== TestFlight build 5). Info.plist
│   │                              generated: icon, BLE/mic/speech usage strings, bluetooth-central +
│   │                              audio background modes, iPad orientations (all 4 — App Store requires).
│   ├── build_on_mac.sh
│   └── Anticipy/
│       ├── AnticipyApp.swift   ← @main + AnticipySession: 3 s polling, ownerID (UUID in AppStorage),
│       │                          agent heartbeat health (agentLastSeenSeconds, online <30 s),
│       │                          pairAgent(code), confirm/decline (job status PATCH), parsePBDate.
│       ├── Theme.swift         ← REAL anticipy.ai design system: ink #0C0C0C, ivory #F5F0EB,
│       │                          champagne #C8A97E, sand/gray/surface/card/stroke; serif display;
│       │                          LogoMark = pill outline + champagne dot (official SVG geometry).
│       ├── BLE/PendantManager.swift ← CoreBluetooth w/ state restoration key, willRestoreState,
│       │                          saved-peripheral retrieve (no scanning on reconnect), auto-reconnect
│       │                          forever (survives app kill/out-of-range/power cycle), manual-disconnect
│       │                          suppression, RSSI keep-alive, battery char. Omi-derived patterns.
│       ├── Audio/LocalTranscriber.swift  ← on-device SFSpeechRecognizer path
│       ├── Audio/TranscriberClient.swift ← Deepgram cloud path (key needed at runtime)
│       ├── Backend/AnticipyBackend.swift ← PocketBase client: pair (pendant), pairAgent (browser),
│       │                          fetchAgent (heartbeat), queueJob, fetchJobs, setJobStatus, isReachable
│       ├── Brain/BrainClient.swift
│       └── Views/ ContentView (status pills incl. "Agent live · Ns", Anticipy briefing card,
│                  proactive feed: Needs your OK / Handling / Heard / Done, in-app Send it / Not now),
│                  OnboardingView (5 steps: welcome → how it works → pair pendant → browser agent
│                  w/ 6-digit code entry → local/cloud choice), SettingsView (pendant, engine,
│                  proactivity, browser agent pairing + health, backend URL).
├── firmware/
│   ├── anticipy.uf2            ← drag-and-drop image for the XIAO's UF2 bootloader (USE THIS — §9)
│   ├── anticipy.hex            ← same build, hex (for J-Link/pyocd routes)
│   └── anticipy_dfu.zip        ← same build, Nordic DFU package (for OTA later)
│       Built from Omi-derived Zephyr firmware: PDM mic → Opus 16 kHz mono → BLE notify on the
│       service above; battery service; streams whenever connected; no-SD build config.
├── proof/                      ← every test + evidence. Run these, don't trust prose.
│   ├── test_memory.py (4/4), test_anticipy.py (4/4), test_anticipy_live.py (live spine vs real PB),
│   ├── test_pairing_live.py (6/6 — pairing/heartbeat/owner-scope/dead-agent requeue),
│   ├── test_backend.py, test_brain.py, test_extension.py, test_full_chain.py, test_end_to_end.py,
│   ├── test_scenarios.py, run_e2e_scenarios.py (10-scenario hands-off harness — run was cut for cost),
│   ├── *-report.md (agent-v2, anticipy-core, ios-build, navigation, scenario, test),
│   └── pendant_audio.wav, deepgram_transcript.txt, local_transcript.txt, screenshots.
├── research/browser_agent_mechanics.md ← deep dive: how Claude-in-Chrome (unpacked 1.0.81),
│   Codex for Chrome (1.2.27221), ChatGPT Agent/Atlas, Kimi, Comet, browser-use actually work,
│   and the mapping to Anticipy. Read before touching the extension.
└── website/ + research/site/   ← anticipy.ai assets: logo SVG, brand colors, extension zip.
```

---

## 4. WHAT IS PROVEN vs NOT (be honest with Omar — he checks)

PROVEN (real runs, evidence in proof/):
- Memory graph: unit tests 4/4. Orchestrator: 4/4. Live spine vs real PocketBase (hear → job
  awaiting_confirm → in-app YES → done → loop closed + memory resolved).
- Pairing spine: 6/6 live (register, pair by code, wrong-code reject, heartbeat freshness,
  owner-scoped claim, dead-agent requeue).
- Twilio: OUTBOUND SMS delivered to +1 604 724 5161; real voice call completed (13 s). Account
  "Anticipy", number +1 619 658 4447. Inbound webhook code exists (sms_server.py) and worked
  historically via a temp tunnel; NOT re-proven on a permanent host.
- Extension: loaded in the (previous agent's) Chrome; chrome.debugger click-loop completed real
  multi-page tasks (login → cart → checkout → confirm, recorded); "started debugging" banner = real CDP.
- iOS: compiles clean (Xcode 26.6), simulator run + screenshots; TestFlight build 5 (0.2.0) uploaded
  and processed VALID under ai.anticipy.app; Omar invited as internal tester.
- Firmware: builds; pendant audio was captured and transcribed correctly in earlier phases
  (proof/pendant_audio.wav + transcripts).

NOT PROVEN (the gap — do these):
- Live LLM triage/extraction/briefing at scale (a 10-scenario hands-off run was started, then
  stopped by Omar for cost; harness: proof/run_e2e_scenarios.py).
- App on Omar's PHYSICAL iPhone (TestFlight install, onboarding, BLE permission).
- Physical BLE + real pendant audio into the latest app; on-device local + cloud transcription.
- Extension in OMAR'S Chrome (only the agent's Chrome so far).
- Full loop phone → backend → extension → confirm → done on real hardware.
- Firmware flashing (deliberately deferred by Omar — software first).
- Production: HTTPS backend hosting, tenant isolation/rules (PocketBase rules are wide open — dev
  only), atomic job claim, rate limits, Chrome Web Store distribution/auto-update, Twilio webhook
  on a permanent URL, contact-authorization policy for calling/texting third parties, key rotation.

---

## 5. CREDENTIALS & SECRETS — where they live (NO values in this repo, ever)

- **OpenRouter key**: was saved in the previous agent's Chrome extension storage and its box's
  `anticipy_app/.env` (that box is gone for you). Omar has the key; ask him to paste it into the
  extension popup ("Save key") and export OPENROUTER_API_KEY for the brain. It was exposed in an
  old chat → should be ROTATED at https://openrouter.ai/settings/keys.
- **Twilio**: account "Anticipy", from-number +1 619 658 4447. SID/token were provided by Omar in
  chat previously (exposed → rotate at console.twilio.com). Set TWILIO_ACCOUNT_SID,
  TWILIO_AUTH_TOKEN, TWILIO_FROM in the environment for voice_arm.py.
- **App Store Connect API key** (this Mac): Key ID `JM8NMC2CQ4`, Issuer
  `f7537a6f-0219-4b3f-80cf-20c2e7d7d548`, .p8 at `~/private_keys/` (or wherever
  `AuthKey_JM8NMC2CQ4.p8` sits — `find ~ -name 'AuthKey_*.p8'`). Team ID `49T86P9XGW`.
- **Signing (this Mac)**: cert "iPhone Distribution: Omar Ebrahim (49T86P9XGW)" in the login
  keychain; profile "Anticipy AppStore Devin" installed; `~/ExportOptions.plist` ready.
  Keychain may need `security unlock-keychain` (ask Omar for his login password — the previous
  one was exposed in chat; he was told to change it).
- **Deepgram** (cloud transcription): key needed at app runtime; Omar has one from earlier phases.
- Never commit .env, .p8, tokens. `.gitignore` already excludes .env.

## 6. RUNNING THE SYSTEM LOCALLY (Mac)

```bash
# 1. Backend
cd backend && ./pocketbase serve --http 127.0.0.1:8090   # migrations auto-apply
curl http://127.0.0.1:8090/api/health

# 2. Brain tests (no LLM needed — deterministic fallbacks)
python3 proof/test_memory.py && python3 proof/test_anticipy.py
python3 proof/test_anticipy_live.py && python3 proof/test_pairing_live.py

# 3. Extension: chrome://extensions → Developer mode → Load unpacked → extension/
#    Popup shows the 6-digit pair code; save the OpenRouter key in the popup.

# 4. iOS: cd app/ios && xcodegen generate (install: brew install xcodegen)
xcodebuild -project Anticipy.xcodeproj -scheme Anticipy \
  -destination "platform=iOS Simulator,name=iPhone 17 Pro" build
# Device/TestFlight: archive with PRODUCT_BUNDLE_IDENTIFIER=ai.anticipy.app, manual signing
# (cert/profile above), export w/ ~/ExportOptions.plist, upload:
xcrun altool --upload-app -f export/Anticipy.ipa -t ios \
  --apiKey JM8NMC2CQ4 --apiIssuer f7537a6f-0219-4b3f-80cf-20c2e7d7d548
# REMEMBER: bump CURRENT_PROJECT_VERSION + CFBundleVersion in project.yml every upload.

# 5. Voice arm (env vars set):
python3 -c "from brain.voice_arm import VoiceArm; VoiceArm().text('+16047245161','Hi, it\'s Anticipy.')"

# 6. Orchestrator with everything on:
python3 - <<'EOF'
from brain.llm import LLM
from brain.anticipy_core import Anticipy
from brain.voice_arm import VoiceArm
a = Anticipy(llm=LLM(), voice=VoiceArm(), owner_phone="+16047245161", owner_id="<app ownerID>")
print(a.hear("I'll send Sarah the pitch deck right after this call."))
print(a.briefing())
EOF
```

## 7. GETTING THE EXTENSION INTO OMAR'S REAL CHROME

1. `chrome://extensions` → Developer mode ON → Load unpacked → select `extension/`.
2. A branded setup tab opens; popup shows the pair code; enter it in the iPhone app.
3. The "Anticipy started debugging this browser" banner is EXPECTED (CDP via chrome.debugger —
   same as Claude-in-Chrome). Don't dismiss jobs because of it.
4. Unpacked = no auto-update. Production requires Chrome Web Store (one-time $5 dev fee,
   review ~days). That is gap G6.

## 8. iOS / TESTFLIGHT STATE

- App record: "Anticipy", bundle `ai.anticipy.app`, App Store Connect under Omar's account.
- Uploaded: build 4 (0.2.0) and build 5 (0.2.0 + pairing UI) — both processed VALID.
- Internal-tester group exists; okebrahim@icloud.com invited. He installs via TestFlight app.
- Known gotchas already solved (don't re-hit them): app icon required (asset catalog +
  CFBundleIconName), iPad needs all 4 orientations, `.topBarLeading` breaks iOS 16
  (use `.navigationBarLeading`), each upload needs a unique CFBundleVersion.

## 9. FIRMWARE + FLASH WALKTHROUGH (two-year-old-proof)

Files: `firmware/anticipy.uf2` (use this one), `anticipy.hex`, `anticipy_dfu.zip` (OTA later).
Only flash AFTER the app is proven on the physical iPhone (Omar's explicit ordering).

1. Plug the pendant (XIAO nRF52840 Sense) into the Mac with a USB-C DATA cable.
2. Double-press the tiny RESET button (left of USB-C) quickly, like a double-click.
3. A drive named **XIAO-SENSE** appears in Finder (like a USB stick). If not: try again faster/slower,
   or a different cable (charge-only cables are the #1 failure).
4. Drag `anticipy.uf2` onto XIAO-SENSE. It copies, the drive ejects itself, the board reboots. Done.
5. Verify: iPhone → Anticipy app → onboarding "Pair pendant" (or nRF Connect app shows "Anticipy"
   advertising the 19B10000-… service). Audio streams whenever BLE is connected (no power switch
   on this board — battery % is voltage-derived).
6. Recovery: it is nearly unbrickable — double-tap RESET always returns the UF2 drive.

## 10. GAP MAP — WHERE WE ARE → WHERE WE NEED TO BE (ordered)

- **G1 Physical proof loop**: TestFlight install on Omar's iPhone → onboarding → BLE pair →
  real pendant audio → local AND cloud transcription → transcript → job → extension in HIS Chrome →
  in-app + SMS confirm → done back in app. Nothing else matters until this loop closes.
- **G2 Live LLM validation at controlled cost**: run proof/run_e2e_scenarios.py (10 scenarios,
  hands-off) with a CHEAP triage model; only the click-loop needs a stronger model. Omar stopped
  the last run for cost. A partial live run (6/10, deepseek-v3.2, recorded) found and FIXED two
  real bugs — see §10.1. Scenarios S7–S10 plus re-runs of S3/S4/S6 remain.

### 10.1 Live-run findings (2026-07-21 hands-off run — read before re-running)
- S1 small talk → correctly ignored. S5 memory recall → correct chain
  ("send the pitch deck —committed_to→ Sarah" with the original quote). PASSED.
- BUG 1 (FIXED): with live LLM triage, goal strings are free-form ("send pitch deck to Sarah")
  and never matched the hardcoded IRREVERSIBLE set → the confirm gate never engaged. Fix:
  `is_consequential()` regex policy layer in anticipy_core.py — send/book/buy/sign-up/etc. goals
  are ALWAYS held at awaiting_confirm regardless of what the model said. Unit-tested.
- BUG 2 (FIXED): jobs running >2 min were eaten by the extension's stale-requeue sweep because
  `claimed_at` was never refreshed mid-run → infinite requeue/respawn loop, ~14 leaked tab groups,
  runaway LLM spend (the actual cause of the cost blow-up). Fix: `activeJobs` set in background.js;
  heartbeat refreshes claims for active jobs; sweep skips this worker's own jobs.
- S2/S6 triage judgment: model chose `ask` for sushi research (over-cautious) and `act` for the
  ambiguous anniversary booking (under-cautious). The policy layer now catches S6's booking, but
  triage prompt tuning in orchestrator.py is still worthwhile.
- Agent loop already caps at maxSteps=20 (agent_loop.js); consider also a wall-clock cap.
- Recording of the run (annotated): was at /home/ubuntu/screencasts/rec-164992f4…-edited.mp4 on the
  old box; per-scenario detail in the notes above.
- **G3 Production backend**: host PocketBase on HTTPS (Fly.io/Railway/VPS), lock collection rules
  to owners, atomic job claim (PB transaction or claim-token), rate limits, backups. Point app
  `backendURL`, extension `BASE`, and Twilio webhook at it.
- **G4 Inbound SMS on permanent URL**: deploy sms_server.py behind the production host; re-prove
  reply-YES-releases-job.
- **G5 Voice/contact policy**: allowlist of contacts Anticipy may text/call; per-contact consent;
  never call arbitrary numbers.
- **G6 Chrome Web Store**: package extension, submit, get auto-updates. Until then: unpacked.
- **G7 Search-API-for-research**: research jobs should hit a web-search API (cheaper/faster),
  browser only for actions. Design agreed with Omar, not built.
- **G8 Cost engine**: model routing (cheap triage → escalate), caching, recorded-workflow replay
  so repeated tasks cost ~0 LLM calls.
- **G9 Security hardening**: prompt-injection defenses in agent_loop (instructions from page text
  must never override policy), banking-domain blocklist, per-site permission grants, key rotation
  (OpenRouter, Twilio, Mac password — all previously exposed in chat).
- **G10 Hardware productization**: enclosure CAD, magnetic charging, chain, 3D prints, then CM
  for ~100 units. Untouched this phase.

## 11. NON-NEGOTIABLE RULES (learned the hard way)

- Never let the model bypass the confirm gate — it lives in job STATUS, outside the model.
- page_map REDACTS password/OTP/payment fields — keep it that way; never fill them.
- No CAPTCHA/bot-detection bypass. Login walls → needs_user, always.
- Don't claim "done" from source. Label evidence: written / unit-tested / live-backend /
  simulator / physical-device / TestFlight / production.
- When Omar gives you 10 things, do all 10 — track them in a visible list.
- Research first, with primary sources. He will ask where a claim came from.
- Talk like Anticipy where it's user-facing: warm, brief, first-person, no invented facts.
