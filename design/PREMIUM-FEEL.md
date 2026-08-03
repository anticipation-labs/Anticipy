# ANTICIPY — PREMIUM FEEL: RESEARCH + DESIGN PLAN (2026-08-03)

Omar's brief, verbatim spirit: "it should be over animated, over hapticated…
you should want to use the app, it should feel blissful, it should feel
beautiful… it is very simply the art of psychology." This document is the
research distilled into concrete build items. Everything here applies to the
iOS app first; the same principles govern the setup guide page and extension
popup.

## 1. THE PSYCHOLOGY (why each item works)

1. **The labor illusion** (Buell/Norton, Harvard): people trust and value a
   service MORE when they can see it working. A instant blank answer feels
   cheap; "she's typing…" then words appearing feels like a person thinking.
   → Her messages must TYPE OUT character-by-character (fast, ~30-45 cps, with
   a blinking cursor), never appear as a block. Feed items should slide in.
2. **Peak-end rule** (Kahneman): people judge an experience by its peak moment
   and its end. → Invest disproportionately in (a) the pairing-success moment,
   (b) onboarding completion, (c) a task completing. These get the full
   celebration: success haptic + spring scale-in + champagne glow.
3. **Perceived responsiveness**: every touch must acknowledge within 100 ms —
   even if the work takes seconds. → Every tappable element gets a pressed
   state (scale 0.97 + light haptic) and an immediate visual response;
   long work shows her "working" state, never a frozen screen.
4. **Variable reward / aliveness** (Eyal, Hooked): subtle motion makes a
   product feel alive. → The logo dot breathes (slow 3s pulse) when she's
   listening; the feed is never static while she works.
5. **Haptic grammar** (Apple HIG): haptics must be a consistent language, not
   noise — light = touch, medium = commitment, success/warning = outcome,
   plus CUSTOM CoreHaptics patterns for signature moments (pairing = two soft
   rising taps; task done = crisp double-tap "tada"). Never haptic-spam
   scrolling.
6. **Doherty threshold** (<400 ms) + **animation duration law**: transitions
   200-350 ms with spring easing (response 0.35, damping 0.8) read as premium;
   >500 ms reads as sluggish, <150 ms as jumpy.
7. **De-AI-ing the look**: what reads "AI-built" is: uniform card grids, evenly
   spaced SF symbols, default system spacing, centered-everything, generic
   copy. What reads designed: a real type scale (display serif used with
   intention at 2-3 sizes only), asymmetric layouts, one signature accent
   used sparingly (champagne), custom iconography for the 3-4 core concepts,
   generous whitespace, and motion with personality (one signature curve
   reused everywhere).
