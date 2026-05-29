# Instant cold start. Day zero, minute one, useful.

Owner thread: 10-instant-cold-start. Drafted 2026-05-29. Working doc.

The premise. A new wearer downloads `Anticipy.app` from `anticipy.ai/app`, drags to `/Applications`, clicks Open, and stares at the popover welcome screen for the next 45 to 60 seconds while macOS prompts mic / screen / automation consent. During those 45 to 60 seconds the engine is NOT idle. It is in the background driving the user's already-running Chrome through their already-logged-in Gmail, Calendar, Drive, plus the macOS Notes app and a `mdfind` walk of `~/Documents`, feeding everything raw to OpenRouter, and writing structured entries to `~/.anticipy/v7/dossiers/<account_id>/dossier.json` as the LLM produces them. By the time the user clicks the final "Got it" on the permissions explainer, the dossier is ~70% populated. The product is useful. Not in five minutes, not after a Twilio call, not after a week of passive listening. By the time the welcome flow ends.

This supersedes `planning/01-cold-start/OPTIONS.md`, which proposed seven strategies around a 5-minute MVP and a 90-second Twilio call. Both are too slow for day zero, both treat the user as a passive participant. The right shape is parallel, background, LLM-driven, generic, and finished before the user notices it ran.

## 1. The bar

Day zero, minute one, the agent answers three classes of question correctly without any role template or recipe registry:

- "What did Sarah and I discuss in our last call?" The agent looks up Sarah Chen in the dossier, finds her email-thread cluster from this week, returns the most recent thread plus the next calendar event they share.
- "Who is the person I email most about the Q3 roadmap?" The agent matches the project-name index built from inbox subject lines + Drive doc titles + recent calendar events, returns the top contributor by email count.
- "Draft a thank-you to the person I met for coffee yesterday." The agent reads yesterday's calendar entries flagged "coffee" or matching a 30-to-60-minute one-on-one with an external attendee, picks the most recent, opens Gmail compose, drafts a short note in the user's writing voice (sampled from their sent folder).

None of these answers come from "if user is a founder then X" templates. None come from regex pattern matching. All come from the LLM reading raw text the engine fed it and producing structured output the dossier loader knows how to consume.

The miss-target: the agent says "I don't have that information yet, give me 30 more seconds." Tolerable at minute one. NOT tolerable at minute three.

## 2. The simultaneous inhale

T+0 begins the moment the engine binds to `127.0.0.1:8731` and confirms Chrome is alive on `localhost:9222`. The orchestrator is a new module at `engine/app/coldstart/instant_inhale.py`. It owns the parallel walk and the streaming write loop. The popover at `desktop/src/popover.html` posts to a new `/api/coldstart/instant/start` route and immediately renders a real-time progress strip with the seven lanes below.

Lane 1: Chrome tab discovery. The orchestrator hits `http://localhost:9222/json` to list open tabs. If `mail.google.com`, `calendar.google.com`, `drive.google.com` are open and authenticated (cookie heuristic: presence of `SAPISID`), they jump to the front of the queue. Otherwise the orchestrator opens them as background tabs via `Target.createTarget` with `background=true`. Same Chrome the user uses every day. User is already logged in. No OAuth, no service API, no token exchange.

Lane 2: Gmail walk. Inside an attached CDP session against the Gmail tab, the orchestrator scrolls the inbox virtualized list (`[role="row"]`) and the sent folder, collecting up to 500 row snippets per folder. For each row it pulls visible columns: sender name and email, subject, snippet, timestamp, label chips. It does NOT open individual messages (no bodies, only row metadata). It then opens the Settings > Accounts URL hash to read the signature block (`#settings/accounts`) and the send-as identities. Walk budget: 12 s inbox, 8 s sent, 2 s settings.

Lane 3: Calendar walk. The orchestrator navigates to the agenda view URL (`https://calendar.google.com/calendar/u/0/r/agenda`), scrolls 30 days back and 30 days forward, captures each event's title, start, duration, attendee chips, recurrence indicator, response status. Walk budget: 8 s.

Lane 4: Drive walk. Navigates to Recents and Shared, captures the first 100 file titles and types and collaborator avatars, ignores bodies. Walk budget: 6 s.

Lane 5: Native Notes app. `osascript -e 'tell application "Notes" to get name of every note'` (the same TCC-gated path `native_action_macos.py` already uses for the Notes surface). Pulls the first line and modification date of the 50 most recently modified notes. Walk budget: 4 s.

