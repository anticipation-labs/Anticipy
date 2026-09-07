# Preserve the actual answer at the reply handoff

Manual review of the50-person planning corpus found two concrete failures:
person10's clarifying question and person43's memory answer were generated but
lost. The initial intent classifier's optimistic acknowledgement survived.
Person35 also selected a full contact name despite two people sharing that name.

Conversation now returns the core's answer or an honest start failure. It accepts
an answer decision as well as an action/question. Explicit goal-less questions
survive the intentionally muted notification callback and return on the original
channel, without a second text. Readiness checks every proposed new task,
including explicit requests whose initial missing-fields array is empty. The
model receives context and examples distinguishing guessed task titles from
actual identity evidence. No phrase classifier or wordlist was added.

## Adversarial review and evidence
- Reviewed muted app/SMS delivery, ambient suppression, missing persistence,
  unrelated pending work and guessed recipient identities. Explicit requests do
  not bypass missing-identity review. A failed core start cannot reuse “on it”.
- Four regression cases plus existing focused tests:26 passed.
- Final full Python run:3,109 passed,2 skipped in58.09seconds. Evidence:
  work/audit/overnight-reply-handoff-final-python.log.
- Real-model whole-worker person35 asks Sam Reed or Sam Kim; person43 returns
  the promised-deck summary. Preserved labels overnight-reply-handoff-development-1
  and overnight-reply-handoff-regression-43.
- Person10c returns the actual Alex Reed/Alex Kim question and keeps its task
  awaiting confirmation. The runner conservatively stamped infrastructure failure
  because a final background model reservation had not settled at collection.
  The ledger later records all22 calls returned; do not overwrite the original
  verdict. The observed question is evidence, not a claim of full task completion.
- Live source rollout and phone-disabled production reply observation remain
  required. Compound preparation can still be held before useful reads.
