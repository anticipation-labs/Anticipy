# Anticipy front end — the plan to make it consumer-ready

*Scope: the iOS app (`app/ios/Anticipy/`), the Chrome extension (`extension/`), the hosted setup page (`backend/pb_public/setup.html`), the marketing page (`website/`). The Python brain, the PocketBase hooks and the Railway services are working production and are not touched by anything in sections 2–4. Everything below cites a line I opened and read myself.*

---

## 1. The verdict

A cold stranger cannot use this today: the first time they tap the app's main button they get two system permission alerts with no explanation, and if they tap "Don't Allow" the app is dead forever with no way back short of deleting it. The single biggest thing between this and consumer-ready is not a feature — it is that **the app confidently asserts things that are not true**: it says a permission problem can't be fixed when it can, says "Audio never leaves your phone" on a switch that controls nothing, says "Listening" when the pendant is capturing nothing, buzzes "sent" when the server refused, and tells the browser popup "Not connected" to every single real user. Fixing that is roughly three to four weeks of focused front-end work, and about a third of it is deleting things rather than building them.

---

## 2. Ship blockers

*Anything that stops a stranger cold, or that fails App Store / Chrome Web Store review. Ranked worst first.*

### B1. Deny the microphone once and the app is permanently broken
**What they see:** They tap "Listen with phone." iOS asks for speech, then asks for the mic. They tap Don't Allow. A line of small grey text appears mid-screen saying "I need microphone & speech access — Settings › Anticipy." They tap the big button again — nothing happens, because iOS never asks twice. There is no button to Settings. And if they *do* go fix it in iOS Settings themselves, the app still shows the same grey error forever.

**Where it lives:**
- `app/ios/Anticipy/Audio/PhoneListener.swift:35` — `@Published var authorized = true`, set to `false` at `:77` and `:82`, and **never set back to `true` anywhere**. I grepped the whole target: the only hits are `:35, :76, :77, :82` and `ContentView.swift:175`.
- `app/ios/Anticipy/Views/ContentView.swift:175-179` — the entire recovery UI is a `.caption` in `Theme.gray`.
- `grep -rn "openSettingsURLString|UIApplication.shared.open" app/ios/Anticipy/` → **zero matches.** There is no route to Settings anywhere in the app.
- `app/ios/Anticipy/Views/ContentView.swift:141-159` — the button is never `.disabled`, so every further tap silently re-enters a call iOS instantly denies.
- `app/ios/Anticipy/AnticipyApp.swift:248-249` — `keepListening = true` is set *before* `listener.start()`, so `resumeListeningIfWanted()` (`:259-261`) re-fires the doomed start on every foreground.

**Fix:** Set `authorized = true` on the success path in `start()` before `begin()`. Replace the caption with a card carrying a real button that calls `UIApplication.shared.open(URL(string: UIApplication.openSettingsURLString)!)`. Disable and relabel the listen button when `!authorized` so a tap is never a no-op. Set `keepListening = true` only after authorization succeeds. **And add a mic primer screen before the ask** — today there is none: the six onboarding steps at `OnboardingView.swift:24-29` are welcome / howItWorks / yourNumber / pairPendant / browserAgent / transcription, so the stranger's first encounter with what the product actually does is two stacked system alerts. A primer that says what is captured, that it continues in the background, and where the text goes is what stops them tapping Don't Allow in the first place.

### B2. A raw "Backend URL" text field in consumer Settings, one keystroke from bricking the app
**What they see:** Scrolling Settings out of curiosity, they tap the odd monospaced field near the bottom. The cursor lands. One typed or deleted character and the app now points at a server that doesn't exist. Both status pills go grey, the feed stops, nothing they say is ever saved, no error is shown, and there is no reset. The only recovery is deleting and reinstalling.

**Where it lives:** `app/ios/Anticipy/Views/SettingsView.swift:158` — `TextField("Backend URL", text: $backendURL)`, sitting *outside* the `if !session.agentPaired` block (which closes at `:157`), bound straight to `@AppStorage("backendURL")` at `:12`. That is the same key the session reads to build every request (`AnticipyApp.swift:40`, `:63`) and polls against every 3 seconds (`:133`). SwiftUI commits the binding per keystroke. The fallback at `AnticipyApp.swift:63` only fires if `URL(string:)` returns `nil`, which a one-character edit will not cause — you get a valid-but-wrong URL. It also feeds the setup link at `SettingsView.swift:138`.

**Fix:** Put it behind `#if DEBUG` or a hidden gesture on the version footer (`SettingsView.swift:217`). If it must stay: bind to local `@State`, commit only on an explicit "Use this server" tap, require https, and add "Reset to Anticipy's server". Also hoist the default out of the four places it's duplicated (`SettingsView.swift:12`, `AnticipyApp.swift:40`, `AnticipyApp.swift:63`, `OnboardingView.swift:272`).

### B3. The second person to install this reads the first person's life
**What they see:** They open Anticipy for the first time and "Heard" is full of someone else's spoken sentences, and the job cards are someone else's errands — with "Send it" inviting them to authorize them.

**Where it lives:**
- `app/ios/Anticipy/Backend/AnticipyBackend.swift:184-187` (`fetchEvents`) and `:197-200` (`fetchJobs`) send only `perPage` and `sort=-created`. **No owner filter, no device filter.** The same class knows how to do it — `fetchAgent` at `:158` filters on `owner="..."`.
- The only identity stamped on a pushed line is `device_id` = `"iphone-b\(CFBundleVersion)"` (`AnticipyApp.swift:66`), and CFBundleVersion is `34` (`Info.plist:24`) — **identical on every install of the same build.**
- A real per-user `ownerID` UUID exists and is generated at `AnticipyApp.swift:41` / `:72`, and is already used for `owner_profile` and agent pairing. It is simply never passed to either query.
- The backend cannot compensate: `backend/pb_hooks/guard.pb.js:17` and `:29` gate the data API on **one shared token**, which every paired phone receives, and `pushEvent` (`AnticipyBackend.swift:167-170`) carries no owner.

