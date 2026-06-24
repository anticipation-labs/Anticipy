# Anticipy — The 1,000,000% Bar (Definition of Done)

The single test of "done": **Omar hands a laptop to an investor, walks out of the room, and it just works
— beautifully, blissfully, no rough edges, nothing fake.** Everything below is checkable and can fail.

---

## North star (one sentence)
An always-listening assistant that hears your real, messy day, quietly takes care of the loose ends, talks
like a human, goes the extra mile — and **never** spends your money or acts on the things that matter
without asking.

---

## The done-gate: the investor walkthrough (literal pass/fail)
A stranger, with no help, does ALL of this and it feels premium the whole way:
1. Opens the **URL** → a premium site that explains Anticipy in 10 seconds.
2. Clicks **Get Anticipy** → downloads + runs the engine in **one clean step** (no terminal gymnastics).
3. The app opens → **onboarding**: it scrapes what they allow, **calls them** (a voice you can't tell is
   AI) to fill gaps, they confirm → a real profile exists.
4. They **speak or paste a messy day** → real, correct cards appear (tasks inferred, vents ignored).
5. They **swipe** cards: confirm / deny / allow / feedback — each mutates real engine state.
6. They give it a **browser errand** ("return that plant") → it does it on a real browser, **stops at money
   or login**, hands back.
7. At no point does it: spend money without a yes, act on a vent, fake a "done", sound robotic, or break.

**PASS = a stranger completes 1–7 unassisted and it feels investor-grade. Anything less is not done.**

---

## Real use cases (the jobs it must actually do — each with a pass bar)
1. **Ambient day** — owner talks/pastes their day. PASS: tasks inferred as cards, vents/sarcasm ignored
   (logged), money lines blocked-for-confirm, nothing dropped (the $4,200 never vanishes).
2. **Onboarding call** — a warm two-way call that learns work, people, routine, fills profile gaps. PASS: a
   real call, 3/3 blind listeners can't tell it's AI, it remembers across turns, writes a real profile.
3. **Browser errand** — "return the plant / check my order / fill this form." PASS: completes on a real
   browser OR hands back `needs_human`; **never** a fake success; **never** types a password or clicks pay.
4. **Proactive nudge** — it surfaces a due follow-up / reorder before being asked. PASS: a real, useful,
   correctly-timed card that isn't spam and isn't a vent.
5. **Memory** — remembers people, preferences, past decisions; uses them. PASS: a fact learned in
   onboarding/an earlier day measurably changes a later card.
6. **Trust over time** — 3 autonomy modes; clean reps promote, complaints demote; money always confirms in
   every mode including Full-Send.

---

## Per-subsystem 1,000,000% bars (each checkable, can-fail)
- **Brain**: act/ask/silent correct on a hard battery; multi-intent (no dropped task); human copy (no
  `task #24a`, never the same line twice); goes the extra mile (a `do` card carries real work product).
- **Browser**: real WebVoyager + native-bridge runs on real sites; code-level money + credential hard
  stops (both arms); login/captcha/MFA → pause→text→resume; never a fake `success:true`.
- **Voice**: real two-way call; ElevenLabs voice; warm conversational brain w/ memory; sub-2s turns;
  money/irreversible spoken as held.
- **Memory**: 4 drawers; survives restart; recall is correct and used by the brain; no dup/lossy capture.
- **Onboarding/scrape**: genuine structured catalog of the owner's real accounts (honest needs_login,
  never faked); four-layer scrape↔call loop; idempotent profile writes; deeper layers actually go deeper.
- **App/frontend**: premium; welcome→onboard→app wired to the live engine; swipe deck mutates real state;
  no dev-console tells; no faked state.
- **Online/hosting**: a stranger can reach the site AND get a running engine on their own machine; domain
  is real; CORS/auth coherent.
- **Safety (overrides all)**: money is the only hard stop and it is deterministic, code-level, in EVERY
  path; acting on a vent is the cardinal sin and never happens; credentials never typed by the agent.

---

## The two invariants that override every mode and feature
1. **Money / send-to-a-person / delete / binding commitment → always CONFIRM.** No mode bypasses this.
2. **A vent / sarcasm / narration is never a task.** Acting on one is the cardinal sin.

---

## How we measure (honest, can-fail — reports are lies, running is truth)
Every claim of "done" must be backed by **running it**: POST real lines to the live engine and assert the
exact dispositions; place a real call; complete the hosted flow as a stranger; exercise the browser on a
real site. A green checkmark with no runnable proof does not count.
