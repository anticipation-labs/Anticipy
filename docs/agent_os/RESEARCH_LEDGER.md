# RESEARCH LEDGER — lanes → decisions (not dumps)

Research must end in a build decision with primary-source citations. A decision cannot be marked
researched until its lane is completed, explicitly irrelevant, or blocked-with-reason. Full source
notes: `docs/agent_os/imported/.../12_SOURCE_NOTES.md`.

| # | Lane | Status | Decision / next step |
|---|---|---|---|
| 1 | **Model/runtime route** | OPEN | Verify the engine's actual runtime model + base URL with a real call (failable). The kit recommends OpenRouter (`https://openrouter.ai/api/v1/chat/completions`) with paid-route check + fallbacks. Prior note: engine ran on Gemini free tier at one point (D18). Re-confirm what's live now in `engine/.env.local` (do not print secrets) and a live smoke call. → part of Gate A receipt 6. |
| 2 | **Browser arm** | OPEN | Kit recommends `browser-use` (open-source, our model, isolated Py3.11+ service via bridge) over the in-house WebVoyager agent. Current in-house arm achieves the round-trip receipt (`b82e660`). Decide: adopt browser-use vs harden in-house. Research before any rebuild; do not switch stacks without cause. |
| 3 | **API integration/auth** | PARTIAL | Arcade already used for onboarding scan + calendar. Confirm Gmail draft + Calendar scopes for prepare-and-park. Every write needs independent read-back. |
| 4 | **Desktop packaging/signing** | OPEN | An "Anticipy Execute" macapp runs (`macapp/`). Verify build/download path + Apple signing/notarization needs (Omar-gated credential). Kit suggests Tauri for a fresh app; current app already runs — don't switch without cause. |
| 5 | **Chrome extension / local bridge** | PARTIAL | `extension/` exists, `/status` shows `extension_connected:true`. Confirm the connection is real (hit the actual endpoint, don't trust a flag) for Gate E/F. |
| 6 | **Voice/transcription** | PARTIAL | Twilio voice/SMS proven for one reminder. MP3 transcription path (OpenAI/Deepgram) — verify it feeds the same brain. Omar-gated for live sends. |
| 7 | **Security/prompt-injection/privacy** | ONGOING | Webpage/email text is untrusted; no page authorizes actions. Tokens encrypted per user; no secrets printed/committed. Keep `safety_mega_eval` + `purchase_guard` as standing gates. |
| 8 | **Eval harness / synthetic life bank** | PARTIAL | Persona bank v1 exists (8 dev + 4 holdout). Kit wants a larger hidden-truth bank (70 owners + ~400 related people). Expand only when it unblocks a real catch-rate measurement, not as busywork. |

_Seeded 2026-06-16. Update as lanes resolve._
