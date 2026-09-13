# Workspace reconciliation — 2026-09-13

This inventory explains what “sync everything” means without overwriting
legitimate work or publishing secrets. It compares the original held checkout at
`e6161de267901b22ff93a401197c74e444d4d0eb` with released
`a29bcea66565e8efe2d1710f0ba451d6af9a2548` on `cloudflare-backend`.
Inventory observed at approximately 16:25 UTC; future edits require a new check.

## Result

The original checkout had 156 status entries and an empty index:

| Classification | Entries | Decision |
| --- | ---: | --- |
| Byte- and mode-identical to released source | 86 | Already in GitHub through the reviewed release; do not commit duplicates. |
| Different, superseded by released source | 9 | Preserve locally; do not roll back newer release repairs. |
| Unpublished historical Markdown | 55 | Retain privately pending manual content review. Publish a fresh safe status/handoff, not a bulk copy. |
| Explicitly held files / excluded state roots | 6 | Leave untouched. Directory entries are roots, not counts of files inside them. |

No non-held source or test candidate was absent from the release. This does not
mean the whole product is complete. It means the previously reviewed code has
been reconciled; new defects and features are separate work.

The integration checkout also contained one private OpenRouter operational note.
It is excluded from publication. A credential-pattern scan is not sufficient to
make historical notes public: ordinary prose can contain identity, billing,
provider, private-data and operational details.

## Nine superseded entries

| Original path(s) | Why not copy them over the release |
| --- | --- |
| `.github/workflows/brain-deploy.yml` | Earlier first-owner/capacity-one flow predates complete-fleet, active-effect and snapshot preflight. |
| `app/ios/Anticipy/AnticipyApp.swift`, `extension/background.js` | Older extension-version labels; release expects 0.18.2. |
| `migration/workers/public/anticipy-extension.zip`, `migration/workers/public/anticipy-claude-version-extension.zip`, `migration/workers/public/anticipy-codex-version-extension.zip` | Older generated extension payloads; regenerate from a reviewed version instead. |
| `proof/audit/d1_additive.py` | Missing the released SQL-as-one-argument correction. |
| `tests/test_d1_additive.py`, `tests/test_d1_connector_readiness.py` | Missing released SQLite fixture portability/integrity checks. |

## Held boundaries

The original `TranscriptCursor.swift`, `TranscriptCursorTests.swift` and
`run_cursor_tests.sh` experiment remains excluded. `.wrangler/`, `desktop/` and
`engine/` are held/excluded roots, not folders to traverse or sweep into Git.
Env files and owner resume prompts remain private. Nothing here authorizes
deletion, reset, stashing, or rewriting of that checkout.

## Collaboration workflow

Use a clean checkout/worktree based on the remote `cloudflare-backend` branch.
Do not run a blanket pull or branch switch inside the original dirty checkout.
Read [AGENTS.md](../AGENTS.md), [HARNESS-LAWS.md](../HARNESS-LAWS.md),
[CLAUDE.md](../CLAUDE.md) and the [development guide](LOCAL-DEVELOPMENT-TEJAS.md).

Each change needs a bounded owner, reproduction/test evidence, independent review
and a PR targeting `cloudflare-backend`. Stage named files and use
`git commit ... -- <exact paths>`; never blanket-add or use a bare shared-index
commit. A public branch must not contain raw operational notes or env files.

The GitHub default branch remains `main`, a different lineage. Existing hardware
PRs target that lineage and are not automatically dependencies of the iOS release.
Discuss shared firmware contracts explicitly; do not merge all branches together.

The [release board](EOD-READINESS-2026-09-13.md) names current evidence and open
work; the [firmware handoff](FIRMWARE-COLLABORATION.md) names the radio/phone seam.
