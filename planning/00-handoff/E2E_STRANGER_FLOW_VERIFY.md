# Stranger Flow End to End Verify

Time of verify: 2026-05-30T06:03Z (Pacific 2026-05-29T23:03 local).
Working tree: `/Users/omarebrahim/Developer/Anticipy-V7` at HEAD `d6354f25b88821f1c2f012dacfb67deeab464551`.
Live engine pid: 94353 on `127.0.0.1:8731` (not touched).

## Method

Each row is one verify step from the request. "Actual" lists the observed value or HTTP response, with the exact command used. "Verdict" is one of PASS, FAIL, SKIP, PARTIAL.

## Web flow

| Step | Expected | Actual | Verdict |
|------|----------|--------|---------|
| 1. GET https://www.anticipy.ai/ returns 200 and body mentions Anticipy plus a download path | HTTP 200, body has Anticipy and a download CTA or path | HTTP 200, 56992 bytes. Body has "Anticipy" branding throughout and an "Anticipy App" header link to /app. No literal word "download" on the marketing page, the CTA flows through /app then /app/download. | PARTIAL |
| 2. GET https://www.anticipy.ai/app returns 200 with download button + Supabase signin | HTTP 200, signin form + path to download | HTTP 200, 17513 bytes. Body has email + password inputs, "Get Anticipy" submit, and a note "Real Supabase". This is the create-account page that flows to /app/download after signup. | PASS |
| 3. /app/download follows to actual DMG URL, content-length matches R2 file | 302 to DMG, content-length matches R2 | /app/download is a client-rendered HTML page (15838 bytes), not a redirect. The download button on that page points to /dl/Anticipy_1.0.0_aarch64.dmg, which is a route that 302s to https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/Anticipy_1.0.0_aarch64.dmg. R2 HEAD: content-length 2516059621. Vercel HEAD: content-length 2515666283. The Vercel HEAD constant is stale by 393338 bytes; the actual GET to R2 is correct and matches the locally built DMG. | PARTIAL |
| 4. GET https://www.anticipy.ai/install.sh returns the canonical install script | byte identical to repo public/install.sh | HTTP 200. `cmp` against `/Users/omarebrahim/Developer/Anticipy-V7/public/install.sh` = byte identical, 9630 bytes. | PASS |
| 5. GET https://www.anticipy.ai/onboarding/audio returns 200 | HTTP 200 | HTTP 200. | PASS |
| 6. GET https://www.anticipy.ai/onboarding/chat returns 200 | HTTP 200 | HTTP 200. | PASS |
| 7. GET https://www.anticipy.ai/onboarding/call returns 200 | HTTP 200 | HTTP 200. | PASS |

## API gates

| Step | Expected | Actual | Verdict |
|------|----------|--------|---------|
| 8. POST /api/twilio/relay no auth returns 401 | 401 | HTTP 401, body `{"ok":false,"error":"Unauthorized"}`. | PASS |
| 9. POST /api/twilio/relay with FAKE bearer token returns 401 | 401 | HTTP 401, body `{"ok":false,"error":"Unauthorized"}`. | PASS |
| 10. POST /api/twilio/status no body returns 400 or 503 | 400 or 503 | HTTP 503, body `Twilio broker is not configured.`. | PASS |
| 11. POST /api/engine/model without Supabase returns 401 | 401 | HTTP 401, body `{"error":"Unauthorized"}`. | PASS |

## Stranger install simulation

| Step | Expected | Actual | Verdict |
|------|----------|--------|---------|
| 12. install.sh downloaded fresh from anticipy.ai matches `public/install.sh` byte for byte | identical | Downloaded to /tmp/install_test_1780120998.sh. `cmp` against repo install.sh = byte identical, 9630 bytes. | PASS |
| 13. install.sh references Python 3.9 floor (cycle 129 fix) | mentions 3.9 floor | Lines 115-128 of install.sh: detects `python3`, parses `PYV`, comments "Stock macOS ships /usr/bin/python3 as 3.9... 3.9 is the right floor for zero-friction", error message says "Python 3.9+ is required". Floor enforced. | PASS |
| 14. install.sh references the correct DMG URL | `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` | Line 11: `URL="https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg"`. | PASS |
| 15. Stranger install does NOT clobber Omar's running install | engine pid 94353 untouched | No `hdiutil attach` to /Applications, no install.sh execution, no killing of pid 94353. `ps -p 94353` confirms still running, etime 16:21, command `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine`. | PASS |

## DMG validation

| Step | Expected | Actual | Verdict |
|------|----------|--------|---------|
| 16. HEAD DMG URL on R2 returns content-length matching local | R2 content-length matches local DMG | R2 (`pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/Anticipy_1.0.0_aarch64.dmg`) content-length 2516059621. Local DMG at `desktop/target/.../Anticipy_1.0.0_aarch64.dmg` is 2516059621. Match. | PASS |
| 17. Mount DMG read only to /tmp/dmg-verify without clobbering Omar's install | mount succeeds, no clobber | `hdiutil attach -nobrowse -mountpoint /tmp/dmg-verify -readonly`. Mounted disk5s1. Omar's /Applications/Anticipy.app untouched. Unmounted cleanly after inspection. | PASS |
| 18. .app inside DMG has the CORRECT sidecar SHA | SHA matches release build | DMG sidecar SHA: `5f4c2253615c722a64b00b973ffcc0a80ad61b24228ea7c11291b7d49ba62a6b`. Equal to release sidecar at `desktop/src-tauri/target/aarch64-apple-darwin/release/anticipy-engine`, to the .app inside the DMG-build directory, and to the installed `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` that Omar's pid 94353 is running. (The older `engine/dist/anticipy-engine` artifact is `5cbac1ee...`, different, but it is not in the DMG.) | PASS |
| 19. parakeet weights bundled at Resources/parakeet-tdt-0.6b-v3/ | dir exists with weights | Yes: `/tmp/dmg-verify/Anticipy.app/Contents/Resources/parakeet-tdt-0.6b-v3/` contains `config.json`, `model.safetensors`, `tokenizer.model`, `tokenizer.vocab`, `vocab.txt`. | PASS |

