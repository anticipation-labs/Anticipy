# anticipy-api.omar-114.workers.dev serves a build we stopped deploying

2026-09-04, ~19:00 UTC onwards. UNRESOLVED. Recorded because the next person to
deploy this Worker will otherwise spend the same hour, and because it is the
Cloudflare version of the failure CLAUDE.md's deploy rule already names:
"`railway up` reports success while failing."

## The symptom

`wrangler deploy` succeeds. A version is created. `wrangler deployments list`
shows it at **100%**. `wrangler versions view <id>` shows the correct secrets
and bindings. And the live URL keeps serving the build from **18:39**.

Bracketed by probing routes with known deploy times:

    /internal/state       ported ~17:55   LIVE  answers
    /internal/notes       ported ~18:20   LIVE  answers
    /internal/reminders   ported ~18:39   LIVE  answers
    /internal/comments    ported ~18:39   LIVE  answers
    /internal/assistant   ported  19:03   LIVE  "hq data routes not yet ported"

That last string was DELETED from src/index.ts in the same commit that added
the assistant. A response containing it is proof the edge is running code that
no longer exists in the tree.

`/internal/health` says `channels: {email:false, sms:false}` while
`wrangler versions view` lists RESEND_API_KEY and TWILIO_AUTH_TOKEN as bound
secrets on the version that is supposedly at 100%. Those two facts cannot both
describe the same running script.

## What was tried, in order, all of it failing

1. Re-deploy. Several times. Success each time, new version id each time.
2. `npm run deploy` (the project's own script, with `--config wrangler.jsonc`
   and the asset staging step) rather than a bare `wrangler deploy`.
3. `wrangler versions deploy <id>@100 --yes` — explicit promotion. Reported
   `SUCCESS ... at 100%`. No change at the URL.
4. Declaring `"workers_dev": true` explicitly, in case the subdomain route was
   never bound. No change.
5. **Setting `"workers_dev": false` and deploying — THE URL STILL RETURNED 200.**
   That is the finding that matters: if the hostname were served by this
   Worker's workers.dev route, disabling that route would have taken it down.
   It did not. Whatever answers that hostname is not this Worker's workers.dev
   binding.
6. A version preview URL (`<prefix>-anticipy-api.omar-114.workers.dev`) returns
   a Cloudflare error page rather than the Worker.
7. Cache was ruled out: the responses carry no cache headers, a cache-busting
   query changes nothing, and the assistant probe is a POST.

## What is NOT the cause

The code and the config are fine, and this is not a guess:

    wrangler dev --remote   (local code, REMOTE bindings and D1)
      /internal/health    -> channels {email:true, sms:true}
      /internal/assistant -> answers from the real board
      full contract suite -> 146 passed, 0 failed

So the bundle, the secrets, the bindings and every route work when the edge is
taken out of the loop. `wrangler deploy --dry-run` confirms the uploaded bundle
contains `hqAssistant` and does NOT contain the stale catch-all string.

## What to try next

- The Cloudflare dashboard for account `114587b715e702461766369b01d42fc7`:
  Workers & Pages -> anticipy-api -> Settings -> Domains & Routes. Look for a
  route or custom domain bound to that hostname independently of the
  workers.dev toggle, and for a Gradual Deployment holding an old version.
- Failing that, deploy under a different script name and point the cutover at
  the new hostname. The name is cosmetic; nothing outside this repo depends on
  it yet, and `next.config.mjs` has not been repointed.
- Cloudflare support, with the two contradictory observations above: a version
  at 100% whose secrets the running script cannot see, and a hostname that
  survived `workers_dev: false`.

## The rule this confirms

Never read a deploy's exit code as evidence. Ask the live URL what it is. The
cheapest probe here is a string that exists in exactly one build:

    curl -s -X POST -H "X-Internal-Key: $KEY" .../internal/assistant \
      -d '{"actor_id":"...","messages":[{"role":"user","content":"hi"}]}'

An answer means the new build. `hq data routes not yet ported` means the old
one, no matter what wrangler said.
