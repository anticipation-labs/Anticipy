# 00 — Read Me First: The Operating Thesis

## Five-year-old version

We are building a helper that listens to your day like a really good assistant.

It does not wait for perfect commands. It hears normal human life:

- “Omar, please call Amazon about that plant I ordered.”
- “I told Sam I’d send the deck before Friday.”
- “Let’s meet at 3.”
- “Can you make sure the client file is ready before the call?”
- “I’m so done with this, I should throw my laptop into the ocean.”

It must know the difference between work and venting. It must remember the work. It must do the harmless prep. It must not press the final button without approval.

The mistake we keep making is building many pieces halfway and calling that progress. That dies at 40–60%. The new system only counts things that are proven with receipts.

## The product law

**If it is not harmful, prepare it. Do not press go.**

That means:

- Draft the email. Do not send.
- Create the calendar hold. Do not invite/send externally unless allowed.
- Fill the form. Do not submit.
- Add to cart. Do not buy.
- Prepare the return/refund path. Do not do a payment or final irreversible action without approval.
- Call support only when the task is harmless or beneficial to the user and the call does not bind the user to a payment/legal/medical consequence. Escalate if the call asks for payment, identity-sensitive decisions, legal commitments, medical instructions, or anything irreversible.

The output should sound human:

> “I found the Amazon plant order and prepared the return/refund path. It is ready; Amazon needs your final approval before submission.”

Not:

> “Dispatching task 6 to workflow executor.”

## Big details before micro details

The big things are:

1. Memory.
2. Proactive intent detection.
3. Safe action preparation.
4. Real browser/API/voice execution.
5. Receipts.
6. The download/onboarding/app path that lets a normal user run it.

MP3 upload, microphone capture, extension buttons, and UI polish matter, but they are subordinate. They must not become rabbit holes that avoid solving the proactive action core.

## The anti-collapse rule

Never be “60% done” with everything.

Be:

- Gate 1: 100% done, receipt in ledger.
- Gate 2: 100% done, receipt in ledger.
- Gate 3: 100% done, receipt in ledger.
- Everything else: 0% until proven.

A feature is not done because tests are green. A feature is done when a skeptic fails to break it and a human-openable receipt proves it.

## The default method

1. Verify current truth.
2. Pick one gate.
3. Spawn parallel agents in isolated worktrees.
4. Builders build.
5. Skeptics try to break.
6. Integrator verifies against current HEAD.
7. Receipt or revert.
8. Update truth files.
9. Continue.

No silent shrinking of done. No agent grading itself. No vague percentages. No fake progress.
