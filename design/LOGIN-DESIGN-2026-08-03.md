> ## ⚠️ DO NOT EXECUTE THE PLAN BELOW AS WRITTEN
>
> An adversarial review (appended at the end) built a real PocketBase 0.30.4 rig
> from this repo's own binary and RAN the plan's own migration and rule strings.
> Three findings are blocking. Read the review first; the plan's *shape* held up
> under attack, but three of its concrete artifacts are wrong:
>
> 1. **The central rule string is wrong and fails SILENTLY.** The plan uses
>    `owner_ref = @request.auth.account`, but the `owners` collection it defines
>    has no `account` field. PocketBase accepts the rule with HTTP 200, resolves
>    it to empty, and the phone's feed returns zero rows — with no error, no log,
>    and all four of the plan's own gates reading green. Use the `||` form
>    (`owner_ref = @request.auth.id || owner_ref = @request.auth.account`), which
>    was measured working for phone, laptop and worker simultaneously.
> 2. **Stage 7 cannot bootstrap the first account.** `createRule: null` plus
>    `passwordAuth: disabled` means no client can create the account, and
>    `request-otp` for a non-existent record returns HTTP 200 while creating
>    nothing. There is also NO mail transport in the image, so an emailed code
>    can never arrive. Sign in with Apple must come first, or the row is minted
>    server-side before login ships.
> 3. **Stage 1 can brick pairing fleet-wide.** The `paired = false` condition must
>    be a server-side record check AFTER the lookup, never a filter-string
>    requirement — the clients send `pair_code="NNNNNN"` and nothing else. Both
>    guard branches must be anchored regexes, not string equality.
>
> The structural lesson, which matters more than any single fix: **every gate in
> this plan verifies DATA, and none verifies BEHAVIOUR.** Each rule flip needs a
> read-back assertion with a real phone token and a real device token, asserting
> a nonzero and correct row count, with immediate rollback if either returns 0.

# Anticipy — the login/auth boundary, as a staged migration that never breaks the running product

*Written against the repo at `/Users/omarebrahim/Anticipy-pendant`, branch `pendant-system`, PocketBase 0.30.4 (`backend/Dockerfile:3`). Everything below traces to a file:line or to the verified research. Read-only: nothing was modified, deployed, or run against production.*

---

## 1. What we have and what we're missing

Anticipy has data that clearly belongs to a person — his transcripts, his errands, his phone number, his birthday — but the backend has no concept of a person at all: `owner` is a plain text column holding a UUID the phone invents for itself on first launch (`app/ios/Anticipy/AnticipyApp.swift:102`), and the only lock on the door is a single shared password sent as a header, checked in one JavaScript file (`backend/pb_hooks/guard.pb.js:29`), while every collection's rules are wide open (`backend/pb_migrations/1700000000_anticipy.js:19-23` and the identical block in every other migration).

**Today the phone cannot read its own data until a Chrome extension is paired on a computer, because the only credential is a shared token handed out by `/agent/key`** — the phone literally waits for a browser to exist before it can fetch the key that lets it read the owner's own feed (`AnticipyApp.swift:248-255` → `AnticipyBackend.swift:127-137` → `backend/pb_hooks/agent_key.pb.js:50`), and that same endpoint hands the same master token, the OpenRouter billing key, and the owner's name, email, phone and birthday to anyone who can name a paired `agent_id` (`agent_key.pb.js:13,18,34-51`).

What's missing is one thing with three consequences: there is no account, so nothing can be scoped to a person, nothing can be deleted for a person, and no second person can ever exist — and the collection that matters most, `events`, doesn't even have a column to say whose words those were (`1700000000_anticipy.js:27-43`; the later additive migration `1700000004_segments.js:45-53` adds eight fields and still no owner).

---

## 2. The recommended design

**In one sentence:** a person becomes a row in a real PocketBase auth collection called `owners`; the phone logs into it directly; every other device (the Chrome extension, and later the pendant) gets its *own* separate machine credential that is bound to that person by the phone; and the Python brain runs on a long-lived superuser token that bypasses rules entirely.

### The identity: an `owners` auth collection

**What it means for a person:** "you" stops being a random number stored only on one phone and becomes an account that survives losing the phone, that you can log into from a new device, and that can be deleted.

Concretely, a new migration `backend/pb_migrations/1700000008_owners.js`, in exactly the shape this repo already uses (`new Collection({...})` + `app.save(...)`, as at `1700000000_anticipy.js:7-25`), with `type: "auth"` and the 0.30.x option blocks:

```js
new Collection({
  type: "auth",
  name: "owners",
  fields: [
    { name: "email", type: "email", required: false },   // overrides PB's required-by-default email
    { name: "phone", type: "text", required: false },    // E.164, verified later
    { name: "legacy_uuid", type: "text", required: false },
    { name: "created", type: "autodate", onCreate: true },
    { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
  ],
  indexes: [
    'CREATE UNIQUE INDEX idx_owners_phone ON owners (phone) WHERE phone != ""',
    'CREATE UNIQUE INDEX idx_owners_legacy ON owners (legacy_uuid) WHERE legacy_uuid != ""',
  ],
  passwordAuth: { enabled: false },
  otp: { enabled: true },
  authRule: "",                       // "" = any record may authenticate; null = nobody can
  listRule: "id = @request.auth.id",
  viewRule: "id = @request.auth.id",
  createRule: null,                   // only the server mints accounts
  updateRule: "id = @request.auth.id",
  deleteRule: null,
})
```

Three details that a plan written from older PocketBase knowledge gets wrong and that matter here: the auth options are **top-level keys, not nested under `options`**; `username` is no longer a built-in field, so any identity field you want must be declared yourself with a single-column UNIQUE index; and `created`/`updated` are ordinary `autodate` fields you declare — exactly as this repo already does at `1700000003_owner_profile.js:15-16`.

### How a person logs in on the phone: Sign in with Apple, with PocketBase's built-in email one-time code as the recovery lane

**What it means for a person:** one tap on the iPhone. No password to invent, no password to forget, no six-digit text message to wait for.

- Primary: `POST /api/collections/owners/auth-with-oauth2` with the Apple provider. Response is the same for every auth endpoint: `{"token": "<jwt>", "record": {...}}`.
- Recovery / second device: `POST /api/collections/owners/request-otp` → `{"otpId": ...}`, then `POST /api/collections/owners/auth-with-otp` with `{otpId, password}`. This is native to 0.30.4, needs no external provider, and is the thing we can prove end-to-end on the local rig before Apple is even configured.
- `passwordAuth: { enabled: false }` — there is no password anywhere in the system.

**Why not the alternatives:**

