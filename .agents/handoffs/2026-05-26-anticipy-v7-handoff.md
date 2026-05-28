# Anticipy V7 Handoff - 2026-05-26

This handoff is for the next Codex or Claude Code agent. It is intentionally blunt. Do not claim Anticipy is complete unless `state/COMPLETE.md` exists and `bash scripts/v7/check_done.sh` passes.

## Current Verdict

NOT DONE.

The public shell, public DMG, installed user-device engine, deploy parity, MP3 input, transcript input, computer mic path, real Chrome/no-clone proof, MP3 streak, WER, cost, inference loop, and no-fake-receipts gates have had green proof.

Fresh `bash scripts/v7/check_done.sh` run during this handoff exited `1`. The current red gates are:

- `V7.2_public_dmg_installs`
- `V7.5_public_dmg_sha_green`
- `V7.6_mp3_input_passes`
- `V7.7_text_transcript_input_passes`
- `V7.8_computer_mic_input_passes`
- `V7.9_external_mic_input_passes`
- `V7.10_real_chrome_user_surface_no_clone`
- `V7.11_100_stranger_successes`
- `V7.12_20_successful_verb_categories`
- `V7.13_5_hard_categories`
- `V7.14_last_20_interactions_pass`
- `V7.18_3_clean_room_public_installs`

Important correction: after the latest proof-state commit, deploy parity is green but the public DMG hash check is currently red. The next agent must resolve public artifact parity before counting more product proof as reliable.

## Repo And Worktree State

Use the active shipped worktree:

```text
/private/tmp/anticipy-ship-8c4935a
```

Reason: the original checkout at `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` is on `bootstrap/v4` with old dirty files. The active shipped worktree is the one used for the V7 production push sequence.

Most recent pushed commit before this handoff:

```text
3fe9df546068719958d22e59bd639f65f8af6325
record v7 stranger proof progress
```

Live site check after that push:

```text
https://www.anticipy.ai/api/app/state
commit: 3fe9df546068719958d22e59bd639f65f8af6325
engine: ready
download: ready
mic: ready
```

Earlier production packaging commits:

```text
e11bedcafca867188687507f079f7ab394336f71 ship: update build manifest for ea8b742
ea8b742fc3b19a5825873bb355e93036dae20757 v7: route strangers through real surface receipts
e355a4b v7: record inference eval and current status
95d0a38 v7: improve uploaded-audio transcript fidelity
77f3c34 v7: record real Chrome profile in surface proof
47a1fdf v7: harden public app audio upload driver
fdf3207 v7: route installed users to listen upload proof
```

Manifest DMG SHA from the last successful ship:

```text
4112202be884d65857e0a29f6e6ad1d4f6f81ea206a8f30b68c85ca0c2b64c43
```

Fresh handoff check found the public DMG currently hashes to:

```text
3cf5ef4a260210744409ccfbdee7b796375769fdb5f444b3433f230f5e538f0b
```

The URL is serving a large disk image:

```text
https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg
content-type: application/x-apple-diskimage
content-length: 2704920395
```

This means `V7.5_public_dmg_sha_green` is red right now. Treat public DMG parity as the first blocker.

Manifest nuance:

- `state/builds/manifest.json` points to the bundled DMG source commit `ea8b742...`.
- The live site can report a later commit such as `e11bedc...` or `3fe9df5...` when later commits only changed verifier/proof/state files and not bundled DMG code.
- This is acceptable only when `scripts/v7/check_done.sh` documents the non-DMG manifest commit exception and the public DMG SHA still matches.

## User's Product Definition

Anticipy is the full public product, not a Gmail bot, not a source-only dev server, and not Omar-only.

Correct product path:

```text
https://www.anticipy.ai/app
  -> user signs in / creates account
  -> user downloads the public app / user-device engine
  -> app installs on that user's Mac
  -> engine runs on that user's device
  -> input comes from MP3/audio upload, text transcript, computer mic, external mic, and later pendant audio
  -> engine uses the user's own signed-in browser and app surfaces
  -> engine acts, asks, or declines
  -> proof comes from visible user surfaces, not backend-only claims
```

