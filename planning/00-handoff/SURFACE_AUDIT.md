# Anticipy Surface Audit

Each surface is scored 1 to 5 against the 12 principles in `DESIGN_BRIEF.md`. Three sub-scores are pulled out as the most load-bearing for that surface. A one-sentence gap and a one-sentence fix follow. A ranked gap list closes the document.

Scoring scale.
- 5 = exemplary, defensibly Apple-level
- 4 = good, small refinements possible
- 3 = acceptable, real gap exists
- 2 = noticeably weak, hurts the perceived quality
- 1 = broken or in conflict with the principle

Files cited use absolute paths.

## Surface 1. Tauri menubar popover

Files. `/Users/omarebrahim/Developer/Anticipy-V7/desktop/src/popover.html`, `/Users/omarebrahim/Developer/Anticipy-V7/desktop/src/main.js`, `/Users/omarebrahim/Developer/Anticipy-V7/desktop/src/styles.css`.

Sub-scores.
- P1 Deference: 4. Three columns are the user's data, the brand wordmark is a single 17px word at top left, the status pill is one word plus a 7px dot.
- P3 Depth: 4. 200ms fade plus 4px translate with a refined cubic bezier (line 106 to 108), banner-in keyframe (line 371), pure SF font stack (line 85).
- P12 Inevitability: 3. Two parallel views (welcome vs columns) is honest, but the welcome state and the populated state are visually so different that the menubar feels like two different apps.

Gap. The popover's welcome state and populated state share no anchor element. The user opens the same icon and lands in two visually disjoint apps depending on dossier state.
Fix. Keep the three-column scaffold visible in both states. In the welcome state the columns show "tell me about you" cards in Now, "we will queue here" in Next, and "your history will live here" in Past, so the user sees the same structure they will see tomorrow.

## Surface 2. Welcome and onboarding pages

Files. `/Users/omarebrahim/Developer/Anticipy-V7/src/app/onboarding/audio/page.tsx`, `/Users/omarebrahim/Developer/Anticipy-V7/src/app/onboarding/chat/page.tsx`, `/Users/omarebrahim/Developer/Anticipy-V7/src/app/onboarding/call/page.tsx`.

Sub-scores.
- P2 Clarity: 4. Audio: "Show me your life." Chat: "A short conversation. Then Anticipy already knows who matters." Call: "Let Anticipy call you to learn who matters." Each headline is one sentence, the body is one paragraph.
- P9 Discoverability: 3. Audio page has a single dropzone (good), chat page has one input plus one Send button (good), call page has three inputs in a row with a single CTA (good). But the three pages do not cross-link each other consistently. Chat page links to call. Call page links to chat. Audio page has no nav at all.
- P11 Conceptual model: 2. The call page tells the user the call is a stub ("Voice provider is not wired up in this build"). That is honest, but a new user reading "let Anticipy call you" then learning it is a log entry forms a broken model.

Gap. The call onboarding option is surfaced as live on the popover welcome card ("Have Anticipy call you, Quick friend-style interview on your phone") but the destination page reveals it is a stub. The user feels lied to before the product even ran.
Fix. Either ship Twilio voice for the onboarding call before exposing the card, or relabel the popover card to "Schedule a call from Anticipy" and remove "hands-free, no typing" from the subtext until it is true.

## Surface 3. Download page

File. `/Users/omarebrahim/Developer/Anticipy-V7/src/app/app/download/page.tsx`.

Sub-scores.
- P9 Discoverability: 5. Single Download for Mac button, three numbered install steps, optional Already-installed deep link block. Numbered 01 02 03 in monospace gold matches the brand.
- P6 Communication: 3. The Gatekeeper warning paragraph is essential ("If macOS says Anticipy is from an unverified developer or that it is damaged"), but it sits above the download button. The user reads about errors before they have done anything, which lowers confidence.
- P11 Conceptual model: 4. Drag to Applications, double click. Three steps. Clear.

