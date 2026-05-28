# Anticipy PRD

Source of truth for what "done" means. Every requirement testable. The `/goal` runner points at this document. The acceptance harness at `engine/tests/anticipy_acceptance.py` enforces it.

Last revised: 2026-05-20.

---

## 1. Product

Anticipy is a local-first Mac app that listens ambiently and acts proactively in the user's logged-in Gmail and Calendar. The Vercel site at `anticipy.ai` is the public surface: marketing page, download host, broker for model calls, pairing flow for the pendant. The engine runs on the user's machine.

Privacy moat (non-negotiable):
- User audio never leaves the device. ASR runs locally via `parakeet-mlx`.
- User Google session never leaves the device. Gmail and Calendar are driven through Chrome CDP against the user's own logged-in Chrome.
- Model calls are routed through the broker at `https://www.anticipy.ai/api/engine/model`. The broker forwards text and screenshots only when the local engine asks. No raw audio is ever sent.

Scale strategy: distribution, not centralization. Each user runs the engine on their own Mac. The site scales as a download host plus thin broker, never as a hosted engine.

---

## 2. User flow (Apple-polish target)

1. User lands at `anticipy.ai`. Background charcoal `#0C0C0C`, cream `#F5F0EB` text, DM Serif Display headers. Headline reads `Vibe your life.` One button: `Get Anticipy.`
2. Click `Get Anticipy`. The DMG downloads from `https://www.anticipy.ai/download`. User drags the app into `/Applications`. Opens it.
3. Welcome screen: `Hi. Let's get to know each other.` One button: `Start.`
4. Three cards on one screen for onboarding source.
   1. `Talk to me`. User enters a phone number. A call stub fires: writes a STUB-LABELED intent record to `~/.anticipy/system_v1/voice_call_stubs.jsonl` and returns success.
   2. `Chat with me`. Real conversation with the broker LLM, 15 to 25 exchanges, adaptive follow-ups. Populates a profile.
   3. `Show me your life`. User drags in an MP3 up to 24 hours. `parakeet_mlx` transcribes with `chunk_duration=120`, `overlap_duration=15`. The LLM extracts a profile from the transcript.
5. User reviews the extracted profile inline. Every field is editable. User confirms.
6. OAuth. User clicks `Connect Google`. Standard Google OAuth completes in their own Chrome. The local engine never holds OAuth tokens; it drives Chrome CDP against the live logged-in session.
7. Main screen: dark charcoal background. One centered pulsing circle. One word below the circle indicating state: `Listening`, `Thinking`, `Acting`, `Resting`. Top-right avatar menu: `Pause`, `Settings`, `Memory`, `Pendant`, `Sign out`.
8. Settings page. Audio source dropdown lists, in this order: Mac built-in microphone, every system-paired Bluetooth audio input device enumerated via CoreAudio, `Upload audio` (file picker), `Anticipy Pendant` (greyed out until paired).
9. Memory page. Lists three groups: people, topics, do-not-touch items. Every field editable inline. Button at bottom: `Forget everything`.
10. Pendant page. Button `Connect Pendant` launches `https://www.anticipy.ai/flash` in the user's default browser. That page uses `navigator.bluetooth.requestDevice()` to discover the nRF5340 pendant and flashes firmware via the `web-bluetooth-dfu` library. On success the page registers the pendant with the Mac app via the broker. After pairing, Settings -> Audio source shows `Anticipy Pendant (connected)` as a selectable option. The Mac app uses CoreBluetooth (not Web Bluetooth) for the ongoing audio stream.
11. Indirect speech: when the user says `I need to send the Friday update to her`, the circle pulses, transitions to `Thinking`, then a subtle notification appears: `Draft for Dana ready.` Click opens Gmail with the draft pre-filled. Anticipy never sends, only drafts.
12. Ambiguity: when `her` could match two people in the profile, the notification reads `Did you mean Dana or Priya?` with two buttons. No Gmail state changes until the user picks.

---

## 3. Architecture (frozen)

- Local Mac engine: FastAPI on `127.0.0.1:8731`, PyInstaller-packaged inside `Anticipy.app`.
- Public Vercel site at `anticipy.ai` (Next.js 14 App Router): marketing, `/app` (main user surface), `/flash` (pendant pairing), `/api/engine/model` (broker), `/download` (DMG host), `/install.sh` (terminal-only installer).
- Supabase for auth.
- OpenRouter via the broker for all model calls. Text: DeepSeek V4 Flash. Vision: Kimi K2.6.
- Chrome CDP on port `9222` driving the user's own logged-in Chrome for Gmail and Calendar actions.
- `parakeet-mlx` for local ASR inside the packaged app. PATH self-repair locates `ffmpeg` at `/opt/homebrew/bin`, `/usr/local/bin`, or `/usr/bin` so ASR works under stripped env.
- All four input modes (Mac mic, Bluetooth mic via CoreAudio, MP3 upload, Pendant via CoreBluetooth) feed the same post-ASR boundary at `_process_utterance` inside `engine/app/product/server.py`.

