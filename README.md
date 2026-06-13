# Anticipy-executor-working

Fresh working environment for Anticipy, wired to its own GitHub repo and Vercel project.

Read [PRODUCT_STATUS.md](./PRODUCT_STATUS.md) for the current human product target,
what is proven, and what is still not public-ready.

- **Framework:** Next.js 15 (App Router)
- **GitHub:** `omize10/Anticipy-executor-working` (private)
- **Vercel:** project `anticipy-executor-working` (auto-deploys on push to `main`)

## Local development

```bash
npm install
npm run dev      # http://localhost:3000
```

## Environment variables

Real secrets live in `.env.local` (gitignored — never committed). The full set of
keys is documented in `.env.example`. The same variables are mirrored into Vercel
(Production / Preview / Development) so deployments have what they need at runtime.

To re-sync local → Vercel after editing `.env.local`:

```bash
vercel env rm <KEY> production -y   # if changing an existing key
vercel env add <KEY> production     # paste value when prompted
```

Or pull Vercel → local:

```bash
vercel env pull .env.local
```

## Notes

- Twilio is set to the **live** account that authenticated (`TWILIO_MOCK=false`).
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are intentionally blank — paste the
  LIVE values when ready (see comments in `.env.local`).
