# Deep Bug Hunt — Concurrency / Idempotency / Race Conditions

Class of bug to find: SELECT-then-INSERT/UPDATE without atomic guards;
notification fan-out without idempotency keys; dedupe checks that drop on
slight wording differences; auth bypass paths; queries that don't filter
by user_id.

The user's prior incident: `/api/engine/analyze` periodic + final fired
in parallel, both inserted, two emails went out.

What follows is every issue the audit turned up, classified by severity.

---

## BLOCKERS (active production hazards)

### 1. handleConfirmedIntent in extension/background.js: read-then-write race
**File:** `/workspaces/Anticipy/extension/background.js:285-295`

```js
const dedupKey = `executed_${intent.id}`;
const stored = await chrome.storage.local.get(dedupKey);   //   read
if (stored[dedupKey]) return;
await chrome.storage.local.set({ [dedupKey]: true });      //  write
```

**Repro:** the SW joins TWO Realtime channels (`anticipy_db` postgres_changes
and `anticipy-intents` broadcast) and a single confirm flips the row AND
broadcasts. Both arrive in the SW within a few ms of each other. Both
pass the `chrome.storage.local.get` check (storage hasn't been written
yet), both call `await chrome.storage.local.set(...)`, and both spin up
a `BrowserAgent` instance. Two agents now race for the same task on the
same tab. Visible symptom: the agent does each step twice, blowing up
on the second click. Even if the page tolerates double-clicks, the user
sees garbled progress messages and the cost doubles.

**Suggested fix (generic):** use `chrome.storage.local`'s atomic semantics —
`chrome.storage` doesn't have CAS, so use a single in-memory `Set`
keyed by `intent.id` AND a `chrome.storage.local.get` for cross-restart
durability. Add the in-memory entry FIRST, fail fast on second arrival
within the same SW lifetime. (Implemented below.)

---

### 2. dedupe_key generated column drops on wording variation
**File:** schema; `anticipy_intents.dedupe_key` is a generated column
`lower(action_type) || ':' || left(lower(summary_for_user), 80)`.

**Repro:** the LLM emits "Email John about Tuesday's meeting" on the periodic
call, then "Send email to John regarding the meeting" on the final call.
Different summaries → different dedupe_keys → unique constraint never
fires → two rows insert → two emails go out. THE EXACT BUG THE USER
REPORTED IS NOT FULLY FIXED — the constraint only catches identical
wording, not the LLM's natural rewording.

**Suggested fix (generic):** add a per-session in-process advisory lock
on `(session_id)` to serialize concurrent /analyze calls — the second
call's fuzzy `isDuplicateOfExisting` check then sees the first's intents
and skips them. Implemented via a Postgres advisory lock in /analyze
below — generic, no per-action keyword tables, works for every future
race in the same shape.

---

### 3. recordPreferenceSignal runs twice on every yes/no
**File:** `/workspaces/Anticipy/src/app/api/engine/confirm/route.ts:101-113`,
`/workspaces/Anticipy/src/app/api/engine/auto-proceed/route.ts:113-121`,
`/workspaces/Anticipy/src/lib/preference-record.ts`

**Repro:** confirm path issues atomic UPDATE that wins → records preference
signal "accept". Auto-proceed timeout fires .5s later (race), atomic
UPDATE returns 0 rows so it short-circuits — but the client also called
/auto-proceed with a different intent in parallel, and that path also
calls `recordPreferenceSignal`. Multiple sources can call this fn on the
same intent: confirm, auto-proceed, sms-reply, voice-callback. Each
fires a Gemini call AND inserts a row.

**Suggested fix (generic):** dedupe on `(user_id, intent_id, signal)`
in `anticipy_preferences` via a UNIQUE constraint. Implemented below.

---

### 4. anticipy_memory accumulates duplicate (user_id, kind, key) rows
**File:** `/workspaces/Anticipy/src/app/api/engine/analyze/route.ts:286-318`

**Repro:** every periodic /analyze (every 30s during recording) re-extracts
the same context. `recallRelevantMemory` dedupes ON READ, but the table
keeps growing — confirmed in production: `(user_id, "speaker_location_vancouver")`
has 8 rows. With heavy users this scales to thousands of duplicate rows
and inflates prompt-side recall queries.

**Suggested fix (generic):** add UNIQUE on (user_id, kind, key) and
upgrade insert to `upsert` on the same target. Implemented below.

---

## MAJOR (likely to recur, fix needed)

### 5. anticipy_actions has no idempotency key
**File:** schema; `anticipy_actions(intent_id, status, result, ...)` has no
unique constraint involving `intent_id`.

