# Anticipy — UX / UI, Interaction & Copy Spec (the spec for DONE)

*Doc 2 of the delivery chain. The PRD says **what** and **why**; this says **what the user sees, in every state, with what words.** It exists to kill Anticipy's single most-cited defect — the "localhost dev-server feel" — by turning the synthesis's design language into **measurable, testable** flows, states, and verbatim strings.*

**Status of the surface this spec replaces (verified, not assumed):** the current web app is a dev console. It renders `Anticipy Owner Mode` as the H1 (`app/page.js:875`), tells the user `"Press Go to transcribe and create task cards"` (`app/page.js:836`), shows raw `status` / `disposition` / `goal_state` tags on cards (`app/page.js:290-291`), and renders connections as a pipe-delimited string `"Google Calendar | connected | api | calendar..."` (`app/page.js:20`). Its palette is light Inter on `#f5f4ef` (`app/globals.css:3-6`). **This spec is the redesign target, not a description of today.** Where the engine already does the right thing, this spec cites it so the surface inherits truth (e.g. the thin-data refusal copy `"No facts assembled. Nothing was invented."` already exists at `app/page.js:260`, sourced from `onboarding/profile_builder.py:77`; the warm call voice `Polly.Joanna-Neural` is already wired at `channels/call.py:52`).

**How to read a requirement.** Every rule below is written to be falsifiable. A spec line you cannot fail is slop; each one here has either a concrete value (hex, ms, word count) or a test phrased as "FAILS if…". The acceptance checklist in §6 is the gate.

---

## 1. Design language

The job of the visual system is to make the product *feel like a competent assistant you'd be upset to lose* (`ANTICIPY_DONE_VISION_2026-06-15.md:35`), and to do it by **restraint, not decoration**. The premium tell is empty space and one idea per screen — "brands confident enough to leave space empty signal they don't need to fill every pixel" (synthesis §design-language). The current console fails this by density; the fix is a *confidence* discipline encoded as tokens.

### 1.1 Color — the exact tokens

These are the only colors the product ships. (Source: synthesis design-language line; reconciled with the live site's understated-luxury mood at anticipy.ai.) The current `app/globals.css` light tokens are **replaced wholesale**.

| Token | Hex | Role | Where |
|---|---|---|---|
| `--ink` (charcoal) | `#0C0C0C` | The ground. Near-black, never pure `#000`. | App background, default surface |
| `--cream` | `#F5F0EB` | Primary text + the pulse. Warm off-white, never `#FFF`. | All body copy, the state orb |
| `--warm-gray` | `#6B635B` | Secondary text, timestamps, the "why" line. | Sub-labels, metadata, captions |
| `--act` (calm green) | `#5E8C6A` | A thing was handled. Used *once*, small. | Silent-act receipt dot |
| `--ask` (amber) | `#C9A24B` | One thing wants your yes. | The single Ask surface accent |
| `--blocked` (clay) | `#B5654A` | The only hard stop (money/2FA/login). | Handoff surface accent only |
| `--hairline` | `rgba(245,240,235,0.08)` | Dividers. Barely there. | Card edges, list separators |

**Rules (testable):**
- R1.1 — No pure black (`#000000`) and no pure white (`#FFFFFF`) anywhere. FAILS if either hex appears in shipped CSS.
- R1.2 — The three *status* colors (act/ask/blocked) appear **at most once per screen each**, and never as a filled background block — only as a ≤8px dot or a 1px left-border. FAILS if a status color fills >5% of any screen's pixels. (This is the anti-"colored status-tag console" rule; contrast `app/page.js:290`'s `tag` chips, which this kills.)
- R1.3 — Default screen is ≥80% `--ink` by area. Whitespace (ground) is the dominant element. FAILS if any default state has >20% non-background ink coverage.

### 1.2 Type

| Use | Face | Weight / size | Notes |
|---|---|---|---|
| The assistant's voice (headers, the one line per screen, digest header, ask line) | **DM Serif Display** | regular, 28–40px | Serif = the assistant *speaking*. This is the human register made visible. |
| Body, receipts, metadata, controls | **Inter** (or system humanist sans) | 15–17px body / 13px meta | Sans = neutral information. |
| Never used | monospace | — | **Banned.** Monospace is the dev-console tell. FAILS if any monospace font ships in the user-facing app. |

