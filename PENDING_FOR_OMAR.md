# PENDING FOR OMAR — the batch that unblocks the rest

> Updated 2026-06-25. **The product PASSES the un-fakeable done-gate** — a realistic day run end-to-end
> scores 0 cardinal-sins, money held, vents silent, tasks caught (`owner_test_run --key day01.json`,
> now permanent in the suite, 110/0). The two things left both need YOU. Read with `LEDGER.md`.
>
> **#0 — The whole product passing the gate is the headline, and the loop now closes by itself.** It
> decides a real day correctly (done-gate PASS) AND a fresh handed-over task routes → runs → finishes on
> its own ("Find the elevation of Denver" → done, "5280 feet"). Routing reaches the hand 8/8 now (was 6/8)
> — the chokepoint fix closed it safely (suite 110/0, zero safety breaches). A real Gmail draft flushed;
> onboarding learned from your real Gmail+Calendar. **The product works end-to-end.**
>
> **#0b — The DOOR SIGN (the real "end to end" bar) is BUILT, hardened, safe, and printed.** Hear the
> subtle ask → infer it → create the real PDF → submit to your Canon → ask first. 3-agent investigation +
> hardening: real headlines from your original words, honest "sent to print queue" (never fake "Printed"),
> no silent drops / no fake printer, safety-verified 0 leaks. Commits f8d63ec → 6946286, suite 110/0.
>
> **THE ONE THING FOR THE REAL TEXT — your Twilio (you offered "i will log u in"):** the SMS code is FULLY
> BUILT (send + inbound YES/NO + /resolve). To make you actually RECEIVE "I heard the door — okay to print?"
> and reply YES, set these env vars on the engine and restart:
> ```
> ANTICIPY_CHANNELS_MODE=live
> TWILIO_ACCOUNT_SID=AC...        TWILIO_AUTH_TOKEN=...        TWILIO_FROM=+1<your twilio number>
> OWNER_PHONE=+1<your cell>       ANTICIPY_INBOUND_POLL_SECONDS=15
> ```
> Then a sign/lookup ask texts you for real and your "YES" drives it. (I can't enter creds — that's yours.)
>
> **THE OTHER TWO (yours by nature):** (1) turn the **Canon online** — print job -195 is queued and drops
> the moment it's reachable; (2) the **pendant** (live ambient audio) is hardware. And **your real days**
> remain the §4 "fully done" stamp — it can't be simulated because it's your life.
>
> Remaining deeper tech (supervised, not unsafe): the moat occasionally rephrases/strips a line on the
> whole-day path + stale-dedup returns an old card on exact re-ingest — the core-brain seam (mitigated for
> single lines via original_text; the deeper fix is a careful supervised pass, not unsupervised thrashing).

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