Required completion language:

- Say `COMPLETE` only if `state/COMPLETE.md` exists and `bash scripts/v7/check_done.sh` passes.
- Say `NOT DONE` when any V7 gate is red.
- Say `STUCK` only for an Omar-only blocker after the required attempts and evidence.

Do not use: `alpha complete`, `prototype complete`, `mostly done`, `works locally`, `Gmail works`, `regression green`, `MP3 button exists`, or `public app is live, so done`.

## Rules To Preserve

1. Public product proof beats source proof.
2. The user-device engine is public software downloaded by each user, even though it binds to localhost on that user's Mac.
3. No cloned Chrome profile counts as product proof. `~/.anticipy/chrome-real-clone` is invalid for V7 proof.
4. Valid surface proof means the same real user or clean-room test-user browser/app surface Anticipy used.
5. Engine logs alone prove nothing. The proof must be visible surface trace, DOM/AX/screenshot/vision, or a competent decline with no broken state.
6. Frozen paths stay frozen unless verifier-first:
   - `engine/app/action_engine/`
   - `engine/app/proactive_day/`
   - `engine/app/anticipy/`
7. If bundled code changes, run `scripts/ship.sh` and prove production received it.
8. Do not commit huge build outputs, bundled model blobs, raw screenshots/audio, or secrets.
9. Do commit small proof JSON, status JSON, handoff docs, and deterministic harness changes when useful.
10. Do not fake the agent's work as the product's work. A Codex action only counts when the installed public product was used and the trace shows what happened.
11. Safety is not the main product feature, but competent ask/decline remains required when acting would be wrong or unprovable.
12. Browser/action/proactive/memory/inference must converge into one user-device product path, not separate demo paths.
13. If a real blocker appears, isolate it, research if needed, patch one layer, rerun proof, and ship if bundled.

## What Has Been Done Recently

### Shipped Product And Harness Work

Commit `ea8b742fc3b19a5825873bb355e93036dae20757` shipped the main V7 route-to-real-surface work:

- `scripts/orchestrate_v6.sh` now uses the deterministic V7 driver selector before prompt-driven fallback.
- Added `scripts/v7/select_stranger_driver.py`.
- `scripts/v7/drive_transcript_paste_ui.py` supports transcript upload/paste and service prechecks.
- `scripts/v6/write_stranger_receipts.py` handles transcript upload input modes.
- `src/app/app/page.tsx` supports `?view=listen` deep link.
- `extension_v4/background.js` falls back to in-memory content script if `content.js` loading fails.
- Added `extension_v4/test_injection_fallback.js`.
- Regenerated `public/anticipy-extension-v6.zip` and `public/anticipy-extension.zip`.
- `scripts/build_dmg.sh` embeds `ANTICIPY_BUILD_COMMIT`.
- `desktop/src-tauri/src/lib.rs` passes compile-time `ANTICIPY_BUILD_COMMIT` to the sidecar.
- Updated `state/STATUS.md` and `state/decisions/queue.md`.

Validations before that commit:

```text
npm run build
cd desktop/src-tauri && cargo check --target aarch64-apple-darwin
python compile checks for changed Python
node extension fallback test
git diff --name-only -- engine/app/action_engine engine/app/proactive_day engine/app/anticipy
git diff --check
```

Then `scripts/ship.sh` was run with the production env file:

```text
ANTICIPY_ENV_FILE=/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local bash scripts/ship.sh
```

Result:

- DMG built.
- DMG uploaded to R2.
- Manifest commit `e11bedcafca867188687507f079f7ab394336f71` pushed.
- Vercel live commit verified at `e11bedc`.
- Public DMG SHA verified as `4112202be884d65857e0a29f6e6ad1d4f6f81ea206a8f30b68c85ca0c2b64c43`.

Then commit `3fe9df546068719958d22e59bd639f65f8af6325` pushed selected proof/state JSON:

