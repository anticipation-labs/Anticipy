# Reuse Map

The rebuild should reuse existing pieces instead of starting over.

## Keep And Reuse

### Next app

Use as canonical product foundation:

- `app/layout.js`
- `app/page.js`
- `app/welcome/page.js`
- `app/onboarding/page.js`
- `app/connect/page.js`
- `app/download/page.js`
- `app/api/*`

Reason:
- Next already owns app routing and API proxies.
- It is the better place for a hosted app.

### Static web design

Use as design/reference source:

- `web/index.html`
- `web/styles.css`
- `web/onboard.html`
- `web/onboard.css`
- `web/app.html`
- `web/app.css`

Reason:
- Static `web/` has the cleaner mood and first-run feel.
- It should inform visual tone and copy.

### Static web behavior

Reuse selectively:

- `web/app.js`
- `web/onboard.js`
- `web/auth.js`
- `web/auth-screen.js`

Reason:
- These files contain useful endpoint knowledge and human copy, but should not remain a separate canonical frontend.

### Engine endpoints

Wire into new UI:

- `/health`
- `/status`
- `/readiness`
- `/owner/cards`
- `/owner/ingest`
- `/owner/ingest-file`
- `/pending`
- `/resolve`
- `/owner/autonomy_mode`
- `/onboard/permissions`
- `/onboard/scan`
- `/onboard/deep-read-hand`
- `/onboard/deep-scrape`
- `/onboard/loop`
- `/onboard/status`
- `/onboard/complete`
- `/listen/start`
- `/listen/stop`
- `/listen/status`
- `/listen/stream`
- `/voice`
- `/cr`
- `/ws/state`

### Proactive engine

Use as canonical product spine:

- `engine/anticipy_engine/core/proactive.py`
- `engine/anticipy_engine/core/control_core.py`
- `engine/anticipy_engine/proactive/triage.py`
- `engine/anticipy_engine/proactive/decider.py`
- `engine/anticipy_engine/proactive/harm.py`
- `engine/anticipy_engine/main.py`

Do not treat `engine/anticipy_engine/proactive/engine.py` as the product engine; it is a stub shell.

Use older V7 / `.anticipy` proactive code only as contract and eval source material:

- `/Users/omarebrahim/.anticipy/engine/app/proactive/types.py`
- `/Users/omarebrahim/.anticipy/engine/app/proactive/engine.py`
- `/Users/omarebrahim/.anticipy/engine/app/proactive/eval/*`
- `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/proactive/*`

Reason:
- The current repo has the safer running spine and is already wired to FastAPI and the UI.
- V7 has better typed streaming contracts and broader eval concepts.
- Whole-copy replacement would reintroduce duplicate systems and may regress the current money wall.

Detailed map:

- `PROACTIVE_ENGINE_REUSE_PLAN.md`

### Extension

Reuse:

- `extension/background.js`
- `extension/content.js`
- `extension/popup.js`
- `extension/manifest.json`

Needed changes later:

- Package from repo source.
- Remove stale public zip.
- Bind user/device identity.
- Add final executor safety.
- Update product host permissions.

### Existing UI logic worth preserving

From `app/page.js`:

- card grouping
- card humanization
- upload route usage
- listen stream route usage
- browser-tab microphone streaming state
- live transcript segment handling
- `ingest_result` application after active listening
- pending ask handling
- owner cards refresh

From `web/app.js`:

- clean board interaction model
- autonomy dial feel
- simpler product copy
- older active-listening copy and permission fallback ideas

From `web/onboard.js`:

- layer visual language
- onboarding progress shell
- complete-state handling

## Replace Or Demote

### Demote

- `app/onboarding/page.js` current technical setup page
- `app/connect/page.js` provider checklist page
- current `/download` developer-style setup page

These can become internal/admin/debug views or be redesigned into human setup states.

### Replace

- Public extension zip if stale.
- Any consumer copy that mentions ports, repo clone, owner token, Railway, Supabase, Twilio, API, memory ledger, or developer mode.
- Split frontend state where `web/` and `app/` both act like product frontends.

### Keep As Internal Only

- Raw readiness JSON.
- Engine mode.
- Hands mode.
- Channel mode.
- Provider names.
- Receipt/debug links.

## New Files To Create In First Implementation

Recommended first UI lab files:

- `app/plan-baby-steps/page.js`
- `app/plan-baby-steps/components/AppShell.js`
- `app/plan-baby-steps/components/SignFlow.js`
- `app/plan-baby-steps/components/OnboardingFlow.js`
- `app/plan-baby-steps/components/ActiveListeningPanel.js`
- `app/plan-baby-steps/components/TranscriptReview.js`
- `app/plan-baby-steps/components/Board.js`
- `app/plan-baby-steps/components/TaskDetail.js`
- `app/plan-baby-steps/components/TextMirrorStatus.js`
- `app/plan-baby-steps/components/MemoryView.js`
- `app/plan-baby-steps/components/SettingsView.js`
- `app/plan-baby-steps/data/seed.js`
- `app/plan-baby-steps/data/source-fixtures.js`
- `app/plan-baby-steps/lib/contracts.js`
- `app/plan-baby-steps/lib/sourceAnchors.js`
- `app/plan-baby-steps/styles.css`

Keep it side-by-side until reviewed.

Recommended backend/helper files for the same first implementation:

- `lib/supabase/client.js`
- `lib/supabase/server.js`
- `app/auth/confirm/route.js`
- `app/api/profile/route.js`
- `app/api/settings/route.js`
- `app/api/onboarding/state/route.js`
- `app/api/listen/status/route.js`
- `app/api/listen/start/route.js`
- `app/api/listen/stop/route.js`
- `app/api/tasks/comments/route.js`

If any of these collide with existing routes, adapt the name but keep the contract: auth, profile, settings, onboarding state, listen status/control, comments.

## Wiring Order

1. Seeded state and source-use-case fixtures.
2. Supabase auth and route protection.
3. Profile/settings/onboarding-state persistence.
4. Read-only engine/listen/extension status.
5. Read-only cards.
6. Type/paste create card.
7. Upload MP3/audio/transcript create card.
8. Browser-tab active listening create card.
9. Local Mac mic start/stop/status.
10. Approval resolve.
11. Task comments/sort preferences.
12. Onboarding scan/loop.
13. Browser progress/proof.
14. Memory/settings writes.
15. Text mirror live wiring.

## Do Not Reuse As Product Proof

- Old gate docs.
- Old guarantee certificates.
- Browser-use demo receipts.
- Public-site browser tasks.
- Raw card JSON with private proof.
- Mock/stub test output as live UI proof.
- A first-screen screenshot as proof that browser work is done.
- A transcript segment as proof that a task was acted on.
