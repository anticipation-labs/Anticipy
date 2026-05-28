# PRODUCT_TARGET.md

This contract defines the V7 public product target.

## Canonical Path

The V7 target is:

`https://www.anticipy.ai/app -> account/onboarding/download -> public downloadable user-device engine -> installed on each user's computer`.

This is the full public product path.

Everything required for a normal user to start must be reachable from the public
app path. A verifier must not need a repository checkout, local source server,
private binary, private URL, Omar credentials, or manual database setup to reach
the product.

## Product Boundary

The public app owns:

- Account creation and sign-in.
- Onboarding.
- Download and install instructions.
- Public installer identity and hash display.
- Pairing the installed user-device engine to the signed-in account.
- Status, settings, and proof review surfaces.

The user-device engine owns:

- Accepting MP3/audio upload, text transcript paste/upload, computer microphone,
  and external microphone input.
- Running ASR for audio inputs where required.
- Feeding normalized input into the same inference boundary.
- Reading the user's actual signed-in browser and app surfaces.
- Acting, asking, declining, or staying silent with proof.

## Product Spine Order

V7 advances through one product spine. Planner, worker, and judge decisions must
prefer the first actionable failure in this order:

1. Installed public product path.
2. Unified input boundary.
3. Surface runtime/action execution.
4. Memory resolution.
5. Proactive observation.
6. Breadth/clean-room.

Verifier and evaluator work is a guardrail on this spine. It can reject fake
progress or preserve proof quality, but it does not replace product work that
makes an earlier spine step true for a user.

## Non-Negotiables

- `anticipy.ai/app` is the public product entry.
- The downloadable engine must be public, current, and tied to a manifest hash.
- The installed engine must run on each user's computer and pair to that user's
  signed-in account.
- Real Chrome and real native app surfaces are the action and proof surfaces.
- Real Chrome/user surface/no clone is the verifier rule.
- No cloned Chrome, fixture account, copied profile, or hidden browser can count
  as a user surface.
- No fake receipts/stale-source proofs. Proof must come from the current public
  build and current visible state.
- No giant global skills catalog can count as the product brain. The user-device
  engine must use universal surface primitives plus small user-local recipes, as
  defined in `contracts/SURFACE_RUNTIME.md`.

## Valid Public Product Proof

A valid proof bundle includes:

- Public app URL and capture timestamp.
- Account or session identifier, redacted where needed.
- Onboarding step path ending at account/onboarding/download.
- Public installer URL, manifest hash, and downloaded file hash.
- Installed user-device engine identity and paired account identity.
- Input-mode artifacts for all four V7 modes.
- Inference and decision artifacts conforming to `contracts/INFERENCE.md`.
- Surface-readable proof for any act, ask, decline, or silent no-op.

Logs may be included, but logs alone do not satisfy this contract.
