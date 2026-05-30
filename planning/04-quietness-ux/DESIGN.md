# 04 Quietness UX

Planning doc. Owner: Omar. Drafted 2026-05-29.

The pendant is always on, the agent is always thinking, and the user is always somewhere they should not be interrupted. This doc covers how the agent talks to the user without breaking the user's current frame.

## 1. What already exists in the codebase

The skeleton is mostly there. The gaps are calendar-awareness, real device-side delivery, and the digest UX.

### `engine/app/proactive/` (the live cascade)

- `types.py` defines the channel ladder `NOTED → IN_APP → PUSH → SMS → VOICE` (`NotificationChannel`), urgency 1-5 with a `channel` property that maps urgency to channel, and `DecisionKind` (EXECUTE, ASK, LOG, REFUSE). This is the existing public contract.
- `urgency.py` is an LLM-driven urgency scorer (1-5). The mapping `1=NOTED, 2=IN_APP, 3=PUSH, 4=SMS, 5=VOICE` is hardcoded as a property of channel intrusiveness; only the score itself is AI. Default on failure is 2 ("be polite").
- `decider.py` routes the cascade outputs into DecisionKind. Donna refuse > irreversible-ASK > high-confidence-EXECUTE > mid-ASK > LOG. EXECUTE here means do-it-and-tell-the-user-after; the channel still applies for the after-the-fact fyi.
- `notifier.py` has the routing/escalation logic. `DeliveryRoutes` carries pluggable `DeliverFn` callables for in_app/push/sms/voice. Notably: an EXECUTE decision is capped at PUSH (`_cap_channel`) so a fyi-after-the-fact never wakes the user with a voice call. The `_ladder_from` walks down on failure (voice → sms → push → in-app), never escalates up.
- `dispatcher.py` is an LLM-driven dedup gate so the user does not get two notifications for the same goal mentioned twice.
- `donna.py` is the refuse layer.

### `engine/app/proactive_day/` (the day-pipeline simulator)

- `comms.py` is the older non-pendant comms design. Channel is `silent_queue | text | email | call | call2`. The big win that we should port forward: `do_not_interrupt` reachability and a `DEBOUNCE_S` window that merges related items into one composed proposal before delivery. `SECONDS_DEADLINE_S` short-circuits the debounce for time-critical items.
- `timing.py` already understands `_AFTER_EVT` (regex for `after the meeting/standup/sync/call/review`) and reads `world.calendar` for the next event end. So the codebase already has the seed of calendar-aware "fire after this meeting ends" scheduling.
- `world.py` has a `calendar` list with `{title, start, end}` and the `SimWorld.hear` method records utterances with a `place` field (home/office/restaurant). The simulator treats this as ground truth; the live product needs a real adapter.

### `desktop/`

- The Mac app is a Tauri menubar app with a tray icon and a 480x600 popover (`src-tauri/src/lib.rs`, `src/popover.html`). Click the tray, popover slides down under the menubar icon. Esc and click-outside hide it.
- There is no notification, no haptic, no audio playback, no system banner. Tauri 2 has `tauri-plugin-notification` available, the app does not include it. The tray icon currently does not change to indicate "I have something for you".
- The popover has a Dossier section that polls the engine, but no inbox / pending-asks list.

### `src/app/` (the website)

- No notification or push code lives here. The website is the brand surface, account/auth, model broker, and DMG host. Phone notifications will hit the user's phone via APNs/FCM, the website's role is to be the registration/manifest surface for the user's push tokens. Nothing exists yet.

### What is missing

- Real device-side delivery callables. The `DeliveryRoutes` slots are all empty in production wiring.
- Calendar adapter. There is no live read of the user's Google/iCloud calendar.
- Ambient-noise meeting detector (the second source of "user is busy").
- Haptic + LED protocol for the pendant (the pendant is not built yet, but the protocol needs spec).
- TTS playback into earbuds.
- Digest renderer.
- 30-second confirm-or-default-deny timer.

## 2. Notification taxonomy: four classes, four surfaces

These are the DecisionKind values plus the post-execute fyi, mapped to the cheapest acceptable surface. The agent picks the class; the surface follows from class + quietness-state + reachability. Hardcoded mapping below; tunable per user later.

### silent-done (EXECUTE + fully reversible + high confidence)