- `state/stranger_breadth.json`
- `state/check_done_v7_after_ecommerce.json`
- `state/check_done_v7_post_ship.json`
- `state/v7/input_modes.json`
- `state/v7/no_fake_receipts.json`
- `state/v7/real_surface_probe_post_ship.json`
- selected `state/strangers/*/{persona,script,driver_result,trace,verdict,transcript_quality,cost_breakdown,baseline}.json`
- selected screenshot proof JSON files under `state/strangers/*/screenshots/*.json`

Not pushed on purpose:

- `desktop/src-tauri/resources/parakeet-tdt-0.6b-v3/model.safetensors`
- `desktop/target/`
- `target/`
- raw PNG screenshots
- raw visible-text screenshot dumps
- raw audio
- ship logs
- giant build outputs
- anything matching secret patterns

Secret scan over staged proof diff was clean for:

```text
R2_
SECRET
OPENROUTER
sk-or-
sb_secret
service_role
PRIVATE_KEY
ACCESS_KEY
```

## Agents And Their Findings

### Hegel

Focus: `V7.9_external_mic_input_passes`.

Finding:

- Installed engine endpoint `/api/audio/devices` exposed BlackHole virtual audio and MacBook Air builtin mic.
- macOS tools showed `The printer123 Microphone`, but the installed engine did not expose it as a valid external mic.
- The classifier in `engine/app/product/server.py` rejects names containing `printer` as unsupported, which may be overbroad if that device is a real physical external microphone.

Smallest honest next options:

1. Connect/pair a real external input that the installed engine sees as non-builtin, non-virtual, non-unsupported.
2. If `The printer123 Microphone` is genuinely a real external microphone, fix the overbroad classifier and prove it with installed-engine device enumeration.
3. Do not fake this with BlackHole. BlackHole can help routing tests, but it is not external mic proof.

### Jason

Focus: `V7.18_3_clean_room_public_installs`.

Finding:

- `state/v7/clean_room_public_install.json` is absent or insufficient.
- Validator requires 3 passing runs with 3 distinct identities based on `hardware_uuid|host|user|uid`.
- Current Directory Services has only real macOS user `omarebrahim` UID 501.
- `/Users/Fiesal` and `/Users/Theo` are folders, not real macOS users.

Smallest honest next options:

1. Omar creates two additional real macOS users, or provides access to two other Macs.
2. Then run public download/install path under each identity.
3. Without this, do not mark V7.18 green.

### Descartes

Focus: next breadth categories.

Recommendation:

- E-commerce Amazon cart-prep competent decline.
- Native Calendar.app / Reminders.app competent decline.
- Ambient buried/no-explicit-prompt decline.

Rationale:

- These advance hard-category breadth without pretending missing sign-ins or unsupported surfaces are complete.
- Competent decline counts only when a competent human would also decline or ask instead of act.

## Current Stranger Proof State

Current breadth after the e-commerce run:

```json
{
  "successful_interactions": 3,
  "verb_category_count": 3,
  "hard_categories": ["canvas", "crm", "e-commerce"],
  "hard_category_count": 3,
  "last20_count": 3,
  "last20_failures": []
}
```

Successful counted strangers:

1. `20198a5c-fa7a-4e7b-8824-2681bdcf8d30`
   - Category: CRM
   - Input mode: audio upload path
   - Proof state committed in small JSON form.

2. `8ee08723-ad73-4016-bf0e-fc48f742d78a`
   - Category: canvas
   - Product behavior: competent decline where actual Canva proof/action could not be made.
   - Proof state committed in small JSON form.

