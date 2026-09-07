# Speech and question delivery repair

The natural replay reproduced the owner's screenshot, rather than relying on
a hand-written expected model reply. The completed calendar/accounting remark
created a new calendar task; another conversation about completed work received
an irrelevant memory answer. A direct calendar request disappeared without SMS.

## Repairs and evidence

- Triage preserves recorded tense, completion and corrections. It cannot invent
  an ASR repair to turn a completed action into a new obligation. Natural5 cases
  1–3 and6–8 stayed quiet; no new jobs or unsolicited app answers.
- Addressed information requests are judged using the actual conversation and
  voice evidence. Question punctuation and a status-word regex no longer route
  an utterance directly to private memory. Unclear/malformed primary verdicts
  get the configured stronger tier.16 real-model cases passed, including Spanish,
  quoted instructions, a different speaker, and a contextual one-word follow-up.
- Factual grounding replaced the active name/count token check. The old check
  considered September an invented person and asked which September the owner
  meant.12 real-model contrasts pass: invented people and quantities are rejected;
  relative dates, spoken numbers and unknown voice attribution do not fabricate
  a contradiction. `tejas_gate.py` now requires that current-source evidence and
  its wired refusal path; it no longer requires the removed word-level check.
- Decision refinements preserve the effect declaration using dataclass replacement.
  Losing `touches=world` during a clarification previously lost the device-calendar
  route. Natural5 case10 retains September10 11:00–12:00 in a held calendar task.
- Questions persist before any optional SMS. A question discovered by the selected
  execution hand uses the same outbox as one identified during triage. Final
  calendar-delivery1 creates exactly one draft calendar job, records the missing
  end-time question, and preserves the invited-question flag. It does not write
  an unsent SMS into outreach history.
- Invited clarifications can text at night without consuming the proactive
  allowance. Proactive suggestions remain deferred. Missing phones, failed
  persistence, duplicate sweeps and restart fences have transport tests.
- Memory rendering retains imported contact JSON as fenced data. Exact record
  identity removes the current utterance's self-echo; word overlap no longer
  erases additional facts or contradictions.

## Limits still requiring work

These results do not mean the backend is fully repaired. Natural5 case9 asks
for Morgan's email despite that address being in the supplied profile, and asks
for document contents before attempting retrieval or requesting its connection.
That is the next memory/context/API repair. Legacy speech-shape, continuation,
voice-name and dedupe heuristics remain elsewhere and must not be described as
removed. The browser's deployed model returned correct comparison data as raw
JSON; human-readable result formatting remains open.

Tests and receipts are in `work/audit/overnight-core-*`, `overnight-natural-*`,
`overnight-calendar-delivery-1`, and the sanitized JSON alongside this report.
Natural runs exercise the real local Worker, brain and models with synthetic
owners; execution arms were intentionally absent and no external effect is
claimed. Live deployment identity is verified separately after release.
