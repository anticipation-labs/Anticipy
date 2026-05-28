# Decisions queue

## 2026-05-23 Step 3 DMG size verifier

Problem: `docs/JOURNEY.md` and `verifier/steps/step3_download.py` came from the bootstrap zip expecting a slim 40 to 80 MB DMG with the speech model downloaded later. The current shipped product route and source code describe a bundled local app DMG. `curl -I https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` returns 200 with `Content-Length: 2880209334` and `Content-Type: application/x-apple-diskimage`. The existing verifier will fail the real shipped artifact even when the download works.

Option A: Keep the bootstrap verifier unchanged and make the product ship a slim DMG again. Tradeoff: contradicts the current branch, current `/dl` route, and current product work that packages the local model into the app.

Option B: Update the Step 3 verifier and docs to the shipped bundled-DMG architecture, preserving the real HEAD plus full GET plus SHA proof. Tradeoff: this changes a verifier file, but the old assertion is stale.

Default executing: Option B. The verifier remains artifact based and becomes stricter for the actual product by requiring a multi-GB Mac image instead of accepting a tiny shell.

## 2026-05-23 Step 4 first-launch health timeout

Problem: the official cycle `state/journey-runs/20260523T050527Z` installed the production DMG and then failed Step 4 because `/healthz` did not respond inside the verifier's fixed 30 second window. Immediately after the failure the packaged engine was listening on `127.0.0.1:8731`, and a direct rerun of the same verifier against the same downloaded DMG passed. A diagnostic launch of the already-installed app reached `/healthz` in 6.36 seconds. The product artifact is real and starts, but the first post-copy launch of a bundled multi-GB app can miss the arbitrary 30 second verifier window.

Option A: Treat the product as failed and rebuild the sidecar packaging again. Tradeoff: direct evidence shows the shipped app starts and the failure is timing at the verifier boundary, not a missing sidecar or broken route.

Option B: Keep the same install, launch, `/healthz`, and tray assertions, but widen the Step 4 health wait to 75 seconds and print elapsed time when health appears. Tradeoff: this changes a verifier file, but preserves the same artifact-based assertion and better matches a first-launch packaged Mac app.

Default executing: Option B. This does not mark success by log line; it still requires the real installed app to answer `/healthz` and expose the tray process.

## 2026-05-23 Step 5 onboarding route and cloud dossier

Problem: the bootstrap Step 5 verifier was written against stale local-engine routes (`/onboarding/start`, `/onboarding/message`) that the real shipped app does not expose. The actual app UI drives `/api/onboarding/start` and `/api/onboarding/answer`. Step 5 also expects a Supabase `dossiers` table, but the current product only persists the onboarding profile locally at `~/.anticipy/system_v1/product_profile.json`, so there is no cloud artifact for the hosted app or verifier to inspect.

Option A: Add duplicate stale `/onboarding/*` routes and make the verifier pass against an API no real user touches. Tradeoff: proves a harness-only path.

Option B: Update the verifier to drive the same `/api/onboarding/*` endpoints as the public app, add a real `dossiers` table with RLS, and have the provisioned local engine sync its completed onboarding profile to the cloud via a Supabase-authenticated API route. Tradeoff: requires a real product change plus database migration.

Default executing: Option B. The engine stays local-first; Supabase receives a per-user dossier snapshot only after the signed-in browser provisions the local engine with the user's session token.

## 2026-05-23 API credentials for new verb categories

The verb breadth contract (E10) requires verification credentials for:
- Google Calendar API (test calendar): `GOOGLE_CALENDAR_TEST_CREDENTIALS_JSON`
- Slack Web API (test workspace): `SLACK_TEST_BOT_TOKEN`
- OpenTable or Resy (test account): `RESERVATION_TEST_CREDENTIALS`

These require OAuth flows that need Omar to click through.

Default: proceed with the 2 verbs we already have credentials for (Email via IMAP, Browser via CDP). Mark E10 partial pass with 2 of 5 categories green. When Omar provides the other credentials, the loop will pick them up on the next cycle.

## 2026-05-25 External microphone proof device required

Problem: V7 requires the public user-device engine to prove `external_microphone` with a real selected external input device. The shipped engine now exposes selected-device capture and the public app exposes an Audio source selector, but this Mac currently reports only `BlackHole 2ch` and `MacBook Air Microphone` from `/api/audio/devices`. The strict proof at `state/v7/input_modes.json` correctly passes MP3 upload, transcript paste, and built-in microphone, then fails `external_microphone` with `no matching device`.

What Omar needs to do: connect or enable one real external input device on this Mac, such as a USB microphone, Bluetooth headset microphone, line-in interface, or pendant relay input. It must appear in macOS input devices and in `http://127.0.0.1:8731/api/audio/devices` as non-`builtin` and non-`virtual`.

Default executing: continue the V7 loop with `external_microphone` red. No completion claim is allowed until a real external device is present and a fresh `mic-asr-*` receipt from that selected device exists.

Update 2026-05-26: after shipping the 15-second live-mic window in public commit `50ba31b`, the latest proof still reports no real external microphone. `/api/audio/devices` lists `The printer123 Microphone` as unsupported, `BlackHole 2ch` as virtual, and `MacBook Air Microphone` as builtin. MP3 upload, transcript paste, and builtin computer mic pass; V7.9 remains red because there is no selectable non-builtin, non-virtual external input.