- R1.4 — Exactly **two** type families ship (one serif display, one sans). FAILS at three+.
- R1.5 — The serif is reserved for *Anticipy's own sentences* (its voice). Data the user supplied or that came from their accounts is set in sans. (Rationale: the serif/sans split is the surface encoding of "this is me talking" vs "this is your stuff.")
- R1.6 — Type scale is a real modular scale (e.g. 1.25 ratio), not arbitrary px. Line-height ≥1.5 on body. FAILS if more than 6 distinct font-sizes exist across the app.

### 1.3 Whitespace & layout — one moment per screen

- R1.7 — **One moment per screen.** Each screen has exactly one primary thing: one state word, OR one digest, OR one ask, OR one handoff. FAILS if a default (non-expanded) screen presents two competing primary actions. (Direct repudiation of the current page, which stacks ingest box + cards + loops + connections + glassbox simultaneously.)
- R1.8 — Content column max-width 560px, centered, with ≥15% viewport margin on each side at desktop. The product reads like a calm letter, not a dashboard.
- R1.9 — Vertical rhythm on an 8px grid. Generous: minimum 24px between distinct elements, 64px above the one primary moment.

### 1.4 Motion — physics, never linear

Motion carries the "premium" signal more than any static pixel: "linear motion is the enemy of premium-feeling animation… it looks robotic and cheap" (synthesis design-language).

- R1.10 — **No linear easing anywhere.** All transitions use ease-out or spring. FAILS if `linear` or `ease-in-out` with equal in/out appears on any user-visible transition.
- R1.11 — Things **settle in**, never blink. New cards/lines fade+rise (translateY 8px→0, opacity 0→1, 320–420ms, ease-out). FAILS if any content appears with 0ms or a hard cut.
- R1.12 — The state orb **breathes** (a slow scale/opacity pulse, ~2.5–4s period, sinusoidal), it does not spin and is not a spinner. FAILS if a determinate/indeterminate spinner appears anywhere.
- R1.13 — The "Thinking" reveal is *choreographed*: caught items surface **one at a time**, ~250ms apart, like an assistant reading your day back — not a list that pops in at once. FAILS if multiple caught items appear in the same frame.
- R1.14 — Motion respects `prefers-reduced-motion`: pulses become a static dim/bright, settles become instant-but-soft. FAILS if reduced-motion users get spinning/looping animation.

### 1.5 The single design principle that governs ties

> When in doubt, **do less and say it human.** Remove the element; if it can't be removed, shrink it; if it can't shrink, set it in plain human language; if even that fails, it belongs in the digest, not on the main surface.

---

## 2. The core screens + states

The app is **mostly invisible**. The user "puts it on and forgets it's there" (anticipy.ai, `synthesis:15`). So the screens are not a place you live — they are the few moments Anticipy needs to be *seen*: onboarding once, the ambient state when you glance, the ask when it needs you, the handoff when it's blocked, and the one digest at day's end.

### 2.1 Onboarding — including the THIN-DATA degraded path

**Normal path — "read me, don't interrogate me."** One question, one connect, one recap you can correct. (Source scene: `synthesis:13`.)

```
┌───────────────────────────────────────────────┐
│                                                │
│                                                │
│                                                │
│     Before I start listening —                 │   ← DM Serif, cream, ~34px
│     who am I helping?                           │
│                                                │
│                                                │
│            [  Connect Google  ]                 │   ← single control, cream outline
│                                                │
│        I read your calendar and the            │   ← warm-gray, 13px, the "why"
│        people you email most. Nothing           │
│        is shared. You can pause me anytime.     │
│                                                │
└───────────────────────────────────────────────┘
```

After connect, the loading state is a *human sentence*, never a percentage:

```
┌───────────────────────────────────────────────┐
│                                                │
│                  ◍                              │   ← the orb, breathing
│                                                │
│            Reading your week                    │   ← DM Serif, the ONE word/phrase
│                                                │
└───────────────────────────────────────────────┘
```

Then the **recap the user didn't ask for** — the identity moat made visible — rendered as correctable inference:

