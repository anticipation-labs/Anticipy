# Layer audit and live status — 8 September 2026

Written from Tejas's Mac against `cloudflare-backend` at `eac3aba1`. Everything
below that says VERIFIED was run or read here; everything else says what it is.

## What this pass could and could not do

**Could not**: use the product. This machine has Command Line Tools and no
Xcode, no iPhone, no pendant, no TestFlight, and no credentials of any kind —
no `ANTICIPY_SERVICE_TOKEN`, no `OPENROUTER_API_KEY`, no `ANTICIPY_BACKEND_URL`,
no SendBlue or Composio. Being the end user requires all of those. Nothing in
this note is a claim about lived use, and no scenario in the 500-case catalogue
was executed.

**Could**: verify the live release by its bytes, run the repo's own gates and
suites, and trace the layers through the source. That is what follows.

## Live state, verified here

| Thing | Result |
|---|---|
| Repo sync | local `cloudflare-backend` == `origin` == `eac3aba1`, tree clean, 0 ahead / 0 behind |
| API health | `https://api.anticipy.ai/api/health` → 200, `x-anticipy-revision: d52eaf38` |
| Mac zip, live | 200, 1,148,615 bytes, `application/zip` |
| Mac zip sha256 | `c27dd01e3257e2d8df99e2f5ff1a80f943b53eab01a5d9ab8431bed8186e1cbb` |
| Same as committed + as the handoff expected | yes, byte for byte |
| Deploy run 34180318042 | completed, success |
| Extension version | 0.18.0 in source, in the committed zip, and served live — all three agree |
| Python suite | 3033 passed, 2 skipped, 0 failed |

The previous handoff left the Mac deployment "in progress" and asked the next
operator to read the bytes back. **That is now done and it matches.** The
committed notarized Mac 171 and the public API URL are the same artifact.

## Gate results, and what they mean

```
stranger_gate    legs 1-10 PASS, leg 11 FAIL      (leg 11 is a real defect, below)
tejas_gate       7 PASS, leg 6 red by design
tape_gate        5 PASS, leg 2 red by design      (Law 2's expiry working)
no_vendor_ears   PASS — no shipped code sends audio to a vendor
done_gate        legs 3 and 4 fail ONLY for want of credentials on this machine
are_the_ears_live    UNPROVEN — needs ANTICIPY_SERVICE_TOKEN
is_memory_durable    UNPROVEN — needs credentials
```

`done_gate` leg 3 says in its own words "no model key, so her judgement cannot
be measured"; leg 4 says "no backend URL is set, so there is nowhere to hand
the job." Those are honest refusals to pass an untestable leg, **not** product
defects. Do not read them as either a pass or a failure of the product.

## Defect 1 — the public download still hands over the old product

`stranger_gate` leg 11, and independently measured here:

```
GET https://www.anticipy.ai/download
  302 -> /dl/Anticipy_1.0.0_aarch64.dmg
  -> 2,516,712,351 bytes of application/x-apple-diskimage
```

A stranger clicking Download gets 2.5 GB of the May 2026 product. The
notarized 1.1 MB build 171 is live and correct at `api.anticipy.ai`; the
website simply does not point at it. The gate says it plainly: "Point the
site's /download at those bytes."

**The fix is already written, reviewed, merged and built.** `aniticipy-web`
branch `cloudflare` (the branch the live `anticipy-site` Worker is built from)
carries `src/app/download/route.ts` redirecting GET and HEAD to
`https://api.anticipy.ai/mac/Anticipy-for-Mac.zip`, and the OpenNext build is
sitting in that checkout, smoke-tested against `wrangler dev`. It has never
been deployed. One command finishes it:

```sh
cd <aniticipy-web checkout>
CLOUDFLARE_ACCOUNT_ID=114587b715e702461766369b01d42fc7 npx wrangler deploy
```

Then re-run `overnight/stranger_gate.py`; leg 11 is the last red leg, so the
gate goes fully green. Note the site is **not** on Vercel: merging to `main`
deploys nothing that reaches the domain. See `anticipy-website-hosting` notes.

## Defect 2 — the connected-API hand cannot see any connection

Verified four ways here, not inferred:

1. `brain/hands.py:1066`, inside `read_connections()`, does
   `GET {base}/api/collections/connections/records`.
2. The Worker's records API defines exactly these collections
   (`migration/workers/src/api/schema.ts`): `agents, events, evidence, jobs,
   owner_profile, owners, pendants, purges, segments`. There is no
   `connections`.
3. `resolveCollection()` (`api/records.ts:206`) is
   `return COLLECTIONS[name] ?? null` — an unknown name resolves to null.
4. No bespoke Worker route serves that path; `grep` for
   `collections/connections` across `migration/workers/src/` returns nothing.

So the request can never succeed. `read_connections()` is careful about this —
its docstring says None means UNKNOWN, "never 'connected nothing'" — so it
fails safe rather than lying. But `gather_context()` (`brain/hands.py:1182`)
builds "the facts for one step" with `connections=read_connections(...)`, which
means **every step the API hand takes believes the owner's connections are
unknown**, even though the connection genuinely exists in D1 and the iOS
Settings screen displays it.

The real surface is `/me/connections`
(`migration/workers/src/routes/connections_api.ts:1610`, routed at
`index.ts:298`). It is **not** a drop-in fix: that route begins with
`whoIsAsking(request, env)` and answers 401 to anything without a signed-in
owner session, while the brain holds only a service token.

So this needs a decision, not a patch:

- **Option A** — add `connections` to the records API `COLLECTIONS` with the
  same owner-scoping every other brain read uses. Smallest change, reuses the
  guard the brain already relies on. Requires care that the list rule scopes to
  the owner and nothing else.
- **Option B** — add a service-token route beside `/me/connections` that
  returns the same rows for an explicitly named owner.

I did not implement either. It changes an authorization boundary on production
data, one owner's connections leaking to another would be a release blocker,
and this machine cannot test it live. It wants someone with credentials and a
live check.

## Everything else

A traced audit of proactivity, the API layer, the browser layer, text-first,
sync, memory durability, cost and the first-run journey produced 42 candidate
findings at blocker/high/medium. They are **not** reproduced here, because they
were produced by tracing agents and had not yet survived adversarial
verification when this note was written — in a comparable pass roughly half of
such findings were refuted or downgraded once challenged. Publishing unverified
findings as defects is the thing this repo's laws exist to prevent.

The two defects above are stated because I verified each of them myself,
end to end, on this machine.
