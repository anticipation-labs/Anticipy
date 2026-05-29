# Anticipy North Star v2 (updated 2026-05-29 after a full day of building)

## What we are building

An AI pendant that hears every conversation you are in and silently completes whatever needs doing. Donna from Suits, for everyone. Works in any industry, any app the user can log into, with no per-app code.

The pendant always listens. **Wake-word is NOT the primary input.** A user who has to say "Hey Anticipy" before each request is a product failure. The pendant captures naturally, the engine decides what matters, the user finds out only when Anticipy fires.

## The shipping form factor

- **Today (Mac prototype):** Tauri menubar app + packaged Python sidecar engine on `127.0.0.1:8731` + bridge on `:7777` + the user's real Chrome on `:9222`. Engine code is the production code; ports unchanged to the pendant rig.
- **V2 (pendant + phone + mini-PC):** pendant captures audio, phone is edge brain (ASR + intent classification), mini-PC Raspberry-Pi-class runs Chrome and acts. Same engine code.

## Three concrete moments that must work

1. **Trivia in your ear.** Friend asks "wait, when did the Roman Empire fall?" 1.2 seconds later the user's earbud whispers "476 AD Western, 1453 Constantinople."
2. **Silent execute.** Lawyer at intake hears the client. By the time the lawyer walks back to her desk, the demand letter is drafted in her firm's case management system citing the relevant statute. She bills 0.3 hours of review, not 2.5 hours of grunt.
3. **"I just do."** Anyone who asks the user a question gets the answer or the action they wanted, before they finish asking. The user looks like Donna.

## Hard rules (no exceptions)

1. **Universal action agent.** No per-app code, no recipe registry. The agent looks at any web page (DOM accessibility tree + screenshot), decides next action via LLM + vision, executes via CDP, observes, loops. Same code path for Gmail, Salesforce, Notion, Quillow, Epic, Procore, custom CRMs, anything the user is logged into.
2. **No service APIs.** No Gmail API, no Slack API, no Salesforce API. Browser navigation of real UIs only. OpenRouter LLM brain calls are the only outbound.
3. **Pre-action confirm channel by urgency.** Phone call for critical + time-sensitive. SMS for critical + not time-sensitive. SMS + email for HIGH. Email or in-app for MEDIUM. Silent for LOW. Default deny on no reply.
4. **Persistent follow-through.** Tasks survive engine restarts, sleep across days/weeks, wake on schedule, retry with exponential backoff, escalate to user via SMS when stuck.
5. **Apple-quality polish on every surface.** Plain human English, no jargon, no debug strings. Smooth animations. Real-voice TTS. Permission explainers BEFORE the system dialog. No em-dashes anywhere.
6. **Local-first privacy moat.** Audio + dossier stay on the user's hardware. Only LLM brain calls + Twilio + Supabase auth go out. No service-side audio storage.
7. **Cost ceiling $200/user/year on 100k tasks.** That is $0.002 per task. DOM-first action, vision only on canvas apps. Aggressive prompt caching. DeepSeek V4 Flash for planner. Kimi K2.6 vision only when DOM is insufficient.
8. **Day-zero useful.** Cold-start inhales the user's real Gmail + Calendar + Drive via the user's logged-in Chrome in under 60 seconds. Real people in the dossier before the user finishes the welcome screen.
9. **Pendant is always-on capture.** No wake-word. No push-to-talk. The engine decides what matters; the user is never asked to invoke.
10. **Confirm + receipt for every external action.** Pre-action SMS confirm with YES/NO/EDIT, default to draft on no reply. Post-action receipt with verifiable identifier (Gmail Message-ID, calendar event link, etc).

## The 6 user-facing gates (mechanical 100% marker)

| Gate | Verify command | Pass criterion |
|---|---|---|
| **G1 install_under_5min** | `bash scripts/v7/stranger_flow.sh` exits 0 | wipe + cold-start + inject + act + verify Gmail draft in under 300 seconds |
| **G2 trivia_fires** | scripted phrase produces TTS within 2 seconds | trivia trigger + cache or fallback + audio plays + correct fact |
| **G3 silent_execute** | `python scripts/v7/z001_e2e_harness.py` exits 0 with verdict=PASS | spoken action becomes real Gmail draft via real Chrome |
| **G4 coldstart_fills_dossier** | active dossier has at least 10 people inhaled within 60 seconds | day-zero useful |
| **G5 packaged_binary_serves** | engine on 8731 is `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` | the DMG-shipped binary actually serves on a clean Mac |
| **G6 demo_rehearsed** | two consecutive dress-rehearsal PASS in last 4 hours | demo is not theoretical |

## What is shipped today (verified mechanically)