Gap. The Gatekeeper apology copy is rendered before the user has even tried to install, so the very first screen they see is a future error.
Fix. Move the Gatekeeper paragraph to appear only after the download has started (state flip on the anchor click) or collapse it behind a small "If macOS shows a warning" disclosure under the install steps.

## Surface 4. Three demo moments end to end

### 4a. Trivia in your ear

Files. `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/trivia/deliver.py`, `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/proactive/notifier.py`.

Sub-scores.
- P5 Real human voice: 3. `_deliver_audio` (line 117 to 150) routes to `app.product.tts` which prefers ElevenLabs then Polly, and falls back to macOS `say` only on import failure or env disable. That is correct. But the failsafe `_spawn_say` is what runs when a stranger downloads the DMG with no cloud TTS credentials, and `say` is the giveaway robot voice that signals "this is a Mac trick", not "this is a wearable".
- P7 Periphery first: 4. TTS is auditory periphery (it plays in the user's earbud while they are doing something else). The recent-fires log persists for the popover. Both correct.
- P10 Feedback: 4. Spawn metadata (synth_ms, play_ms, total_ms) is captured per fire so latency regressions are measurable. The cached-audio path plays in under 50ms (deliver.py header comment).

Gap. New DMG installs hit the `say` failsafe because they have no ElevenLabs key, and the macOS `say` voice is the single largest "this feels like a Toyota" tell in the product.
Fix. Bundle a small set of pre-rendered ElevenLabs audio for the seeded trivia answers in the DMG (deliver.py already has `cache_hit` plumbing) and ship a server-side broker key for fresh synth so strangers get a human voice on day one without rolling their own ElevenLabs account.

### 4b. Silent execute

File. `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/product/sms_pre_confirm.py`.

Sub-scores.
- P4 Restraint: 4. The pre-confirm body (`build_proposal_text`, line 408 to 477) is one sentence with the verb, recipient, subject, 100-char preview, and the three-letter reply set (YES, NO, EDIT). 320 char hard cap. Single SMS segment. Right amount.
- P6 Communication: 4. The proposal names the action plainly ("Anticipy is about to email lara@example.com about...") and the YES/NO/EDIT contract is unambiguous.
- P11 Conceptual model: 3. The expiry sweep saves the work as a Gmail draft after 5 minutes and SMS-pings the user (line 1294 to 1323). That is good follow-through. But the user's mental model is "I replied YES, Anticipy sent it" or "I replied NO, Anticipy didn't". The "EDIT" reply path has no defined UX inside the SMS thread; the user is told they can EDIT but the next message is not specified.

Gap. EDIT is offered as a third option in every pre-confirm SMS but there is no SMS thread that handles the actual edit; the user types EDIT and then has nothing to do.
Fix. After parsing reply_class == "edit" in `resolve_inbound` (line 1262), send a follow-up SMS containing the current draft body and ask the user to text back the edited version, OR remove EDIT from the prompt until the round-trip is implemented.

### 4c. "I just do" post-action receipt

Files. `_emit_action_receipt` and `_send_receipt_sms_sync` in `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/product/server.py`.

Sub-scores.
- P6 Communication: 4. The receipt SMS includes the recipient, subject, and (when available) a link to the sent message in Gmail. The self-email is sent to the user's own address with the screenshot path inline.
- P10 Feedback: 5. SMS plus a self-email plus a Gmail Message-ID plus a screenshot path. Anticipy is closing the loop with verifiable evidence. This is the strongest surface in the product.
- P4 Restraint: 3. The combination of SMS and self-email for every action is one channel too many for the daily case. A self-email for every Anticipy action will pile up in the user's inbox quickly.

Gap. Every successful action fires both an SMS and a self-email, which becomes inbox noise after the first dozen actions; the inbox stops feeling like the user's inbox.
Fix. Make self-email the audit-trail surface (file it under a "Anticipy" Gmail label by default so it skips the inbox) and keep SMS as the realtime receipt; or batch self-emails into a once-daily digest.

## Surface 5. Error and failure messages

File. `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/product/failure_recovery.py`.

Sub-scores.
- P2 Clarity: 5. The six SMS templates (login_required, mfa_challenge, captcha_blocked, rate_limited, network_error, unknown_error) are plain English. No HTTP codes. No stack traces. Each ends with "I will retry once you ..." which closes the loop.
- P6 Communication: 5. The service label map (line 266 to 292) translates `mail.google.com` to "Gmail", `accounts.google.com` to "your Google account", `appleid.apple.com` to "your Apple ID". The user reads the message and knows exactly what to fix.
- P8 Inform and encalm: 4. The body cap at 320 chars keeps the SMS to a single segment. The deduplicate guard (line 644 to 658) prevents double-sending the same kind for the same task. Both reduce anxiety.

Gap. The unknown_error template ("Anticipy paused {summary} on {service} and needs a hand. I will retry once you take a look.") gives the user nothing concrete to do; they get a friendly ping with no signifier for the next action.
Fix. When `classify_failure` returns unknown_error, log the raw exception text into a popover "things to look at" feed and include a tap link in the SMS to that feed entry, so the user has somewhere to go even if Anticipy cannot tell them what to do.

## Surface 6. TCC permission flow

File. `/Users/omarebrahim/Developer/Anticipy-V7/desktop/src/popover.html` (lines 389 to 401 for the pre-prompt, the mic-card recovery banner, and the mic-open-settings button).

Sub-scores.
- P6 Communication: 5. The pre-prompt banner ("Microphone access in a moment. Anticipy needs to hear what people ask you to do. macOS will ask you to allow it next.") fires before the macOS dialog, so the user knows what is about to happen and why. The denied-state recovery banner has a direct "Open System Settings" button. Both are textbook calm-tech communication.
- P9 Discoverability: 4. The single button (`mic-open-settings`) invokes a Rust command that deep-links into System Settings privacy pane. The user does not have to navigate System Settings on their own.
- P11 Conceptual model: 4. "macOS will ask Anticipy for permission to use your microphone, take screenshots, and control other apps. That is so Anticipy can hear what you mention and act in your real Chrome." The two-clause sentence aligns the technical request with the product purpose.

Gap. The pre-prompt explainer only covers the microphone request; screenshot and Automation TCC dialogs land later with no pre-prompt and no recovery card.
Fix. Mirror the mic pre-prompt pattern for the Screen Recording dialog and the Automation (Apple Events) dialog: a banner fires when Rust is about to invoke the permission probe, and a denied-state recovery card with an Open System Settings button appears if the user denies.

## Surface 7. Random tab opens (the Omar pain)

Files. `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/coldstart/auto_inhale.py`, `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/product/calendar_prep.py`, `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/coldstart/cdp_walker.py`, `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/proactive/notifier.py`.

Sub-scores.
- P7 Periphery first: 1. `_cdp_create_new_tab` (cdp_walker.py line 147 to 179) opens real tabs in the user's Chrome via `/json/new`. Chrome adds these to the tab strip. The user watches Gmail inbox, Gmail sent, and Calendar tabs flick in then close. The inhaler does this once per cold start (`walk_gmail` twice plus `walk_calendar`). The calendar prep scheduler does this every 5 minutes while it scans (`find_upcoming_meeting` calls `walk_calendar` from `_scheduler_loop`, line 974 to 1001). Per-meeting prep adds two more tabs (Gmail search and Drive search via `_walk_gmail_for_attendee` and `_walk_drive_for_attendee`).
- P11 Conceptual model: 1. The user's model is "Anticipy is on my Mac listening". The reality is "every 5 minutes my Chrome window jolts because Anticipy opened a tab I did not ask for". Two models in direct conflict.
- P8 Inform and encalm: 1. Visible tab churn is the opposite of calm. It interrupts whatever the user was reading.

Gap. The calendar prep scheduler scans every 5 minutes by opening visible tabs in the user's primary Chrome window, which is the single largest violation of calm tech in the whole product.
Fix. Drive every CDP walker call through a dedicated separate Chrome window (created once with `Browser.createBrowserContext` plus a minimized or off-screen window via `Browser.setWindowBounds`) so the user's primary tab strip stays untouched, and surface a one-line popover row "Anticipy is scanning your calendar" the first time it runs so the user has a conceptual model for the activity even when they cannot see it.

## Ranked gaps

Sorted by impact desc, effort asc.

| # | Gap | Surface | Principle violated | Effort | Proposed fix | Impact |
|---|-----|---------|-------------------|--------|--------------|--------|
| 1 | Calendar prep scheduler opens visible Chrome tabs every 5 min, inhaler opens Gmail inbox + sent + Calendar tabs at cold start, per-meeting prep opens Gmail and Drive search tabs. | Random tab opens | P7 Periphery, P8 Inform and encalm, P11 Conceptual model | L | Route every CDP walker call through a dedicated Anticipy Chrome window that is minimized or off-screen, and surface "Anticipy is scanning your calendar" once in the popover. | 5 |
| 2 | New DMG installs fall back to macOS `say` voice for trivia because no ElevenLabs key, which is the single biggest "Toyota" tell. | Trivia in your ear | P5 Real human voice | M | Bundle pre-rendered ElevenLabs audio for the seeded trivia answers in the DMG and ship a server-side broker key so fresh synth uses a real human voice on day one. | 5 |
| 3 | Onboarding call card is surfaced as live but the destination page is a stub. | Onboarding | P11 Conceptual model | S | Either wire Twilio voice for onboarding before exposing the card, or relabel the popover card to remove "hands-free, no typing" until it is true. | 4 |
| 4 | Every successful action fires both SMS and self-email, which becomes inbox noise. | "I just do" receipt | P4 Restraint | S | Auto-label self-emails under "Anticipy" and skip the inbox by default, or batch into a once-daily digest. | 4 |
| 5 | Pre-confirm SMS offers EDIT as a reply option but no SMS round-trip handles the edit. | Silent execute | P11 Conceptual model | S | After reply_class == "edit", send a follow-up SMS with the current body and accept the user's edit, or remove EDIT until the round-trip is implemented. | 4 |
| 6 | TCC pre-prompt covers only the microphone, not Screen Recording or Automation. | TCC permission flow | P6 Communication, P9 Discoverability | S | Mirror the mic pre-prompt banner and denied-state recovery card for the Screen Recording dialog and the Automation dialog. | 4 |
| 7 | Notifier defaults to "Anticipy" as title when DecisionKind is None. | All notifications | P6 Communication | XS | Always derive a one-sentence title from the decision body in `_default_local_notify_title` instead of returning the bare brand word. | 3 |
| 8 | Download page shows the Gatekeeper warning paragraph above the download button. | Download page | P6 Communication, P11 Conceptual model | XS | Render the Gatekeeper text only after the download starts, or collapse it as a small disclosure below the install steps. | 3 |
| 9 | Popover welcome state and populated state share no anchor element. | Menubar popover | P12 Inevitability | M | Keep the three-column scaffold visible in both states with "tell me about you" cards filling Now, Next, Past until the dossier is populated. | 3 |
| 10 | unknown_error recovery SMS gives the user nothing concrete to do. | Failure messages | P9 Discoverability | S | Log the raw exception into a popover "things to look at" feed and link to that entry from the SMS body. | 3 |
| 11 | Onboarding pages do not cross-link consistently. | Onboarding | P9 Discoverability | XS | Add the same three-link nav (call, chat, audio) to all three pages so users can switch path. | 2 |
| 12 | Popover "Past" column polls every 5s so receipt feedback can lag up to 5s. | Menubar popover | P10 Feedback | S | Push a `task-completed` Tauri event from Rust when the engine emits a receipt and trigger an immediate refresh, leaving the 5s poll as the safety net. | 2 |