- **Email + password.** Rejected. It adds a secret to steal and a reset-email channel to phish, on a product where the first-run friction lands before any value has been demonstrated. Keep email as a recovery attribute, never as a primary credential.
- **SMS / phone-number OTP as the login.** Rejected as a *credential*, kept as a *routing address*. NIST SP 800-63B-4 (final, July 2025) makes PSTN out-of-band verification a **restricted authenticator** (§3.1.3.3) and puts four affirmative duties on anyone shipping it (§3.2.9): offer a non-restricted alternative, give meaningful notice, document the risk, hold a migration plan. That is the floor for ordinary data; this payload is continuous ambient audio of the owner *and of bystanders who never consented*. The quieter argument is stronger than SIM-swap: US carriers may reassign a disconnected number after 45 days, so if the phone number is the account key, a stranger who inherits Omar's recycled number inherits the transcript of his life. And PocketBase's OTP is email-native anyway — `recordRequestOTP` looks the user up with `FindAuthRecordByEmail` and delivers via the mailer; there is no SMS transport in PocketBase, so an SMS OTP means writing delivery code in `pb_hooks` — the exact place that has taken production down twice.
- **Passkeys.** The right destination, wrong first step. PocketBase 0.30.4 has no WebAuthn; you would be writing a relying party from scratch in `pb_hooks`. Revisit once the `owners` collection exists — adding a second login method to an existing auth collection is additive by then.

**The phone keeps the number, but demotes it.** `owners.phone` becomes a verified-once routing address with a UNIQUE index, not a credential. That is what finally lets `backend/pb_hooks/sms.pb.js:17-19` stop deciding who the owner is from an environment variable and start deciding it from data — today a second person who onboards through the app is authorised by the worker (`brain/worker.py:42-56`) and silently dropped by the hook, because the hook only knows `ANTICIPY_OWNER_PHONE`.

### How the Chrome extension becomes the same user without a second login

**What it means for a person:** you never sign in on your laptop. You install the extension, it shows a code, you type the code into your phone once, and the laptop is yours — and you can un-link that one laptop later without logging anything else out.

This is a device-pairing ceremony, which is what `agents` already is (`1700000002_agents.js:10-30`, `extension/background.js:39-59`). The shape is right; what's wrong is that the ceremony currently hands over the *shared master token* (`agent_key.pb.js:50`). Two changes:

1. **A second auth collection, `devices`** (one row per browser install), with `account` = a relation to `owners`, and `authToken: { duration: 2592000 }` (30 days) since the extension heartbeats every 10 seconds (`background.js:98-116`) and can refresh trivially.
2. **Two new routes in a new hook file** — deliberately *not* in `guard.pb.js`:
   - `POST /agent/register` — unauthenticated by necessity (a fresh install has no credential), creates an **unowned** `devices` record with a short-lived single-use pair code and returns `{device_id, pair_code, token}`. The extension is authenticated from second one, but its token opens nothing except its own row.
   - `POST /agent/claim` — called by the **phone**, carrying the phone's own `Authorization` token plus the code. The hook looks the device up server-side (hook DAO calls bypass collection rules), checks it is unbound and the code unexpired, and sets `devices.account`.

Because the lookup happens inside the hook, the pair code never has to be listable by anyone — which closes the enumeration that is live in production today (`HANDOFF.md:44-49`, and the substring-`.test()` regexes at `guard.pb.js:55,59`).

Every data rule then reads the same for a phone token and a laptop token, because both resolve through one field:

```
@request.auth.id != "" && owner_ref = @request.auth.account
```

where `owners.account` is the record's own id and `devices.account` is its owner's id. One rule string, no per-client branching, no `OR` clause.

### How the Python worker keeps full-access read/write

**What it means for a person:** nothing. The brain keeps working through every single stage, unchanged in behaviour.

Use a **`_superusers` impersonate token** — PocketBase's own documented substitute for API keys:

```
POST /api/collections/_superusers/impersonate/{superuserRecordId}
Authorization: <a superuser auth token>
{"duration": 31536000}
```

→ a static, non-refreshable JWT with a caller-chosen lifetime. Store it in Railway as `ANTICIPY_PB_JWT` and add it in one place: `brain/pb.py:17-19`, alongside the header it already sends. Superusers bypass collection rules entirely (`apis/record_crud.go` guards every branch on `!requestInfo.HasSuperuserAuth()`), so the worker sails through every rule flip with zero rule surgery, and it already sails through the guard hook twice over — once at `guard.pb.js:29` because it keeps sending `X-Anticipy-Token`, once at `guard.pb.js:33` because `e.hasSuperuserAuth()` is true.

Two properties to plan around, both verified: the token is **not renewable** — since v0.29.0 you may call `/auth-refresh` with it, but the handler only mints a new token when the `refreshable` claim is true, otherwise it returns the same token unchanged, so `/auth-refresh` is a validity probe, not an extension. And revocation means changing that superuser's password or rotating the `_superusers` auth-token secret.

*Rejected alternative:* a non-superuser service account in `owners` with `|| @request.auth.id = "<id>"` added to six rule strings. More least-privilege, but it writes a literal record id into six schemas and gives the worker no path through the guard hook without still carrying the shared token. Not worth it for a single-tenant worker that legitimately needs to write on the owner's behalf.

---

## 3. What happens to Omar's existing data

**What it means for him:** he logs in once, and everything he already has — every errand, every profile field, every conversation segment, and his whole transcript history — is his account's, with nothing to re-enter and nothing lost.

His owner UUID `D2846190-381B-4AF8-8F15-3E5B986B5D5F` (the value appears in the repo at `proof/dry_run_his_reply.py:61`; the authoritative copy lives in `@AppStorage("ownerID")` on his phone, `AnticipyApp.swift:56`) is already stamped on:

| collection | column | written by |
|---|---|---|
| `jobs` | `owner` (`1700000002_agents.js:33`) | brain, `anticipy_core.py:492` |
| `segments` | `owner` (`1700000004_segments.js:17`) | brain, `segmenter.py:197` |
| `agents` | `owner` (`1700000002_agents.js:16`) | iOS, `AnticipyBackend.swift:175` |
| `pendants` | `owner` (`1700000000_anticipy.js:14`) | iOS, `AnticipyBackend.swift:151` |
| `owner_profile` | `owner_id` (`1700000003_owner_profile.js:12`) | iOS, `AnticipyBackend.swift:112` |

The conversion is three moves, none of which touches an existing column:

1. **A new nullable `owner_ref` column** (relation → `owners`, single, `cascadeDelete: false`) is added to each of those collections *and* to `events`. Purely additive, exactly like `1700000004_segments.js:44-60`.
2. **His first login creates the `owners` row** and writes `legacy_uuid = D2846190-…` onto it. This is the join key, recorded once, in data rather than in someone's head.
3. **One backfill**, run once by hand against a snapshot-then-production, with a superuser session: set `owner_ref` = his new record id on every row where `owner` (or `owner_id`) equals the legacy UUID **or is empty**. Empty counts because it is still his — `brain/worker.py:480-484` warns in as many words that an unset `ANTICIPY_OWNER_ID` produces jobs with no owner, and there is nobody else those could belong to.

