# Baby Steps Plan

This plan follows the whiteboard instruction: build the UI, make the flow exist, then wire/build around it. Do not add more hidden plumbing until the user path forces it.

## North Star

A normal person can go to hosted Anticipy, sign up, install/pair the helper, let Anticipy read their world, get a warm call, approve the operating contract, then land on a clean board with:

- Welcome / status.
- Upload MP3.
- Listen.
- Active tasks.
- Memory/settings.

The first real proof is not "all features complete." It is one honest end-to-end product path:

`welcome -> sign in -> helper ready -> Layer 1 read -> Call 1 -> Layer 2 read -> Call 2 -> final confirm -> board -> input -> browser prepare -> approval -> proof -> memory -> follow-up`

## Step 0. Freeze The Truth

Goal:
- Stop context loss and stop old docs from steering work.

Do:
- Treat `ANTICIPY_SOURCE_OF_TRUTH.md` and this audit folder as current.
- Demote `Gate N green`, guarantee certificates, and old wakeup docs to history unless backed by raw receipt.
- Add/maintain `EVIDENCE_LEDGER.md`.

Done when:
- A new agent can read this folder and know what is real, what is demo, and what to build next.

## Step 1. Pick One Front Door

Goal:
- One consumer path starts the product.

Recommended choice:
- Use the better product shell from `web/onboard.html` or `/welcome`, but do not keep both as equal front doors.

Do:
- First screen: "Hi, I am Anticipy. I will listen, learn your day, and ask before anything important."
- One primary button: `Start`.
- If signed out, ask for email/login.
- Show human setup checklist:
  - Browser helper ready.
  - I can read your signed-in accounts.
  - I can call/text you.
  - I am learning your world.

Avoid:
- `127.0.0.1`
- engine
- owner token
- Railway
- Supabase
- Twilio
- API
- memory ledger
- developer mode
- repo clone

Done when:
- A normal user can start without seeing implementation words.

## Step 2. Pick One Board

Goal:
- One place where Anticipy works after onboarding.

Decision:
- Static board is cleaner.
- Next board is more wired.
- Pick one as product and demote the other to internal/demo until merged.

Do:
- Board must show:
  - Listen.
  - Upload MP3.
  - Type/paste.
  - Active tasks.
  - Pending approvals.
  - Memory/settings.
  - What Anticipy is doing right now.

Done when:
- Every post-onboarding flow lands on the same board.

## Step 3. Build The Onboarding State Machine In UI

Goal:
- Make the flow exist visibly before more backend work.

States:
1. Signed out.
2. Signed in.
3. Browser helper ready.
4. Permissions/sign-in to accounts.
5. Layer 1 reading.
6. Call 1.
7. Layer 2 reading.
8. Call 2.
9. Optional Layer 3.
10. Final confirmation call.
11. Board ready.

Do:
- Stub call states first with real UI copy.
- Show "I am reading your world" and "I will call you now" states.
- Keep the state machine durable in local/backend state, not just React state.

Done when:
- The UI can walk the entire source-of-truth onboarding flow even if some backend states are mocked/labeled as pending.

## Step 4. Fix Extension Packaging And Pairing

Goal:
- One extension source, one packaged helper, no Desktop drift.

Do:
- Regenerate `public/anticipy-chrome-extension.zip` from current `extension/`.
- Include `content.js`.
- Update manifest host permissions for product domains.
- Make loaded extension source traceable to repo commit.
- Bind extension socket to signed-in user/device, not default global core.

Done when:
- Consumer setup uses the same extension source as development and runtime.

## Step 5. Consolidate Browser Runtime

Goal:
- One product browser hand.

Do:
- Make extension/WebVoyager the canonical user-account runtime.
- Route `/api/browser/run` and owner-card browser tasks through the same engine state machine.
- Keep browser-use/throwaway browser only for isolated research or tests, never as product proof.
- Add final executor safety in extension:
  - refuse pay/checkout/final submit/send/delete/share/permission/credential actions unless the engine passes a fresh confirmation token scoped to that action.
- Replace Amazon demo recipes with labeled adapters or remove them from product path.

Done when:
- Every real browser action has the same safety/proof semantics.

## Step 6. Wire Existing Endpoints Into Onboarding

Goal:
- Use current plumbing inside the visible state machine.

Do:
- Layer 1 uses `/onboard/scan` and discovery.
- Deep reads use `/onboard/deep-read-hand` and `/onboard/deep-scrape`.
- Calls use `/voice` or `/cr`.
- Completion writes the final operating contract into memory.

Done when:
- Onboarding produces a profile with people, role/context, tools/systems, open loops, style, rules, do-not-touch list, autonomy dial, and open questions.

## Step 7. Memory Lifecycle Before More Capture

Goal:
- Make "record every part of life" safe enough to scale.

Do:
- Define memory classes:
  - Raw audio/transcript.
  - Extracted task.
  - Person profile.
  - System/account map.
  - Open loop.
  - Derived preference.
  - Sensitive artifact.
  - Browser proof/receipt.
  - Cache.
  - Archive.
- For each class define:
  - why keep it
  - default retention
  - redaction
  - user visibility
  - deletion path
  - model-use policy
  - evidence/source link

Done when:
- Memory UI can show what Anticipy knows and why, and the backend can delete/archive/redact by class.

## Step 8. Voice/Text Two-Way Loop

Goal:
- Warm check-ins actually control work.

Do:
- Enable inbound replies in a controlled way.
- Route YES/NO/clarification into pending asks.
- Add call states to onboarding.
- Add transcript summaries to memory.

Done when:
- A user can answer a text/call and the board/task state changes correctly.

## Step 9. One Real Acceptance Scenario

Goal:
- Prove the product loop, not plumbing.

Use controlled dummy logged-in apps first:
- Dummy Gmail.
- Dummy calendar.
- Dummy commerce/order page.
- Dummy docs/drive.

Scenario:
1. User says a messy real-world instruction with one vent and one real task.
2. Anticipy ignores the vent.
3. Anticipy reads relevant account data through the extension.
4. Anticipy prepares work.
5. Anticipy asks warmly before risky action.
6. User approves.
7. Anticipy executes or parks at final review.
8. Independent readback proves result.
9. Memory updates.
10. Follow-up fires later.

Done when:
- The receipt is product-path, live-extension, durable, independently read, and redacted.

## Step 10. Then Build The Remaining Plumbing

Only after the above:
- Better browser research/adapters.
- Cloud per-user browser runtime or secure device tunnel.
- Mobile/pendant integration.
- More skills/tool discovery.
- More SaaS/account coverage.
- Long-running autonomous task manager.
- Five-day owner test.

## Non-Negotiables

- No "Gate green" language.
- No fake done.
- No public/demo/browser-use proof treated as owner Chrome proof.
- No hardcoded consumer path.
- No raw sensitive receipts in docs.
- No irreversible action without point-of-risk confirmation.
- No more equal frontends.