The agent did the thing. The user need not know in real time.

- Default surface: `NOTED` (the "things I noticed" feed only). Pendant LED gives a single slow gold pulse (1.5s rise, 1.5s fall) at the moment of completion, then off. No haptic.
- Examples: "find the Italian place near me with no shellfish", "set a reminder for 6pm", "look up the Roman empire question".
- Phone shows it on the lockscreen NEXT TIME the screen wakes naturally. No push, no badge sound.
- Mac shows the tray icon switch to a filled-gold dot from hollow-gold for ~10 seconds, then back to hollow.

### notify-after (EXECUTE + irreversible-but-the-user-asked-clearly, or executed-on-clear-prior-consent)

The agent did the thing AND the user should know promptly.

- Default surface: `IN_APP` first (popover badge, phone in-app badge). If user has the popover open or phone unlocked, that is the delivery; otherwise it sits in the inbox and the next phone-unlock or popover-open renders it. The `_cap_channel` cap at PUSH stays; we never voice-call a fyi.
- Pendant LED: two slow gold pulses, no haptic.
- Examples: "I sent the demand letter draft to your matter system", "the OpenTable booking for Saturday is confirmed".

### confirm-before (ASK + irreversible OR mid-confidence)

The agent has a plan and needs a yes/no before acting. The user might be in a meeting.

- Surface depends on quietness state. In a quiet window (no calendar event, no detected meeting): pendant single short haptic pulse + LED amber + earbud TTS "Maya Patel or Maya Chen?". In a busy window: enqueue silently into the next digest; pendant gives no signal; the agent waits.
- If the agent computes the action has a hard deadline that falls inside the meeting, it surfaces ONCE during the meeting via earbud-only TTS (no haptic, no LED, no phone). The TTS is short enough that the user can decide without breaking eye contact. If no earbud is in, see failure-modes (§7).
- 30-second response window. Default-deny if confirm-class. Default-accept ONLY if the action is reversible and confidence is high (which would have routed to silent-done anyway, so default-accept in practice is rare).

### ask-before (ASK + clarification needed, no plan yet)

The agent does not know enough to plan. It needs a disambiguation.

- This is the only class that NEVER fires during a meeting unless the action has a meeting-internal deadline. Default surface is `NOTED` + digest queue.
- In a quiet window: pendant single short haptic + LED amber + earbud TTS question.
- Why different from confirm-before: ask-before is the agent admitting it does not know. Bothering the user during a meeting with "which Maya" when there is no deadline pressure is worse than waiting six minutes.

### REFUSE (the Donna no)

Always silent at the moment of refusal. Goes into the "things I noticed" feed with the refusal reason ("you sounded tired, I did not send that to Sarah"). User sees it on next phone-unlock. The agent never interrupts to tell you it did not do something.

## 3. Calendar-aware quietness

The agent reads two signals: calendar busy and ambient detection.

### Sources

- Calendar adapter. Read-only access to Google Calendar / iCloud / Outlook via the existing OAuth flow used for the planner. Pull the next 8 hours of events at app start and every 5 minutes. Each event becomes a `QuietWindow{start, end, type=calendar, title, hardness=hard}`.
- Mic ambient detector. The existing diarization pipeline already separates wearer from other voices. If the past 90 seconds contains continuous non-wearer voice cluster activity at >40% airtime, that is a `QuietWindow{start=now, end=now+5min sliding, type=ambient_meeting, hardness=soft}`. Sliding because the meeting can run long. Recomputed every 30s.
- User-toggle DND. Tray icon long-press or popover toggle. `QuietWindow{type=manual, hardness=hard, end=user-clears}`.

### Behavior during a quiet window

- All NOTED/IN_APP traffic continues unchanged (they are silent).
- All PUSH/SMS/VOICE traffic is suppressed UNLESS the urgency-5 voice path is reached and the underlying action has a deadline that falls inside this same window.
- All confirm-before and ask-before items are added to a `pending_digest` queue keyed by the quiet window's end time.
- The pendant LED still pulses gold for silent-done, because LED is below the interrupt threshold (no one notices a 1.5-second LED pulse on a pendant from across a table). LED haptic is OFF.

### Between-meetings digest delivery