**Fix — the jobs half is front-end and can land now.** `jobs` already has an `owner` column (`backend/pb_migrations/1700000002_agents.js:33`) and the brain stamps it (`brain/anticipy_core.py:492`), so `fetchJobs` can add `filter=owner="\(ownerID)"` today, front-end only. **The transcript half cannot** — `events` has no owner field at all (`backend/pb_migrations/1700000000_anticipy.js:29-36`: device_id, kind, text, decision, goal, needs_confirmation). See §5.

### B4. The extension popup tells every real user the product is broken
**What they see:** They click the Anticipy icon in Chrome to check on it. It says "Not connected — open the setup guide below," with an unlit dot. Forever. Even while pairing and jobs are working perfectly. The reassuring sentence directly below it then reads as a lie.

**Where it lives:** `extension/popup.js:1` — `fetch("http://127.0.0.1:8090/api/health")`. A local PocketBase. Nothing else in the extension uses localhost: `background.js:10` sets `DEFAULT_BASE` to the Railway URL and `onboarding.js:1` hardcodes the same. On any machine with no local PocketBase the fetch is refused and lands on the catch at `popup.js:7`. The dot at `popup.html:27` only gets `.on` inside the success branch (`popup.js:5`), so it never lights. **I confirmed this file ships as-is inside the downloadable zip** (`unzip -p backend/pb_public/anticipy-extension.zip popup.js` → identical line 1).

**Fix:** Resolve the base the way the worker does — read `backendUrl` from `chrome.storage.local`, fall back to the Railway constant, health-check that. Then rebuild the zip.

### B5. No privacy policy, no consent, no delete, no support — anywhere
**What they see:** They hand an always-listening app their first name, last name, email, birthday, phone number and every conversation of their day. Then they have second thoughts. There is no policy to read, no human to contact, no way to delete a single sentence, and no way to erase themselves. Uninstalling doesn't help — the server copy survives and the UUID that identified it is gone.

**Where it lives:** A case-insensitive grep of the whole iOS target for privacy / consent / delete / retention / policy / terms / mailto / support / erase returns **zero product strings** — the only hits are `supportsHaptics`, `supportsOnDeviceRecognition`, and three code comments (`HapticEngine.swift:13`, `PhoneListener.swift:364`, `ContentView.swift:182`). The one destructive control in the app is `SettingsView.swift:49-51` "Forget this pendant", and `PendantManager.forgetPendant()` (`:70-77`) only clears a Bluetooth UUID from UserDefaults — it erases nothing Anticipy heard. Meanwhile the app runs a `.record` session (`PhoneListener.swift:114`) with `audio` in `UIBackgroundModes` (`Info.plist:38-42`) — i.e. from a pocket — and nothing anywhere tells the user that the people around them are being transcribed. `ls backend/pb_public/` returns exactly two files: `anticipy-extension.zip` and `setup.html`. There is no policy page to link to.

**Fix:** The screens are front-end: a consent step after the mic primer that names bystanders and asks for an affirmative tap; a "Privacy & data" section in Settings with a policy link, a support route, and delete controls behind verb-titled confirmations. But it cannot land front-end-only — see §5.

### B6. An engineering debug lab ships inside consumer Settings
**What they see:** Scrolling Settings, a stranger hits a section headed "Haptics — find out what's wrong" with buttons labelled "1 · Buzz the normal way" and "2 · Buzz the other way", an instruction to run an A/B experiment, a sentence addressed to the developer rather than to them, a monospaced dump of internal audio state, and a raw error string. At 47 lines it is about a quarter of the entire Settings screen.

**Where it lives:** `SettingsView.swift:164` (section header), `:171-175` (the two test buttons), `:177` (the experiment instruction), `:193` ("That's mine to fix — tell me you saw this."), `:201-206` (the `mic-allows-haptics / engine / audio` state dump), `:207-209` (raw `r.error` in red).

**Fix:** Wrap `SettingsView.swift:164-210` in `#if DEBUG`, or move it behind a hidden gesture on the version footer at `:217`. This is also the loudest single signal in the product that it is an unfinished internal build, and a straightforward App Review 2.1 rejection for developer content in a shipping binary.

### B7. A privacy promise attached to a switch that controls nothing
**What they see:** The nervous first-timer does exactly the right thing — opens Settings, checks where their voice goes, reads "Audio never leaves your phone," and relaxes.

**Where it lives:** `SettingsView.swift:57-67` — a picker between "On this iPhone — private, offline" and "Cloud — fastest, most accurate", with the caption at `:63-65`. The same choice is offered in onboarding at `OnboardingView.swift:339-342`. A repo-wide grep for `transcriptionEngine` returns **exactly three lines**: `SettingsView.swift:10`, `OnboardingView.swift:10`, and nothing else — no consumer, in iOS, brain, backend or extension. There is no cloud path to select: `TranscriberClient` and `LocalTranscriber` appear only on their own declaration lines (`Audio/TranscriberClient.swift:7`, `Audio/LocalTranscriber.swift:8`) and are never constructed. And the claim itself isn't guaranteed: `PhoneListener.swift:248-250` sets `requiresOnDeviceRecognition = true` **only** `if recognizer?.supportsOnDeviceRecognition == true` — on any device where that is false, SFSpeechRecognizer sends audio to Apple, and the deployment target is iOS 16 (`app/ios/project.yml:5`). Separately, every finalized line's *text* is uploaded regardless (`AnticipyApp.swift:96`), which no screen mentions.

**Fix:** Delete the picker and the onboarding step — that also removes a step from a six-step wall. Make the remaining privacy sentence true of the whole pipeline: audio stays on the phone, the transcript text goes to Anticipy's server so she can act on it. If `supportsOnDeviceRecognition` is false, either refuse to start and say why, or change the sentence on that device.

### B8. "Send it" and "Pair" can fail while telling you they worked
**What they see:** They tap "Send it" on the email Anticipy prepared. The phone buzzes success. It didn't send — the card is still sitting there, which reads as a UI glitch, so they tap again. Or: they type the correct 6-digit pairing code, no error appears, and they believe Chrome is paired. It isn't, and nothing will ever run.