The old `owner` text columns are left in place and dual-written for as long as it takes. Nothing reads `owner_ref` until stage 13. Reverting the whole thing is dropping a column nothing depends on.

### `events` is the hard one, and it is the reason for the ordering

`events` has no `owner` column and never had one (`1700000000_anticipy.js:27-43`). The only per-row identifier is `device_id`, and that is `"iphone-b36"` — **the build number, identical on every install of that build** (`AnticipyApp.swift:96`). The phone fetches the feed with no filter at all (`AnticipyBackend.swift:206-216`).

So: **his transcript history cannot be attributed by query.** It can only be attributed by *inference* — "there is exactly one human using this product, therefore every row is his." That inference is sound today and will never be sound again. Three things follow, and they are the spine of the plan:

- **The backfill has a deadline.** It must run before a second real account exists. After that, the unattributed rows are unattributable forever.
- **The inference must be verified, not assumed.** Before the blanket assignment, count the distinct non-empty values of `owner` across `jobs`, `segments`, `agents`, `pendants` and of `owner_id` across `owner_profile`. If that count is 1, assign all of `events` to him. If it is greater than 1, fall back to the partial correlation that does exist — `events.segment` (`1700000004_segments.js:53`) joins to `segments.owner` (`:17`) — attribute what joins, and leave the rest unattributed rather than guessing.
- **`events` is flipped last** (stage 13). Any owner-scoped rule on `events` written before the backfill completes would make his entire history invisible to his own phone, and would starve the brain's intake at `brain/worker.py:382` — the one read in the entire brain that raises on failure, and which reports the failure as "backend unreachable" (`worker.py:643`), a wrong diagnosis that sends whoever debugs it at the network instead of at auth.

---

## 4. The staged plan

Two structural rules hold across every stage:

**Rule A — widen before you narrow.** Every change that touches `guard.pb.js` is *strictly widening* (it adds a way in, never removes one) until the very last stage. Narrowings live in collection rules instead. This matters because of an asymmetry worth naming: **a rule can be reverted from the PocketBase dashboard in seconds with no deploy; a guard-hook change needs a redeploy to revert.** Put the risk where the undo is instant.

**Rule B — nothing narrows until the column it narrows on exists, is populated, and every client that touches it authenticates.** Enforced mechanically, not by discipline — see stage 3 and stage 13.

| # | Stage | Touches | Revert |
|---|---|---|---|
| 0 | Owner UUID → Keychain | iOS only | previous build |
| 1 | Close the anonymous path to the master token | `guard.pb.js` | one-line revert + deploy |
| 2 | `/agent/key` returns the *requesting* agent's owner | `agent_key.pb.js` | restore one line |
| 3 | The traffic ledger (the gate) | new hook file | delete the file |
| 4 | `owners` auth collection | new migration | `migrate down 1` |
| 5 | `owner_ref` columns, incl. on `events` | new migration | `migrate down 1` |
| 6 | Guard widening: accept a real auth token | `guard.pb.js` | delete one line |
| 7 | iOS login | iOS only | previous build |
| 8 | Adopt the legacy UUID + backfill | one-off script | restore `pb_data` snapshot |
| 9 | Clients stamp `owner_ref` | iOS, brain, hooks | previous build / env |
| 10 | Extension gets its own identity | new hook + migration + extension | keep old path alive |
| 11 | Worker gets a superuser token | `brain/pb.py` + env | unset env var |
| 12 | Fix the call sites that lie on denial | brain + extension | previous build |
| 13 | Flip rules, one collection at a time | one migration each | set rule back to `""` |
| 14 | Retire the shared token + tokenless exceptions | `guard.pb.js`, `agent_key.pb.js` | restore file |

---

### Stage 0 — His identity survives deleting the app

**For him:** delete Anticipy and reinstall it, and it's still him. Today it isn't — it's a brand-new stranger, and everything he had is orphaned with no key that reaches it.

- **Changes:** `AnticipyApp.swift:56,102` — read `ownerID` from the Keychain, falling back to the existing `@AppStorage` value and *copying* it up (never clearing the old one).
- **Verified before production:** simulator run; confirm the same UUID survives an app delete + reinstall; confirm a fresh install still mints one.
- **Rollback:** ship the previous build. Because we copy rather than move, the UserDefaults value is still there.
- **Why first:** stages 7-8 depend on that UUID still being findable. This is the cheapest highest-value item in the plan and it touches no backend at all.

### Stage 1 — An anonymous stranger can no longer walk out with the master key

**For him:** nothing changes visibly. What changes is that the live hole recorded in `HANDOFF.md:44-49` — an anonymous request returning all four agent rows including paired `agent_id`s, which `/agent/key` then trades for the service token, the OpenRouter key and his name/email/phone/birthday — is closed.

- **Changes:** `guard.pb.js:53-61`. Replace the two unanchored substring regexes with **exact whole-filter equality**, and cap `perPage`. This is safe *because the clients send exactly those strings and nothing else* — verified: `AnticipyBackend.swift:141` and `:166` build `pair_code="<6 digits>"`, `AnticipyBackend.swift:183` builds `owner="<uuid>"`. `?filter=pair_code="000000" || id!=""` stops matching; the two legitimate callers are untouched. Additionally require `paired = false` on the **pair-code branch only** — *not* on the owner branch at `:59`, which is how a paired phone finds its own already-paired agent (`AnticipyApp.swift:248`).
- **Verified before production:** local rig, curl matrix — the exact two client filters must return 200; six bypass variants must return 403; `perPage=500` must be capped.
- **Rollback:** revert the file, redeploy. Emergency: clearing `ANTICIPY_SERVICE_TOKEN` on Railway disables the whole guard live with no redeploy (`guard.pb.js:17-18` reads it per request) — that is the existing panic button and it survives until stage 13.
- **Ships alone.** This file has taken production down twice; it does not get batched with anything.

### Stage 2 — The browser stops being handed a stranger's identity

**For him:** nothing today, since he is the only user. It is a prerequisite: the moment a second `owner_profile` row exists, every paired browser receives whichever profile is first in the table and fills booking forms with that person's name, email, phone and birthday.

- **Changes:** `agent_key.pb.js:32` — replace `findFirstRecordByFilter("owner_profile", "id != ''", {})` with a lookup scoped to `rec.getString("owner")`. The join already exists in the schema (`1700000002_agents.js:16` ↔ `1700000003_owner_profile.js:12`); it is simply not used.
- **Verified before production:** local rig with two `owner_profile` rows and two paired agents — each must receive its own.
- **Rollback:** restore the line. Fails soft either way: if no profile matches, `owner` is `null` and the extension keeps its cached copy (`extension/background.js:307-311`).

### Stage 3 — The gate that makes the rest of this plan safe

**For him:** invisible. This is the instrument that tells us, from data rather than from confidence, when it is safe to lock a collection.

