# ANTICIPY V7 - canonical correction

This is the controlling document for the V7 correction. It updates the target
from an Omar-specific runtime to the full public product. If any inherited V6
contract conflicts with this file, this file wins for V7.

## PART 0 - THE TARGET

Anticipy V7 is the full public product path:

`https://www.anticipy.ai/app -> account/onboarding/download -> public downloadable user-device engine -> installed on each user's computer`.

The user signs in through the public app, completes onboarding, downloads the
public installer, installs the user-device engine on their own computer, grants
normal permissions, and uses Anticipy against their actual signed-in browser and
app surfaces.

The load-bearing words are:

- Public product. The target is what any user can reach from `anticipy.ai/app`,
  not a developer checkout, internal binary, private URL, or Omar-only session.
- User-device engine. The installed runtime belongs to each signed-in user and
  runs on that user's computer.
- Actual surfaces. Anticipy acts, asks, or declines using the user's real Chrome
  profile, native apps, visible browser tabs, files, microphones, and signed-in
  app state.
- Proof. Every action, ask, and decline needs a fresh, surface-readable proof
  tied to the public build that produced it.

The load-bearing absences are:

- No fake receipts/stale-source proofs. Logs, fixture screenshots, old source
  captures, mocked API responses, cloned browser profiles, or stale public
  builds do not count.
- No cloned Chrome. Anticipy may not prove work in a hidden browser, copied
  profile, fixture account, or parallel app surface that the user is not using.
- No proof bureaucracy as product work. Verifier and evaluator work is a
  guardrail against fake progress; it is not a substitute for making the public
  product path work on a user's computer.
- No completion claim without gates. V7 is complete only when every V7 gate is
  green and `state/COMPLETE.md` exists.

## PART 1 - PUBLIC PRODUCT CONTRACT

The public product contract is `contracts/PRODUCT_TARGET.md`.

The V7 product starts at `https://www.anticipy.ai/app`. From there a user must
be able to create or enter an account, complete onboarding, reach the download
step, install the public user-device engine, and return to the app with the
installed engine paired to that account.

Cloud surfaces are allowed to host account, onboarding, download, pairing,
policy, and status views. They are not the private engine. The engine that acts
on browser and app surfaces is the user-device engine installed on the user's
computer.

## PART 1A - SINGLE PRODUCT SPINE ORDER

The V7 loop must choose the next task from one real product spine. Do not expand
proof, verifier, schema, persona, or breadth bureaucracy while an earlier
product-spine failure is actionable.

The next-task order is:

1. Installed public product path: `https://www.anticipy.ai/app` through
   account/onboarding/download to the public installer, installed user-device
   engine, and paired account on the user's computer.
2. Unified input boundary: MP3/audio upload, text transcript paste/upload,
   computer microphone, and external microphone all reach the same normalized
   inference boundary.
3. Surface runtime/action execution: the installed user-device engine reads real
   user surfaces and can act, ask, decline, or stay silent with surface proof.
4. Memory resolution: user/account/device memory is read, written, resolved, and
   cited at the same boundary without stale or cross-user state.
5. Proactive observation: the engine observes actual visible user surfaces and
   opportunities without cloned Chrome, hidden profiles, or fixture state.
6. Breadth/clean-room: only after the earlier spine items are green or precisely
   blocked, broaden personas, clean-room proof, and evaluator coverage.

Verifier work may block fake receipts, expose the first red gate, or keep proof
honest. It must always name the product-spine step it guards and must not replace
a task that would make that step work.

## PART 2 - INPUT MODES

The input contract is `contracts/INPUT_MODES.md`.

V7 has four input modes:

1. MP3/audio upload.
2. Text transcript paste/upload.
3. Computer microphone.
4. External microphone.

Future pendant audio is treated as an external microphone source. It must feed
the same inference boundary as every other source and must not create a separate
decision path.

All modes converge at the same inference boundary: normalized transcript text
plus normalized source metadata plus current user surface context. Audio modes
produce transcript text through ASR before the boundary. Text paste/upload enters
the same boundary directly.

## PART 3 - USER-DEVICE ENGINE

The runtime contract is `contracts/USER_DEVICE_ENGINE.md`.

The user-device engine runs on each user's computer. It operates only through
that user's real Chrome, native apps, files, microphones, accessibility state,
screen state, and signed-in app state. It may launch or attach to real Chrome
with session preservation, but it must not use a cloned profile, fixture profile,
hidden browser, or synthetic account as proof.