**Where it lives:** Four write calls throw away the server's answer.
- `AnticipyBackend.swift:151-152` — `pairAgent` does `_ = try await URLSession.shared.data(for: patch)` then `return true`. A 403, 404 or 500 all read as success.
- `AnticipyBackend.swift:132-133` — same pattern in `pair()`.
- `AnticipyBackend.swift:215` — same in `setJobStatus`, which is what "Send it" and "Not now" call.
- Only `post()` gets it right, at `AnticipyBackend.swift:235-237`.
- `ContentView.swift:380-382` fires `Haptics.success()` **before** the network call.
- `AnticipyApp.swift:290` and `:295` swallow everything with `try?`.

**Fix:** Have every write check `(200..<300).contains(http.statusCode)` and throw `BackendError` the way `post()` already does. Move the haptic to after a confirmed 2xx, show an in-flight state so a double-tap is impossible, and render an in-card failure row with Retry.

### B9. No network is reported to the user as a wrong pair code
**What they see:** Offline, on hotel wifi, or during a backend blip, someone who typed the correct six digits is told the code is wrong. They retype it, walk back to the laptop, regenerate, retype — still wrong, with no way to discover the real cause.

**Where it lives:** `AnticipyApp.swift:265` collapses every thrown error into `false` — `(try? await backend.pairAgent(...)) ?? false`. `AnticipyBackend.pairAgent` throws out of `readData` (`:53-59`) on any transport failure. The UI has exactly one failure string: `OnboardingView.swift:309` and the same at `SettingsView.swift:153`, both of which blame the user.

**Fix:** Surface a thrown transport error as "I can't reach Anticipy right now" with Retry, and reserve "That code didn't match" for an actual empty lookup. Clear `pairResult` on `.onChange(of: pairCode)` — today the red line stays on screen while they retype.

### B10. The phone number — the product's only way to reach you — is silently thrown away
**What they see:** They type their number, the champagne "That's you" checkmark appears (`OnboardingView.swift:185`), they tap Continue, and the flow advances as if it worked. On a plane, on captive wifi, or during a blip, it didn't. Worse: if they *swipe* to the next step instead of tapping Continue, it is discarded even with a perfect connection.

**Where it lives:** `OnboardingView.swift:56-58` — `Task { _ = await session.saveOwnerPhone(phone) }`, result discarded with `_ =`, and `:59-60` advances synchronously on the next line. `saveOwnerPhone` (`AnticipyApp.swift:224-229`) only persists when the write succeeds. The steps are a `TabView(selection: $step)` at `:23` with `.tabViewStyle(.page(indexDisplayMode: .never))` at `:31` — freely swipeable — and the *only* code that saves is inside the Continue button's action. "Skip for now" at `:75` just does `step += 1`.

**Fix:** Save on *leaving* the step (`.onChange(of: step)` when the old value was 2), or on every valid edit via `session.e164(phone)`. Await the result before advancing; on failure keep them on the step with a plain sentence plus Retry.

### B11. The browser setup path sends strangers to screens that don't exist
Three separate breaks on the one journey that unlocks the whole product:

- **The phone promises a one-click install and hands over a developer sideload.** `OnboardingView.swift:270` — `numbered(2, "Add Anticipy to Chrome (it walks you through it)")`. What actually follows is `setup.html:63-87`: download a zip, unzip it, type `chrome://extensions`, flip Developer mode, click Load unpacked, then pair. Most non-technical people stop at "Developer mode."
- **Step 5 names a screen a first-timer does not have.** `setup.html:85-86` says "In the Anticipy app on your phone, open Settings and type that code. Done — the app will show `Agent live`." During first run there *is* no Settings: `AnticipyApp.swift:13-16` renders `HomeView()` only `if hasOnboarded`, otherwise `OnboardingView()`, and the Settings link is a toolbar item inside HomeView (`ContentView.swift:88`). The pair field is already on the onboarding screen (`OnboardingView.swift:271`, `:291-296`). And "Agent live" is the *home feed* pill (`ContentView.swift:134`) — the Settings row says "Paired" or "Live · seen Ns ago" (`SettingsView.swift:130`, `:133`), and onboarding says "Paired — your browser is hers now." (`OnboardingView.swift:282`).
- **Opened on a phone, setup.html is a dead end.** `SettingsView.swift:138-141` uses `Link(destination: setup)`, which opens the page in Safari *on the phone*. Its one action is the download button at `setup.html:65`, which saves a 33,842-byte zip into Files, and steps 2–5 are impossible on iOS. I read all 94 lines: nothing on the page says you need a Mac or PC. (Onboarding does mitigate this — `OnboardingView.swift:269` says "On your computer" and `:274` offers "Send the setup guide to your computer" — so this bites on the Settings path, not the first run.)

**Fix:** Tell the truth on the phone ("takes about two minutes and needs one Chrome setting flipped") and give the step an equal-weight "I'll do this later." Rewrite `setup.html:85-86` against the real flow and the strings the app actually renders. Make setup.html device-aware: on a small viewport, swap the hero for "You're on your phone — send this to your computer" with a copy-link button, and hide the download.

### B12. Extension onboarding step 2 is an order a consumer cannot obey
**What they see:** The welcome tab is a numbered 3-step page. Step 2 is headed "Give it a mind" and tells them to paste an OpenRouter key, with a password field and a permanently unlit dot reading "No key yet." They have no OpenRouter account and no idea what OpenRouter is. Many stop there believing setup is incomplete.

**Where it lives:** `extension/onboarding.html:73-77`; repeated at `popup.html:36-37`. The code says the opposite: `background.js:66-67` — "Consumers never paste API keys: once paired, the agent fetches its key from the backend" — and `ensureLLMKey()` (`:68-96`) fetches it from `/agent/key` the moment pairing lands. There is no per-user key to supply: `backend/pb_hooks/agent_key.pb.js:18` reads one server env var. Worse, a key pasted there is discarded — `background.js:75` requires `agentModel` and `serviceToken` too, which a popup save doesn't set, so the next `ensureLLMKey()` overwrites it at `:84-85` while `popup.js:25` says "key set".

