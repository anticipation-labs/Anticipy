# URLS.md — URL consolidation (frozen)

`anticipy.ai/app` is the single canonical entry point. Everything else either redirects to it or is removed.

## Canonical map

| Path | Behavior | Verification |
|---|---|---|
| `/` | Landing page → CTA to `/app` | HTTP 200, contains `<a href="/app">` or equivalent |
| `/app` | The full product entry: signup, download, install, dashboard. **The only place a user does anything.** | HTTP 200, renders signup form, shows download CTA after auth |
| `/app/download` | Internal sub-route inside `/app`. May exist but reachable only after auth. | HTTP 200 only with valid session, otherwise 302 to `/app` |
| `/download` | **301 redirect to `/app`**. No standalone page. | HTTP 301 → `/app` |
| `/engine` | **301 redirect to `/app`**. No standalone page. | HTTP 301 → `/app` |
| `/install.sh` | Bash installer at root for `curl ... \| bash` install. May exist. Points at the same DMG as `/app/download`. | HTTP 200, content-type `text/x-shellscript`, contains R2 DMG URL |
| `/dl/Anticipy_*.dmg` | Vercel rewrite to R2 for the actual DMG. Single canonical URL for the binary. | HTTP 200, content-type `application/x-apple-diskimage`, sha256 matches manifest |
| `/api/app/state` | Internal API for the live app's state. May exist. Not user-facing. | HTTP 200 with valid session |
| `/api/engine/*` | **Removed.** Engine runs locally on the user's Mac; the cloud should not expose engine APIs. | HTTP 404 or removed entirely |
| `/funded` | Investor page. Currently has known red flags. Not in scope for this loop. | (skipped — not part of the consumer journey) |

## What this means concretely

Currently the live site (per Omar's 8:10 AM Codex report) has /app, /download, /engine all separately addressable. /download was pointing at an older DMG until cdb1139 fixed it. /engine status is "ready" as a separate page.

The fix: collapse /download and /engine into /app. /download → 301 → /app. /engine → 301 → /app. The only place a user lands, signs up, downloads, installs, and uses Anticipy is /app.

## Why this matters

A stranger does not type `/download` or `/engine`. They go to the URL their friend told them about: `anticipy.ai/app`, or they Google "anticipy" and click the first link. If multiple URLs are addressable, search results split between them, social shares break, and the site feels patchy. One URL. One product. Apple-like.

## Verification (scripts/regression.sh)

```bash
# E1 verification
curl -sI https://anticipy.ai/download | grep -E "^location: .*\/app" || fail
curl -sI https://anticipy.ai/engine   | grep -E "^location: .*\/app" || fail
curl -s  https://anticipy.ai/app      | grep -q '<form'              || fail
curl -sI https://anticipy.ai/api/engine/foo | grep -E "404|410"      || fail
```

## When this changes

Only Omar changes this. If you (the build system) need a new public path, write `state/decisions/queue.md` with the proposed addition and a justification. Default: do not add the path. Use a sub-route under `/app` instead.
