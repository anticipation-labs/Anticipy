# Questions should follow context and retrieval

The natural worker replay found a concrete failure: “draft a note to Morgan
using the delivery change in the workshop brief” asked for Morgan's email,
already present in imported memory, and asked the owner to supply the brief's
contents. The task had never tried retrieval or connection setup.

Two paths caused this. The old sufficiency checker saw only a generated task
title. A triage result of `ask` bypassed the check and memory filling entirely.

`brain/readiness.py` now asks one contextual question on the existing strong
model: does useful authorized progress require an owner-only answer? The
record includes actual speech, conversation, quoted memory with provenance,
local time and connection/browser availability. A named document is a lookup
target; a missing reservation time remains the owner's choice. Disconnected
access is a setup step, not a reason to ask the owner to recite a document.

Both `act` and `ask` are reviewed. No verdict preserves existing uncertainty.
Only the existing trusted, active-memory filler can promote values into a
plan. Imported memory remains quoted; readiness does not grant send/payment
authority. Partial trusted answers now remain attached to the question's task
and are cleared before the next utterance.

## Evidence

- Full Python regression: **3,083 passed, two skipped**, recorded in
  `work/audit/overnight-readiness-full-2.log`.
- iOS pre-edit suite passed at build162; no iOS source changed here.
- Twelve real-model contrasts pass in `readiness-model-results.json`.
  The first two evidence runs are retained under `work/audit/`: three initial
  fixtures accidentally omitted the city or the reason for a thank-you note.
  Their clarification answers were justified; the fixtures were made explicit,
  not the production prompt weakened to suppress those questions.
- Actual worker replays: `readiness-worker-results.json`. The known-contact
  case no longer asks for the email/source contents. Missing calendar end still
  asks; corrected calendar time preserves September10,11AM–noon/no invites.
  The first replay preceded the final per-utterance memory reset; source hashes
  are recorded per case. Unit regressions exercise that last state-isolation fix.

## Still open

This does **not** prove a completed draft. The task still awaits approval before
preparation. That is an independent workflow defect: useful read/draft/setup
work should precede approval of the final external effect.

`_queue_job` also incorrectly gates the entire hand router on `BRAVE_API_KEY`.
The router must see actual research/API/browser availability independently.
The existing connection text-command handler is called only by SMS webhooks,
not by typed app messages or captured speech. The optional device-context offer
handles only calendar titles/times and contact names. It is not the connected
API offer the user expects. These are measured missing wires, not model-quality
claims, and remain next in the repair queue.
