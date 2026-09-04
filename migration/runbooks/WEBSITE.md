# RUNBOOK: the Next.js website on Cloudflare Workers

Target: `src/` — 62 pages, 94 API route files — served by `anticipy-web`, a
Worker built with `@opennextjs/cloudflare@1.15.1`.

Config artifacts this runbook installs:

    migration/config/wrangler.website.jsonc
    migration/config/open-next.config.ts

Everything below was read or measured in this tree at commit `e8cf315b`
**plus the staged deletion of `src/app/c/[handle]/route.ts`**, wrangler 4.129.0,
`next@14.2.35`. Where a number was measured on a real workerd rather than
reasoned about, it says so.

This branch is being worked by several people at once and moved three times
while this was written. Re-run the one-line counts in §1.1, §2.1 and §9 before
trusting them; each is written as a command for that reason.

---

## §0. Two things to settle before the first deploy

**0.1 The Worker is named twice, differently.** `wrangler.jsonc:3` at the repo
root says `anticipy-site`. `runbooks/SECRETS.md:68` says `anticipy-web`, and
every one of the 29 `wrangler secret put --name anticipy-web` lines at
`SECRETS.md:255-283` assumes that name. Deploying both files creates **two
Workers**, one of which has all the secrets and no traffic.

`migration/config/wrangler.website.jsonc` uses `anticipy-web`. Delete the root
`wrangler.jsonc`, or reduce it to a pointer, before the first deploy.

**0.2 The adapter version is load-bearing.** `@opennextjs/cloudflare` raised its
`next` peer to `>=15` at 1.16.0. 1.15.1 declares
`^14.2.35 || ~15.0.7 || …` (`node_modules/@opennextjs/cloudflare/package.json`,
`peerDependencies.next`) and this site is on exactly `next@14.2.35`
(`package.json:25`). **Leaving Vercel needs no Next.js major upgrade.** Keep
`^1.15.1` pinned at `package.json:38`; unpinning it means upgrading Next first.

Build and deploy from the repo root:

```sh
npx opennextjs-cloudflare build
npx wrangler deploy -c migration/config/wrangler.website.jsonc --env=""
```

The `--env=""` is not decoration — the config declares an `env.staging`, and
wrangler warns and asks for an explicit target when more than one environment
exists.

---

## §1. The rewrites to Railway

### 1.1 There are 35, not 34 — and 37 rewrites in total

Counted from the built manifest, which is the authority because it is what the
Worker actually routes on:

```sh
node -e "const r=require('./.next/routes-manifest.json').rewrites; console.log(r.length)"
# 37
```

37 = 2 PostHog (§7) + **35** pointing at `backend-production-61e0a.up.railway.app`.
The 35 are `/r/:code`, `/c/:code`, and 33 `/internal/*` paths.

All 35 are built from the same template literal, so they all move together by
changing one constant at `next.config.mjs:10-11`:

```js
const FELLOWSHIP_ORIGIN =
  process.env.FELLOWSHIP_ORIGIN || "https://backend-production-61e0a.up.railway.app";
```

### 1.2 THE REWRITES ARE BAKED AT BUILD TIME

`FELLOWSHIP_ORIGIN` is read by `next.config.mjs` during `next build`, and the
resolved string is frozen into `.next/routes-manifest.json`. Proof — the current
build has the literal Railway host in it, because the variable was unset when it
ran:

```sh
grep -c 'backend-production-61e0a' .next/routes-manifest.json   # 35
```

**Setting `FELLOWSHIP_ORIGIN` as a wrangler `var` does nothing.** It must be in
the environment of the *build*:

```sh
FELLOWSHIP_ORIGIN=https://api.anticipy.ai npx opennextjs-cloudflare build
npx wrangler deploy -c migration/config/wrangler.website.jsonc --env=""
```

Verify before deploying, never after:

```sh
node -e "
const r = require('./.next/routes-manifest.json').rewrites;
const bad = r.filter(x => /railway\.app/.test(x.destination));
console.log(bad.length === 0 ? 'OK: no Railway destinations' : 'STILL ON RAILWAY: ' + bad.length);
"
```

### 1.3 All 35, with their new destination

New origin is the backend Worker `anticipy-api` (`SECRETS.md:69`). Use
`https://api.anticipy.ai` once that hostname exists; until it does, use the
`workers.dev` name — `migration/spec/contract_tests.py:16` already assumes
`https://api.anticipy.workers.dev`. Every path is unchanged; only the host moves.

| # | `next.config.mjs` | source | new destination |
|---|---|---|---|
| 1 | :82 | `/r/:code` | `https://api.anticipy.ai/r/:code` |
| 2 | :83 | `/c/:code` | `https://api.anticipy.ai/r/:code` |
| 3 | :101 | `/internal` | `https://api.anticipy.ai/internal.html` |
| 4 | :104 | `/internal/state` | `https://api.anticipy.ai/internal/state` |
| 5 | :105 | `/internal/login` | `https://api.anticipy.ai/internal/login` |
| 6 | :106 | `/internal/health` | `https://api.anticipy.ai/internal/health` |
| 7 | :107 | `/internal/people` | `https://api.anticipy.ai/internal/people` |
| 8 | :108 | `/internal/todos` | `https://api.anticipy.ai/internal/todos` |
| 9 | :109 | `/internal/todos/delete` | `https://api.anticipy.ai/internal/todos/delete` |
| 10 | :110 | `/internal/events` | `https://api.anticipy.ai/internal/events` |
| 11 | :111 | `/internal/events/delete` | `https://api.anticipy.ai/internal/events/delete` |
| 12 | :112 | `/internal/tracks` | `https://api.anticipy.ai/internal/tracks` |
| 13 | :118 | `/internal/me` | `https://api.anticipy.ai/internal/me` |
| 14 | :119 | `/internal/session` | `https://api.anticipy.ai/internal/session` |
| 15 | :120 | `/internal/session/end` | `https://api.anticipy.ai/internal/session/end` |
| 16 | :121 | `/internal/people/code` | `https://api.anticipy.ai/internal/people/code` |
| 17 | :122 | `/internal/comments` | `https://api.anticipy.ai/internal/comments` |
| 18 | :123 | `/internal/notifs/read` | `https://api.anticipy.ai/internal/notifs/read` |
| 19 | :124 | `/internal/settings` | `https://api.anticipy.ai/internal/settings` |
| 20 | :127 | `/internal/clerk/exchange` | `https://api.anticipy.ai/internal/clerk/exchange` |
| 21 | :129 | `/internal/expenses` | `https://api.anticipy.ai/internal/expenses` |
| 22 | :130 | `/internal/expenses/delete` | `https://api.anticipy.ai/internal/expenses/delete` |
| 23 | :131 | `/internal/passwords` | `https://api.anticipy.ai/internal/passwords` |
| 24 | :132 | `/internal/passwords/reveal` | `https://api.anticipy.ai/internal/passwords/reveal` |
| 25 | :133 | `/internal/passwords/delete` | `https://api.anticipy.ai/internal/passwords/delete` |
| 26 | :136 | `/internal/assistant` | `https://api.anticipy.ai/internal/assistant` |
| 27 | :138 | `/internal/notes` | `https://api.anticipy.ai/internal/notes` |
| 28 | :139 | `/internal/notes/delete` | `https://api.anticipy.ai/internal/notes/delete` |
| 29 | :141 | `/internal/people/faces` | `https://api.anticipy.ai/internal/people/faces` |
| 30 | :142 | `/internal/me/password` | `https://api.anticipy.ai/internal/me/password` |
| 31 | :143 | `/internal/fellows` | `https://api.anticipy.ai/internal/fellows` |
| 32 | :144 | `/internal/fellows/remove` | `https://api.anticipy.ai/internal/fellows/remove` |
| 33 | :149 | `/internal/fellows/pay` | `https://api.anticipy.ai/internal/fellows/pay` |
| 34 | :150 | `/internal/fellows/submissions/remove` | `https://api.anticipy.ai/internal/fellows/submissions/remove` |
| 35 | :151 | `/internal/fellows/submissions/release` | `https://api.anticipy.ai/internal/fellows/submissions/release` |

