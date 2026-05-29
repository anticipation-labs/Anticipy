# Confidence ladder: silent / notify / confirm / refuse

Owner: confidence-ladder thread, planning sprint of 2026-05-29. Design doc, not a shipped spec.

## 1. What the engine does today

Decision surface lives in two files that don't know about each other:

- `engine/app/product/risk_assessor.py:185` exposes `assess(intent, binding, memory_context) -> RiskAssessment`. Returns `silent | notify | confirm | ask`. No `refuse` mode per the never-decline directive (docstring lines 1-8); `ask` is the closest, routes to a confirm card.
- `engine/app/product/confirm_card.py:242` exposes `needs_confirmation(...)` and `build_confirm_card(...)`. Binary "card or no card." This is what the dispatcher actually keys off of.
- `engine/app/safety.py:104` is the deterministic floor: `ALWAYS_BLOCKED` and `ALWAYS_CONFIRM` keyword tables, `check_needs_confirmation()` (line 281) is a substring match.

Rules in `risk_assessor.assess()` (lines 186-244): do_not_touch -> `high/ask`; money verb or $ amount -> `high/confirm`; missing slots -> `medium/ask`; irreversibility >= 0.7 -> `high/confirm`; third-party email with external recipient -> `medium/notify` or `confirm` if `relationship_sensitive`; irreversibility 0.3-0.7 -> `medium/confirm`; default -> `low/silent`.

Hardcoded: verb tables (`risk_assessor.py:17-38`), irreversibility weights (lines 157-171: `send=0.7`, `publish=0.8`, `delete=1.0`, `draft=0.0`), the 0.7 and 0.3 thresholds, `ALWAYS_BLOCKED` and `ALWAYS_CONFIRM` (`safety.py:34-143`), `FINANCE_HOST_HINTS` (`confirm_card.py:36-42`).

Learned: only `scoped_memory.is_do_not_touch()` (`scoped_memory.py:290`), reading per-account `KIND_DO_NOT_TOUCH` items from `~/.anticipy/v7/memory/<account_id>/<device_id>/memory.jsonl`. `memory_context.relationship_sensitive` (`risk_assessor.py:231`) is read but nothing writes it.

Net: one fixed table for every user plus an opt-out list. No outcome feedback, no per-user adjustment.

## 2. Proposed 4-class taxonomy

Rename internal state to match user-facing language. Today `ask` means "show a confirm card" in code and "ask me a question" in UX, which is bad.

| Class | Meaning | Reversal |
|---|---|---|
| `silent` | Does it, no notification unless asked. Daily digest only. | 60 s undo for mutable-artifact actions. |
| `notify` | Does it, 1-line ambient notification with undo. | 5 min for third-party actions. |
| `confirm` | Stages, sends a confirm card, executes on tap. Double-tap variant for high-stakes. | n/a. |
| `refuse` | Refuses. Hands the action back with a deeplink to the prefilled surface. | n/a. |

`refuse` is new. Today the engine normalizes any leaked `decline` to `ask` (`risk_assessor_endpoints.py:58-62`). Money transfers, trades, and password entry land here. The redirect is the affordance: open Robinhood prefilled, do not press Submit. Matches MEMORY.md ("no money movement") and `safety.py:55-72`.

16 spanning examples:

1. Trivia ("when did the Roman empire fall") -> **silent**. Earbud + lock-screen.
2. Gmail draft to coworker, no Send -> **silent**. Reversible. Covered by `_is_safe_draft()` at `confirm_card.py:235`.
3. Gmail send to internal coworker on a thread user already authored -> **notify** after calibration. 5-min undo.
4. Gmail send to external client, first-time recipient ("email Sarah the quote") -> **confirm**.
5. Legal motion filing ("file the response to the MSJ") -> **confirm with double-tap**. Two taps in 3 s. Motion, e-file destination, and case number shown.
6. Epic lab order ("order a CBC for the next patient") -> **confirm with double-tap**. Order set and patient name shown.
7. Stock trade ("buy 100 AAPL") -> **refuse**. Open Robinhood prefilled. Already in `safety.py:69-72` `ALWAYS_BLOCKED`.
8. Money transfer between user's own accounts -> **refuse**. Same redirect.
9. Calendar reschedule, no conflict -> **silent**. Ambient toast.
10. Calendar reschedule that conflicts with another meeting on user's calendar -> **notify**. Action runs, notification surfaces the collision.
11. Calendar reschedule that triggers a meeting-update email to attendees -> **confirm**. Like Gmail-to-client.
12. OpenTable booking, 2-top -> **notify**. 5-min undo.
13. OpenTable booking requiring a credit-card hold -> **confirm**. Card holds treated as financial.
14. CRM activity log -> **silent**. Reversible, internal-only.
15. DocuSign sales quote to client -> **confirm**. Outbound + binding + financial.
16. Construction subcontractor message -> **notify** first, **silent** after 4 weeks of clean calibration.

