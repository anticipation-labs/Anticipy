# PENDING_FOR_OMAR

No all-work gate is active. The Factory runs nightly (22:30-07:00) regardless of these.

## Worth 20 minutes soon (in order of leverage)
1. **Red-pen the holdout persona keys** (~20 min, once). Open the four
   `factory/personas/holdout/*/days/day01.expected.json` files next to their `day01.txt`
   and mark anything you'd decide differently (act vs ask vs silence, the money tripwires).
   Your marks are the honesty bar the builder never sees. Tell me your edits or edit the
   files directly — they are local-only, never committed.
2. **Confirm the phone number for SMS/calls**: the engine will text/call the number in
   `OWNER_PHONE` (currently set in .env.local — say "use +1..." if it should change).
   Needed before gate_P1's live SMS leg can pass.
3. **Top up OpenRouter** (~$25 to start; you approved budget). Unblocks live-tier persona
   evals (P2 decider) and the engine's live planning. The key name is OPENROUTER_API_KEY
   in .env.local; account: openrouter.ai -> Credits.
4. Optional, unlocks Gmail drafts later: approve the `gmail.compose` scope (Arcade OAuth
   URL in WAKEUP.md section 2a still works, or I'll regenerate one when we get there).

## Standing facts (no action now)
- Keep the Mac on (or asleep-with-power) at night so the 22:30 launchd window runs.
- Apple Developer ID ($99/yr) is required only when we package the public download
  (next plan, after the Owner Test).
- Possible stray test event `[Anticipy test] M2 typed smoke 20260607-continue` on
  June 12, 15:00-16:00 — safe to delete from Google/Apple Calendar if you see it.
- Old test cart items may remain in some store accounts from the retired M3 work;
  harmless, removable whenever.
- The old Codex CLI quota note is obsolete — the Factory does not use Codex.