Lane 6: Native Calendar app. Two-tier read: first via `osascript -e 'tell application "Calendar" to get summary of every event whose start date is greater than ...'`, then via `EventKit` through the existing `native_action_macos.py` helper. Caught by the Calendar TCC consent the popover pre-prompts. Walk budget: 4 s.

Lane 7: Filesystem. `mdfind 'kMDItemFSContentChangeDate > $time.today(-30) && (kMDItemContentType == "com.microsoft.word.doc" || ...)'` to enumerate recently modified `.docx`, `.pdf`, `.md`, `.txt`, `.pages` files under `~/Documents` and `~/Desktop`. For each file, capture path, modification date, owner, and (for the top 30 by recency) the first 500 characters via `textract` for office docs and `pdftotext -l 1` for PDFs. Walk budget: 10 s.

All seven lanes run concurrently on `asyncio.gather`. Each lane streams its raw output as small JSON chunks (one row per Gmail message, one event per calendar entry) to a per-lane queue. A consumer task drains the queues and batches into 30-to-50-item windows for the LLM. The model broker (`/api/engine/model` proxying to OpenRouter DeepSeek V4 Flash) receives the windows with one of three system prompts (people-extraction, project-extraction, voice-sampling) and returns structured deltas. Each delta appends to the dossier via a new `DossierLoader.merge_delta(delta_dict)` method, atomic temp-file rename.

Concurrency budget: 4 in-flight broker requests per user, prompt-cache hits on the static system prompts. DeepSeek V4 Flash at ~700 tok/s decode, ~30 tok per delta entry. We land ~80 entries per second across the four streams. With 50 people, 20 projects, 8 tools, 5 voice samples to extract, the dossier crosses the 70% threshold at roughly T+45 s. The remaining 30% is the long-tail trickle that runs to T+90 in the background. User is not blocked.

## 3. The structured output schema

The dossier extends the existing `~/.anticipy/v7/dossiers/<account_id>/dossier.json` shape (parsed by `dossier_active_loader.py:139`). Current loader reads `people`, `preferences`, `do_not_touch`, `pronoun_map`, `recent_topics`. New top-level keys for v2:

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
    {"name": "Q3 roadmap", "aliases": ["q3-roadmap"],
     "related_people": ["Sarah Chen", "Marcus Wei"],
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
    "free_focus_blocks": ["08:30-10:00 Mon/Wed/Fri"],
    "provenance": "inhaled_from_calendar"
  }
}
```

`provenance` is required on every leaf. The dossier loader's `as_context_block` (line 308) gets extended to surface project names and writing-voice samples to the planner. The `_finalize_plan` heuristic in `server.py` gains a project-name resolver that matches "Q3 roadmap" to the project entry the way it currently matches first names to people.

## 4. The streaming write

Each LLM completion returns a JSON list of partial entries, not a full dossier. The consumer takes each entry, runs a fast schema check (presence of `name` or `email` for people, `name` for projects), and calls `DossierLoader.merge_delta` which:

1. Acquires the existing `_LOCK` in `dossier_active_loader.py`.
2. Reads the current dossier JSON.
3. For each delta: if a matching person/project/tool exists (key = email-or-name for people, normalized name for projects), merge field-by-field with newer `last_seen` winning. Otherwise append.
4. Re-sorts arrays by `last_seen` descending.
5. Writes `dossier.json.tmp` then `os.replace` to `dossier.json`. Atomic on POSIX.
6. Bumps in-memory `self._raw` so subsequent reads don't re-hit disk.
7. Emits a server-sent event to the popover: `{lane: "gmail", added: 3, total_people: 47, total_projects: 12, eta_s: 18}`.

The agent gets useful progressively. T+5: Gmail signature gives `name`, `role_title`, `email`. T+12: first 50 senders identified. T+20: calendar attendees tagged with relationships. T+30: projects clustered from email subjects + Drive titles. T+45: writing voice samples extracted. T+60: dossier is demo-ready. The user's first question at any moment reads `DossierLoader.snapshot()` for the freshest state.

## 5. What we DON'T do

No role templates. The `/roles/Lawyer-Litigation.md`, `Sales-AE-B2B.md` directory of pre-built dossiers is wrong: every user is unique and the priors actively poison the dossier. A "Founder-Hardware" template pre-populating "your investors are X, Y, Z" gives confident wrong defaults that take days to correct.

No 90-second Twilio call as default. The `INTERVIEW_SCRIPT` from `engine/app/anticipy/onboarding.py:24` is slow (90 s is forever when the demo is now), intrusive (user has to answer in front of an investor), error-prone (ASR mishearing "Sarah" as "Sara" cements wrong aliases). We keep the script as fallback when the inhale lanes return empty, not as the day-zero path.

No hardcoded category rules. We do not write code that says "if sender ends in `.gov` they are a government contact." Brittle, leaks bias, breaks in non-English markets. The LLM categorizes. Our code is a pipeline.

No 24-hour passive-listening warmup. The 72-hour ambient-listen strategy is right as steady-state refinement, wrong as a cold-start gate. The instant-inhale fills the day-zero dossier. Passive listening corrects it over the following week.

No skill library or per-app recipe registry. The seven lanes are generic: scroll a list, capture row metadata, ship to the LLM. Not "Salesforce recipe v3" + "Procore recipe v1." If the user is logged into HubSpot instead of Salesforce, lane 4 finds the HubSpot tab the same way it would find Salesforce. DOM extraction is row-based, not selector-based.

## 6. Privacy

The privacy moat is the single largest reason a user picks Anticipy over Limitless or Bee. Hard rules:

- All seven lanes run in the user's local Chrome, against the user's local cookies, under the user's local Mac account. No keys leave the device. No tabs on a remote browser. No service API receives a token.
- The LLM is the OpenRouter broker at `https://www.anticipy.ai/api/engine/model`, which proxies to DeepSeek V4 Flash via `provider_routing.order=["deepseek"]` exactly as `platform_adapter.model_call` already pins at line 126. OpenRouter is configured for non-retention providers per their privacy docs.
- The dossier on disk is the only persisted artifact. It contains names, emails, project labels, voice samples, schedule patterns. It does NOT contain email bodies, calendar descriptions, or file contents. Raw walk output is held in memory in the orchestrator's queues and never written to disk.
- Dossier is encrypted at rest using the existing Fernet key already used for `~/.anticipy/system_v1/cookies` (V6 cookie-jar pattern). Key in keychain under `com.anticipy.dossier-key`.
- Popover welcome shows one sentence: "Anticipy reads your open tabs to learn your people and projects. Nothing leaves your Mac except the bare minimum sent to our AI model." Link to a plain-English privacy explainer. No legalese.
- User can disable any lane from the popover (slide toggles). Disabling a lane means less data, not a broken product.
- No raw email content sent to the LLM. Only visible row metadata Gmail's inbox already shows. If the user later asks Anticipy to draft a reply to a thread, that body is read for that one task and discarded after.

