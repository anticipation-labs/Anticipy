# W2A clarify-reflex fix notes

## Problem (W2A)

W2A scored 16 of 20 plans as `mode=clarify` asking "Which email address
should I use?" even when Maya / Devon / James and other dossier people
had emails on file. The planner was reflex-clarifying instead of
consulting the active dossier.

## Trace

The reflex lives in `engine/app/product/server.py`, the `emailish`
branch of `_finalize_plan`. When the model returned
`mode=act, intent=email_draft, person=""`, `_draft_task_from_plan` ran
`_email_from_memory` against the legacy memory anchors only. The V7
`DossierLoader.people()` was never consulted. With no match,
`_finalize_plan` returned the canned `"Which email address should I
use?"` clarify, even though the dossier had the answer.

## Heuristic (the assertion the unit test will pin)

For any `emailish` plan (intent in `{email_draft, gmail_draft, email}`
or instruction matching the action-verb regex):

1. If `_draft_task_from_plan` already resolves an email anywhere
   (`plan["person"]` includes an `@`, the onboarding profile.people
   map has the email, or `_email_from_memory` returns a single match):
   proceed with `mode=act`.
2. ELSE consult the active dossier via
   `_resolve_person_from_active_dossier(instruction)`. The lookup is
   deterministic (single full / first / last / alias match against
   `DossierLoader.people()` for the current account). If a single
   match is found:
      - fill `plan["person"]` with the canonical name
      - re-run `_draft_task_from_plan`
      - return `mode=act` with the substantive task.
3. ELSE (the dossier doesn't have the person) check whether a clear
   recipient name is present in the instruction itself via
   `_extract_named_recipient`. If yes, return `mode=act` with a
   substantive task that says "Open Gmail, search for [name], draft
   an email about [thing]" plus the `missing_slots=["recipient_email"]`
   flag so the Confirm card surfaces the missing email for review.
4. ONLY when none of (1)-(3) applies do we fall through to the
   original clarify: `"Did you mean A or B?"` if `_email_from_memory`
   returned 2+ candidates, otherwise the canned "Which email address
   should I use?".

## Unit-style assertions (to be folded into a real test once the engine
has a pytest harness for the planner; the harness is currently missing
which is why we're documenting here)

Given the rich test dossier (Maya, Devon, Priya, James, Liang, Sara,
Tomas, Hannah, Andre, Jules):

- `_finalize_plan("draft a follow-up for Maya about Friday", {"mode":
  "act", "intent": "email_draft", "person": "", "thing": "Friday digest",
  "task": ""})` returns `mode=act` with `person="Maya Chen"` and a
  non-empty `task`.
- `_finalize_plan("Devon asked for the invoice numbers", {"mode":
  "act", "intent": "email_draft", "person": "", "thing": "invoice
  numbers", "task": ""})` returns `mode=act` with `person="Devon Park"`.
- `_finalize_plan("send Elena a maybe for the lunch", {"mode": "act",
  "intent": "email_draft", "person": "", "thing": "lunch maybe-RSVP",
  "task": ""})` returns `mode=act` with `person="Elena"`,
  `missing_slots=["recipient_email"]`, and a substantive `task` that
  mentions searching Gmail for Elena. (Elena is NOT in the dossier;
  the named-recipient fallback covers her.)
- `_finalize_plan("I owe her a reply on the slide deck", {...})`
  returns the original clarify because there is no name in the
  transcript and no single-match in the dossier.

## Why this is the right shape

The brief's principle: clarify is only for when the answer is truly
absent and unrecoverable. Reflex-asking "Which email address?" when
the dossier already has the answer is a worse user experience than
acting on the dossier-resolved email and surfacing a Confirm card. The
fallback path (named recipient lifted from the instruction but no
email in the dossier) is also strictly better than reflex-clarifying
because the user can correct the recipient on the Confirm card without
ever having to type "use maya@studiozero.ca" into a dialog.

## Files touched

- `engine/app/product/server.py`: `_resolve_person_from_active_dossier`
  (new), `_extract_named_recipient` (new),
  `_NAMED_RECIPIENT_BLOCKERS` (new), `_finalize_plan` `emailish`
  branch (modified to consult dossier before clarify, and to emit
  act-mode substantive task when the recipient is in-text but not in
  dossier).
</content>
</invoke>