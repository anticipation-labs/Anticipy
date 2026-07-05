# Anticipy — UI TRULY DONE: the build spec

**Repo:** `/Users/omarebrahim/Anticipy-devin` · **Branch:** `hoe/build`
**Two files carry ~all of this:** `app/globals.css` (3,590 lines) and `app/phase-zero/PhaseZeroApp.js` (2,862 lines). Plus `lib/phase-zero/store.js`, `app/connect/page.js`.

This is the single coherent plan to make Anticipy (1) **look reference-quality** (calm editorial charcoal/cream/gold) and (2) **work end-to-end** (no cosmetic controls, no invented data, no silent no-ops). It is written to be executed top-to-bottom. Every step compiles, is checkable live in Chrome, and holds the suite.

---

## 0. The two root problems (read first)

1. **Two design languages in one stylesheet.** `globals.css` has **two `:root` blocks** — the light editorial system at **line 3** (`--bg:#faf9f7`, `--ink:#141311`, gold `--ask:#b07912`, DM Serif Display, graded shadows) and a **dark "Phase Zero V2" block at line 1559** (`--pz-bg:#080807`, `--pz-cream:#f8f4ec`, `--pz-gold:#d7b36a`, `body{background:var(--pz-bg)}`). Landing/sign render light; the **core product surface (board, orb, deck, settings, connect) renders dark**. `--pz-cream` is used **73×** vs `var(--ink)` **29×** — the dark theme quietly became the default and fights the "Vibe your life." brief. A third dead system (`.ant-*`, globals.css:840–1544, ~700 lines, **zero JS usages**) and a fourth namespace (`.shell` for `/connect`, globals.css:3172, on `--pz-*` tokens) add to the incoherence.

2. **The board is a Tinder swipe-stack.** `SwipeDeck` (PhaseZeroApp.js:1298) → `DeckCard` (:1391) renders one draggable card over a `position:absolute` stack; **right=confirm, left=deny, up=autonomy** via `SWIPE_THRESHOLD` (:1296). The card fill is **translucent** (`globals.css:3404` = `linear-gradient(rgba(248,244,236,.09), .045)`), so under-cards' cream titles **bleed through** the top card — the "overlap" bug. Swipe also fires **real engine mutations under a gesture** (risky), and hides queue depth. Anticipy's cards are glanceable status objects ("On it / Waiting for you / Needs a yes"), not a decision queue — the correct pattern is a **calm vertical list** (Linear / Things / Apple Reminders / Pocket / Claude), not a stack.

Fix both and the product reads as one warm editorial surface with an ambient orb heartbeat.

---

## 1. THE DESIGN SYSTEM (concrete tokens)

One light theme, canonical. DM Serif Display = **display only** (never < 20px). Inter = all functional UI. Hairlines separate, not heavy shadows. One accent: gold. 4px base / 8px rhythm. Fast ease-out default; exactly one spring (the completion commit).

### 1.1 Token block — replace the `:root` at `globals.css:3`

```css
:root {
  color-scheme: light;

  /* Surfaces (charcoal / cream) */
  --bg:#faf9f7; --bg-tint:#f4f1eb; --panel:#ffffff; --panel-tint:#f6f4f0;

  /* Ink */
  --ink:#141311; --ink-soft:#2e2d2a; --muted:#6b6860; --faint:#9e9a92;

  /* Lines (hairlines do the separating) */
  --line:#e8e5de; --line-soft:#f0ede6; --line-strong:#d9d5cc;

  /* Gold — the single brand accent */
  --gold:#b07912; --gold-strong:#97650a; --gold-tint:#fef8eb;
  --gold-ring:rgba(176,121,18,.28);

  /* Semantic (muted, editorial — never neon) */
  --do:#1a7f55;      --do-bg:#eaf7f0;    /* On it */
  --ask:#b07912;     --ask-bg:#fef8eb;   /* Waiting for you (== gold) */
  --blocked:#c4423a; --blocked-bg:#fdf0ee;/* Needs a yes */
  --remember:#3570a7;--remember-bg:#edf3fa;/* I'll remember */
  --calm:#8a857b;    --calm-bg:#f3f1ed;  /* Resting */

  /* Spacing: 4px base, 8px rhythm */
  --s-1:4px; --s-2:8px; --s-3:12px; --s-4:16px;
  --s-5:24px; --s-6:32px; --s-7:48px; --s-8:64px;

  /* Radius (continuous feel) */
  --r-xs:8px; --r-sm:12px; --r-md:16px; --r-lg:20px; --r-pill:999px;

  /* Elevation: low, warm, charcoal-tinted (never black) */
  --shadow-xs:0 1px 2px rgba(20,19,17,.04);
  --shadow-sm:0 1px 3px rgba(20,19,17,.06), 0 1px 2px rgba(20,19,17,.04);
  --shadow-md:0 4px 16px rgba(20,19,17,.06), 0 1px 3px rgba(20,19,17,.04);
  --shadow-lg:0 16px 48px rgba(20,19,17,.10), 0 4px 12px rgba(20,19,17,.04);
  --ring:0 0 0 1px var(--line);           /* elevation-by-hairline */
  --ring-gold:0 0 0 1px var(--gold-ring); /* active / focus */

  /* Type */
  --serif:"DM Serif Display","Fraunces",Georgia,serif;
  --sans:"Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;

  /* Motion (one ease, one spring, three durations) */
  --ease:cubic-bezier(.2,.8,.2,1);
  --ease-in-out:cubic-bezier(.4,0,.2,1);
  --spring:cubic-bezier(.34,1.56,.64,1);  /* checkbox / commit overshoot */
  --t-fast:120ms; --t:180ms; --t-slow:280ms;
}
```