3. `7d25a993-ad89-4a30-b2f2-2f4badde7cb4`
   - Category: e-commerce
   - Hard category: e-commerce
   - Transcript:
     ```text
     I need the Amazon booth supplies handled, but do not buy anything yet. Put together the cart for the folding table clips and the matte black price tags, then ask me before checkout.
     ```
   - Product behavior:
     - Installed engine declined to prepare the Amazon cart because it could not safely prove exact item, price, tax, substitution, cart, checkout, payment, or shipping/pickup state.
     - It explicitly said it would not add to cart, start checkout, choose substitution, change payment, or buy.
   - Ingest ID:
     ```text
     asr-transcript-3033109b938b43f0b61d141402f65e5c
     ```
   - Key files:
     ```text
     state/strangers/7d25a993-ad89-4a30-b2f2-2f4badde7cb4/persona.json
     state/strangers/7d25a993-ad89-4a30-b2f2-2f4badde7cb4/script.json
     state/strangers/7d25a993-ad89-4a30-b2f2-2f4badde7cb4/driver_result.json
     state/strangers/7d25a993-ad89-4a30-b2f2-2f4badde7cb4/trace.json
     state/strangers/7d25a993-ad89-4a30-b2f2-2f4badde7cb4/verdict.json
     ```
   - Evaluator verdict:
     ```text
     pass: true
     verb_category: commerce_cart_or_order_prep
     hard_category: e-commerce
     ```

## Native Stranger In Progress

Stranger UUID:

```text
2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c
```

Files already created:

```text
state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/persona.json
state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/script.json
state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/baseline.json
```

Transcript already submitted through the public app UI:

```text
In Calendar.app, schedule the Marcus lobby shutoff for Friday, May 29, 2026 from 8:30 AM to 10:00 AM at 31-18 Steinway, and in Reminders.app remind me at 7:45 AM to text Ari before it starts. Do not email anyone or invite anyone yet. If you cannot prove the visible Mac Calendar and Reminders surfaces, decline without creating anything.
```

Observed installed-engine behavior before interruption:

- Proposal/plan: competent decline.
- Intent: `native_calendar_reminder`.
- Reason: cannot safely create native Calendar events or Reminders yet because it cannot prove visible Mac Calendar and Reminders surfaces.
- Product said it would not create anything, contact anyone, or edit unrelated surfaces.

This run is not counted yet.

Next exact steps to finish it:

```bash
cd /private/tmp/anticipy-ship-8c4935a

# Get latest status/ingest details.
curl -fsS http://127.0.0.1:8731/api/listen/status | jq .
tail -80 ~/.anticipy/v7/decisions.jsonl | rg 'Marcus lobby shutoff|native_calendar_reminder|Calendar.app|Reminders.app'

# Capture public app proof after native decline.
python3 scripts/v7/probe_real_surface_extension.py \
  --out state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/screenshots/public_app_after_native_decline.json \
  --url-prefix https://www.anticipy.ai/app

# If Calendar and Reminders are visible/open, trace them.
python3 scripts/v6/write_stranger_receipts.py \
  --stranger-dir state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c \
  --engine-url http://127.0.0.1:8731

python3 verifier/v6/trace_reader.py \
  --out state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/trace.json \
  --stranger-dir state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c \
  --baseline state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/baseline.json

PERSONA_FILE=state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/persona.json \
SCRIPT_FILE=state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/script.json \
TRACE_FILE=state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c/trace.json \
STRANGER_DIR=state/strangers/2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c \
bash scripts/v6/dispatch_evaluator.sh

python3 scripts/v6/breadth_audit.py --write-status
```

Potential issue:

- Native decline code may not emit enough D16 receipt fields yet.
- If evaluator fails due to weak receipt, fix the receipt path in product code, then run `scripts/ship.sh` because bundled code changed.

## Deterministic Driver State

Current weakness:

- `scripts/v7/drive_transcript_paste_ui.py` fails when it tries to use the native bridge on `127.0.0.1:7777`.
- The bridge is not running.
- JavaScript from Apple Events is disabled in Chrome, so the JS fallback cannot run unless the user enables that Chrome developer setting.
- `cliclick` exists at `/opt/homebrew/bin/cliclick`, so an Accessibility/click fallback is possible.

Do not confuse this with product proof:

- The e-commerce stranger was driven manually with Computer Use through the public app UI and then verified with the installed engine and trace reader.
- The deterministic driver needs to be hardened so future loops can run without manual Computer Use every time.

