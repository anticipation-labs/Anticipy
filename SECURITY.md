# Security

## Reporting a vulnerability

Report privately through GitHub's private vulnerability reporting on this
repository (the Security tab, "Report a vulnerability"). Do not open a public
issue, and do not include real customer data, transcripts, or credentials in
a report; describe how to reproduce with synthetic data.

Note for the repository owner: private vulnerability reporting is switched on
by the owner under the repository's Settings, Security section (one click).
Until it is on, the Security tab does not show the report button.

## Scope

- API Worker: `migration/workers/` — D1, R2, the Durable Object, the records
  API, the product routes, HQ, the model proxy, the connect flows, static
  downloads.
- Brain: `migration/workers/brain/` (the fleet controller) and `brain/` (the
  per-owner Python process, its memory, its messaging arms).
- Chrome extension: `extension/` — runs in the owner's logged-in Chrome with
  broad host permissions and the `debugger` permission.
- iPhone app: `app/ios/`.
- Mac app: `app/macos/`.
- Pendant firmware: `firmware/`.

Especially relevant: anything that lets one owner's data, memory, credential,
job or connection reach another owner; anything that lets a hand act without
the row's approval, lease or receipt; anything that reads meaning off a
pattern where a model verdict is required (HARNESS-LAWS.md Law 1).

## No secret values in the repository

Credentials are Worker secrets (`wrangler secret put`), GitHub Actions
secrets, or a private environment file kept outside the checkout.
`migration/runbooks/SECRETS.md` is the inventory of every credential by
**name and location only**; no value appears there or anywhere else in the
tree. `.gitignore` excludes `.env`, `.env.*`, `*.env` and `.dev.vars*`. A
credential that appears in a file in this repository is a bug: report it, and
the owner rotates it (`migration/runbooks/ROTATION.md`).

## The private-data boundary

- **Per-owner memory.** `memory.db` is one real person's mind: every line they
  said, their profile facts, their commitments. It is never committed
  (`.gitignore`: `migration/workers/owners/`, `**/owners/*/memory.db`). The
  durable copy lives in R2 and reaches a container only for its own owner.
- **Disposable rigs.** `work/` is git-ignored and holds local proof state
  (loopback tokens, synthetic owners, results). Copy reviewed, redacted
  findings under `research/`, never the raw directory.
- **Screenshots and traces.** `output/playwright/` is git-ignored because
  captures can carry session headers or personal data.
- **Speaker models.** `.speaker-models/`, the owner's voice profile, is never
  in git.

## Firmware safety status

The pendant firmware is a candidate, not production firmware. Encryption and
one persisted bond do not authenticate an owner: without a physical
enrollment/erase gesture or an allowlist, the first nearby central can take
the sole bond. Read the "Safety status" section of
`firmware/source/README.rst` and `docs/FIRMWARE-COLLABORATION.md` before
flashing anything.