---

## 4. Brand

- Background: charcoal `#0C0C0C`.
- Primary text: cream `#F5F0EB`.
- Secondary text: warm gray `#6B635B`.
- Headers: DM Serif Display.
- Body: system font (San Francisco on macOS, system-ui fallback).
- Forbidden visual elements: glassmorphism, purple gradients, emoji clutter.
- Forbidden visible text: technical jargon ("port numbers", raw JSON, status codes, "key_ok"), error stack traces, model names, vendor names.
- Loading states use short human phrases ("Listening to your week", not "Transcribing 71%").
- Error states use one-line human language ("I lost the thread for a moment. Try again."), never a raw stack trace or HTTP code.

---

## 5. Frozen code paths

Must not be modified by any goal pointing at this PRD:

- `engine/app/action_engine/*` (the broker-consumer changes from commit `71eb4b8` are baseline, not new diff).
- `engine/app/proactive_day/*`
- `engine/app/anticipy/*`
- `engine/tests/audiostack/gate_astack_p4.py` (preexisting dirty file, never commit, never revert).

Verification: `git diff --name-only -- engine/app/action_engine engine/app/proactive_day engine/app/anticipy` returns empty.

---

## 6. Stubs that must exist

These stubs allow the product to be exercised end-to-end without burning real external integrations.

1. Phone call stub.
   - Path: `~/.anticipy/system_v1/voice_call_stubs.jsonl`.
   - Trigger: every `Talk to me` submission and every later `Call me` click.
   - Record shape: one JSON object per line with `stub: true`, ISO timestamp, intended phone number, intended payload, source endpoint. The label `"stub": true` must be present so it cannot be confused with real call telemetry.
2. Pendant firmware stub.
   - Placeholder firmware lives at `public/firmware/anticipy-latest.zip`.
   - Every flash attempt writes a STUB-LABELED record (`"stub": true`, ISO timestamp, device id if known, intended firmware checksum, source) to `~/.anticipy/system_v1/flash_stubs.jsonl`.

---

## 7. Verification harness

The harness lives at `engine/tests/anticipy_acceptance.py`. It runs all checks in order, prints a per-check `PASS` or `FAIL` line with the artifact path, and prints a summary table at the end: total checks, count PASS, count FAIL. Each check writes its proof to `proof-artifacts/acceptance_<timestamp>/CHECK_NN.json` with fields `status`, `artifact_path`, and `key_contents`.

Definition of acceptance: 18 / 18 PASS. Any FAIL fails the goal.

### CHECK 1: site_live

`curl https://www.anticipy.ai/api/app/state` returns HTTP 200 with JSON where `engine.status != "gated"` and `mic != "needs_user"`. Print the full response.

### CHECK 2: dmg_downloadable

`curl -I https://www.anticipy.ai/download` returns HTTP 200. `Content-Type` header contains either `x-apple-diskimage` or `octet-stream`. Print the response headers.

### CHECK 3: install_path_terminal_only

`curl https://www.anticipy.ai/install.sh` body does NOT contain the substring `open "/Applications/Anticipy.app"`. (Installer must finish in the terminal and not auto-open the GUI.) Print the last 20 lines of the script.

### CHECK 4: app_runs

Launch `/Applications/Anticipy.app/Contents/MacOS/Anticipy --server --port 8731` with the canonical env from the handoff. Within 30 seconds, `GET http://127.0.0.1:8731/health` responds 200 and `GET http://127.0.0.1:8731/api/state` returns JSON with `key_ok: true`. Print the JSON.

### CHECK 5: onboarding_chat

`POST /api/onboarding/chat` with 5 user turns covering at least two named people (with email addresses) and at least one do-not-touch item produces a profile containing both. PASS if `profile.people` has 2+ entries each carrying an email-like value AND `profile.do_not_touch` (or equivalent field) is non-empty. Print the path to the saved profile JSON.

### CHECK 6: onboarding_audio

Generate a 30+ minute MP3 if one does not already exist (use `say` with multiple voices to produce dialog mentioning at least two named people with email addresses, then concatenate to length). `POST /api/onboarding/from_audio` with that MP3 returns a profile with 2+ people. Print the transcript word count and the profile JSON path.

### CHECK 7: onboarding_call_stub

`POST /api/onboarding/call_stub` with a phone number writes a record to `~/.anticipy/system_v1/voice_call_stubs.jsonl` whose JSON has `"stub": true` and the supplied phone number. Print the new line.

### CHECK 8: input_paste