## 7. The "user not logged into Gmail" fallback

If `mail.google.com` is not in any open tab, the orchestrator checks `outlook.live.com`, `outlook.office.com`, `mail.proton.me`, `mail.fastmail.com`, `app.hey.com`, `app.superhuman.com`. The same row-scroll lane works against any of them; the lane uses a generic "find the scrollable list with the most repeated child elements" heuristic via JS injected through `Runtime.evaluate` rather than hardcoded selectors. If no webmail tab is open, the orchestrator opens `mail.google.com` first. If the result is a sign-in screen rather than an inbox (cookie heuristic), close silently and fall back to section 8.

Calendar and Drive have the same generic shape: Outlook Calendar (`outlook.live.com/calendar`), Fastmail Calendar, Apple Calendar iCloud web UI; Drive could be Google Drive, OneDrive, Dropbox, iCloud Drive web. Orchestrator never assumes Google.

## 8. The fallback fallback

User runs Apple Mail desktop, no webmail tab. Switch to the local file system path. Apple Mail stores `.mbox` files under `~/Library/Mail/V10/<account_id>/INBOX.mbox/Messages/`. Each `.emlx` is plain-text envelope + headers + body. We need only headers for the inhale: `From:`, `To:`, `Subject:`, `Date:`, `Message-ID:`. `email.parser.BytesParser` over the most recent 500 files yields the same data the Gmail row walk produces. Mail.app's index at `~/Library/Mail/V10/MailData/Envelope Index` (SQLite) holds the same data faster with threading already resolved; we read it read-only via `sqlite3` `mode=ro`. Caught by the existing Documents-folder TCC consent the popover requests.

For Outlook desktop: `~/Library/Group Containers/UBF8T346G9.Office/Outlook/Outlook 15 Profiles/Main Profile/Data/`. Thunderbird: `~/Library/Thunderbird/Profiles/<random>.default-release/Mail/`. Add adapters as users surface them; orchestrator picks the first one that finds a recently modified file.

