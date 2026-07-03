# Anticipy UI — Screen-by-Screen Implementation Spec

Base: `/Users/omarebrahim/Anticipy-devin`, branch `hoe/build`. Every route is `app/<route>/page.js` → `<PhaseZeroApp screen="…" />`, except two standalone pages (`connect/page.js`, `download/page.js`) that render outside `AppShell`. Central file: `app/phase-zero/PhaseZeroApp.js` (1974 lines). Data/config: `app/phase-zero/sourceData.js`. Styles: `app/globals.css`. This spec reskins + re-sequences the existing app; it does not rebuild it. Line anchors are current-state; they shift as edits land — match on component/string, not the number.

---

## The target flow (final screen list + order)

| # | Screen | Route | `screen` prop | Component | Note |
|---|---|---|---|---|---|
| 1 | Welcome | `/welcome` | `welcome` | `WelcomeScreen` | RESKIN + unwrap from `AppShell` |
| 2 | Sign in | `/sign` | `sign` | `SignScreen` | KEEP, strip jargon |
| 3 | Setup | `/setup` | `setup` | `SetupScreen` | **MERGE-IN** `/download` |
| 4 | Connect | `/connect` | (standalone) | `ConnectPage` | **WIRE IN** (currently orphaned) |
| 5 | Onboarding | `/onboarding/2…8` | `onboarding-*` | `OnboardingScreen` | KEEP (the aha); **absorbs `/great`**; ends by POST-complete → `/` |
| 6 | Main | `/` | `board` | `MainScreen` (renamed from `BoardScreen`) | **MERGE-IN** `/mp3` + `/go-to`; collapse to one orb + one input |
| 7 | Settings | `/settings` | `settings` | `SettingsScreen` | **MERGE-IN** `/memory` as advanced |

**DELETED (route dir + component + render-switch branch + nav entries):**
- `/great` → `GreatScreen` — its confirm-mirror + `POST /api/onboard/complete` (PhaseZeroApp.js:808) move into the onboarding final stage. Nothing else survives.
- `/done` → `DoneScreen` — redundant; onboarding routes straight to `/`.
- `/go-to` → `GoToScreen` — review cards move onto Main.
- `/mp3` → `Mp3Screen` — file upload becomes a mode of Main's one input.
- `/download` → `DownloadPage` (standalone) — extension download folds into Setup; the `git clone / pip / uvicorn` Quick Start block is deleted outright.

**MERGED:** `mp3 + go-to → Main` (one input + cards); `download → Setup`; `memory → Settings` (advanced, minus `ContextPackInspector`); `great → Onboarding final stage`.

**Render switch to edit** (PhaseZeroApp.js:1955–1966): delete the `great`, `done`, `mp3`, `go-to` branches; keep `welcome/sign/setup/onboarding*/memory→settings/board`. Welcome must return **without** `AppShell` (see below).

---

## Per screen: the build

Global (applies to all, do first — see Build order step 1):
- **Tokens:** `globals.css:34` `--serif: "Fraunces"…` → `--serif: "DM Serif Display", Georgia, serif` (add via `next/font` in `app/layout.js` or `@import`). Charcoal/cream/gold already live in the `--pz-*` block (globals.css:1557–1570); the `.pz` shell uses them. The top light `:root` (globals.css:1–36) only styles the two standalone pages — leave it until Connect/Setup are reskinned.
- **Kill dev-leaks (already `display:none`, but strip from DOM):** delete `SourceTruthStrip` (PhaseZeroApp.js:387–397) and `SOURCE_TRUTH_PATH` (sourceData.js:1–2); remove every `<SourceTagList …>` render site (454, 528, 545, 834, 1084, 1238); the `SourceTagList` component (210–218) can stay defined but unused, or delete it and `SOURCE_TAGS` (sourceData.js:17–30). Strip the visible id text in `TaskCard` footer (1233–1237: drop the `· Gateway …`/`· Browser …` spans). `AppShell` drawer subtitle (252) `<small>{item.href}</small>` → a human label field on `NAV_ITEMS`. Remove `JourneyRail` (call at 270; component 276–290; `JOURNEY_ITEMS` 88–95). The `body:not(.pz-debug) .pz-dev-tags,.pz-gateway { display:none }` gate (globals.css:2822–2823) stays as the belt-and-suspenders for anything debug-only.
- **Nav prune (sourceData.js):** `NAV_ITEMS` (4–15) drop `/great`, `/done`, `/mp3`, `/go-to`; add `label`+human `sub`. `SCREEN_TITLES` (75–86) drop `great/done/mp3/go-to`; set `board: ""`.