## Engine endpoints (against live engine on 127.0.0.1:8731)

| Step | Expected | Actual | Verdict |
|------|----------|--------|---------|
| 20. /api/state has all 6 new keys | quiet_mode, proactive_status, tab_activity_60s, task_queue_summary, cost_last_hour, engine_health | All 6 keys present. quiet_mode=true. engine_health.pid=94353, etime_seconds=881, rss_mb=46, bound_port=8731, bundled_binary=true. | PASS |
| 21. /api/trivia/recent returns 200 not 404 | HTTP 200 | HTTP 200. | PASS |
| 22. /api/recovery/test login_required returns 96-char SMS | sms_body length 96 | HTTP 200, body has `"sms_body_len":96`, sms_body = "Anticipy couldn't finish the task because the site is logged out. I will retry once you sign in." | PASS |
| 23. /api/task_queue/list returns valid JSON | valid JSON | HTTP 200, body `{"ok":true,"count":0,"tasks":[]}`. | PASS |
| 24. /api/cost/stats returns valid JSON | valid JSON | HTTP 200, body has `per_task_ceiling_usd:0.002`, `per_task_hard_cap_usd:0.005`, and percentile metrics. Window empty (no tasks yet). | PASS |

## Sentinel and watchdog

| Step | Expected | Actual | Verdict |
|------|----------|--------|---------|
| 25. sentinel runner alive (`pgrep anticipy_loop_sentinel_runner`) | pid present | `pgrep -fl anticipy_loop_sentinel_runner` returns NOTHING. No matching process. | FAIL |
| 26. SENTINEL_LATEST.json exists + last_check_ts within last 5 min | file fresh < 300s | File exists at `state/orchestrator/SENTINEL_LATEST.json`. last_check_ts = 2026-05-30T05:42:35Z. Now = 2026-05-30T06:03Z. Age = 1270s, ~21 minutes. NOT within 5 min. The cached verdict is "RED" but it is testing a stale engine pid (92216) and reports stranger-engine 404s for trivia/recovery/cost that are actually live and returning 200 against pid 94353. So the sentinel snapshot is wrong about the current engine state. | FAIL |
| 27. watchdog loaded (`launchctl list` shows com.anticipy.engine-watchdog) | present | `launchctl list` shows `92924  0  com.anticipy.engine-watchdog`. `launchctl print` confirms state=running, program=/bin/bash, script `desktop/scripts/engine_watchdog.sh`. | PASS |

## Counts

PASS: 22
PARTIAL: 2
FAIL: 2
SKIP: 0

## Honest gaps for a real stranger today

1. The sentinel runner is dead. Last successful tick was at 05:42Z, currently 06:03Z, so cached verdict is RED against a dead pid (92216) while the live engine on pid 94353 actually answers 200 on the same endpoints. A real stranger does not depend on the sentinel, but Omar's gate-monitoring loop is currently blind.

2. The `/dl/Anticipy_1.0.0_aarch64.dmg` HEAD on Vercel returns a hard-coded `DMG_BYTES = 2515666283` while R2 actually serves 2516059621 (a newer DMG by 393338 bytes). The user gets the right bytes (GET 302s to R2), but anything that pre-checks Content-Length via HEAD against `www.anticipy.ai/dl/...` will mismatch the actual download. Update `DMG_BYTES` in `src/app/dl/Anticipy_1.0.0_aarch64.dmg/route.ts` to 2516059621.

3. The landing page at https://www.anticipy.ai/ has no literal "Download" word above the fold; the only call to action toward the Mac app is the "Anticipy App" link in the top nav and a "Pre-order" CTA in the hero. A real stranger who lands on / and wants the Mac app has to know to click the small nav link. Consider adding a visible "Download for Mac" CTA on /.

4. Onboarding pages (audio, chat, call) return 200 but were NOT functionally exercised in this audit. We did not sign in, did not record a sample, did not simulate the chat handoff, did not initiate a call. They render, that is all this verify proves.

5. install.sh runs `pip install` of `httpx`, `cryptography`, `supabase`, `python-dotenv` into a venv under `~/.anticipy/venv` after install. A real stranger on a stock macOS Sonoma machine with no pre-existing pip cache and a fresh `/usr/bin/python3` will hit network for those wheels. If PyPI is slow or the SSL cert path is misconfigured (we saw `SSL_CERT_FILE` in the watchdog env), the install can stall. Not verified end to end on a stranger's machine.

## Notes on guarded behaviors that were honored

- No real Twilio sends triggered. Only 401 and 503 responses observed on /api/twilio/relay and /api/twilio/status.
- No modification of /Applications/Anticipy.app. Mount target was /tmp/dmg-verify, ejected after inspection.
- No kill or restart of pid 94353.
- No execution of install.sh; only fetched and byte-compared.
- install.sh confirmed to reference `python3` only (no `pip` outside the venv it creates).