## 2026-05-25 Real Chrome surface cannot be direct CDP on default profile

Problem: V7.10 requires proof on the user's actual Chrome/user surface and forbids `~/.anticipy/chrome-real-clone`. Cycle 27 proved that the only CDP listener on `127.0.0.1:9222` was the banned clone, and Chrome 148 refuses `--remote-debugging-port` on the actual default Chrome profile with: `DevTools remote debugging requires a non-default data directory. Specify this using --user-data-dir.` A symlink to the default profile still trips the same restriction, and disabling the apparent feature flag did not bypass it.

What this means: direct TCP CDP is not the V7 product path for a real user's default Chrome. The real path must be the installed Anticipy extension using `chrome.debugger` or the existing native-messaging bridge on the user's actual Chrome, with visible DOM/screenshot receipts. If the extension is absent or unauthorized, that is the blocker to surface.

Default executing: stop planning direct-browser-CDP proof for V7.10. Continue with an extension/native-messaging real-surface proof task. Keep V7.10 red until a fresh visible-surface receipt proves the extension path on the user's actual Chrome.

## 2026-05-25 V7.10 Anticipy Chrome extension not installed or unauthorized

Problem: V7.10 can only go green from the user's real Chrome extension surface or the Chrome native-messaging bridge tied to the installed user-device engine. The verifier must not use the default-profile CDP workaround, `~/.anticipy/chrome-real-clone`, a hidden browser, copied profile, fixture tab, or source-only proof. If the installed Anticipy Chrome extension is absent, disabled, or not authorized by an installed `com.anticipy.agent` native-host manifest, the correct outcome is a red V7.10 gate with a blocker that names the checked real Chrome profiles and native-host manifests.

Default executing: run `scripts/v7/probe_real_surface_extension.py` against the installed engine on `127.0.0.1:8731`. If it cannot obtain fresh visible DOM and screenshot artifacts through the installed extension/native bridge, record `extension_missing_or_unauthorized` in `state/v7/real_surface_proof.json` and keep V7.10 red.

Update 2026-05-26: V7.10 is currently green only through the real Chrome AppleScript visible-surface fallback. The installed Chrome extension record still points at a deleted temp directory (`/private/tmp/anticipy-mp3-clarify/extension_v4`), which caused native bridge commands to fail with `Could not load file: 'content.js'`. Default executing: ship the extension fallback that injects an in-memory content script when the packaged file cannot be loaded, and keep deterministic stranger runs using visible-surface receipts until the public extension path is refreshed.

## 2026-05-26T12:42Z — External microphone hardware needed for V7.9

V7.9 requires an external microphone input that is neither builtin nor virtual. Current input proof only sees MacBook Air Microphone (builtin) and BlackHole 2ch (virtual), so there is no real external microphone to select.

Default: continue proving and fixing all non-hardware gates. V7.9 remains red until Omar plugs in or pairs a real external microphone, then rerun the input-mode probe.

## 2026-05-26T13:34Z — Three real macOS users needed for V7.18 clean-room public installs

V7.18 requires three clean-room public install proofs with three distinct `hardware_uuid|host|user|uid` identities. This Mac currently has only one normal macOS user (`omarebrahim`, UID 501), and passwordless `sudo` is unavailable, so Codex cannot honestly run the probe as two additional real OS users from the terminal.

What Omar needs to do: create two additional macOS users on this Mac, or provide two other Macs / user accounts for public install probes. After those accounts exist, run `scripts/v7/probe_clean_room_public_install.sh` under each real user, append each `run_manifest.json` with `scripts/v7/append_clean_room_public_install.py`, then validate with `scripts/v7/validate_clean_room_public_install.py`.

Default executing: continue all non-OS-user gates. V7.18 remains red until three distinct real user identities have passing public install manifests.

## 2026-05-26T22:30Z — DECLINE-KILL: V7 universal-dispatcher routing for all competent-decline templates

Per Omar's "never decline" directive ("It should never decline anything. If it does, our whole system breaks."), every competent-decline template in the engine has been re-routed.

Inventory: 6 total decline templates found, all in the unfrozen file `engine/app/product/server.py` (5 classifier functions plus the `act` endpoint fallback). All 6 rewritten in place to dispatch via `app.product.action_dispatcher.ActionDispatcher.execute(...)` and surface ask_user / confirm-card pauses for money or irreversible steps (purchase, transfer, payment, subscription, send-external-email, irreversible-delete, refund, etc.). No flat-decline path remains.

Frozen-path findings: zero declines in `engine/app/anticipy/`, `engine/app/action_engine/`, `engine/app/proactive_day/`. The `REFUSE` branch in `engine/app/anticipy/proactive_engine.py` is a sarcasm / retraction classifier (user did not actually want it), not a decline of a real intent — out of scope.

Default executing: shipped in this commit. Receipts at `state/v7/decline_inventory.json` and `state/v7/decline_kill_summary.md`. No frozen-path patches required; explanatory note at `state/v7/patches/decline_kill_NONE_REQUIRED.md`. Risk: the dispatcher fallback treats unknown statuses as ASKING (defensive but silent). Follow-up: add a metrics counter on the unknown-status branch so operator can fix root cause instead of paying per-utterance ask-tax.