## 9. The dossier provenance

Every leaf carries a `provenance` string. Today the field exists conceptually in `memory_provenance.py` but isn't enforced in the active dossier. The instant-inhale enforces it. Values:

- `inhaled_from_gmail`, `inhaled_from_outlook_web`, `inhaled_from_apple_mail_local`
- `inhaled_from_calendar`, `inhaled_from_drive`, `inhaled_from_notes_app`
- `inhaled_from_filesystem`, `inhaled_from_chrome_tab_inventory`
- `asked_user` (the rare Twilio fallback)
- `observed_in_session` (later, from ambient listening)
- `inferred_by_llm` (when the LLM combined multiple sources, listed with parent provenances)

This matters for two reasons. One, when an inhaled fact is wrong (LLM mis-parsed a signature, calendar event was a recurring "hold" with no real attendee), the agent apologizes specifically: "I had Sarah Chen as VP Product because of her Gmail signature, but you just told me she's CTO now. Updating." Two, when the user changes jobs we selectively purge `inhaled_from_<old_employer_domain>` entries while preserving personal entries.

A `provenance_freshness` timestamp tracks when the source was last walked. A nightly background job re-walks the same surfaces and refreshes entries that still appear; entries absent for 14 days demote to `stale` and stop influencing planner output until re-confirmed.

## 10. The 60-second target

Detailed breakdown, popover progress strip surfaces these milestones live:

T+0 to T+5: Engine binds 8731. Chrome alive on 9222. Orchestrator hits `/json` for tab inventory. If Gmail signature is in the DOM of an open tab we extract it immediately. Popover: "Found you in 4.2 seconds. Reading your tabs."

T+5 to T+15: Lane 5 (Notes), Lane 6 (Calendar app), Lane 7 (filesystem) complete. Local-only, fast. Dossier has writing-voice samples from recent docs, the user's name from `~/Library/Preferences/.GlobalPreferences.plist` plus `id -F`, and 30+ recent file headlines. Popover: "Read 47 recent files. Got your writing style."

T+15 to T+30: Lane 2 (Gmail inbox + sent + signature), Lane 3 (Calendar), Lane 4 (Drive) hit their walk budgets. Raw data streams to the LLM in 30-row batches. First people-extraction delta lands around T+22 with ~25 people. First project delta around T+28 with ~10 projects. Popover: "Found 47 people, 12 projects so far."

T+30 to T+60: Lanes drain their tail queues. By T+45 the dossier has 50+ people, 20+ projects, 8 tools, 5 voice samples, top sender clustering, calendar relationship inference. Popover: "Dossier 70% done. Ready when you are." User clicks "Start using Anticipy."

T+60 onward: Background trickle continues. The 50-to-200-most-recent-people range fills in over the following 90 seconds. The user's first command at any point reads `DossierLoader.snapshot()` for whatever's there.

The popover shows a single horizontal bar with seven segment markers, each painting gray to gold as that lane completes. No spinning gears, no fake percent counter. Just "tabs / inbox / sent / calendar / drive / notes / files," painted left to right.

## 11. Computer-use as primary actor for the cold-start

This cold-start is NOT a Chrome-extension job. The extension at `extension_v4/` requires explicit install, is blocked by MDM on managed Macs, gives no advantage over CDP. The primary actor is the agent driving Chrome at port 9222 (the load-bearing LaunchAgent-managed `~/.anticipy/chrome-real-clone`) plus computer-use (`mcp__computer-use__*`) for flows that escape the browser (the macOS Notes app TCC dialog, Calendar.app permission prompt).

The CDP path is production-grade: `engine/app/action_engine/cdp_dispatcher.py` and `scripts/v7/anticipy_bridge_fallback_cdp.py` both work today against 9222. The instant-inhale orchestrator uses the same CDP connection. It does NOT open a new Chrome, spawn a new profile, reach for a headless background browser. It reads the tabs the user already has open in the Chrome the user is already using.

Computer-use enters only for welcome-screen TCC prompts: when the user first sees "Anticipy wants to access Notes," the agent observes the dialog via screenshot, clicks OK. Same for Screen Recording, Accessibility, Calendar, Reminders permissions. The user watches the popover and follows the screen.

