# Anticipy — SOURCE OF TRUTH (canonical, 2026-06-23)

> One page. If anything in the repo contradicts this, this wins. The ~29 older
> STATUS/DONE/MISSION/LEDGER docs are **historical** — superseded by this + `WAKEUP_REPORT.md`.

## The one trunk (never fork the engine again)
- **Canonical:** `~/Anticipy @ factory/build` — the only body with one integrated engine, a real test
  suite (106/107 green; the 1 fail `premium_copy` is a UX copy string, not logic), and proven safety.
- **Remote:** `omize10/Anticipy-executor-working`. Treat `omize10/Anticipy` as archive.
- **Archived parts-bins (read-only, do NOT build on):** `~/Developer/Anticipy-DEV-FINAL`,
  `~/Developer/Anticipy-V7`, `~/Desktop/Anticipy Core`, `~/Desktop/Anticipy-Browser-Hand`,
  `~/Desktop/Anticipy-Extension`, `~/Projects/anticipy`. Their uncommitted work is preserved on
  `preserve/2026-06-23-archive` branches — nothing was lost.

## Architecture decision — FULLY BROWSER (API arm CUT) — Omar, 2026-06-23
- **Every action the product does for the user happens in the user's real Chrome, like a human.**
  Email = open Gmail, click Compose, type To/Subject/Body by hand. No Arcade, no Gmail/Calendar API,
  no API shortcuts. The `api_hand` / Arcade path is **removed from the product runtime.**
- **The ONE exception is Twilio** (SMS + voice), which uses its REST API. It is infrastructure for
  reaching the user, not a user-facing action. Never log into Twilio.
- Money never auto-executes (prepare + park before the final pay/send/submit). Acting on a vent is
  the cardinal sin (never). These two floors stay hard-coded; nothing else about decisions is.
- **Consequence to fix:** the engine still routes some actions (e.g. "pick up kids at 2:45") to
  `route: "api"`. Re-route ALL such actions through the browser. The provider/hands abstraction stays
  so browser/SMS/voice/memory plug in cleanly, but no API connector is required to boot or to act.

## What the product ACTUALLY is (not a glorified email/calendar tool) — Omar, 2026-06-23
The value is operating a person's **real professional systems like a human would**: detailed CRMs and
records — doctors in patient/EMR records, lawyers in case/client records, founders/sales in **HubSpot,
Salesforce**, and whatever vertical tool that person actually uses. Gmail/Calendar are the trivial
warm-up that proves the hand works; **the real gates are "operate a real professional web system,
parked at the irreversible step."** The browser arm must generalize to arbitrary logged-in pro apps,
horizontal across professions — proven by running 2-3 genuinely different real lives, not claimed.

## Current status & definition of done
- **Live status:** `WAKEUP_REPORT.md` (generated from the un-gameable harness `overnight/harness.py`).
- **Done = the gate board hits 14/14**, each row a replayable receipt on Omar's machine, then he lives
  a few real days on it with zero vent-actions and trusts it. "Done" is never an agent's word — it is a
  green gate that drives the real product. See the board + plan in `WAKEUP_REPORT.md`.

## The two things only Omar can do (one-time, batched)
1. Make sure the Anticipy Chrome (`~/.anticipy/chrome-real-clone`) is logged into Gmail / the real pro
   systems we'll operate — or point the hand at his main Chrome. (Browser actions need logged-in sites.)
2. Twilio creds in `.env.local` + confirm his phone number — for the voice/SMS loop.
Everything else is built and proven autonomously; money is the only thing never auto-executed.