No path rewriting is needed. Set `FELLOWSHIP_ORIGIN` and all 35 move at once.

Note #3: the destination is `internal.html`, a **136 KB single-page app** served
from PocketBase's static directory (`backend/pb_public/internal.html`). The
backend port must keep serving that file at that path or HQ is a blank page even
though all 33 API paths answer.

### 1.4 `/internal/docs/*` is NOT rewritten, and must stay that way

There are 3 real Next pages under it:

    src/app/internal/docs/page.tsx
    src/app/internal/docs/competitive/page.tsx
    src/app/internal/docs/pendant-upload/page.tsx

`next.config.mjs:113-117` says this explicitly: the list is *enumerated, never
globbed*, because a `/internal/:path*` catch-all "would swallow the whole
hardware hub."

The mechanism that saves it is Next's route ordering. A `rewrites()` that
returns a bare array is `afterFiles`, applied **after** filesystem routes.
`/internal/docs` is a static filesystem route, so it wins. OpenNext implements
the same ordering (`@opennextjs/aws/dist/core/routingHandler.js:96-116`), so the
behaviour carries over unchanged.

**Do not "simplify" these 33 lines into one wildcard.** It compiles, deploys, and
silently 404s three internal doc pages behind a passcode nobody checks daily.

### 1.5 A rewrite that shadowed a real route — resolved during this pass