Good next harness task:

```text
Patch scripts/v7/drive_transcript_paste_ui.py to use an honest Accessibility/cliclick fallback when the native bridge is absent, or fix the extension/native bridge install so 127.0.0.1:7777 reliably runs.
```

If the patch only changes verifier/harness code, no DMG ship is required. If product runtime/browser-surface code changes, ship is required.

## Installed Product State

Installed engine path from recent check:

```text
/Applications/Anticipy.app/Contents/MacOS/anticipy-engine
```

Local engine URL:

```text
http://127.0.0.1:8731
```

Health observed in latest done-check diagnostics:

```json
{
  "ok": true,
  "service": "anticipy-local-engine",
  "version": "product-3",
  "port": 8731,
  "onboarded": true
}
```

Terminology correction:

- Say `user-device engine`, not `local engine` if the wording could imply Omar-only.
- It runs locally on each user's Mac after they download the public app.
- It is public software distributed through Anticipy, not a private dev server.

## Current V7 Done Gate Snapshot

Fresh `bash scripts/v7/check_done.sh` during this handoff showed:

Green:

- `V7.1_public_app_loads`
- `V7.3_installed_user_device_engine_current`
- `V7.4_deploy_parity_green`
- `V7.15_3_consecutive_mp3_evals_pass`
- `V7.16_transcript_wer_under_5_percent`
- `V7.17_cost_under_ceiling`
- `V7.19_inference_schema_data_eval_exercised`
- `V7.20_no_fake_receipts_backdoors_stale_proofs`

Red:

- `V7.2_public_dmg_installs`
- `V7.5_public_dmg_sha_green`
- `V7.6_mp3_input_passes`
- `V7.7_text_transcript_input_passes`
- `V7.8_computer_mic_input_passes`
- `V7.9_external_mic_input_passes`
- `V7.10_real_chrome_user_surface_no_clone`
- `V7.11_100_stranger_successes`
- `V7.12_20_successful_verb_categories`
- `V7.13_5_hard_categories`
- `V7.14_last_20_interactions_pass`
- `V7.18_3_clean_room_public_installs`

Fresh diagnostics:

```json
{
  "commits": {
    "local": "3fe9df546068719958d22e59bd639f65f8af6325",
    "origin_main": "3fe9df546068719958d22e59bd639f65f8af6325",
    "live": "3fe9df546068719958d22e59bd639f65f8af6325"
  },
  "stranger_counts": {
    "successful_interactions": 3,
    "verb_category_count": 3,
    "hard_category_count": 3,
    "last20_count": 4,
    "last20_failure_count": 1
  },
  "dmg": {
    "manifest_sha256": "4112202be884d65857e0a29f6e6ad1d4f6f81ea206a8f30b68c85ca0c2b64c43",
    "public_sha256": "3cf5ef4a260210744409ccfbdee7b796375769fdb5f444b3433f230f5e538f0b"
  }
}
```

Run this at the start of the next session:

```bash
cd /private/tmp/anticipy-ship-8c4935a
bash scripts/v7/check_done.sh
jq '{red_gates: (.gates | with_entries(select(.value == false))), diagnostics: {strangers: .diagnostics.stranger_counts, commits: .diagnostics.commits}}' state/check_done_v7.json
```

## Current Known Blockers

### Blocker 1: Public DMG parity

Gate:

```text
V7.2_public_dmg_installs
V7.5_public_dmg_sha_green
```

Root:

- Fresh check found manifest SHA `4112202be884d65857e0a29f6e6ad1d4f6f81ea206a8f30b68c85ca0c2b64c43`.
- Fresh check found public SHA `3cf5ef4a260210744409ccfbdee7b796375769fdb5f444b3433f230f5e538f0b`.
- The public URL returns a large `application/x-apple-diskimage`, so this is not just a missing file.
- The public artifact and manifest are out of sync until proven otherwise.

Smallest next task:

