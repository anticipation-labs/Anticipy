# Room 2 — The Harm-Line (act-first, ask-only-before-harm)

## Recipe (from current practice, last-12-mo sources)
- **Reversibility-first.** Autonomous execution for reversible actions; mandatory human
  approval ONLY before irreversible / external / high-stakes ones. "The agent drafts the
  email; a human sends it." This is exactly act-first + ask-before-harm.
- **Deterministic enforcement close to the action — NOT purely in the LLM loop.** Irreversible/
  high-risk gating "should not live purely inside the LLM reasoning loop; they need
  deterministic enforcement close to the action itself." So the harm-line is a DETERMINISTIC
  policy (rules close to the action); the smart model only assists on genuinely hard cases.
- **Four-tier risk model**: read-only → reversible → external → high-risk. Maps to binary:
  read-only/reversible = ACT; external/high-risk = ASK.
- **Fail safe.** Unsure whether detrimental → treat as detrimental → ASK (the LAW).

## Design — `proactive/harm.py::HarmLine.assess(action_text, ctx) -> HarmVerdict`
ONE inspectable policy. Detrimental signals are checked FIRST and OVERRIDE reversible ones
(a paid booking is money-detrimental even though "book" is reversible).
- **DETRIMENTAL / ASK (general categories):** money/payment, destroy/delete/cancel, post
  publicly, BINDING SEND to a real person, sign-up/subscribe (paid/hard-to-cancel),
  authenticate-past-a-wall (never auto-auth). 
- **REVERSIBLE / ACT (general categories):** research/look-up/read, draft/prepare (NOT send),
  add-to-cart (NOT buy), calendar hold / reminder, hold/reserve a (free) reservation,
  prepare a document.
- **Gray middle = memory.** A SEND is irreversible+external → detrimental BY DEFAULT; memory
  (inject) may downgrade to ACT only if HIGH-confidence the recipient is casual/non-binding.
  Memory is currently weak (0.30 abstention), so most sends fail-safe to ASK.
- **UNSURE → ASK.** No detrimental AND no recognized-reversible signal → unclassified → can't
  confirm safe → fail-safe ASK.
- **Deferred-2 fallback (explicit + logged):** whenever LOW memory confidence / abstain forces
  an ASK on something that might otherwise act, set `memory_forced=True` and count it — that
  count measures how badly we need the stronger confidence signal next.

## HARD SUB-GATE (the old risk gate, folded in)
No detrimental action is EVER executed silently — 100%, no exceptions. The engine asserts it
never created a goal for a detrimental verdict. Recall on detrimental MUST be 1.000.

## Test (written before the impl)
`engine/scripts/test_harmline.py` — ~50 labeled realistic actions (clearly-safe / clearly-
detrimental / gray). Assert: ACT on clearly-safe, ASK on detrimental. Report act-precision +
per-category precision/recall + over-ask rate + the memory-forced-ask count. **HARD: detrimental
recall == 1.000 (no silent harm).** Deterministic, zero model calls, CI-safe.

## Sources
- MindStudio — Classify AI Agent Actions by Risk (four-tier): https://www.mindstudio.ai/blog/classify-ai-agent-actions-by-risk
- Galileo — AI Agent Guardrails Framework: https://galileo.ai/blog/ai-agent-guardrails-framework
- chenyezhu — Tool Eligibility: Deterministic Guardrails for Production AI Agents: https://www.chenyezhu.com/writing/tool-eligibility-deterministic-guardrails-ai-agents/
- Dextra Labs — Agentic AI Safety Playbook 2025: https://dextralabs.com/blog/agentic-ai-safety-playbook-guardrails-permissions-auditability/
