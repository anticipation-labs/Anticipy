# Instant cold start. Day zero, minute one, useful.

Owner thread: 10-instant-cold-start. Drafted 2026-05-29. Working doc.

The premise. A new wearer downloads `Anticipy.app` from `anticipy.ai/app`, drags to `/Applications`, clicks Open, and stares at the popover welcome screen for 45 to 60 seconds while macOS prompts mic / screen / automation consent. During those seconds the engine is NOT idle. It is in the background driving the user's already-running Chrome through their already-logged-in Gmail, Calendar, Drive, plus the macOS Notes app and a `mdfind` walk of `~/Documents`, feeding everything raw to OpenRouter, writing structured entries to `~/.anticipy/v7/dossiers/<account_id>/dossier.json` as the LLM produces them. By the time the user clicks the final "Got it" the dossier is ~70% populated. The product is useful. Not in five minutes, not after a Twilio call, not after a week of passive listening. By the time the welcome flow ends.

This supersedes `planning/01-cold-start/OPTIONS.md`, which proposed seven strategies around a 5-minute MVP and a 90-second Twilio call. Both are too slow for day zero, both treat the user as a passive participant. The right shape is parallel, background, LLM-driven, generic, and finished before the user notices it ran.

## 1. The bar

Day zero, minute one, the agent answers three classes of question correctly without any role template or recipe registry:

- "What did Sarah and I discuss in our last call?" Looks up Sarah Chen, finds her email-thread cluster from this week, returns the most recent thread plus the next calendar event they share.
- "Who do I email most about the Q3 roadmap?" Matches the project-name index built from inbox subjects + Drive doc titles + calendar events, returns the top contributor by email count.
- "Draft a thank-you to the person I met for coffee yesterday." Reads yesterday's calendar for events flagged "coffee" or matching a 30-to-60-minute one-on-one with an external attendee, opens Gmail compose, drafts a short note in the user's writing voice sampled from their sent folder.

None of these come from "if user is a founder then X" templates. None from regex pattern matching. All from the LLM reading raw text the engine fed it and producing structured output the dossier loader knows how to consume.

Miss-target: agent says "I don't have that information yet, give me 30 more seconds." Tolerable at minute one. NOT tolerable at minute three.

## 2. The simultaneous inhale

T+0 begins when the engine binds to `127.0.0.1:8731` and confirms Chrome alive on `localhost:9222`. Orchestrator is a new module at `engine/app/coldstart/instant_inhale.py`. It owns the parallel walk and the streaming write loop. The popover at `desktop/src/popover.html` posts to a new `/api/coldstart/instant/start` route and renders a real-time progress strip.

Lane 1: Chrome tab discovery. Orchestrator hits `http://localhost:9222/json` to list open tabs. If `mail.google.com`, `calendar.google.com`, `drive.google.com` are open and authenticated (cookie heuristic: presence of `SAPISID`), they jump to the front of the queue. Otherwise the orchestrator opens them as background tabs via `Target.createTarget` with `background=true`. Same Chrome the user uses every day. No OAuth, no service API, no token exchange.

Lane 2: Gmail walk. CDP session against the Gmail tab. Scroll inbox virtualized list (`[role="row"]`) and sent folder, collect up to 500 row snippets per folder: sender name+email, subject, snippet, timestamp, label chips. NOT bodies. Then open Settings > Accounts URL hash for the signature block and send-as identities. Budget: 12s inbox, 8s sent, 2s settings.

Lane 3: Calendar walk. Navigate to agenda view (`/calendar/u/0/r/agenda`), scroll 30 days back and 30 days forward, capture each event's title, start, duration, attendee chips, recurrence, response status. Budget: 8s.

Lane 4: Drive walk. Recents and Shared, first 100 file titles + types + collaborator avatars, ignore bodies. Budget: 6s.

Lane 5: Native Notes. `osascript -e 'tell application "Notes" to get name of every note'` (same TCC path `native_action_macos.py` uses). First line + mtime of the 50 most-recent notes. Budget: 4s.