With an established profile loaded, `POST /api/listen/inject` with an indirect utterance (the utterance must reference a profile person by pronoun, not name) produces a pending plan. `POST /api/act` then drives Chrome CDP and creates a real Gmail draft. Take a Playwright screenshot of the Gmail compose tab via CDP on port 9222 and save it as `gmail_draft_paste_success.png`. Print the screenshot path.

### CHECK 9: input_mp3

`POST /api/listen/upload` with `mp3_priya_strategy.mp3` (existing artifact) produces a non-empty transcript that resolves to Priya Shah. `POST /api/act` creates a real Gmail draft. Take a CDP screenshot and save as `gmail_draft_mp3_success.png`. Print the path.

### CHECK 10: input_mic

Generate audio with `say`, play it through the Mac speaker with `afplay`, listener captures it via the built-in microphone, transcript resolves to a profile person, `POST /api/act` creates a real Gmail draft. Save the screenshot as `gmail_draft_mic_success.png`. This is acoustic (speaker-to-mic), not virtual loopback; the artifact record must explicitly say so. Print the path.

### CHECK 11: input_bluetooth_audio_devices_enumerated

Call the existing CoreAudio device enumeration in `engine/app/audiostack/` and return a list of all input devices. PASS if the list includes the built-in microphone and is returned as a structured array (not raw text). Print the array.

### CHECK 12: ambiguity_trap

With two profile people who both plausibly match an indirect referent, `POST /api/listen/inject` with that referent produces a clarification response that names BOTH contenders by name. PASS if and only if: (a) clarification text contains both names, (b) Gmail draft count via CDP is identical before and after the inject. Print the question text and the before / after counts.

### CHECK 13: flash_page_live

`curl https://www.anticipy.ai/flash` returns HTTP 200. The HTML body contains the literal string `Connect Pendant`, references `navigator.bluetooth`, and references `web-bluetooth-dfu` (by package name or CDN URL). Print the `<head>` block plus the body section that hosts the button.

### CHECK 14: flash_stub_log

`POST /api/pendant/flash_stub` (or equivalent local route) writes a record to `~/.anticipy/system_v1/flash_stubs.jsonl` with `"stub": true`. Print the new line.

### CHECK 15: brand_audit

Playwright opens, in turn: `/`, `/app`, `/flash`, `/onboarding/chat`, `/onboarding/audio`. For each:
- Computed `body { background-color }` equals `rgb(12, 12, 12)`.
- Computed primary text color equals `rgb(245, 240, 235)`.
- No heading (`h1`..`h6`) text node contains an emoji codepoint.
- No visible text node anywhere on the page contains the literal `key_ok`, the literal `8731`, or the literal `127.0.0.1`.
- Save a screenshot per page.

PASS per page if all five conditions hold. Overall PASS if all five pages pass. Print PASS/FAIL per page plus all screenshot paths.

### CHECK 16: agent_reliability

`engine/tests/agent_reliability.py` runs 30 scenarios: 20 resolvable (utterance unambiguously maps to one profile person and one intent), 10 ambiguous (utterance maps to two or more candidate people or candidate intents). Prints a scoring table.

PASS if 19 or more of 20 resolvable scenarios end with the correct Gmail or Calendar draft, AND 10 of 10 ambiguous scenarios end in clarification (asks, never silently acts).

### CHECK 17: frozen_paths_clean

`git diff --name-only -- engine/app/action_engine engine/app/proactive_day engine/app/anticipy` returns empty. Print the diff output (which should be empty).

### CHECK 18: cleanup_passes

After all 17 prior checks complete:
1. Remove `/tmp/anticipy-*` directories.
2. Back up then remove `~/.anticipy/system_v1/product_profile.json` to `/tmp/anticipy_backup_<timestamp>/product_profile.json`.
3. Print the `rm` commands and an `ls` of `~/.anticipy/system_v1/` proving the profile is gone.
4. Fresh-launch `/Applications/Anticipy.app --server --port 8731`.
5. `GET /api/state` returns `onboarded: false` (proves first-run state is fully restored).

PASS if step 5 holds.

---

## 8. Out of scope for v-final-prototype

- Sending email or sending calendar invites (drafts only).
- Code signing or notarization of the DMG. The DMG ships unsigned per `feedback_phase8_unsigned_dmg`.
- Any cloud-hosted engine (no Browserbase, Steel, Cloud Run, Fly.io).
- Any server-side ASR (no Groq Whisper, no Deepgram).
- Service APIs for Gmail / Calendar / Slack / Notion. Browser navigation only.

---

## 9. Definition of done

All 18 checks PASS in a single uninterrupted run of `engine/tests/anticipy_acceptance.py`. The summary line reads `18 PASS / 0 FAIL`. The artifact directory `proof-artifacts/acceptance_<timestamp>/` contains one JSON per check plus the screenshots referenced above.