**Fix:** Delete the key card from `onboarding.html` and the key field from `popup.html`. Renumber to 2 steps.

### B13. The Chrome Web Store package cannot be submitted as it stands
- `extension/store/LISTING.md:57-58` points the privacy policy at `/privacy.html` and admits it needs creating. `ls backend/pb_public/` returns two files. That URL 404s.
- `LISTING.md:60-64` lists the screenshots and the 440×280 tile as still needed.
- `LISTING.md:30` says "Requires the Anticipy app (TestFlight)" — a reviewer cannot obtain it, and I read all 64 lines: **there is no Test Instructions section anywhere.** A reviewer would never get past the pair screen, see a non-functional extension, and reject it.
- `LISTING.md:53-55` tells the reviewer page text goes "to the AI model chosen by the user's own account." Not true: `agent_key.pb.js:18` returns one server-wide `OPENROUTER_API_KEY` and `:24` a server-wide model defaulting to `anthropic/claude-sonnet-4.6`; `background.js:80` fetches that bundle and the model is passed into the run. An inaccuracy caught at review is a rejection; caught after publication it is grounds for suspension.
- `manifest.json:6` requests `notifications` and `LISTING.md:47` justifies it as a shipped feature. A case-insensitive grep of `extension/` for "notification" returns exactly those two lines — there is no `chrome.notifications` call anywhere. On a package already under extra scrutiny for `debugger` (`LISTING.md:5`), a false permission justification is not a good look.
- The public Description (`LISTING.md:16-30`) never says page content leaves the browser; that only appears in the internal reviewer form at `:53-56`.

**Fix:** Write the Test Instructions section (a pre-paired reviewer account, or a documented way to exercise a task without the iOS app). Correct the key/model disclosure. Drop `notifications` from the manifest and the listing, or implement it. Add one plain sentence to the public Description: the text of the page Anticipy is working on is sent to an AI model to decide the next click, and nothing else is collected, sold or shared.

---

## 3. Trust and feel

*The things that make an always-listening product read cheap, templated, or untrustworthy.*

### T1. The permission alerts describe a smaller, more private app than the one shipping
The mic string promises "on-device transcription" and the speech string references "Local mode" — a name that appears nowhere in the UI and gates nothing. Meanwhile the app declares the `audio` background mode, keeps a `.record` session active, and POSTs every finalized line to Railway.
`Info.plist:34-35`, `:36-37`, `:38-42`; `PhoneListener.swift:114`, `:122`; `AnticipyApp.swift:96`. Also `Info.plist:29-30` sets `NSAllowsArbitraryLoads` to `true` in a build whose onboarding says "Streamed securely" (`OnboardingView.swift:342`).
**Fix:** Rewrite both strings in `app/ios/project.yml:40-41` (the generator of record) to name continuous background capture and transmission. Drop the "Local mode" reference. Remove `NSAllowsArbitraryLoads` or scope it to a named dev host.

### T2. The pendant pill says "Listening" while capturing nothing
`ContentView.swift:243` returns "Listening" for a connected pendant, `:295-296` makes Anticipy say "I'm listening.", and `:276-278` breathes the dot on it. But `PendantManager.onOpusFrame` is declared at `BLE/PendantManager.swift:38` and invoked at `:213` — and a grep of the target returns **only those two lines**. The closure is never assigned; every reassembled frame is discarded. No transcript, no brain event, no "Heard" row.
**Fix:** Until an Opus→transcription path exists, gate `:243`, `:276-278` and `:295-296` on `session.listener.isListening`, and label a connected pendant honestly: "Pendant connected · not capturing yet." Three edits, all in ContentView.swift.

### T3. Onboarding tells them the pendant is the microphone, and never mentions the phone
`OnboardingView.swift:133-134` — "She listens / Your pendant hears your day and transcribes it." I read all six steps: the phone microphone is never mentioned once. The pendant step tells them to skip if they have none (`:240`). So a stranger with no pendant finishes onboarding believing the product needs hardware they don't have, lands on a feed where Anticipy says "Nothing needs you right now — I've got it covered." (`ContentView.swift:326` via `:304-306`) with listening switched off, and is given no reason to press the one control that starts her.
**Fix:** Rewrite the `howItWorks` cards phone-first — the phone is the microphone, the pendant is optional and later. Suppress the "I've got it covered" idle line while listening is off.

### T4. A Bluetooth permission alert lands over the welcome screen, for hardware that doesn't ship
`PendantManager.init()` unconditionally builds a `CBCentralManager` with `CBCentralManagerOptionShowPowerAlertKey: true` (`:46-52`), and the manager is a `@StateObject` on the App struct (`AnticipyApp.swift:6`), constructed in the same launch frame it's injected at `:19`. The literal first interaction with the product is a system alert asking for Bluetooth so a device they don't own can "hear your day" (`Info.plist:32-33`).
**Fix:** Gate construction on `hasPairedPendant` (`PendantManager.swift:35`) rather than deferring unconditionally — note `CBCentralManagerOptionRestoreIdentifierKey` at `:49` needs early construction for state restoration, so it must be a gate, not a delay. Consider dropping the `pairPendant` step from the TabView until hardware ships.

### T5. There is no way to stop her from Settings — and Settings tells you to do it there
Listening is a standing state: `keepListening` persists (`AnticipyApp.swift:46`) and `resumeListeningIfWanted()` re-arms the mic on appear and on every foreground (`ContentView.swift:97-106` → `AnticipyApp.swift:259-261`). SettingsView has **no listening control in any of its eight sections** — yet `SettingsView.swift:177` instructs the user to "Turn Listening OFF, try both." The only off switch is on the home feed (`ContentView.swift:141-147`). There is also no timed pause anywhere: it's on or off, forever. (Credit where due: `keepListening` is only ever set by the user's own tap, and the button does become a filled "Listening with phone" pill — so nobody is recording without having asked for it.)
**Fix:** Add a Listening section at the top of Settings: current state, one-tap stop, and timed pause (15 min / 1 hour / until I turn it back on), bound to the existing `session.stopListening()` / `startListening()`.