Lane 6: Native Calendar. Two-tier: `osascript` + EventKit via `native_action_macos.py`. Caught by the Calendar TCC consent the popover pre-prompts. Budget: 4s.

Lane 7: Filesystem. `mdfind 'kMDItemFSContentChangeDate > $time.today(-30) && (kMDItemContentType == "com.microsoft.word.doc" || ...)'` over `~/Documents` and `~/Desktop`. For each file: path, mtime, owner, and (for the top 30 by recency) first 500 chars via `textract` for office docs and `pdftotext -l 1` for PDFs. Budget: 10s.

All seven lanes run concurrently on `asyncio.gather`. Each lane streams output as small JSON chunks to a per-lane queue. A consumer drains queues and batches 30-to-50-item windows for the LLM. The model broker (`/api/engine/model` proxying to DeepSeek V4 Flash) receives windows with one of three system prompts (people-extraction, project-extraction, voice-sampling) and returns structured deltas. Each delta appends to the dossier via a new `DossierLoader.merge_delta(delta_dict)` method, atomic temp-file rename.

Concurrency budget: 4 in-flight broker requests per user, prompt-cache hits on the static system prompts. DeepSeek V4 Flash at ~700 tok/s decode, ~30 tok per delta entry. We land ~80 entries per second across four streams. With 50 people, 20 projects, 8 tools, 5 voice samples to extract, dossier crosses 70% at roughly T+45s. Remaining 30% is the long-tail trickle that runs to T+90 in the background. User is not blocked.

## 3. Structured output schema

Extends the existing `dossier.json` shape (parsed by `dossier_active_loader.py:139`). New top-level keys for v2:

```json
{
  "schema_version": 2,
  "people": [
    {"name": "Sarah Chen", "email": "sarah.chen@acme.io", "pronouns": "she/her",
     "role": "VP Product at Acme", "relationship": "external_collaborator",
     "frequency": {"emails_30d": 47, "meetings_30d": 6},
     "last_seen": "2026-05-28T16:00:00-07:00",
     "tags": ["q3_roadmap"], "aliases": ["Sarah"],
     "provenance": "inhaled_from_gmail+calendar", "confidence": 0.91}
  ],
  "projects": [
    {"name": "Q3 roadmap", "related_people": ["Sarah Chen", "Marcus Wei"],
     "related_tools": ["Linear", "Notion"], "status": "active",
     "evidence_count": 23, "first_seen": "2026-04-12",
     "provenance": "inhaled_from_gmail+drive", "confidence": 0.84}
  ],
  "tools_used": [
    {"name": "Gmail", "url_hint": "mail.google.com", "primary": true,
     "evidence": "500 messages in 30 days",
     "provenance": "inhaled_from_chrome_tab_inventory"}
  ],
  "writing_voice": {
    "samples": ["Thanks for jumping on that, Sarah. I'll loop in Marcus."],
    "formality": "casual_professional", "sign_off_pattern": "Best,\\nOmar",
    "common_phrases": ["loop in", "circle back"], "avg_sentence_length": 14,
    "provenance": "inhaled_from_gmail_sent_folder"
  },
  "schedule_pattern": {
    "timezone": "America/Los_Angeles", "working_hours": "08:30-18:30 Mon-Fri",
    "typical_meeting_density": "4.2 per day",
    "provenance": "inhaled_from_calendar"
  }
}
```

`provenance` is required on every leaf. `DossierLoader.as_context_block` (line 308) gets extended to surface project names and writing-voice samples to the planner. The `_finalize_plan` heuristic in `server.py` gains a project-name resolver matching "Q3 roadmap" the way it currently matches first names to people.

## 4. The streaming write

Each LLM completion returns a JSON list of partial entries, not a full dossier. The consumer takes each entry, runs a schema check (`name` or `email` for people, `name` for projects), and calls `DossierLoader.merge_delta` which:

1. Acquires the existing `_LOCK` in `dossier_active_loader.py`.
2. Reads current dossier JSON.
3. For each delta: if a matching person/project exists (key = email-or-name for people, normalized name for projects), merge field-by-field with newer `last_seen` winning. Otherwise append.
4. Re-sorts by `last_seen` desc.
5. Writes `dossier.json.tmp` then `os.replace` to `dossier.json`. Atomic on POSIX.
6. Bumps in-memory `self._raw`.
7. Emits SSE to the popover: `{lane: "gmail", added: 3, total_people: 47, eta_s: 18}`.