**Repro:** confirm/sms-reply/voice-callback/auto-proceed all do
`INSERT INTO anticipy_actions` after a successful flip. The single-flip
guard prevents duplicates today — but if the flip succeeds and the
INSERT fails partway, retry creates two action rows for one execution.
Or if executeAction has its own retry, doubles up on the actions row.

**Suggested fix (generic):** UNIQUE on `(intent_id, status)` is too
restrictive. Instead enforce that `intent_id` appears at most once with
status='success'. Use a partial index. Implemented below.

### 6. recordPreferenceSignal swallows `error.code = 23505` silently
**File:** `/workspaces/Anticipy/src/lib/preference-record.ts:140-145`

After fix #3 above, the UNIQUE constraint will start raising 23505 on
the second insert. The current code logs a warning and continues — fine,
but it's worth treating 23505 explicitly so it doesn't show up in the
warn log every time.

### 7. /api/engine/analyze still allows isFinal+session.status='ended' by mid-recording
**File:** `/workspaces/Anticipy/src/app/api/engine/analyze/route.ts:89-94`

If the periodic call (isFinal=false) is in flight when stopRecording marks
the session ended, the in-flight call still completes and inserts. Then
the final call (isFinal=true) sees session.status='ended' and 409s. The
LLM's last analysis (which had MORE transcript) is lost.

Not a bug — but the user might be surprised that the final analysis got
shadowed. Worth a follow-up: queue the final call until in-flight
periodic finishes, or at least merge their output.

### 8. Realtime broadcast fan-out can dispatch the same intent twice per client
**File:** `/workspaces/Anticipy/extension/background.js:194-216`

The SW listens to BOTH `postgres_changes INSERT/UPDATE on anticipy_intents`
AND `broadcast.event=new_intent`. Insert path also broadcasts (analyze
route line 502-525). For every intent the SW receives:
- 1× `postgres_changes INSERT` (RLS allowing) — calls handleNewIntent
- 1× `broadcast new_intent` — calls handleNewIntent again

The second call to handleNewIntent calls `chrome.notifications.create`
with the same `intent.id` as notification id, and chrome COALESCES into
one — so no duplicate notification visible. BUT: `lastActions` array
gets the same entry pushed twice, and `chrome.action.setBadgeText` shows
2× the count.

**Suggested fix (generic):** dedupe on `intent.id` in handleNewIntent the
same way handleConfirmedIntent should — Set + chrome.storage.local
fallback. Implemented below.

### 9. /api/engine/auto-proceed — dual race with /confirm
**File:** `/workspaces/Anticipy/src/app/api/engine/auto-proceed/route.ts`

Both confirm and auto-proceed correctly use atomic conditional UPDATE.
HOWEVER: their preference-recording calls happen UNCONDITIONALLY after
the UPDATE. If two paths both UPDATE simultaneously, one wins the
status flip (correct) but BOTH still call `recordPreferenceSignal` —
because the atomic UPDATE check is for status, not for who-calls-record.
The losing path bails after `updated.length === 0` — looking again:
auto-proceed line 103-109 correctly returns BEFORE recording. So this
particular race is OK. But confirm line 101-113 records preference
unconditionally for every successful UPDATE. If the user clicks Yes
TWICE rapidly, the first wins UPDATE, records preference. Second loses
UPDATE (line 49 returns "handled"), so it does NOT record. Good. False
alarm here — but Note: the `intentRow` SELECT at line 76 happens AFTER
the UPDATE. Theoretically `intentRow` could be null if FK or row
disappeared between UPDATE and SELECT. Logged as MINOR below.

---

## MINOR (code quality, not user-impacting today)

### 10. confirm: optional fetch of `intentRow` after UPDATE without re-checking ownership
**File:** `/workspaces/Anticipy/src/app/api/engine/confirm/route.ts:76-95`

The GET endpoint has NO auth guard at all (intentionally — email/SMS link
clicks). It only verifies ownership via `prefUserId` for preference
recording, but `executeAction(intentRow)` runs regardless. Since the
intentId is a UUID and the link is mailed to the user, this is "secure
through unguessable URLs". If a UUID leaked (forwarded email), the recipient
can confirm/reject the intent. Probably fine for v1; flag for v2 to add a
short-lived signed token or HMAC to confirm URLs.

### 11. transcribe route: no rate limit, no per-session row cap
**File:** `/workspaces/Anticipy/src/app/api/engine/transcribe/route.ts`

A loop of clients spamming the JSON path with 10k segments each will fill
the table fast. There IS a `MAX_SEGMENTS_PER_REQUEST = 10_000` but no
session-total cap. With 50 sessions per user and 10k per call, a single
user can insert 500k transcript rows in one minute.

**Suggested fix (generic):** rate-limit by `user_id` at the route level.
Existing `rate-limit.ts` is unused on this route.

