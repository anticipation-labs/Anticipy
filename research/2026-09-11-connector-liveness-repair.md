# Connector transport liveness repair — local candidate

Date: 2026-09-11. Author: Tom. Branch: `cloudflare-backend`, based on `943cd79`.
Scope: the Composio provider transport and provider-focused regression tests only.
Independent review is required; these results are not live connector acceptance.

## Reproduced defect and repair

Before the patch, the provider passed no abort signal to fetch, awaited response
JSON without a deadline, and followed arbitrarily many distinct connected-account
cursors. A stalled session creation also kept that owner's single-flight entry
pending. The new regressions first exited 1 with 18 failures and four controls
passing (`work/tom-connector-liveness-red-20260911.log`). Watchdogs made those
reproductions finite; the source confirmed the missing deadlines/page ceiling.

The provider now enforces:

- 20,000 ms per request across headers and body, with an AbortController attached
  to the actual fetch and explicit body cancellation on failure. A raced deadline
  also bounds a non-cooperating injected transport; late responses are disposed
  of, not cached as sessions.
- 30,000 ms for the whole connected-account or tool-catalogue page walk. The next
  request receives only the remaining budget. Connected-account pagination stops
  at ten pages; exhausting the cap throws rather than returning a partial list.
- A 4 MiB streamed response-byte ceiling, enforced on actual chunks even when
  Content-Length is absent or false. The bounded text is parsed only after EOF.
- Positive, integer, lower-only constructor overrides for deterministic tests.
  No new environment variables, secrets, packages, remote endpoints, or retries.

These are asynchronous I/O bounds, not a promise that JavaScript timers can
preempt synchronous CPU work. The byte ceiling bounds what JSON parsing receives;
the deadline is checked again after parsing. A malicious injected implementation
that ignores AbortSignal may leave its own private promise pending, but the
adapter settles and releases the owner's single-flight waiters. Native fetch
actually closed the stalled local sockets in the tests.

## Preserved authority and uncertain effects

Every owner guard, provider owner echo check, reverse session-owner cache check,
stored write permission, and execute call site is unchanged. No partial account
list is returned on timeout, page exhaustion, malformed data, or foreign owner.
Timed-out session creation is not cached, and a subsequent explicit session call
can create a fresh session. There is no automatic provider retry.

Timeout, interrupted body, and oversized body failures use HTTP status 0. Existing
`isRetryableStatus(0) === true` is preserved as descriptive metadata, not an
authorization to retry. The actual API hand maps it to `kind=other` and
`mayHaveLanded=true`; the actual route disposition for a write is `needs_user`,
`effectUncertain=true`, retaining the API lane rather than retrying via the browser.
The new integrated regression exercises both functions and observes one execute
POST. A revoke timeout does not continue to DELETE.

Arbitrary exception names are no longer copied into errors. Fixed tokens describe
transport timeout/failure/oversize; the existing genuine TypeError category is
preserved by type, not its mutable name. Provider HTTP error-code redaction remains
unchanged. Two existing redaction assertions now require the complete fixed safe
message instead of a URL placeholder copied from an arbitrary exception name.

## Verification

All commands used a clean environment, dotenv autoload disabled, npm offline, and
the OS outbound-network denial with loopback allowed. No real provider account,
customer data, personal browser profile, production API, secret, or message send
was used. No commit, push, or deployment was performed by this lane.

- Focused liveness suite: 28 cases passed, actual exit 0.
- Full Worker `npm test`: all 44 registered commands passed, actual exit 0. The
  provider gate includes the imported liveness suite; all 203 provider cases pass.
- Worker `npm run typecheck`: actual exit 0.
- `git diff --check` for owned tracked files: clean.

Evidence logs (ignored local files):

- `work/tom-connector-liveness-red-20260911.log`
- `work/tom-connector-liveness-green-20260911.log`
- `work/tom-connector-full-api-20260911.log`
- `work/tom-connector-typecheck-20260911.log`

Coverage includes native loopback HTTP stalls before headers and during body;
shared header/body budget; cancelled/rejecting/never-settling body cleanup;
late response disposal; single-flight release and different-owner independence;
distinct-cursor exhaustion, complete final-page control, aggregate deadlines;
foreign-owner refusal; content-length lies and exact UTF-8 boundary control;
malformed JSON retaining a known HTTP error; bounded option rejection; and
ambiguous execute/revoke no-retry behavior.

## Current primary documentation consulted

- [Cloudflare Web Standards](https://developers.cloudflare.com/workers/runtime-apis/web-standards/):
  AbortController/AbortSignal and Workers timer/performance clock limitations.
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/):
  per-isolate memory and cancellation of unneeded response bodies.
- [Cloudflare Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/):
  bounded buffering and runtime safety guidance.
- [Composio v3.1 connected-account listing](https://docs.composio.dev/reference/api-reference/connected-accounts/getConnectedAccounts):
  owner filtering, cursor pagination, and the documented items/next_cursor shape.

ECC defect/orchestration and Cloudflare Workers skills informed the regression-first
workflow and transport-only bounds. No API version or provider semantics were
changed based on documentation alone.

## Frozen code hashes for independent review

```text
0ee0d628b07d49ad2c74f9684675d5e56ab9c231bd026344714664081720f61a  migration/workers/src/connections/provider.ts
f1b4edfd8fa7b5bb330b4ade3b67c3028320b67fd47830860ada0ccc01bb4655  migration/workers/test/connections-provider.test.ts
ff33ea9e7ad748f788c799e79966d7781ba4642b65e561cc0adf07236635f685  migration/workers/test/connections-provider-liveness.test.ts
```

Remaining: independent review, root integration/release gates, and separately
scoped real-account connector tests. Local transport success does not prove OAuth
pairing, live credential validity, provider-specific tools, or every connector.