- Universal action agent: verified on Google Calendar with zero calendar-specific code
- Trivia fire: 11-22ms perceived latency, correct facts (Roman/Moon/Eiffel/Declaration tested live)
- Cold start: 24 real people inhaled from real Gmail in 44-91 seconds, real entities (Joe@PostHog, Zara Somani@OpenDoor Law, Therese@Klip, etc)
- Silent execute: Z-001 9/9 PASS, real Gmail draft in real Chrome
- Stranger flow: 7/7 hard steps PASS, ~136 seconds end-to-end
- CHECK 16 reliability: 28/30 (resolvable 20/20 perfect, ambiguous 8/10). Up from 17/30 baseline. Codex-class.
- Planner latency: 0.9-1.8s cached calls (90% prompt cache hit), down from 211s worst-case
- Tab hijack prevented: ownership map ensures agent never touches user's tabs
- Hardcoded planner regex (V1+V2+V3) replaced with one unified LLM intent extractor
- Handoff ghost fixed: real `engine/app/anticipy/handoff.py` module ships, traceback no longer swallowed
- SMS pre-confirm before irreversible action: YES/NO/EDIT reply, 5-min TTL, default to draft on no reply
- Post-action receipt: proven by real "Anticipy: Anticipy draft" landing in `omarkebrahim@gmail.com` Drafts
- Persistent task queue with wake-up scheduling (in DEV-FINAL worktree, cross-repo deploy pending)
- Engine stability: packaged Anticipy.app sidecar wins port 8731 on clean Mac
- Tab-ownership safety on bridge
- Dress rehearsal harness with append-only log

## What is missing (the remaining real work)

Ordered by impact on the North Star, primary work first:

### P0 — block the "production-ready" claim

1. **Cross-repo deploy of persistent task queue.** Commit 666fd4b2 is in DEV-FINAL worktree. Until it lands in V7 main, multi-day tasks die on engine restart.
2. **Inbound SMS webhook on the website.** Twilio needs a stable HTTPS URL to POST replies to. Without this, the SMS pre-confirm only sends; the YES/NO/EDIT reply path is incomplete in production.
3. **Audit-trail screenshots in receipts.** Receipts say "I sent X" but no proof. Need: Gmail Message-ID + canonical link, calendar event link, screenshot of the resulting page. So the user can verify in one click.
4. **Failure-recovery transparency.** When Gmail logs out, MFA challenges, or CAPTCHA blocks the agent, today the engine returns silent error. Need: SMS user "Couldn't finish X because Y, here is the link to fix it, I will retry once you do." + persistent queue keeps task alive.

### P1 — needed for real-user reliability

5. **Apple-quality polish pass on the Tauri popover.** Typography, animations, plain-English copy, permission walkthrough sequencing.
6. **First-launch TCC permissions walkthrough.** Mic + screen + accessibility + automation in one guided flow, with one-line explainers BEFORE each macOS system dialog.
7. **Calendar auto-prep.** "Prep for the 3pm with Sarah" pulls the last email thread, agenda, related Drive docs, dossier notes into a brief. Distinct from cold-start.
8. **Higher-quality TTS.** Replace macOS `say` with Polly or ElevenLabs. Real human-sounding voice in the user's earbud.
9. **Per-user account multi-tenancy.** Right now everything keys off one account_id. Real multi-tenancy: each user's dossier, queue, recents stay isolated.

### P2 — nice-to-have, not blocking

10. **Speaker biometrics / voice-print enrollment.** So pendant doesn't act on other people's voices in the room. Eventually mandatory; not blocking the demo.
11. **Telemetry from real installs.** Privacy-respecting counts, latencies, failure modes. Without this we ship blind. Build before first 100 users.
12. **Wake-word fallback.** "Hey Anticipy" as a secondary path for edge cases. NOT the primary input.

## The 2-3 full E2E tests to confirm "done"

When the P0 list is shipped, run all three. The user runs them. The user confirms PASS.

**Test 1: New user signup on Omar's Mac.**
1. Create a new macOS user account
2. Download DMG from `anticipy.ai/app`
3. Install + open
4. Complete onboarding (Twilio voice call + welcome screen sequence)
5. Within 60 seconds, dossier shows at least 10 real people from Omar's Gmail
6. Say out loud: "I should send Zara Somani the meeting notes from yesterday"
7. Within 30 seconds, get an SMS asking YES/NO/EDIT
8. Reply YES
9. Verify real Gmail draft appears in real Chrome with Zara as recipient + body in Omar's voice
10. Receipt SMS arrives confirming the send with Message-ID

**Test 2: Trivia in the wild.**
1. User has the pendant on / Mac mic listening
2. Say out loud to a friend: "Wait, when did the Roman Empire fall?"
3. Within 2 seconds, earbud TTS speaks "476 AD Western, 1453 Constantinople"
4. Phone notification mirrors the answer for lock-screen glance
5. Repeat with 5 different trivia phrases. All correct, all under 2 seconds, no false fires on rhetorical questions

**Test 3: Multi-day follow-through.**
1. Say "Remind me to send the contract to Joe in 3 weeks"
2. Engine confirms task accepted, persists to queue
3. Kill the Anticipy app
4. Reopen 5 minutes later, task still in queue
5. Skip 3 weeks (or override wake_at to now+30s for test)
6. Engine fires the task, SMS prompts user to confirm
7. User replies YES, draft appears in real Gmail to Joe
8. Receipt arrives

## When the user says "done"

The cron writes `state/orchestrator/DONE_v2.json` only when:
- All 6 gates GREEN simultaneously for 5 consecutive cycles
- All 3 full E2E tests above PASS without manual intervention
- The user has signed off in writing in the orchestrator log

Until then, the work continues.
