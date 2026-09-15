# System integration and reliability plan — 15 September 2026

The owner prioritized the work in this order after the initial app audit.
This is an execution plan with acceptance criteria, not a claim of completion.

## 1. Finish and record the current audit checkpoint

- Preserve the original checkout's local work and record the fetched Git heads.
- Commit the tested local persistence/onboarding repairs, their regressions,
  the audit and the new crash evidence summary on the audit branch.
- Keep that branch distinct from the app release branch. No release while the
  Mac button-interaction crash is unresolved.
- Complete the ongoing full-history fetch and verify the reachable-object
  inventory before calling the historical Git review complete.

## 2. Establish the firmware source and wiring contract

Handoff received from the hardware task: local 0.9.8 candidate has not been
committed to Git. Its supplied UF2 hash is
`93256773d375d0a61cca125b98f7884ef2a73b133590867b3351e5d8411a23d0`.
The task reports a temporary memory diagnostic is currently on the assembled
unit and no longer enumerates USB; one physical double-reset is needed to
restore the normal updater. This report is not a new physical test by this
audit. The 0.9.8 LED implementation does not meet the requested state meanings.

- Obtain the firmware handoff from the existing hardware task; verify every
  path, board target, binary hash and source commit locally.
- Confirm the assembled board is the intended Seeed XIAO Sense variant and
  reconcile microphone, battery and external storage wiring against its actual
  firmware pinout. USB enumeration alone cannot establish soldered pinout.
- The owner reports the pendant assembled and connected by a data cable, with
  memory hardware present but no SD card inserted.
- Before changing firmware, identify the attached device and its running
  version. Preserve the known rollback image and recovery procedure.

## 3. Closed-case maintenance and repeated provisioning

- Prove update/reset entry while connected to USB without pressing the board's
  button or opening the enclosure.
- Prove a recoverable failure path for an interrupted update. Distinguish
  ordinary application reset, owner reset and firmware replacement.
- Make the procedure detect and verify the particular device before writing;
  record serial/identity, input hash, source revision and post-update version.
- Run the same procedure against each additional attached pendant. A success
  on one unit is not recorded as a success for all units.

## 4. Firmware state and storage acceptance

- Ready must be green. Pairing, low battery and listening must have distinct
  indications; document precedence when states overlap.
- An LED must describe a measured firmware state, not imply microphone capture,
  pairing or storage success merely because the board is powered.
- Test microphone input with a known audible control, BLE transport,
  reconnect/restart, battery status and any available onboard memory.
- SD-absent behavior must be explicit and non-crashing. SD read/write,
  integrity, full-card, removal and power-loss tests require an inserted card;
  host simulations do not establish physical-card results.

## 5. End-to-end product and crash repair

- Trace pendant → receiving app → account/backend → task/result, recording
  which link is established and which is unavailable. The audited iOS version
  has no pendant Opus decode path; pairing alone cannot clear capture.
- Diagnose the captured Mac build178 button crash. Reproduce from a clean
  launch, verify binary identities, fix the cause and retest the triggering
  interaction during a controlled recording.
- Investigate disappearing windows, all onboarding controls, denied
  permissions, sleep/wake, restart, unsaved edits and account change.
- Collect an actual phone crash report for the intermittent iPhone exit;
  simulator success does not explain a physical-device crash.
- Bring the in-app setup instructions and animations into agreement with the
  verified wiring, LED meanings and available capture path.

## 6. Cleanup and subsequent work

- Clean up only test-created processes, fixtures and rebuildable outputs once
  evidence and changes are preserved. Retain real recordings, original local
  changes, firmware rollback images and the old Mac archive.
- Update the Git documentation and execution ledger with commit/push/merge and
  live verification facts. Record failures and unproven acceptance legs.
- Plan and execute the owner's subsequent tasks when supplied, researching
  their actual dependencies and current primary documentation. Do not invent
  a task list or schedule based on the existence of future work.