When a quiet window ends AND the next quiet window starts ≥10 minutes away, the agent fires the digest. If the gap is <10 minutes (back-to-back meetings) the digest is held to the next ≥10-minute gap or until end-of-day.

The 10-minute floor is the rule of thumb that the user can actually process and respond to a small list of asks; less than that and the user just lands in the next meeting with the asks still open.

Delivery sequence:

1. Phone push: "Anticipy: 12 minutes free until 10am — 3 things to confirm."
2. Tray icon switches to filled-amber, indicating pending asks.
3. If the user unlocks the phone within 60 seconds OR clicks the tray icon, render the full digest.
4. If neither happens, fire a second push at T+5min (during the gap). If still no engagement, items roll into the next digest.

## 4. Trivia / quick-answer flow latency budget

The marquee use case. Friend says "when did the Roman empire fall" during dinner. The pendant catches it. Within 1.2 seconds the answer lands in the user's earbud and on their phone lockscreen. The user looks like they just remembered.

Target end-to-end: 1500ms p50, 2000ms p95. From end-of-utterance to start-of-TTS.

| Stage | Budget (ms) | Path |
|---|---|---|
| Pendant VAD end-of-speech | 100 | Silero VAD on the pendant DSP, 100ms hangover window |
| BLE audio chunk → phone | 80 | Last chunk already in flight; ~80ms BLE LE Audio latency budget |
| Phone-side Parakeet ASR | 220 | Parakeet TDT 0.6B v3 on phone NPU, streaming, finalizes ~220ms after VAD end |
| Diarization gate (non-wearer? trivia intent?) | 60 | Sortformer pass, already running streaming, marks "other speaker" + question form |
| Local salience classifier (is this a trivia/lookup?) | 80 | On-device 1-3B classifier, returns binary "answer this" verdict |
| Intent extraction (what is being asked, in canonical form) | 150 | On-device 1-3B → "year of fall of Western Roman Empire" |
| Cloud lookup (Brave/Perplexity/etc API + LLM read) | 600 | Round trip to model broker → search API → reranker → one-sentence answer |
| Phone TTS warmup + first audio frame | 100 | Coqui XTTS-v2 or Apple AVSpeechSynthesizer, first chunk in 100ms |
| BLE audio frame → earbud | 80 | Same path as input |
| **Total cold** | **1470** | |
| Total warm (model broker hot) | 950 | Skip cloud cold-start ~520ms |
| Phone push (parallel, lockscreen render) | ~120 | Fires in parallel with TTS start, hits screen ~120ms after the cloud lookup returns |

Where we can win 200-400ms:

- Run the salience + intent extraction as a single fused on-device call. 80ms + 150ms → 180ms.
- Pre-warm the cloud lookup connection (HTTP/3 keep-alive to the broker, already-loaded LLM context).
- Speculative search: fire the lookup against the partial ASR transcript before finalization completes; if the final transcript matches the partial, reuse the answer.

Where we can NOT win: the BLE in/out 160ms total, and the 220ms ASR finalize, are physical floors with the current pendant hardware. If those need to drop, the answer is a higher-bandwidth radio (UWB) or moving ASR to the pendant DSP, both of which are pendant-hardware decisions.

## 5. Confirmation that does not break flow

The pendant has a single capacitive surface and a single coin haptic. Gestures:

- Double-tap (two firm taps within 400ms): confirm. Maps to "yes" for the most recent pending ask.
- Swipe-down (finger drag down the front face, ~10mm): reject. Maps to "no".
- Long-press (>1s): "ignore this whole conversation for the next 60 seconds", a manual override.

Earbud TTS pairs each ask with "double-tap for yes, swipe for no" the FIRST time per session, then drops the reminder.

Timeout behavior:

- confirm-before class, no response in 30s: default-deny. The agent does nothing and writes to "things I noticed" feed.
- ask-before class, no response in 30s: enqueue for next digest. The agent waits.
- notify-after class: no response expected. Item sits in feed.

If the pendant is not worn (no skin contact detected via the cap-sense floor), all haptic/LED is suppressed and the surface fallback is phone lockscreen.

## 6. The between-meetings digest

What the user sees on phone lockscreen unlock at 9:48 with a meeting at 10:00.

