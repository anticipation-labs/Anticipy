# What is actually blocking this migration

> **STALE AS OF 2026-09-04 — do not plan off the table below without reading
> this first.** Re-measured on the same account a day later: **Workers Paid has
> landed and R2 is enabled.** `wrangler containers list` → "No containers
> found" (not "Unauthorized"), and `wrangler r2 bucket list` returns three
> buckets. Two of the four rows below are resolved. The remaining brain-side
> blockers, re-measured, are in `BRAIN-ON-CONTAINERS.md` §1.

Measured 2026-09-03 against Cloudflare account `114587b715e702461766369b01d42fc7`
(`omar@anticipy.ai`), wrangler 4.129.0 authenticated by OAuth.

## It is one thing: the account is on the Workers FREE plan

Four separate findings turned out to be the same finding. Every one of them is
resolved by a single upgrade, and none of them can be engineered around.

| Blocked | Evidence | Free-plan limit |
|---|---|---|
| **Containers** — where `brain/` must run | `wrangler containers list` → *"Unauthorized: You do not have access to Cloudflare Containers. Deploying containers requires the Workers Paid plan."* | not available at all |
| **R2** — evidence files, static assets, downloads, backups | `wrangler r2 bucket list` → *"Please enable R2 through the Cloudflare Dashboard [code: 10042]"* | needs enabling + a payment method |
| **bcrypt login** — verifying the 7 existing accounts | ~50 ms CPU per verify at cost factor 10, measured on workerd (`spike/bcrypt-on-workerd.md`) | 10 ms CPU per request |
| **Website bundle** — 2.63 MB gzipped | `wrangler deploy --dry-run` (`spike/website-verification.md`) | 3 MB gzip; we are at 88% |

Workers Paid is $5/month. R2 and D1 bill on usage on top of it.

### Why none of these can be worked around

- **Containers.** There is no free substitute. The alternative is not a cheaper
  Cloudflare product, it is rewriting `brain/`'s 22,614 lines of Python as
  TypeScript on Cron Triggers + Durable Objects.
- **bcrypt.** The 50 ms is inherent: bcrypt is deliberately compute-bound. The
  only way to make it fit 10 ms is to lower the cost factor, which silently
  downgrades the security of every stored password and cannot be undone without
  the plaintext. Do not do this.
- **Bundle size.** 370 KB of headroom on the free ceiling. One dependency and
  the deploy stops fitting — and it fails at deploy time, not review time.
- **R2.** Evidence photos must be fetchable by Twilio's `MediaUrl` from a
  stranger's infrastructure. There is nowhere else for those bytes to live.

## What already works on the free plan

- **D1.** `anticipy-backend-staging` created and the full schema applied: 26
  tables, 46 indexes, 5 partial-unique. Verified.
- **Workers.** The site builds and runs on workerd: 60/60 pages, 84/84 API
  routes. Verified.
- **KV.** Available (empty).

So the whole website half of the migration is proven on the free plan. It is the
backend half — containers, object storage, and password verification — that
stops at the paywall.

## A second question, and it is not a small one

`backend/pb_migrations/1700000053_off_volume_backups.js` configures PocketBase's
scheduled backups to an R2 bucket named `anticipy-pocketbase-backups-production`.
**R2 is not enabled on this account.** So either those backups go to a different
Cloudflare account, or they have been failing.

That bucket is the stated safety net for discarding the Railway volume. Nobody
should discard anything until somebody has confirmed, by listing it, that the
backups exist and are recent. The last generation the repo's own research claims
is 2026-09-01; today is 2026-09-03.

## Access still needed from the owner

1. **Upgrade to Workers Paid**, and **enable R2** in the dashboard. Unblocks
   everything above.
2. **Confirm where the PocketBase backups actually land** — and that they are
   current.
3. **PocketBase superuser credentials** — to export the 26 collections and to
   discover any collection the repo does not know about. `d1/GAPS.md` lists
   what is already known to be missing.
4. **`ANTICIPY_SERVICE_TOKEN`** — 175 of the 189 contract tests skip without it.
   The 14 that run today are green; the rest are the actual conformance proof.
5. **`ANTICIPY_VAULT_KEY`** — see `runbooks/reencrypt_vault.md`. Without it the
   password vault exports as unreadable ciphertext, and that is discovered only
   after the source is gone.
