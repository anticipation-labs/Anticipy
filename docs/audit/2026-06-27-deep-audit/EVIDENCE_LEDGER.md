# Evidence Ledger

This replaces "Gate N green" language.

## Verdict Labels

- `LIVE_PRODUCT_PROVEN`: real user-facing product path, live systems, durable result, independent readback.
- `LIVE_ARM_PROVEN`: external arm works live, but not necessarily through product path.
- `INTEGRATION_PROVEN`: route/component works in controlled or mock environment.
- `DETERMINISTIC_CONTRACT`: unit/eval/harness proves a behavioral rule.
- `CODE_ONLY`: implementation exists but has no trustworthy receipt.
- `BLOCKED`: known blocker remains.
- `FAILED`: receipt shows failure.
- `RETIRED`: misleading, stale, or no longer part of product proof.

## Required Receipt Fields

Every new proof should include:

- Date/time.
- Commit.
- Capability.
- Product claim.
- Invocation path:
  - UI
  - API
  - script
  - direct function
- Runtime mode:
  - model provider
  - hands mode
  - browser runtime
  - channels mode
  - data dir
- User/device identity.
- External system touched.
- Human involvement.
- Result.
- Independent readback.
- Durable artifact path.
- Sensitive data redaction status.
- What it does not prove.
- Expiry.
- Verdict.

## Current Capability Ledger

| Capability | Current best evidence | Verdict | What it does not prove |
| --- | --- | --- | --- |
| Engine health | `/health` returned ok on local engine | `INTEGRATION_PROVEN` | Product flow |
| Live engine status | `/status` showed extension connected, Twilio live-ready, pending approvals, proactive armed | `LIVE_ARM_PROVEN` | Full owner task completion |
| Extension connection | `/ws/state` returned connected; log shows `/ws/extension` accepted | `LIVE_ARM_PROVEN` | Safe horizontal browser work |
| Repo vs loaded extension | `diff -ru extension Desktop/0-ANTICIPY-EXTENSION-LOAD-ME` empty | `INTEGRATION_PROVEN` | Future drift prevention |
| Static board | `web/app.js` calls real owner/card/resolve endpoints | `INTEGRATION_PROVEN` | Canonical clean product flow |
| Next board | `app/page.js` exposes richer owner app features | `INTEGRATION_PROVEN` | Clean consumer UX |
| Onboarding shell | `web/onboard.js` calls scan/loop/complete routes | `INTEGRATION_PROVEN` | Source-of-truth scrape-call loop |
| Browser hand | Extension observe/act plus WebVoyager exists and local socket is connected | `LIVE_ARM_PROVEN` | Production-safe, per-user, generic task execution |
| Amazon return demo | Live card proof exists, but with hardcoded recipe and sensitive browser proof | `LIVE_ARM_PROVEN` narrowly | Horizontal browser capability |
| API/Arcade | Readiness reports Google/Arcade live | `LIVE_ARM_PROVEN` | Browser-only product direction |
| Twilio outbound | Readiness reports text/call live-ready | `LIVE_ARM_PROVEN` | Inbound two-way check-in loop |
| Inbound SMS/call | Live status says inbound reply polling disabled | `BLOCKED` | Two-way approval loop |
| Memory store | History/open-loop/profile storage exists and live counts are present | `INTEGRATION_PROVEN` | Privacy-grade lifecycle |
| Proactive engine | ControlCore/core proactive routes and tick exist; proactive armed | `INTEGRATION_PROVEN` | Multi-day product autonomy |
| Owner stop | Next API route exists, engine route missing | `BLOCKED` | User can reliably stop work |
| Public extension zip | zip exists but stale/incomplete | `FAILED` | Consumer install path |
| Guarantee docs | claims exceed receipts | `RETIRED` | Finish-line proof |

## Proof Levels To Use Going Forward

Level 1: code exists.

Level 2: deterministic unit/harness proves a rule.

Level 3: local integration path works with controlled dependencies.

Level 4: live external arm works, but not through canonical product path.

Level 5: canonical product path works with live external system and independent readback.

Level 6: repeated owner-day proof over time with no operator handholding.

The next meaningful target is Level 5 for one controlled full loop, then Level 6 for multi-day owner use.