8. **Trust through modesty in permissions** (onboarding scrape): ask AFTER
   demonstrating value, frame as her curiosity not data collection, show a
   live narrated log of what she's reading, make "skip" a first-class equal
   button, and promise what she will NOT do ("I never send anything; I only
   read"). One toggle per source, preselected off.

## 2. BUILD ITEMS — APP-WIDE SYSTEM

- `Theme.swift` grows into a full design system:
  - Motion: `Theme.spring` (one signature spring), `Theme.springSlow`,
    standard durations; every `withAnimation` in the app uses these.
  - `PressableStyle` ButtonStyle: scale 0.97 + opacity + `Haptics.tap()` on
    press — applied to EVERY button.
  - Haptics vocabulary extended with CoreHaptics signature patterns:
    `Haptics.pairing()`, `Haptics.taskDone()`, `Haptics.herMessage()` (one
    soft tick as her typing starts).
- `TypewriterText` view: types her words in at ~35 cps with a champagne
  cursor, `Haptics.herMessage()` at start, skippable by tap.
- `BreathingDot`: the champagne dot in the logo pulses slowly whenever she is
  listening/working — the app's heartbeat.
- Feed rows: slide+fade insertion, spring; status changes crossfade; the
  "done" state gets the celebration treatment once (not on re-render).

## 3. ONBOARDING REWORK (page by page)

Overall: it becomes HER talking — every page's headline types out as if she's
introducing herself. Progress dots stay. Every "Continue" is a commitment →
medium haptic + page spring-slide.

1. **Welcome**: logo draws itself in (stroke animation), dot drops in with a
   soft haptic, THEN "Anticipy" fades up, then her line types: "I'm Anticipy.
   I listen, I remember what matters, and I quietly do the work."
2. **How it works**: cards cascade in staggered (80 ms apart), icons get a
   one-time micro-bounce.
3. **Your number**: keep the copy warmth; number field auto-formats as you
   type (spaces/dashes), checkmark morphs in when valid + light haptic; on
   save, success haptic.
4. **Pair your pendant**: honest state — if no pendant hardware exists yet,
   this page is "Your pendant finds you later" with the breathing logo and a
   real skip; when scanning, radar ripple animation (repeating, not the
   current one-shot); on connect: signature pairing haptic + ring lights up
   champagne.
5. **Browser agent**: biggest rethink — see §4.
6. **Transcription choice**: reword "Where should words become text?" →
   "Who turns your voice into words?"; options as two tactile cards, chosen
   card lifts (shadow + border glow) with medium haptic. Fix the flat look.
7. **NEW final page — "Want me to actually know you?" (the life scrape)**:
   see §5. Then completion: full celebration, her line types "Give me a day.
   You'll see." → button "Start living your day".

## 4. BROWSER AGENT PAIRING (consumer-grade rethink)

Chrome Web Store reality (researched): $5 one-time dev fee; review is human +
automated, typically 1-3 days, LONGER for extensions requesting `debugger`
(ours does — it's how she clicks). Not one-click, but worth doing once UI is
stable: auto-updates alone justify it. Until then, load-unpacked stays but the
experience gets redesigned:

- The app page becomes a live status page: "waiting for your computer…" with
  breathing dot → the moment the extension registers, the phone VIBRATES
  (signature pairing haptic) and shows the code entry pre-focused → on pair:
  celebration + "Your browser is mine now. In a good way."
- The setup.html page gets the same brand treatment (serif display, ink/
  champagne, numbered steps with screenshots/gifs, a copy-code button) — it
  currently reads like a README.
- Store package prepared in `extension/store/`: 128px icon, screenshots,
  privacy-policy page, listing copy — so store submission is one upload when
  Omar says go.

## 5. THE LIFE SCRAPE (onboarding intelligence, works WITH the memory graph)

Goal: after pairing, she offers to learn who you are from your own logged-in
browser. Never sends anything; read-only; everything lands in the memory
graph as provenance-tagged facts.

- **Round 1 — mail**: open major mail providers (Gmail/Outlook/iCloud/Yahoo);
  whichever is logged in stays, others close instantly. Read recent
  threads/subjects: who you talk to, what's ongoing, commitments in flight.
- **Round 2 — professional**: LinkedIn (+ whatever round 1 revealed): role,
  company, field. From the field, infer the tools of that trade.
- **Round 3 — tools of the trade**: open the CRMs/systems common to that
  field (plus generalist ones); the logged-in ones are read for deals,
  clients, pipeline, cadence.
- **Rounds 4+ — unscripted deep research**: a generalist prompt takes over:
  "given everything learned so far, what would you open next to understand
  this person's life?" — the browser agent already runs open-ended goals;
  this is a special job kind (`life_scrape_round`) with a budget of pages
  and a hard read-only rule (no typing into forms, no sending, no buying).
- UX on the phone: one page, her voice: "Want me to actually know you?" +
  per-source toggles (Mail / LinkedIn / Work tools / Deep dive), a live
  narrated feed while she reads ("reading your last 50 subject lines… you
  and Marcus have something in flight"), skippable at every moment, and a
  standing promise line: "I read. I never send. Ever."
- Backend: a `life_scrape` orchestrator in the brain queues rounds as jobs;
  extracted facts go through the existing memory extractor with source
  provenance; a summary card lands in the feed and she texts one insight as
  the payoff moment.

## 6. WHAT READS "AI-BUILT" TODAY (specific fixes)

- Same card component repeated everywhere → introduce hierarchy: hero
  moments (pairing, listening) get bespoke layouts, not cards.
- SF Symbols for core concepts → custom-draw the four core glyphs (listen /
  remember / act / confirm) from the logo's pill-and-dot DNA.
- Static screens → the breathing dot + typed text give every screen life.
- Copy is good (keep the voice) but presentation is uniform — vary rhythm:
  some pages one big line, some a cascade.
- Color: keep ink/ivory/champagne (Omar: don't leave brand colors), but add
  depth: subtle champagne radial glow behind hero elements, 2% noise texture
  on ink backgrounds, elevated cards get real shadows (currently flat).

## 7. ORDER OF WORK

1. Design system: motion + PressableStyle + haptic vocabulary + Typewriter +
   BreathingDot (foundation everything else uses).
2. Onboarding rework (pages 1-6 + browser pairing rethink).
3. Main app feed + Listen screen polish (same system).
4. setup.html brand pass + store package.
5. Life-scrape: brain orchestrator + extension read-only mode + onboarding
   page + narrated feed.
6. New TestFlight build after each coherent stage; Omar feels it on-device.
