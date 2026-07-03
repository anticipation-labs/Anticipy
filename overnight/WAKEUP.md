# WAKEUP — the loop's plain-English status (overwritten each build cycle)

_This is the canonical status the factory loop writes every cycle. The root `WAKEUP.md` is superseded._

## Where we are (2026-07-02, build cycle just finished)
- **done_gate:** legs 1–4 PASS, leg 5 (real person, real day) is the human finish line — not yet. Unchanged.
- **suite:** 113 passed / 9 failed (fail-set identical to baseline — did NOT grow). **wiring debt:** 35 (unchanged).
- **This cycle built:** UI_SPEC step 7 — the **Main-screen collapse**. The old cluttered board (three-tile dock + "Live circuit" gateway panel + separate transcript box + featured card) is gone. The Main screen (`/`) is now **one orb + one word + one input + cards**:
  - The listening orb + a single state word (**Listening. / Thinking. / Acting. / Resting.**) — the noisy Start/Mac-mic/Status controls and transcript are still there but only under `?debug`.
  - **One input** (`OneInput`) that does everything: a mic button (talk), a textarea (type, placeholder "Say it, type it, or drop a recording — I'll catch the task."), and a paperclip (drop an MP3/transcript) → one Send.
  - Pending "waiting for your yes" asks + a compact review board of the top cards below it.
  - The page title bar is hidden on Main so the orb is the calm focus.
- **Proven:** `/` compiles to 200 with no error; SSR HTML shows the new elements and none of the old chrome; a Playwright snapshot confirms orb + "Resting." + OneInput(mic/textarea/clip/Send); all other routes still 200; premium-copy gate CLEAN; no gate regressed.
- **Also fixed this cycle:** the running dev server had gone into a stale/broken compile state serving **500 on `/` and `/welcome`** (source was fine). A clean dev-server restart cleared it — both are 200 again. No code was to blame.

## Honest caveats (pre-existing, not from this cycle)
- Every screen logs an **SSR hydration mismatch** (server renders the debug rail/tags, client renders null) — introduced by UI step 1's `typeof window` guards, present on untouched screens too. Harmless to the gates; the cheap next fix is to render those consistently and hide via CSS. Noted in `loop_state.json` known_issues.
- In this dev env the app's `/api/*` proxy returns **503** because the engine is bound at :8790 and the app expects its own binding — environmental, not a regression.

## Next buildable (order-of-attack)
- The remaining UI steps: 2 (Welcome unwrap from AppShell), 3 (Sign), 4 (Setup + fold download), 5 (Connect wire-in), 6 (Onboarding), 8 (Settings + memory), 9 (Coming-soon registry) — then **delete the now-redundant `/mp3`, `/go-to`, `/great`, `/done` routes** (their content now lives on Main / onboarding; deletion was deferred this cycle to keep the blast radius to `/`).
- Then the brain/memory/browser legs per THE_MAP §5.

## What needs Omar
See `overnight/HUMAN_QUEUE.md` — the short list (leg 5 = a real day on real accounts; load the extension; one Twilio token).