Agent becomes useful progressively. T+5: Gmail signature gives `name`, `role_title`, `email`. T+12: first 50 senders identified. T+20: calendar attendees tagged with relationships. T+30: projects clustered from email subjects + Drive titles. T+45: writing voice samples extracted. T+60: dossier is demo-ready. The user's first question at any moment reads `DossierLoader.snapshot()` for the freshest state.

## 5. What we DON'T do

No role templates. The `/roles/Lawyer-Litigation.md`, `Sales-AE-B2B.md` directory of pre-built dossiers is wrong: every user is unique and the priors actively poison the dossier with confident wrong defaults.

No 90-second Twilio call as default. The `INTERVIEW_SCRIPT` from `engine/app/anticipy/onboarding.py:24` is slow, intrusive (user has to answer in front of an investor), error-prone (ASR mishearing "Sarah" as "Sara" cements wrong aliases). Keep it as fallback when inhale lanes return empty, not as the day-zero path.

No hardcoded category rules. No "if sender ends in `.gov` they are a government contact." Brittle, leaks bias, breaks in non-English markets. The LLM categorizes.

No 24-hour passive-listening warmup. The 72-hour ambient-listen strategy is right as steady-state refinement, wrong as a cold-start gate. The instant-inhale fills the day-zero dossier; passive listening corrects it over the following week.

No skill library or per-app recipe registry. The seven lanes are generic: scroll a list, capture row metadata, ship to the LLM. Not "Salesforce recipe v3." If the user runs HubSpot, lane 4 finds the HubSpot tab the same way it finds Salesforce. DOM extraction is row-based, not selector-based.

## 6. Privacy

The privacy moat is the single largest reason a user picks Anticipy over Limitless or Bee. Hard rules:

- Seven lanes run in the user's local Chrome, against local cookies, under the local Mac account. No keys leave the device. No remote browser. No service API gets a token.
- LLM is the OpenRouter broker at `https://www.anticipy.ai/api/engine/model` proxying to DeepSeek V4 Flash via `provider_routing.order=["deepseek"]` exactly as `platform_adapter.model_call` pins at line 126. OpenRouter configured for non-retention providers.
- Dossier on disk is the only persisted artifact. Names, emails, project labels, voice samples, schedule patterns. NOT email bodies, calendar descriptions, or file contents. Raw walk output lives in in-memory queues, never written to disk.
- Dossier encrypted at rest using the existing Fernet key already used for `~/.anticipy/system_v1/cookies`. Key in keychain under `com.anticipy.dossier-key`.
- Popover welcome shows one sentence: "Anticipy reads your open tabs to learn your people and projects. Nothing leaves your Mac except the bare minimum sent to our AI model."
- User can disable any lane from the popover (slide toggles). Disabling means less data, not a broken product.
- No raw email content sent to the LLM. Only visible row metadata Gmail's inbox already shows.

## 7. The "user not on Gmail" fallback

If `mail.google.com` is not open, the orchestrator checks `outlook.live.com`, `outlook.office.com`, `mail.proton.me`, `mail.fastmail.com`, `app.hey.com`, `app.superhuman.com`. The same row-scroll lane works against any of them; lane uses a generic "find the scrollable list with the most repeated child elements" heuristic via JS injected through `Runtime.evaluate` rather than hardcoded selectors. If no webmail tab is open, open `mail.google.com` first. If it lands on a sign-in screen rather than an inbox (cookie heuristic), close silently and fall back to section 8.

Calendar and Drive have the same shape: Outlook Calendar, Fastmail, Apple Calendar iCloud web; Drive could be Google, OneDrive, Dropbox, iCloud Drive web. Orchestrator never assumes Google.

## 8. The fallback fallback

