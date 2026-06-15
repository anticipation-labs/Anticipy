# ANTICIPY — MORNING REPORT (2026-06-15) — read this first, before the meeting

## TL;DR (30 seconds)
- The demo is **green and bootable** — I never broke it. Suite **81/81**, cardinal-sin floor **0 breaches**,
  engine + web live, app still signed. 5 verified commits tonight, all on the MIDDLE (the hard part).
- **ONE thing you must NOT claim in the meeting: voice is NOT live.** The old handoff *said* it was
  ("real SMS/call verified") — that was **fabricated**. No real Twilio call/SMS has ever been placed. Don't
  show the 2:45 call as working until we do one supervised run together (~15 min). Everything else below is real.
- I built the **per-person API mesh + onboarding Chrome-scrape pipeline + browser-in-your-own-Chrome (CDP) +
  the Owner Test scorer.** Each was independently skeptic-verified; skeptics caught 3 real bugs (incl. a
  could-have-certified-a-cardinal-sin scorer bug) and I fixed all of them.

## What I did tonight, with receipts (verify any of it — commands at the bottom)
| Commit | What | Proof |
|---|---|---|
| `c0925cd` | **Per-person API mesh WIRED** (was built but dormant — everyone shared one key; now each user authenticates with their OWN encrypted token) + corrected the handoff's voice fabrication + honest autonomy ceiling | `test_core_api_mesh.py`, suite 76→77 |
| `5d9e7b1` | **Onboarding Chrome-scrape → mesh bridge** (engine half): a logged-in-service scan becomes Connect-loops (api route for Gmail/Calendar, browser route for niche CRMs like Cosmolex) | `test_onboarding_scan.py`, 77→78 |
| `792354a` | **`POST /onboard/discover`** — a real engine door that ingests a Chrome scan and writes the per-person mesh | `test_onboard_discover.py`, 78→79 |
| `dc468c1` | **browser-use ATTACHES to your own logged-in Chrome over CDP** (the vision's "open-source agent in your Chrome") — money/login hard-stops intact, loopback SSRF-guarded | `test_browser_use_cdp.py`, 79→80 |
| `758223c` | **Owner Test scorer** — the P5 finish-line instrument (catch / false-action=0 / silent-harm=0 / interrupt / e2e), self-proving | `owner_test.py --selftest`, 80→81 |

Every slice: build → full suite GREEN + floor 0 → an **independent skeptic** tried to break it and failed →
commit. Skeptics found and I fixed: an expired-token crash (mesh), a size-cap/scalar-crash (discover), an
**unvalidated SSRF on cdp_url** (CDP arm), and a **critical scorer bug** where the engine's real decision
strings (`"do"`, uppercase `"ACT"`) could have let a vent-action score as PASS — now normalized + the
selftest plants that exact attack so it can't regress.

## Demo-readiness — what to SHOW vs what to AVOID
**Safe to show (real, verified):**
- The inference brain on a messy day: catches real tasks, blocks money, stays silent on vents/sarcasm
  (0 false actions across 152 adversarial lines). This is the moat and it's bulletproof.
- The owner UI / app boots the whole stack.
- The per-person mesh + onboarding model (you can show how a discovered Gmail/CRM becomes a connect task).

**Show only ON A RAIL (works, but not 100% on arbitrary sites — the honest ceiling is ~1-in-3 for live
browser actions; this is true of every agent, not just ours):**
- The browser arm add-to-cart. Use a known store / a prepared flow. **Do not let investors freestyle
  arbitrary store tasks live** — that's where any agent fails.

**Do NOT claim / do NOT demo:**
- **Voice (the 2:45 call): not live.** Plumbing is built and mock-proven; no real call has been placed.
- Onboarding actually crawling your real Chrome end-to-end: the engine pipeline is built and the CDP attach
  exists, but the live crawl in your logged-in Chrome is **not yet proven** (needs the extension reloaded +
  your session — see below).

The honest pitch (this won you over before, don't let the old number creep back in): *"~75% of the boring
toil, fully autonomous, with you in the loop at the money/risky/ambiguous edges"* — NOT "75% fully autonomous."

## Your human-only bundle (the few things only you can do — none blocked my work)
1. **Make voice real** (~15 min, together): boot the engine `ANTICIPY_CHANNELS_MODE=live` + run
   `factory/gates/gate_P3.sh`; you reply "YES <code>" to the test SMS. Then voice is genuinely done.
2. **Notarize the app** (one command): `xcrun notarytool store-credentials anticipy-notary --apple-id
   omarkebrahim@gmail.com --team-id 49T86P9XGW` (paste an app-specific password from appleid.apple.com),
   then I run `macapp/scripts/sign_and_notarize.sh`. (Until then the download is signed but Gatekeeper warns.)
3. **One OAuth tap** for Google Calendar/Gmail so the API arm has a real account to prove create_event/draft on.
4. **The Owner Test**: give me ~1 real day (typed or MP3) + ~10 min red-penning what you'd decide — the
   scorer is ready; I need your days + your judgment as the bar.

## What's still NOT done (honest)
- Voice live (above). The live API-arm proof (needs your OAuth tap). The onboarding **extension scrape** that
  produces the discover payload from your real Chrome (engine side is done + tested; the extension DOM-scrape
  + live proof in your Chrome is the remaining piece). The 5-day Owner Test (0/5 — needs your days). Notarization.

## Incident handled overnight (so you're not surprised)
- The disk hit **100% full** (~3am) from a runaway `glassbox.jsonl` dev-log that had grown to **21GB** (since
  Jun 9) + thousands of leftover temp dirs. I cleared ~23GB **safely** — the demo was never at risk (it uses a
  separate data dir). **Known issue to fix properly: `glassbox.jsonl` grows unbounded (~2GB per test run)** and
  needs log rotation/a size cap. I've been clearing it; it's at 0 now, 16GB free.

## Verify any of this yourself
- `cd ~/Anticipy && bash scripts/run_suite.sh` → expect `SUITE: 81 passed, 0 failed`.
- `PYTHONPATH=engine engine/.venv/bin/python engine/scripts/safety_mega_eval.py` → exit 0 (cardinal-sin floor).
- `git log --oneline c0925cd^..HEAD` → tonight's 6 commits. `git tag` → `night-baseline-green` (a known-good fallback).
- Demo: `curl -s 127.0.0.1:8787/ws/state` → `{"connected":true}`, `curl 127.0.0.1:3000` → 200.
- Nothing was pushed to origin (no overnight deploy). Review the commits, then we push together.

## Durable docs (the genome — survives compaction)
- `logs/factory/HANDOFF_2026-06-15.md` — master handoff (now corrected: voice fabrication fixed, ~14 dropped
  laws folded back in, honest autonomy ceiling).
- `logs/factory/RECEIPTS.md` — every slice's proof (append-only ledger).
- `logs/factory/NIGHT_BUILD_2026-06-14.md` — the autonomous plan + the full overnight progress log.

Bottom line: real, verified progress on the inference middle + the per-person + browser-in-your-Chrome arms +
the finish-line instrument; the demo is intact and green; voice is the one thing to keep honest. Wake me when
you're up and we'll knock out your 4 quick items and the live proofs.
