<!-- CANON v1 · written 2026-07-02 by the HoE agent · Omar's UI flow, captured verbatim so it is
     NEVER re-explained. On conflict about screens/flow/feel, THIS wins. Fix here, never fork. -->

# CANON/UI_FLOW — the one true flow (Omar's words, captured)

Omar has described this many times. It is captured here so it is loaded every session and never
re-explained. The current 13-screen app is **too cluttered, too much per page, and does not feel
5-year-old-simple** — that is the problem this flow fixes. KEEP the app; reskin + re-sequence it.

## The flow (in order)
1. **Welcome** — dead simple. One line + one button. *"Hi, I'm Anticipy. I listen to your day and quietly handle the small stuff. I draft — you approve."*
2. **Sign in.**
3. **Setup** — walk them through **downloading the app + the Chrome extension.** The DOWNLOAD lives HERE (not bolted on at the end as a separate `/download` screen).
4. **Connect accounts** — early, right after setup. One "Allow" over the list of sites, not per-service toggles.
5. **Onboarding** — the **4-layer scrape ⇄ phone-call loop** (reads your real accounts, calls you, deepens each layer). This IS the "scrape-you" aha.
6. **Main screen** (rename "board" — the word is bad) — **ONE input, one place: talk / type / drop an MP3.** Not separate `/mp3` and `/go-to`. One button. Then the cards.
7. **Settings** — advanced: manage **what each connected app is allowed to do**, manage **memory**, the detailed controls.

## KILL (redundant / confusing screens)
- **"great"** (`/great`) — pointless screen after onboarding. Remove.
- **standalone "done"** (`/done`) — redundant. Fold into the flow.
- **"go-to"** (`/go-to`) — merge into the one main input.
- **separate `/download`** — move into Setup (#3).

## The laws (5-year-old-simple + Wispr-hooky)
- **One primary action per screen.** Zero jargon (NO source tags like `ST-NO-FAKE-DONE`, no "gateway", no model names, no ports).
- **Recognition over recall** — restate what it heard; never make them remember.
- **The main screen collapses to one calm focus** — a pulsing orb + one word (Listening / Thinking / Acting / Resting). Everything else behind `?debug=1`.
- **The hook** = onboarding's guaranteed first win: it reads your week and tells you something you didn't ask for.
- **Full buy-in / "Coming soon":** show the WHOLE vision — every capability as a real button (voice, do-it-on-the-web, deep-scrape, digest, remembered-review) — with a small **"Coming soon"** tag on the ones not wired yet. Feels complete + honest; turns the 35 unwired seams into a visible roadmap.

## Reference feel
Charcoal/cream/gold, DM Serif Display, editorial calm, motion/physics, one-thing-per-screen.
(Full per-screen copy + psychology in CANON/THE_MAP.md §3.)