User runs Apple Mail desktop, no webmail tab. Switch to the local file system path. Mail.app's index at `~/Library/Mail/V10/MailData/Envelope Index` (SQLite) holds headers + threading; read read-only via `sqlite3 mode=ro`. Yields the same data the Gmail row walk produces. Caught by the Documents-folder TCC the popover requests. Equivalent paths: Outlook desktop at `~/Library/Group Containers/UBF8T346G9.Office/Outlook/...`, Thunderbird at `~/Library/Thunderbird/Profiles/<random>.default-release/Mail/`. Add adapters as users surface them.

## 9. Dossier provenance

Every leaf carries a `provenance` string. The field exists conceptually in `memory_provenance.py` but isn't enforced in the active dossier. Instant-inhale enforces it. Values: `inhaled_from_gmail`, `inhaled_from_outlook_web`, `inhaled_from_apple_mail_local`, `inhaled_from_calendar`, `inhaled_from_drive`, `inhaled_from_notes_app`, `inhaled_from_filesystem`, `inhaled_from_chrome_tab_inventory`, `asked_user`, `observed_in_session`, `inferred_by_llm`.

Two reasons it matters. One, when an inhaled fact is wrong (LLM mis-parsed a signature, calendar event was a recurring "hold" with no real attendee), the agent apologizes specifically: "I had Sarah Chen as VP Product because of her Gmail signature, but you just told me she's CTO. Updating." Two, when the user changes jobs we can selectively purge `inhaled_from_<old_employer_domain>` entries while preserving personal entries.

A `provenance_freshness` timestamp tracks when the source was last walked. A nightly job re-walks and refreshes entries that still appear; entries absent for 14 days demote to `stale` and stop influencing planner output until re-confirmed.

## 10. The 60-second target

Popover progress strip surfaces these milestones live:

T+0 to T+5: Engine binds 8731, Chrome alive on 9222, orchestrator hits `/json` for tab inventory. If Gmail signature is in the DOM of an open tab, extract immediately. Popover: "Found you in 4.2 seconds. Reading your tabs."

T+5 to T+15: Lanes 5, 6, 7 (Notes, Calendar app, filesystem) complete. Local-only, fast. Dossier has writing-voice samples from recent docs, user's name from `~/Library/Preferences/.GlobalPreferences.plist` plus `id -F`, 30+ file headlines. Popover: "Read 47 recent files. Got your writing style."

T+15 to T+30: Lanes 2, 3, 4 (Gmail, Calendar, Drive) hit their walk budgets. Raw data streams to the LLM in 30-row batches. First people-extraction delta around T+22 with ~25 people. First project delta around T+28 with ~10 projects. Popover: "Found 47 people, 12 projects so far."

T+30 to T+60: Lanes drain tail queues. By T+45 dossier has 50+ people, 20+ projects, 8 tools, 5 voice samples, top sender clustering, calendar relationship inference. Popover: "Dossier 70% done. Ready when you are." User clicks "Start using Anticipy."

T+60 onward: Background trickle continues. Long-tail people fill in over the following 90 seconds. The user's first command at any point reads `DossierLoader.snapshot()` for whatever's there.

Popover shows a single horizontal bar with seven segment markers, each painting gray to gold as that lane completes. No spinners, no fake percent counter. Just "tabs / inbox / sent / calendar / drive / notes / files," painted left to right.

## 11. Computer-use as primary actor

This cold-start is NOT a Chrome-extension job. The extension at `extension_v4/` requires explicit install, is blocked by MDM, gives no advantage over CDP. The primary actor is the agent driving Chrome at port 9222 (LaunchAgent-managed `~/.anticipy/chrome-real-clone`) plus computer-use for flows that escape the browser (Notes TCC dialog, Calendar.app permission prompt).

CDP is production-grade: `engine/app/action_engine/cdp_dispatcher.py` and `scripts/v7/anticipy_bridge_fallback_cdp.py` both work today against 9222. Instant-inhale uses the same connection. Does NOT spawn a new Chrome or a headless background browser. Reads the tabs the user already has open. Computer-use enters only for welcome-screen TCC prompts: agent observes via screenshot, clicks OK on Notes, Screen Recording, Accessibility, Calendar, Reminders.

