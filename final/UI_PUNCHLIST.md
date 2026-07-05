# UI PUNCH-LIST — live QA of anticipy-welcome.vercel.app (2026-07-04, post S1-S3 deploy)

Found by looking at the LIVE cloud, screen by screen. Fix in the deep pass AFTER S4/S5 land, then redeploy + re-QA.

## P1 — HIGH: dark form controls (theme-flip miss) ⭐
The S1 light theme flip did NOT restyle inputs / selects / textareas — they still render **dark grey** against the cream surface. Visible on: onboarding stage-2 form (Name, One-sentence summary, Phone, Timezone, Trust dial select, "Always ask before" textarea) and Settings (Autonomy `<select>`).
- Fix: global light form-control styling — `input, select, textarea { background: var(--panel-tint); color: var(--ink); border: 1px solid var(--line); border-radius: var(--r-sm); }` + focus ring `--gold-ring`. Restyle native `<select>` (custom chevron) so it isn't dark. Search globals.css for any `--pz-*` dark input rules left over.

## P2 — HIGH: board top panel overflows right (not centered)
On the board, the "Resting." orb panel + content are **left-aligned and overflow off the right edge** — the board container isn't `max-width:720px; margin-inline:auto` on the listening/orb panel (spec §2.7 said normalize all panels to 720px centered; the orb/listening panel was missed).
- Fix: constrain + center the listening/orb panel to match the 720px column.

## P3 — MED: "Live" status pill stretched full-width
On card headers (Settings card, onboarding intro panel) the small "Live" badge **spans the full card width** instead of hugging its text.
- Fix: the pill should be `display:inline-flex; width:auto; align-self:flex-start;` — it's inheriting a block/stretch.

## P4 — LOW: onboarding stage-2 left panel mostly empty
The left intro panel ("Tell me three simple things.") is a tall near-empty card next to the form. Consider single-column (spec §3.4) or give the intro real content.

## Working well (keep) ✓
- Board card LIST: clean, real cards (Cactus Club / dentist), no overlap, heard-quote shown — the S2 redesign is good.
- Settings: grouped inset lists + gold pill switches — premium, on-spec.
- Theme: cohesive cream/charcoal/gold; serif headers; "VIBE YOUR LIFE." kicker.
- Onboarding stage timeline → rows (BASICS/YOU/LAYER 1) — readable.

## Still to QA (next passes)
welcome (top/orb overflow), sign, setup, connect, onboarding read-stages (3/5/7) + final (fabricated-data honesty bug), the mobile/narrow layout, motion/micro-interactions, every card action (Confirm/Not-now/Autonomy/Note) end-to-end.

## Round 2 QA (post-deploy, 2026-07-04) — verified P1-P4 all FIXED live ✓
- ✅ P1 form controls light · P2 board centered · P3 pill small · P4 onboarding intro hugs content — all confirmed on cloud.
- ✅ Functional: sent "email Priya + grab milk" → TWO clean cards; vent ignored, $4200 held, call-mom task — proactive + money-safety proven live.
- ✅ /connect: light, clean, grouped rows, honest copy — good.
- ✅ /settings: grouped inset + gold pill switches — good.

### New findings (round 2):
- **P5 (DECISION) — /welcome is DARK, rest of app is LIGHT.** Land on a dark serif hero → "Come in" → cream app. Either unify welcome to light (full consistency) OR keep a deliberate dramatic dark hero. Needs Omar's taste call.
- **P6 (LOW) — copy: heard-quote says "remind WEARER to…" not "you".** Engine transcription artifact. Fix the pronoun in the card/observed-line copy.
- **P7 (LOW) — /welcome logo "Anticipy" top-left is low-contrast** (dark on dark gradient).
### Still to QA: /sign, /setup, mobile/narrow, motion, every card action (Confirm/Not-now/Autonomy/Note) end-to-end.

## Round 3 QA (2026-07-04) — remaining screens verified
- ✅ /sign — clean light card, light inputs, "Come in. One account, everywhere." Good.
- ✅ /setup — "Let's get you set up.", grouped readiness rows, honest copy, clear install steps, small Live pill. Good.
- ✅ Onboarding persistence FIXED + proven live (engine /owner/profile) — profile sticks.
- Net: every screen clean/on-theme EXCEPT the open decision:
  - **P5 (Omar's call) — /welcome DARK vs app LIGHT.** P7 (welcome logo contrast) rides on this. Held for Omar.
- **UI is in genuinely good shape.** No functional/visual blockers remain besides Omar's welcome-theme taste call + his own testing feedback.

## Round 4 QA (2026-07-04) — conversation loop + edges
- ✅ Conversation loop proven live end-to-end: talk → assistant bubble + chips → tap Go ahead → "On it…" → "Done — taken care of. ✓"; typed "yes" resolves too; vent → silent (no bubble). Chips render cleanly across re-seeded thread.
- 🟡 P8 (LOW) — the "…" autonomy chip shows NO visible menu/feedback on tap (thread just scrolled). A consumer taps it → nothing apparent. Give it a clear popover ("Always okay to do this kind" / "Ask me each time") or visible toast.
- 🟡 P9 (INFO) — mobile/narrow QA blocked: the Chrome screenshot renders at a fixed ~1425px regardless of window resize, so couldn't visually verify the phone layout. Needs a real device/devtools check (the composer + bubbles look fluid, but unconfirmed on <430px).
- Note: thread shows accumulated test asks (ephemeral cloud data) — a genuinely fresh user starts at the calm "I'm listening…" state.

## Round 5 QA (2026-07-04) — P8 RESOLVED (false alarm)
- ✅ P8 NOT a bug — the "…" chip opens a clear popover ("Go ahead — and stop asking for these"); clicking it posts as your line AND replies "Got it — I'll take care of these without asking from now on. You can change that anytime in settings." My earlier tap just missed the popover. Autonomy control is clear + conversational + honest.
- Net: EVERY conversation control verified live — talk-back, Go ahead/Not now chips, "…" autonomy menu+feedback, tap→confirm→act→report, type yes/no, money flagged, vents silent.
- Remaining open: P5 welcome dark/light (Omar's call), P9 mobile layout unverified (tooling limit). No functional gaps.
