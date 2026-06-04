# Room 7 — The Proactive-Judgment Eval (the report card; numbers, not vibes)

## Recipe (from current practice, last-12-mo sources)
- Proactive-agent evals (ProAgentBench) score with **precision** (interruption cost — don't
  nag) and **recall** (need coverage — don't miss). Safety benchmarks (AgentHarm, ATBench)
  add **harm** dimensions with **machine-checkable safety policies** + FPR.
- So the report card = act-precision + act-recall + over-ask (interruption cost) + harm-catch
  recall + a machine-checkable **silent-harm gate** (a detrimental action executed without an
  ask — must be 0, 100%).

## Design — `engine/scripts/proactive_eval.py`
- Scores the REAL decision components (Room 1 `Triage` + Room 2 `HarmLine`) on a labeled day,
  exactly as `on_event` decides: `ignore` if not actionable; else `ask` if detrimental else
  `act`. Deterministic, ZERO model calls.
- A labeled day (~40 events): `act` (safe/reversible), `ask` (detrimental), `ignore` (noise).
- Metrics: act-precision, act-recall, over-ask rate, ignore-correctness, **harm-catch recall**
  (detrimental → ask), and the **SILENT-HARM gate** (detrimental → act count; HARD 0).
- **SELF-PROVE the instrument first** (`--selftest`, in CI): (a) plant one clear act/ask/ignore
  and assert they classify right; (b) verify the metric math on a tiny known set; (c) INJECT a
  synthetic silent-harm (a detrimental scored as `act`) and assert the gate FLAGS it — so the
  eval can't pass vacuously. Only after the instrument is proven do we report a score.
- **Judged layer** (flag-gated `--judge` / `ANTICIPY_EVAL_JUDGE=live`; never in free CI): a
  pinned judge rates a sample of decisions ("was act/ask appropriate for this action?") →
  agreement rate. Real calls; cost printed.

## Test
`proactive_eval.py --selftest` (in the suite, zero model calls): instrument SOUND — plants of
each class classify right, the metric math checks out, and a planted silent-harm is caught.
The full deterministic report (act-precision / recall / over-ask / harm-recall / silent-harm)
is run and pasted straight.

## Sources
- ProAgentBench — proactive-assistance benchmark (precision = interruption cost, recall = need coverage): https://arxiv.org/pdf/2602.04482
- AgentHarm — harmfulness benchmark for LLM agents: https://arxiv.org/pdf/2410.09024
- Evaluation and Benchmarking of LLM Agents: A Survey: https://arxiv.org/html/2507.21504v1
- Beyond Task Completion — assessment framework for agentic AI: https://arxiv.org/html/2512.12791v1