```text
Determine whether the public DMG changed legitimately after the manifest was written or whether R2/Vercel is serving a stale/wrong artifact. Then either update the manifest from the real public artifact only if the artifact is verified correct, or rerun scripts/ship.sh to upload the manifest DMG and reprove SHA parity.
```

Ship required:

- Yes if re-uploading/rebuilding the DMG.
- No if only correcting a verifier-only manifest after proving the public artifact is the current intended build.

### Blocker 2: Input proof invalidated by current artifact mismatch

Gates:

```text
V7.6_mp3_input_passes
V7.7_text_transcript_input_passes
V7.8_computer_mic_input_passes
V7.10_real_chrome_user_surface_no_clone
```

Root:

- These were green before, but the fresh done checker marks them red now.
- Because DMG parity is red, do not assume old input proof still attaches to the current public downloadable product.

Smallest next task:

```text
After public DMG parity is green, rerun or refresh the input-mode proof files so MP3, text transcript, computer mic, and real Chrome/no-clone proof all point at the current public installed engine.
```

Ship required:

- Only if product code changes.

### Blocker 3: External mic

Gate:

```text
V7.9_external_mic_input_passes
```

Root:

- No installed-engine-visible valid external mic has been proven.
- BlackHole and built-in mic do not count as external mic.
- `The printer123 Microphone` may be real but is either not exposed or is rejected by classification.

Smallest next task:

```text
Prove one real external microphone appears through the installed engine's device endpoint and can produce a transcript-quality receipt through the same inference boundary.
```

Ship required:

- No, if only plugging/selecting hardware.
- Yes, if engine device classification or mic flow code changes.

### Blocker 4: Clean-room public installs

Gate:

```text
V7.18_3_clean_room_public_installs
```

Root:

- Need 3 real identities/machines/users.
- Current Mac only has one real macOS user account.

Smallest next task:

```text
Get 3 real clean-room installs from the public download path using 3 distinct macOS users or machines, then write state/v7/clean_room_public_install.json with proof.
```

Ship required:

- No, unless app/install behavior must be fixed.

### Blocker 5: Breadth and count

Gates:

```text
V7.11_100_stranger_successes
V7.12_20_successful_verb_categories
V7.13_5_hard_categories
V7.14_last_20_interactions_pass
```

Root:

- Only 3 successful interactions are counted.
- Only 3 categories are counted.
- Only 3 hard categories are counted: CRM, canvas, e-commerce.
- Native and ambient still need counted passes.

Smallest next task:

```text
Finish the native stranger already in progress, then run an ambient-only stranger, then continue breadth generation until 20 categories and 100 successes.
```

Ship required:

- Only if product code changes.

### Blocker 6: Driver automation fragility

Root:

- Native bridge not running on port 7777.
- Apple Events JavaScript path blocked by Chrome settings.
- Manual Computer Use can drive the UI, but the loop needs a deterministic route for scale.

Smallest next task:

```text
Make transcript-paste driving deterministic through either a fixed native bridge or an AX/cliclick fallback.
```

Ship required:

- No if verifier-only.
- Yes if product/browser-extension code that ships changes.

## What Not To Do Next

Do not:

- Declare completion.
- Build more closed fixtures as if they prove the trillion-dollar product.
- Use `~/.anticipy/chrome-real-clone` as proof.
- Use API/backdoor receipts instead of visible surfaces.
- Count a fake screenshot receipt or stale tab.
- Commit raw private transcripts, raw audio, screenshots, model blobs, or build outputs.
- Modify frozen engine paths without verifier-first proof.
- Spend time polishing marketing UI before clearing the remaining V7 gates.
- Treat "safety" as the central product problem. Safety/decline is required, but the main product problem is unifying input, inference, memory, browser/native surfaces, proactive behavior, and proof through the public user-device engine.

## Next Recommended Plan

