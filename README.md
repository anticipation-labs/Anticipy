# Anticipy

The proactive assistant: an iPhone captures speech, a server brain interprets it
with context and memory, and approved work reaches browser, API, or device hands.

**Work on `cloudflare-backend`.** It is the source of record for the iOS app and
Cloudflare API Worker. `main` is a different lineage and has no iOS app.

Read [HARNESS-LAWS.md](HARNESS-LAWS.md), [CLAUDE.md](CLAUDE.md), and
[AGENTS.md](AGENTS.md) before changing anything. Meaning belongs to a model with
context; regexes, word lists, and thresholds must not decide what people mean.

## Start here

- [Mac development guide](docs/LOCAL-DEVELOPMENT-MAC.md): the prepared checkout,
  local Worker, simulator, tools, and commands.
- [Setup baseline, 2026-09-06](research/2026-09-06-mac-development-setup.md):
  measured checks and remaining limits.
- [Current audit and delivery status](research/audit-2026-09-06/PLAN.md):
  deployed repairs, real-model tests, provider checks and unfinished reset work.
- [Product brief](docs/BRIEF.html): product behavior, screens, and evidence.
- [iOS release handoff](docs/HANDOFF-SHIP-IOS.md): CI release process. Read the
  actual workflow too; historical instructions can lag the code.

Before editing code:

```sh
git status --short --branch
sh app/ios/Tests/run_all.sh
```

The iOS app is in `app/ios/`; the Cloudflare API Worker is in
`migration/workers/`; the Python brain is in `brain/`; browser execution is in
`extension/`. The production API is `https://api.anticipy.ai`.
The PocketBase hooks and their startup instructions are gone; the migration runbooks are historical
references. `backend/pb_public/` remains the source for Worker static assets.

iOS source changes and their build-number increase belong in the same commit.
Edit both `app/ios/project.yml` and
`app/ios/Anticipy.xcodeproj/project.pbxproj` by hand. Build locally for the
simulator; ship through CI. Stage named paths and commit with explicit paths so
another agent's work cannot be included accidentally.
