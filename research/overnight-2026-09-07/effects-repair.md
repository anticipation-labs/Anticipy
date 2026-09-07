# Private preparation should not ask permission to begin

The initial cross-domain run held private drafts before any source lookup.
Two separate causes contributed: triage examples labelled a private draft as a
world-changing task, and `is_consequential` interpreted goal verbs with a regex
even when the model had supplied an effect declaration. A third defect dropped
that declaration on both quiet-research paths into the queue.

The repair asks a focused model question with the original request,
conversation, clock and provenance-bearing memory. Producing a private answer
or draft differs from saving in another account or sending to another person.
The consequence function now consumes declared effects only. Missing or
unreadable declarations hold; the queue asks the model for absent declarations.
The verb list, read-only regex and calculator-based permission fallback are
removed. Existing device-act, workflow approval, API catalog and browser
execution checks remain separate from this planning judgment.

The routing prompt also distinguishes remembering what someone said about a
calendar from actually reading that calendar. A missing connection or an
offline browser cannot turn private-source work into a memory answer. The
router now uses the available stronger model after the cheaper model continued
making that substitution with the corrected context and prompt.

Evidence in effects-results.json:

- 20 real-model contrasts passed, including draft versus send, calendar read
  versus write, compound tasks, and hostile text inside a source document.
- Actual worker replays persisted private drafts as queued/read-only rather
  than awaiting confirmation. No provider effects or browser execution were
  armed in these transcript fixtures.
- A compound request to update thesis notes and schedule reading correctly
  remained consequential. Preparing its sources before final approval is
  still a separate improvement; this repair does not claim it completes that.
- The stronger router identified the unavailable private calendar/document
  access. A helpful connection request is still needed at that point.

Full Python run: 3,094 passed, two skipped. The three remaining failures were
the retirement ledger detecting the two deleted pieces of tape. The following
ledger commit records this removal commit and preserves both expiry predicates;
it must be included before deployment. Earlier failed runs are preserved in
work/audit/overnight-effects-full-1.log and -2.log.