The engine chooses exactly one decision for each actionable inference:

- Act when it has enough evidence and the risk policy permits action.
- Ask when a competent person would need clarification, consent, permission, or
  missing context.
- Decline when it cannot safely verify the surface, intent, permissions, or
  expected outcome.

Each decision must cite proof artifacts that a verifier can inspect without
trusting engine logs alone.

## PART 4 - INFERENCE AND DATA ARTIFACTS

The inference contract is `contracts/INFERENCE.md`.

These are the required data/eval artifacts for V7.

Every normalized input creates an `anticipy.inference_event.v7` record. Every
act, ask, decline, or silent no-op creates an `anticipy.decision.v7` record. The
records must be append-only, schema-valid, tied to the account and device, and
linked to the public build SHA and current source capture.

Required artifact families:

- `normalized_inputs.jsonl` for input-mode convergence.
- `inference_events.jsonl` for boundary events and candidate intents.
- `decisions.jsonl` for act, ask, decline, and silent outcomes.
- `surface_context/` for Chrome, native app, screen, file, and permission reads.
- `proofs/` for screenshots, DOM reads, accessibility reads, hashes, installer
  receipts, and visible state diffs.
- `eval_runs/<run_id>/manifest.json` for evaluator results, schema validation,
  source freshness, public build identity, and pass/fail reasons.

## PART 5 - CLEAN-ROOM PUBLIC INSTALL PROOF

The clean-room contract is `contracts/CLEAN_ROOM_PUBLIC_INSTALL.md`.

A public clean-room proof starts outside the repo and outside Omar's private
runtime. It uses a fresh or ordinary user account, the public `anticipy.ai/app`
path, the public download artifact, and a user-device install on a real computer.
It must exercise the four input modes, the same inference boundary, real Chrome
or native user surfaces, and action/ask/decline proof from visible surfaces.

Invalid proofs include fake receipts, stale-source proofs, copied build outputs,
private install URLs, manually launched source servers, mocked browser state,
fixture accounts presented as real users, or engine logs without surface proof.

## PART 6 - V7 DONE CHECKLIST

This checklist defines the V7 completion gate. It is a contract, not a status
claim.

1. `https://www.anticipy.ai/app` is the public entry and leads through
   account/onboarding/download to the public downloadable user-device engine.
2. The downloaded installer hash matches the public manifest and the manifest
   ties back to the live app state.
3. A public clean-room install passes from the public product path with no repo
   checkout, no private binary, no Omar credentials, and no copied runtime state.
4. The installed user-device engine is paired to the signed-in account on that
   user's computer.
5. MP3/audio upload, text transcript paste/upload, computer microphone, and
   external microphone all enter the same inference boundary.
6. Future pendant audio is represented as an external microphone source and uses
   the same inference boundary.
7. The engine uses real Chrome and real user app surfaces. No cloned Chrome, no
   hidden profile, no fixture surface, and no synthetic account can satisfy
   proof.
8. Act, ask, decline, and silent no-op decisions emit valid
   `anticipy.inference_event.v7` and `anticipy.decision.v7` artifacts.
9. Data and eval artifacts prove schema validity, source freshness, public build
   identity, input-mode parity, inference parity, surface proof, cost, transcript
   quality where audio is involved, and decision quality.
10. No fake receipts/stale-source proofs are accepted by the evaluator.
11. A competent verifier can inspect proofs from the current public build without
    trusting logs alone.
12. `state/COMPLETE.md` exists and cites the green V7 gate artifacts.

If any item above is missing, V7 is not complete.

## PART 7 - OPERATING RULES

R1. The principle in PART 0 wins.
R2. Use public-product language when describing V7.
R3. Use user-device engine language for the installed runtime.
R4. The user's actual browser and app surfaces are the proof surfaces.
R5. Real Chrome/user surface/no clone is the browser proof rule.
R6. All input modes feed the same inference boundary.
R7. Logs support proof, but logs alone are not proof.
R8. No fake receipts/stale-source proofs.
R9. No no-op success claims. Silent no-op is a decision record with a reason.
R10. No completion claim unless the V7 done checklist is green and
    `state/COMPLETE.md` exists.
R11. If a rule conflicts with a contract file, the stricter public-proof rule
    applies.
R12. Choose next work in the single product spine order from PART 1A. Verifier
    work is a guardrail for that order, not an alternate product track.
