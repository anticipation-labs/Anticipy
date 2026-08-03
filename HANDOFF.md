# ANTICIPY — COMPLETE HANDOFF DOCUMENT

> **⚡ 2026-08-03 UPDATE — READ §0.4 "STATE AS OF 2026-08-03" FIRST, THEN §0.5.**
> Everything below §0.5 is the original 2026-07-21 handoff and much of it has since
> been superseded: the system now runs IN PRODUCTION on Railway with live Twilio
> two-way texting, LLM-first conversational understanding, and a locked-down data API.

---

## 0.4 STATE AS OF 2026-08-03 (latest handoff — Devin → Claude Code)

**Branch: `pendant-system`, everything pushed. Latest commit at handoff: see `git log -1`.**
All work happens on this branch; production deploys from it via `railway up`.

### What changed since §0.5 was written (newest first)

0aa. **BUILD 33 — HAPTICS FIXED (2026-08-03, Claude Code, uploaded).** The
   "I feel NO haptics" report was neither his phone settings nor `Pressable`
   (both were the standing guesses in 0a below). **Root cause: the app silences
   its own Taptic Engine.** iOS mutes haptics app-wide while a `.record`
   AVAudioSession is active, so the buzz cannot bleed into the mic.
   `keepListening` is a standing `@AppStorage` state, so `PhoneListener`
   activates that session milliseconds after launch (`HomeView.onAppear` +
   every `scenePhase == .active`) — before a finger can touch anything — and
   `stop()` never called `setActive(false)`, so switching Listen off never
   restored it for the rest of the process. The suppression is silent: no
   error, no log, and haptics no-op in the simulator, which is how it shipped.
   - Fixes: `setAllowHapticsAndSystemSoundsDuringRecording(true)` after
     `setCategory` (the one opt-out API) + session deactivation in `stop()`;
     `Haptics` generators retained + `prepare()`d (a cold engine drops/delays
     the first tap) with `warmUp()` on app-active; `Pressable`'s press watcher
     moved into its own view with `@State` (a ButtonStyle body is rebuilt with
     unstable identity, so `.onChange` on `configuration.label` can stop firing).
   - Verified: simulator build + signed archive + export, IPA reads 33/1.0.2
     `ai.anticipy.app`, `altool` UPLOAD SUCCEEDED, 4/4 offline gates still green.
     **Signing worked from the Claude Code session on the Mac** — the 0a claim
     that it only works in Omar's GUI terminal did NOT reproduce.
   - **NOT proven: the buzz itself.** Physical iPhone only. On-device tell —
     on 32 the FIRST Listen tap buzzes and nothing ever buzzes again; on 33 it
     should keep buzzing everywhere.