### 1. Welcome
- **Primary action:** one button — **"Come in"** → `/sign`.
- **Copy:** kicker `Vibe your life.` · H1 `I listen to your day and quietly handle the small stuff.` · sub `I draft — you approve. I never send anything without you.` · button `Come in` · hint `Takes about a minute.`
- **Layout:** the hero (`.pz-land-hero`, 300–312) is the whole above-the-fold. **Remove** `.pz-land-beats` (314–333), `.pz-land-trust` (357–361), and the duplicate `.pz-land-door` CTA (363–367). Optionally keep one proof beat: `.pz-land-moment` (335–355). Keep `.pz-land-bar` + `.pz-land-foot`.
- **Code:** `WelcomeScreen` currently renders inside `AppShell` (which re-adds the appbar, the `Vibe your life./Welcome` `.pz-top` H1 at 260–264, and the journey rail) → **double-chrome bug**. Fix the render/return (1955–1972): special-case `if (screen === "welcome") return <WelcomeScreen/>;` **before** the `AppShell` wrap. No route change.

### 2. Sign in
- **Primary action:** **Sign in** / **Create account** (one form).
- **Copy:** H2 `Come in.` · sub `One account, everywhere. That's it.` · buttons unchanged.
- **Layout:** two panels → one. Delete `<SourceTagList tags={["OPS-BASIC-PLUMBING","ST-TRUST-DIAL"]}/>` (454). Keep the `StatusPill` (457) only under `.pz-debug` (wrap in `<span className="pz-only-debug">`).
- **Code:** `SignScreen` (409–478). Keep `emailRedirectTo …next=/setup` (427) and `auth/confirm` default — correct entry point. No route change.

### 3. Setup (absorbs download)
- **Primary action:** **Continue** → `/connect` (auto-advance when extension detects — poll `refreshEngine`).
- **Copy:** H2 `Let's get you set up.` · sub `Two quick things, then I can start.` · helper block `Add the browser helper — it lets me work inside the Chrome you already use. Nothing sends without your okay.` · install steps kept as a plain `<ol>`.
- **Layout:** `SetupScreen` (481–503). Rename `ReadinessRow label="Engine"` (489) → drop the row entirely (or label `Connection`). Keep two rows: `Browser helper`, `Listening`. **Fold in** the download `Browser Helper` `<section>` from `DownloadPage` (download/page.js:14–57): the `.zip` download button + the 5-step install `<ol>`, shown inline when `!engineState.extensionConnected`. **Delete** the `Quick Start` git/pip section (download/page.js:59–89) and the `How it works` section (91–113).
- **Code:** Continue href (495) `/onboarding/2` → `/connect`. Remove the `<a href="/download">Get the browser helper</a>` (497) — content is now inline. Delete `app/download/` route dir + `DownloadPage`.

