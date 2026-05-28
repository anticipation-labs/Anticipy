# CLEAN_ROOM_PUBLIC_INSTALL.md

This contract defines public clean-room proof for V7.

## Purpose

The public clean-room proof shows that a normal user can start from
`https://www.anticipy.ai/app`, create or enter an account, complete onboarding,
download the public user-device engine, install it on a computer, provide input,
and receive act/ask/decline behavior with proof on real user surfaces.

## Clean-Room Conditions

A valid run must:

- Start from the public app URL, not a local source server.
- Use the account/onboarding/download path.
- Download the public installer and record its URL and SHA-256 hash.
- Install the user-device engine on a real computer.
- Pair the installed engine to the signed-in account.
- Use real Chrome or real native app surfaces for any browser or app action.
- Avoid Omar credentials, private env vars, private binaries, copied runtime
  state, fixture profiles, mocked services, and cloned Chrome.

## Required Exercise

The run must exercise:

1. MP3/audio upload.
2. Text transcript paste/upload.
3. Computer microphone.
4. External microphone.

Future pendant audio is valid only as an external microphone source that enters
the same inference boundary.

The run must produce at least one inspectable record for act, ask, decline, and
silent no-op across the run or across the evaluator suite. Every record must link
to `anticipy.inference_event.v7` and `anticipy.decision.v7`.

## Proof Bundle

The proof bundle must contain:

- Public app capture with timestamp.
- Account/onboarding/download capture with timestamp.
- Installer URL, installer SHA-256, and public manifest reference.
- Install log and paired device id.
- Permission state captures for microphone, screen, accessibility, and browser
  automation where applicable.
- Input artifacts for all four modes.
- Normalized input, inference event, and decision JSONL files.
- Real Chrome or native app proof for each surface action.
- Proofs for asks and declines, including the user-visible message or logged
  silent reason plus absence of broken visible state.
- Evaluator manifest with pass/fail reasons.

## Invalid Proofs

These do not satisfy V7:

- Fake receipts.
- Stale-source proofs.
- Screenshots from an older public build.
- Logs without surface-readable proof.
- Manually copied binaries.
- Local source servers.
- Private download URLs.
- Mocked browser or app surfaces.
- Fixture accounts represented as public users.
- Cloned Chrome profiles.
- Engine-only claims that do not tie back to the public app and installer hash.

## Pass Rule

The clean-room proof passes only when the public app path, public installer,
installed user-device engine, four input modes, same inference boundary, real
user surfaces, current proof artifacts, and evaluator manifests agree.

If any part cannot be inspected, the clean-room proof fails.