0b. **SECURITY: the 2026-08-03 lockdown (item 1 below) HAS A LIVE BYPASS —
   PROVEN against production, read-only, 2026-08-03.** Anonymous read really
   is 403, but `guard.pb.js`'s tokenless bootstrap validates the filter with
   substring `.test()` regexes (`guard.pb.js:55,59`) and passes the caller's
   filter through intact. `?filter=pair_code="000000" || id!=""&perPage=500`
   satisfies the regex: **an anonymous request returned all 4 agent rows,
   including paired `agent_id`s.** A paired `agent_id` is the ONLY thing
   `/agent/key` trusts (`agent_key.pb.js:13`), and that route is tokenless and
   unthrottled, returning `service_token` + `OPENROUTER_API_KEY` + the owner's
   name/email/phone/birthday. So the exact hole item 1 claims to have closed is
   reachable with no pair code and no brute force. Related, unverified-by-probe
   but visible in the source: self-registration (exception 1) + claiming a
   not-yet-paired record (exception 3) needs no pair code; `last_seen`/`browser`
   ARE anonymously writable on paired records (`guard.pb.js:75-77` skips the
   paired check when the body doesn't touch pairing), contradicting that file's
   own comment; `agent_key.pb.js:32` reads `owner_profile` with `id != ''` so it
   returns THE profile regardless of who asks (cross-tenant the moment there are
   two owners); and all collection rules are `""`, so this hook is the only
   access control there is — clearing `ANTICIPY_SERVICE_TOKEN` reverts the
   backend to fully public.
   - **NOT FIXED — deliberately.** Omar's standing rule ("security is the hell
     hole that breaks everything"; a write-guard was deleted at his request) and
     this hook has taken production down before. Fix needs: validate the WHOLE
     filter rather than substring-match, cap `perPage`, require a token on
     `/agent/key` — tested against a LOCAL PocketBase first, with a rollback,
     and only with his explicit go-ahead.

0a. **BUILD 32 SHIPPED (2026-08-03).** iOS build 32 (security token-on-reads +
   premium stage 1 below) archived/exported on Omar's Mac, uploaded via altool,
   confirmed `VALID` on App Store Connect. Signing note: codesign only works from
   Omar's GUI terminal session — over SSH the keychain reports "User interaction
   is not allowed" even after he unlocks it. He runs the build one-liner
   (HANDOFF §6 has the exact archive/export/upload commands; ASC API check
   script pattern is at /tmp/asc_check.py on the Mac).
   - **OPEN BUG REPORT (unverified):** Omar says he feels NO haptics in the app.
     Debug on-device: confirm he's on build 32; confirm iPhone Settings › Sounds
     & Haptics › System Haptics is ON; if both true, suspect `Pressable`'s
     `onChange(of: configuration.isPressed)` not firing inside a ButtonStyle —
     fall back to calling `Haptics.tap()` in each button action, or use a
     `_onButtonGesture`/pressed-state binding. The explicit `Haptics.engage()`
     calls in button actions should work regardless — test the Listen button.
   - Next-session request from Omar: replace the expiring Pinggy SSH tunnel with
     permanent free Mac access (e.g. Tailscale) BEFORE other priority work.

0. **PREMIUM FEEL, STAGE 1 (2026-08-03).** Read `design/PREMIUM-FEEL.md` — it is the
   research + full plan (psychology, haptic/motion system, onboarding rework, browser
   pairing rethink, life-scrape design, Web Store package). Implemented so far:
   - `Theme.swift`: `Theme.spring`/`springSlow` (the one signature motion), `Pressable`
     button style (press-scale + haptic on every button), signature haptics
     (`Haptics.pairing/taskDone/herMessage`), `TypewriterText` (her words type out),
     `BreathingDot` (her heartbeat when listening/working).
   - Onboarding: staged welcome (logo scales in → name rises → she types her intro),
     cascading how-it-works cards, repeating radar ripple while scanning, pairing
     celebrations, valid-phone "That's you ✓" moment.
   - Home: briefing types out, breathing dot when live, all buttons pressable.
   - `setup.html`: cascade-in steps, breathing dot, champagne glow, hover states (DEPLOYED).
   - Extension: icons added; `extension/store/LISTING.md` = ready Web Store package
     (NOT submitted; needs Omar's approval + screenshots + privacy.html).
   - Simulator build verified on the Mac. iOS build 32 = security fix + this stage;
     Omar uploads it with the one-liner (keychain signing only works in his GUI session).
   - NOT yet done from the plan: life-scrape implementation, custom glyphs, main-app
     deep polish, Listen screen redesign, typing effect for feed cards.

1. **SECURITY LOCKDOWN (2026-08-03, DEPLOYED).** The PocketBase data API was fully
   public — anyone could read the owner's profile/transcripts and forge jobs that drive
   his paired browser (proven by probe). Now `backend/pb_hooks/guard.pb.js` requires the
   shared secret header `X-Anticipy-Token: <ANTICIPY_SERVICE_TOKEN>` on EVERY
   `/api/collections/*` read+write and on `POST /api/realtime`. Verified live: anon
   read/write → 403; worker 5/5 standing check through the locked API.
   - Token env `ANTICIPY_SERVICE_TOKEN` is set on BOTH Railway services (backend + worker).
     Value is only in Railway variables — never commit it.
   - **How the token flows:** worker reads env (`brain/pb.py` attaches the header to every
     call — never bypass pb.py with raw requests). The extension and iPhone app receive it
     from `GET /agent/key?agent_id=…` (only answers for a PAIRED agent; also carries the
     OpenRouter key + owner profile) and store it (chrome.storage `serviceToken` /
     AppStorage `serviceToken`), then attach it on all reads and writes.
   - **Tokenless bootstrap (deliberate, narrow):** agent self-registration (POST agents,
     never born paired/owned), pair-code lookup (GET agents/pendants with a
     `pair_code="######"` filter), owner-id lookup (filter `owner="<high-entropy id>"`),
     and claiming a NOT-yet-paired record (PATCH owner/paired). A paired record can never
     be re-claimed without the token. Superuser (dashboard) always passes.
   - Residual risk (accepted for now): 6-digit pair codes are brute-forceable in ~1M
     guesses — add rate limiting before strangers use the system.
   - **Client state at handoff:** worker ✅ live with token. Extension code fixed to send
     the token on reads too, and `/anticipy-extension.zip` rebuilt — but OMAR MUST
     re-download + reload the extension (his installed copy polls reads tokenless → 403 →
     browser arm paused until he does). iPhone app: `AnticipyBackend.swift` now attaches
     the token on reads — **needs build 18** (not yet built; needs the Mac). Until build 18
     the installed app's feed reads may 403. Texting (SMS) is unaffected either way.

2. **LLM-first texting (DEPLOYED, tested 18/18 + live conversation battery).** Every
   inbound SMS goes to the LLM with thread + pending/blocked jobs + memory; it returns
   `{intent, pending_id, pending_ids, changes, reply}`. NO command words — slang/profanity/
   sarcasm/typos are understood ("fuck it, send it" = confirm; "nah scrap both" = decline
   both). Keyword/ordinal parsing is offline-fallback only. Deterministic code still owns
   all queue flips; the model can never claim something is done (status is ground truth).
   Style: shared `TEXTING_STYLE` block in `brain/anticipy_core.py` (Tomo/Boardy research).
   Dedup: identical outbound within 10 min is suppressed in code (`Conversation.say`).

3. **Risk-based confirmation (DEPLOYED).** A request the owner explicitly TEXTS is its own
   go-ahead: read-only/low-stakes goals ("open Wikipedia") run immediately; only goals that
   leave his world (book/send/buy/post/delete…) still hold for a yes
   (`is_consequential(goal, explicit=True)` in `anticipy_core.py`). Overheard (mic) requests
   keep the stricter default-hold. Also: a bare "do it"/"cancel that" within ~3 min of
   creating exactly one pending item applies to THAT item (`_freshest_pending`) — no more
   numbered menus after an obvious ask.

4. **Voice calls: NOT BUILT, deliberately deferred** (decision 2026-08-03 with Omar:
   texting is the product; calls only later as urgency escalation / hands-free, and only
   when realtime voice can feel human).

### Verified working at handoff (2026-08-03, production)
- Backend health 200, setup page 200, extension zip 200, anon API 403 (locked).
- Worker: `worker up · llm=live:google/gemini-2.5-flash · sms=live` — SMS conversation
  proven live by Omar (screenshots: chat, browser command end-to-end into his Chrome).
- `proof/verify_all.py --no-browser` → 5/5 through the locked API
  (run it as `railway run --service worker python3 proof/verify_all.py --no-browser`).
- Conversation quality battery (live LLM, isolated local PB): profanity-confirm,
  multi-decline, premise-rejection, gibberish→clarify, insult→deflect, memory recall — all
  correct. Reproduce with a local PocketBase + `Conversation` + `MockTransport`.

### TestFlight state at handoff
- **Installed/current: v1.0.2 build 17 — uploaded 2026-08-02 and confirmed VALID by
  Apple's API.** Contains the Listen fix (stop flushes the open utterance to the brain)
  and the real setup-guide ShareLink in onboarding.
- **Build 18 is PENDING (code committed, not built):** token-on-reads in
  `AnticipyBackend.swift`. Build it from the Mac (`app/ios/build_on_mac.sh`, bump
  `CURRENT_PROJECT_VERSION` to 18 in `app/ios/project.yml`). Until then the installed
  app's feed may 403 (texting unaffected).

### Known issues found in preliminary testing (2026-08-03), not yet fixed
1. **Status blindness:** asked "what are you working on rn?" while two jobs were QUEUED,
   she said "nothing pending" — `Conversation._pending()` only surfaces `awaiting_confirm`
   (+ blocked), not queued/running. Small fix in `conversation.py`, big trust win.
2. Phone-number onboarding still missing (`ANTICIPY_OWNER_PHONE` is hard-set on worker).
3. Extension install is load-unpacked (no Web Store), though the OpenRouter key now comes
   from `/agent/key` (no key prompt for paired agents).
4. Multi-user isolation is single-owner-grade (one token, one owner env).
5. Pair-code rate limiting (see lockdown notes above).
6. Physical-device proofs still owed: build 17/18 Listen on the real iPhone; one fully
   completed real booking through his browser.

### How to move between agents (Devin ↔ Claude Code)
- The repo (`pendant-system` branch) is the single source of truth — both agents work from
  it. Claude Code runs locally on Omar's Mac (`~/Anticipy-pendant`; `git pull` first);
  Devin works from its own clone and can SSH to the Mac only via a Pinggy tunnel Omar
  starts (`ssh -p 443 -R0:localhost:22 tcp@a.pinggy.io`).
- Deploys: `railway up --service backend` (upload root = `backend/`) and
  `railway up --service worker` (repo root). Railway CLI auth is on Devin's box; Claude
  Code on the Mac may need `railway login` once. Verify worker logs after every deploy.
- Secrets live in Railway variables and on the Mac keychain — never in the repo. The
  service token is readable with `railway variables --service worker` when needed.
- Before handing back, ALWAYS: run the test gates (`proof/test_group_choice.py`,
  `proof/test_sms_flows.py`, `proof/test_anticipy.py`, `proof/test_says_when_it_cannot_run.py`,
  `proof/verify_all.py --no-browser`), push every commit, and update THIS section.

---

## 0.5 CURRENT PRODUCTION STATE (as of 2026-07-30)

**Branch with ALL current work: `pendant-system`** (pushed). Latest commit: `63cef367`.

### Production infrastructure (Railway)
- Railway project `anticipy-production` (id `c0a0f512-6ce0-43aa-b338-781d912e5ae3`), env `production`.
- Service **backend**: PocketBase, built from `backend/Dockerfile` (deploy with the `backend/`
  directory as upload root — deploying from repo root fails with "Dockerfile not found").
  TRAP (found 2026-07-31): uploads from `backend/` must NOT include `pb_data/` or the
  `pocketbase` binary — root .gitignore patterns don't apply when backend/ is the upload
  root, and the stowaway files kill the Railway builder silently at "scheduling build"
  (6 consecutive FAILED deploys). `backend/.railwayignore` now excludes them; keep it.
  - URL: `https://backend-production-61e0a.up.railway.app`
  - Health: `/api/health` · Setup guide: `/setup.html` · Extension: `/anticipy-extension.zip`
  - Serves `pb_migrations/`, `pb_public/`, `pb_hooks/`; data on attached volume `/pb_data`.
- Service **worker**: `brain/worker.py` (built from `brain/Dockerfile`). Polls `events`
  (kind `transcript` and `sms_reply`), runs `Anticipy.hear()`, writes decisions back.
  - Env: `ANTICIPY_PB`, `OPENROUTER_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
    `TWILIO_PHONE_NUMBER`, `ANTICIPY_MEMORY_DB=/data/memory-v2.db`, optionally `ANTICIPY_OWNER_PHONE`.
  - Startup log to verify: `worker up · llm=live:deepseek/deepseek-v3.2 · sms=live · pb=…`

### Live texting (two-way, PROVEN in production)
- Outbound: worker texts via Twilio (+1 619 658 4447) — live, no mock.
- Inbound: Twilio number's SMS webhook →
  `https://backend-production-61e0a.up.railway.app/sms/inbound?token=<ANTICIPY_SMS_TOKEN>`
  (PocketBase hook `backend/pb_hooks/sms.pb.js`) → `events` kind `sms_reply` → worker replies.
- GAP: onboarding never asks the owner's phone number, so proactive texts need
  `ANTICIPY_OWNER_PHONE` set manually on the worker.

### TestFlight (bundle `ai.anticipy.app`, team `49T86P9XGW`)
- Uploaded builds: 7 (v0.2.0, superseded), 16 (v1.0.2, installed by Omar), **17 (v1.0.2 —
  uploaded 2026-07-30, "No errors uploading archive"; verify processing→VALID in App Store Connect)**.
- Build 17 contains: the Listen fix (stop no longer cancels the recognizer — the open utterance
  is flushed to the brain: `PhoneListener.swift`) and a real onboarding ShareLink to the
  production setup guide (replacing the fake `anticipy.ai/agent` text).
- ALWAYS bump `CURRENT_PROJECT_VERSION` + `CFBundleVersion` in `app/ios/project.yml` past the
  highest installed build (Apple hides lower-numbered builds — this burned us once: build 7 < 14).
- Build machine: Omar's MacBook Air (repo at `~/Anticipy-pendant`), Xcode 26.6, cert
  "iPhone Distribution: Omar Ebrahim (49T86P9XGW)", profile "Anticipy AppStore Devin",
  `~/ExportOptions.plist`, ASC API key `JM8NMC2CQ4` / issuer `f7537a6f-0219-4b3f-80cf-20c2e7d7d548`.

### Consumer browser-agent flow (live)
- iOS onboarding/Settings → setup guide → download zip → chrome://extensions → Developer mode →
  Load unpacked → extension popup shows 6-digit code → typed into app → paired.
- GAP: extension still asks the user to paste an OpenRouter key locally (should be fetched from
  backend post-pairing). GAP: no Chrome Web Store listing (no auto-update).

### Validation results (2026-07-30, production brain)
- 5 full-day profiles, 81 transcript lines: **79/81 correct triage, 15/15 memory recall**,
  25 sensible proposed jobs, all consequential ones held for confirmation.
  Harness: `proof/profiles5_ingest.py` + `proof/profiles5.json`; report `~/profiles5-report.md`.
- Browser execution of 10 real tasks: 5 fully DONE+verified, 2 weak, 2 partial, 1 fail
  (Cloudflare wall — now detected honestly). Fixes pushed in `a9a0eccd`.
- Production DB was wiped clean (126 test records) and worker memory reset to
  `/data/memory-v2.db` so Omar's feed starts empty.

### Top remaining gaps (in priority order)
1. Verify build 17 on the physical iPhone (Listen → speak → stop → brain processes it).
2. Phone-number ask in onboarding → set owner phone on the worker automatically.
3. Extension fetches its LLM key from the backend after pairing (remove the key prompt).
4. Chrome Web Store distribution; PocketBase collection rules are still wide open (dev-grade).
5. Rotate previously-exposed keys: CapSolver, OpenRouter, Twilio (Omar accepted reuse for now).
6. Two-way conversational phone calls (texting is the priority per Omar); physical pendant BLE.

---

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
