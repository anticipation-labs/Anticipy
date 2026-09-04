# Branch archive — 2026-09-04

Law 4 says state lives in repo files, never in chats. This directory is the
harvest taken before the 2026-09-04 branch cleanup, so that deleting a ref
never deletes a finding.

## What is here

- `DELETED-BRANCHES.md` — every branch removed in the cleanup, by SHA, with the
  evidence that made it safe. Restore any of them with `git branch <name> <sha>`.

- `hoe-build/` — from `origin/hoe/build`, a *fourth* unrelated root in this repo
  (`79112f0b`), 2,083 files of which 2,072 exist on no other branch. Only the
  prose was taken: `CANON/` (the doctrine: what Anticipy is, the proactive
  engine, architecture, definition of done), `PLANS/` (numbered FIX- plans), and
  the top-level design/audit markdown. Its 984 `marketing/` files, 233 `logs/`
  and its own `engine/` were deliberately left behind — that engine shares only
  five basenames with today's `brain/` and is a different system.

- `recon-engine-state/` — from `origin/recon/engine-state-2026-05-11`. A
  read-only audit of production as it stood: `ENGINE_STATE.md` plus 17 captured
  live artifacts (production OpenAPI, Railway health, env-key inventories, a
  realtime listen log). This is exactly the artifact class Law 4 wants kept.

- `deploy-preorder/` — from `origin/deploy/preorder-to-main`,
  `planning/00-handoff/`: the 2026-05-30 session handoff, `BLOCKERS_LIVE.md`,
  the bug list and cost-ceiling audits. That branch carries 22,568 lines that
  never landed on `main`, including a Resend receipt-email pipeline
  (`src/lib/resend.ts`, `src/emails/Receipt.tsx`) that appears never to have
  shipped. Whether that is still wanted is a product question, recorded here
  rather than lost.

## Branches harvested but NOT deleted

`hoe/build`, `deploy/preorder-to-main`, `recon/engine-state-2026-05-11`, and
`feature/r2-dmg-hosting-clean` still exist. Their prose is now here, so they can
be deleted whenever someone decides to — but that was not part of the approved
cleanup, so they were left alone. `feature/r2-dmg-hosting-clean` is the only ref
holding `extension_v2/`, `extension_v3/` and four packaged extension zips; those
are binaries and were not copied.

## What this cleanup did NOT resolve

`main` and the `cloudflare-backend`/`jose_anticipy_system` line share **no common
ancestor**. This repo has four unrelated roots. `main` is the local Mac Action
Engine + ESP32 line (4,599 files); `cloudflare-backend` is the iOS + PocketBase +
brain + harness line (1,957 files). They have six paths in common. Neither is
"ahead" of the other and neither can be deleted without destroying a product.
That decision was deliberately left open.
