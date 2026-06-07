# Last Lap

Lap: 20260607T075335Z
Date: 2026-06-07T08:22:56Z
Milestone: M1 - real front door
ALL_MILESTONES_DONE: false

Judge verdict: PENDING

What changed:
- In the production-linked source tree `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`, changed the Tauri app so first launch shows the Anticipy popover and the Rust microphone permission request is only user-initiated through the wizard.
- Changed `desktop/scripts/tauri.mjs` so the `.app` is ad-hoc signed before DMG creation.
- Fixed the same wrapper to write every plausible DMG output path, preventing `scripts/build_dmg.sh` from copying a stale unsealed DMG.

What M1 verification did:
- Ran `bash scripts/build_dmg.sh` through the production packaging path after the fixes.
- Mounted the regenerated root DMG and verified `/tmp/anticipy-m1-mount-20260607T075335Z/Anticipy.app` with `codesign --verify --deep --strict --verbose=2`.
- Confirmed `codesign -dvvv` reports `Sealed Resources version=2`.
- Confirmed `spctl --assess --type execute -vv` still rejects because the app is ad-hoc signed and not Developer ID signed/notarized.
- Local root DMG SHA-256: `ddd20a490ac6a301fc9f6d321fd4ec53e6d74711364929171c869882119c7692`.
- Public `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` still serves the old artifact size, so the rebuilt DMG is not deployed.

What was inconclusive:
- Mounted-DMG GUI launch showed the Anticipy popover, but the screen was already polluted by unresolved microphone permission prompts in Safari/Chrome. This is not clean launch proof.
- The production-linked repo had substantial pre-existing dirt; this lap only intentionally changed `desktop/src-tauri/src/lib.rs` and `desktop/scripts/tauri.mjs`, while package builds also regenerated extension zips and an engine spec.

Next:
- Cleanly isolate the remaining microphone prompt source on first launch and prevent any automatic prompt before the visible surface.
- Decide a safe publish path for the production-linked repo that does not run `scripts/ship.sh` as-is, because that script pushes to `origin main`.
- Upload/deploy only after the local mounted DMG launches cleanly and the separate judge can verify the public artifact.
