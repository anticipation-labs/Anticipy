# Anticipy — The Plan (verified, 2026-06-23)

> One canonical doc. Built from **actually running** each component on this Mac (not reading docs),
> plus Omar's rules from the 2026-06-23 session. Supersedes the older STATUS/DONE/MISSION docs.

---

## A) WHAT WE'RE BUILDING (Omar's words, captured)

**Fully Done =** a hosted, live website anyone can visit (anticipy.ai or a fresh Vercel) →
**premium, clean welcome** ("here's what Anticipy is", looks $45k-assistant, NOT owner-mode ugly) →
**onboarding** = layered scrape #1 → phone call #1 → scrape #2 → call #2 → (#3, final if needed) →
**confirmation** → **main app**: Listen / MP3 / Paste + a **swipeable card deck** (confirm / deny /
allow / feedback, self-improving) → a **proactive brain that's flawless** + a **browser agent equally
good** → it **talks like a human** (never `task #24a`, never formulaic, feels like a person at a desk)
→ it **goes the extra mile** every time → **horizontal** (any profession). Backend impeccable, nobody
notices because it's that good.

**The new rules (this session):**
- **Human copy.** No task-IDs, no templates, never the same line twice. "I parked the $4,200 invoice —
  say the word and I'll pay it," not "Block money action."
- **Go the extra mile.** The plant-return example: hears it → opens *your* logged-in Chrome → finds the
  item → pulls context/memory → does the reversible work → even calls Amazon to negotiate a returnless
  refund → confirms the one irreversible button with you. A `do`-card carries **real work product**
  (candidates, drafted message), never a bare label.
- **Three autonomy modes:** **Full-Send** (does whatever; pre-consent / approve-once; trust builds over
  time) · **Regular** (does most, keeps you in the loop) · **Limited** (only a couple tasks, asks more).
  Set during onboarding/calls. **Override in every mode:** money / send-to-a-human / delete / binding =
  confirm; below the confidence floor, every mode drops a level.
- **Only contact when needed.** Ambient → digest → push → text → call. A *call* only for
  irreversible-if-missed + hard deadline + you didn't answer the text.
- **Premium real-time voice** that you can never tell is AI (the phone calls).
- **Money / irreversible = always confirm.** That's the trust floor, not a limitation.

---

## B) WHERE WE ARE (verified by running it, 2026-06-23)

**Base CONFIRMED: `~/Anticipy/engine` (factory/build)** — the only live, persistent, end-to-end build.
**DEV-FINAL is a parts donor**, not a competing base.

| Component | Score | Reality (from a real run) |
|---|---|---|
| Memory (4-drawer) | **7.5** | Recall proven: "text Maya" surfaced "Maya prefers texts after lunch". Fix: `/memory/drawers` 404, dedupe, fold recall into the card. |
| Proactive brain | **6.5** | Strong (third-party strip, money-park, sarcasm-ignore). **Bugs:** money-flag bled onto "pick up the kids"; "dinner, no restaurant" auto-done instead of asking; copy templated; do-cards return null (no extra-mile). |
| Browser agent | **6.5** | Real vision agent, no recipe. **Bug:** returned `success:true` on a task it failed (hit a wall) instead of pause→text-you→resume. |
| DEV-FINAL extractor | **7.0** | Cleaner typed slots but **single-intent** (dropped the $4,200 when bundled). |
| Voice | **0** | Not built. |
| UI | **0** | Nothing hosted. |

**Graft from DEV-FINAL → base:** (1) the **structured intent-extractor** (made **multi-intent**, dead
cascade dropped — gemini-2.5-flash won 10/10 live); (2) **`cdp_walker` stealth scrape** (drives your
real logged-in Chrome over CDP — for onboarding scrape AND browser wall-recovery).

**Twilio:** creds valid + funded (200, "Anticipy", Full account). One safe env fix from live. Not
flipped to real-send without Omar's go.

---

## C) THE ROAD TO FULLY-DONE (milestone-gated, each has a pass/fail proof)

- **M1 — Brain correctness (graft + fix). ~1wk.** Multi-intent splitting; scope money-flag to the
  clause; missing-slot→ask; ignore-trace. *Pass:* the 6-line battery — kids=do, $4,200=confirm,
  vent=ignored(logged), dinner=ask-for-slot, plant/Sarah/judgment handled; **$4,200 never dropped.**
- **M2 — Human-copy engine + go-the-extra-mile. ~1wk.** One render layer, zero IDs/templates on
  surfaces; do-cards carry real work product; memory facts fold into cards. *Pass:* 20 cards, no
  UUID/"Confirm task:" leaks; dinner card shows real candidate spots.
- **M3 — Autonomy modes + trust ledger. ~1.5wk.** Full-Send/Regular/Limited dial; per-task-type trust
  promote/demote; pre-consent tokens; both invariants enforced. *Pass:* coffee task promotes after 5
  clean reps; a $4,200 spend stays CONFIRM in *every* mode.
- **M4 — Browser honesty + wall handoff. ~1.5wk.** `task_succeeded` via `/agent/judge`; wall →
  pause→text→`/agent/resume`; mode param escalates to cdp_walker. *Pass:* re-run a walled task — real
  answer OR `needs_human`+text; **never** a false success.
- **M5 — Stealth onboarding scrape. ~1wk.** cdp_walker pulls your real accounts. *Pass:* a logged-in
  scrape returns structured data, zero credential-typing by the agent.
- **M6 — Premium voice. ~1.5wk.** ElevenLabs Conversational AI via Twilio ConversationRelay; the
  onboarding calls are real. *Pass:* 3/3 blind listeners can't tag it as AI; sub-second turns.
- **M7 — Frontend: welcome → onboarding → cards. ~2.5–3wk.** Hosted, editorial visual system,
  pre-filled progress onboarding, swipe deck wired to the live engine. *Pass:* a stranger completes the
  whole flow on the public URL and swipes real cards.
- **M8 — Hosting + hardening. ~1wk.** Off localhost, secure secrets, per-user data. *Pass:* works from a
  phone on cellular with no laptop running.
- **M9 — The trust bar (continuous, partly beyond-frontier).** Fully-autonomous real-commerce action is
  ~40–65% raw today; you **engineer around it**: deterministic macros for the top ~20 flows +
  self-verify judge + real-Chrome CDP + **human-confirms the one irreversible button.** Promise =
  *"goes the extra mile, you approve the one button that matters."*

**Honest total: ~10–13 focused weeks.** M1–M8 buildable now on the verified base + 2 grafts.

---

## D) THE NEXT COUPLE OF THINGS TO TACKLE (start here)

1. **M1 — make the brain correct.** It's the foundation; nothing else matters if the brain mis-reads
   the day. Fix the money-bleed, add missing-slot→ask, graft the multi-intent extractor. Proven against
   your 6-line battery. **(Recommended first.)**
2. **M2 — the human-copy + extra-mile layer.** This is the first thing that will *feel* like the product
   you described — no task-IDs, real work product on cards. High emotional payoff, builds on M1.
3. *(then)* **M3 — the three autonomy modes**, once the brain is right and speaks human.

One at a time, Omar leads. Each lands with a replayable proof, never a "trust me it's done."
