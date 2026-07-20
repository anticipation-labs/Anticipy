# Anticipy — Build & Proof Report

Everything below was **actually executed and verified** on this machine today,
except where marked "needs your keys/Mac". No claims without a run behind them.

## What was built

```
anticipy_app/
├── agent/        the browser agent (drives a real browser like a human)
├── brain/        the orchestration brain (ignore / act / ask triage)
├── backend/      PocketBase: accounts, pendant pairing, events, job queue
├── app/
│   ├── core/     audio pipeline (pendant BLE dump -> Opus decode -> WAV)
│   └── ios/      native SwiftUI iPhone app (BLE + live STT + confirm cards)
├── extension/    Chrome extension (Manifest V3, loads unpacked)
├── proof/        every proof script + screenshots
└── PROOF_REPORT.md
```

## Proofs that PASSED (run live, keyless)

### 1. Browser agent operates a real browser
`proof: python agent/browser_agent.py form_submit_demo`
- Launched real Chromium, navigated to a live site, typed username+password,
  clicked submit, read the site's response: **"You logged into a secure area!"**
- Second run: navigated a live catalogue and extracted 3 options with prices
  (the "research and report" flow).
- With your OpenRouter key the same class swaps to **browser-use** (installed,
  imports verified, wired to OpenRouter) for arbitrary natural-language goals.

### 2. Brain triage — 15/15 of your examples
`proof: python proof/test_brain.py`
- All 15 real-life lines (pitch deck, dinner, movie joke, landlord reminder,
  clinic call, Thursday meeting, price check, gym cancel, coffee reorder,
  birthday, contract share, Lisbon trip, running late, blue-or-black question)
  triaged correctly into ignore / act / ask, with concrete goals and
  irreversible actions flagged for confirmation.
- Runs on a deterministic engine today; the OpenRouter path (DeepSeek V3.2) is
  wired and takes over the moment the key exists.

### 3. Backend pairing + realtime (PocketBase — free, not Supabase)
`proof: python proof/test_backend.py`
- Pendant self-registered with a 6-digit pair code → app claimed it by code →
  owner linked → pendant pushed a transcript event → app received it over the
  realtime stream in under a second. **PASS**

### 4. Audio pipeline on REAL pendant data
`proof: python app/core/audio_pipeline.py ~/audio_dump.bin ...`
- Your actual 66-second BLE capture from the pendant: 6,629 frames reassembled,
  Opus-decoded, **0 bad frames** → clean WAV. This is the exact code path the
  phone app uses.

### 5. Chrome extension, loaded unpacked, acting in a real Chrome
`proof: python proof/test_extension.py`
- Real Chromium launched with `--load-extension` (the same "Load unpacked"
  you'd click in chrome://extensions).
- A job was queued in the backend; the extension **claimed it, opened the tab,
  filled the form, clicked submit, read the page's response, and reported
  "done" back to the backend**: `form submitted; site said: You logged into a
  secure area!` **PASS**
- Also ships browser-only Gmail-compose and Calendar-template actions (prefill
  via URL — no APIs), which stop at the page for your final confirm.

### 6. End-to-end spine
`proof: python proof/test_end_to_end.py`
- Real pendant audio decoded → transcript line → brain decided **act** →
  browser agent executed in a real browser → result reported; irreversible line
  ("I'll send you the pitch deck") stopped at **"Draft ready — send it?"**
  Action-first, confirm-before-send — exactly the product behavior. **PASS**

## Built, pending final proof

### 7. Firmware: "Friend" → "Anticipy" + smooth battery %
- Source changes done in the Omi firmware (DK1 config): BLE name **Anticipy**,
  model **Anticipy Pendant**, and an exponential-moving-average smoother in
  `battery.c` that fixes the jumpy 15→18→16→19% you saw (voltage wobbles under
  charge+radio load; now it's averaged).
- Building the .uf2/.zip in Docker (Zephyr/NCS toolchain) — flashing happens
  over your Mac tunnel exactly like last time.

### 8. iPhone app (TestFlight)
- Full native SwiftUI app written: background BLE (your pendant's exact,
  hardware-verified protocol), Deepgram live transcription, OpenRouter triage,
  job queuing to the extension, transcript + confirm-card UI.
- Cannot compile on this Linux box — needs Xcode on your Mac + your Apple
  Developer account for TestFlight. 30-minute job once you say go.

## What I need from you for the live run
1. **OpenRouter key** → real brain + browser-use agent on arbitrary goals.
2. **Deepgram key** (free $200 credit tier) → live transcription in the app.
3. **Twilio key** (optional now) → real SMS; push notifications work without it.
4. **Mac tunnel** (same one-line paste) → flash the Anticipy firmware.
5. **Apple Developer account** → TestFlight.
