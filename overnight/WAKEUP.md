# WAKEUP — the loop's plain-English status (overwritten each build cycle)

_This is the canonical status the factory loop writes every cycle. The root `WAKEUP.md` is superseded._

## Where we are (2026-07-02, build cycle just finished)
- **done_gate:** legs 1–4 PASS, leg 5 (real person, real day) is the human finish line — not yet. Unchanged.
- **suite:** 113 passed / 9 failed (fail-set byte-identical to baseline — did NOT grow). **wiring debt:** 35 (unchanged, CLEAN). **premium-copy:** CLEAN.
- **This cycle built:** UI_SPEC **step 3 — Sign in**. Three fixes:
  1. **Two panels → one.** The Sign screen used to be a 2-column layout (an "intro" panel on the left, the form on the right). Now it's a single calm centered panel. Done with a new, screen-scoped CSS modifier `.pz-form-shell.pz-form-single` (a two-class/compound selector, so it wins regardless of source order and does **not** touch the Onboarding screen, which reuses the same base `.pz-form-shell`).
  2. **Killed the jargon.** Deleted the developer source-tag row (`OPS-BASIC-PLUMBING`, `ST-TRUST-DIAL`) that used to sit under the heading. The little live/unavailable `StatusPill` is now wrapped in a `pz-only-debug` span, so it only shows with `?debug=1` — invisible to a real user.
  3. **Human copy.** Heading `Come in.` (unchanged), new sub `One account, everywhere. That's it.` One catch I found and fixed live: the sub was first colored with `--ink-soft`, which is the *light-page* dark token — invisible on the dark charcoal panel. Swapped it to `--pz-cream-soft` (the muted-cream token the dark shell uses), so it reads clearly now.
- **Proven (un-gameable):** `/sign`, `/welcome`, `/` all compile to **200**; the served `/sign` HTML has **zero** `ST-*`/`OPS-*` source-tag leaks, **zero** `pz-form-intro` (the old second panel is gone), and the new sub is present. A Playwright screenshot confirms: one panel, serif "Come in.", a single Email/Password form with one "Sign in" primary action, no tags, no status pill. Re-ran all gates after the edit — none regressed.

## Honest caveats (pre-existing, not from this cycle)
- Every screen still logs an **SSR hydration mismatch** (server renders the debug rail/tags, client renders null) — from UI step 1's `typeof window` guards, on untouched screens too. Harmless to the gates.
- In this dev env the app's `/api/*` proxy returns **503** because the engine is bound at :8790 and the app expects its own binding — environmental, not a regression.
- UI step 1 was supposed to strip **all** `SourceTagList` render sites but several remain on other screens (Setup/Onboarding/Great/Board/Settings, lines ~370/504/521/810/1126/1280). Those get cleaned as each screen's own step lands (Sign's is now done).

## Next buildable (order-of-attack, UI_SPEC build order)
- **Step 4 — Setup (+ fold `/download`):** fold the extension `.zip` download + install `<ol>` into `SetupScreen`, point Continue → `/connect`, delete `app/download/` (and its git/pip Quick-Start block). Verify `/setup`=200, `/download`=404.
- Then step 5 (Connect wire-in → add a `Continue`→`/onboarding/2`), 6 (Onboarding fold `/great`), 8 (Settings fold `/memory`), 9 (Coming-soon capability registry) — then **delete** the now-redundant `/mp3`, `/go-to`, `/great`, `/done`, `/download` routes.
- Then the brain/memory/browser legs per THE_MAP §5.

## What needs Omar
See `overnight/HUMAN_QUEUE.md` — the short list (leg 5 = a real day on real accounts; load the extension in real Chrome; one Twilio token). None of these are buildable autonomously.
