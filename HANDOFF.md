# Anticipy Website — Handoff Document

For anyone (human or Claude) picking up this codebase on a new machine.

## Where the code lives

- **Repo:** https://github.com/omize10/Anticipy (canonical URL — the repo was renamed/moved; old lowercase URLs redirect here)
- **Active branch:** `devin/1784393000-emotive-redesign`
- **Open PR:** https://github.com/omize10/Anticipy/pull/2 (targets `main`)

To work on it locally:

```bash
git clone https://github.com/omize10/Anticipy.git
cd Anticipy
git checkout devin/1784393000-emotive-redesign
npm install
npm run dev   # http://localhost:3000
```

Type-check with `npx tsc --noEmit`. Note: there is no ESLint config; `npm run lint` opens Next.js's interactive setup prompt — avoid it or add a config first.

## What the site is

Next.js (App Router) + Tailwind + GSAP/ScrollTrigger marketing site for the Anticipy pendant:
a titanium wearable that hears spoken commitments ("I'll send Marcus the notes tonight"),
drafts the concrete action, asks for approval, executes it, verifies the result, and keeps a receipt.

**Product facts (do not contradict):** titanium, ~8 g, BLE 5.3, wireless charging pad + chain in box,
$149.99 pre-order / $199 at launch, ships August 2026, full refund before shipping,
free shipping US & Canada, NOT waterproof (no IP rating — never claim one).
Per owner instruction (Aug 2026): do NOT mention "first year of service included" anywhere in marketing copy —
pricing is stated simply as "$149.99 now, $199 at launch". Legal pages (terms/refund/pre-order agreement)
still describe the service subscription; changing those needs an explicit owner decision.

**Never fabricate:** testimonials, reviews, user counts, press, scarcity.

## Homepage architecture (`src/app/page.tsx`)

Scroll story, in order: `Nav → StoryHero (dark, hero video) → Wound (light, pinned kinetic type) →
Turn (dark, golden-thread video) → Chapters (light, 3 steps w/ videos) → LiveDemo (light, pinned phone demo) →
Compare (light table) → ObjectSection (video + light specs) → Worn (light, horizontal video gallery) →
Trust (light) → Honest (light, "what it doesn't do") → Faq (light, + founder note) → Close (dark, CTA + waitlist) →
StickyBuyBar → Footer`.

Visual system (deliberate, keep it): dark cinematic bookends (hero + close), warm-paper editorial middle
(`.section-cream`), serif display headings (DM Serif Display) with NO gold italics, bronze `--bronze: #8A6B44`
accent for eyebrows/links on light backgrounds, gold reserved for the dark phone-demo UI. The Nav auto-flips
dark/light by detecting `.section-cream` sections. Tokens in `src/app/globals.css`.

## Key links / integrations

- **Booking:** Google Calendar link `https://calendar.app.google/QnCVQxa9Aj3x8QKD7`.
  Embedded booking page at `/book` (iframe of the Google appointment schedule).
  The `/funded` page intentionally still uses older Cal.com fundraising links.
- **Waitlist:** `POST /api/waitlist` → Supabase (`src/app/api/waitlist/`). Requires
  `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` env vars. Without them the form
  shows a graceful error.
- **Checkout:** Stripe via `/pre-orders/purchase` (`PurchaseForm`); requires `STRIPE_SECRET_KEY`
  (+ webhook secret) env vars. Confirmation email in `src/lib/email.ts` (Resend).
- **Twilio:** onboarding call/SMS APIs under `src/app/api/twilio/` (separate from the marketing site).
- **Deploy:** intended for Vercel. Set the env vars above in the Vercel project, then point the domain.

## Media policy

All product footage/images are generated from real product renders via Higgsfield CLI, reviewed
frame-by-frame. Never use stock imagery of other products, wrong geometry (backwards pendant,
engraved chain tags), or anything that reads as AI (warped hands, impossible lighting).
Videos live in `public/videos/`, images in `public/images/` (rejected originals in
`public/images/originals_backup`). `hero.png` and `lifestyle-male.png` contain engraved chain tags —
do not reintroduce them into galleries.

## Known open items

- Supabase / Stripe / Resend / Vercel env keys are not in the repo (correctly) — they must be set
  in the deploy environment.
- Waitlist DB insert has never been verified end-to-end locally (no creds on the dev box).
- Waitlist email input lacks `id`/`name` attributes (minor a11y).
- No ESLint config (see above).
- Legal pages still reference the service subscription (see product facts note).