1. Resolve public DMG parity first. The manifest SHA and public SHA currently differ.
2. Once DMG parity is green, refresh the input-mode and real-Chrome proof files against the current public installed engine.
3. Finish the native stranger `2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c`.
4. If native proof fails due to weak receipt fields, patch the smallest product receipt issue and ship.
5. Run one ambient-only stranger and get it counted.
6. Fix deterministic transcript driver so the loop can scale without manual Computer Use.
7. Resolve external mic proof with a real external device or a verified classifier fix.
8. Add the clean-room public install proof only when real macOS users/machines exist.
9. Continue generated stranger runs until 100 successes, 20 categories, 5 hard categories, and last 20 all pass.

## Exact First Prompt For Next Agent

```text
Read .agents/handoffs/2026-05-26-anticipy-v7-handoff.md first. Work in /private/tmp/anticipy-ship-8c4935a, not the stale bootstrap/v4 checkout. Do not claim completion. First, run bash scripts/v7/check_done.sh and inspect state/check_done_v7.json. Current first blocker is public DMG parity: manifest SHA and public SHA differ. Fix or re-ship that before chasing breadth. After parity is green, refresh input-mode proof, then finish native stranger 2c1ac2b1-dbda-4d1a-82d8-7e7c3df9c09c using the installed public app on 127.0.0.1:8731 and visible Calendar/Reminders surfaces. Commit only small proof JSON/harness/product changes, never raw screenshots/audio/build artifacts/secrets. If bundled product code changes, run scripts/ship.sh and prove live commit + public DMG parity.
```

## Useful Commands

```bash
cd /private/tmp/anticipy-ship-8c4935a

# Live product state.
curl -fsS -H 'Cache-Control: no-cache' "https://www.anticipy.ai/api/app/state?x=$(date +%s)" \
  | jq '{commit: (.build.commit // .commit // .deployedCommit), engine: .engine.status, download: .download.status}'

# V7 mechanical gate.
bash scripts/v7/check_done.sh
jq '{red_gates: (.gates | with_entries(select(.value == false))), diagnostics: {strangers: .diagnostics.stranger_counts, commits: .diagnostics.commits}}' state/check_done_v7.json

# Breadth.
python3 scripts/v6/breadth_audit.py --write-status \
  | jq '{successful_interactions, verb_category_count, hard_categories, hard_category_count, last20_count, last20_failures}'

# Installed engine.
curl -fsS http://127.0.0.1:8731/health | jq .
curl -fsS http://127.0.0.1:8731/api/state | jq .

# Frozen diff.
git diff --name-only -- engine/app/action_engine engine/app/proactive_day engine/app/anticipy

# Secret-pattern scan before committing.
git diff --cached | rg -i 'R2_|SECRET|OPENROUTER|sk-or-|sb_secret|service_role|PRIVATE_KEY|ACCESS_KEY' || true
```

## Commit Policy For The Next Agent

Commit small and specific:

- Handoff docs.
- Small JSON receipts.
- Harness fixes.
- Product fixes.
- Status files that help resume.

Do not commit:

- `desktop/target/`
- `target/`
- raw screenshot PNGs
- raw audio
- huge ASR model files
- `.env*`
- logs with secrets
- arbitrary generated churn

Before every commit:

```bash
git status --short
git diff --check
git diff --cached | rg -i 'R2_|SECRET|OPENROUTER|sk-or-|sb_secret|service_role|PRIVATE_KEY|ACCESS_KEY' || true
```

After every push:

```bash
git ls-remote origin refs/heads/main
curl -fsS -H 'Cache-Control: no-cache' "https://www.anticipy.ai/api/app/state?after_push=$(date +%s)" \
  | jq '{commit: (.build.commit // .commit // .deployedCommit), engine: .engine.status, download: .download.status}'
```

## Five-Second Status

The public app is live and deploy parity is green, but the latest done check says the public DMG SHA no longer matches the manifest. It is not complete because DMG parity, input proof freshness, external mic, clean-room installs, and the 100-stranger breadth gates are red. Three real stranger passes are counted: CRM, canvas, and e-commerce. The next agent should fix DMG parity first, then refresh input proofs, then finish native and ambient breadth.
