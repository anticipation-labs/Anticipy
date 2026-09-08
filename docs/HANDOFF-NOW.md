# Anticipy handoff, 7 September 2026

Use `/Users/omarebrahim/Anticipy`, branch **cloudflare-backend**. `main` is an
unrelated lineage. The Mac/iOS source and Cloudflare backend are here.
The owner requested an immediate stop to further repairs and synchronization.
No additional repair work or overnight automation is running.

## Exact state

- **Source repair:** `0cb078e6`. Tejas's PRs #59 and #62 were already merged;
  his front-facing Mac window, meeting library and local notes are included.
- **Mac binary:** build **171**, version **1.1.1**, universal Intel/Apple Silicon,
  signed, Apple-notarized and stapled. Committed at
  `migration/workers/public/mac/Anticipy-for-Mac.zip` via release commit
  `f0b657e0`. Local signature, ticket and Gatekeeper checks passed.
- **Browser agent:** source and downloadable archive **0.18.0** already match.
  A user's old unpacked Chrome installation still needs an explicit update;
  publishing the ZIP does not update that installation automatically.
- **iPhone:** the previously verified TestFlight release is **170**. The shared
  project build number is now 171 for the Mac release. No iOS 171 upload was
  requested or performed by this Mac task.
- **Backend:** previous live API/brain release is `cb201095`. This Mac task
  changes client delivery and static downloads; it changes no brain code.
- **Engineer briefing:** `docs/engineer-handoff-2026-09-07/brief.md`, its
  README, 500 acceptance scenarios and CSV result sheet were committed by the
  parallel documentation work in `b52327e1`. Scenarios are acceptance cases,
  not a claim that 500 cases were executed.

## What was repaired

The public Mac ZIP was build 119, an old menu-bar app pointing at the retired
backend. The new source already feeds transcript text into the same authenticated
Cloudflare events API as the phone. Its offline queue now retries final speech,
uses stable capture identities to avoid duplicate inserts, preserves new lines
while requests are in flight, and prevents old responses from signing out a new
account. Queue storage errors remain visible and do not erase unreadable data.

Both speaker channels and original capture times were verified through the
actual compiled MacBackend against the live API. Seven actual-client failure
cases and the full Mac/iOS logic suites passed. A new Mac window was launched.
No human-language classifiers, phrase lists or intent regexes were added.

## Release handoff

Apple accepted ticket `4deaee84-257a-46d5-8602-6243b27034f2`. Run
`34179162484` is marked failed solely because GitHub disallows Actions-created
PRs. The artifact itself passed; its branch was integrated directly without
conflict. The signed ZIP's SHA-256 is
`c27dd01e3257e2d8df99e2f5ff1a80f943b53eab01a5d9ab8431bed8186e1cbb`.

The API deployment to publish this static ZIP will be dispatched after the
handoff commit is pushed. Until live byte verification succeeds, distinguish
**committed notarized Mac 171** from **the public URL serving Mac 171**.

Deployment command, if the next operator needs to rerun it:

```sh
gh workflow run brain-deploy.yml --ref cloudflare-backend -f component=api -f confirm=DEPLOY -f cap=100
```

Read back `https://api.anticipy.ai/mac/Anticipy-for-Mac.zip` and compare the
SHA-256 above. Do not redeploy the brain for this static-asset release.

## Boundaries and remaining work

- The Mac sends transcript text. Typed meeting notes and raw audio stay local.
  Brain follow-ups use the phone and messaging; there is no Mac task inbox.
- The successful live transport probe erased its synthetic account. An initial
  probe crashed during its readback, leaving synthetic owner `54f7tfow74itqqq`
  and two harmless transcript lines (no phone, browser or integrations). One
  known event is `504b7319f4044e74a029577e4dcbff12`. Use the normal account
  erasure lifecycle for that fixture; do not delete arbitrary owner rows.
- Live model decisions, real meeting audio capture and the entire Mac UX were
  not re-audited by this release task. The earlier 15-person lab and follow-up
  results remain under research/ and the PDF report.
- The marketing site's `/download` page could not be verified in this final
  pass (HTTP 403 to the read-only fetch). The API-hosted Mac URL is canonical.
- The draft GitHub release `mac-candidate-171` is a signing input, not a public
  release. The approved artifact and Apple receipt are committed separately.

## Local-only material

`work/` contains private credentials, raw diagnostics and temporary signed
builds. `output/playwright/` contains raw browser traces/screenshots that may
include session data; it is now ignored explicitly. These remain on the Mac
and are intentionally not uploaded to Git. No user files were deleted.
The pre-existing live-stall proof script and masked TestFlight receipt are
included in this handoff; the script was syntax-checked, not rerun.

Read HARNESS-LAWS.md and CLAUDE.md before any edits. Stage and commit exact
paths in this shared checkout. Ship iOS through CI only. Keep both project
build numbers together. Neither paused overnight automation was resumed.