### 12. /confirm GET endpoint has no rate limit
**File:** `/workspaces/Anticipy/src/app/api/engine/confirm/route.ts`

Anyone with the URL can hammer it. Atomic UPDATE prevents double-execute
but still costs a Gemini call (preference reasoning) per request. Easy DoS.

### 13. memory-recall returns first 200 rows by recency only
**File:** `/workspaces/Anticipy/src/lib/memory-recall.ts:42-44`

If the table keeps growing (it has — see bug #4), recall pulls only the
most-recent 200, so OLDER memory items get permanently invisible. Fix #4
(UNIQUE upsert) keeps the table small per user, which fixes this too.

### 14. SMS reply route: most-recent notification is fragile
**File:** `/workspaces/Anticipy/src/app/api/engine/twilio/sms-reply/route.ts:51-62`

If the user got SMS for two intents and replies "yes" to the first,
they'll confirm the SECOND because we only look at the most-recent.
Phone-number-based correlation is broken once two intents are pending.

**Suggested fix (generic):** require the user reply with `YES <intent-id-prefix>` —
out of scope for this bug hunt, flag for future.

### 15. Realtime reconnect doesn't deduplicate replayed intents
**File:** `/workspaces/Anticipy/extension/background.js:228-234`

If WS drops and reconnects, postgres_changes does NOT replay (Realtime
v2 only delivers new events), but if the join sequence is wonky, the
extension MIGHT see an INSERT it already saw. handleNewIntent would
push a duplicate. Same fix as #8.

### 16. preference signal is fire-and-forget but caller doesn't await
**File:** `/workspaces/Anticipy/src/app/api/engine/confirm/route.ts:104-113`

`void recordPreferenceSignal(...)` — fine for performance but if the
function throws AFTER the await, Vercel kills the lambda before the
preference row is written. Since it's `void`, the route returns 200
before the insert resolves. Not a bug today, but if a user does many
yes/no clicks and the lambda recycles aggressively, some preferences
silently drop.

### 17. /analyze cross-session memory query joins all user sessions
**File:** `/workspaces/Anticipy/src/app/api/engine/analyze/route.ts:131-158`

Pulls ALL user sessions in last 72h (cap 50), then `.in("session_id", allSessionIds)`.
For a heavy user with 50 sessions × 50 intents each, this is fine. For
1000 sessions, the IN clause balloons. Easy to fix later with a JOIN view.

### 18. Engine page subscription leaks `seenFollowUpsRef` / `seenCheckInsRef` across tab refreshes
**File:** `/workspaces/Anticipy/src/app/engine/page.tsx:375, 430`

Refs reset on full reload, so refreshing the page mid-session re-surfaces
follow-up cards the user already dismissed. UX nit.

### 19. handleConfirmedIntent removes dedup key on auth failure
**File:** `/workspaces/Anticipy/extension/background.js:312`

```js
await chrome.storage.local.remove(dedupKey);
```

On the OTHER hand, after the agent ACTUALLY fails (network, timeout), the
key is NOT removed — the user can never retry. Should remove on actual
agent failure, not just on auth failure. Logged for follow-up.

### 20. Engine page CHECKIN_WINDOW_MS auto-resolve fires every 500ms
**File:** `/workspaces/Anticipy/src/app/engine/page.tsx:1437`

If multiple check-ins are pending, EVERY tick scans them all. With 100
pending check-ins (extreme case), that's 200 scans/sec. Fine today, but
worth converting to per-checkin setTimeout when scaling.

---

## DATA-LEAK / AUTH

No critical leaks found:
- /analyze, /transcribe, /session, /auto-proceed all gate on `requireSupabaseUser` AND ownership-check.
- /confirm GET intentionally has no auth — relies on unguessable UUID. Acceptable for v1.
- /sms-reply, /voice-callback, /voice-script all verify Twilio HMAC.
- recallRelevantMemory + recallUserPreferences both filter by `user_id` strictly.
- Realtime subscriptions on engine page filter client-side to only intents originated this tab.

## SUMMARY

5 BLOCKER/MAJOR bugs in production today:
1. handleConfirmedIntent TOCTOU race
2. dedupe_key generated column doesn't catch wording variation (the user's bug NOT fully fixed)
3. recordPreferenceSignal duplicates on yes-yes / yes-auto race
4. anticipy_memory accumulates dupes
5. anticipy_actions has no uniqueness key

Generic fixes applied:
- DB constraints (UNIQUE) at insert sites
- Per-session advisory lock for /analyze concurrent calls
- handleConfirmedIntent / handleNewIntent dedupe Set in SW

Test added: `engine/test_concurrency.py` proves each is fixed.