```
┌───────────────────────────────────────────────┐
│                                                │
│   Here's what I picked up:                      │   ← DM Serif header
│                                                │
│   • You talk to Dana most.                      │   ← sans (it's YOUR data), each
│   • Tuesdays are packed.                        │     line tappable to edit/remove
│   • You have two kids — pickup matters.          │
│                                                │
│   Fix anything that's off.                      │   ← warm-gray
│                                                │
│        [ Looks right — start listening ]        │
│                                                │
└───────────────────────────────────────────────┘
```

- R2.1 — Onboarding is **≤3 screens and ≤60 seconds** to "start listening" on a normal account. FAILS at 4+ screens or a form with >1 field.
- R2.2 — Every recap line is **editable and deletable** in place. The user can correct the inference before it's trusted. FAILS if the recap is read-only.
- R2.3 — Loading copy is a human present-tense sentence ("Reading your week"), **never** a percentage, a count, "Transcribing", or a progress bar. FAILS on any numeric progress indicator.

**THIN-DATA degraded path — the refusal to fabricate.** If the scrape returns too little to support a confident recap (no browser arm available, a sparse calendar, reads that come back `low`-confidence / `needs_cross_check` — the trust tiers from `onboarding/profile_builder.py:97-105,250,269`), Anticipy **must not invent a picture.** It says so, plainly, and still lets the user proceed. The exact refusal copy already lives in the codebase and must be the surface string:

```
┌───────────────────────────────────────────────┐
│                                                │
│   I didn't find enough to know you yet.         │   ← DM Serif header
│                                                │
│   No facts assembled. Nothing was invented.     │   ← VERBATIM, app/page.js:260
│                                                │
│   I'll learn you by listening instead —         │   ← warm-gray, sets expectation
│   the picture fills in as your day goes.        │
│                                                │
│        [  Start listening anyway  ]             │
│                                                │
└───────────────────────────────────────────────┘
```

- R2.4 — When the scrape is thin, the recap shows **zero fabricated facts** and surfaces the verbatim line `"No facts assembled. Nothing was invented."` FAILS if a single inferred fact appears that is not backed by a real read with confidence ≥ medium (`profile_builder.py` trust tier). This is the onboarding-side expression of the cardinal-sin discipline: *the product would rather admit it doesn't know you than pretend.*
- R2.5 — A *partial* scrape shows only the facts that cleared the confidence floor, plus a one-line "still getting to know you" note for the rest — never pads to look complete. FAILS if low-confidence facts are shown without a visible "needs check" treatment.

### 2.2 The always-on states — Listening / Thinking / Acting / Resting

The ambient screen is **one centered breathing orb and one word.** Nothing else. (Source: `synthesis:39`.) This is the screen the user sees on a glance; it must read as calm presence, not a running process.

```
        ┌─────────────────────────┐
        │                         │
        │                         │
        │           ◍             │   ← orb, --cream, breathing pulse
        │                         │
        │       Listening         │   ← DM Serif, ~28px, --cream
        │                         │
        │                         │
        │      ⏸ pause            │   ← warm-gray, tiny, always reachable
        │                         │
        └─────────────────────────┘
```

| State | Word | Orb behavior | Meaning to user | Maps to engine |
|---|---|---|---|---|
| **Listening** | `Listening` | slow steady breath (~3.5s) | ambient capture is on; consent is visible | `/listen/status` active (`main.py:818`) |
| **Thinking** | `Thinking` | breath quickens slightly (~2.2s), no spin | a candidate is being weighed (triage→decider→harm) | `proactive/` pipeline running |
| **Acting** | `Acting` | a single soft expansion, then settle | a silent act is being executed (calendar held, draft prepared) | a SILENT-act executing |
| **Resting** | `Resting` | very slow dim breath (~5s) | paused, or quiet hours; not capturing | `/listen/stop` (`main.py:806`) or pause |

