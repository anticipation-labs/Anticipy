# Last Lap

Lap: 20260610T074854Z
Date: 2026-06-10
Phase: P1 closed -> operating as P2-brain STAGE 2 per TARGET v3 (registered phase_gate still gate_P1)
Slice: BUILD — recover and land lap 20260610T072358Z's lost F5 fix; extend it through the
live false-action found by independent re-verification

What happened to the previous lap (read this first):
- Lap 20260610T072358Z (first live-tier run) found F5 (live decider acts on narration)
  and F6 (triage live tiebreak raises and fails open), rewrote the decider prompt around
  the HANDOFF test, and verified it live (contractor_luis false_action 2->0) — then hit
  its session bound (101 turns, stop_reason=tool_use) BEFORE committing. verify_gate
  captured the work to its lap dir's uncommitted.patch and the tree was reset: HEAD still
  had the old prompt while the scoreboard row said kept=True. Ledgered as D20.

What changed (product):
- engine/anticipy_engine/proactive/decider.py — the recovered HANDOFF prompt, upgraded
  twice: (1) to the dead lap's authored-but-never-tested v4 variant ('"-ing" openings
  describing their own activity are not instructions') after probing showed v3 26/27 vs
  v4 27/27; (2) two new clauses from this lap's live doctor_amara evidence — purpose
  tails ("so the morning isn't chaos") don't convert "-ing" self-activity into an
  instruction, and self-personification self-talk ("future me", "tomorrow-me") is
  narration. Docstring records the lineage.
- engine/scripts/test_decider.py — the recovered F5 prompt-clause pins, extended to pin
  the '"-ing" openings' clause.
- logs/factory/laps/20260610T074854Z/probe_decider.py — the dead lap's probe, extended
  to 31 lines: 3 generic self-personification probes (no bank phrasing) + 1 same-domain
  imperative guard ("Remind me tonight to set out my running clothes..." must stay ACT).

Eval numbers I saw (verify_gate recomputes everything):
- Live probe (Gemini free tier, temp 0): old prompt on disk would have scored as before;
  recovered v3 = 26/27; landed prompt = 31/31 with all ACT/ASK true positives held.
- Live tier, dev bank, contractor_luis + doctor_amara (run 20260610T074854Z-live2):
  false_action 0 (doctor was 1 under v3 — pre-existing, found in the dead lap's
  unanalyzed live-full run too), catch 1.0 both, silent_harm 0, interrupt 2.0 / 2.5
  (gate_P2 needs <=3.0). The one residual ask ("Reminder-me must exist") restates an
  already-captured reminder — ask-debounce/goal-dedupe territory, not prompt territory.
- Stub tier, full 8-persona bank (run 20260610T074854Z-pre): catch 1.0/1.0, false 0,
  harm 0, interrupt 1.0625/1.5, correct_action 0.6788, recall 1.0 — ratchet best on all
  gated metrics. e2e_completion 0.3249 vs best 0.3427: stub goal-completion timing noise
  (decider is provably unconstructed in stub; e2e has drifted 0.22-0.34 across identical
  code in prior laps).
- Suite: 32/32 green.

Process notes:
- lap_type=build; attempt_gate_close=false (gate_P1 already closed; re-running strands
  real calendar events, B7). The stub scoreboard cannot count this lap mechanically
  (catch_rate_worst at ceiling 1.0, decider live-only) — treadmill 2->3 expected and
  stated in the manifest. The real movement: gate_P2 guards now hold at LIVE tier on
  both probed personas, and the F5 fix is actually in a commit this time.
- NEW ledger D20 (ops): bounded sessions that commit last can lose the whole lap;
  builder lesson is commit-as-soon-as-verified; foreman options listed in the entry.
- Zero real-world side effects: live calls were Gemini free tier (zero spend) through
  the persona runner's mock hands/channels; no gate run; no real artifacts.

Next:
- Foreman: flip current_phase/phase_gate to P2/gate_P2.sh — thresholds pass builder-side
  on the dev bank at stub AND on the two live-probed personas; a gate-close attempt lap
  is cheap once flipped. Consider D20's loop hardening (auto-WIP-commit or FAIL on
  product files in uncommitted.patch).
- Full 8-persona LIVE run is the remaining unproven surface (only 2 personas live-probed
  this lap; the dead lap's live-full run covered 6 minus analysis). Watch 429/quota
  pressure: decider fail-SILENT under quota is safe-by-design but uncounted live catch
  risk (the dead lap's hypothesis, still only partially tested).
- F6 (triage live tiebreak fails open) remains OPEN by design — fixing it means making
  the triage path async; its own slice. The decider currently carries live precision alone.
- Ask-debounce/goal-dedupe for restated reminders ("Reminder-me must exist" class) is a
  named candidate slice: it is interrupt cost, not a false action.
- Still-open product gaps unchanged: B5/B6 (capture-time act artifact, quoted-title
  drop), B7/B8 (gate env), D16 (restart double-fire), F3 first-person sends (the HANDOFF
  prompt now holds it on probes and both live personas, but recipient extraction is
  still unbuilt).