```
Anticipy                                       9:48 AM
12 minutes until your 10:00 with Maya Patel.

Quick asks (3):
[1] Confirm: book Italian on Sat for 2 at 7pm
    OpenTable, Bottega del Vino, $0 hold
    [Yes]  [No]  [Snooze]

[2] Maya Patel or Maya Chen for the 10 AM?
    [Patel]  [Chen]  [Ask me later]

[3] Reply to Dana?
    "thx, on it, will land by EOD"
    [Send]  [Edit]  [Skip]

Done quietly (2):
- Reservation for Tue at Gjelina, confirmed
- "Roman empire" sent to your phone earlier
```

Structure rules:

- Top line: the gap context. "12 minutes until your X." Makes the time pressure honest and bounded.
- Asks section before done section. Asks are why the user opened it. Done is decoration.
- Each ask is a single tap to commit, ideally without scroll. Three asks max per digest; if more, the rest spill into a "+5 more" expander.
- Yes/No buttons are large (>= 44pt touch targets, Apple HIG floor). Snooze re-queues to the next digest.
- Done section is collapsed by default if >3 items.
- Tap any item to expand to full detail (the matter context, the source of the action, the recent transcript excerpt). This is the audit surface, not the primary surface.

The same digest renders in the Mac popover when clicked from a filled-amber tray icon.

## 7. Failure modes

The user has the phone on silent, earbuds out, in a meeting on calendar, pendant on. The agent has a confirm-before that has a hard deadline inside the meeting (rare but real).

The escalation:

1. Pendant: single short LED amber pulse, no haptic. If the user happens to glance at their chest, they see it.
2. Wait 15 seconds. No earbud, so no TTS attempt.
3. If the deadline is <2 minutes away and the action has irreversible-money or hard-commitment risk, fire one phone vibrate pulse (the OS will buzz even on silent for designated apps with critical-alert entitlement). This is the only case where the agent actively breaks "silent" mode.
4. If the user never responds and the deadline passes, the action defaults to deny and the feed records "I had to skip this because I could not reach you, here is the context."

If the user has phone off + pendant off + no earbud, the agent can do nothing. All asks queue. On next interaction (phone unlock, pendant connect, popover open), all queued asks render as a catch-up digest with a clear header: "Here is what I held while you were unreachable (1h 47m)."

If the calendar adapter is unreachable, the agent falls back to ambient-detection only. If ambient detection is also unreachable (mic off), the agent treats every window as quiet (the conservative direction would be the reverse, but the user will report a chatty agent faster than they will report a silent one, and we already have user-side DND as the explicit override).

If the model broker is degraded and the trivia path is >5 seconds, the agent abandons the trivia for that utterance and writes it to the feed for next-time. Better silent than slow.

## 8. Open problems

- Apple Critical Alerts entitlement requires App Review approval. We need to apply, and we need a clear policy for when we use it (currently: irreversible-money + <2-minute deadline + user unreachable, period). Without the entitlement, point 3 of §7 fails on iOS.
- The 30-second default-deny window on confirm-before may be too short for a doctor mid-rounds. Calibrate per user role from the cold-start dossier (see thread 01).
- Earbud detection. iOS gives us "headphones connected" but not "headphones in ear" on AirPods unless we go through CoreBluetooth gymnastics. Worth the engineering or skip and fall back to phone push?
- Ambient meeting detection vs. private one-on-one. A two-person dinner with the spouse is detected as ambient_meeting today and would suppress the digest. Maybe whitelist a "private" calendar tag.
- LED visibility under shirt. Pendant LED needs to be bright enough to be useful but not so bright it pulses through fabric like a beacon. Hardware-side decision.
- TTS voice. Personalized vs. neutral, female default vs. user-chosen. Lean neutral-female for v1 (matches Donna brand).
- Cross-device coordination. If the user is wearing the pendant AND has the Mac popover open AND the phone unlocked, who delivers? Today nothing arbitrates. Proposal: pendant + Mac if Mac is the active foreground app; phone if it is the unlocked-and-recently-touched device; lockscreen otherwise. A small device-presence broker on the model server resolves it.
- Digest cadence in a chatty day. If the user has 9 meetings with 5-minute gaps, the digest never fires under the 10-minute floor. End-of-day catch-up needs a different surface (likely an evening "your day in 60 seconds" email).
