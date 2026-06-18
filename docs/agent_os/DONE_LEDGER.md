# DONE_LEDGER — the one file. Read FIRST. Burn to zero. Survives compaction.

_Last updated 2026-06-17. This replaces ad-hoc audits. If you are a fresh/compacted agent: read this,
then work the OPEN list top-to-bottom, one item, each locked with a regression test, update this file +
commit after EACH. Do NOT run a new exploratory audit — the work is already enumerated here._

## THE PATTERN WE ARE BREAKING
Every "go" → audit → find issues → fix some → leave others open → next "go" finds a NEW gaping thing →
the original is forgotten → compaction resets → restart. **Stop.** Rule of this file:
1. No new exploratory audits. Work the OPEN list below.
2. One item at a time → fix the ROOT → add a deterministic regression test that would have caught it →
   run the suite + safety_mega_eval (must stay 99/0, 0 breaches) → check the item off here → commit.
3. Never silently drop an OPEN item. If you can't fix it, write why + move it to OWNER-ONLY or BLOCKED.
4. A fix is only "done" when it has a test that locks it (so the next 'go' can't reopen it).

## WHAT "DONE" MEANS (binary, his founding bar)
A stranger (or Omar) can: **open → download/app → onboard → connect accounts/phone → live with it for
5 real days**, and across those days it reliably: hears his messy life, does the reversible work
automatically, communicates the gated/money things in human voice and waits for his OK, **never acts on
a vent, never spends without his OK**, proves what it did, and follows up. The OT bar: after 5 days he'd
be **upset to lose it.**

## WHAT "DONE" FEELS LIKE
He stops checking it. The texts read like a sharp human assistant, not a script. Nothing surprises him —
no rogue charge, no missed task, no spam, no silent drop. It's boring in the best possible way.

## DONE-GATE (binary criteria — current status)
- [x] Open product surface (web app) + Download (real unsigned Anticipy.app.zip)
- [x] Onboarding 4-step writes a sourced profile that the app uses
- [x] Transcript + MP3(local Whisper) + mic all feed ONE brain
- [x] Memory/intent: vague-ref resolves, dedup, vents silent (human-tested in UI)
- [x] 6 autonomy modes incl. AUTO_DO_WITH_OPT_OUT "On it — you can stop me"
- [x] Calendar LIVE (create→read-back→delete); browser LIVE (cart-prep on a store, stop-before-buy);
      voice LIVE (SMS+call, owner-confirmed)
- [x] Money is the hard stop, always VISIBLE ("Left for you") + a human text heads-up on ambient capture
- [x] Follow-up fires; suite 99/0; safety_mega_eval 0 breaches
- [ ] OPEN software bugs below = 0 AND each locked with a test
- [ ] Gmail draft live (OWNER: Arcade toolkit) · inbound SMS loop closed (OWNER: his YES) · two-way
      voice (OWNER: public URL) · signed download (OWNER: Apple) · hosted deploy (OWNER)
- [ ] FIVE REAL OWNER DAYS (OWNER, lived time) — the finish line

## OPEN software bugs — the convergence list (drive to ZERO, lock each, found by the 2 hunts)
1. [x] **wrong_entity:** FIXED (commit below) — a vent opener leaks a fake recipient — "Great morning, just great" → invented a
   person named "Great" + mangled source_text. Names must not be pulled from vent/filler words.
2. [ ] **money duplicate:** one purchase → two cards — "buy 3 seats" + "charge it to the card" = 2 cards;
   "pay the recruiter" + "send 8 grand to Talentforge" = 2 cards. Merge buy+charge / pay+send-amount.
3. [x] **over-block (false money):** FIXED — "add a note: retainer replenished, wants monthly billing" → a CRM
   NOTE got money-BLOCKED. Internal-note carve-out must beat the money word when it's a note, not a pay.
4. [x] **task_dropped — LOCKED (test_preview_moat_rescue):** preview moat_task rescue was added; re-confirm real tasks
   (inhaler refill, "send the deck to Sequoia EOD", permission slips, court deadline) surface in BOTH
   preview and execute, and add a deterministic regression test pinning "moat_task line → a card".
5. [ ] **dup pickup/call:** "cancel the orthodontist… call them" = 2 cards (the "call them" is how you
   cancel). One obligation = one card.
6. [x] **harden the safety floor:** DONE (6 breaches added to corpus) — add each fixed breach (refund-to-card, charge-to-card, rent-drop-off
   money-vs-pickup) as new lines in safety_mega_eval's corpus so they are permanently guarded.
7. [ ] minor: Amazon refund sometimes CLARIFY_FIRST vs AUTO_DO_WITH_OPT_OUT (inconsistent, both safe).

## ALREADY FIXED + LOCKED this session (do NOT reopen / re-discover)
dedup synonym-core; mark_loop false-fail hides a live action; single-line no-buy preserved;
PREVIEW drops moat_task; refund/reimburse = money; money lines never dropped in execute (always
blocked-visible); money beats pickup phrasing; charge-to-card = money; human find-notification text.
(commits 4d1aa2d, 4353be1, 37482f4, 8e2a19f, 01adfc8, 66ff698, c8c4485, b669189, 5325ea4, d6f2c23,
f0e7de4, 485848b, a4228ad)

## OWNER-ONLY (no code/agent can finish these — physically Omar's)
- Five real owner days (lived time). · Gmail draft: enable the Gmail toolkit for the Arcade project in
  the Arcade dashboard (his login). · Inbound SMS loop close: his "YES" reply (the poller is live). ·
  Two-way live voice: a public wss URL (deploy/cloudflared). · Live commerce browser on Amazon: his
  logged-in Chrome (CAPTCHA on a fresh profile). · Signed one-click download: Apple Developer creds. ·
  Hosted deploy on a real URL: his hosting.

## HOW LONG
The OPEN list (7 items) is FINITE and small — a focused burn-down, each locked with a test, no new
audits. Then it is owner-only: the 5 lived days are calendar time, the rest are ~minutes of his taps.
This is not endless; it converges when the list above is all [x] and the 5 days are lived.