Subtle problem: the Chrome at port 9222 is the LaunchAgent-managed clone, NOT the user's daily-driver Chrome. For day-zero the clone has no cookies, no logged-in Gmail. The clone is for safe action execution; it is not where the user's life lives. The instant-inhale needs the user's real Chrome. Cleanest fix: a "first-run import" that copies the user's Chrome cookies and history into the clone before the inhale runs. Popover's first action after permissions is "Import your Chrome data," which copies `~/Library/Application Support/Google/Chrome/Default/{Cookies,Login Data,Bookmarks,History}` into the clone profile. Walk budget: 4 s. Then inhale runs against the now-logged-in clone.

## 12. What works for the investor demo tomorrow

Minimum viable for 2026-05-30:

- `engine/app/coldstart/instant_inhale.py` exists and runs Lane 2 (Gmail) + Lane 3 (Calendar) + Lane 7 (filesystem). Lanes 1, 4, 5, 6 can be cut.
- Chrome data import from user's real Chrome to the clone runs at first launch.
- `DossierLoader.merge_delta` is implemented.
- System prompts for people-extraction and project-extraction are tuned against Omar's actual Gmail. Calibrated to land ~30 people and ~8 projects in the first 45 s.
- Popover shows the progress strip with three segments (gmail / calendar / files).
- The planted demo question is "draft a thank-you to the person I met for coffee yesterday." The dossier has the coffee meeting (calendar event titled "Coffee with X" yesterday, single external attendee). `_fastpath_plan_from_memory` at `server.py:5276` matches X to a dossier person, the LLM composes the draft using the writing_voice sample, and `/api/act` opens Gmail compose with the draft pre-filled. Question to draft: under 8 s.

Cut for the demo, ship next week: voice-style sampling sophistication, project-clustering quality past ~70% accuracy, the Apple Mail / Outlook desktop fallbacks (assume Gmail), the Fernet wrapper (ship plaintext; the rest of `~/.anticipy/` is plaintext today).

Dry run before the demo: clean macOS account on a second Mac, fresh download from `anticipy.ai/app`, install, open, observe the inhale, ask the planted question, verify the draft. Three consecutive cold runs PASS = green for demo.

Failure mode to monitor: the OpenRouter broker rate limit. With 4 in-flight requests and 50 people to extract we might hit the per-user QPS cap. Mitigation: pre-warm the broker with a no-op request 5 minutes before the demo, confirm headroom.

## 13. Risks and open questions

Chrome data import touches the user's `Cookies` SQLite, locked while Chrome is running. Either close Chrome briefly (jarring) or read via `Network.getAllCookies` (cleaner but only returns cookies for currently-open tabs). The Network path is preferable; verify it returns expired-but-cached cookies too.

The 30-day calendar walk depends on Google Calendar's agenda-view DOM not changing. Brittle. Long-term we want LLM-guided "find the meeting list and extract titles" rather than CSS-selector-based. Short-term, ship the selectors, accept the breakage risk.

Dossier schema v2 changes are break-compatible: `DossierLoader` already parses dict-shaped and list-shaped `people` (line 180). New fields (projects, tools_used, writing_voice, schedule_pattern) need new accessor methods but existing callers continue to work.

The "user has no Chrome at all" case (Safari only) needs an AppleScript adapter for Safari that reads tab titles via `tell application "Safari" to get URL of every tab of every window`. Safari has no CDP equivalent and AppleScript can't walk a virtualized inbox list. Safari users get a degraded "instant inhale" that reads only the calendar app + filesystem + Notes, no inbox. Mention this in the popover: "Anticipy works best with Chrome. Safari-only users get a lighter dossier." About 12% of macOS users per StatCounter 2026Q1.

The investor may not ask the planted question. If they ask something the dossier doesn't cover ("schedule a follow-up with my CFO"), the agent needs a graceful fallback that says "I don't know your CFO yet, want me to add them now?" rather than fabricate. This is the calibration question for `actionable_probability`; default conservative.

Open: dossier survival across devices. If Omar runs on laptop and iMac, do both run their own inhale and diverge? Or does one device run and sync to the other? V7 `scoped_memory.py` has a Supabase outbox at `memory_cloud_sync.py` that could handle this; extend to dossier deltas. Out of scope for day-zero, in scope for V1.

Open: legal exposure on the filesystem walk. We read file titles and the first 500 chars of office docs to extract project names. If the doc contains attorney-client privileged or HIPAA-covered data and the title alone reveals it, are we creating a privacy hazard by surfacing the project name to the LLM? Mitigation: the LLM call sees only project-name candidates, not full text. The full text never leaves the device. Document this explicitly in the privacy explainer.
