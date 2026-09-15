## What changes

<!-- One paragraph: which component, which behaviour, why now. -->

## Evidence

<!-- The command and the last line of each suite you ran. Name any leg that is red or UNPROVEN and why. -->

## Checklist

- [ ] Target branch is `cloudflare-backend`; nothing here touches `main`.
- [ ] Commits are path-limited (`git add <files>`; `git commit -- <paths>`); no other session's work is swept in.
- [ ] The suites for every directory I changed ran green offline (`docs/TESTING.md`), and I read the exit codes, not a pipeline's last stage.
- [ ] iOS or Mac change: `CURRENT_PROJECT_VERSION` moved in both `app/ios/project.yml` and `app/ios/Anticipy.xcodeproj/project.pbxproj` in this same change.
- [ ] Extension change: `manifest.json` `version`, `ENGINE_BUILD`, the iOS `expectedExtensionVersion` and `StaleExtensionTests` agree; `sh extension/build-zip.sh` ran and all three ZIP aliases are committed; `python3 proof/audit/check_extension_package.py` passes.
- [ ] D1 change: the migration is additive and rerunnable (`proof/audit/d1_additive.py` accepts it) and is added to the API deploy job.
- [ ] No pattern-match decides meaning (HARNESS-LAWS Law 1); any `TAPE:` carries a red `overnight/tape_gate.py` leg (Law 2).
- [ ] An adversarial review pass ran and its findings are recorded above (Law 6).
- [ ] Docs are public-safe: no personal absolute paths, e-mail addresses, phone numbers, record ids, provider budgets, credential dates, invite links, or secret values.
- [ ] The title does not contain `[ship]` unless a TestFlight upload is intended.

## Rollout

<!-- What has to be dispatched after merge, if anything (`docs/RELEASE.md`), and how it will be verified live. -->
