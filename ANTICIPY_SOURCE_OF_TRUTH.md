# ANTICIPY — THE SOURCE OF TRUTH

> The single canonical document. What Anticipy is, how it **actually** works, the real use cases,
> what "fully finished" genuinely means, where we honestly are, and the plan to get there.
> Supersedes every other status/mission/done doc (CURRENT_STATE.md, THE_BAR.md, the factory docs).
> Captured 2026-06-24 from Omar's whiteboards (IMG_2942, IMG_3029) + his direct corrections.
> If anything here is wrong, **fix it here** — don't fork a new doc. Newest dated line wins.

---

## 0. THE ONE SENTENCE

Anticipy is a **proactive personal assistant — "Donna from Suits"** — that **listens to your real day**,
catches the things you get **told or asked to do**, and quietly **handles them inside your own real
systems** (your logged-in browser, calendar, email, voice), checking with you like a sharp human
before anything that matters. The goal: it genuinely runs **~50% of your workload, end to end.**

---

## 1. HOW IT ACTUALLY WORKS (the model — get this right)

1. **It LISTENS — ambient.** Input is your *real life*: conversations, what people tell/ask you to do,
   the commitments you make out loud. Typed transcript / MP3 now; a pendant later.
   - ❌ NOT a todo app. Nobody says "ugh traffic, remind me to call the dentist."
   - ✅ Real: a client says *"can you get me the contract before Friday?"* → Anticipy catches the task.
2. **It INFERS the real tasks** from natural speech, and **silently lets non-tasks pass** — venting,
   sarcasm, hypotheticals. It does not announce "ignored." It just doesn't act. **Acting on a vent is
   the cardinal sin.**
3. **For each real task it decides:** handle it / prepare-and-ask / stay silent — by confidence,
   reversibility, and the trust dial.
4. **It TALKS like a human, never like a system:**
   - Money → *"Hey, I heard this involves money — want me to go ahead, or hold off?"* (NEVER "BLOCKED").
   - Send (email/text) → it **drafts it**, then *"Got the email to Sanket ready — okay to send?"*
   - It goes the extra mile: does the prep, hands you the finished thing for one tap.
5. **It ACTS in YOUR real systems via the browser** — navigating, opening items, clicking, *operating
   like a human* (NOT screenshotting one screen). Browser-only by design; no per-service OAuth.
   Plus voice/SMS to reach you and close the loop ("draft's ready", "made the calendar hold").
6. **It REMEMBERS everything** — who matters, your preferences, open loops — and compounds over time.
7. **Trust dial: Full-Send / Regular / Limited.** Money + irreversible **always** confirm, every mode.

---

## 2. ONBOARDING = THE WHOLE SYSTEM AT ONCE

New user → **Welcome** → it **learns you** by actually exploring your real accounts (browser agent) ↔
**phone call(s)** to fill the gaps it can't infer → **confirm** → you're live.
Onboarding exercises **every** part — browser agent, engine, memory, proactive, voice, the human-
confirm UX. **If onboarding is genuinely real, the product is real.** That's why it keeps being the
hard thing: it can't be faked one piece at a time.

---

## 3. REAL USE CASES (the corrected model)

- **[mom, at home] "return that plant to Amazon"** → opens Amazon in *your* Chrome, finds the order,
  starts the return, *calls Amazon* if a returnless refund is better, parks before anything
  irreversible, tells you it's done.
- **[client email] "send me the contract by Friday"** → drafts it → *"okay to send?"*
- **[colleague] "let's grab a 1:1 Tuesday"** → finds a slot, prepares the invite → *"want me to send?"*
- **[work, a real CRM/EMR — Salesforce, HubSpot, Toddle, a patient record]** → operates the actual
  system like a human would, browser-only, parking at the irreversible step.

---

## 4. WHAT "FULLY FINISHED" MEANS (the bar — non-negotiable)

You hand it to a stranger (or an investor). They get onboarded. From then on it genuinely runs
**~50% of their real workload across their real systems, end to end, over multiple real days** —
talking like a human, never acting on a vent, always confirming money/irreversible — and they'd
**pay a real human** to do what it does. **Every capability is provable** (watch it / replay it),
never just claimed. Horizontal: any profession. Setup scales from very simple to ultra complex.

---

## 5. WHERE WE HONESTLY ARE (no spin — 2026-06-24)

**Real + proven (ran it, read the output):**
- The brain: infers tasks, ignores vents, confirms money. (Live test today: vent ignored, $4,200
  held with a "check with you first" message, Sanket email recognized.)
- Per-user cloud accounts (Railway engine + Supabase + Vercel) — A genuinely can't see B.
- Memory (4 drawers) + the scrape→memory loop (real facts about Omar persisted).
- Site ↔ engine connection.

**Real but SHALLOW — the #1 gap: THE BROWSER AGENT.**
- Onboarding's "scrape" only reads the **first visible screen** and scrolls/screenshots. It does NOT
  open emails, click in, navigate, or *operate*. That is not a real browser agent.
- The agent that actually OPERATES arbitrary real systems reliably is the hardest, least-finished
  part — and the spine of the whole product.

**Bugs found by testing today (honest):**
- Multi-line input **drops a task** (the "dentist" reminder vanished when bundled) — splitter bug.
- Email path returns `do` instead of **draft-then-ask**.
- Money copy is close but must be the warm *ask*, not a `blocked` status surfaced to the user.
- Open-loop **dedup** (the Sanket follow-up was written 3×).

**Not done:** real browser *operation* depth; onboarding wired to it; voice turned on; hands-in-cloud
per-user; the multi-day reliability bar.

---

## 6. THE PLAN TO GET THERE (ordered; each provable by running it)

1. **THE BROWSER AGENT — make it actually OPERATE.** Navigate, open items, click, explore, read the
   real thing, verify it worked — not screenshot-and-scroll. The spine; the biggest gap.
   *(engine/anticipy_engine/agent/webvoyager.py, core/browser_link.py, extension/background.js)*
   **Proof:** point it at real Gmail → it opens an email, reads the body, comes back with the actual
   content; point it at a task → it completes the steps, parks before send.
2. **Brain copy + flow corrections.** Email = draft-then-ask; money = warm ask (not "blocked"); fix
   the multi-line drop; dedup open loops. *(core/control_core.py, core/voice.py, owner_mode.py)*
   **Proof:** re-run a real multi-task day → every task survives; email lands as a draft + "okay to send?".
3. **Onboarding = wire the REAL browser agent** to actually explore your accounts + the phone-call
   loop + confirm. *(onboarding/*, web/onboard.js, channels /cr)* **Proof:** click through onboarding,
   watch it open and read your accounts, take a call, confirm — no flashing, no screenshot-only.
4. **Hands in the cloud, per-user** (extension carries your identity, drives only your Chrome).
5. **Voice on** (point /cr at the cloud, flip channels live carefully).
6. **The reliability grind + the multi-day owner test = the finish line.**

---

## 7. HOW WE WORK (so it stops going back to zero)

- **Verify by running, never claim.** Show real input → real output.
- **Commit every real win** — no evaporation back to 40%.
- **One engine, one extension** — no copy/repo chaos (a stale engine squatted port 8787 for a whole
  session; that's the kind of thing that eats the work).
- **This document is the source of truth.** Update it as reality changes; never fork a parallel doc.
