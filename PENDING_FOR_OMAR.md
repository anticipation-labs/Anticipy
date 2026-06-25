# PENDING FOR OMAR — the batch that unblocks the rest

> Updated 2026-06-25. **The product PASSES the un-fakeable done-gate** — a realistic day run end-to-end
> scores 0 cardinal-sins, money held, vents silent, tasks caught (`owner_test_run --key day01.json`,
> now permanent in the suite, 110/0). The two things left both need YOU. Read with `LEDGER.md`.
>
> **#0 — The whole product passing the gate is the headline.** It decides a real day correctly, the loop
> closes for tasks that reach the hand (Eiffel→done, a real Gmail draft flushed, onboarding learned from
> your real accounts). What remains is (A) one routing-reliability POLISH that needs a careful supervised
> pass (thrashing the core brain unsupervised breaks it — proven this session), and (B) your real days.
>
> **A — Routing-reliability supervised pass (~20 min with me).** Fresh web tasks reach the hand ~75% of
> the time; the misses dead-end as a generic confirm via a tangled multi-path router. The fix is to
> consolidate routing into ONE place (or a model-assigned route) — core-brain surgery I won't do solo
> after it bit us. Sit with me once (or say "do it, the suite + safety corpus are your guard, revert any
> regress") and I'll drive it to ~100%, gated.
>
> **B — Your real days = the §4 finish.** Live with it a few real days (accounts stay connected); we read
> the same gate metrics on your days. That is the only thing that can stamp "fully done," by definition.

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
   → Unblocks: **Phase 5 cloud deploy.** The per-user routing is BUILT + proven (each user's extension
   binds only their own Chrome, `test_per_user_hands` 10/10) — the remaining piece is the extension
   carrying your Supabase identity on connect, which only matters/works once it's deployed with real
   sign-in. Data also survives restarts once the volume exists.

**4. (30-sec cleanup, optional but recommended) Remove the duplicate hand extensions.**
   `chrome://extensions` → remove the two **"Anticipy Bridge v6"** entries (folder `Anticipy-Browser-Hand`).
   Keep only **"Anticipy (the hands)"** (`Anticipy-Extension`). The dupes don't talk to the engine but
   occasionally cause a transient "chrome-extension:// URL" error during form-fills (a retry currently
   works around it). One canonical extension = no jank.

## How to hand it back to the loop
Do any subset above and say so — the loop picks up the now-unblocked phase, builds + live-proves it
with you, ratchets it green, and commits. Smallest highest-leverage first step: **#1** (just stay
logged in) — it unblocks the spine's live proof and most of onboarding.