- R2.6 — The ambient screen shows **exactly one** of these four words at a time, plus the orb, plus the pause affordance. Nothing else. FAILS if a card, count, log, or second control appears on the ambient screen.
- R2.7 — **Consent is always visible and one-tap reversible.** When Listening, the indicator is unmistakably "on"; tapping pause moves to Resting and the user can *see* it is off (the orb dims, the word changes). FAILS if pause state is ambiguous or buried >1 tap. (Repudiates Bee's "red = muted, default-on invisible recording" anti-pattern, `synthesis:87`.)
- R2.8 — There is **no visible "Acting" with a spinner and a percent.** Acting is a settle, then back to Listening. The proof of the act lives in the digest/receipt, not in a live progress UI.

### 2.3 The end-of-day digest — the one calm report

One screen, once a day, default ~6:30pm: *"Here's what I handled and what's waiting on you."* (Source scene `synthesis:25`.) Silent acts are a quiet list (read-back receipts, not interruptions); the one thing needing a yes is the single accented row.

```
┌───────────────────────────────────────────────┐
│  Tuesday, June 17                               │   ← warm-gray date
│                                                │
│  Here's what I caught today.                    │   ← DM Serif, ~30px, the header
│                                                │
│  Handled                                        │   ← sans label, warm-gray
│  ● Held 3:00 pickup on your calendar            │   ← act-green dot, the real artifact
│  ● Prepared a note to Dana (not sent)           │   ← shows it's PARKED, not fired
│  ● Remembered: pharmacy closes Fri 6pm          │
│                                                │
│  Waiting for your yes                           │   ← amber label
│  │ Pick up Mom's prescription before Fri 6pm.   │   ← amber 1px left-border, ONE row
│  │ Want me to set a Thursday reminder?          │
│  │            [ Yes ]      [ Not now ]           │
│                                                │
│  Nothing else needed you today.                 │   ← warm-gray, the calm close
└───────────────────────────────────────────────┘
```

- R2.9 — **One digest per day** by default. FAILS if the product sends >1 scheduled digest/day without the user opting in.
- R2.10 — Each "Handled" line shows the **real artifact or its faithful description** (the actual held calendar slot, "prepared a note… not sent"), never a hollow `done`/`✓`. Prepared-not-sent items explicitly say they were **not** sent/spent. FAILS if a receipt implies an irreversible action that did not occur. (This is the surface side of prepare-then-park, `CONSTITUTION.md:59-67`.)
- R2.11 — At most **one** "waiting for your yes" row is given the amber treatment per digest; additional pending items queue below, plainly, without competing accent. FAILS if the digest shows 2+ amber/urgent rows screaming at once.
- R2.12 — A quiet day shows the close line ("Nothing else needed you today.") rather than padding the digest. FAILS if an empty digest invents filler.

### 2.4 The confirm / ask surface (real-time, budgeted)

When something **touches another person, is hard to reverse, or is medium-confidence on a real obligation**, Anticipy may *interrupt* — but rarely (budget below), and always with a preview and a plain reason.

```
┌───────────────────────────────────────────────┐
│                                                │
│   Quick one.                                    │   ← DM Serif
│                                                │
│   School moved pickup to 3:00.                  │   ← the WHY, first (sans)
│   Want me to set a 2:45 reminder call?          │   ← the ask (serif), one sentence
│                                                │
│        [ Yes ]        [ No ]                    │
│                                                │
│        not now ↩                                │   ← defer, never a dead-end
│                                                │
└───────────────────────────────────────────────┘
```

- R2.13 — Every ask states the **reason ("because…") before the request.** FAILS if an ask appears with no surfaced cause. (Exposing the why is what prevents over- and under-trust, `synthesis:83`.)
- R2.14 — An ask offers **Yes / No / Not now** — never a dead-end yes-only. FAILS if a defer path is missing.
- R2.15 — Real-time asks are **rate-limited to the interrupt budget** (§3.4). A candidate that doesn't clear the bar becomes a *digest line*, not an interrupt. FAILS if the app interrupts for a low-P(act) item.

### 2.5 The "needs you" / blocked-handoff surface (the only hard stop)

Money, captcha, 2FA, or a login wall → **BLOCKED**, handed back as the smallest next step. This is the one place the clay color appears. (Source: the only hard stop, `CONSTITUTION.md:35`, `OWNER_ACTION_ENGINE.md:38`; engine gate at `actions/`.)

```
┌───────────────────────────────────────────────┐
│                                                │
│   I got it all the way to the last step.        │   ← DM Serif — "prepared, parked"
│                                                │
│   │ The flight is held in your cart.            │   ← clay 1px border
│   │ Paying is yours — I won't spend for you.    │   ← the hard stop, plainly
│                                                │
│        [ Open the cart to pay ]                 │   ← hands back the smallest step
│                                                │
│   Nothing was bought.                           │   ← warm-gray reassurance
│                                                │
└───────────────────────────────────────────────┘
```

- R2.16 — A blocked item **always says what was already done** (prepared/held) and **what remains yours** (pay / verify / log in), and hands back the *single smallest* next action. FAILS if a block reads as a dead error or hides what's done.
- R2.17 — The handoff **never** auto-spends, auto-2FAs, or auto-logs-in. FAILS on any auto-execution past the money/auth edge. (This holds even when the browser arm is on a hostile page — untrusted page text can never escalate to crossing this edge, `synthesis:97`.)
- R2.18 — Blocked copy is reassuring and concrete ("Nothing was bought."), never a status code or stack trace.

### 2.6 The ledger (proof-of-action = privacy log, one surface)

A single, user-readable, user-deletable list that is **both** the receipt log (what Anticipy did) **and** the privacy log (what it heard/stored). (Source: `synthesis:87` — "anti-spam and anti-creep are the same system run on outputs vs. inputs.") This is *not* the main surface; it's reachable, plain, and honest. It replaces the current `/glassbox` raw-events dump (`main.py:1140`) with human rows.

- R2.19 — Every silent act and every stored fact has exactly one ledger row, in human language, with a delete control. FAILS if any action or stored fact is invisible to the user, or if a row shows raw JSON/IDs (cf. current `ask.ask_id.slice(0,6)` at `app/page.js:319`).

---

## 3. Key flows (step by step)

### 3.1 First 60 seconds (onboarding)

1. Open → near-black screen, one serif line: *"Before I start listening — who am I helping?"* (orb idle).
2. Tap **Connect Google** → standard OAuth (Anticipy's own chrome around it; no raw consent-screen jargon leaks into our copy).
3. Return → orb breathes, **"Reading your week"** (no percent). Engine scrapes calendar + top contacts + recent threads (`onboarding/connection_scan.py`, `profile_builder.py`).
4. **Branch:**
   - *Enough data* → recap screen (§2.1), each line editable. User taps **"Looks right — start listening."**
   - *Thin data* → refusal screen (§2.1), verbatim *"No facts assembled. Nothing was invented."* User taps **"Start listening anyway."**
5. → Ambient **Listening** state. Done. (Target: ≤60s, ≤3 screens, ≤1 input field.)

**Acceptance:** a stopwatch from app-open to "Listening" is ≤60s on a seeded normal account; the thin-data seed produces zero fabricated recap facts.

### 3.2 A catch → the digest (the 9:14am moment)

1. User, on a call with their sister, says *"…I still have to get Mom's prescription before the pharmacy closes Friday."* App is in **Listening**; user does not open it.
2. Engine: capture → triage (survives as a candidate, not an explicit command) → decider → harm. The implied obligation is caught; because it touches no other person and is reversible, it routes **SILENT-act / hold** with a pending "want a reminder?" — **not** a real-time interrupt (it's not urgent now).
3. Orb briefly → **Thinking** → back to **Listening**. No ping. The user's day is uninterrupted.
4. At ~6:30pm, the **one digest** carries the line: *"Caught: pick up Mom's prescription before Fri 6pm. Want me to set a Thursday reminder?"* with **Yes / Not now**.

**Acceptance:** the buried obligation appears in the digest, never as a mid-day interrupt; the digest line names *what* and *by when* and offers a yes — it does not silently create the reminder without the yes (because a reminder is fine to prepare, but the user's preference for *being reminded* is a one-tap confirm, not an assumption).

### 3.3 An ask → your yes → done

1. Condition that *does* warrant a real-time ask (touches a person / time-critical): e.g. *"can you grab the kids at 3?"* heard at 11am with a hard 3:00 deadline.
2. Engine routes **ASK** (or, if confidence is high and it's reversible, prepares silently and confirms with one line). Interrupt budget checked (§3.4).
3. Ask surface (§2.4): *"School moved pickup to 3:00. Want me to set a 2:45 reminder call?"* → **Yes**.
4. One tight confirmation line, then silence: **"Got it. I'll call you at 2:45 so you're not late."** (verbatim, §4). No "Task completed ✓."
5. Calendar event made + reminder armed (real artifacts; read-back is the proof). The item also appears in that evening's digest "Handled."

**Acceptance:** the yes produces a real calendar artifact and an armed reminder, exactly one confirmation line, and no celebratory/robotic confirmation copy.

### 3.4 The interrupt budget governing 3.2/3.3 (cadence as visible state)

- Default **3 real-time interrupts/day**, hard ceiling **5** (research-anchored; engine default `max_per_day=5` at `proactive/budget.py:42-43`, with the boot/window `InterruptGuard` backstop at `budget.py:78-99` born from the 6-SMS-in-36s cold-boot bug).
- Silent acts and the daily digest **do not** draw from this budget.
- When the budget is spent, a new candidate must **displace** a lower-priority queued one (honest priority comparison), never stack.
- Non-urgent asks are **held to a breakpoint** (end of call/conversation, a speech pause) before release; a hard deadline (the 2:45 call) overrides breakpoints.

**Acceptance:** in a seeded noisy day, real-time interrupts ≤5; everything else lands in the digest; `dismiss-rate` is tracked as a health metric.

### 3.5 The 2:45 call (the canonical scene, end-to-end)

1. At capture (step 3.3): one line set the expectation — *"I'll call you at 2:45."*
2. At **2:45pm sharp**, the user's phone **rings** (Twilio call, `channels/call.py`). It ignores breakpoints — the hard deadline wins.
3. The voice is **warm Polly.Joanna-Neural** (`channels/call.py:52`), not the robotic default. It speaks ~15 words, delivers the reminder, and **hangs up.** It does not chat, does not loop, does not ask the user to "press 1."
4. The act is logged to the ledger and reflected in the evening digest.

**Acceptance:** the call actually rings at 2:45 (`HANDOUT:45-48` bar), uses the neural voice (not `<Say>` default), says the spec string in §4, and terminates itself.

---

## 4. The VOICE / COPY spec (verbatim strings)

**Register:** Anticipy speaks like a calm, competent person who already read the file — Donna, not a chatbot. Plain sentences, the *why* before the *what*, under-confirm the routine, confirm the consequential with care. Assistant voice always: *"Here's what I caught today,"* never *"2 tasks ingested."*

### 4.1 The 2:45 call — the exact words (then it hangs up)

> **"Hi, it's Anticipy. Quick reminder — pickup is at three today, so head out around two forty-five. That's all. Talk soon."**

- 20 words spoken (target ~15–22; one breath of greeting, the reminder with its *why*-anchor, a clean close). The `{time}`/`{task}` are slotted from the event.
- Spoken in `Polly.Joanna-Neural` (`channels/call.py:52`). The call ends after this line — **no menu, no "press 1", no follow-up question.** (If two-way is enabled via ConversationRelay, `channels/call.py:56-87`, the same opener is the greeting, but the default and fallback is speak-and-hang-up.)
- FAILS if: the call says a port/URL/ID, reads more than ~25 words, asks the user to interact to dismiss, or uses the robotic default voice.

**Template:** `"Hi, it's Anticipy. Quick reminder — {task} is at {time} today, so {lead_action} around {remind_time}. That's all. Talk soon."`

### 4.2 The capture-moment confirmation (one tight line)

> **"Got it. I'll call you at 2:45 so you're not late."**

- One sentence, sets the expectation, names the time. No checkmark, no "Task completed", no "Successfully created event."

### 4.3 The digest header

> **"Here's what I caught today."**  *(serif, with the date in warm-gray above it)*

- Alternates allowed for tone, all assistant-voiced: *"Here's what I handled and what's waiting on you."* / *"Quiet day — here's the short version."*
- FAILS if the header says "Digest", "Summary", "Report 2026-06-17", a count ("3 items"), or any system noun.

### 4.4 The ask line

> **"School moved pickup to 3:00. Want me to set a 2:45 reminder call?"**

- Pattern: **`{reason}. Want me to {action}?`** — the *why* first, then a single yes/no request. Options are **Yes / No / Not now.**
- FAILS if an ask leads with the action and hides the reason, or offers no defer.

### 4.5 The thin-data line (the refusal to fabricate)

> **"No facts assembled. Nothing was invented."**  *(verbatim — already in `app/page.js:260`, sourced from `profile_builder.py:77`)*

- Followed by: *"I'll learn you by listening instead — the picture fills in as your day goes."*
- FAILS if onboarding ever pads thin data with an unsourced fact.

### 4.6 The blocked / money line

> **"I got it all the way to the last step. The flight is held in your cart — paying is yours, I won't spend for you. Nothing was bought."**

- Pattern: `{what's done}. {what's yours}. {reassurance that nothing irreversible happened}.`

### 4.7 The error line (never a stack trace)

> **"I lost the thread for a moment. Try again."**  *(`synthesis:41`)*

- FAILS if the user ever sees an exception, status code, traceback, or `null`/`undefined`.

### 4.8 BANNED visible strings (the anti-localhost wordlist)

The product **never** shows the user any of:

| Banned | Because | Say instead |
|---|---|---|
| `Ingest` / `Press Go` | codebase verb; dev-console tell (live today at `app/page.js:836`) | *(nothing — capture is ambient)* or "Start listening" |
| `Owner Mode` / `Owner` | internal role label (live at `app/page.js:875`) | the user's name, or nothing |
| `localhost`, `:8787`, `:3000`, any port | dev artifact | *(never shown)* |
| JSON, `{...}`, raw IDs, `ask_id.slice(0,6)` (`app/page.js:319`) | machine noise | a human sentence |
| model/vendor names (Claude, GPT, Polly, Twilio, Arcade) | implementation leak | *(never shown)* |
| `status` / `disposition` / `goal_state` / `ACT`/`ASK`/`SILENT` tags (`app/page.js:290`) | engine internals | "Handled" / "Waiting for your yes" / "Held" |
| `done` / `✓ Task completed` / "Successfully…" | robotic confirmation | the real artifact, or under-confirm |
| `Transcribing 71%`, progress bars, spinners, percentages | process exposure | "Reading your week" / "Thinking" |
| stack traces, `Error:`, `null`, `undefined`, HTTP codes | failure leak | "I lost the thread for a moment." |
| `connected | api | calendar` pipe strings (`app/page.js:20`) | raw data dump | "Calendar — connected." |

- R4.1 — A grep of the rendered DOM for the banned-strings list returns **zero** matches in any user-facing state. This is a CI-able test. FAILS on any hit.

---

## 5. What makes it feel premium vs. a dev tool (the explicit anti-localhost requirement)

The "dev-server smell" is a **confidence/restraint problem expressed in a thousand small surface decisions** (density, monospace, codebase-verbs, raw status tags), *not* a deploy problem. The domain is the last 5%; the 95% is the discipline below. (Source: `synthesis:89-91`.)

| Dev-tool tell (some live in the app today) | Premium replacement (the requirement) |
|---|---|
| Dense dashboard, many panels at once (`app/page.js` stacks ingest+cards+loops+connections+glassbox) | One moment per screen (R1.7); 560px column, 80%+ whitespace (R1.3, R1.8) |
| Monospace / code font | Banned; serif voice + sans data only (R1.4, banned-mono) |
| Raw status chips: `status`, `disposition`, `goal_state` (`app/page.js:290`) | Human labels: Handled / Waiting for your yes / Held (R1.2, §4.8) |
| Codebase verbs: "Ingest", "Press Go" (`app/page.js:836`) | Ambient capture — no button; "Start listening" at most (§4.8) |
| `Anticipy Owner Mode` H1 (`app/page.js:875`) | The user's name, or the assistant's one serif line (§4.8) |
| Pipe-delimited connection strings (`app/page.js:20`) | "Calendar — connected." sentences (§4.8) |
| Spinners, percentages, "Transcribing 71%" | Breathing orb + one human word (R1.12, R2.3) |
| Hard cuts, linear animation | Settle-in, ease-out/spring, choreographed reveal (R1.10–R1.13) |
| Light Inter on `#f5f4ef` (current `globals.css`) | Charcoal `#0C0C0C` / cream `#F5F0EB` / DM Serif (R1.1, §1.1–1.2) |
| Robotic confirmations ("Done", "✓") | Under-confirm routine; the real artifact is the receipt (R2.10) |
| Raw event/glassbox dump (`/glassbox`, `main.py:1140`) | The human ledger, deletable, one row per act/fact (R2.19) |
| Localhost URL, no domain | Real domain inheriting the anticipy.ai visual DNA (last 5%) |

**The single litmus for "premium" (testable):** show any screen to a stranger for 3 seconds and ask *"is this a finished product or an internal tool?"* — DONE means "finished product" with no further prompting. And the product-level litmus from the synthesis still rules: *you vent about quitting your job and nothing happens — and that evening it quietly surfaces the prescription you mentioned to someone else.* The surface's job is to make both of those moments **feel like a person who's got you**, never like a process that ran.

- R5.1 — Inheritance, not reinvention: the app uses the anticipy.ai palette/mood and introduces **no second, busier visual language** (`synthesis:42`). FAILS if the app's visual system diverges from the marketing site's restraint.
- R5.2 — Failure degrades to **silence**, never retry-and-ping (`synthesis:98`). A surface that can't render falls back to calm, not to an error spew or a notification storm. FAILS on any retry-loop that produces repeated user-visible pings.

---

## 6. Acceptance checklist (the gate)

A build satisfies this spec only when **all** of the following hold (each is falsifiable):

- [ ] **A1.** Palette is exactly §1.1; no `#000000`/`#FFFFFF`; status colors ≤ one small instance each per screen (R1.1–R1.3).
- [ ] **A2.** Two type families only (serif voice + sans data); no monospace anywhere (R1.4–R1.6).
- [ ] **A3.** Every default screen presents exactly one primary moment; 80%+ whitespace; 560px column (R1.7–R1.9).
- [ ] **A4.** No linear easing, no spinners; orb breathes; caught items reveal one-at-a-time; reduced-motion honored (R1.10–R1.14).
- [ ] **A5.** Onboarding ≤3 screens / ≤60s / ≤1 field; recap editable; loading is a human sentence (R2.1–R2.3).
- [ ] **A6.** Thin-data path shows zero fabricated facts and the verbatim "No facts assembled. Nothing was invented." (R2.4–R2.5).
- [ ] **A7.** Ambient screen = one of {Listening, Thinking, Acting, Resting} + orb + pause; consent visibly reversible in one tap (R2.6–R2.8).
- [ ] **A8.** One digest/day; receipts show real artifacts; prepared-not-sent says so; ≤1 amber row; quiet day says so (R2.9–R2.12).
- [ ] **A9.** Asks state the why first, offer Yes/No/Not now, and respect the interrupt budget (R2.13–R2.15).
- [ ] **A10.** Blocked surface names what's done + what's yours, hands back the smallest step, never auto-spends/auth (R2.16–R2.18).
- [ ] **A11.** Single human ledger; no raw JSON/IDs; every act and stored fact is visible and deletable (R2.19).
- [ ] **A12.** The 2:45 call rings on time, ~15–22 words in Polly.Joanna-Neural, then hangs up; says §4.1 (R §4.1).
- [ ] **A13.** Verbatim strings §4.2–§4.7 used at their moments.
- [ ] **A14.** Banned-strings grep over rendered DOM returns zero hits (R4.1).
- [ ] **A15.** Stranger 3-second test reads "finished product"; failure degrades to silence (R5.1–R5.2).

---

*Grounding: `ANTICIPY_DONE_VISION_2026-06-15.md` (synthesis — palette §1.1, states §2.2, the four scenes §3, copy rules §4, anti-localhost §5); `app/page.js` & `app/globals.css` (the dev-console surface this replaces, cited line-by-line); `engine/anticipy_engine/channels/call.py:52` (Polly.Joanna-Neural, the warm voice — real); `proactive/budget.py:42-43,78-99` (interrupt budget + InterruptGuard — real); `proactive/harm.py:276` (0.66 send floor — real); `onboarding/profile_builder.py:77,97-105` (no-invented-facts trust tiers — real); the deployed pitch at anticipy.ai ("Vibe your life." / "It heard you. It's handled." / "You put it on. You forget it's there."). What is NOT yet built and this spec specifies as target: the charcoal/serif premium shell, the four-state ambient screen, the one-per-day digest surface, the visible interrupt-budget cadence, and the banned-strings CI gate.*