Rules for picking a class, highest-precedence first:

1. **Refuse table** (new). Action that (a) types a password, (b) presses Submit on a money transfer, (c) places a market/limit order, (d) signs the user's legal name. From `safety.ALWAYS_BLOCKED` plus a new `REFUSE_VERBS` set. Not user-overridable.
2. **Confirm with double-tap**. `risk_class in {medical, legal, financial_irreversible}` where surface is in a new `HIGH_STAKES_SURFACES` table (Epic, Athena, Cerner, NetDocuments, Clio, MyCase, court e-filing portals, `*.gov`, `*.uscourts.gov`).
3. **Confirm**. (a) Sends to an external recipient where user has not calibrated this recipient class to silent/notify, or (b) irreversibility >= 0.7 on a binding surface, or (c) parsed money > 0 below refuse threshold.
4. **Notify**. Touches a third party, reversible inside the 5-min window, and user has calibrated this surface/recipient class to "notify or below."
5. **Silent**. Default for reversible self-only actions.

Class boundary lives in a new `confidence_classifier.py` that wraps `risk_assessor.assess()` and adds the per-user adjustments in section 3.

## 3. Per-user calibration

Three observed signals, each cheap to capture:

- **Reversal**: did the user invoke "undo last 60 s" within N minutes of a silent/notify action? Recorded as `KIND_ACTION_OUTCOME` (kind exists at `scoped_memory.py:30`) with `extra={"outcome": "reversed", "delta_ms": ...}`.
- **Edit-before-send**: for a draft promoted from `silent` to `confirm` where the user opened and edited before sending, record the diff. Small diff: silent draft calibrated. Large diff: demote back to "draft + notify."
- **Manual redo**: did the user redo the same action themselves the long way within 24 h (same surface, recipient class, verb)? Strong negative signal.

Storage uses the existing `scoped_memory` JSONL at `~/.anticipy/v7/memory/<account_id>/<device_id>/memory.jsonl`. New kinds: `KIND_CALIBRATION` (per-surface-per-recipient-class score) and reuse `KIND_ACTION_OUTCOME` for raw events. Local-only.

Math is intentionally boring. Each (surface, recipient_class, verb) tuple carries a running confidence score in [0.0, 1.0]. Reversal: -0.25. No reversal in 24 h: +0.05. Large edit before send: -0.15. Manual redo: -0.40. Clamp. Cross 0.75 upward: drop one rung (confirm -> notify -> silent). Cross 0.40 downward: climb one rung. Hysteresis prevents flapping.

Recipient class is the key per-user concept. We learn `sarah@acme.com` is "client," `jenny@anticipationlabs.com` is "coworker," `mom@gmail.com` is "family." Resolution lives in `person_resolver.py`. Calibration keys off the class, so the user does not have to recalibrate per coworker.

Example: in week 1, every "send email to internal coworker" is `confirm`. After 5 clean sends the score climbs past 0.75 and drops to `notify`. After 20 more clean sends, it drops to `silent`. User did nothing explicit. One reversal crashes the score back to `notify` for the next 5.

## 4. Week 1 vs week 2 vs week 4 dial

Until calibration takes, a global multiplier biased by observed action count for the account.

| Week | Actions | Default for ambiguous | Forced to confirm regardless |
|---|---|---|---|
| 1 | 0-30 | `confirm` for anything touching a third party, modifying an external surface, or containing money. `silent` only for drafts and queries. | Every send, booking, irreversible mutation. |
| 2 | 30-150 | `notify` for low-risk external touches (CRM log, calendar move on own calendar with no conflict). `confirm` for sends. | Sends, bookings > $50, all medical/legal/financial. |
| 4+ | 150+ | Per-user calibration from section 3 takes over. | Refuse class always. Double-tap class always. |

"Week" is a count of observed actions, not a calendar week. A heavy user might hit week 4 in 4 calendar days. Avoids "I bought it Monday, only used it twice, why is it silent on Tuesday."

