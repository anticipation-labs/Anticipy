# Wave 1 — fix the completion-killers (gauge-measured, ranked)

Branch `wave1/fixes` off green main (`2495943`). Every fix judged by re-running the WHOLE
`journey_eval` (deterministic core + live slice), not a local unit test. SILENT_HARM stays 0
throughout; a fix that makes it non-zero is reverted on the spot.

Live slice = real-model planning + STUB execution (the real browser/API hands need a one-time
human setup — see the bottom of this file). So the live number measures the PLANNING layer with
a real model; the real-HANDS number is gated on Omar's setup.

## KILLER 1 — PLAN_BAD @ live (the big one) ✅
- **Root cause:** the orchestrator asked the model for a plan and did a bare `json.loads(raw)` —
  a real model returns fenced / prose-wrapped / slightly-off JSON, so the WHOLE plan dropped and
  every live journey died before a single step ran. (Secondary: with no tool vocabulary, a real
  model invents intents no worker handles → HAND_FAILED.)
- **Fix (general; reused the browser-agent pattern):** request structured output (`json_mode=True`
  on the plan call) + a resilient extractor `_robust_json` (strip fences → whole → balanced-brace)
  + skip a malformed step instead of dropping the plan + ONE bounded re-ask for clean JSON on
  failure. Plus: give a REAL model the available intent vocabulary (all registered worker intents,
  general — the model still chooses), gated to `provider == openrouter` so the STUB tier's prompt
  and plans stay byte-identical (it greps the prompt for keywords).
- **Measured (whole house):**

  | metric | before | after |
  |---|---:|---:|
  | live completion (real-model plan + stub exec) | 0/10 | **9/10** |
  | live DIED: PLAN_BAD | 10 | **0** |
  | live DIED: HAND_FAILED | 0 | 0 (was 9 mid-fix; vocabulary closed it) |
  | live SILENT_HARM | 0 | 0 |
  | deterministic completion | 0.952 | 0.952 (byte-identical) |
  | deterministic DIED-WHERE | TRIAGE_DROPPED=4, OVERASK=1 | same |
  | full suite | 29/29 | 29/29 |

  Remaining live death = 1 × HARMLINE_OVERASK_STALL (the same "book us a table" → Killer 3).
- **Commit:** see Commit stack (bottom).
