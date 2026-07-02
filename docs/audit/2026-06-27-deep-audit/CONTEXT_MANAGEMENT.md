# Context Management Protocol

Purpose: prevent future agents from losing the product, repeating old audits, or trusting stale "done" claims.

## Read Order For Any Future Agent

1. `/Users/omarebrahim/.codex/attachments/e0e18a4b-bcbb-410a-a9ec-beb1ef328da2/pasted-text.txt`
2. `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/AUDIT.md`
3. `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/STAGE_MATRIX.md`
4. `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/BABY_STEPS_PLAN.md`
5. `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/EVIDENCE_LEDGER.md`

Then inspect code for the slice being changed.

## Current Working Truth

Anticipy is not done until the clean hosted product path works:

`welcome -> signup/signin -> extension/device helper -> layered onboarding -> calls -> board -> listen/upload -> browser action -> warm approval -> proof -> memory -> follow-up`

Any result that proves less than this must say what it does not prove.

## Context Pack

Every substantial future session should keep a small context pack updated:

- Objective.
- Source-of-truth line or product requirement.
- Files touched.
- Routes involved.
- Runtime mode:
  - model provider
  - hands mode
  - channel mode
  - data dir
  - extension source
  - whether running local/cloud
- Test path.
- Receipt path.
- Remaining gaps.

## Evidence Rules

Do not write "done", "green", "certified", "gate closed", or "proven" without a receipt that identifies:

- Product claim.
- Exact route/UI/script invoked.
- Live vs mock mode.
- Data directory.
- User/device identity.
- Human involvement.
- External system used.
- Durable artifact path.
- Independent readback method.
- What the receipt does not prove.
- Expiry date.

## Subagent Use

Use subagents for independent slices only:

- Engine/proactive/memory.
- Browser/extension.
- Frontend/onboarding.
- Evidence/tests/docs.
- Security/privacy.

Subagents should produce findings with file paths and line references. The main agent integrates them into this audit packet or a dated successor. Do not leave important findings only in chat.

## Resume Discipline

When resuming:

1. Check `git status --short --branch`.
2. Check whether engine is running.
3. Check `/health`, `/status`, `/ws/state`, and `/readiness`.
4. Check whether the loaded extension matches repo source.
5. Read the relevant stage in `STAGE_MATRIX.md`.
6. Make the smallest product-flow change that crosses off the current baby step.

## What Not To Trust By Default

- Old gate docs.
- Guarantee certificates.
- Receipts without mode/path/readback.
- Mock tests as live proof.
- Browser-use public-site demos as owner Chrome proof.
- API Calendar/Gmail proof as browser-only proof.
- Screenshots without independent readback.
- Raw card JSON that includes private user/browser data.

## What To Preserve

- The source-of-truth doc.
- Whiteboard images in this audit folder.
- Raw receipts, but redacted/summarized before sharing.
- Commit hashes and environment modes for every proof.
- Distinction between:
  - code exists
  - route works
  - live arm works
  - product path works

## Memory Architecture Note

For Anticipy itself, "remember everything" must not mean "store everything forever." Use a lifecycle:

1. Capture raw signal.
2. Extract candidate facts/tasks.
3. Classify sensitivity and purpose.
4. Store only needed raw data for a short retention window.
5. Store durable derived memory with source links and confidence.
6. Archive or delete stale raw data.
7. Let user inspect, correct, and delete memory.
8. Redact receipts before using them as proof.

This matches NIST/FTC-style privacy lifecycle practice and the product need for trust.