- **Changes:** a **new** hook file (leaving `guard.pb.js` untouched) registering its own `routerUse`. Because PocketBase's auth loader runs at priority −1020, well before `routerUse` handlers at priority 0, `e.auth` is already populated when our middleware runs — which is why `e.hasSuperuserAuth()` already works at `guard.pb.js:33`. For each guarded request the hook notes, once per collection per day per runtime, whether the caller had **any** resolvable identity. One row written the first time an anonymous request hits a collection on a given day; nothing after. Near-zero cost, and the only question it answers is the only one we need: *did anything touch this collection today without an identity?*
- **Verified before production:** local rig — anonymous request produces a row, authenticated request produces none, and a load loop confirms one row per collection per day, not one per request.
- **Rollback:** delete the file. It is read-only in effect; nothing depends on it.

### Stage 4 — Accounts exist (and nothing uses them yet)

- **Changes:** new migration `1700000008_owners.js`, the collection above. Nothing reads it, nothing writes it, no rule references it.
- **Verified before production:** apply against a **copy** of `backend/pb_data`, confirm the server boots; run `pocketbase migrate down 1`, confirm it boots again; apply against an empty dir for the clean-boot case.
- **Rollback:** `migrate down 1` — the down function is a single `app.delete(...)`.
- **Why it cannot break the live path:** it touches no existing collection and changes no rule.

### Stage 5 — Every row gains a place to record whose it is

