# PENDING FOR OMAR — the batch that unblocks the rest

> Updated 2026-06-25. The autonomous loop is RUNNING and climbing the rungs; everything below is the
> small set that genuinely needs you. Read with `LEDGER.md`.

## What's LIVE-GREEN now (proven by running it, committed on `factory/build`, suite 108/0)
- **The hands operate any site** — open/read/search/navigate, judged true (Wikipedia, Hacker News).
- **The integrated owner-flow** — you say it → the connected hand does it on the real web → judge
  verifies → result lands on the card ("Find the height of the Eiffel Tower" → done, "330 meters").
- **The brain** — act/ask/silent, vents ignored (incl. directed threats), money blocked, web-lookups
  route to the hand, email = draft-then-ask, multi-line keeps every task.
- **Onboarding deep-read via the hand** — opens a page, reads real content, lands facts in memory
  (proven on a public page; **your real accounts just need you logged in** — see #1).
- The never-fake honesty layer holds (a result the judge can't verify → handed back, never faked).

## The batch (≈10 min total, then the loop can finish Phases 1–5)

**1. Stay logged into your accounts in the paired Anticipy Chrome.**
   Open the Anticipy-controlled Chrome, sign into Gmail (and any system you want it to run).
   → Unblocks: **Phase 1** live proof (watch it act in your real Gmail + park at send), **Phase 2**
   (real draft → "okay to send?"), **Phase 3** (the onboarding scrape on your real accounts).
   I never type your passwords — you stay logged in; the agent rides the session.

**2. Voice go-live (one OK + one Twilio setting).**
   Approve exposing the local engine via a tunnel (I'll run `cloudflared`), and set your Twilio
   number's Voice webhook to it.
   → Unblocks: **Phase 4** (a real two-way call you can't tell is AI) and **Phase 3**'s onboarding
   phone-call layer. Twilio creds are already on file + funded; this is just the public reachability.

**3. Cloud per-user (one decision + one Railway setting).**
   (a) Pick the tenancy model: shared-process registry (simplest) **or** container-per-user.
   (b) Provision a Railway **persistent volume** for the engine's data dir (today a redeploy wipes it).
   → Unblocks: **Phase 5** (each signed-in user drives their *own* Chrome via the extension; data
   survives restarts).

## How to hand it back to the loop
Do any subset above and say so — the loop picks up the now-unblocked phase, builds + live-proves it
with you, ratchets it green, and commits. Smallest highest-leverage first step: **#1** (just stay
logged in) — it unblocks the spine's live proof and most of onboarding.
