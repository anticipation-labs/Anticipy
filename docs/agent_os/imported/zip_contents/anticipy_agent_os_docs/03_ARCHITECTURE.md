# 03 — Architecture

## One sentence

Anticipy is a local-first proactive assistant that hears messy life, builds memory, infers intent, prepares safe work through API/browser/voice arms, parks irreversible steps for approval, and proves outcomes with independent read-back.

## System map

```text
Inputs
  ├─ live mic / device
  ├─ MP3/audio upload
  ├─ pasted transcript
  ├─ SMS/text/images
  ├─ browser context
  ├─ email/calendar/CRM context
  └─ onboarding scrape

Core
  ├─ speaker/context resolver
  ├─ memory store
  ├─ intent detector
  ├─ vent/sarcasm guard
  ├─ prepare/park planner
  ├─ harm-line / press-go policy
  └─ receipt verifier

Hands
  ├─ API arm: Gmail, Calendar, Outlook, CRM, Slack, legal/accounting tools
  ├─ browser arm: browser-use + user Chrome/CDP/extension bridge
  └─ voice/text arm: call/SMS/clarification/approval

Product shell
  ├─ Vercel website/download page
  ├─ Anticipy Execute desktop app
  ├─ Chrome extension/native bridge
  └─ review/approval UI
```

## Onboarding architecture

Onboarding is not a form. It is how Anticipy learns the person.

Steps:

1. User opens app.
2. App explains what it will inspect and why.
3. User connects Chrome extension/local bridge.
4. User authorizes major accounts.
5. Browser read-only scan discovers logged-in services and public/profile context.
6. API mesh discovers available direct integrations.
7. Profile builder writes:
   - people,
   - companies,
   - apps,
   - calendars,
   - inbox patterns,
   - recurring obligations,
   - preferences,
   - tone/style,
   - safety boundaries,
   - uncertainty list.
8. Clarification call or chat asks only for missing high-value facts.
9. Profile facts are source-backed and confidence-scored.

Onboarding must not become a scrape rabbit hole. Minimum viable onboarding is enough context to run the first real owner day.

## Memory architecture

Use multiple memory lanes, not one blob.

1. **Profile memory:** stable facts about the user.
2. **People memory:** family, coworkers, clients, vendors, patients, etc.
3. **Commitment memory:** things said or promised.
4. **Open-loop memory:** actionable items with deadlines/status.
5. **Inert remembered list:** generous capture that never triggers.
6. **Receipts memory:** artifacts proving done.
7. **Failure memory:** patterns that previously broke the system.

Important distinction:

- **Remembered** does not mean “trigger later.”
- **Open loop** can trigger only if it passed stricter criteria.
- **Parked prep** means “work prepared, waiting for approval.”

## Intent/action architecture

The runtime loop:

```text
hear → normalize → speaker/context resolve → memory recall → classify
    → if vent/joke/sarcasm: silent or inert remember
    → if clear harmless task: prepare automatically
    → if uncertain task: prepare if reversible, park silently for review
    → if irreversible/risky/money/legal/medical: ask or block
    → read-back → receipt → human summary
```

## API arm

API arm should be preferred for reliable work:

- Gmail draft creation.
- Calendar holds/events.
- CRM notes/tasks.
- Slack drafts/messages if authorized.
- Document generation.
- Accounting/legal tool preparation where APIs exist.

Every API write must run a second independent read. The write response is not proof.

## Browser arm

Use browser arm for what APIs cannot do:

- Amazon returns.
- Web forms.
- CRM screens without an API.
- Logged-in web apps.
- Research pages.
- Shopping carts.

Browser action policy:

1. Read freely where authorized.
2. Prepare reversible state.
3. Stop before submit/send/pay/buy/delete/file.
4. Take screenshot + DOM receipt.
5. Summarize in human language.

## Voice/text arm

Voice/text is for closure:

- “I prepared the return; approval needed.”
- “The calendar hold is ready.”
- “I need one clarification.”
- “I’ll call you at 2:45.”

Voice/text is not the product core. It is a delivery arm.

## Product app shell

Recommended:

- Next.js on Vercel for web/download front door.
- Tauri for native macOS app unless current repo is already Electron-dominant.
- Native Messaging / local websocket/HTTP bridge for Chrome extension ↔ desktop app.
- Sidecar services for engine, browser-use bridge, transcription worker.

## Security and privacy architecture

This is not a micro detail; it is a product boundary. But it should be built as infrastructure, not as endless discussion.

Rules:

- No secrets printed.
- User logs into accounts themselves.
- Tokens stored encrypted per user.
- Browser page text is untrusted data, never policy authority.
- Webpage prompt injection cannot authorize actions.
- Money/payment is hard stop.
- Legal/medical final advice/filing is high-risk and parks for human approval.
- Destructive actions require explicit approval.

## Scaling architecture

For one owner, local-first is fine.

For many users:

- Local app handles browser and sensitive local context.
- Cloud handles account, orchestration, model routing, sync, deploy, receipts, and observability.
- Per-user tools are capability-scoped.
- Agent runs are logged as receipts, not opaque chat.