### 4. Connect (wire the orphan)
- **Primary action:** **Allow & continue** — one affirmative over the list, then → `/onboarding/2`.
- **Copy:** keep H1 `Give me a way to help.` and the honest sub (connect/page.js:478–483). Add a bottom primary CTA `Continue` → `/onboarding/2`, plus keep `Get to know me` as the in-page first-win (521–552).
- **Layout:** `ConnectPage` (connect/page.js) already human and clean. Keep `CapabilityRow` list + `OauthConnect` + `KnowYouRecap`. Add the trailing `Continue` button after the money-note (554–557). Move onboarding's per-service `AccountReadStage` consent here is optional — simpler: **delete `AccountReadStage`'s toggle UI from onboarding** (see #5) since this page is the one consent surface.
- **Code:** this page is standalone (own `.shell`/`.column` classes, light tokens). It needs a `Continue` link (`<a className="primary" href="/onboarding/2">Continue</a>`). It's now reachable because Setup's Continue points here.

### 5. Onboarding (the 4-layer scrape ⇄ call aha)
- **Primary action:** per layer, mostly **watch** → **Next**; final stage → **Looks right — start**.
- **Copy:** keep the guaranteed-first-win rhythm — `Reading your week…` → the unasked-for recap (`You talk to Dana most. Tuesdays are packed. Want me to keep an eye out?`). Final stage folds Great's `Does this feel right?` mirror + the one correction note.
- **Layout:** `OnboardingScreen` (515–561). Strip `<SourceTagList>` (528, 545). Replace the full 8-step `OnboardingTimeline` (740–751, rendered 532/558) with a minimal progress dot (`stage N of 4`). For read layers, keep `AccountReadStage`'s scan/deep-loop (567–673) but drop its per-service checkbox toggles (642–651) — consent now lives on `/connect`.
- **Code — the load-bearing edit:** `nextOnboardingHref` (675–678) last-stage `return "/great"` → `return "/"`. In the **final stage** render, inline `GreatScreen`'s `confirmDossier()` (804–815): call `POST /api/onboard/complete` then `window.location.href = "/"` (not `/done`). Delete `app/great/` + `GreatScreen`, `app/done/` + `DoneScreen`, and their render branches (1960–1961).

### 6. Main (one orb + one word + one input + cards)
- **Primary action:** the **orb** (tap to talk) — and one input that does talk / type / drop-MP3.
- **Copy:** no page title. Orb state word only: **Listening. / Thinking. / Acting. / Resting.** Input placeholder: `Say it, type it, or drop a recording — I'll catch the task.` Check-in copy on cards unchanged (already human).
- **Layout:** `BoardScreen` (921–937) → rename `MainScreen`. **Remove** `GatewayCircuit` (926), the 3-tile `.pz-action-dock` (929–933). Collapse `ActiveListeningPanel` (974–1025) to just the orb + one state word: map `listenState` → word via `stateWord()` (`listening→Listening`, `processing→Thinking`, `cards_created/working→Acting`, `ready/stopped→Resting`); move the controls row (1003–1011), meta (1012–1015), and transcript (1017–1022) into `<div className="pz-only-debug">`. **Build `OneInput`** by merging `TranscriptInput` (1027–1051) + `FileUpload` (1111–1129): one textarea (type→`submitTranscript`), a mic button (talk→`startBrowserListening`), a paperclip that opens a hidden `<input type=file>` (drop→`uploadFile`). Delete the `<a href="/mp3">Upload</a>` link (1046). Keep `PendingAsksPanel` (900–919) and a compact `TaskBoard` (from `GoToScreen`, 1145–1199) below the input for review.
- **Code:** SCREEN_TITLES `board: ""` + hide `.pz-top` when `screen==="board"` (AppShell 260–264) so the orb is the focus. Delete `app/mp3/` + `Mp3Screen`, `app/go-to/` + `GoToScreen`, and branches (1962–1963). `FeaturedTaskCard` (939–972) can be replaced by the compact `TaskBoard` or kept as the single top card.
- **CSS:** add `body:not(.pz-debug) .pz-only-debug{display:none!important}`; add a large orb + one-word state style near `.pz-listen-orb` (globals.css:2116–2151).

### 7. Settings (advanced: app-permissions + memory + controls)
- **Primary action:** the **autonomy dial** (Quiet · Balanced · Take the wheel).
- **Copy:** H2 `Settings.` · sub `Choose what I can hear, remember, and do. Anything sensitive stays ask-first.` Add a group `What each app can do` sourced from `/api/readiness` (the same data `/connect` uses).
- **Layout:** `SettingsScreen` (1392–1509). **Remove** `GatewayCircuit` (1436). **Fold in** from `MemoryScreen`: `LearnedMemoryPanel` + `ForgetMePanel` as a collapsible `Memory` group. **Delete `ContextPackInspector`** (1323–1389, rendered 1268) entirely — pure dev inspector.
- **Code:** delete `app/memory/` top-level route + `MemoryScreen` (1253–1272) and its branch (1964) → replace with `else if (screen === "memory") content = <SettingsScreen .../>` OR keep a thin `/memory` that redirects to `/settings#memory`. Keep the wired autonomy sync (1395–1414).

---

## The "Coming soon" system

A tiny capability-registry + badge that renders the **whole vision** as real buttons, with a `Coming soon` tag on the ~35 unwired seams — honest roadmap, not dead greyed-out buttons.

- **Registry — new file `app/phase-zero/capabilities.js`** (co-located with `sourceData.js`). Exports one array; implementation flips `wired:true` as each seam lands (this list IS the burn-down of the 35 seams):

```js
export const CAPABILITIES = [
  // group: "Hear"
  { id: "listen",     group: "Hear",   label: "Talk to me",        wired: true,  action: "orb" },
  { id: "type",       group: "Hear",   label: "Type it",           wired: true,  action: "input" },
  { id: "mp3",        group: "Hear",   label: "Drop a recording",  wired: true,  action: "upload" },
  // group: "Do"
  { id: "draft_email",group: "Do",     label: "Draft an email",    wired: false, route: "/connect" }, // Gmail-compose hand NOT built
  { id: "web_hand",   group: "Do",     label: "Do it on the web",  wired: false }, // extension_connected:false
  { id: "text_call",  group: "Do",     label: "Text & call me",    wired: false }, // Twilio 401
  { id: "deep_scrape",group: "Learn",  label: "Read my world deep",wired: false }, // crawl orphaned
  { id: "digest",     group: "Learn",  label: "Daily digest",      wired: false },
  { id: "proactive",  group: "Learn",  label: "Notice before I ask",wired: false }, // derive loop not live
  { id: "review",     group: "Approve",label: "Review what's ready",wired: true,  route: "/" },
  { id: "memory",     group: "Approve",label: "See what I know",   wired: true,  route: "/settings#memory" },
];
```

- **Components (add to PhaseZeroApp.js):**
  - `ComingSoonBadge` → `<span className="pz-soon">Coming soon</span>`.
  - `Capability({ cap })` → renders a button; if `cap.wired` it links/acts, else it's non-navigating and shows `<ComingSoonBadge/>` (still visible, still styled as a real button — anticipation, not disabled).
  - `CapabilityRail({ group })` → maps `CAPABILITIES.filter(c=>c.group===group)`.
- **Where it renders:** a collapsible `What I can do` strip on **Main** (below the input, collapsed by default so the orb stays the focus) and an always-open `What I can do` group in **Settings**. One source, two mounts.
- **CSS:** `.pz-soon` — a small gold-tinted pill (`background:rgba(215,179,106,.14); color:var(--pz-gold); font-size:11px; letter-spacing:.04em; border-radius:999px; padding:2px 8px`) near `.pz-pill` styles.

---

## Build order (one screen at a time, smallest-risk first)

Each step is independently shippable and verifiable: `curl -sS -o /dev/null -w "%{http_code}" http://localhost:3000<route>` (expect `200`, or `404` for deleted routes) **plus** a screenshot (Playwright/Chrome). No step breaks the app because deletions come only after the replacement path is wired.

1. **Global de-jargon + tokens** (no routes touched). Swap `--serif` → DM Serif Display; remove all `SourceTagList` render sites + `SourceTruthStrip` + `SOURCE_TRUTH_PATH`; strip `TaskCard` id footer; `AppShell` drawer human labels; remove `JourneyRail`; prune `NAV_ITEMS`/`SCREEN_TITLES`. Add `.pz-only-debug` + `.pz-soon` CSS. **Verify:** every route still `200`; screenshot any screen shows zero `ST-*`/path leaks.
2. **Welcome** — unwrap from `AppShell`; trim to hero (+ optional moment). **Verify:** `curl /welcome`=200; screenshot = one hero, single appbar, no double-chrome.
3. **Sign** — strip intro tags, gate `StatusPill`. **Verify:** `curl /sign`=200; screenshot one panel.
4. **Setup (+download)** — fold extension download in; Continue → `/connect`; delete `app/download/`. **Verify:** `curl /setup`=200, `curl /download`=404; screenshot shows install steps, no shell commands.
5. **Connect wired-in** — add `Continue` → `/onboarding/2`; drop onboarding consent toggles. **Verify:** `curl /connect`=200; click-through Setup→Connect→Onboarding reachable.
6. **Onboarding** — strip tags + timeline; fold Great's complete-POST + mirror into final stage; last href → `/`; delete `app/great/`, `app/done/`. **Verify:** `curl /onboarding/8`=200, `/great`&`/done`=404; final "Looks right" lands on `/`.
7. **Main** — rename `MainScreen`; build `OneInput` (merge `/mp3`); mount compact `TaskBoard` (merge `/go-to`); collapse orb to one word; remove dock + `GatewayCircuit`; delete `app/mp3/`, `app/go-to/`. **Verify:** `curl /`=200, `/mp3`&`/go-to`=404; screenshot = orb + one word + one input + cards.
8. **Settings** — fold in memory drawers + Forget-me + app-permissions; delete `ContextPackInspector` + `GatewayCircuit`; retire `app/memory/` (redirect to `/settings#memory`). **Verify:** `curl /settings`=200, `/memory`→200/redirect; screenshot no context-inspector.
9. **Coming-soon registry** — add `capabilities.js` + `Capability`/`ComingSoonBadge`/`CapabilityRail`; mount on Main + Settings. **Verify:** `curl /`=200; screenshot shows every capability as a button, unwired ones tagged `Coming soon`.

Relevant files: `/Users/omarebrahim/Anticipy-devin/app/phase-zero/PhaseZeroApp.js`, `/Users/omarebrahim/Anticipy-devin/app/phase-zero/sourceData.js`, `/Users/omarebrahim/Anticipy-devin/app/phase-zero/capabilities.js` (new), `/Users/omarebrahim/Anticipy-devin/app/globals.css`, `/Users/omarebrahim/Anticipy-devin/app/connect/page.js`, `/Users/omarebrahim/Anticipy-devin/app/download/page.js` (delete), and the route dirs `app/{great,done,mp3,go-to,memory}/` (delete/redirect).