### T6. Loading, offline, refused and genuinely-empty are all the same confident screen
On first launch in airplane mode a stranger gets "Live your day." and Anticipy saying "I've got the watch" — from an app that cannot reach its own server and has heard nothing. HomeView has exactly one non-content branch (`ContentView.swift:38-40`); a grep of the target returns **zero** `ContentUnavailableView`, zero `.alert`, zero `confirmationDialog`. `backendReachable` starts `false` (`AnticipyApp.swift:35`) and the first probe can take the full 4s timeout (`AnticipyBackend.swift:221`), so a cold launch paints the finished empty state before anything has been tried. And `readData` (`AnticipyBackend.swift:53-60`) never inspects the HTTP status — it hands back the body of a 403 as if it were data, and every caller swallows the decode failure with `try?` (`AnticipyApp.swift:146`, `:149`). Reachability is judged only by `/api/health` (`:219-225`), which the guard hook doesn't protect (`guard.pb.js:24-26`), so the phone can report itself perfectly healthy while every data read is being refused.
**Fix:** Have `readData` throw on non-2xx the way `post()` does. Give the session an explicit state — loading / empty / offline / error — and render four different screens. Never show "Live your day." unless a read actually succeeded and returned zero rows. Pull-to-refresh already exists (`ContentView.swift:76`) but is undiscoverable; give the offline state a visible Retry.

### T7. Words spoken offline vanish without a trace
`unsent` is a plain in-memory array (`AnticipyApp.swift:51`), not `@AppStorage`, not written to disk. `heard(_:)` appends to it only when the push throws (`:97-102`), and `flushUnsent()` drains it only from inside `refresh()` (`:106-114`). The feed row reads "Sending…" (`ContentView.swift:506`). If iOS reclaims the app or they swipe it away before reconnecting, the queue is empty on relaunch, the local rows are gone, and the server never got it. From a product whose entire promise is remembering.
**Fix:** Persist `unsent` and the pending `local-` rows to disk on write, restore on launch, retry from there. Past a threshold, mark the row failed with a Retry instead of "Sending…" forever.

### T8. A failed job is a shrug plus a line of machine text
`DoneCard` renders a non-`done` job as the fixed sentence "Couldn't finish this one" (`ContentView.swift:451-455`) followed by `Text(r)` — `job.result` printed verbatim (`:456-458`). The only interaction is a tap that expands the same raw string (`:465-469`). What lands in there: `extension/background.js:319` writes `result: String(e)` — a raw JavaScript exception. A `needs_user` job gets a "Try again" button (`ContentView.swift:384`); **failure is the one outcome with no way forward.**
**Fix:** Give failed jobs the same treatment as stuck ones — a plain-language reason and a primary "Try again" that re-queues, plus a dismiss. Map known failures to sentences; keep the raw string behind a disclosure.

### T9. Four surfaces promise a browser prompt that never appears
`popup.html:35` ("always pausing for your OK before anything is sent"), `onboarding.html:85` ("always pause for your confirmation before anything is sent, booked, or paid"), and `LISTING.md:24-25` all imply Chrome will stop and ask. It won't. A gate does exist — `agent_loop.js:84` fills everything reversible and returns `needs_user` when unauthorized — but on the normal path the job arrives authorized (`background.js:301-303`) and the agent is explicitly told never to pause again: `agent_loop.js:26` ("The owner gave their answer ONCE… Do not ask again for any part of it") and `:28` ("Ticking 'I agree', accepting terms, a confirmation page, a 'are you sure' dialog — all continue."). That is a defensible design. It is just not what the copy says.
**Fix:** Rewrite all four strings to describe the real gate: the OK happens in the app or by text *before* the task starts, and the browser then carries out exactly what was approved, stopping only if reality differs from it — which is what `agent_loop.js:29` actually enforces.

### T10. Chrome's scariest banner is explained once, at the wrong moment — and cancelling it doesn't work
`onboarding.html:85` is genuinely good copy: it names the exact string "Anticipy started debugging this browser" and explains it. But `background.js:415-421` opens that page only when `details.reason === "install"` — before the banner has ever fired. I grepped `popup.html` and `popup.js` for "debug": zero hits. Days later a yellow bar appears across their tabs and the popup they click in alarm says nothing. And if they click Cancel on the bar — the one thing Chrome offers them — `agent_loop.js:513-519` re-attaches and continues, re-raising it; `attachDebugger` itself retries three times (`:475-480`) and nothing counts re-attaches, so this can repeat for up to `maxSteps` iterations. Only when all three attach attempts fail does it return a message (`:521`) that goes to the job row and is delivered via the *phone* — never shown in Chrome.
**Fix:** Put a persistent "Why is Chrome saying that?" line in `popup.html` whenever a task is running, and one sentence in the public store Description and on `setup.html` **before** the download. Treat a user-cancelled debug session as an explicit stop, not a transient error: end the run and say so in Chrome, with a "Start it again" control.

### T11. The extension popup can only ever say two things
`popup.js:9-16` renders exactly two states — paired, or awaiting-pair — and there is no wiring to build more: `grep -rn "onMessage|sendMessage"` across all five extension JS files returns **zero hits**, and the running-job set is worker memory only (`background.js:63`). So Anticipy opens tabs, attaches a debugger and drives their browser, and its own popup says "Paired with your iPhone ✓". When a task stalls on a login wall or fails (`background.js:276`, `:319`), Chrome shows nothing and there is no stop control on the machine it's running on. (The owner *can* cancel from the phone — `jobStillLive()` at `background.js:239-250`, polled at `agent_loop.js:506`.)
**Fix:** Running tasks are already persisted (`agent_loop.js:463` writes `agentTabs`). Have the worker persist a small `currentJob` record — status, one-line what-I'm-doing, last result — and render it in the popup with a Stop that flips the job row. No backend change needed.