Subtle problem: Chrome at 9222 is the LaunchAgent-managed clone, NOT the user's daily-driver Chrome. Clone has no cookies, no logged-in Gmail. Fix: a "first-run import" copies `~/Library/Application Support/Google/Chrome/Default/{Cookies,Login Data,Bookmarks,History}` into the clone profile. Walk budget: 4s. Then inhale runs against the now-logged-in clone.

## 12. What works for the investor demo tomorrow

Minimum viable for 2026-05-30:

- `engine/app/coldstart/instant_inhale.py` exists and runs Lane 2 (Gmail) + Lane 3 (Calendar) + Lane 7 (filesystem). Lanes 1, 4, 5, 6 can be cut.
- Chrome data import from user's real Chrome to the clone runs at first launch.
- `DossierLoader.merge_delta` is implemented.
- System prompts for people-extraction and project-extraction are tuned against Omar's actual Gmail. Calibrated to land ~30 people and ~8 projects in the first 45s.
- Popover shows the progress strip with three segments (gmail / calendar / files).
- Planted demo question: "draft a thank-you to the person I met for coffee yesterday." Dossier has the coffee meeting (calendar event titled "Coffee with X" yesterday, single external attendee). `_fastpath_plan_from_memory` at `server.py:5276` matches X to a dossier person, the LLM composes the draft using the writing_voice sample, and `/api/act` opens Gmail compose pre-filled. Question to draft: under 8s.

Cut for the demo, ship next week: voice-style sophistication, project-clustering past ~70% accuracy, Apple Mail / Outlook desktop fallbacks (assume Gmail), Fernet wrapper (ship plaintext; the rest of `~/.anticipy/` is plaintext today).

Dry run before the demo: clean macOS account on a second Mac, fresh download, install, open, observe inhale, ask planted question, verify draft. Three consecutive cold runs PASS = green.

Failure mode to monitor: the OpenRouter broker rate limit. With 4 in-flight requests and 50 people to extract we might hit per-user QPS cap. Mitigation: pre-warm the broker with a no-op request 5 minutes before the demo.

## 13. Risks and open questions

Chrome data import touches the user's `Cookies` SQLite, locked while Chrome is running. Either close Chrome briefly (jarring) or read via `Network.getAllCookies` (cleaner but only returns cookies for currently-open tabs). The Network path is preferable; verify it returns expired-but-cached cookies too.

The 30-day calendar walk depends on Google Calendar's agenda-view DOM not changing. Brittle. Long-term: LLM-guided "find the meeting list and extract titles" rather than CSS-selector-based. Short-term, ship the selectors, accept the breakage risk.

Dossier schema v2 changes are break-compatible: `DossierLoader` already parses dict-shaped and list-shaped `people` (line 180). New fields need accessor methods, existing callers continue to work.

"User has no Chrome at all" (Safari only) needs an AppleScript adapter for Safari. Safari has no CDP equivalent and AppleScript can't walk a virtualized inbox. Safari users get a degraded inhale (calendar app + filesystem + Notes, no inbox). Popover says: "Anticipy works best with Chrome. Safari-only users get a lighter dossier." About 12% of macOS users per StatCounter 2026Q1.

The investor may not ask the planted question. If they ask something the dossier doesn't cover ("schedule a follow-up with my CFO"), the agent says "I don't know your CFO yet, want me to add them now?" rather than fabricate. Calibration question for `actionable_probability`; default conservative.

Open: dossier survival across devices. If Omar runs on laptop and iMac, do both run their own inhale and diverge? V7 `scoped_memory.py` has a Supabase outbox at `memory_cloud_sync.py` that could handle this; extend to dossier deltas. Out of scope for day zero, in scope for V1.

Open: legal exposure on the filesystem walk. We read file titles and the first 500 chars of office docs to extract project names. If the doc contains attorney-client privileged or HIPAA-covered data and the title alone reveals it, are we creating a privacy hazard by surfacing the project name to the LLM? Mitigation: the LLM call sees only project-name candidates, not full text. Full text never leaves the device. Document this explicitly in the privacy explainer.