### 1.2 The theme flip — the **safe, atomic, reversible** move

Do **not** hand-edit 73 `--pz-*` call sites first (that's a big risky diff and would break `.shell`/`/connect`). Instead **redefine the dark "Phase Zero V2" `:root` (globals.css:1559) as light aliases** pointing at the tokens above. This flips the entire product surface (board, orb, deck, settings, connect) to light in **one edit**, trivially revertible:

```css
/* globals.css:1559 — was the dark V2 block; now aliases to the light system */
:root {
  --pz-bg:var(--bg);          --pz-bg-soft:var(--bg-tint);
  --pz-surface:var(--panel);  --pz-surface-2:var(--panel-tint);
  --pz-cream:var(--ink);      --pz-cream-soft:var(--ink-soft);
  --pz-muted:var(--muted);    --pz-faint:var(--faint);
  --pz-line:var(--line);      --pz-line-soft:var(--line-soft);
  --pz-gold:var(--gold);      --pz-gold-soft:var(--gold-tint);
  --pz-good:var(--do);        --pz-red:var(--blocked);
}
```

Then neutralize the dark canvas painters immediately below it (globals.css:~1574–1586):

```css
body { background:var(--bg); color:var(--ink); }   /* was var(--pz-bg) + dark gradient */
.pz  { background:var(--bg); }                       /* drop the dark linear-gradient */
```

**Later cleanup (non-blocking, own commit):** `sed` `--pz-cream→--ink`, `--pz-cream-soft→--ink-soft`, `--pz-muted→--muted`, `--pz-line→--line`, `--pz-gold→--gold`, `--pz-good→--do`, `--pz-red→--blocked`, then delete the alias block, delete the dead `.ant-*` block (globals.css:840–1544), and fold `.shell` into the shared primitives. Purely mechanical; ship after the visual is confirmed.

### 1.3 Type scale (serif = display only)

| Token | Size / line-height | Weight | Family | Use |
|---|---|---|---|---|
| Display | clamp 40–56px / 1.05 | 400 | serif | Welcome hero, "Vibe your life." |
| Title | clamp 28–34px / 1.08 | 400 | serif | Screen titles, board header |
| Card title | 20–24px / 1.15 | 400 | serif | The task line on a card |
| Heading | 17px / 1.4 | 600 | sans | Section labels, settings groups |
| Body | 15px / 1.6 | 400 | sans | Check-in copy, "here's what I heard" |
| Meta | 13px / 1.5 | 500 | sans | Timestamps, source tags |
| Micro | 11–12px / 1.4 | 600 | sans | Pills, kicker (uppercase, +.08em) |

**Rule: one serif line per card maximum** (the task itself). Everything supporting is Inter. That is what reads "editorial," not "decorated."

### 1.4 Kill the double-title bug (global, affects every screen)

`.pz-top h1` is defined **twice** — a 56px serif headline at `globals.css:175` and a **15px muted sans** override later (~:1725). The second wins, so `Sign in` / `Setup` / `Settings` render as tiny grey breadcrumb chrome while a decorative panel `<h2>` shouts below. Delete the 15px override; keep **one** rule: `.pz-top h1 { font:400 clamp(28px,4vw,34px)/1.08 var(--serif); color:var(--ink); }`. This alone re-establishes hierarchy on 4 screens.

### 1.5 Global focus + motion defaults

```css
:focus-visible { box-shadow:var(--ring-gold); outline:none; border-radius:inherit; }
@media (prefers-reduced-motion:reduce){ *{animation:none!important;transition-duration:1ms!important;} }
```

---

## 2. THE CARD BOARD — vertical list replacing the swipe-stack ⭐

**File:** `app/phase-zero/PhaseZeroApp.js` — `SwipeDeck` (:1298), `DeckCard` (:1391), rendered by `MainScreen` (:1523, `{props.cards.length ? <SwipeDeck …/> : null}`). CSS: `.pz-deck-*` (globals.css:3351–3440).

### 2.1 Layout (grouped vertical list, 720px centered)

```
Your day                         ← serif Title 28–34
Vibe your life.                  ← gold micro kicker

WAITING FOR YOU · 2              ← section label, Meta, --muted
┌──────────────────────────────────────────────┐
│ ● Get Leila after school         2:40pm   ⌄  │  row (collapsed)
│   "can you get Leila after school?"          │  heard-quote, Inter 15, --ink-soft, ≤62ch
└──────────────────────────────────────────────┘
┌──────────────────────────────────────────────┐  row (expanded, accordion — only one)
│ ● Start the return for your headphones  ⌄    │
│   "the headphones are the wrong ones"        │
│   Okay for me to go ahead?                   │  check-in line, Body
│   ▸ proof / receipt (details)                │
│   ▸ note field                               │
│   [ Not now ]              [ Go ahead ]  ⋯   │  inline actions
└──────────────────────────────────────────────┘

ON IT · 1
│ ◐ Booking the dentist        ·  in progress │

RESTING · calm today             ← collapsed by default
```

### 2.2 Row anatomy (the atom)

- Container: `background:var(--panel); border:1px solid var(--line); border-radius:var(--r-md); box-shadow:var(--shadow-xs);` hover → `box-shadow:var(--shadow-sm); border-color:var(--line-strong);` transition `var(--t-fast) var(--ease)`.
- **Left rail:** 6px status dot colored by semantic token (`--ask`/`--do`/`--blocked`/`--remember`/`--calm`). For "On it → done", a **Things-style circular checkbox that spring-fills** (`--spring`) — the one delight in the whole system.
- **Line 1:** serif card title 20–24px/400, one line, ellipsis. Right: timestamp (Meta, `--muted`) + chevron.
- **Line 2 (always):** the **heard** quote, Inter 15/1.6, `--ink-soft`, `max-width:62ch`.
- **Expanded (chevron, not swipe):** check-in line + `<details>` proof + note field + action row. Animate `grid-template-rows:0fr→1fr` over `--t-slow var(--ease)`. **Accordion: one row open at a time.**
- Row gap `var(--s-3)`; section gap `var(--s-6)`; board `max-width:720px; margin-inline:auto` (matches `OneInput`).

### 2.3 Actions become buttons (keep the 3 engine mutations, drop the gestures)

- **Go ahead** — gold-filled primary → `resolveCard(card, true)`
- **Not now** — ghost → `resolveCard(card, false)`
- **⋯ overflow** — "Always okay to do this" → `allowAutonomy(card)` (behind confirm, see §4.7); "Note" → `saveComment`.
- Keyboard-first (Linear): `↑/↓` move focus, `Enter` expand, `Y`/`N` confirm/deny.

### 2.4 Motion

- Rows enter: 12px rise + fade, `--t-slow var(--ease)`, **40ms stagger**.
- On confirm: gentle **scale→.98 + fade + collapse** (not a fling), then list re-flows. No off-screen throw.
- The only spring: the completion checkbox fill.

### 2.5 Empty state (calm, one line)

Centered hairline circle + thin check, serif "**Nothing needs you right now.**", Inter sub "I'm listening. I'll surface things as they come." Reuse `.pz-deck-empty`; repoint colors. Replace the emoji/unicode `✓` (PhaseZeroApp.js:~1383) with an inline SVG for a consistent icon language.

### 2.6 Concrete code changes

- **`DeckCard` (1391–1520):** delete `drag` state, `onPointerDown/Move/Up`, `SWIPE_THRESHOLD` (1296), the `commit(direction)` mapping (1336–1342, 1433–1435), and the `translate(${drag.x}px…) rotate` / `position:relative|absolute` inline styles (~1457–1469). Render a single `<li>` expandable row (§2.2). **Guard the under-card text** — the current bug is that `.pz-deck-card-top`/`.pz-deck-title` render *before* the `interactive` gate (~:1476–1482); in a flat list there is no stack, so the bleed-through disappears by construction.
- **`SwipeDeck` (1298):** replace the absolute stack with `<ul>` grouped by `card.category` into three sections (Waiting for you / On it / Resting). Keep `resolveCard`, `stopCard`, `allowAutonomy`, `saveComment` wired to the buttons.
- **`globals.css`:** `.pz-deck-stack` → `display:grid; gap:var(--s-3);` remove `padding:8px 0 2px` seam (~:3391) and `.pz-deck-card{position:absolute}` behavior (:3394). `.pz-deck-card` background → **opaque** `var(--panel)` (kills translucency at :3404). Delete `.hint-confirm/-deny/-autonomy` swipe-hint rules (:3424–3440). Fix width mismatch: give `.pz-deck-head` the **same** `max-width:720px; margin-inline:auto` as the rows (header currently full-width while cards are 620px). Delete dead `TaskBoard`/`TaskCard`/`FeaturedTaskCard` (PhaseZeroApp.js:1793/1851/1694) and their CSS (`.pz-task-shell`/`.pz-queue`/`.pz-featured-task`).

### 2.7 The board's other three panels (unify)

The board stacks four different content widths and three differently-styled input panels. Normalize all to `max-width:720px; margin-inline:auto`:
- **OneInput** (`.pz-oneinput`, globals.css:~3074) — keep (see §3.6), the archetype.
- **PendingAsks** (`.pz-pending-asks`, ~:2953) — add `max-width:720px` (currently full-width).
- **WebActionPanel / BoardActionsPanel** (~:3115/:3153) — either fold into the OneInput card as a "/act" affordance or give them the identical card frame (`--panel`, `--r-lg`, `--line`, `--shadow-sm`). No more three-dialect stacking.

---

## 3. PER-SCREEN POLISH + FIX PLAN (each tied to file:line)

### 3.1 Welcome — `PhaseZeroApp.js:329` `WelcomeScreen` / `.pz-land` (globals.css:2962+)
Cleanest screen; keep the tone. **Fix:** delete dead `.pz-land-beats/-beat/-trust/-door` (globals.css:2998–3035) — styled, never rendered. No layout bleed here.

### 3.2 Sign — `PhaseZeroApp.js:415` / `.pz-form-single` (globals.css:2022)
**Fix the competing double title:** AppShell shows kicker "Vibe your life." + tiny grey h1 "Sign in" while the panel shows big serif h2 "Come in." — two headings fighting, the "real" one 15px. Resolved by §1.4 (single `.pz-top h1` rule); additionally **drop the panel `<h2>` "Come in." (PhaseZeroApp.js:456)** or demote it to Body sub-copy so there is exactly one heading per screen.

### 3.3 Setup — `PhaseZeroApp.js:484` `SetupScreen` / `.pz-stage-minimal` (globals.css:1937), `.pz-setup-helper` (:1990)
- **Vertical rhythm:** `.pz-stage-hero` is a flex column with **no `gap`** — spacing is a mix of `<p>` margins + ad-hoc `margin-top` (:1965=24, :1992=18). Set `.pz-stage-hero{display:flex;flex-direction:column;gap:var(--s-4);}` and strip the per-child margins.
- **Left-hugging blocks:** `.pz-readiness-list` + `.pz-setup-helper` are `width:min(520px,100%)` with no centering inside a full-width card → left gutter. Add `margin-inline:auto` (or make the card `max-width:560px`).
- **Detached action row:** Continue / Check-again (:514) sit **outside** the hero card as a sibling. Move them **inside** the card as its footer.

### 3.4 Onboarding "You" (stage 2) — `PhaseZeroApp.js:537` / `.pz-onboarding-card` (globals.css:2037)
- **Empty hole beside "Name":** 2-col grid (:2046); `summary` + `doNotTouch` are forced `grid-column:1/-1` (:2052) but Name sits in row1/col1 with a **blank cell to its right** (auto-placement can't backfill). Fix: make Name span full width too, or reorder so two single-column fields pair up. Simplest: **single-column form** (`grid-template-columns:1fr`) — calmest and removes the hole.
- **Mismatched centering:** intro panel `align-content:center` (:2041) vs top-aligned form. Set both columns `align-content:start`.

### 3.5 Onboarding read stages 3/5/7 — `PhaseZeroApp.js:562–582`, `AccountReadStage` (:589)
- **Cramped 8-col timeline:** `.pz-timeline` is `repeat(8,…)` at `min-height:66px` (globals.css:2116–2120) — 8 tiny cells. Change to a **vertical list of 8 rows** (or `repeat(auto-fit,minmax(120px,1fr))`), each a status row (label + status word) reusing the row atom.
- **Unstyled open-loop rows:** `OpenLoopsSection` renders `<li className="pz-loop-row">` (:873) but **`.pz-loop-row` has zero CSS** → raw bullets. Add: `.pz-loop-row{display:flex;align-items:center;justify-content:space-between;gap:var(--s-3);padding:var(--s-3);border:1px solid var(--line);border-radius:var(--r-sm);list-style:none;}`.
- **Nav highlight gap:** during onboarding-3/5/7 nothing is highlighted (`NAV_ITEMS` only maps `onboarding-2`→"You", PhaseZeroApp.js:99; active detection is `href.includes(screen)` at :280). Add a single "Onboarding" nav destination whose `screens` array includes all `onboarding-*` so the user always sees where they are.

### 3.6 Onboarding final — `PhaseZeroApp.js:1120` `OnboardingFinalStage`
- **Column-count whiplash:** `pz-profile-summary` 4-col (globals.css:2110) → `LearnedMemoryPanel` 2-col (`.pz-grid.two`, :344) → single panels — three grid rhythms stacked as unrelated boxes. Pick **one** rhythm: a single-column stack of the row-atom, or a consistent `.pz-grid.two`. Remove the 4-col summary.
- Inherits the `.pz-loop-row` fix (§3.5). Long page — add `--s-6` section gaps and section labels.
- **Data honesty:** this screen currently shows fabricated Priya/Marcus/Gmail/Notion (see §4.1 + §5). Must read real data or say "nothing yet."

### 3.7 Board — see §2 (the headline redesign) + §2.7 (panel unification).

### 3.8 Settings — `PhaseZeroApp.js:2078` `SettingsScreen` / `.pz-settings-*`
- **Uneven 2-col body:** `.pz-settings-body` is `repeat(2,1fr)` (globals.css:2469) mixing tall selects with short checkbox pills in one row (e.g. Autonomy `<select>` next to "Money always asks", :2151–2159) → different heights/frames; odd child counts leave blank half-cells (Listening = 3 checks :2170; Text&call = 3 :2181). **Fix: make every settings group a single-column grouped inset list** (Apple Settings pattern). Delete `.pz-settings-body`/`-body-wide` split; one column everywhere.
- **Grouped inset lists:** each `<details>` group = white `--panel` card, `--r-md`, `--ring`; rows divided by `--line-soft` **inset** dividers; group header = Heading 17/600 + one-line `--muted` description.
- **Rows:** label left (Body 15), control right, `min-height:44px`, `--s-3`/`--s-4` padding.
- **Build a real pill switch** (replace checkboxes for on/off prefs): 44×26 track, `--line`→`--gold` on, 22px white knob sliding `var(--t) var(--ease)`, `--shadow-xs` on knob.
- **Unstyled raw spots (0 CSS, render broken):** `pz-recall-form` (:942), `pz-remembered-head/-row/-actions/-preview` (:1064–1113), `pz-channel-mode` (:2063), `pz-loop-row`. Give each a flex layout so buttons align instead of wrapping under text.
- **Panel-in-panel nesting:** Memory drawer nests `LearnedMemoryPanel` + `MemoryRecallPanel` (another `pz-grid.two` of panels) + `RememberedReviewPanel` + `ForgetMePanel` (:2229–2241) — flatten one level; not every sub-panel needs its own border.
- **Destructive isolation:** "DELETE MY DATA" (~:1977) + Forget-me → own group at the bottom, `--blocked` text, keep the type-to-confirm gate.
- **Footer hierarchy:** four equal-weight buttons (Save / Run a tick / Download Mac app / Back) (:2243–2250) → Save primary, the rest ghost/text.
- **Summary tags:** the `<small>` per group mixes live state ("Regular","On","7 days") with static nouns ("Permissions","What I know"); make them all live state or all labels.

### 3.9 Connect — `app/connect/page.js` (629 lines) / `.shell` (globals.css:3172)
A **fourth** namespace (`shell/row/primary/secondary`) on `--pz-*` tokens. After §1.2 it inherits light automatically. **Polish:** render services as calm status rows — status dot + "Connect" ghost button flipping to a `--do` "Connected" pill (reuse `.pz-readiness-row` + `.pz-dot.ok`). No logo grid. Note: this is the **API/Arcade arm** the memory deprioritized in favor of browser-only — keep it working but do not expand it.

### 3.10 The orb (ambient anchor) — `.pz-listen-orb-button` (PhaseZeroApp.js:1759) / `.pz-listen-orb` (globals.css:606)
- **Idle:** cream sphere defined by a gold inner glow, not a hard border. `background:radial-gradient(circle at 38% 34%,#fff,#f4efe4 62%,#ede6d6); box-shadow:inset 0 1px 2px rgba(255,255,255,.9), 0 8px 30px rgba(176,121,18,.10), var(--ring);` **slow breathe** `scale(1→1.02)` over **4s ease-in-out infinite** (replace the current 1.8s pulse).
- **Active/listening:** warm **gold** core + two concentric gold ripple rings on a 2.2s loop. **Remove the red `#d65b4a` active state** (`.pz-listen-orb.active`, globals.css:615) — red reads as record/danger, off-brand. Repoint to gold. Optional 3–5 gold waveform bars only while capturing.
- Reduce shadow from `0 30px 80px rgba(0,0,0,.34)` → `0 16px 44px rgba(176,121,18,.14)`. Honor `prefers-reduced-motion` (static ring + opacity crossfade).

---

## 4. FUNCTIONAL FIX LIST (broken/stub → working; blocking first)

**Architecture is sound:** every `app/api/*` route is an owner-gated proxy (`app/api/_engine.js`) to a real FastAPI engine (`engine/anticipy_engine/main.py` + `core/control_core.py`); no proxy points at a missing endpoint; engine boots on the real model (`env.load_local_env()` before gateway build). The holes are specific.

### BLOCKING (honesty / silent no-ops)

**4.1 — Fabricated fresh-user profile.** `lib/phase-zero/store.js:7` `DEFAULT_PROFILE` ships fake people (**Priya line 16, Marcus line 17**), fake tools (Gmail/Calendar/Notion/HubSpot), fake open loops. A brand-new user sees invented facts about themselves on onboarding-final + profile — directly contradicts "nothing invented." **Fix:** make `DEFAULT_PROFILE` empty, mirroring `EMPTY_PROFILE` (PhaseZeroApp.js:35). Every summary then reads real data or an honest empty state.

**4.2 — Card Confirm/Not-now is a no-op on non-ask cards.** `resolveCard` (PhaseZeroApp.js:2625) only hits `/resolve` when `card.askId` exists; otherwise it just `setMirror(id,"coming_soon")` — the card visually retires but **nothing closes on the engine** (~:2625–2640). **Fix:** add a real close/ack endpoint for non-ask ("On it") cards, **or** hide Confirm on cards with no `askId` and show only "Mark done"/"Stop" as appropriate. No button may lie.

**4.3 — Card "Note" never reaches the brain.** `saveComment` (PhaseZeroApp.js:2477) → `/api/tasks/comments` writes to `.anticipy-data` only; the copy "I'll keep it on this one" implies the assistant learns. **Fix:** POST the note into the engine (memory/feedback on the card's gateway event), **or** change the copy to "private local note." Prefer the former.

### HIGH

**4.4 — Profile basics form is siloed.** `/onboarding/2` writes name/summary/trust-dial to the local store, **not** the engine profile drawer — the brain never learns the user's stated identity/trust. **Fix:** also push these to `/owner/ingest` or a profile-write engine route.

**4.5 — `ProfileBuiltPanel` is effectively dead.** UI always sends `sources:[]` (no `sources` in `EMPTY_PROFILE`/`DEFAULT_PROFILE`, PhaseZeroApp.js:~1143) → **always a 0-fact scaffold**. **Fix:** feed it real source URLs from deep-scan discovery, **or** remove it and lean on `LearnedMemoryPanel` (`/memory/drawers`), which already shows real learning.

### MEDIUM

**4.6 — Settings safety/listening/retention toggles are cosmetic.** They persist to `.anticipy-data` via `/api/settings` but the engine's real gates are hardcoded and don't read them (unchecking "Money always asks" changes nothing). Per CLAUDE.md, deeper safety-gating is deliberately deferred — so **do not build new gates**; instead **stop presenting inert toggles as live controls** (mark display-only, or hide until wired). Autonomy dropdown is already live (`/owner/autonomy_mode`).

**4.7 — "Allow autonomy" flips GLOBAL autonomy to `full_send`.** `allowAutonomy` (PhaseZeroApp.js:2647) → `/owner/autonomy_mode` sets global, not per-card as the copy implies — big blast radius under a swipe. In the new list it's behind the `⋯` overflow (§2.3); **add a confirm** ("Let me do things like this without asking?") and, if the engine supports it, scope by class.

### EXPECTED / DEPLOY

**4.8 — The "hands" arm is extension-gated (the #1 real-world dependency).** "Do it on the web" (`/agent/run`), onboarding scan/deep-read (`/onboard/scan`, `/onboard/loop`), and Continue all **no-op honestly** without the paired Chrome extension. Nothing breaks; nothing acts. This is the single biggest gate on "does anything actually get done." Keep the honest "connect the helper" messaging; make pairing the top of the setup flow.

**4.9 — Deploy-context risks (low locally, blocking on serverless).** (a) The local store writes to `process.cwd()/.anticipy-data` (store.js:4) — fine on Railway/local, **fails on read-only serverless FS** (Vercel) for profile/settings/onboarding/tasks. (b) Browser mic WS connects the browser straight to `ws://engine:8787/listen/stream`, bypassing the Next proxy + owner auth — works on localhost, needs a directly-reachable `wss` engine on cloud. Track these before any Vercel push.

---

## 5. ONBOARDING + CUSTOM-PROFILE + DOSSIER COMPLETENESS

The end-to-end onboarding promise is: **land → sign → setup(pair the hand) → connect → read my accounts → the profile I built for you → looks right → done**, with **nothing invented** and every stated fact reaching the brain.

Completeness checklist (all must hold):
1. **No fabricated data** anywhere — §4.1 empties `DEFAULT_PROFILE`; every panel reads real engine/memory data or shows a calm empty state.
2. **Stated identity reaches the brain** — §4.4 pushes name/summary/trust-dial into the engine, not just the local store.
3. **The learned dossier is the source of truth** — `LearnedMemoryPanel` → `/memory/drawers` (four real drawers: You / People / Tools / Open loops) is what the user reviews. Either fix `ProfileBuiltPanel` to show real discovered sources (§4.5) or remove it so there is **one** dossier surface, not a dead scaffold competing with the real one.
4. **The hand is paired before "read my accounts"** — surface extension pairing (§4.8) as step 1 of setup; scan/deep-read honestly report `triggered:false` until paired.
5. **Consent gates are real** — `AccountReadStage` → `/onboard/permissions` is a genuine consent gate; keep it. Retention/listening toggles must not claim to gate anything they don't (§4.6).
6. **"Looks right → complete"** writes the durable `/onboard/complete` marker (already real) — the flow ends by learning, not by a cosmetic checkmark.
7. **You always know where you are** — the nav highlights an "Onboarding" destination across onboarding-2/3/5/7 (§3.5).

Custom profile = the user can (a) state basics that the engine ingests, (b) watch the real dossier fill from scan/deep-read, (c) correct any fact (correction form on onboarding-final), and (d) forget-me wipes it (already real, phrase-gated). No step shows invented facts; no step silently drops user input.

---

## 6. ORDERED BUILD SEQUENCE (each step compiles, checks live, holds the suite)

**Verification harness for every step:**
- **Compile:** `npm run build` (Next) must pass; `npm run lint`.
- **Live Chrome check:** `npm run dev`, engine up (`engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`), open the named screen with the claude-in-chrome MCP, screenshot, confirm the specific acceptance below.
- **Suite no-regression (GATE-S):** `bash scripts/run_suite.sh` — baseline **109 passed / 10 failed**; the **failed name-set may never grow** (byte-diff the tail line vs baseline). Milestone batteries against a **fresh** engine + fresh `ANTICIPY_DATA_DIR`: `overnight/m1_battery.py`, `m2_copy_test.py`, `m3_integration_test.py`. Wiring gate: `engine/.venv/bin/python factory/bin/check_wiring.py`.
- **Concurrency:** if `factory/.lock` exists, a factory lap is running — **do not commit** (`ls factory/.lock` first).

Steps are ordered so each is independently shippable and low-risk-first. UI-only steps cannot change suite results; that's the point of front-loading them.

| # | Step | Files | Acceptance (live) |
|---|---|---|---|
| **1** | **Theme flip.** Alias the dark V2 `:root` to light (§1.2); neutralize `body`/`.pz` dark painters. | globals.css:1559, ~1574–1586 | Board/orb/deck/settings/connect all render **cream**, not near-black. No dark seams. Suite unchanged. |
| **2** | **Token block + double-title fix + focus/motion defaults.** | globals.css:3 (§1.1), :175/~1725 (§1.4), (§1.5) | Screen titles render as 28–34px serif; `Sign in`/`Setup`/`Settings` no longer tiny grey. Gold focus ring visible on tab. |
| **3** | **Board redesign → vertical list.** Rip out `DeckCard` drag/`SWIPE_THRESHOLD`; `<ul>` grouped rows; opaque cards; button actions; empty state; unify panel widths. | PhaseZeroApp.js:1296–1520, 1523; globals.css:3351–3440, dead TaskBoard/CSS | No overlap/bleed-through. One card expands (accordion). Go-ahead/Not-now/⋯ work; keyboard nav works. Header aligns to 720px rows. |
| **4** | **Orb refine.** Idle breathe 4s, gold active (drop red), lighter warm shadow, reduced-motion. | PhaseZeroApp.js:1759; globals.css:606–615 | Idle sphere breathes slowly; listening = gold ripples, never red. |
| **5** | **Per-screen polish.** Welcome dead CSS; Sign single-heading; Setup gap/centering/action-in-card; Onboarding-2 hole; timeline vertical; `.pz-loop-row` + unstyled settings spots; settings single-column inset lists + pill switch + footer hierarchy + destructive isolation; connect status rows; nav onboarding destination. | §3.1–3.9 | Each screen matches its §3 acceptance; no left-hugging blocks, no blank grid cells, no raw bullets, no double input dialects. |
| **6** | **FUNCTIONAL blocking.** Empty `DEFAULT_PROFILE`; non-ask Confirm real-close-or-hide; Note → engine (or honest copy). | store.js:7–17; PhaseZeroApp.js:2625, 2477 | Fresh user sees **no** Priya/Marcus. Confirm on an "On it" card actually closes it on the engine (verify via `/memory` or a tick), or the button is absent. Note persists to the brain (read back). |
| **7** | **FUNCTIONAL high.** Basics form → engine (§4.4); ProfileBuiltPanel real-or-removed (§4.5). | PhaseZeroApp.js onboarding-2, ~1143 | Stated name/trust visible in `/memory/drawers` after submit. No dead 0-fact scaffold. |
| **8** | **FUNCTIONAL medium.** Autonomy confirm + scoping (§4.7); inert settings toggles marked display-only or hidden (§4.6). | PhaseZeroApp.js:2647; SettingsScreen | Autonomy asks before flipping. No toggle claims a gate it doesn't drive. |
| **9** | **CSS cleanup (non-blocking).** `sed` `--pz-*`→semantic tokens; delete alias block + dead `.ant-*` (840–1544) + dead `.pz-land-*`; fold `.shell` into primitives. | globals.css | Grep: 0 `--pz-` refs remain; build passes; visuals identical to step 5. |
| **10** | **Deploy hardening (before any Vercel push).** Store FS fallback; mic `wss` reachability. | store.js:4; listen route | Note as NEEDS-OMAR if targeting serverless; harmless on Railway/local. |

**Definition of done:** one warm cream/charcoal/gold theme end-to-end; the board is a glanceable unhurried list with the orb as ambient heartbeat and one DM Serif Display line per card; every control does what it says (no cosmetic toggles, no silent no-ops, no invented facts); onboarding ingests what the user states and shows only real learning; and `bash scripts/run_suite.sh` still reads 109/10 with the identical failed-set. Verified live in Chrome, screenshots pasted, not merely compiled.