### T12. The pair code is the smallest thing on the page, can't be copied, and can't be replaced
On the extension's welcome page the visual hero is the h1 at `onboarding.html:55` (40px serif, `:19`), the last card is headed "That's it — live your day" (`:84`), and the one thing the user must act on is injected into a 14px grey paragraph (`:31`) at `:66`, below a status line, in the middle of card 1. The code renders at 20px (`onboarding.js:25`) — smaller than the popup's 26px (`popup.html:32`). Meanwhile the unobeyable key card gets a full-width input and a champagne button (`:75-76`), so the fake action outranks the real one. Neither surface has a copy button, and the code is minted exactly once — `ensureRegistered()` early-returns at `background.js:41` before the code is generated at `:43`, so it never rotates and there is no regenerate action anywhere. The owner's own brief asks for a copy-code button (`design/PREMIUM-FEEL.md:105-106`).
**Fix:** Make the code the hero — large, letter-spaced, click-to-copy with a confirmation state — with the explicit instruction naming where to type it. Demote the "you're in" copy to a subtitle and turn card 3 into a live "waiting for your phone…" → "paired" state. Add "Show me a new code" that clears `recordId`/`pairCode` and re-runs the existing registration POST.

### T13. Nothing tells a browser-first user they need an iPhone app they may not be able to get
`onboarding.js:25` says "Type this code in the Anticipy app on your iPhone" with no link, no App Store or TestFlight route, and no branch for someone who doesn't have it. I grepped `onboarding.html`, `onboarding.js` and `popup.html` for "app store", "testflight" and "download": zero hits. `manifest.json:5` never mentions a phone app. The dependency is stated plainly only in `LISTING.md:30`. Once this is in the store, browser-first is the normal order.
**Fix:** State the requirement in the manifest description and above the code on the onboarding page, with a link to get the app, plus an explicit "I don't have the app yet" branch.

### T14. Developer-preview language on the consumer path
`onboarding.js:16` asks the user "is your Anticipy backend running?" — they do not have a backend and won't know what one is. `onboarding.html:90` calls the product a "developer preview" and makes maintaining it via a Chrome internals page their job. And `setup.html:60-61` promises "Five minutes, once" while withholding both ugly facts — that this is a developer install and that it won't auto-update — until *after* they've committed.
**Fix:** Rewrite the unreachable state in the product's voice with a next action. Say the developer-preview truth up front on `setup.html`, not after the download.

