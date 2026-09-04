# Branch deletion manifest — 2026-09-04

Every branch deleted in the 2026-09-04 cleanup, recorded by SHA so it can be
restored with `git branch <name> <sha>` (objects survive locally; GitHub keeps
them reachable for a period after ref deletion).

Nothing here carried unique work. The first 9 are strict git ancestors of a
branch that was kept; `codex/anticipy-v75` had 3 of 4 commits already applied
by patch-id and a 4th that was a symmetric build-75 version bump (obsolete at
build 88+); the 15 `claude/*` branches sit on an unrelated root and were
path-superseded.

| branch | SHA | last commit date | subject | why safe |
|---|---|---|---|---|
| `devin/1784393000-emotive-redesign` | `8e65ffaf` | 2026-08-03 | Log unexpected waitlist route exceptions | strict ancestor of main |
| `devin/1785000000-seo-polish` | `424a26ff` | 2026-08-03 | Remove opengraph-image.tsx so og:image uses the og.png product photo | strict ancestor of main |
| `merge/v7-resync-2026-05-30` | `fac316d5` | 2026-05-30 | build: gitignore desktop/target + *.dmg (prevent giant build artifac | strict ancestor of main |
| `harness/tejas-fixes` | `2c524ad9` | 2026-08-24 | fold Fifty Moments of Done into the Brief; retire the separate plan  | strict ancestor of cloudflare-backend |
| `overnight-directed-speech` | `ee84c3ae` | 2026-08-05 | Held-out verdict: PARKED. The rule was beat the baseline; it did not | strict ancestor of cloudflare-backend |
| `pendant-system` | `b5b87e84` | 2026-08-12 | A plan already running absorbs its re-mentions; a bare ack is never  | strict ancestor of cloudflare-backend |
| `recovery/full-reconstructed` | `3b106c24` | 2026-08-18 | Commit the pendant firmware source — it lived on one laptop | strict ancestor of cloudflare-backend |
| `codex/anticipy-v75` | `89e3d595` | 2026-08-22 | Ship Anticipy build 75 with standalone extension | 3/4 applied by patch-id; 4th an obsolete version bump |
| `devin/1787105362-proto-cad` | `99ad2c6f` | 2026-08-23 | pendant v6.2: enlarge internal cavity per fit feedback (+20mm L, +10 | strict ancestor of devin/1787507284-pendant-v63 |
| `claude/adoring-kirch-f39b3b` | `671102e9` | 2026-04-29 | Per-user calendar, /api/health, Deepgram drop recovery, setup card p | path-superseded (unrelated root) |
| `claude/amazing-satoshi` | `5657d84f` | 2026-04-14 | Fix double-execution guard: atomic UPDATE replaces SELECT→check→UPDA | path-superseded (unrelated root) |
| `claude/beautiful-gagarin-84b17b` | `d7702670` | 2026-04-17 | Fix action pipeline: always save note + anticipy_actions row, even f | path-superseded (unrelated root) |
| `claude/competent-hertz` | `0445ca65` | 2026-04-14 | Fix double-execution guard: use atomic UPDATE...RETURNING instead of | path-superseded (unrelated root) |
| `claude/determined-hugle-72590b` | `3f7aad12` | 2026-04-16 | Fix extension access code: default to "123" when env var unset | path-superseded (unrelated root) |
| `claude/exciting-bartik-3a4ad7` | `c622b998` | 2026-04-30 | Nav: fix invalid transform on hamburger middle bar | path-superseded (unrelated root) |
| `claude/festive-banach-52f491` | `838eadbf` | 2026-04-17 | Fix intent execution pipeline: broadcast confirmed_intent to extensi | path-superseded (unrelated root) |
| `claude/gallant-murdock` | `1befa70b` | 2026-04-13 | Make intent extraction genuinely intelligent: context-driven reasoni | path-superseded (unrelated root) |
| `claude/gracious-chaplygin` | `ba10b081` | 2026-04-15 | Add 7 internal doc pages with full content — replace GitHub links wi | path-superseded (unrelated root) |
| `claude/heuristic-sanderson-bf9b2d` | `76368460` | 2026-04-30 | Harden engine: fail-closed secrets, WS abuse limits, expanded safety | path-superseded (unrelated root) |
| `claude/kind-cori` | `5ae7b9ab` | 2026-04-13 | Upgrade intent analysis to genuine LLM reasoning: open action types, | path-superseded (unrelated root) |
| `claude/sleepy-ride` | `63140826` | 2026-04-14 | Fix browser agent startup timeout: retry loop + 60s event timeouts | path-superseded (unrelated root) |
| `claude/vibrant-hodgkin` | `120b07e4` | 2026-04-14 | Fix browser agent: stale lock cleanup, headless detection, thread is | path-superseded (unrelated root) |
| `claude/xenodochial-euler-29ad8e` | `ef4e76d4` | 2026-04-26 | Send intent emails to user_email + omar@anticipy.ai when provided | path-superseded (unrelated root) |
| `claude/zen-banach` | `b2662e98` | 2026-04-15 | PCB schematic, assembly docs, packaging design, signup flow fixes | path-superseded (unrelated root) |

## Kept deliberately

`main`, `cloudflare-backend`, `jose_anticipy_system`, `cloudflare-migration` (local-only),
and the four hardware branches carrying unique CAD/PCB/firmware work:
`codex/investor-xiao-r0`, `devin/1788105992-custom-pcb-r1`,
`devin/1787853189-hardware-v1`, `devin/1787507284-pendant-v63`.

Harvested-but-NOT-deleted (their docs are now in this directory; delete when ready):
`hoe/build`, `deploy/preorder-to-main`, `recon/engine-state-2026-05-11`,
`feature/r2-dmg-hosting-clean` (holds `extension_v2/`, `extension_v3/` and four
packaged extension zips in `public/` — binaries, not copied here).
