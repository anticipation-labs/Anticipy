<!-- CANON v1 · written 2026-07-02 by the HoE agent (post-Devin) · NEW documentation, not Devin's.
     On conflict with any doc outside CANON/ (except MISSION_LOCK.md for live mission status), THIS file wins. Fix errors HERE — never fork. -->

# 01 · WHAT ANTICIPY IS

This is the product truth for the whole system. It compresses two source documents in this repo —
`ANTICIPY_SOURCE_OF_TRUTH.md` (§0–§2, captured 2026-06-24 from Omar's whiteboards) and
`ANTICIPY_DONE_VISION_2026-06-15.md` (Part 1) — verified against both files on 2026-07-02.
CANON/ is timeless truth; for what we are building *right now* and how far along it is, read
`MISSION_LOCK.md`.

---

## 1. THE ONE SENTENCE

Quoted verbatim from `ANTICIPY_SOURCE_OF_TRUTH.md` §0 (it's already right — do not paraphrase it):

> Anticipy is a **proactive personal assistant — "Donna from Suits"** — that **listens to your real day**,
> catches the things you get **told or asked to do**, and quietly **handles them inside your own real
> systems** (your logged-in browser, calendar, email, voice), checking with you like a sharp human
> before anything that matters. The goal: it genuinely runs **~50% of your workload, end to end.**

Proof it's unchanged: `grep -A5 "THE ONE SENTENCE" ANTICIPY_SOURCE_OF_TRUTH.md`

---

## 2. HOW IT ACTUALLY WORKS — THE 7-POINT MODEL

(Compressed from SOURCE_OF_TRUTH §1. Get this model right and everything else follows.)

1. **It LISTENS — ambient.** Input is your real life: conversations, what people tell or ask you to
   do, commitments you make out loud. Typed transcript / MP3 now; a pendant later. It is NOT a todo
   app — nobody says "ugh traffic, remind me to call the dentist." Real: a client says *"can you get
   me the contract before Friday?"* and Anticipy catches the task.
2. **It INFERS the real tasks** from natural speech — and silently lets non-tasks pass: venting,
   sarcasm, hypotheticals. It never announces "ignored"; it just doesn't act.
   **Acting on a vent is the cardinal sin.**
3. **For each real task it decides:** handle it / prepare-and-ask / stay silent — weighed by
   confidence, reversibility, and the trust dial (point 7).
4. **It TALKS like a human, never like a system.** To send an email or text, it drafts it first, then
   asks: *"Got the email to Sanket ready — okay to send?"* It goes the extra mile — does the prep and
   hands you the finished thing for one tap.
5. **It ACTS in YOUR real systems via the browser** — navigating, opening items, clicking, operating
   like a human (not screenshotting one screen). Browser-only by design: no per-service API keys or
   OAuth, nothing hardcoded to one service. Voice/SMS is how it reaches you to close the loop
   ("draft's ready", "made the calendar hold") — the comms channel, not the action arm.
6. **It REMEMBERS everything** — who matters, your preferences, open loops — and compounds over time.
7. **Trust dial: Full-Send / Regular / Limited.** Money and anything irreversible **always** get a
   confirmation, in every mode, no exceptions.

---

## 3. A DAY LIVING WITH IT

(The scenes from DONE_VISION Part 1, compressed. This is what "done" feels like.)

**9:14am — the catch you didn't expect.** On the phone with your sister you half-complain:
*"...and I still have to get Mom's prescription before the pharmacy closes Friday."* You weren't
talking to Anticipy; you forgot it was there. That evening's digest holds one line: *"Caught: pick up
Mom's prescription before Fri 6pm. Want me to set a Thursday reminder?"* It heard an obligation
buried three clauses deep in speech aimed at someone else.

**1:30pm — the quiet when you vented.** Bad meeting. You mutter: *"Honestly I should just quit and
move to the woods."* Nothing happens. No draft resignation, no job-search tab, no "I noticed you
mentioned quitting." The silence is engineered — it is the most important feature in the product.

**2:45pm — the promise kept on time.** This morning your wife said in passing, *"can you grab the
kids at 3?"* You got one tight line then — *"Got it. I'll call you at 2:45 so you're not late."* Now
your phone rings: a warm human voice, not a robot. The loop closed exactly where it mattered.

**6:30pm — the calm report.** Not twelve pings across the day. One digest: *"Here's what I handled
and what's waiting on you."* Three things done silently, one thing waiting for your yes, nothing
screaming.

**The three feelings, in order** (named precisely in DONE_VISION — not "delight", not "magic"):
1. **Unburdened** — the weight of remembering left your body without you noticing.
2. **Caught** — someone competent was watching your life when you weren't.
3. **Safe enough to forget it's there** — you trust it *because* it stayed silent on the vent.

---

## 4. THE LITMUS

Verbatim from `ANTICIPY_DONE_VISION_2026-06-15.md` ("The one-line litmus"):

> **You know it's done when you vent about quitting your job and nothing happens — and twenty
> minutes later it quietly reminds you about your mom's prescription that you mentioned to someone
> else.** Silence on the vent, the catch on the buried real task: both in the same hour. That
> contrast *is* the product.

---

## 5. ONBOARDING IN ONE PAGE

(Compressed from SOURCE_OF_TRUTH §2. Onboarding is not a setup wizard — it's the first time the
whole product runs at once, on your real life. It ends when Anticipy knows you well enough to do
half your job, and its deliverable is a rich structured profile, not "connected accounts.")

**The spine — a layered scrape ⇄ phone-call loop** ("scrape" = the agent reading through your real
accounts in the browser; each scrape feeds the next call, each call re-aims the next scrape):

1. **Layer-1 scrape (guided, broad).** You connect Google + give a phone number — that's the whole
   ask. The agent opens Gmail and reads the last ~2–4 weeks, opening the threads that carry weight
   and **reading them to the bottom — not screenshots**. It opens Calendar events (bodies, attendee
   lists, attachments) and Contacts, and notes every tool it spots in the wild (Notion, a CRM,
   Stripe) as a Layer-2 target. Output: a provisional profile plus a list of gaps — the agenda for
   Call 1.
2. **Call 1 — the warm intro.** Human voice, hand-held. It proves it actually looked (one concrete,
   correct observation), confirms the people who matter and the role it inferred, **sets the
   autonomy dial** (Full-Send / Regular / Limited), locks the money + irreversible always-confirm
   rule, captures do-not-touch zones, and gets explicit permission to go deeper.
3. **Layer-2 scrape (deeper, autonomous, re-aimed by Call 1).** Months back, not weeks, for the
   people who matter. It **picks its own next clicks from what it discovered** — opens the Notion
   and reads the docs the team lives in, opens the CRM pipeline, follows a thread → to a contract
   doc → to a Q3 renewal → to a calendar check → to a gap worth raising. Output: the real catalog —
   person dossiers, tool inventory, open loops, an evidence-based writing-style model — plus a
   smaller set of genuine gaps.
4. **Call 2 — fill the true gaps.** Shorter, peer-to-peer. Only what reading can't tell you:
   priorities, real ambiguities, drafting preferences, and situation-level autonomy rules calibrated
   on real examples ("auto-nudge overdue invoices, or always ask?").
5. **Layer-3 scrape (only if needed).** Surgical and fully autonomous — goes only where Call 2
   pointed (a named tool, an under-read person), not broad again.
6. **Final mirror call.** The agent reflects you back to yourself — people, priorities, open loops,
   where your work lives, how it will write like you — states the operating contract, and gets your
   explicit "yes, run."

**The five principles** (SOURCE_OF_TRUTH §2.0):
- **Layered, not one-shot** — the loop runs until confidence is useful, not a fixed step count.
- **Earned autonomy** — starts hand-held with you watching; ends self-driving with you trusting.
- **Infer first, ask only for the gaps** — it never asks a question it could have answered by reading.
- **Read-only during onboarding** — it catalogs; it sends nothing, changes nothing. The only
  outbound contact is the agent → you phone call. This is what makes deep access safe to grant.
- **Human voice the entire time** — never "SCRAPE LAYER 2 COMPLETE."

**The named anti-pattern — the screenshot-one-screen fake scrape.** The cardinal failure of a fake
agent: open the account, screenshot the first screen, scroll once, declare it "reviewed." That tells
you an inbox exists; it tells you nothing about the person. Anticipy's test: after Layer-1 it can
say a true sentence about the *content* of your life, not "Gmail: connected, ~40 unread."

---

## 6. REFERENCE POINTERS

- **The 120 use cases** (real ambient triggers across every profession, in the corrected model):
  `ANTICIPY_SOURCE_OF_TRUTH.md` §3 — `grep -n "## 3. USE CASES" ANTICIPY_SOURCE_OF_TRUTH.md`
- **The full feel spec** (design language, cadence numbers, trust guardrails, roadmap logic):
  `ANTICIPY_DONE_VISION_2026-06-15.md`, all three parts.
- **What "fully finished" means and the live plan:** SOURCE_OF_TRUTH §4–§7, superseded for live
  status by `MISSION_LOCK.md`.
- Everything else in the repo is archive — see `CANON/99` for the index.