### T15. Accessibility: nothing in the iOS app uses a single accessibility API
A grep of the whole target for `accessibilityLabel`, `accessibilityHidden`, `accessibilityElement`, `accessibilityReduceMotion`, `dynamicTypeSize`, `ScaledMetric` and `relativeTo:` returns **zero matches.** Three concrete consequences:
- **Dynamic Type does nothing to headlines.** `Theme.display(_:)` returns `.system(size:weight:design:)` with an absolute point size (`Theme.swift:17-19`), used for the toolbar title (`ContentView.swift:83`), the briefing title (`:274`), every section header (`:336`), the empty-state headline (`:346`) and six places in onboarding (`OnboardingView.swift:96, 131, 168, 213, 264, 337`). Body copy on the same screens uses `.body`/`.callout`, which *does* scale — so at large accessibility sizes the hierarchy inverts. And none of the six onboarding steps sits in a ScrollView (grep returns nothing), so content can be clipped.
- **Reduce Motion is ignored everywhere.** `BreathingDot` runs `.easeInOut(duration: 1.5).repeatForever` (`Theme.swift:223-226`) on the home screen whenever she's listening or working (`ContentView.swift:276-278`); `RadarRipple` runs `.easeOut(duration: 1.6).repeatForever` (`OnboardingView.swift:413`); the feed cross-fades on a spring (`ContentView.swift:73-74`).
- **VoiceOver gets a text element that mutates 36 times a second.** `TypewriterText` appends one character at a time in a loop (`Theme.swift:199-203`) at 36 cps (`:179`) and composes a literal cursor glyph into the string (`:186`). It delivers the welcome sentence (`OnboardingView.swift:101-104`) and the home briefing (`ContentView.swift:281`). Decorative views (`LogoMark`, `BreathingDot`, the status-pill dots) are unhidden, and the two icon-only controls — Settings (`ContentView.swift:88-91`) and Send (`:219-223`) — carry no explicit label. *(To be fair: every button contains real text, so the app is not unusable by VoiceOver — it's unpolished, not blocked.)*

**Fix:** `Theme.display` → `.custom(_, size:relativeTo:)`; wrap each onboarding step in a ScrollView; read `@Environment(\.accessibilityReduceMotion)` in `BreathingDot`, `RadarRipple` and `TypewriterText` and render static/instant when set; add `.accessibilityLabel` to the two icon buttons and `.accessibilityHidden(true)` to the decoration. Then walk the app at AX5 with Bold Text and VoiceOver on.

### T16. The marketing page is a different brand from the product
`website/index.html:9-15` defines `--bg:#07080a`, `--panel:#0e1013`, `--accent:#3ddc84` (bright green), with a system-sans stack (`:21`), an 800-weight headline at -1.5px tracking (`:36`), and a green glowing pulse dot as the logo (`:28-29`). Everything else in the product uses the opposite system — `Theme.swift:8-15` (ink #0C0C0C, ivory #F5F0EB, champagne #C8A97E, serif display), declared verbatim in `setup.html:8-9` and drawn as an ivory pill with a champagne dot in `popup.html:24-25`. The install section is also wrong twice: `:179` says to pick the unzipped `anticipy` folder (both archives produce something else — the hosted zip has 12 files at the root, which macOS extracts as `anticipy-extension`, exactly as `setup.html:80` says), and `:180` promises "The green Anticipy dot appears in your toolbar" — I decoded `extension/icons/icon128.png` and it has exactly three colours: #0C0C0C, #F5F0EB, #C8A97E. No green. And `website/anticipy-extension.zip` is a July 20 build: 5 entries, manifest 0.1.0, no `debugger` and no `tabGroups` permission, `background.js` 3,750 bytes against the shipped 19,310, with no `agent_loop.js` — it physically cannot drive a browser.
**Honest caveat:** this page is not deployed. It is not served from `backend/pb_public/` (which holds two files), and its install section contains no download link at all — all five `href`s are internal anchors. So nobody is currently hitting it.
**Fix:** Delete `website/anticipy-extension.zip`. Either rebuild the page on the `Theme.swift` token set with the real mark, or point the install section at the hosted `/setup.html` as the single source of truth.

---

## 4. Polish

*One line each. All verified, all cheap.*

- **Progress dots**: remaining steps are drawn in `Theme.stroke` #252525 on `Theme.ink` #0C0C0C — a 1.28:1 contrast ratio, effectively invisible, so the flow reads as open-ended. `OnboardingView.swift:41-43`, `Theme.swift:8`, `:11`.
- **"Skip for now"** is a 13pt grey footnote under a filled capsule, with no padding and therefore a tappable area well under 44pt — and it renders on four steps (`step > 0, step < totalSteps - 1`), not two. `OnboardingView.swift:74-78`; the owner's own brief asks for the opposite at `design/PREMIUM-FEEL.md:45`.
- **"Replay the welcome tour"** ejects you into a six-page tour with no confirmation and no exit — step 0 and step 5 have no skip, so the only way back is tapping through the whole thing. `SettingsView.swift:213`, `OnboardingView.swift:63`, `:74`.
- **"Thinking…" never ages out** on a line the brain never decided; if the worker stalls, rows say it for hours with nothing to tap. `ContentView.swift:502-506`.
- **The briefing wipes and re-types itself, with a haptic, on background job changes** — `TypewriterText` keys on the string itself (`Theme.swift:195-199`) and `briefingText` is recomputed from job counts refreshed every 3s (`ContentView.swift:293-308`, `AnticipyApp.swift:133`).
- **Other audio ducks and nothing says so** — `.duckOthers` at `PhoneListener.swift:114`; no screen mentions that music or a podcast will drop while she's listening.
- **Status pills are non-interactive jargon** — "Agent unpaired" means nothing to a stranger, and tapping the pill (the natural instinct) does nothing, because `statusPill` is an `HStack`, not a Button. `ContentView.swift:133`, `:252-265`.
- **Two differently-coloured tab groups both named "Anticipy"** — green at `agent_loop.js:467`, yellow at `background.js:335` — in the exact surface meant to make the agent legible.
- **The popup says "key set" for a key that is thrown away** on the next pairing heartbeat. `popup.js:24-25` vs `background.js:75`, `:84-85`. Moot once the key field is deleted.
- **Extension HTML accessibility floor**: neither `popup.html` nor `onboarding.html` has a `lang` attribute, `popup.html` has no `<title>` (`:3-5`), and a grep for `aria-`/`role=` across both returns nothing — while `onboarding.js:47` rewrites status text every 5 seconds with no live region.
- **setup.html's step animation plays in the wrong order** — the delay rules use `:nth-of-type` (`:44-46`), which counts divs, and `.logo` (`:57`) is div #1, so Step 5 matches no rule and rises first at 0s, 330ms before Step 1.
- **setup.html has no `prefers-reduced-motion`** and every piece of content defaults to `opacity:0` (`:41-42`), so the page is contingent on an animation completing; the logo dot pulses forever (`:39-40`).
- **setup.html's five steps are `<b>` tags, not headings or a list** (`:25-27`, `:63`) — a screen-reader user can't jump between them or hear how many there are; the page's only heading is the h1 at `:59`.
- **`chrome://extensions` must be hand-typed with no copy button** (`setup.html:69`) — Chrome genuinely blocks linking to it, so a copy control is the only correct affordance and the page has no script tag at all.
- **The download is an unsigned zip with no version, size or publisher** (`setup.html:65`) from an auto-generated Railway subdomain, at the moment the user is asked to trust software with `<all_urls>` + `debugger`. Labelling it "v0.2.0 · 33 KB" is free.
- **Windows users silently fail step 1** — "unzip it (double-click the file)" (`setup.html:64`) opens a read-only Explorer view on Windows; Load unpacked cannot read it. No OS branching anywhere in the file, and "Extract All" never appears.
- **The download button has a designed hover state and no authored focus state** — `setup.html:48-50` vs a grep for `:focus` returning nothing.

---

## 5. Explicitly out of scope (needs backend work — your call, separately)

Five things cannot be finished on the front end. Each is listed with exactly *why*.

1. **Scoping the "Heard" transcript to one person.** The `events` collection has no owner field — `backend/pb_migrations/1700000000_anticipy.js:29-36` lists device_id, kind, text, decision, goal, needs_confirmation. There is nothing to filter on. A migration adding `owner`, plus the phone and the brain stamping it, is required. *(The jobs half of B3 is front-end-only and should ship anyway: `jobs` already has `owner` at `1700000002_agents.js:33` and the brain writes it at `brain/anticipy_core.py:492`.)* Also note `guard.pb.js:17`/`:29` gates on **one shared token** for everyone, so even scoped queries are a client-side courtesy, not a security boundary, until the server scopes reads.

2. **A real delete and a real privacy policy.** The Settings UI is front-end, but "Delete everything Anticipy has heard" needs an endpoint that exists, and the policy link needs a page that exists — `backend/pb_public/` currently holds two files. `privacy.html` is a static asset and touches no hooks or migrations, but publishing it still means deploying the backend service. Without both, B5 cannot fully land, and 5.1.1 is a real App Review risk.

3. **Showing the user what they're actually approving.** `ConfirmJobCard` displays only `job.humanGoal` (`ContentView.swift:373-375`) plus `job.result` when non-empty (`:376-378`) — and `result` is optional. The card can only show a draft that something writes. Today nothing does: the brain creates awaiting-confirm jobs with goal/params/status/device_id/owner and no result (`brain/anticipy_core.py:492`), and the extension's held jobs write "opened … page in tab N" (`background.js:368`). Until the brain or the extension writes a real preview — recipient, message text, the fields to be submitted — "Send it" (`AnticipyApp.swift:287-290`) asks people to authorize something they cannot see.

4. **Making the Proactivity slider mean anything.** `@AppStorage("proactivityLevel")` at `SettingsView.swift:11` is its *only* occurrence in the entire repo — iOS, brain, backend, extension. The labels at `:72` — "Only when I ask", "Balanced", "Act on everything" — describe behaviour nothing controls. It is the only thing in the app that looks like a leash on an agent that texts people and drives your logged-in Chrome. **Deleting it is front-end and I'd do that now**; making it real requires the brain to honour it.

5. **The consent + bystander screen.** The screen itself is front-end, but it has to link to a policy that exists and promise a delete that works, so it's gated on items 2 above.

---

## 6. The order I would do it in

Six batches. Batches 1–3 and 5 are iOS; batch 4 is the browser/web path; batch 6 is store and marketing. **Batch 4 and batch 6 can run fully in parallel with the iOS work** — different files, no shared code. Within iOS, do 1 → 2 → 3 in order (2 deletes code that 3 would otherwise have to fix), and 5 can run in parallel with 3.

### Batch 1 — "Nobody gets stuck" *(1 build, ~2 days)*
Fix the mic dead end (B1) including the new primer step; delete the Backend URL field (B2); wrap the haptics lab in `#if DEBUG` (B6).
**Proof it's done:** On a factory-reset device, deny the microphone, then recover to a listening state without deleting the app. Scroll every screen in Settings and find nothing addressed to a developer and nothing that can break the app. `grep -rn "openSettingsURLString" app/ios/Anticipy/` now returns a hit.

### Batch 2 — "Stop saying things that aren't true" *(1 build, ~2 days, mostly deletions)*
Delete the transcription picker and its onboarding step, and the proactivity slider (B7, §5.4); rewrite the purpose strings in `project.yml:40-41` and remove `NSAllowsArbitraryLoads` (T1); gate the pendant "Listening" wording (T2); rewrite `howItWorks` phone-first and suppress the idle line when off (T3); gate the Bluetooth manager on `hasPairedPendant` (T4); add the Listening section to Settings (T5); rewrite the "Add Anticipy to Chrome" line (part of B11).
**Proof it's done:** `grep -rn "transcriptionEngine|proactivityLevel" app/ios` returns nothing. Every user-facing claim in the app maps to a code path you can point at. Fresh launch shows no Bluetooth alert.

### Batch 3 — "Nothing fails silently" *(1 build, ~3–4 days)*
Status checks in `readData`, `setJobStatus`, `pairAgent`, `pair` (B8, T6); typed results through `confirm`/`decline`/`pairAgent` with distinct offline vs wrong-code messages (B9); haptic after 2xx plus in-flight state; save the phone number on leaving the step and await the result (B10); explicit loading/offline/empty/error states with a visible Retry (T6); persist the unsent queue to disk (T7); "Try again" on failed jobs and stop printing raw exceptions (T8); scope `fetchJobs` by owner (the front-end half of B3).
**Proof it's done:** A full walkthrough in airplane mode — onboarding, number entry, pairing, "Send it" — where every single failure produces a sentence a non-engineer understands plus a Retry, and nothing ever buzzes success for a write that didn't land. Kill the app mid-flight with unsent lines; relaunch; the lines are still there and get sent.

### Batch 4 — "The path a stranger actually walks" *(browser + web; parallel with 1–3; ~3–4 days)*
Fix the popup's health check and rebuild the zip (B4); delete the OpenRouter card from `onboarding.html` and `popup.html` and renumber (B12); rebuild the onboarding page around the pair code with copy and regenerate (T12); add running/needs-you/failed popup states with a Stop (T11); rewrite the four "always asks" strings (T9); move the debugger-banner explanation into the popup and onto `setup.html` before the download, and stop auto-re-attaching after a user cancel (T10); make `setup.html` device-aware and rewrite Step 5 against the real flow (B11); Windows unzip branch; the developer-preview truth up front (T14); the "no iPhone app yet" branch (T13); the `nth-of-type` cascade, reduced-motion, `<ol>`/`<h2>` semantics, copy buttons, labelled download, focus style (Polish).
**Proof it's done:** On a clean Chrome profile on a machine that has never run this: download the zip from the hosted page, follow the five steps without help, and pair. The popup is green and truthful at every point. Open `setup.html` on an iPhone and be told to switch devices.

### Batch 5 — "It works at any text size, for anyone" *(1 build, parallel with batch 3; ~2 days)*
`Theme.display` → `relativeTo:`; ScrollView per onboarding step; Reduce Motion branches in `BreathingDot`, `RadarRipple`, `TypewriterText`; VoiceOver labels and hidden decoration; stable typewriter identity so the briefing stops retyping itself; progress-dot contrast; a real 44pt skip button (T15 + Polish).
**Proof it's done:** Screenshots of all six onboarding steps and the home feed at AX5 with Bold Text on — nothing clipped, nothing overlapping, headings still larger than body. Reduce Motion on: nothing loops. VoiceOver on: the welcome sentence is announced once, whole.

### Batch 6 — "Store and marketing" *(parallel with everything; ~1–2 days plus asset production)*
Write the LISTING.md Test Instructions section; correct the key/model disclosure; add the page-text-goes-to-a-model sentence to the public Description; drop `notifications` from `manifest.json` and the listing; delete `website/anticipy-extension.zip`; fix or retire the website install section (B13, T16).
**Proof it's done:** A reviewer with no phone and no TestFlight build can follow the Test Instructions and see a task run. Every sentence in `LISTING.md` matches the code. Nothing in the repo can hand a user a build with no `debugger` permission.

---

**Honest scale.** Sections 2–4 are about 60 distinct changes across roughly a dozen files. Batches 1, 2 and 5 are small and satisfying — a lot of batch 2 is deletion, which is the fastest quality you will ever buy. Batch 3 is the real engineering: it touches the whole backend client and every screen that reads from it. Batch 4 is a rewrite of the extension's two HTML surfaces plus the setup page. Call it three to four weeks for one person working steadily, and none of it touches the brain, the hooks or Railway. The two things you cannot ship a stranger without, that are *not* in that estimate, are the privacy policy page and a working delete — both in §5.