`/c/:code` (#2) is an `afterFiles` rewrite, and `afterFiles` is applied before
**dynamic** routes. `src/app/c/[handle]/route.ts` was a dynamic route, so the
rewrite always won and that handler — which dropped a 90-day creator-attribution
cookie — was unreachable on Vercel and would have stayed unreachable on Workers.

It was pre-existing, not caused by the migration. The file has since been
deleted (staged in the working tree at the time of writing; `git status` shows
`D  src/app/c/[handle]/route.ts`). Rewrite #2 is now the only thing serving
`/c/*`, which is the correct end state — one handler, not two.

**Confirm before deploy** that exactly one of the two still exists:

```sh
ls src/app/c/ 2>/dev/null; grep -n '"/c/:code"' next.config.mjs
```

---

## §2. `runtime = "nodejs"` and the `node:crypto` imports

### 2.1 What is actually pinned

22 pins, not 20 — the extra two are pages, not API routes:

```sh
grep -rn 'runtime = "nodejs"' src/ | wc -l    # 22
```

- **20** API route handlers under `src/app/api/` — this is the audit's number, and it is right
- **2** pages: `src/app/analytics/page.tsx:11`, `src/app/pre-orders/success/page.tsx:5`

(It was 23 until `src/app/c/[handle]/route.ts:5` was deleted — see §1.5.)

There is **no** `runtime = "edge"` anywhere:

```sh
grep -rn 'runtime\s*=\s*"edge"' src/    # no matches
```

The audit's "1 edge" was true of `origin/main`; commit `d8d99ff7` removed both
edge pins (`src/app/api/geo/route.ts` and `src/app/apple-icon.tsx`, §3).

**On Workers the pins are inert.** There is one runtime. Every route runs in the
same isolate under `nodejs_compat` whether it declares `"nodejs"` or declares
nothing. Leave them: they keep `next dev` and any future Vercel deploy honest,
and removing 23 lines buys nothing.

### 2.2 The 8 route files importing `crypto` directly

| file:line | imports | verdict |
|---|---|---|
| `src/app/api/extension/access-code/route.ts:3` | `randomBytes` (:11, :56) | covered |
| `src/app/api/auth/google/route.ts:4` | `randomUUID` (:44) | covered |
| `src/app/api/crm/voice/route.ts:2` | `randomUUID` (:51) | covered |
| `src/app/api/crm/files/route.ts:2` | `randomUUID` (:51) | covered |
| `src/app/api/crm/extract-receipt/route.ts:2` | `randomUUID` (:39) | covered |
| `src/app/api/engine-transfer-gate/route.ts:10` | `timingSafeEqual` (:21) | covered |
| `src/app/api/internal-gate/route.ts:9` | `timingSafeEqual` (:40) | covered |
| `src/app/api/twilio/status/route.ts:1` | `createHmac("sha1")` (:178), `timingSafeEqual` (:184) | covered |

11 more modules under `src/lib/` import it, and they are where the interesting
calls live: `createCipheriv("aes-256-cbc")` at `src/lib/google-calendar.ts:24`
and `src/lib/crm/google.ts:64`, and `scrypt` at `src/lib/crm/password.ts:7,17`.

### 2.3 Measured on real workerd — none of it needs a WebCrypto rewrite

Run against `wrangler dev --local`, wrangler 4.129.0,
`compatibility_flags: ["nodejs_compat"]`, importing from `node:crypto`:

| call | as used at | result | CPU |
|---|---|---|---|
| `randomBytes(16)` | `access-code/route.ts:11` | ok | 0 ms |
| `randomUUID()` | `auth/google/route.ts:44` | ok | 0 ms |
| `createHash("sha256")` | `src/lib/analytics-server.ts:34` | ok | 1 ms |
| `createHmac("sha256")` | `src/lib/gate-cookie.ts:12` | ok | 0 ms |
| `createHmac("sha1")` | `twilio/status/route.ts:178` | ok | 0 ms |
| `timingSafeEqual` | `internal-gate/route.ts:40` | ok | 0 ms |
| `createCipheriv`/`createDecipheriv` `aes-256-cbc` round-trip | `google-calendar.ts:24,34` | ok, plaintext recovered | 0 ms |
| `scrypt` N=16384 r=8 p=1 keylen=64 | `crm/password.ts:17` | ok, 64 bytes | **25 ms** |

**Verdict: `nodejs_compat` covers all of it. Zero WebCrypto rewrites required.**

Two consequences worth carrying forward:

1. **`scrypt` costs 25 ms of CPU**, and bcrypt costs ~50 ms
   (`spike/bcrypt-on-workerd.md:31`). Both blow the free plan's 10 ms ceiling.
   The account has since been upgraded — `c1b95071` records Containers becoming
   available, which is Paid-only — so this is no longer blocking, but it is why
   `wrangler.website.jsonc` sets `limits.cpu_ms`. Note `migration/BLOCKERS.md`
   still describes the account as free; that document is now stale on this point.

2. **The four routes that pay the 25 ms are not the pinned ones.** Transitive
   import closure over `src/`:

   | reaches `scrypt` | declared runtime |
   |---|---|
   | `src/app/api/crm/gate/route.ts` | UNSPECIFIED |
   | `src/app/api/crm/users/route.ts` | UNSPECIFIED |
   | `src/app/api/crm/users/me/password/route.ts` | UNSPECIFIED |
   | `src/app/api/crm/users/[id]/password/route.ts` | UNSPECIFIED |

   And 10 routes reach `aes-256-cbc`, 9 of them also UNSPECIFIED. So the
   `runtime = "nodejs"` pins are **not** a map of where Node APIs are used —
   another reason not to treat the pin list as a migration checklist.

`maxDuration` (10 routes, up to `300` at `src/app/api/app/run/route.ts:4`) has no
Workers equivalent and is ignored. Wall-clock time awaiting `fetch` is not
charged; only CPU is, which is what `limits.cpu_ms` bounds.

---

## §3. `apple-icon` — already fixed, here is how to confirm

**The change this runbook was asked to recommend has already been applied**, in
commit `d8d99ff7`. Recording it so nobody re-does it or reverts it.

Before: `src/app/apple-icon.tsx`, `runtime = "edge"`, `ImageResponse` from
`next/og` — which drags in Satori plus a resvg WASM binary to draw a capsule and
a dot.

After: `src/app/apple-icon.png` — a static 180×180 PNG rendered from the same
geometry, **1,632 bytes**.

```sh
$ file src/app/apple-icon.png
src/app/apple-icon.png: PNG image data, 180 x 180, 8-bit/color RGB, non-interlaced

$ grep -rn "next/og\|ImageResponse" src/
# no matches

$ ls src/app/apple-icon.tsx
# No such file
```

The URL did not change. Next still serves it through the app-router file
convention, at `/apple-icon.png?b7841db8b514b1db`, with
`cache-control: public, immutable, no-transform, max-age=31536000`
(`.next/server/app/apple-icon.png.meta`).

One residual, low priority: because it is a file-convention route rather than a
`public/` file, every request for it invokes the Worker instead of being served
by the asset layer. Moving it to `public/apple-icon.png` and declaring
`icons.apple` in the `metadata` export at `src/app/layout.tsx:27` would make it a
static asset. Not worth doing before cutover — it is 1.6 KB with a one-year
immutable cache.

---

## §4. `next/image` — the premise is wrong in our favour

**sharp is never involved.** OpenNext's Cloudflare adapter handles `/_next/image`
in the Worker itself. From the generated entrypoint, `.open-next/worker.js:38-41`:

```js
if (url.pathname === `${globalThis.__NEXT_BASE_PATH__}/_next/image…`) {
  return await handleImageRequest(url, request.headers, env);
}
```

and `handleImageRequest` resizes through the **Cloudflare Images binding**, not
a Node library
(`node_modules/@opennextjs/cloudflare/dist/cli/templates/images.js:125-148`).

The behaviour when the binding is absent is the part that decides the
recommendation, and it is explicit in the source
(`images.js:126-132`):

```js
if (env.IMAGES === undefined) {
    warn("env.IMAGES binding is not defined");
    const response = createImageResponse(imageStream, contentType, { immutable });
    return response;      // original bytes, unresized
}
```

So `<Image>` **works either way**. Without `IMAGES` it degrades to serving
originals; it does not error.

### 4.1 The live call sites — 11 files, 12 `<Image>` elements

The audit's "~3 surfaces" undercounts. Verified:

```sh
grep -rn 'from "next/image"' src/     # 11 files
```

| file | `<Image>` count |
|---|---|
| `src/components/Hero.tsx:4` | 1 |
| `src/components/ChargingSection.tsx:4` | 1 |
| `src/components/ProductSplit.tsx:4` | 1 |
| `src/components/SizeComparison.tsx:4` | 1 |
| `src/components/Colorways.tsx:4` | 1 |
| `src/components/Scenarios.tsx:4` | 1 |
| `src/components/FullBleedImage.tsx:4` | 1 |
| `src/components/Triptych.tsx:4` | 1 |
| `src/components/story/Worn.tsx:4` | 1 |
| `src/app/funded/page.tsx:6` | 2 |
| `src/app/pre-orders/purchase/Gallery.tsx:4` | 2 |

These are the marketing homepage and the pre-order gallery — the two pages that
sell the product — and the source images are large: 18 PNGs in `public/images/`,
several over 1.5 MB (`scenario-couch.png` 1.7 MB, `lifestyle-female.png` 1.5 MB).

### 4.2 Recommendation: add the binding. Do not set `unoptimized: true`

`unoptimized: true` would ship a 1.7 MB PNG to a phone on the hero of the page
that sells a $149.99 product. The binding is one line and is already in
`wrangler.website.jsonc`:

```jsonc
"images": { "binding": "IMAGES" }
```

`next.config.mjs` needs **no** `images` block. The defaults in
`.next/images-manifest.json` (8 device sizes, 8 image sizes, `loader: "default"`,
`path: "/_next/image"`) are exactly what OpenNext's handler validates against
(`images.js:386`, `images.js:433`).

Requires Cloudflare Images to be enabled on the account. If it is not enabled
yet, deploy anyway — the fallback path above keeps the pages correct — and add
the binding when it is. Confirm which branch you are on from the Worker log line
`env.IMAGES binding is not defined`, or:

```sh
curl -sI 'https://www.anticipy.ai/_next/image?url=%2Fimages%2Fhero.png&w=828&q=75' \
  -H 'accept: image/webp' | grep -i '^content-type'
# image/webp  -> resizing through the binding
# image/png   -> binding absent, original bytes
```

---

## §5. `@vercel/analytics` and `@vercel/speed-insights`

Both are mounted in the root layout and nowhere else:

```
src/app/layout.tsx:8   import { Analytics } from "@vercel/analytics/react";
src/app/layout.tsx:9   import { SpeedInsights } from "@vercel/speed-insights/next";
src/app/layout.tsx:145 <Analytics />
src/app/layout.tsx:146 <SpeedInsights />
```

Both post to Vercel-owned collection endpoints, and `@vercel/speed-insights`
additionally expects a `/_vercel/speed-insights/*` path that only Vercel's edge
serves. Off Vercel they are two script loads that fail quietly. Remove them.

### 5.1 What actually replaces them — mostly nothing, because PostHog already does it

Before adding a replacement, note what is already collected. `PostHogProvider`
is initialised at `src/components/PostHogProvider.tsx:20-41` with:

```js
capture_pageleave: true,          //  -> $prev_pageview_duration, max scroll %
capture_performance: { web_vitals: true },   // <- Core Web Vitals, field data
enable_heatmaps: true,
rageclick: true,
```

`capture_performance.web_vitals` is the same LCP/CLS/INP/FCP/TTFB that Speed
Insights reports, and `capture_pageleave` covers what Analytics reports. **The
Vercel pair was already redundant.** Deleting them loses no signal.

Cloudflare Web Analytics is worth adding anyway as a server-side-truth
counterpart that ad blockers do not drop — but it is a *supplement*, not a
replacement for something being lost.

### 5.2 The exact layout change

```diff
--- a/src/app/layout.tsx
+++ b/src/app/layout.tsx
@@ -5,8 +5,6 @@
 import { PostHogProvider } from "@/components/PostHogProvider";
 import { AnalyticsProvider } from "@/components/AnalyticsProvider";
 import { OfferMount } from "@/components/offer/OfferMount";
-import { Analytics } from "@vercel/analytics/react";
-import { SpeedInsights } from "@vercel/speed-insights/next";
 
 const dmSerif = DM_Serif_Display({
@@ -142,8 +140,6 @@ export default function RootLayout({
         <OfferMount />
         <LenisProvider>{children}</LenisProvider>
-        <Analytics />
-        <SpeedInsights />
         <script
           type="application/ld+json"
```

Then:

```sh
npm remove @vercel/analytics @vercel/speed-insights
```

(`package.json:18-19`.)

### 5.3 Adding Cloudflare Web Analytics

Do **not** paste the beacon `<script>` into the layout by hand. On a zone
proxied through Cloudflare, enable it in the dashboard — Web Analytics → the
`anticipy.ai` zone → *Enable automatic setup*. Cloudflare injects the beacon at
the edge, which means:

- no token in the repo,
- nothing to remove from `layout.tsx` later,
- and the injection respects the same origin, so it does not fight the
  `Content-Security-Policy` this site has deliberately not set yet
  (`next.config.mjs:157-161` explains why).

If manual injection is ever required instead, it is one `<script defer>` in
`layout.tsx` before `</body>` carrying a `data-cf-beacon` token — and that token
then belongs in `vars`, not in source.

---

## §6. The daily digest cron

`vercel.json:1-8` is the whole of Vercel's scheduling:

```json
{ "crons": [ { "path": "/api/cron/daily-digest", "schedule": "0 14 * * *" } ] }
```

### 6.1 wrangler config

Already in `migration/config/wrangler.website.jsonc`:

```jsonc
"triggers": { "crons": ["0 14 * * *"] }
```

Same expression, same meaning: Cloudflare cron is UTC and so was Vercel's, so
the digest keeps firing at the same instant. `vercel.json` can be deleted once
Vercel is gone.

### 6.2 The handler — a Cron Trigger does NOT call `fetch()`

This is the part that silently does nothing if you skip it. A Cron Trigger
invokes `scheduled()`. OpenNext's generated entrypoint exports **only** `fetch`
(`.open-next/worker.js:16`). Adding `triggers.crons` alone produces a Worker that
ticks and does nothing.

`.open-next/worker.js` is generated on every build, so it must not be edited.
Wrap it instead. Create `migration/config/worker-entry.ts`:

```ts
// Wraps OpenNext's generated worker to add a scheduled() handler.
// Point wrangler's `main` at this file instead of .open-next/worker.js.
import openNextWorker from "../../.open-next/worker.js";

export { DOQueueHandler, DOShardedTagCache, BucketCachePurge } from "../../.open-next/worker.js";

const CRON_PATH = "/api/cron/daily-digest";

export default {
  fetch: openNextWorker.fetch,

  async scheduled(event: ScheduledController, env: Record<string, string>, ctx: ExecutionContext) {
    // The route authorizes on `Authorization: Bearer <CRON_SECRET>` or on
    // `x-cron-secret` -- src/app/api/cron/daily-digest/route.ts:22-39.
    // It is a GET; it takes no body.
    const req = new Request(`${env.NEXT_PUBLIC_SITE_URL}${CRON_PATH}`, {
      method: "GET",
      headers: { "x-cron-secret": env.CRON_SECRET ?? "" },
    });

    ctx.waitUntil(
      openNextWorker
        .fetch(req, env, ctx)
        .then(async (res: Response) => {
          // Surface failures in the Worker log; a cron that 401s is otherwise silent.
          if (!res.ok) console.error("daily-digest failed", res.status, await res.text());
          else console.log("daily-digest ok", res.status);
        })
        .catch((e: unknown) => console.error("daily-digest threw", e))
    );
  },
};
```

and change `main` in `wrangler.website.jsonc`:

```diff
-  "main": "../../.open-next/worker.js",
+  "main": "./worker-entry.ts",
```

Three details that matter:

- **`CRON_SECRET` must be set.** `route.ts:36-38` fails *open* when it is unset
  ("allow only if no CRON_SECRET is set yet, so a fresh deploy still ticks").
  That is a public, unauthenticated endpoint that emails everyone. Set it:
  `wrangler secret put CRON_SECRET --name anticipy-web`.
- **`CRON_SECRET` must not equal `NEXT_PUBLIC_CRON_SECRET`.** The latter is
  shipped to every visitor of `/crm/settings`
  (`src/app/crm/settings/page.tsx:150-151`; `SECRETS.md` §2b calls it "a bug, not
  a design"). If they match, the gate is public.
- The route declares `maxDuration = 60` (`route.ts:20`), which is ignored;
  `limits.cpu_ms` governs. The work is Supabase queries and a SendGrid/Resend
  POST — almost all awaiting `fetch`, which is not charged as CPU.

Test without waiting for 14:00 UTC:

```sh
npx wrangler dev -c migration/config/wrangler.website.jsonc --test-scheduled
curl 'http://localhost:8787/__scheduled?cron=0+14+*+*+*'
```

---

## §7. The PostHog reverse proxy — verified, it works

`next.config.mjs:60-67`:

```
/ingest/static/:path*  ->  https://us-assets.i.posthog.com/static/:path*
/ingest/:path*         ->  https://us.i.posthog.com/:path*
```

`src/components/PostHogProvider.tsx:12` defaults `api_host` to `/ingest`, so
these carry all first-party event traffic. The comment at `next.config.mjs:20-25`
explains why they exist: PostHog's own hostnames are blocked by every major
content blocker, "disproportionately from the technical, privacy-minded audience
this product is aimed at."

**They survive the port as ordinary Worker subrequests.** Chain, verified in the
installed code:

1. Both are in the built manifest as external destinations —
   `.next/routes-manifest.json`, entries 1 and 2 of 37.
2. The router recognises an absolute destination as external —
   `@opennextjs/aws/dist/core/routing/matcher.js:118-121,156`.
3. The request handler proxies it —
   `@opennextjs/aws/dist/core/requestHandler.js:72-76`.
4. The Cloudflare adapter selects the **fetch**-based proxy, not the Node one —
   `@opennextjs/cloudflare/dist/api/config.js:15,36` (`proxyExternalRequest: "fetch"`).
5. That implementation is a plain `fetch` forwarding method, headers and body —
   `@opennextjs/aws/dist/overrides/proxyExternalRequest/fetch.js`.
6. It is in the shipped bundle: `grep -c "fetch-proxy"
   .open-next/server-functions/default/handler.mjs` → 1.

Two behaviours to know:

- **`cf-connecting-ip` is stripped** before forwarding
  (`fetch.js`, the `headers` filter). PostHog's geo resolution will fall back to
  `x-forwarded-for`, which Cloudflare does set on the inbound request and which
  *is* forwarded. Worth confirming against a real event after cutover (see
  Unverified).
- Each proxied request is one subrequest against the per-invocation subrequest
  limit. One rewrite = one subrequest; nowhere near any ceiling.

No config change is required for §7. Do not "optimise" these into a Cloudflare
redirect — a 30x would put PostHog's blocked hostname back in front of the
browser and undo the entire point.

---

## §8. `src/middleware.ts`

### 8.1 It is 187 lines / 7,388 bytes, not 27 KB

```sh
$ wc -l -c src/middleware.ts
     187    7388 src/middleware.ts
```

About 4.6 KB of that is a single inlined HTML string (`UNLOCK_PAGE`,
`:64-131`). The 27 KB figure is not this file; the *bundled* middleware is
`.open-next/middleware/handler.mjs` at 253 KB, which is the file plus its Next
runtime.

### 8.2 What it does — two things

**`/engine` → `/app`**, a 301 (`:137-142`).

**The `/internal` gate** (`:148-176`). Without a valid `anticipy_internal_gate`
cookie it returns **401** — never a redirect, never a 200 — and content-negotiates
the body: `text/html` in `Accept` gets the unlock form, anything else gets one
sentence. The comment at `:157-161` states the invariant: "no URL under here
answers 200 without the cookie," so curl and crawlers cannot read the hardware
docs, BOM or pinouts.

Matcher (`:180-186`): `/engine`, `/engine/:path*`, `/internal`, `/internal/:path*`.

### 8.3 It ports unchanged. It was written for this.

The verifier is already WebCrypto, not `node:crypto`:

```
src/middleware.ts:2-4   "Edge middleware can use the global Web Crypto API; the
                         HMAC scheme matches src/lib/gate-cookie.ts byte-for-byte"
src/middleware.ts:39-46  crypto.subtle.importKey / crypto.subtle.sign, HMAC SHA-256
src/middleware.ts:16-23  hand-rolled constant-time hex compare
```

`crypto.subtle` is available on workerd with no flag. No `Buffer`, no `fs`, no
Node import anywhere in the file. Confirmed running by
`migration/spike/website-verification.md:20` — `/internal/*` still answered 401
under `wrangler dev`.

Ordering is preserved too, and it matters: middleware runs **before** the 33
`/internal/*` rewrites, so an uncookied request is refused at the edge and never
reaches the backend. OpenNext keeps that order
(`@opennextjs/aws/dist/core/routingHandler.js:96-107`).

One environment dependency: the secret is
`GATE_COOKIE_SECRET || SUPABASE_SERVICE_ROLE_KEY` (`:34-37`), and an empty
secret returns `false` — fail-closed, correct. Both are Worker secrets on
`anticipy-web` (`SECRETS.md` §2a). `SECRETS.md` §7 notes the consequence of the
fallback: rotating `SUPABASE_SERVICE_ROLE_KEY` re-signs every gate cookie unless
`GATE_COOKIE_SECRET` is set explicitly. **Set it explicitly.**

---

## §9. `public/` — already done, by a sibling commit

Commit `1065593b`, "Stop serving the rejected product originals", landed while
this runbook was being written. `public/images/originals_backup/` — 16 files,
23 MB — has been moved to `design/`, which is not served and not part of any
build.

Current state:

```sh
$ ls public/images/originals_backup
ls: No such file or directory

$ du -sh public
44M     public          # was 67M
```

Its finding is worth preserving: those 16 files were **rejected** renders
carrying the exact defects the media policy forbids (engraved chain tags), and
`public/` is served verbatim, so every one of them answered 200 on the marketing
domain.

**How to confirm nothing referenced them** — the method, for the next candidate:

```sh
# 1. Every code and content reference, excluding build output.
grep -rn "originals_backup" \
  --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx' \
  --include='*.css' --include='*.json' --include='*.html' --include='*.md' . \
  | grep -v node_modules | grep -v '\.next' | grep -v '\.open-next'
# -> the only hit was prose in docs/HANDOFF-website-legacy.md:70, now repointed.

# 2. Nothing survived into the built asset set.
find .open-next/assets -path '*originals_backup*'   # empty

# 3. Nothing survived into the rendered HTML either.
grep -rl "originals_backup" .next/server/app/*.html # empty
```

Step 3 is the one people skip, and it is the one that catches a path built by
string concatenation that step 1 misses.

Current asset footprint, measured:

```sh
$ find .open-next/assets -type f | wc -l
147
$ npx wrangler deploy --dry-run -c migration/config/wrangler.website.jsonc --env=""
✨ Read 226 files from the assets directory
Total Upload: 12658.57 KiB / gzip: 2687.84 KiB
```

The two counts differ because **wrangler's "226 files" includes directories**:
147 files + 79 subdirectories = 226. The real file count is 147, largest
`videos/flatlay-done.mp4` at 5.7 MB.

Remaining size note: the Worker **bundle** is 2.69 MB gzipped and images were
never in it, so §9 saved upload time, not bundle headroom. Five dependencies are
declared and never imported by `src/` — `@sendgrid/mail`, `@playwright/test`,
`web-bluetooth-dfu`, `crc-32`, `@stripe/stripe-js` (SendGrid is called over
`fetch` at `src/lib/crm/email.ts:36-40`, not through its SDK). Removing them
shrinks `node_modules` and install time; it does **not** shrink the Worker,
because nothing imports them and esbuild already tree-shook them out. Do not
count on it for headroom.

---

## §10. DNS and domain cutover

### 10.1 What is moving, and what is not

| hostname | today | after |
|---|---|---|
| `anticipy.ai` / `www.anticipy.ai` | Vercel | `anticipy-web` Worker |
| `api.anticipy.ai` | does not exist | `anticipy-api` Worker (§1) |
| `anticipyfellowship.com` | **a separate Vercel project, not in this repo** | see 10.4 |
| `pub-e97c6305….r2.dev` | already Cloudflare R2 | unchanged |

That last row is worth stating plainly: the 2.5 GB Mac DMG **already** serves
from R2. `src/app/dl/Anticipy_1.0.0_aarch64.dmg/route.ts:11-17` is a 302 to a
public R2 bucket URL, and `src/app/download/route.ts:11` redirects to that route.
Nothing about the download path needs to change, and no 2.5 GB file ever goes
near the Worker asset layer.

It also contradicts `migration/BLOCKERS.md:14`, which says R2 is not enabled on
account `114587b715e70246…`. Either that bucket lives on a different account or
R2 is enabled after all. **Resolve this before trusting any statement about
where the PocketBase backups are landing** — `BLOCKERS.md:46-56` already flags
that the backup bucket may have been failing silently.

### 10.2 Order of operations

Do these in order. Each step is reversible until step 5.

1. **Deploy with no routes.** `wrangler.website.jsonc` ships with the `routes`
   block commented out and `workers_dev: true`, so this publishes to
   `anticipy-web.<subdomain>.workers.dev` and touches no DNS.

   ```sh
   FELLOWSHIP_ORIGIN=https://backend-production-61e0a.up.railway.app \
     npx opennextjs-cloudflare build
   npx wrangler deploy -c migration/config/wrangler.website.jsonc --env=""
   ```

   Keep pointing at Railway for now — this step proves the *Worker*, not the
   backend move. Two variables changing at once is two variables to bisect.

2. **Set every secret** (`SECRETS.md:255-283`, 29 of them) and confirm by name:

   ```sh
   npx wrangler secret list --name anticipy-web
   ```

   `GATE_COOKIE_SECRET`, `CRON_SECRET` and `GATE_PASSCODE_INTERNAL` are the
   three whose absence changes behaviour rather than producing an error.

3. **Run the conformance pass against the workers.dev URL** (§14). Do not skip
   to DNS on a green build; a build proves it compiles.

4. **Lower the TTL on the existing records to 60 s** and wait out the old TTL.
   This is the step that decides how fast step 6 can be. Do it a day ahead.

5. **Cut over.** Uncomment in `wrangler.website.jsonc`:

   ```jsonc
   "routes": [
     { "pattern": "anticipy.ai",     "custom_domain": true },
     { "pattern": "www.anticipy.ai", "custom_domain": true }
   ],
   ```

   ```sh
   npx wrangler deploy -c migration/config/wrangler.website.jsonc --env=""
   ```

   `custom_domain: true` makes Cloudflare create and manage the DNS record and
   the certificate. It **replaces** whatever `A`/`CNAME` currently points at
   Vercel — record the existing values first (10.3).

6. **Enable the visitor-location transform.** Zone → Rules → Managed Transforms →
   *Add visitor location headers*. Without it, `cf-ipcity` / `cf-region` /
   `cf-ipcountry` are absent and `src/app/api/geo/route.ts:48-50` prefills the
   application location field empty. Not an outage; a quiet regression on the
   hiring funnel.

7. **Re-apply the security headers at the zone.** `next.config.mjs:151-186`
   applies five headers to `/(.*)`, and they are in the built manifest — but the
   Worker only sets them on responses *it* generates. Static assets served
   directly by the asset layer bypass it. Add a Response Header Transform Rule
   on the zone for `X-Frame-Options`, `X-Content-Type-Options`,
   `Referrer-Policy`, `Permissions-Policy` and `Strict-Transport-Security`
   (`max-age=31536000; includeSubDomains; preload`) so coverage matches what
   Vercel gave. HSTS in particular is also a zone setting (SSL/TLS → Edge
   Certificates → HSTS) and belongs there.

8. **Only then** repoint `FELLOWSHIP_ORIGIN` (§1) and rebuild. Separate deploy,
   separate blast radius.

### 10.3 Record this BEFORE step 5

```sh
# The current Vercel-facing records, so rollback is a paste and not a memory test.
dig +short anticipy.ai      A     > /tmp/rollback-anticipy-apex.txt
dig +short www.anticipy.ai  CNAME > /tmp/rollback-anticipy-www.txt
dig +short anticipy.ai      NS
cat /tmp/rollback-anticipy-*.txt
```

Keep the Vercel project **deployed and building** through the whole window. Do
not delete it, do not remove its domains until it has been quiet for a week.

### 10.4 The fellowship domain

`anticipyfellowship.com` is a **separate Vercel project that is not in this
repository**. Nothing in this tree builds or deploys it. What this tree knows:

- `next.config.mjs:4-8` — the fellowship "has its own domain, its own Vercel
  project, and a CATCH-ALL rewrite to this same backend."
- `CLAUDE.md:203` — "`anticipyfellowship.com` catch-alls to the same backend.
  Changing either side without the other breaks HQ."
- `migration/d1/FELLOWSHIP-PRECEDENT.md:14` — as of 2026-09-03 it still answers
  `server: Vercel`, fronting the Railway PocketBase, while a D1 database
  `anticipy-fellowship` (9 tables) already exists **empty**. Staged, not cut over.

Six redirects on this site point at it and must keep working
(`next.config.mjs:42-43,53-56`): `/ugc`, `/ugc/apply`, `/fellowships`,
`/fellowships.html`, `/fellowship-growth-learning`,
`/fellowship-growth-learning.html`. All are `permanent: false` (302) on purpose —
`next.config.mjs:45-52` explains that three people applied under retired terms
and "are owed a conversation, not a 301." **Do not flip these to 301 during the
migration.** They are redirects on `anticipy-web` and port unchanged.

The catch-all itself cannot be reproduced from this repo, because its source is
not here. When that project moves, its shape on Cloudflare is a Worker route:

```jsonc
// in the FELLOWSHIP project's wrangler config, not this one
"routes": [
  { "pattern": "anticipyfellowship.com/*", "zone_name": "anticipyfellowship.com" }
]
```

with a Worker whose `fetch` forwards every unmatched path to
`https://api.anticipy.ai` preserving path, method, headers and body.

**It must move at the same time as the backend, or after it — never before.**
Its catch-all points at the same origin the 33 `/internal/*` rewrites do. If
`FELLOWSHIP_ORIGIN` moves to `api.anticipy.ai` while the fellowship project
still points at Railway, HQ and the fellowship are reading two different
databases.

### 10.5 Rollback

**Website (steps 5-7), any time:**

1. Re-point DNS at Vercel using `/tmp/rollback-anticipy-*.txt`. With a 60 s TTL
   (step 4) this is minutes.
2. Remove the `custom_domain` routes from `wrangler.website.jsonc` and redeploy,
   so the Worker stops claiming the hostnames:
   ```sh
   npx wrangler deploy -c migration/config/wrangler.website.jsonc --env=""
   ```
   Or, faster and without a build, disable the Worker's routes in the dashboard.
3. The Vercel project is still deployed (10.3), so it serves immediately.

**Nothing to undo on the data side.** The website is stateless with respect to
this cutover: Supabase stays exactly where it is, and no schema or row moves in
steps 1-7. That is what makes the website the safe half to do first.

**Rewrites (step 8), separately:** rebuild with the old `FELLOWSHIP_ORIGIN` and
redeploy. Because the value is compiled in (§1.2), reverting is a **rebuild**,
not an environment-variable change — budget the build time into the rollback
plan, or keep the previous version deployed and use
`wrangler rollback` (`wrangler deployments list --name anticipy-web` to find it).

---

## §11. Rate limiting is broken on Workers, and it protects the login gates

Not in the assignment; found while enumerating bindings, and it is the largest
correctness gap after §12.

`src/lib/rate-limit.ts:10`:

```ts
const buckets = new Map<string, Bucket>();
```

Its own header (`:1-7`) calls it "alpha-grade… process-local so a deploy or
cold-start resets all counters." On Vercel that was weak. On Workers each isolate
gets its own `Map`, and there are many isolates per colo and many colos — so the
effective limit is `limit × isolates`, which is not a limit.

**25 route files call it**, including all three brute-force gates:

| route | limit | window |
|---|---|---|
| `src/app/api/internal-gate/route.ts:48` | 10 | 60 s |
| `src/app/api/admin/login/route.ts:26` | 5 | 10 min |
| `src/app/api/analytics/login/route.ts:16` | 5 | 10 min |
| `src/app/api/applications/route.ts:117` | 5 | 1 h |
| `src/app/api/ugc/route.ts:40` | 5 | 1 h |
| `src/app/api/crm/gate/route.ts` | 8 | 60 s |
| `src/app/api/engine-transfer-gate/route.ts` | 10 | 60 s |
| … 18 more | | |

`src/app/api/internal-gate/route.ts` is the gate in front of a page that
`src/middleware.ts:150-152` describes as listing "three people's phone numbers."

### 11.1 Why not the native `ratelimits` binding

Wrangler does have one (`RawConfig.properties.ratelimits`), but its `simple.period`
is constrained to **10 or 60 seconds only**. The site uses windows of 60 s, 10 min,
1 h and 24 h. It would cover roughly a third of the call sites and silently not
cover `admin-login` (10 min) or `applications` (1 h). Wrong tool.

### 11.2 KV-backed replacement

Preserves the exact `rateLimit(key, limit, windowMs)` signature except for
becoming `async` — which is the one change that ripples to callers.

```ts
// src/lib/rate-limit.ts
import { getCloudflareContext } from "@opennextjs/cloudflare";

export interface RateLimitResult { allowed: boolean; remaining: number; resetAt: number }

export async function rateLimit(
  key: string, limit: number, windowMs: number
): Promise<RateLimitResult> {
  const kv = (getCloudflareContext().env as { RATE_LIMIT?: KVNamespace }).RATE_LIMIT;
  const now = Date.now();

  // No binding -> fail CLOSED for the gates, not open. An unbound limiter that
  // returns `allowed: true` is worse than no limiter, because the 429 branch
  // in every caller becomes unreachable and nobody notices.
  if (!kv) return { allowed: false, remaining: 0, resetAt: now + windowMs };

  const bucket = Math.floor(now / windowMs);
  const k = `rl:${key}:${bucket}`;
  const resetAt = (bucket + 1) * windowMs;

  const current = Number((await kv.get(k)) ?? 0);
  if (current >= limit) return { allowed: false, remaining: 0, resetAt };

  // Eventually consistent: concurrent requests in different colos can both read
  // the same value. Over-admission is bounded by concurrency, not unbounded as
  // the Map version is. TTL floor is 60 s, so short windows expire late but the
  // bucket key already partitions by window.
  await kv.put(k, String(current + 1), {
    expirationTtl: Math.max(60, Math.ceil(windowMs / 1000) + 60),
  });
  return { allowed: true, remaining: limit - current - 1, resetAt };
}

export function clientIp(req: Request): string {
  // CF-Connecting-IP is set by Cloudflare and cannot be spoofed by the client;
  // x-forwarded-for can be. Prefer it, keep the old chain as fallback.
  return (
    req.headers.get("cf-connecting-ip") ||
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    req.headers.get("x-real-ip")?.trim() ||
    "unknown"
  );
}
```

Then in each of the 25 callers, `const limit = rateLimit(...)` becomes
`const limit = await rateLimit(...)`. All 25 call sites are already inside
`async` handlers.

Note the `clientIp` change is a security fix in its own right:
`src/lib/rate-limit.ts:51` currently trusts `x-forwarded-for` first, which a
client can set. On Cloudflare, `cf-connecting-ip` is authoritative.

Provision and wire up:

```sh
npx wrangler kv namespace create RATE_LIMIT
# paste the id into the commented kv_namespaces block in wrangler.website.jsonc
```

---

## §12. THE STRIPE WEBHOOK IS BROKEN ON WORKERS — proven, and it loses orders

The most serious finding in this port. It is not a build error; it is a **200-shaped
silent failure** on the endpoint that records pre-orders.

### 12.1 The mechanism

`migration/config/open-next.config.ts` leaves `useWorkerdCondition` at its
default `true`
(`@opennextjs/cloudflare/dist/api/config.d.ts:48-58`). esbuild therefore resolves
the `workerd` export condition. `stripe@22.2.0` declares one
(`node_modules/stripe/package.json`, `exports.workerd`), pointing at
`stripe.esm.worker.js`, which initialises `WebPlatformFunctions`
(`node_modules/stripe/esm/stripe.esm.worker.js:5`), whose default crypto provider
is SubtleCrypto (`cjs/platform/WebPlatformFunctions.js:34-36`), whose synchronous
HMAC **throws by design** (`cjs/crypto/SubtleCryptoProvider.js:19-20`).

`src/app/api/webhooks/stripe/route.ts:33` calls the synchronous variant:

```ts
event = stripe.webhooks.constructEvent(rawBody, sig, secret);
```

and `:34-37` catches everything and returns **400 "Bad signature"**. So a
perfectly valid Stripe webhook is rejected as forged. Stripe retries, backs off,
and disables the endpoint. Nothing in the logs says "Workers"; it says bad
signature.

### 12.2 Proven on real workerd, not inferred

`wrangler dev --local`, wrangler 4.129.0, `nodejs_compat`, this tree's own
`node_modules/stripe`:

```json
{
  "build": { "cryptoProvider": "SUBTLE (Stripe: `createNodeCryptoProvider()` is not available in non-Node…)" },
  "constructEvent_sync":  { "ok": false,
                            "name": "CryptoProviderOnlySupportsAsyncError",
                            "err": "SubtleCryptoProvider cannot be used in a synchronous context.\nUse `await constructEventAsync(...)` instead of `constructEvent(...)`" },
  "constructEventAsync":  { "ok": true, "type": "ping" }
}
```

### 12.3 Why the existing verification missed it

`migration/spike/website-verification.md:16` reports "84/84 API routes run, zero
5xx caused by the port." That pass never reached line 33.
`src/app/api/webhooks/stripe/route.ts:22-28` returns 400 immediately when the
`stripe-signature` header or `STRIPE_WEBHOOK_SECRET` is missing, and the spike
ran with placeholder env and no signature. **A probe without a valid signature
cannot exercise signature verification.** This is the general lesson for §14: a
route that answers is not a route that works.

### 12.4 The fix

```diff
--- a/src/app/api/webhooks/stripe/route.ts
+++ b/src/app/api/webhooks/stripe/route.ts
@@ -30,7 +30,16 @@ export async function POST(request: NextRequest) {
   const rawBody = await request.text();
 
   try {
-    event = stripe.webhooks.constructEvent(rawBody, sig, secret);
+    // MUST be the async form on Workers. The bundler resolves stripe's
+    // "workerd" export condition, whose crypto provider is SubtleCrypto, and
+    // SubtleCrypto has no synchronous HMAC -- constructEvent() throws
+    // CryptoProviderOnlySupportsAsyncError and the catch below turns a VALID
+    // webhook into a 400. Verified on workerd; see migration/runbooks/WEBSITE.md §12.
+    event = await stripe.webhooks.constructEventAsync(
+      rawBody,
+      sig,
+      secret,
+      undefined,                          // tolerance: keep the default
+      Stripe.createSubtleCryptoProvider() // explicit, so it is correct under either build
+    );
   } catch (err) {
```

`Stripe` is already imported at `route.ts:2`. Passing the provider explicitly
means the line is correct whether the Node or the Worker build is resolved, so it
does not silently depend on `useWorkerdCondition` staying `true`.

### 12.5 Check the other Stripe caller

`src/app/api/pre-orders/checkout/route.ts` uses `stripe.checkout.sessions.create`,
which is async and goes over `fetch` in the worker build — no equivalent problem.
It is the *synchronous crypto* that breaks, and `constructEvent` is the only
synchronous crypto call in the Stripe surface this site uses.

Verify after fixing, with a real signature — the CLI signs correctly:

```sh
stripe listen --forward-to https://anticipy-web.<subdomain>.workers.dev/api/webhooks/stripe
stripe trigger checkout.session.completed
# expect 200 {"received":true}, and a row in the Supabase pre-orders table
```

---

## §13. Build-time env vs Worker vars — the trap

Three classes, and putting one in the wrong place fails silently:

| class | example | where it must be set |
|---|---|---|
| compiled into `next.config.mjs` output | `FELLOWSHIP_ORIGIN` | **build environment only** (§1.2) |
| `NEXT_PUBLIC_*` read in the browser | `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_SITE_URL` | **build environment** (inlined into the client bundle) |
| read via `process.env` on the server | `STRIPE_SECRET_KEY`, `NEXT_PUBLIC_SITE_URL` | wrangler `vars` or `wrangler secret` |

`NEXT_PUBLIC_SITE_URL` is in **two** rows, and that is not a mistake. Verified:
it stays a live `process.env` read in the server bundle
(`grep -o 'process\.env\.NEXT_PUBLIC_SITE_URL' .next/server/app/api/twilio/voice-relay/route.js`
→ 1 hit), while the browser copy is inlined at build. **Set it in both places,
to the same value.**

Worker `vars` and secrets reach `process.env` because OpenNext copies them at
request init
(`@opennextjs/cloudflare/dist/cli/templates/init.js:92-95`).

**`VERCEL_URL` disappears with Vercel.** Six call sites fall back to it and then
to `http://localhost:3000`:

```
src/lib/google-calendar.ts:13-17          <- OAuth redirect_uri
src/lib/crm/google.ts:24-25               <- OAuth redirect_uri
src/lib/notification-adapter.ts:170-171
src/app/api/twilio/voice-relay/route.ts:237
src/app/api/engine/analyze/route.ts:891-893
src/app/api/engine/twilio/voice-script/[intentId]/route.ts:46-48
```

If `NEXT_PUBLIC_SITE_URL` is unset, the Google OAuth `redirect_uri` becomes
`http://localhost:3000/api/auth/google/callback` and Google rejects the
consent screen. It is set in `wrangler.website.jsonc` for exactly this reason.

One more, easy to get wrong: `TWILIO_MOCK` is compared `=== "true"`
(`src/lib/notification-adapter.ts:94`). `"1"` is not truthy there and a staging
deploy would place real calls.

---

## §14. The verification gate

`migration/spike/website-verification.md` recorded 60/60 pages and 84/84 API
routes. That pass is **not sufficient to cut over**, for three reasons now
documented above:

1. It ran with **placeholder credentials**, so no route touched real data
   (`website-verification.md:70-71` says so).
2. It could not reach the Stripe signature path (§12.3).
3. It ran with `nodejs_compat` alone; `wrangler.website.jsonc` adds
   `global_fetch_strictly_public`, which is a behavioural delta.

Re-run before step 5 of §10.2, against the workers.dev URL, with real
credentials in a staging Worker:

```
[ ] 62 pages + 94 API routes respond with the same status as production Vercel
[ ] POST /api/webhooks/stripe with a `stripe listen` signature -> 200, row written   (§12)
[ ] GET  /internal without the cookie -> 401 + unlock form                            (§8)
[ ] GET  /internal/docs -> the Next page, NOT the backend                             (§1.4)
[ ] POST /api/internal-gate x11 from one IP -> the 11th is 429                        (§11)
[ ] GET  /_next/image?url=/images/hero.png&w=828&q=75 with Accept: image/webp
         -> image/webp                                                                (§4)
[ ] /ingest/e/ receives a PostHog event and it appears in PostHog                     (§7)
[ ] GET  /api/geo -> a non-empty label from a real client                             (§10.2 step 6)
[ ] curl -I https://<worker>/ -> all five security headers                            (§10.2 step 7)
[ ] curl -I https://<worker>/images/hero.png -> same five headers                     (§10.2 step 7)
[ ] `wrangler dev --test-scheduled` + /__scheduled -> digest sends once               (§6)
[ ] grep -c 'railway.app' .next/routes-manifest.json matches the intended origin      (§1.2)
```

`migration/runbooks/smoke.sh` (added in `c1b95071`) is the place to add these.

---

## Unverified

Everything above is sourced to a file, a line, or a measurement. These are not.

1. **Nothing is deployed.** All of this is `wrangler dev --local`,
   `wrangler deploy --dry-run` and static reading. No public URL exists, no DNS
   record was touched, no Cloudflare dashboard setting was changed.

2. **The `IMAGES` binding was never exercised against real Cloudflare Images.**
   The fallback path (binding absent → original bytes) is read from
   `images.js:126-132`, not observed. Whether Cloudflare Images is enabled on
   account `114587b715e70246…` is unknown; `BLOCKERS.md` does not mention it
   either way, and it is a separately-billed product.

3. **`global_fetch_strictly_public` was not run.** It is in the config on the
   strength of the upstream template
   (`@opennextjs/cloudflare/templates/wrangler.jsonc:5`). The 60/60 + 84/84 pass
   was made without it. §14 exists to close this.

4. **PostHog geo through the proxy.** `fetch.js` strips `cf-connecting-ip` and
   forwards the rest; I did not confirm that PostHog resolves geo from the
   forwarded `x-forwarded-for` in practice, only that the header is not removed.

5. **`limits.cpu_ms: 60000` was not tested against the account's plan.** The
   field is real (`wrangler/config-schema.json`, `UserLimits.cpu_ms`) and
   `c1b95071` establishes the account is on a paid plan, but I did not confirm
   60000 is an accepted value for this account, nor what the plan's ceiling is.

6. **Cloudflare Web Analytics automatic setup** (§5.3) is described from general
   knowledge of the product, not from this account's dashboard. The `layout.tsx`
   removal in §5.2 is verified; the replacement is not.

7. **Whether `_headers` files work for Workers static assets.** §10.2 step 7
   recommends a zone Transform Rule instead, deliberately, because I could not
   confirm `_headers` support for Workers Assets (as opposed to Pages) from
   anything in this tree.

8. **The fellowship catch-all Worker in §10.4 is a proposal, not a port.** Its
   source is not in this repository. I have not seen the Vercel project's
   config, so I cannot confirm the catch-all is a single wildcard rather than an
   enumerated list, nor what it does with `/api/*`.

9. **The R2/BLOCKERS contradiction in §10.1 is reported, not resolved.** I did
   not call the Cloudflare API to check whether R2 is enabled, nor list the
   backup bucket.

10. **Subrequest limits.** §7 asserts one rewrite costs one subrequest and that
    this is "nowhere near any ceiling." The per-invocation subrequest limit for
    this account's plan was not looked up.

11. **`stripe listen` verification (§12.5) has not been run.** The failure and
    the fix were both proven on workerd with a locally-computed signature; an
    end-to-end test against Stripe's own signing was not performed.