- **Changes:** new migration adding nullable `owner_ref` (relation → `owners`) to `events`, `jobs`, `segments`, `agents`, `pendants`, `owner_profile`. Same additive-nullable pattern as `1700000004_segments.js:44-60`. **The existing `owner` text columns are not touched** — converting a live text column to a relation is the one genuinely dangerous migration available here, and we are not doing it.
- **Verified before production:** apply to a copy of `pb_data`; confirm every existing client request still succeeds unchanged; confirm that a write carrying a *bad* `owner_ref` is rejected with 400 rather than silently stored (this is the reason for choosing a relation over free text — junk fails loudly instead of quietly recreating today's un-attributable dataset); confirm the down function removes the fields and the server reboots.
- **Rollback:** `migrate down 1`.

### Stage 6 — The door learns to accept a real key

**For him:** nothing yet — no client has a real key. The instant one does, it works.

- **Changes:** `guard.pb.js`, one line added immediately after `:29`, in the same defensive style as the existing `:32-34`:
  ```js
  try { if (e.auth) return e.next(); } catch (_) {}
  ```
- **Strictly widening.** It cannot lock anyone out, which is precisely the failure mode that took production down twice.
- **Verified before production:** local rig — a request with a valid `owners` token and *no* `X-Anticipy-Token` must now pass; a request with neither must still 403; every existing client path must be byte-identical.
- **Rollback:** delete the line and redeploy.

### Stage 7 — He logs in on the phone

**For him:** one tap. And from this moment the phone stops needing a Chrome extension to exist before it can read his own feed — the answer to the sentence in §1.

- **Changes:** iOS only. A login screen; store the returned PB token in the Keychain; add `Authorization: <token>` in `AnticipyBackend.swift:58-68` and `:82-90` **alongside** the existing `X-Anticipy-Token` (there is no `Authorization` header anywhere in the app today — the only two in the codebase go to OpenRouter). Refresh on foreground via `POST /api/collections/owners/auth-refresh`, and treat **401 from refresh** as "log in again" — the reliable expiry probe, because an expired token is *silently ignored* by PocketBase's auth loader and the request continues as a guest, so a list read returns `200` with an empty `items` array, not a 401. Also: `authAlert.enabled` defaults true, so decide deliberately whether he wants an email on every reinstall.
- **Login is optional at this stage.** If it fails, the app behaves exactly as today. Nothing is gated on it.
- **Verified before production:** simulator pointed at the local rig via the Backend URL field that already exists at `SettingsView.swift:211` — no code change needed to test against localhost. Prove: login → token in Keychain → every read still works; kill the token → app recovers via refresh; expire the token → the 401-from-refresh path fires and not the empty-list path.
- **Rollback:** ship the previous build.
- **Sequencing note:** ship email-OTP login first (fully native, fully testable locally), then Sign in with Apple as a follow-up build. Apple's native flow uses the Bundle ID as `client_id` while a web flow needs a separate Service ID, and PocketBase tracks one `client_id` per provider — irrelevant here only because the extension never signs in with Apple. Verify the exact provider config on the rig before it goes near production.

### Stage 8 — His history becomes his account's

- **Changes:** on first successful login, PATCH `owners.legacy_uuid`. Then a one-off backfill script run with a superuser session: verify exactly one distinct owner exists across the five collections, then set `owner_ref` on every matching row, then blanket-assign `events` (with the segment-correlation fallback if the verification fails). No rules change, no client change.
- **Verified before production:** run the whole script against a copy of `pb_data` first; assert row counts before and after; assert zero rows left with an empty `owner_ref`; assert the phone's feed is byte-identical afterwards (nothing reads `owner_ref` yet, so it must be).
- **Rollback:** this is the only stage that is a *data write*. Snapshot the Railway volume immediately before; rollback is restoring the snapshot. Also keep a reverse script that nulls `owner_ref` where it equals his id — cheap, and it makes the rollback not depend on the snapshot.

### Stage 9 — New rows arrive already attributed

- **Changes:** stamp `owner_ref` on write — iOS `pushEvent` (`AnticipyBackend.swift:191-196`), `queueJob` (`:198-203`, which today writes no owner at all despite `jobs` having the column), `upsertOwner` (`:100-124`); brain `_queue_job` (`anticipy_core.py:492`), `SegmentStore.create` (`segmenter.py:197`), `post_event` (`worker.py:91`); and `sms.pb.js:21-28`, which today writes an `events` row with no owner and no source.
- **Additive:** the column is nullable, so any not-yet-updated client keeps working.
- **Verified before production:** local rig — every write path produces a row with a correct `owner_ref`; an old client's write still succeeds with it empty.
- **Rollback:** previous builds; the column stays and is simply not populated.

### Stage 10 — The laptop gets its own key

**For him:** unchanged pairing experience — code on screen, typed into the phone. What changes is that the laptop now holds a credential that is only the laptop's, and that he can revoke on its own.

- **Changes:** `devices` auth collection (migration); `/agent/register` and `/agent/claim` in a **new** hook file; `extension/background.js` prefers its device token and falls back to today's path. `/agent/key` keeps returning `service_token` for now — removing it is stage 14.
- **Verified before production:** local rig, full ceremony: register → code → claim from an authenticated phone token → device reads only its owner's rows; a second claim of the same code fails; an expired code fails; deleting the device row invalidates its token immediately.
- **Rollback:** the old registration path is still live and the extension still falls back to it; revert the extension build, and the new routes become dead code.

### Stage 11 — The brain gets a key that outranks the rules

- **Changes:** mint a `_superusers` impersonate token once (a live superuser call or the dashboard's Impersonate button — it cannot be created from a migration); store as `ANTICIPY_PB_JWT`; `brain/pb.py:17-19` adds `Authorization` when the env var is set, keeping `X-Anticipy-Token`.
- **Verified before production:** local rig — every one of the brain's ~31 call sites succeeds with the JWT and with rules already flipped to `@request.auth` expressions on a *local copy*. This is the dress rehearsal for stage 13.
- **Rollback:** unset the env var. `headers()` falls straight back to today's behaviour with no deploy.

### Stage 12 — Make failure honest before failure can happen

**For him:** this is the stage that prevents the two worst outcomes of everything after it — Anticipy texting him the same thing over and over, and a job he cancelled continuing to click through his real logged-in browser.

Once a rule is non-empty, a refused list read returns **200 with an empty array**, not an error. Roughly 35 call sites read that as "nothing there," and a handful actively fail *open*:

- `brain/worker.py:286,323,354` — the duplicate-suppression guards return `False` ("I haven't said this yet") on failure. Denial ⇒ she repeats herself forever.
- `brain/conversation.py:565` — `_requeue` returns the job id unconditionally without checking the response, and deliberately bypasses `_flip` (`:951-954`), the helper in the same file written to make exactly this impossible. Denial ⇒ "I'll finish the booking now" followed by nothing.
- `extension/background.js:260-261` — `jobStillLive` treats a 403 as **still live**, by explicit design comment. Denial ⇒ a cancelled job keeps running in his real browser. Highest-consequence failure in the whole map.
- `brain/anticipy_core.py:623` and `brain/conversation.py:647` — call `.json()` with no `ok` check; the guard's `{"error":"forbidden"}` body parses cleanly and yields `None`/`[]`, and the surrounding `except` never fires.
- `extension/popup.js:27` and `extension/onboarding.js:34` — check `/api/health`, which is outside the guard and will keep returning 200 forever, so the one screen he'd check to diagnose an outage will confidently say "I'm connected and watching for work."

The model to copy already exists in the repo: `conversation.py:951-954` and `AnticipyApp.swift:192-208`.

- **Verified before production:** point each client at a local rig with rules already locked and assert each site now *reports* rather than *invents*.
- **Rollback:** previous builds.

### Stage 13 — Lock the collections, one at a time

Order, ascending blast radius: **`pendants` → `owner_profile` → `agents` → `segments` → `jobs` → `events`.** `pendants` first because its only iOS writer (`AnticipyBackend.swift:140`) is dead code — it is the cheapest possible live test of the entire machinery.

Each flip is one migration changing one collection's rules from `""` to:
```
@request.auth.id != "" && owner_ref = @request.auth.account
```
`agents` needs one exception so a brand-new extension can still register itself; by this stage that exception lives in a rule string (`@request.body.paired = false && @request.body.owner = ""`), which reverts instantly, instead of in the guard hook, which needs a deploy. **Verify the exact `@request.body` semantics for an absent-versus-empty field on the local rig before relying on that string.**

**How the ordering is enforced, precisely.** A collection may be flipped only when all four hold:

1. It has `owner_ref` (stage 5 shipped).
2. **Zero rows** have an empty `owner_ref` — a counted query under a superuser session, not an estimate.
3. Every client that writes to it stamps `owner_ref`, *observed in the data*. The build-stamped `device_id` at `AnticipyApp.swift:96` — normally a defect — is exactly the adoption telemetry needed: `iphone-b37` rows carrying `owner_ref` prove the new build is the one writing.
4. **The traffic ledger from stage 3 has recorded zero anonymous days for that collection, for seven consecutive days.**

And the check is wired into the migration itself: the up-function reads the ledger, and **if the gate is not met it leaves the rule as `""` and logs loudly rather than throwing.** A throwing migration would fail the container at boot — i.e. the one thing forbidden — because Railway applies migrations at startup (`backend/Dockerfile:13`). The honest caveat: PocketBase then records that migration as applied, so a no-op flip needs a fresh migration to retry. That is the correct trade: a wasted migration file versus an outage.

- **Verified before production:** the entire client matrix against the local rig with that collection locked — phone, extension, worker — before any of it goes near Railway.
- **Rollback:** set the rule back to `""`. From the dashboard this takes seconds and no deploy; land the revert migration afterwards so the repo and the database don't drift.

### Stage 14 — Retire the shared key

Only now: `/agent/key` stops returning `service_token`; the tokenless exceptions at `guard.pb.js:44-80` are deleted; `ANTICIPY_SERVICE_TOKEN` is retired. This is the only stage that removes a way in, and by then every client has its own.

---

## 5. How each stage is tested locally

There is a real, Apple-silicon PocketBase binary in the repo (`backend/pocketbase`, Mach-O 64-bit arm64) and the migrations auto-apply on boot (`HANDOFF.md:527`).

### The standing hazard, and the exact way around it

**A fresh `pb_data` makes PocketBase print an installer link and open a browser tab on Omar's Mac asking him to create a superuser.** The rig must never do that. The mechanism that prevents it is creating the superuser *before* the server ever starts — verified from the binary's own help: `pocketbase superuser` exposes `upsert` ("Creates, or updates if email exists, a single superuser") and `--dir` is a global flag.

```
DIR=<scratchpad>/pbtest        # never backend/pb_data, never /tmp
./backend/pocketbase superuser upsert dev@local test1234567890 --dir "$DIR"
./backend/pocketbase serve --http 127.0.0.1:8091 \
  --dir "$DIR" --migrationsDir backend/pb_migrations --hooksDir backend/pb_hooks
```

Three non-negotiables: **port 8091, not 8090** (8090 is the documented dev port at `README.md:10` — don't collide with anything he has running); **`--dir` always points at the scratchpad**, never at `backend/pb_data`, which holds a real July-21 snapshot; and the rig is always run in the foreground and torn down, never left serving unattended.

### Per stage

- **Migrations (4, 5, 13).** Three runs each. (a) Against an **empty** scratch dir — proves clean boot. (b) Against a **copy** of `backend/pb_data` — proves it applies to a populated older schema, which is the closest available stand-in for production. (c) `pocketbase migrate down 1` then boot again — proves the rollback is real, not aspirational. A migration that throws on the production dataset is a *boot-time* failure, which is downtime; this is the rehearsal that prevents it.
- **Hooks (1, 2, 3, 6, 10, 14).** A curl matrix asserting exact status codes, run with `ANTICIPY_SERVICE_TOKEN` set (enforcement on) and unset (`guard.pb.js:18` fail-open path, which is the local-dev default). Every legitimate client filter must stay 200; every bypass variant must be 403. `--hooksWatch` is on by default so hook edits reload without a restart.
- **iOS (0, 7, 9, 12).** Simulator, with the Backend URL pointed at `http://127.0.0.1:8091` using the field that already exists at `SettingsView.swift:211` — no debug build, no code change.
- **Extension (10, 12).** Load unpacked against the local rig and run the full ceremony. Note the recorded pitfall: when POSTing jobs by hand, `params` must be a **JSON-encoded string**, not a nested object, or PocketBase stores `""` and the agent burns twenty no-op steps.
- **Brain (11, 12).** Run the worker against the local rig with `ANTICIPY_SERVICE_TOKEN`, then with `ANTICIPY_PB_JWT`, then with rules locked — the same three-way matrix that stage 13 will face in production.
- **The one thing that cannot be rehearsed locally** is the production dataset itself. Mitigation: stage 8 snapshots the Railway volume first, and every flip in stage 13 is one collection with a seconds-long dashboard undo.

---

## 6. What breaks if we get it wrong

The general shape of the danger, stated once: **the guard hook and the collection rules are two independent layers, and the guard's shared token creates no PocketBase identity.** A perfectly valid `X-Anticipy-Token` satisfies `guard.pb.js:29` and is then invisible to the rule engine. So flipping rules before clients can authenticate locks out *every* legitimate client at once — and, because hook code calls `e.app.find*` / `e.app.save` at the DAO level, which bypasses rules entirely, it locks out **nothing** in `/agent/key` or `/sms/inbound`. A rules-only change makes the system strictly worse: every real client dead, both leak surfaces open.

| Stage | Worst case | Which of his daily flows dies |
|---|---|---|
| 0 | Wrong Keychain read | Nothing — the old value is copied, not moved |
| 1 | Regex too strict | **Pairing.** Phone can't find its agent → can't get the token → `AnticipyApp.swift:192-205` clears the token it *had*, `fetchAgent` fails, `:252` never refetches, and `ContentView.swift:624` tells him nothing is linked when it is. Fleet-wide brick with no in-app escape. **This is why stage 1 is exact-string-matched against the two filters the clients actually send and ships alone.** |
| 2 | Wrong join | Browser fills forms with a blank profile. Fails soft — cached profile survives (`background.js:307-311`) |
| 3 | Ledger writes per request | Backend load. Bounded by once-per-collection-per-day-per-runtime; delete the file |
| 4 | Migration throws at boot | **Everything.** Container won't start. Prevented by the three-way rehearsal in §5 |
| 5 | Same | Same |
| 6 | None — widening only | Nothing |
| 7 | Login screen blocks first run | Same shape as the live defect at `OnboardingView.swift:166-205`, where advancing off the phone step is blocked on a server write. Login must be skippable |
| 8 | Backfill mis-assigns | Data corruption. Snapshot first; reverse script second |
| 9 | Bad `owner_ref` on write | Writes 400. **Transcripts** queue on disk and retry every 3s forever (`AnticipyApp.swift:184`, `:136`) |
| 10 | Pairing ceremony broken | **The browser lane.** New installs can't pair. Old path stays live as the fallback |
| 11 | Bad JWT | Brain 403s everywhere → **texting, the feed's brain-written half, segmentation.** Unset one env var |
| 12 | None — makes failures visible | Nothing |
| 13 | Flip before the gate | The full lockout: **the feed** goes empty and silent (`fetchEvents`' `try?` at `AnticipyApp.swift:209` hides it), **the browser lane** goes dark with no console line and no popup change, **two-way texting** stops (the SMS hook keeps *writing* the row via the DAO while `worker.py:574` can no longer *read* it — the message lands, is never read, is never answered), and **pairing** reports it as a connection problem because `PairOutcome` has no `.refused` case (`AnticipyApp.swift:347-351`) |
| 14 | Removing the shared token too early | Any client that hasn't adopted its own credential dies. Last stage for exactly this reason |

---

## 7. What this unlocks — and what it does not

**Per-user data scoping.** Right now the second person to install Anticipy sees the first person's transcripts verbatim in their own feed (`AnticipyBackend.swift:206-216` fetches globally) and gets their name, email, phone and birthday pushed into their browser's form-filler (`agent_key.pb.js:32`). After this, "whose is this" is a column the database enforces, not a filter the client politely applies — the repo's own comment at `AnticipyBackend.swift:222-224` calls the current arrangement "a courtesy, not a security boundary."

**A real "delete everything about me."** Apple requires in-app account deletion of the entire account record and its associated personal data — not deactivation, no email-support detour, and offered regardless of where the user lives. **That requirement is technically unimplementable today**, because `events` has no owner column, so there is no query that selects one person's transcripts. `owner_ref` is what makes deletion expressible at all; it also becomes the only mechanism by which a *bystander's* erasure request could ever be honoured, since their speech lives inside someone else's transcripts. Don't forget `owner_profile.facts` (`1700000007_owner_facts.js:15`) — per-owner PII stored as one JSON blob, easy to miss because it isn't a column per fact.

**Multi-user.** Three places currently hard-code the assumption that exactly one human exists: `agent_key.pb.js:32` (the first `owner_profile` row, whoever asks), `brain/worker.py:42-56` (the most recently updated profile, globally), and `sms.pb.js:17` (an environment variable). Those are prerequisites, not follow-ups.

**What it does not solve.** Six things, worth saying plainly so nobody mistakes this plan for more than it is:

- **Bystander consent.** Accounts make the gap auditable; they don't close it. People who never signed up are still recorded, and their speech is still sent to a third-party model provider (`agent_key.pb.js:18-24`). If anything, accounts *raise* the exposure: once transcripts sit under an account carrying a verified name, email, phone and birthday, a bystander's name in a transcript becomes linkable personal data held by you about *them*.
- **The recording indicator.** Apple's rule about a clear indication when recording is about the device, and `keepListening` is a standing state that survives backgrounds and relaunches (`AnticipyApp.swift:57-61`).
- **The OpenRouter key still travels to every browser** (`agent_key.pb.js:18`). Closing that needs a backend LLM proxy — a bigger, separate piece of work.
- **The inbound SMS webhook still has no Twilio signature check.** The token rides in the URL query string, so it lands in Railway logs, Twilio's console and every proxy in between; the legacy `backend/sms_server.py:77` validates the signature and the live hook does not. Orthogonal to all of this, and worth its own stage.
- **Retention.** Nothing here deletes an old transcript. A retention limit on raw `events.text` is the single most effective bystander mitigation available, it bounds every possible claim by time, and it needs no schema migration and no client release.
- **Speaker identification.** Don't add it. Diarization is the line where recording law becomes biometric law, with per-violation statutory damages owed to people who never touched the product.

---

## 8. The honest cost

**Roughly 70% of this is mechanical.** Stages 0, 2, 3, 4, 5, 6, 9 and 11 are small, additive, individually testable, and revert to a known-good state by deleting a line, dropping a nullable column, or unsetting an environment variable. Stage 4 and stage 5 in particular *cannot* break the live path: they touch no existing collection and change no rule, and their down-functions are single `app.delete` / `removeByName` calls of exactly the shape already proven at `1700000004_segments.js:61-71`.

**Three stages carry real, non-mechanical work.** Stage 7 (iOS login) is a genuine product surface with an onboarding-order trap the repo has already hit once. Stage 10 (the pairing ceremony) is new protocol design, though it is deliberately built as a parallel path with the old one still live. Stage 12 (fixing ~35 call sites that read a denial as an empty result) is tedious, unglamorous, and the single highest-leverage thing in the plan — it is what turns a future mistake into an error message instead of into Anticipy texting him the same sentence forever, or into a cancelled job that keeps clicking through his real logged-in browser.

**The single riskiest stage is 13 — the first rule flip.** Not because the change is large; because it is the first moment the two independent layers meet, and because its failure mode is *silence*. A denied list read returns 200 with an empty array, so the phone shows an empty feed, the extension goes dark with no log line, the popup keeps saying "I'm connected and watching for work" because `/api/health` is outside the guard, and only `brain/worker.py:388` raises at all — reporting it as "backend unreachable," which is the wrong diagnosis.

Three things make that risk survivable, and they are the reason the stages are ordered the way they are: it is flipped **one collection at a time**, starting with `pendants`, whose only client-side writer is dead code; the flip is **gated on seven consecutive anonymous-free days in the ledger**, checked by the migration itself, which leaves the rule as `""` rather than throwing if the gate isn't met; and the undo is **a rule string changed from the dashboard in seconds with no deploy** — which is precisely why every narrowing in this plan lives in a rule and every change to `guard.pb.js` is a widening.

**Stage 8 is the only irreversible-ish stage**, because it writes data. It gets a Railway volume snapshot immediately before, plus a reverse script, plus a full rehearsal against a copy. And it has a deadline that nothing else in the plan has: `events` can only be attributed to Omar while he is the only person using Anticipy. After a second account exists, that history is unattributable forever.

---

# Adversarial review of this plan

Rig down, repo untouched, `backend/pb_data` still Jul 21.

---

# Adversarial review — Anticipy auth migration

**Method:** read every file the plan cites, then built a throwaway PocketBase 0.30.4 rig from the repo's own binary (scratchpad only, superuser pre-created so no browser tab, port 8091, torn down) and **executed the plan's own migration and rule strings**. Findings 1, 2, 3, and the "verified safe" items are empirical, not analytical.

---

## 1. CRITICAL — Stage 13: the universal rule string locks Omar's phone out, silently, with all four gates green

The plan's whole design hangs on one string: `@request.auth.id != "" && owner_ref = @request.auth.account`. **`owners` has no `account` field.** I applied the plan's §2 migration verbatim; PocketBase generated exactly: `id, email, phone, legacy_uuid, created, updated, password, tokenKey, emailVisibility, verified`. The plan's prose ("`owners.account` is the record's own id") describes a field its own migration never creates.

PocketBase **accepts the rule with no validation error** (HTTP 200 on the rule PATCH), then resolves `@request.auth.account` to empty. Measured, with `jobs` seeded so both rows are Omar's:

| rule | phone | laptop | worker |
|---|---|---|---|
| `owner_ref = @request.auth.account` ← **the plan** | **0** | 2 | 2 |
| `owner_ref = @request.auth.id` | 2 | **0** | 2 |
| `(owner_ref = @request.auth.id \|\| owner_ref = @request.auth.account)` | 2 | 2 | 2 |

All HTTP 200. Zero means an empty feed, no error, no log line.

Worse, I ran it through the plan's own gate: I backfilled until `rows with empty owner_ref = 0` (gate #2 satisfied) — the phone still returned `totalItems=0`. **All four gate conditions can be green while the rule is inverted**, because every gate counts *data* and none of them ever evaluates the *rule*. This is precisely the "silence" failure the plan names as its riskiest moment, arriving through the one door it believed it had bolted.

Note the third row: the plan explicitly rejects the `||` form ("One rule string, no per-client branching, no `OR` clause"). That stated goal is **unachievable** — a phone token identifies by `id`, a device token by `account`; no single comparison covers both.

**Fix:** use the `||` form (proven above). Add a **fifth, mandatory gate**: after setting each rule, do a read-back with a real phone token and a real device token and assert a *nonzero, correct* row count — flip back immediately if either is 0. Do this on the rig for `pendants` before it ever reaches Railway.

## 2. CRITICAL — Stage 7: there is no path for Omar to create his account, and the failure is a 200

`request-otp` for an email with no `owners` record returned `{"otpId":"o7awikabczs3tq4"}`, **HTTP 200, and created zero records** (enumeration protection). With `createRule: null` and `passwordAuth: {enabled:false}`, no client can mint the account. Stage 7's stated sequencing — "ship email-OTP login first, then Sign in with Apple" — cannot bootstrap the first account. Omar taps login, gets a code-entry screen, and waits for a code that will never exist.

Compounding: **there is no mail transport.** OTP is email-delivered; `backend/Dockerfile` is `alpine:3.20` with only `ca-certificates unzip wget` — no sendmail — and there is no SMTP env var anywhere in the repo (`ANTICIPY_*`, `OPENROUTER_*`, `TWILIO_*` only). Even for an existing record the code never arrives, and `request-otp` still returns 200.

**Fix:** (a) invert the sequencing — Sign in with Apple is the only self-bootstrapping method here, since `auth-with-oauth2` creates the record; (b) or mint the `owners` row server-side in stage 8 (dashboard/superuser) *before* stage 7 ships, and treat OTP purely as second-device recovery; (c) configure SMTP as a hard prerequisite for any OTP claim. Also: PB defaults `otp.length = 8` and `otp.duration = 180s`, not the six digits the plan implies.

## 3. HIGH — Stage 1: "require `paired = false` on the pair-code branch" bricks pairing fleet-wide

The clients send `pair_code="NNNNNN"` **and nothing else** (`AnticipyBackend.swift:141`, `:166` — verified verbatim). If the new `paired = false` requirement is implemented as a *filter-string* requirement — which the sentence reads as, alongside "exact whole-filter equality" — the legitimate filter stops matching and pairing 403s. That is exactly the fleet-wide brick the plan's own risk table describes for stage 1, and stage 1 ships alone.

Second trap in the same stage: "exact whole-filter equality" is **impossible** for the owner branch — the guard cannot know the UUID. It must be an anchored regex (`^owner="[A-Za-z0-9-]{8,64}"$`). If someone implements literal equality there, `fetchAgent` dies — and that is the single call that recovers a stale token (`AnticipyApp.swift:248-255`), so the phone loses its only self-heal path.

**Fix:** state explicitly that `paired = false` is a **server-side record check after the DAO lookup**, never a filter requirement; and that both branches are **anchored regexes**, not string equality. Write the six curl assertions as literal strings copied out of the Swift source.

## 4. HIGH — Stage 13: the extension is structurally invisible to gate #3

Gate #3 is "every client that writes to it stamps `owner_ref`, observed in the data." The extension **never creates a `jobs` row** — it only PATCHes `status`/`claimed_by`/`claimed_at` (`background.js` `updateJob`). It can therefore never appear in that telemetry, and the gate passes while the extension is entirely unmigrated. Then: `claimJob` list → 200 empty → browser lane dark; `jobStillLive` returns `true` on any non-ok → **a cancelled job keeps clicking through his real logged-in Chrome**; `updateJob` only `console.warn`s on 403.

And he loads it unpacked (`manifest.json` 0.2.0) — stages 10 and 12 both need a manual reload he may not do for days.

**Fix:** add an observable adoption signal the extension actually writes — e.g. an `agents.ext_version` field stamped on the existing 10-second heartbeat — and make gate #3 read *that*, not `owner_ref`.

## 5. HIGH — Stage 13: realtime is never mentioned and dies silently

`background.js:418-437` opens `EventSource(${BASE}/api/realtime)` and POSTs subscriptions. PocketBase evaluates `listRule` **per subscriber** for realtime and denied clients simply receive nothing — no error, no close. After the `jobs` flip, push dies and the 5s poll fallback is also empty.

**Fix:** stage 10 must add `Authorization` to the **realtime subscribe POST** specifically, not just the data calls; add an SSE assertion to the stage-13 rig matrix.

## 6. HIGH — Stages 4/5: `migrate down 1` is not a production rollback

`backend/Dockerfile` CMD is `serve ... --migrationsDir /app/pb_migrations`; migrations auto-apply at boot. Running `migrate down` on Railway means changing CMD → redeploy → run → change back → redeploy, and because the file is still in the image **the next boot re-applies it**. Any restart (deploy, crash, platform maintenance) undoes the undo.

**Fix:** rewrite these rollback cells honestly: *"irreversible in practice, harmless by construction"* — which is true, since both are additive and nothing reads them. Don't claim an undo that doesn't exist; the plan's credibility elsewhere depends on these cells being accurate. Stage 13's dashboard-rule undo **is** real and fast — that reasoning is correct.

## 7. MEDIUM — Stage 9 + 13 rollbacks are not independent

Stage 9's rollback ("previous builds; the column stays unpopulated") holds only before stage 13. After a flip, `createRule` requires `owner_ref`, so an old build's write is rejected → `AnticipyApp.swift:136` queues the line into `unsentStore` (UserDefaults) and retries every 3s **forever**, unbounded.

**Fix:** state that once a collection is flipped, its clients can no longer be rolled back — reverting the rule is the *only* rollback at or after stage 9. Add a cap + user-visible warning on the unsent queue.

## 8. MEDIUM — Stage 14: retiring `ANTICIPY_SERVICE_TOKEN` disables the whole guard

`guard.pb.js:17-18` is `if (!token) return e.next()`. Unsetting the var makes the guard a **no-op for every request**. Survivable only because stage 13 locked everything — but any collection added later is then unguarded by default, `/api/realtime` included, and the panic button is gone.

**Fix:** at stage 14 keep the var set and delete only the tokenless-exception blocks; or invert the fail-open to fail-closed in the same commit.

## 9. MEDIUM — the brain's one safety net doesn't fire

The plan says `worker.py:382` is "the one read in the entire brain that raises on failure." Verified: `fetch_unprocessed` uses `r.raise_for_status()` — but a rule denial is **200**, so it does not raise. The brain goes silently deaf rather than crashing, and the "backend unreachable" misdiagnosis never even prints.

Token facts, verified: `owners.authToken.duration` defaults to **604800 (7 days)** and the plan never sets it; an invalid/expired `Authorization` is **silently ignored** and the request proceeds as guest (PocketBase's loadAuthToken explicitly does not error) — the plan is right about this and right that refresh is the probe. But `auth-refresh` with an impersonate token returns 200 with the **same token** (verified), so the worker cannot use the 401-from-refresh probe.

**Fix:** set `authToken.duration` explicitly on `owners`. Add a worker startup assertion: read a row known to exist; if 0, exit loudly. Add stage 12 coverage for "200 but empty" as a distinct failure from "non-200."

## 10. LOW — the §5 rig recipe does not run

`./backend/pocketbase superuser upsert dev@local test1234567890` → `Error: missing or invalid email address`. Needs a TLD (`dev@local.dev` works). The plan says this was "verified from the binary's own help" — the help was read; the command was not run. Small, but it is the first command anyone executes.

## 11. LOW — stage 8 reverse script over-reaches

"Nulls `owner_ref` where it equals his id" will also strip attribution from rows written by stage-9 clients. Key it on `owner_ref = <id> AND created < <backfill timestamp>`.

---

## Things I tried to break and could not — these are correct

- **Stage 6's widening line works exactly as claimed.** With the plan's literal `try { if (e.auth) return e.next(); } catch (_) {}` injected: anonymous → **403**, `X-Anticipy-Token` → **200**, owners-token-only → **200**, garbage token → **403**. Strictly widening, cannot lock anyone out.
- **The stage-4 migration applies cleanly** against the real 0.30.4 binary. Auth options are correctly top-level; PB auto-injects `password`/`tokenKey`/`emailVisibility`/`verified`; both partial unique indexes were really created in `sqlite_master`.
- **The stage-13 `agents` create-exception works.** `@request.body.paired = false && @request.body.owner = ""` accepted the real `ensureRegistered()` payload with `owner` **absent** → HTTP 200. The plan's flagged open question is answered: absent behaves as empty.
- **The worker's superuser impersonate token bypasses locked rules** — 200 with full row visibility against a locked collection. Stage 11 is sound. And `auth-refresh` returns the same token unchanged, confirming the plan's "probe, not extension" analysis.
- **`pendants` really is dead code** — one reference in the whole iOS app, inside the uncalled `pair()`. Correct choice for the first flip.
- Every client fail-open site the plan cites is real and correctly characterised (`jobStillLive` true-on-403, `_requeue` bypassing `_flip`, `already_said`/`already_raised` false-on-failure, `/api/health` outside the guard).

---

## Verdict

**Safe to execute with the fixes named — not as written.**

The architecture is sound and unusually well-reasoned: widen-before-narrow, narrowings in rules where the undo is instant, additive nullable columns, a superuser worker that sails through every flip, one collection at a time starting with dead code, and stage 12 before stage 13. I attacked the sequencing hard and the *shape* held up.

But the plan would take his product down in exactly the way it fears, at exactly the stage it identifies as riskiest, through the one artifact it never tested: **the rule string is wrong, PocketBase accepts it without complaint, and the phone's feed goes empty with HTTP 200 while all four gates read green.** Findings 1, 2, and 3 are blocking — 1 and 3 are outages, 2 is a stage that cannot ship at all. Fold in 4–8 before stage 13 and the rest is the careful plan it looks like.

One structural note worth more than any single fix: **every gate in this plan verifies data, and none verifies behaviour.** Add a read-back assertion with real client tokens to each flip and most of this class of failure stops being possible.

Rig at `/private/tmp/claude-501/-Users-omarebrahim-Desktop/c6b91f04-3014-4810-8532-a2fbc61abc26/scratchpad/rig` if you want to re-run any of it; `/Users/omarebrahim/Anticipy-pendant` was never modified.