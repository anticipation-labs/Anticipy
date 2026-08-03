# Chrome Web Store — Anticipy listing package

Status: PREPARED, NOT SUBMITTED. Omar approves the wording, then it's one
upload at https://chrome.google.com/webstore/devconsole ($5 one-time fee,
review typically 1–3 days; expect extra scrutiny for the `debugger`
permission — the justifications below are written for that reviewer).

## Name
Anticipy — your hands on the computer

## Summary (132 chars max)
Anticipy does real work in your own logged-in Chrome — and always asks
before anything consequential is sent.

## Description
Anticipy is a personal assistant that listens to your day, remembers what
matters, and quietly handles the follow-through. This extension is her
hands: when you approve a task from the Anticipy app or by text, she opens
the pages, fills the forms, and reports honestly on what happened — inside
your own browser, with your own logged-in accounts, never with your
passwords.

- Pairs to YOUR phone with a 6-digit code; only your tasks run here.
- Every consequential action (sending, booking, buying) waits for your
  explicit OK first.
- Stops at logins, CAPTCHAs, and payment fields — it never fills passwords
  or card numbers.
- Everything it does is visible: it works in a tab group you can watch.

Requires the Anticipy app (TestFlight) and an Anticipy account.

## Category
Productivity / Tools

## Permission justifications (reviewer form)
- `debugger`: Anticipy performs trusted user-gesture clicks and typing on
  pages the user asked it to operate (e.g. filling a reservation form).
  CDP input events are the only reliable way to interact with modern
  event-delegated UIs. Used only during a user-approved task, detached
  immediately after.
- `tabs`/`tabGroups`: tasks open in a labelled "Anticipy" tab group so the
  user can watch and take over at any moment.
- `scripting`: reads page structure (a numbered element map) so the
  assistant can decide what to click; injects no third-party code.
- `storage`: stores the pairing identity and configuration locally.
- `alarms`: polls the user's own job queue while paired.
- `notifications`: tells the user when a task finishes or needs them.
- `<all_urls>`: tasks are open-ended user requests ("book a table at…");
  the destination cannot be known in advance. Sensitive categories
  (banking, passwords, payments) are refused in code.

## Privacy disclosures (data-use form)
- Collects: none sold, none shared with third parties. Page text from the
  active task tab is sent to the AI model chosen by the user's own account
  to decide the next step; task results go to the user's own Anticipy
  backend. No analytics, no ads, no tracking.
- Privacy policy URL: https://backend-production-61e0a.up.railway.app/privacy.html
  (needs to be created before submission).

## Assets still needed before submission
- Screenshots: 1280×800, 3–5 of the popup, a task running in a tab group,
  and the pairing flow.
- The privacy.html page above.
- A promo tile (440×280) if we want featuring.
