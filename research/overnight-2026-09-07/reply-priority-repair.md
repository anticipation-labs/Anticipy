# Reply priority and preserved task context

September 7, 2026, Vancouver. Release proof is recorded separately after CI.

## Why this work resumed

The “Repair Anticipy overnight” thread follow-up was scheduled every 15 minutes
for the earlier overnight request. It woke this thread after the completed
15-person lab was delivered. It is now **PAUSED** at the owner’s request for
clarity and a finite finish. This repair closes the one in-progress extension
of that lab; it does not start a new general audit.

The original lab, five deployed fixes, and six-page PDF remain documented in
[persona-lab-status.md](persona-lab-status.md).

## What failed and what changed

Direct texts and app answers were processed after a serial speech batch.
Executing the real main-loop section with simulated 20-second speech decisions
made both replies wait 300 seconds. The candidate checks the same owner’s direct
inputs before initiative and between speech decisions. The first reply ran at
0 seconds; one arriving during a decision ran at 20 seconds. Speech continued.
This is a scheduling proof, not measured production phone latency.

Prioritizing a reply can overtake speech that has been captured but not yet
interpreted. A real-model probe reproduced “which two links?” despite both URLs
being present in the earlier speech. Supplying that speech fixed understanding,
but a second inspection caught the URLs missing from the queued execution.

The repair reads earlier speech within the current owner and incoming-event time,
retains speaker/source labels, and persists flat quoted source records with the
task. Classifier, brain, API tool selection, server work and browser background
receive the evidence. Source context never becomes an approval or a form value.
Repeated handoffs cannot recursively embed entire task histories. Later replies
are excluded from reconstructed conversation history.

No sentence patterns, word lists or semantic thresholds were added. Scheduling
uses transport kind/source; ownership and timestamps bound retrieval. Models
continue to interpret human meaning and decide actions.

## Verification

- Python: **3,033 passed, 2 skipped**. The first full run caught the extension
  version reference needing an update; it was fixed, and the full suite rerun.
- Browser: **all 83 suites passed**; source context remains outside approval
  facts, with existing submission restrictions unchanged.
- iOS: the pre-edit build-169 run and post-edit build-170 run passed. Both
  build files move with the app’s extension-version reference in this commit.
- Actual-model retest: Mina retains both exact URLs in one queued research task;
  Theo’s fictional dialogue produces zero tasks. Both fixture accounts erased.
- Actual isolated Chrome: the saved task context supplies the links; the browser
  reads both fixture pages and returns USD 87 and USD 94 with the correct URLs.
  Three model calls, no external website effects. This is adapted extension
  plumbing in isolated Chrome, not the owner’s installed extension.
- Real local Worker query: mixed app/SMS/composer order, owner isolation, processed
  exclusions and earlier-versus-later speech all pass. Both fixture accounts erased.
- Follow-up probes used **49 model calls, US$0.373505328**, within the original
  audit budget. The original lab’s 555 calls/US$3.8450 are a separate dated total.
- Extension **0.18.0**: all three ZIP aliases match source and package dependencies.
  SHA-256: `4e409dcec8fa01669fe07fb60e83ef14870bf6cd0327a9db7a65e346b2a4690a`.

[Machine-readable before/after evidence](reply-priority-evidence.json) retains
failures as well as retests. Reproduce with `tests/test_interactive_priority.py`,
`tests/test_text_task_context.py`, the persona driver’s `--unheard-ambient` mode,
and `proof.audit.reply_priority_probe`. No real texting was used in these probes.

## Adversarial review and limits

The review challenged lost source data, false consent, cross-owner reads, future
reply leakage, recursive context growth, exception leakage, stale extension
packaging and iPhone version drift. These checks pass in the recorded scope.

An in-flight model call, profile import or other serial worker duty can still
hold a reply. This repair removes the speech-batch ordering penalty; it does not
make every operation instant or prove fresh phone capture speed. Context windows
are finite. Real OAuth, carrier delivery, arbitrary browser tasks and the owner’s
installed extension remain separate proof gaps. The last observed personal
extension was 0.15.0; publishing a ZIP does not update an unpacked Chrome install.

The iPhone source change only updates the extension-version warning. Build 170
must be shipped by CI and independently checked in App Store Connect. Do not
report it available before that receipt exists.
