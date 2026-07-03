# WAKEUP — the loop's plain-English status (overwritten each build cycle)

_This is the canonical status the factory loop writes every cycle. The root `WAKEUP.md` is superseded._

## Where we are (2026-07-02, build cycle just finished)
- **done_gate:** legs 1–4 PASS, leg 5 (real person, real day) is the human finish line — not yet. Unchanged.
- **suite:** 113 passed / 9 failed (fail-set byte-identical to baseline — did NOT grow). **wiring debt:** 35 (unchanged). **premium-copy:** CLEAN.
- **This cycle built:** UI_SPEC **step 2 — Welcome**. Two fixes:
  1. **Killed the double-chrome bug.** The Welcome page is its own standalone landing page (its own top bar), but `PhaseZeroApp` was wrapping it in `AppShell`, which re-stacked a second appbar + a "Vibe your life." title header + the journey rail on top of it. Now there's an early `return <WelcomeScreen />` **before** the AppShell wrap, so Welcome renders clean — one bar, one hero.
  2. **Reskinned it to a single calm hero** per CANON copy: H1 is now **"I listen to your day and quietly handle the small stuff."** and the sub is **"I draft — you approve. I never send anything without you."** Removed the noisy "How it works" 3-beat row, the "The honest part" trust block, and the redundant second "Come in" door section. Kept the one proof-moment (the school-pickup text example) and the footer.
- **Proven:** `/welcome` and `/` both compile to **200**; the served Welcome HTML now shows the new H1/sub, has **no** `pz-appbar` / `pz-top` / `pz-journey` (double-chrome gone), the beats + trust sections are gone, the proof-moment is kept, and "Vibe your life" is still in the page (so done_gate leg 1's token check stays safe). No gate regressed.
- **Also cleared this cycle (environmental, not code):** the running `next dev` had again drifted into a stale `.next` state serving 500/404 on `/`. A `rm -rf .next` + dev-server restart fixed it — both routes 200 again. Same recurring flake noted in known_issues; no code was to blame.

## Honest caveats (pre-existing, not from this cycle)
- Every screen still logs an **SSR hydration mismatch** (server renders the debug rail/tags, client renders null) — from UI step 1's `typeof window` guards, on untouched screens too. Harmless to the gates.
- In this dev env the app's `/api/*` proxy returns **503** because the engine is bound at :8790 and the app expects its own binding — environmental, not a regression.

## Next buildable (order-of-attack, UI_SPEC build order)
- **Step 3 — Sign:** strip the intro source-tags, gate the `StatusPill` behind debug, one panel. (smallest next risk)
- Then step 4 (Setup + fold `/download`), 5 (Connect wire-in), 6 (Onboarding fold `/great`), 8 (Settings fold `/memory`), 9 (Coming-soon registry) — then **delete** the now-redundant `/mp3`, `/go-to`, `/great`, `/done`, `/download` routes.
- Then the brain/memory/browser legs per THE_MAP §5.

## What needs Omar
See `overnight/HUMAN_QUEUE.md` — the short list (leg 5 = a real day on real accounts; load the extension in real Chrome; one Twilio token). None of these are buildable autonomously.
