# USER_DEVICE_ENGINE.md

This contract defines the installed V7 runtime.

## Canonical Term

Use "user-device engine" for the installed runtime. The phrase means the public
downloaded engine installed on each signed-in user's computer.

## Responsibilities

The user-device engine must:

- Pair to the user's public Anticipy account after install.
- Accept the four V7 input modes defined in `contracts/INPUT_MODES.md`.
- Convert every input mode into the same inference boundary.
- Read the user's real Chrome, native apps, screen, files, permissions, and
  microphone state.
- Act, ask, decline, or stay silent according to the decision schema in
  `contracts/INFERENCE.md`.
- Emit proof artifacts that can be inspected without trusting logs alone.

## Real User Surfaces

The engine operates on the user's actual signed-in surfaces:

- Real Chrome profile and tabs.
- Native apps through accessibility and screen reads.
- Browser DOM, screenshot, and vision reads when available.
- Files, downloads, and operating-system permission state visible to the user.
- Microphones selected by the user or operating system.

It must not use a cloned Chrome profile, a hidden browser, a copied fixture
account, a synthetic app surface, or a mocked service response as proof.

## Universal Surface Runtime

The engine must not depend on a giant global skills library. It uses the
primitive runtime in `contracts/SURFACE_RUNTIME.md`: read, open, click, type,
shortcut, wait, verify, ask, decline, and notify. App-specific recipes are
learned per user only after a real surface receipt exists, then retrieved in a
small bounded set for that user and surface.

## Chrome Rule

Chrome work must happen in the user's real Chrome state. If Anticipy needs
browser automation, it may attach to or launch Chrome with session preservation
and an explicit user-visible state. The verifier must read the same browser or
visible surface the user would read.

## Decision Rule

For every actionable inference, the engine records exactly one decision:

- `act`: execute when evidence is sufficient and policy permits.
- `ask`: request clarification, consent, permission, or missing context.
- `decline`: refuse or defer when the task cannot be safely verified.
- `silent`: do nothing when a competent assistant would not interrupt or act.

Each decision cites the input, inference event, target surface, reason, and proof
references. A decision without proof references is incomplete unless the reason
is a purely internal non-action such as duplicate suppression, and even then the
input and inference event must be recorded.

## Proof Rule

Surface proof wins over logs. Valid proof includes current DOM reads,
accessibility reads, screenshots, visible state diffs, file hashes, installer
hashes, permission captures, and evaluator records tied to the public build.

Invalid proof includes fake receipts, stale-source proofs, private source runs,
fixture screenshots, mocked API responses, hidden browser state, and logs with no
surface-readable corroboration.
