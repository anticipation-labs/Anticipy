import { defineCloudflareConfig } from "@opennextjs/cloudflare";

/**
 * OpenNext -> Cloudflare adapter configuration for the Anticipy website.
 *
 * WHERE THIS FILE HAS TO LIVE
 * ---------------------------
 * `opennextjs-cloudflare build` looks for `open-next.config.ts` at the ROOT of
 * the Next.js app. This copy under migration/config/ is the reviewed source of
 * truth; the build reads the root one. Keep them identical, or make the root a
 * re-export:
 *
 *     // open-next.config.ts (repo root)
 *     export { default } from "./migration/config/open-next.config";
 *
 * The root file at open-next.config.ts:7 currently already calls
 * `defineCloudflareConfig({})`, which is behaviourally the same as this file.
 * This version differs only in writing down WHY each default is being kept, so
 * that the next person does not "fix" one of them.
 *
 *
 * WHY THE CACHE IS NOT CONFIGURED
 * -------------------------------
 * The single hardest part of an OpenNext port is the incremental cache, and
 * this site does not have the problem. Verified across src/:
 *
 *     ISR / `revalidate`      0 occurrences
 *     `revalidateTag`         0
 *     `unstable_cache`        0
 *     `generateStaticParams`  0
 *     `draftMode`             0
 *
 * With no ISR and no tag revalidation there is nothing to persist between
 * invocations and nothing to invalidate, so:
 *
 *   - `incrementalCache` is left unset. Setting it (R2, KV) would provision
 *     storage that nothing writes to.
 *   - `tagCache` is left unset. It only exists to serve `revalidateTag`.
 *   - `queue` is left unset. It only exists to deduplicate ISR revalidations.
 *   - `cachePurge` is left unset. It purges the CDN after a revalidate.
 *
 * Consequently the wrangler config needs NO `NEXT_INC_CACHE_R2_BUCKET` and no
 * `WORKER_SELF_REFERENCE` service binding, both of which the upstream template
 * (node_modules/@opennextjs/cloudflare/templates/wrangler.jsonc:12-29) ships by
 * default. Their absence from migration/config/wrangler.website.jsonc is
 * deliberate, not an omission.
 *
 * IF THAT EVER CHANGES — the first `export const revalidate` or `revalidateTag`
 * added to this codebase — this file must gain an `incrementalCache` and
 * wrangler must gain the R2 bucket and the self-reference binding. Until then,
 * adding them is dead weight.
 *
 *
 * THE ONE OPTION THAT IS A JUDGEMENT CALL
 * ---------------------------------------
 * `routePreloadingBehavior` defaults to "none" and is left there. The other
 * values ("withWaitUntil", "onWarmerEvent", "onStart") trade cold-start CPU for
 * warm-request latency, and the adapter's own type doc warns they "can result in
 * higher CPU usage on cold starts"
 * (node_modules/@opennextjs/cloudflare/dist/api/config.d.ts:36-40).
 *
 * CPU is the scarce resource on this Worker, not latency: bcrypt verify costs
 * ~50 ms (migration/spike/bcrypt-on-workerd.md:31) and scrypt at N=16384 costs
 * 25 ms measured on workerd. Spending more of the budget on cold starts is the
 * wrong direction until there is a latency measurement that asks for it.
 *
 *
 * `useWorkerdCondition` IS TRUE BY DEFAULT — AND IT MATTERS
 * --------------------------------------------------------
 * Left at its default `true` (config.d.ts:48-58). It makes esbuild resolve the
 * "workerd" export condition, so packages that ship a Workers-specific build get
 * it. That is correct and desirable, but it is NOT free: it is exactly why
 * `stripe` resolves to stripe.esm.worker.js, whose crypto provider is
 * SubtleCrypto, whose synchronous HMAC throws.
 *
 * That breaks src/app/api/webhooks/stripe/route.ts:33 — proven on real workerd,
 * see runbooks/WEBSITE.md §12. Do not "fix" it by setting this to false: that
 * would drag Stripe's Node build (node:http, node:os, node:events) into the
 * bundle instead. Fix the call site.
 */
export default defineCloudflareConfig({
  // Cache interception short-circuits the Next server for cached routes. With
  // no ISR there is nothing to intercept, and `false` is the default.
  enableCacheInterception: false,

  // See the note above. "none" is the default; stated explicitly so that a
  // future change to it is a visible edit rather than a silent version bump.
  routePreloadingBehavior: "none",
});