The first-week pattern is deliberately high-friction. The user is teaching Anticipy by pressing the green button 30 times; each press is a data point. Frame in onboarding: "the first week feels chatty because I'm learning your preferences. I get out of your way fast."

## 5. Reversal window

Silent actions need a rescue rope. Per surface:

- **Gmail draft**: saves the draft; reversal deletes it. Always available. /app shows "Last 60 s: drafted reply to Sarah. Tap to delete."
- **Gmail send**: when promoted to silent, set Gmail's "Undo Send" to 30 s during onboarding and hook into that window. Past 30 s, reversal becomes "send a retraction." Make explicit at promotion.
- **Calendar create/move**: snapshot the event JSON before mutating; reversal posts it back. Window 5 min.
- **OpenTable / Resy booking**: cancel the booking. Window: until the restaurant's own no-fee cancel window closes. Deadline surfaced in the toast.
- **CRM activity log**: delete the log entry within 5 min.
- **Calendar accept/decline of someone else's invite**: send the opposite response within 5 min.

Reversal lives in a new `ReversalLog` JSONL, one entry per reversible action with `expires_at`, `surface`, `revert_recipe` (primitives), and a 1-line summary. Phone shows the most recent 3; tapping runs the revert recipe through the dispatcher at `action_dispatcher.py:84`.

Hard rule: every silent action must produce a `ReversalLog` entry. If no revert recipe exists, the action is not eligible for silent. The classifier enforces this.

## 6. Cross-class transactions

"Schedule the appointment AND send the patient the confirmation" decomposes into:

1. Create calendar event (silent).
2. Send confirmation email to patient (confirm in week 1; notify after calibration).

Boundary rule: **each primitive evaluated independently; if any is `confirm` or `refuse`, the whole transaction goes to `confirm` as one bundle.** The card shows both steps. Approve runs both. Deny runs none.

Partial-failure semantics: if step 1 (silent) ran first and step 2 (confirm) is denied, the engine offers reversal for step 1 in the same response ("created the appointment but you said no to the confirmation; want me to delete the appointment?"). User can accept reversal, accept partial state, or do step 2 themselves.

If any primitive is `refuse`, the whole transaction is `refuse` and we redirect to the prefilled surface for the refused step. Prior steps do not auto-run; we wait.

For "A silent + B notify," the whole thing runs and the notification is the louder of the two. No double-notify; batch into one ambient toast.

## 7. Open problems

- **Per-recipient class resolver.** `person_resolver.py` does name-to-person, not person-to-class. Need a `PersonClassifier` that observes salutations, signatures, frequency, domain and assigns {family, coworker, client, vendor, opposing_counsel, patient, unknown}.
- **Reversal recipes for vendor surfaces.** OpenTable has a cancel button; not every booking surface does. Need a recipe library and a "not reversible -> not eligible for silent" gate. Maybe 30-40 surfaces matter day 1.
- **The cautious user.** Some users prefer `confirm` everywhere forever. Need account-level `risk_appetite in {cautious, default, fast}`. Cautious never drops below `notify`; fast drops faster but never on refuse-class.
- **Cross-device calibration.** Storage is per `(account_id, device_id)` (`scoped_memory.py:8`). When the user has both the pendant and the mini-PC, calibration should sync. Per the scale-not-local directive we cannot use a server today; need a local pairing protocol.
- **"Didn't reverse but unhappy" signals.** Reversal is strong negative; absence of reversal is weak positive. Might need explicit thumbs-down on the action card, or a weekly digest "any of these 14 silent actions you'd have rather I checked first?"
- **First-bad-action weighting.** A single botched send to a client is catastrophic; ten flawless drafts are not catastrophic gains. A "first 10 reversals count 2x" rule might be enough.
- **Double-tap UX on pendant.** Pendant has one button. Double-tap is feasible, but visual confirmation lives on the phone. If the phone is across the room the user double-taps blind. Likely rule: double-tap on pendant only permitted when phone is paired-and-screen-on in last 10 s.
- **Recovery from a wrong calibration.** If we wrongly demote "send to client X" to silent and the user fixes the damage manually (apology email), we want to detect the apology pattern and snap calibration back to confirm. Non-trivial event classification, and the most user-trust-load-bearing problem in this doc.

Estimated build: 1.5 weeks for classifier + reversal log + 30 surface recipes, then multi-month calibration in the wild. Section 4's week-1 dial is the safety net.
