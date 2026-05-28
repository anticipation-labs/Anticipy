# V7 Decline Kill Summary

Author: agent (Opus 4.7)
Date: 2026-05-26
Directive: Omar's "never decline anything" rule. Re-route every competent-decline template through the universal ActionDispatcher OR an ask_user confirm-card surface. Money / irreversibility carve-out: pause for confirmation, never flat-decline.

## Counts

- Total decline templates found: **6**
- Rewritten in place in unfrozen files: **6** (100%)
- Patches written for frozen paths: **0**
- Money / irreversibility carve-outs preserved: **3** (ecommerce admin, ecommerce cart prep, CRM external-comms)

## What was rewritten in place

All six declines lived in one unfrozen file: `engine/app/product/server.py`.

1. `_unsupported_canvas_decline` (line ~2682). Canva / Figma / Adobe Express edits.
2. `_unsafe_ecommerce_decline` (line ~2755), admin branch. Refunds, labels, customer mail on Shopify / Etsy / ShipStation.
3. `_unsafe_ecommerce_decline` cart-prep branch (line ~2862). Cart fill, checkout, payment on retail surfaces.
4. `_unsupported_crm_saas_write_decline` (line ~2891). Salesforce / HubSpot / Notion / Jira writes.
5. `_unsupported_native_calendar_reminder_decline` (line ~3108). Native macOS Calendar / Reminders.
6. `act` endpoint pending-decline fallback (line ~5554). The end-of-line safety hatch in POST /api/act.

`_apply_competent_decline` (line ~3001) was also rewritten: it now ALWAYS dispatches via the new universal ActionDispatcher and never sets outcome=DECLINED at attempt time. The decline / competent_decline flags only ever flip when a user later answers no on a surfaced confirm card.

## Infrastructure added

- `_IRREVERSIBLE_VERB_TRIGGERS` and `_IRREVERSIBLE_INTENT_KINDS`: data tables.
- `_intent_requires_confirm(intent_kind, instruction) -> bool`: routing classifier.
- `_ask_user_plan_from_template(template, instruction) -> dict`: converts a legacy decline template into an ask_user / act plan (mode is never "decline").
- `_dispatch_via_universal_runtime(instruction, plan, rec) -> dict | None`: calls `app.product.action_dispatcher.ActionDispatcher().execute(...)` with account_id and device_id resolved from env / session. Returns the DispatchOutcome dict, or None on import / call failure so the caller can fall back to surfacing an ask_user pending (still not a flat-decline).

## Frozen-path findings (no patches needed)

- `engine/app/anticipy/proactive_engine.py`: contains a REFUSE branch for sarcasm / retraction / third-party-recap. That is a "user didn't actually want it" classification, not a decline of a real intent. Out of scope.
- `engine/app/action_engine/*.py`: only "cannot" mentions are in comments. No decline templates.
- `engine/app/proactive_day/*.py`: same. No decline templates.

Result: zero frozen-path patches required.

## Non-decline findings (informational)

- `src/lib/intent-prompt.ts`: contains LLM-prompt instructions teaching the extractor to skip delegations / pleasantries / aspirations. Those are extraction-time filters, not user-facing decline templates. Not a decline. No rewrite.
- `src/app/api/engine/analyze/route.ts` and `confirm/route.ts`: only auth / rate-limit / validation responses. No decline templates.

## Money carve-out risk assessment

The carve-out behaves like this:

1. Any intent whose kind is in `_IRREVERSIBLE_INTENT_KINDS` (purchase, payment, refund, send_external_email, etc.) is dispatched but the plan carries `require_confirm=True`.
2. Any instruction string that contains an irreversible verb (`buy`, `purchase`, `pay`, `transfer`, `refund`, `wire`, `venmo`, `zelle`, `checkout`, `place order`, `send to`, `send email to`, `publish`, `post to`, `delete`, `cancel subscription`, etc.) also trips `require_confirm=True`.
3. The dispatcher itself, via `app.product.confirm_card.needs_confirmation()`, owns the canonical risk classification with finer rules (finance-surface URL, do-not-touch scoped memory, money_amount thresholds). The verb / kind triggers in this file are a defense-in-depth shortcut at the listen-loop boundary.
4. When `require_confirm=True`, the plan is surfaced on `_LISTEN["pending"]` with `mode="ask_user"` and a generated `confirm_card_id`. The user yes-flow proceeds; the no-flow is the ONLY place that flips `decline=True`.

## The ONE risk I am most worried about

If `app.product.action_dispatcher.ActionDispatcher` throws or returns an outcome with `status` outside the four it documents (`success | ask_user | notify | in_progress`), my fallback treats unknown statuses as ASKING (defensive). That is correct for the never-decline goal, but it means an internal dispatcher bug becomes a silent permanent "asking" loop the user has to click through every time. I would rather have a noisy dispatcher than a silent one. A follow-up is to add a metrics counter on the unknown-status branch so the operator sees the dispatcher returning malformed outcomes and can fix the root cause instead of always paying the per-utterance ask-tax.
