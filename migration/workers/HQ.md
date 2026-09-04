# HQ on Cloudflare

`backend/pb_hooks/internal_hq.pb.js` — 4,276 lines, **38 `routerAdd` routes**,
**2 `cronAdd` jobs**, **1 `routerUse` middleware**, **14 collections**, its own
auth stack, a Clerk JWT exchange, an encrypted vault, an ICS feed, and a 136 KB
single-page app it reads off disk.

Companion artifacts already in this tree, referenced and not repeated here:
`migration/spec/CONTRACT.md` (the behavioural oracle),
`migration/d1/schema.sql` (all 14 `internal_*` tables, lines 639–1024),
`migration/d1/GAPS.md` (what production serves that this repo cannot describe),
`migration/runbooks/reencrypt_vault.md` (**read before touching the vault**).

---

## 1. The recommendation, first, because it changes everything below

> **HQ becomes Next.js Route Handlers in the existing site Worker. It does not
> become a separate Worker.**
>
> **And the files go at `src/app/internal/<route>/route.ts`, NOT
> `src/app/api/internal/*`.** A file under `src/app/api/internal/state/` answers
> at `/api/internal/state`. Every client in existence asks for `/internal/state`.

### 1.1 Why one Worker and not two

**The client already sends relative paths.** `backend/pb_public/internal.html:507-513`:

```js
function api(path, opts){
  ...
  if (S.session) headers["X-HQ-Session"] = S.session;
  else if (S.key) headers["X-Internal-Key"] = S.key;
  return fetch(path, { ... });          // ← path is "/internal/state", relative
}
```

So where the page is served from decides where its API calls go. Today the page
is served from the Railway origin, the calls go there, and that is the *entire*
reason `internal_hq.pb.js:4224-4240` exists — a hand-written CORS block with an
allow-list, on routes that carry a credential in a custom header. **Serve the
page from anticipy.ai and that middleware, the `OPTIONS /internal/{path...}`
preflight at `:4243`, and the `Access-Control-Allow-*` headers all become
dead code.** One fewer security surface, deleted rather than ported.

**The rewrites already exist and are already the preferred design.** The source
says so itself (`internal_hq.pb.js:4209-4213`):

> *"PREFERRED, and it is not in this repo: two rewrites in omize10/Anticipy's
> next.config.mjs, /hq -> /fellows/hq and /internal/:path\* -> /internal/:path\*
> on the Railway origin. That makes the page and its data same-origin, which
> means no CORS at all."*

`origin/main`'s `next.config.mjs:101-151` is that change, landed. 27 `/internal/*`
paths are enumerated there. Porting HQ into the site Worker means **deleting**
those 27 rewrites and answering the same URLs directly. Nothing about the client
changes; nothing about the URL changes.

**A second Worker would need everything back.** It would need its own CORS
allow-list, its own D1 binding to the same database (two Workers writing the
same tables), its own copy of the session-resolution code, and a rewrite from
the site Worker to reach it — which is a subrequest per HQ call, forever, for
no benefit.

**And the site middleware already gates it.** `src/middleware.ts:149-174`
matches `/internal` and `/internal/:path*` (`:184-185`) and answers **401 to
anything without the signed `anticipy_internal_gate` cookie** — before any
handler runs. That gate is already in front of HQ. It cannot be in front of a
separate Worker on a separate hostname without being rebuilt there.

### 1.2 The one thing that breaks, and it must be fixed deliberately

`src/middleware.ts` gating `/internal/:path*` is exactly why the ICS feed is
served from the Railway origin today. From `internal_hq.pb.js:2875-2878`:

> *"Served from the Railway origin directly (the page prints that URL) because
> the anticipy.ai edge sits behind the passcode gate and Google's fetcher will
> never have the cookie."*

and `/internal/me` builds the printed URL from `RAILWAY_PUBLIC_DOMAIN`
(`:3528-3529`). **When Railway is gone, that URL is gone, and every subscribed
calendar silently stops updating.** See §6.

### 1.3 What "port" means here, concretely

| Today | Tomorrow |
|---|---|
| `internal_hq.pb.js`, 4,276 lines, one file, JSVM | ~30 files under `src/app/internal/*/route.ts` |
| `e.app.findRecordsByFilter(...)` | `env.DB.prepare(...).all()` on D1 |
| `$security.equal` | `crypto.subtle.timingSafeEqual` *(§4.1)* |
| `$security.sha256` | `crypto.subtle.digest("SHA-256", …)` |
| `$security.encrypt/decrypt` | WebCrypto AES-256-GCM — **and a re-wrap first** *(§5)* |
| `$security.parseJWT` | HS256 verify via `crypto.subtle.verify` *(§4.4)* |
| `$os.getenv("X")` | `env.X` (secret) |
| `$os.readFile("pb_public/internal.html")` | Workers Static Assets *(§7)* |
| `$http.send` | `fetch` |
| `cronAdd(...)` | `triggers.crons` + `scheduled()` *(§8)* |
| `routerUse` CORS block | **deleted** *(§1.1)* |

### 1.4 The one rule of the source file, and why it stops applying

`internal_hq.pb.js:5-10`:

> *"THE ONE RULE OF THIS FILE: every handler redeclares EVERYTHING it uses
> inside its own body — the auth check, the helpers, the base64 encoder, all of
> it. PocketBase JSVM handlers run in isolated contexts and cannot see anything
> declared outside themselves; that trap has bitten this codebase at least three
> times."*

That is why `$security.equal` appears **34 times** and `X-HQ-Session` **31
times** in one file. Workers have no such isolation: the auth check becomes one
`resolveActor(request, env)` in `src/app/internal/_auth.ts` that all 30 handlers
import.

**This is the single biggest win of the port and also its single biggest risk.**
Thirty inlined copies drifted from each other over time; one shared function
cannot. But it also means one bug in `resolveActor` is a bug in all thirty. The
`migration/spec/contract_tests.py` harness is what makes that trade safe — run
it against PocketBase, then against the Worker, diff.

---

## 2. All 38 routes

`✅` = live · `⛔` = returns 410, body retained · `K` = `X-Internal-Key` ·
`S` = `X-HQ-Session` · `—` = no credential.

| # | Route | Line | Auth | What it does |
|---|---|---|---|---|
| 1 | `GET /internal/health` | 20 | — | ✅ Liveness + `gated` (is `ANTICIPY_INTERNAL_KEY` set) + `channels.{email,sms}` **derived from env presence, never a literal** (`:22-29`). Booleans that cannot leak a key. |
| 2 | `POST /internal/login` | 42 | K in body | ✅ Lets the gate screen validate the team key *before* storing it. `$security.equal` on `body.key`. |
| 3 | `GET /internal/state` | 55 | K **or** S | ✅ The whole board in one round trip: `people, tracks, todos, events, activity, comments, notifs, reminders, signins, expenses, passwords, notes, config, channels, me, via_session, meters` (`:101-103`). Explicit projections throughout — `code_hash` is never returned, only `has_code` (`:107-120`); `secret_enc` is never returned, not even encrypted (`:261-268`); `signins` are **admins only** (`:294-307`) and omit `token_hash` and `ip`. |
| 4 | `POST /internal/people` | 333 | K **or** S | ✅ Self-serve join. Mints an 8-char code, returns the plaintext **once** — "not logged, not written to activity, and not in /internal/state" (`:487-489`). |
| 5 | `PATCH /internal/people` | 483 | K **or** S | ✅ Self-edit contacts; `role`/`active`/`is_admin` are admin-only. Writes `internal_activity`. |
| 6 | `POST /internal/todos` | 611 | K **or** S | ✅ Create a task, flag people, arm a reminder, notify assignees (`:782-790`). |
| 7 | `PATCH /internal/todos` | 796 | K **or** S | ✅ Changed fields only; stamps `done`; re-arms the reminder on a re-time; pushes `assign`/`blocked`/`done` notifications to creator + watchers (`:1018-1033`). |
| 8 | `POST /internal/todos/delete` | 1040 | K **or** S | ✅ Creator or admin. "Destruction stays human." |
| 9 | `POST /internal/events` | 1109 | K **or** S | ✅ Calendar entry + countdown chip. |
| 10 | `POST /internal/events/delete` | 1179 | K **or** S | ✅ Creator or admin. |
| 11 | `POST /internal/tracks` | 1239 | K **or** S | ✅ Admin-only project/board upsert. |
| 12 | `POST /internal/router` | 1350 | K | ⛔ 410 at `:1362`. The task-routing concierge, killed 2026-08-23. Body kept because "cutting a block out of it by hand is how you take the whole of HQ down with a stray brace" (`:1356-1359`). |
| 13 | `POST /internal/assistant` | 1465 | K **or** S | ✅ **Revived the same day it was killed** (`:1466-1469`). Calls OpenRouter (`:1663-1665`) with `ANTICIPY_INTERNAL_MODEL` (`:1660`), default `google/gemini-3.7-flash`, `max_tokens: 2000`, `response_format: json_object`. Returns `{say}` or executes one of **13** validated actions: `create_todo, complete_todo, delete_todo, assign_todo, set_reminder, create_event, add_person, set_contact, set_priority, set_stage, add_subtask, comment, create_project` (`:1630-1642`). Note the banner at `:1463` still says "No delete tool, by design" — **stale**, `delete_todo` is at `:1796`. |
| 14 | `POST /internal/research` | 2015 | K | ⛔ 410 at `:2026`. |
| 15 | `GET /internal/research/status` | 2089 | K | ⛔ 410 at `:2100`. |
| 16 | `POST /internal/session` | 2714 | — | ✅ **The code IS the credential.** Exchange an 8-char code for a 30-day token. §4.3. |
| 17 | `POST /internal/expenses` | 2882 | K **or** S | ✅ Upsert an expense; rows carry the person, the page filters "Mine"/"Company" (`:2872-2874`). |
| 18 | `POST /internal/expenses/delete` | 2950 | K **or** S | ✅ Logger or admin. |
| 19 | `POST /internal/passwords` | 3013 | K **or** S | ✅ Vault upsert. Empty `secret` on update means keep (`:3076-3078`). §5. |
| 20 | `POST /internal/passwords/reveal` | 3087 | K **or** S | ✅ `$security.decrypt` → plaintext in the response. The only read path. §5. |
| 21 | `POST /internal/passwords/delete` | 3146 | K **or** S | ✅ |
| 22 | `POST /internal/notes` | 3204 | K **or** S | ✅ Shared notebook; anyone edits, `updated_by` records who. Body capped at 50 000 chars (`:3261`). |
| 23 | `POST /internal/notes/delete` | 3271 | K **or** S | ✅ Creator or admin. |
| 24 | `GET /internal/cal/{token}` | 3328 | token | ✅ Per-person ICS feed. §6. |
| 25 | `POST /internal/clerk/exchange` | 3385 | Clerk JWT | ✅ Trade a Clerk HS256 token for an HQ session. §4.4. |
| 26 | `POST /internal/session/end` | 3453 | S | ✅ Deletes the row, not the code. **Always 200** — whether that token existed is not a thing this route reports (`:3468`). |
| 27 | `GET /internal/me` | 3472 | K **or** S | ✅ Who am I + team rules + **`cal_url`**, built from `RAILWAY_PUBLIC_DOMAIN` (`:3528-3529`). §6. |
| 28 | `POST /internal/people/code` | 3538 | K **or** S, admin | ✅ Mint a new login code. Returns plaintext once, kills that person's sessions (`:3582-3586`) and reports how many (`:3602`). |
| 29 | `POST /internal/comments` | 3608 | K **or** S | ✅ Task thread; bumps `internal_todos.cmt_count`. |
| 30 | `PATCH /internal/comments` | 3717 | K **or** S | ✅ Author only. Stamps `edited_at` — "the mark that makes the thread honest" (`:3759-3760`). |
| 31 | `POST /internal/comments/delete` | 3766 | K **or** S | ✅ Author or admin. **A TOMBSTONE, not a DELETE** (`:3764`); decrements `cmt_count` (`:3809-3813`); the increment is at `:3666`. |
| 32 | `POST /internal/reminders` | 3821 | K **or** S | ✅ Standalone reminders "the ones `remind_at` cannot express". `fire_at`, `channel`, `label`. |
| 33 | `POST /internal/reminders/delete` | 3954 | K **or** S | ✅ Whoever armed it, or an admin. |
| 34 | `POST /internal/notifs/read` | 3996 | K **or** S | ✅ `{ids:[…]}` or `{all:true}`; returns the new unread count (`:4053-4057`). |
| 35 | `POST /internal/tracks/delete` | 4058 | K **or** S, admin | ✅ **Nothing is ever orphaned** — tasks move to the home track and the count is reported (`:4129`). |
| 36 | `POST /internal/settings` | 4135 | K **or** S, admin | ✅ `team_name`, `perm_assign`, `perm_delete` into `internal_config`. |
| 37 | `OPTIONS /internal/{path...}` | 4243 | — | ✅ 204 and nothing else — "never reveals whether the path behind it exists" (`:4241-4242`). **Delete on port**: §1.1. |
| 38 | `GET /fellows/hq` | 4250 | — | ✅ Serves the SPA from disk. §7. |

**Three of the 38 are already dead** (12, 14, 15). Do not port their bodies.
Port the 410 — something in the world may still be calling them, and a 404 and a
410 are different sentences.

### 2.1 The two crons and the middleware

| | Line | What |
|---|---|---|
| `cronAdd("internal_hq_sweep", "*/5 * * * *")` | 2139 | Five passes: **reminders** (`:2228`), **follow-ups** — one nudge, ever, 2 days past due (`:2278`), **PASS C** standalone `internal_reminders` (`:2301`), **PASS D** the notification digest, one message per person per sweep (`:2408`), the **research slot backstop** (`:2490`), and the **repeat motor** that lays down recurring tasks (`:2517`). Sends via Twilio (`:2170-2171`) and Resend (`:2189-2190`). `REMIND_MAX_TRIES = 3`. |
| `cronAdd("internal_hq_prune", "17 4 * * *")` | 2642 | 60-day `internal_activity` prune, then everything v2 added that grows without a ceiling — expired sessions included. Written because *"the audit ledger once filled the 5GB volume"* (`:2637-2638`). |
| `routerUse` CORS | 4224 | Origin allow-list for `/internal/*` and `/fellows/hq`, never `*`, because these routes carry a credential in a custom header (`:4220-4223`). **Deleted on port.** |

**CLAIM-FIRST, THEN SEND** governs the sweep and it is not a style choice
(`:2143-2151`): the cron refires every five minutes forever, so send-first with a
failed persist means *unbounded* duplicate texts — a loop the worker has actually
lived. The stamp rolls back only when **every** channel failed. Any port that
reorders this reintroduces a bug that has already reached a real phone.

---

## 3. The 14 collections

All present in `migration/d1/schema.sql`:

| Collection | schema.sql | Note |
|---|---|---|
| `internal_people` | 639 | carries `code_hash`, `is_admin`, `active`, `remind_pref`, `email_on`, `sms_on`, `last_in` |
| `internal_tracks` | 674 | projects/boards |
| `internal_todos` | 709 | `assignees` is a JSON array of person ids (`internal_hq.pb.js:3361`), `cmt_count` is denormalised |
| `internal_events` | 754 | |
| `internal_activity` | 774 | append-only feed, pruned at 60 days |
| `internal_meter` | 802 | two named rows: `login` (hourly brute-force ceiling) and `llm` (hourly assistant ceiling) |
| `internal_comments` | 823 | |
| `internal_notifs` | 847 | `emailed_at` / `smsed_at` are the claim stamps |
| `internal_reminders` | 873 | `fire_at`, `channel`, `attempts`, `sent_at` |
| `internal_sessions` | 897 | `token_hash`, `expires`, `ip`, `ua` — last ten per person |
| `internal_config` | 922 | key/value; only `team_name`, `perm_assign`, `perm_delete` are read (`:284-289`) |
| `internal_expenses` | 946 | |
| `internal_passwords` | 982 | `secret_enc` — §5 |
| `internal_notes` | 1003 | |

*(The brief said 13. It is 14; `internal_meter` is easy to miss because it holds
two rows and no user data, and losing it silently disables the login
brute-force ceiling — see §4.3.)*

---

## 4. The parallel auth stack

Four credentials, none interchangeable. `migration/spec/CONTRACT.md:§0.1` is the
canonical table; this section is what a port has to *build*.

### 4.1 `X-Internal-Key` — the shared team key

```js
// internal_hq.pb.js:43-48
const key = $os.getenv("ANTICIPY_INTERNAL_KEY") || "";
if (!key) return e.json(503, { error: "internal HQ is not configured" });
...
if (!$security.equal(sent, key)) return e.json(401, { error: "wrong key" });
```

**FAIL-CLOSED, and it is the deliberate inversion of `guard.pb.js`'s fail-open**
(`internal_hq.pb.js:12-15`):

> *"if the env var is missing the routes answer 503, they do not open… a fresh
> deploy that forgot one variable must not publish the team's phone numbers."*

`$os.getenv("ANTICIPY_INTERNAL_KEY")` appears **52 times** and `$security.equal`
**34 times**. On Workers this collapses to one module:

```ts
// src/app/internal/_auth.ts
const enc = new TextEncoder();

/** $security.equal — timing-safe. crypto.subtle.timingSafeEqual throws when the
 *  byte lengths differ, which is itself an oracle for length; hash both sides to
 *  a fixed 32 bytes first so every comparison costs the same. */
export async function timingSafeEqualStr(a: string, b: string): Promise<boolean> {
  const [ha, hb] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(a)),
    crypto.subtle.digest("SHA-256", enc.encode(b)),
  ]);
  return crypto.subtle.timingSafeEqual(ha, hb);
}

export async function sha256Hex(s: string): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", enc.encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
```

`$security.sha256` returns **lowercase hex** — every stored `code_hash`,
`token_hash` and calendar token is compared against that form
(`internal_hq.pb.js:3334` requires `/^[0-9a-f]{64}$/`). Do not emit base64.

### 4.2 `X-HQ-Session` — the personal session

`internal_sessions` keyed on `sha256(token)`, token = 64 hex chars from
`$security.randomStringWithAlphabet(64, "0123456789abcdef")`
(`:2786`, `:3423`), 30-day expiry, **last ten per person** kept (`:2807-2812`).

The resolution block is inlined 31 times. The canonical copy is `:71-90`, and
two details in it are load-bearing:

```js
// :78-79  — THE ZZ/NaN TRAP
let exp = String(sess.getString("expires")).trim().replace(" ", "T");
if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";
```

PocketBase datetimes arrive with or without a trailing `Z`. Without this, `exp`
parses to `NaN`, `Date.now() < NaN` is `false`, and **every session is rejected**.
On D1 the stored strings are whatever `migration/runbooks/import_d1.py` wrote —
normalise on import, and keep this shim anyway.

```js
// :88  — NEVER A FALL-THROUGH
if (!actor) return e.json(401, { reauth: true });
```

> *"A silent downgrade from 'this is Ari' to 'whoever holds the key says they are
> Ari' is the attack: an expired token must log you out, not quietly demote you
> to client-asserted identity."* (`:69-72`)

The client depends on the exact shape: `internal.html:518` signs out on **401
while a session is held**. `{reauth:true}` with status 401 — both.

### 4.3 The 8-character login code

```js
// :2786 (mint) and :3573 — alphabet excludes I, L, O, U
$security.randomStringWithAlphabet(8, "0123456789ABCDEFGHJKMNPQRSTVWXYZ")
```

```js
// :2769-2777 — look up BY HASH, then compare timing-safely anyway
person = e.app.findFirstRecordByFilter("internal_people",
  "code_hash = {:h}", { h: sha256(raw) });
if (!person) return no();
if (!$security.equal(sha256(raw), person.getString("code_hash"))) return no();
```

Guarded by a **global hourly ceiling counted on the attempt, before the
comparison** (`:2744-2766`), `ANTICIPY_HQ_LOGIN_CEILING` default 40, stored in
`internal_meter` row `login`. Global rather than per-IP because an attacker
rotates addresses. **If the meter row cannot be read or written, the route
refuses** (`:2758`, `:2766`) — *"a brute-force guard that silently stops counting
is worse than none."*

And **one sentence for every failure** (`:2739-2743`): wrong code, revoked code,
deactivated person, tripped ceiling — all answer identically, so the login screen
never becomes an oracle.

> **Port note, and it is a real finding.** The alphabet is 32 characters and the
> code is 8 long: 32⁸ ≈ 1.1 × 10¹² ≈ 2⁴⁰. `code_hash` is **unsalted SHA-256** of
> that 40-bit secret. The hourly ceiling is a complete defence *online*; it is no
> defence at all against anyone holding a copy of `internal_people`. A commodity
> GPU exhausts 2⁴⁰ unsalted SHA-256 in minutes.
>
> The current design is coherent — `/internal/state` deliberately never projects
> `code_hash` (`:107-113`), and PocketBase's backups were the only copy. **A D1
> export is a new copy**, and `migration/runbooks/EXPORT.md` produces one.
>
> Fix it during the port, not after: store PBKDF2-SHA256 with a per-row salt and
> ~100 000 iterations. On Workers that is a few milliseconds and it is paid at
> most 40 times an hour by the ceiling above. Requires re-minting all codes (route
> 28 already does this, one person at a time) or a dual-read window. This is
> cheap now and expensive later — do it now.

### 4.4 The Clerk JWT exchange

```js
// :3387-3401
const jwtKey = $os.getenv("CLERK_HQ_JWT_KEY") || "";
if (!jwtKey) return e.json(503, { error: "Clerk sign-in is not configured" });
...
if (!tok || tok.split(".").length !== 3) return e.json(400, …);
try { claims = $security.parseJWT(tok, jwtKey); } catch (_) {}
if (!claims) return e.json(401, { error: "Clerk did not recognise that sign-in" });
```

**HS256, not Clerk's default RS256**, and the reasoning is recorded at
`:2853-2860`: the PocketBase JSVM cannot check an RS256 signature, and Clerk's
server-side verify endpoint answered 410 (deprecated) when it was tried on
2026-08-23. So the page asks Clerk for a token from the **`hq` JWT template** —
HS256, 60-second life, signed with a key only Clerk and this backend hold.

Then (`:3402-3417`): `email` and `sub` are **re-checked** because a merely-absent
claim would sail through as an empty string; the email must match an **active**
row in `internal_people`, case-insensitively (`:3411-3413`); and the 403 names
the address — *"only to someone who has just proven to Clerk that they own it"*
(`:3416-3418`).

From `:3421` onward it is `/internal/session`'s mint verbatim in shape.

**On Workers this is easier, not harder**, because WebCrypto does RS256 natively.
Two options:

1. **Keep HS256.** ~20 lines with `crypto.subtle.verify("HMAC", …)`. Nothing
   changes for Clerk, the `hq` template, or the page. Recommended for cutover:
   change one thing at a time.
2. **Move to RS256 against Clerk's JWKS** afterwards. Removes a shared secret
   entirely. Do it as its own change, with its own test, after HQ is live.

Whichever, keep the architectural note at `:2846-2852` true — **fourteen handlers
accept `X-HQ-Session`; only this one knows Clerk exists.** A Clerk outage must
stop new sign-ins and nothing else.

```ts
// src/app/internal/clerk/exchange/route.ts — the verify, HS256
async function verifyHS256(token: string, secret: string): Promise<Record<string, unknown> | null> {
  const [h, p, s] = token.split(".");
  if (!h || !p || !s) return null;
  const key = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["verify"]
  );
  const sig = Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  const ok = await crypto.subtle.verify("HMAC", key, sig, new TextEncoder().encode(`${h}.${p}`));
  if (!ok) return null;
  const claims = JSON.parse(atob(p.replace(/-/g, "+").replace(/_/g, "/")));
  // $security.parseJWT enforces exp (:3402). WebCrypto does not — do it here or
  // an expired Clerk token is accepted forever.
  if (typeof claims.exp !== "number" || claims.exp * 1000 <= Date.now()) return null;
  return claims;
}
```

### 4.5 The "session door" — the pattern that must be preserved exactly

Twenty handlers carry an identical block added 2026-08-23. `:611-625` is a
representative copy:

> *"This handler predates personal sessions and only knew the team key — which
> meant a Clerk or code sign-in could read the board but got 'wrong key' the
> moment they tried to create anything. Found live: Omar, signed in through
> Clerk, created a task and was thrown back to the login screen."*
>
> *"A valid session is translated INTO the key path right here: the actor becomes
> the session's person (**overwriting whatever `actor_id` the client claimed — a
> session must not impersonate**), and the key check is skipped."*

Three rules, and a port that gets any of them wrong is a security bug:

1. Session present and valid → actor is the **session's** person. The client's
   `actor_id` is **discarded**, not merged.
2. Session present and invalid → **401 `{reauth:true}`**. Never fall through to
   the key branch.
3. No session → key check, and the actor is whoever the client says it is. That
   is the founder's explicit v1 call (`:2698-2702`), it stays visible in the
   activity feed, and *"it is not quietly improved into something that looks like
   auth."*

```ts
// src/app/internal/_auth.ts — the whole door, once
export type Actor = { id: string; name: string; is_admin: boolean; active: boolean };

export async function resolveActor(
  req: Request, env: Env, claimedActorId?: string
): Promise<{ actor: Actor | null; viaSession: boolean } | Response> {
  const key = env.ANTICIPY_INTERNAL_KEY || "";
  if (!key) return json(503, { error: "internal HQ is not configured" });   // FAIL CLOSED

  const tok = req.headers.get("X-HQ-Session") || "";
  if (tok) {
    const row = await env.DB.prepare(
      `SELECT person, expires FROM internal_sessions WHERE token_hash = ?`
    ).bind(await sha256Hex(tok)).first<{ person: string; expires: string }>();
    if (row && parsePbTime(row.expires) > Date.now()) {
      const p = await env.DB.prepare(
        `SELECT id, name, is_admin, active FROM internal_people WHERE id = ?`
      ).bind(row.person).first<Actor>();
      if (p && p.active) return { actor: p, viaSession: true };
    }
    // Rule 2. NEVER fall through to the key branch. internal_hq.pb.js:88
    return json(401, { reauth: true });
  }

  if (!(await timingSafeEqualStr(req.headers.get("X-Internal-Key") || "", key))) {
    return json(401, { error: "wrong key" });
  }
  // Rule 3. Client-asserted identity, visibly.
  if (!claimedActorId) return { actor: null, viaSession: false };
  const p = await env.DB.prepare(
    `SELECT id, name, is_admin, active FROM internal_people WHERE id = ?`
  ).bind(claimedActorId).first<Actor>();
  return { actor: p ?? null, viaSession: false };
}

/** internal_hq.pb.js:78-79 — the ZZ/NaN trap. */
export function parsePbTime(v: string): number {
  if (!v) return NaN;
  let t = String(v).trim().replace(" ", "T");
  if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(t)) t += "Z";
  return Date.parse(t);
}
```

---

## 5. The vault

```js
// :3052, :3079                    // :3126, :3140
const vk = $os.getenv("ANTICIPY_VAULT_KEY") || "";
row.set("secret_enc", $security.encrypt(String(body.secret).slice(0, 500), vk));
plain = $security.decrypt(row.getString("secret_enc"), vk);
```

Three routes touch it: write (19, `:3013`), reveal (20, `:3087`), delete
(21, `:3146`). `/internal/state` deliberately carries **metadata only** —
*"not even encrypted, because nothing on the page needs it and habits start
somewhere"* (`:262-264`). So the ciphertext column is the only copy.

### 5.1 This is the one-way door

**`migration/runbooks/reencrypt_vault.md` already exists in this tree and is
correct. Follow it. Do not re-derive it here.** Its position, restated because it
must not be softened:

> `$security.encrypt` is PocketBase's **Go** implementation. Its wire format —
> nonce placement, key derivation, tag layout — is an undocumented internal of a
> dependency being decommissioned. **Plan on nothing in a Worker being able to
> open those bytes**, and note that the guess cannot be re-run after the instance
> is gone.

`migration/runbooks/import_d1.py` enforces it: it **refuses** to import a
non-empty `secret_enc` unless `<export>/vault/vault_rewrapped.json` is present.
That is the right shape — the failure happens at import time, not at reveal time
three weeks after Railway was deleted.

### 5.2 The re-encryption dependency, as a sequence

```
PocketBase alive
      │  $security.decrypt(secret_enc, ANTICIPY_VAULT_KEY)   ← ONLY here, ONLY now
      ▼
rewrap_vault.mjs   AES-256-GCM · random 12-byte IV · 128-bit tag · AAD = record id
      │            key: ANTICIPY_VAULT_KEY_GCM (32 raw bytes, base64 in env)
      ▼
<export>/vault/vault_rewrapped.json                          ← the receipt
      │
      ▼
import_d1.py  → D1: secret_gcm populated, secret_enc = ''
      │
      ▼
HQ on Workers reads secret_gcm with crypto.subtle
      │
      ▼
ONLY NOW may PocketBase be decommissioned
```

**AAD = the record id** is not decoration: without it, a ciphertext lifted from
one vault row and pasted into another decrypts cleanly, and the reveal route
returns Stripe's password under the heading "Figma".

### 5.3 The Worker side

```ts
// src/app/internal/_vault.ts
// Reads what rewrap_vault.mjs wrote: base64( iv(12) || ciphertext || tag(16) ),
// AES-256-GCM, additionalData = the internal_passwords record id.
async function vaultKey(env: Env): Promise<CryptoKey> {
  const raw = Uint8Array.from(atob(env.ANTICIPY_VAULT_KEY_GCM), (c) => c.charCodeAt(0));
  if (raw.byteLength !== 32) throw new Error("ANTICIPY_VAULT_KEY_GCM must be 32 raw bytes, base64-encoded");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export async function vaultEncrypt(env: Env, plain: string, recordId: string): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: new TextEncoder().encode(recordId), tagLength: 128 },
    await vaultKey(env), new TextEncoder().encode(plain)
  ));
  const out = new Uint8Array(iv.length + ct.length);
  out.set(iv); out.set(ct, iv.length);
  return btoa(String.fromCharCode(...out));
}

export async function vaultDecrypt(env: Env, blob: string, recordId: string): Promise<string> {
  const buf = Uint8Array.from(atob(blob), (c) => c.charCodeAt(0));
  const pt = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: buf.slice(0, 12), additionalData: new TextEncoder().encode(recordId), tagLength: 128 },
    await vaultKey(env), buf.slice(12)
  );
  return new TextDecoder().decode(pt);
}
```

Keep the error text the reveal route already returns —
`"could not decrypt — was the vault key rotated?"` (`:3141`). It is the sentence
that tells an operator what actually happened, and it is the sentence a rotation
runbook is written against.

**A vault row created after the re-wrap and before the cutover is lost.** Freeze
writes to route 19 for the duration, or run the re-wrap twice and diff.

---

## 6. The ICS feed

```js
// :3328-3343
routerAdd("GET", "/internal/cal/{token}", (e) => {
  let tok = String(e.request.pathValue("token") || "");
  if (tok.slice(-4) === ".ics") tok = tok.slice(0, -4);
  if (!/^[0-9a-f]{64}$/.test(tok)) return e.json(404, { error: "not found" });

  const people = e.app.findRecordsByFilter("internal_people", "active = true", "+name", 200, 0);
  for (const p of people) {
    if ($security.equal($security.sha256(key + p.get("id")), tok)) { person = p; break; }
  }
  if (!person) return e.json(404, { error: "not found" });
```

**The token is the credential**, and it is `sha256(ANTICIPY_INTERNAL_KEY + person_id)` —
deterministic, so there is no new column and no minting flow, and rotating the
team key revokes every feed at once (`:2868-2872`). The cost is stated honestly
in the source: *"a leaked feed URL stays valid until the key rotates."* (`:2871-2872`)

The lookup is a **linear scan over every active person**, recomputing the hash
each time, with a timing-safe compare inside the loop. At `perPage: 200` that is
at most 200 SHA-256 operations — microseconds on Workers, nowhere near a CPU
limit. **Port it as it is.** A reverse index would be faster and would require a
new column, which is exactly what the design avoided.

The body: `internal_todos` where `status = 'open' && due != ''`, filtered to rows
whose JSON `assignees` array contains this person (`:3358-3364`), plus **every**
`internal_events` row (`:3370-3379`). All-day `VALUE=DATE` entries — *"a feed that
guesses at hours puts wrong hours on someone's phone, and an all-day banner never
lies"* (`:3345-3347`). CRLF line endings, `esc()` at `:3348`, `Content-Type:
text/calendar; charset=utf-8` via `e.blob` (`:3382`).

### 6.1 The thing that must be decided before cutover

`src/middleware.ts:149` gates `/internal/:path*` with a 401 for anything lacking
the `anticipy_internal_gate` cookie. **Google's, Apple's and Outlook's calendar
fetchers will never have that cookie.** That is precisely why the feed is served
from the Railway origin today and why `/internal/me` prints a
`RAILWAY_PUBLIC_DOMAIN` URL (`:3528-3529`).

Three options, and one of them has to be chosen deliberately:

| Option | Cost |
|---|---|
| **(a) Move the feed to `/cal/{token}.ics`** — outside the middleware matcher — and change `cal_url` in route 27 to match. | Every already-subscribed calendar stops updating and each person must re-subscribe **once**. They must re-subscribe anyway: their current URL is a Railway hostname that is about to stop existing. **Recommended.** |
| (b) Add `/internal/cal/:path*` as an exception inside `src/middleware.ts`. | Keeps the path, punches a documented hole in a gate whose whole point (`src/middleware.ts:145-148`, bug B061) is that no URL under `/internal` answers 200 without the cookie. |
| (c) Serve it from a separate hostname. | Reintroduces the cross-origin problem §1.1 deletes. |

Whichever is chosen, **route 27 (`/internal/me`) must stop reading
`RAILWAY_PUBLIC_DOMAIN`.** That variable will not exist. Left as-is it silently
prints `https://undefined/internal/cal/…` — the page keeps rendering, the button
keeps working, and the URL is garbage.

---

## 7. Serving the 136 KB SPA

```js
// :4253-4256
const path = $os.getenv("ANTICIPY_HQ_PAGE") || "pb_public/internal.html";
let html = "";
try { html = String(toString($os.readFile(path))); } catch (_) {}
if (html.length < 200 || html.toLowerCase().indexOf("<!doctype") < 0) { … 503 … }
```

`backend/pb_public/internal.html` is 136,244 bytes and is served by two paths
today: `GET /fellows/hq` (route 38) and `next.config.mjs:101`
(`/internal` → `${FELLOWSHIP_ORIGIN}/internal.html`).

**On Workers this becomes a static asset**, which the site Worker already has:
`wrangler.jsonc:9-12` binds `.open-next/assets` as `ASSETS`. Put the file at
`public/internal.html` and it is served from the edge with an ETag, with **zero
Worker CPU**. `$os.readFile` on every request is a per-request disk read that
existed only because PocketBase had no other way.

Three details that must survive the move:

1. **`X-Robots-Tag: noindex, nofollow`** (`:4274`). The page ships no data and no
   secrets — everything it shows it fetches through the keyed or session routes —
   which is *"what makes it safe to serve from a public prefix at all"*
   (`:4271-4273`). Set it in `next.config.mjs`'s `headers()` for `/internal.html`,
   or keep a route handler that streams the asset and adds it.
2. **Fail visibly, not partly** (`:4257-4267`). *"A page that renders with its
   script missing looks like a broken product; a page that says it could not load
   looks like a thing to go and fix."* With Static Assets, "missing" is a 404
   rather than half a page — which satisfies the intent. If a route handler is
   used instead, keep the `< 200 bytes || no <!doctype>` check and the 503.
3. **`GET /fellows/hq` (route 38) must keep answering.** It is a bookmarked URL
   and `internal_hq.pb.js:4200-4207` explains that `/internal.html` at the edge
   *"is a 404 and always has been."* Port it as a permanent redirect to
   `/internal`, or as a second asset path. Do not simply drop it.

**Also inventory `backend/pb_public/`** — `internal.html` is not alone. It holds
three 277 KB extension zips, `mac.html`, `mac/`, `privacy.html`, `setup.html`,
`site.css`, `theme.js`. Those are download targets for real clients. They are
not HQ's problem, but they are on the same volume and they die with it. Route
them to R2 or `public/` before Railway is switched off.

---

## 8. The crons on Workers

```jsonc
// repo-root wrangler.jsonc — add
"triggers": { "crons": ["*/5 * * * *", "17 4 * * *"] }
```

```ts
// src/app/... has no scheduled handler; OpenNext generates the Worker entry, so
// the cron handler is added in open-next.config.ts or in a thin wrapper around
// .open-next/worker.js. VERIFY THIS FIRST — see §11.
export default {
  async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext) {
    if (controller.cron === "*/5 * * * *") ctx.waitUntil(hqSweep(env));
    if (controller.cron === "17 4 * * *")  ctx.waitUntil(hqPrune(env));
  },
};
```

Two things the sweep does that a naive port loses:

* **`internal_hq.pb.js:2139-2636` is 497 lines with six passes.** Port them as
  six functions, each independently failure-swallowed the way the original is
  (`:2648` — *"prune failed"* is logged, never thrown), so one broken pass cannot
  stop the reminder that matters.
* **The `$http.send` calls to Twilio (`:2170-2171`) and Resend (`:2189-2190`)
  become `fetch`, and they are now subrequests.** A sweep across a growing team
  is bounded by the per-invocation subrequest limit. At three people it is not
  close; write the loop so it pages and can resume, rather than assuming.

The 5-minute cadence and the `17 4 * * *` minute offset both carry meaning — the
prune runs at a quiet hour, off the top of the hour. Keep them.

---

## 9. Seven paths the edge forwards that have no handler in this repo

`next.config.mjs` rewrites these to the Railway origin. **Nothing in
`backend/pb_hooks/` registers any of them, and nothing anywhere in this
repository implements them.** Verified by `grep -rl` across `backend/` and then
across the whole tree (only `next.config.mjs` and `migration/d1/GAPS.md` match).

| Path | next.config.mjs | Handler in repo |
|---|---|---|
| `/internal/people/faces` | 141 | **none** |
| `/internal/me/password` | 142 | **none** |
| `/internal/fellows` | 143 | **none** |
| `/internal/fellows/remove` | 144 | **none** |
| `/internal/fellows/pay` | 149 | **none** |
| `/internal/fellows/submissions/remove` | 150 | **none** |
| `/internal/fellows/submissions/release` | 151 | **none** |

Seven paths, five surfaces. The comments around them are not speculative — they
describe live behaviour:

* `:140` — *"The welcome screen's cast list and the settings password change"*
  → `/internal/people/faces` and `/internal/me/password` are called by a **newer
  HQ page than the one in `backend/pb_public/internal.html`**. The SPA in this
  tree calls neither (`grep -oE "/internal/[a-z/]+" backend/pb_public/internal.html`
  lists 24 paths and none of these). So production is serving a build that is not
  in this repository.
* `:145-148` — *"These three existed in the backend and nowhere here, so past the
  site gate they 404'd at Vercel while answering 401 'wrong key' at the origin —
  alive, and unreachable through the domain. **One of them is the route that pays
  a fellow.**"*

### 9.1 What this means for the migration

**These are unknowable from the repo and require a production listing.** They
cannot be ported, tested, or safely dropped from anything readable here.

`migration/d1/GAPS.md` already carries the fellowship half with real evidence: a
live Cloudflare D1 database `anticipy-fellowship`
(`2f2abfae-9618-45f2-b53d-d302274bcb52`) holds **nine** `fellow_*` tables,
including `fellow_payouts` with `amount_usd`, `commission_usd` and
`idempotency_key` — **all empty**, while the rows still live only in production
PocketBase. Do not duplicate that analysis; extend it.

The concrete asks, in order:

1. **PocketBase superuser credentials.** `GET /api/collections` lists every live
   collection. Diff against `migration/d1/schema.sql`'s 26 and against
   `GAPS.md`'s nine. That answers `/internal/fellows*` completely.
2. **The live `pb_hooks` directory listing.** These seven routes are registered
   by *some* JS file on that instance. If a hook file exists there that is not in
   `backend/pb_hooks/`, this repository is not the source of truth for the
   backend and that fact is bigger than this migration.
3. **The production HQ page.** `curl https://www.anticipy.ai/internal` with a
   valid gate cookie and diff against `backend/pb_public/internal.html`. That
   names every route the real client calls.

**Until 1–3 are answered, `/internal/fellows/pay` must not be switched off.** It
moves money. The other six degrade a screen; that one is a payment path with an
idempotency key, and an idempotency key exists precisely because somebody already
worried about paying twice.

---

## 10. Scars a port must not reopen

Each of these is a comment in the source describing something that actually
happened. They are the acceptance criteria.

| Behaviour | Source | What happened without it |
|---|---|---|
| Missing key → **503**, never open | `:12-15` | a deploy that forgot one variable would publish the team's phone numbers |
| Invalid session → **401 `{reauth:true}`**, never fall through | `:69-72`, `:88` | an expired token silently demotes you to client-asserted identity |
| A session **overwrites** the client's `actor_id` | `:619-625`, `:2694-2697` | a session could impersonate anyone |
| `code_hash` never leaves the server; only `has_code` | `:107-113` | *"a `return p` here would hand every offline cracker the hash of every login code in the building"* |
| `secret_enc` never in `/internal/state` | `:262-264` | *"habits start somewhere"* |
| `signins` are admin-only, and never carry `token_hash` or `ip` | `:294-306` | a hash on the wire is a hash somebody can grind offline |
| Login ceiling **counted before the compare**, fail-closed if it cannot count | `:2744-2766` | a brute-force guard that silently stops counting |
| **One sentence for every login failure** | `:2739-2743` | the login screen becomes an oracle for who is on the team |
| `channels` derived from **env presence**, never a literal | `:22-29` | the Settings page reported "Connected" from a hardcoded string, three times |
| Sweep is **claim-first, then send** | `:2143-2151` | unbounded duplicate texts, every five minutes, forever |
| Comment delete is a **tombstone** | `:3764` | |
| Comment edit stamps `edited_at` | `:3759-3760` | *"the mark that makes the thread honest"* |
| Track delete **orphans nothing** | `:4056` | |
| Session end always answers 200 | `:3468` | whether a token existed is not a thing that route reports |
| The datetime `Z` shim | `:78-79` | `NaN` in a comparison rejects **every** session |
| CORS origin allow-list, never `*` | `:4220-4223` | any page a teammate visits could be taught to ask this API questions |

`migration/spec/contract_tests.py` is the executable half. Run it against
PocketBase, record, run it against the Worker, diff. `migration/BLOCKERS.md`
notes that 175 of 189 tests skip without `ANTICIPY_SERVICE_TOKEN` — **that token
is a prerequisite for this port, not a nicety.** Fourteen green tests is not the
conformance proof; it is the shape of one.

---

## 11. Unverified

1. **`$security.encrypt`'s wire format.** No PocketBase Go source is vendored in
   this tree and none is on this machine. I did not guess at it, and
   `migration/runbooks/reencrypt_vault.md` is correct to forbid guessing. §5 is
   written on the assumption that the bytes are opaque.
2. **`$security.parseJWT`'s exact validation.** `:3402` says it *"enforces exp"*.
   I could not read the implementation, so §4.4's replacement enforces `exp`
   explicitly rather than relying on the claim. Whether it also checks `nbf`,
   `iat` or `aud` is unknown — check before assuming parity.
3. **`crypto.subtle.timingSafeEqual` on workerd.** Present in Cloudflare's
   runtime as far as I know, but not executed here. If unavailable, the fallback
   is a constant-time byte loop over the two SHA-256 digests; the digest-first
   step in §4.1 is what makes either correct.
4. **The `scheduled()` handler under OpenNext.** §8 shows the Worker-level shape.
   How `@opennextjs/cloudflare@1.15.1` exposes a cron handler alongside the
   generated `.open-next/worker.js` I did not verify. Check `open-next.config.ts`
   support before assuming the crons can live in the same Worker; if they cannot,
   a small second Worker for **the crons only** is the fallback — and that is a
   different thing from putting HQ's routes in a second Worker.
5. **D1 row-count and query-shape parity.** `/internal/state` issues 13 reads
   with `perPage` between 10 (`:299`) and 500 (`:252`) (`:106`, `:153`, `:209`, `:252`, `:261`, `:273`, `:299`).
   Whether that fits a single Worker invocation's D1 budget at production data
   volumes was not measured. It is the most read-heavy route in the file and the
   first place to look if the port is slow.
6. **The 401-vs-cookie interaction for the ICS feed** (§6.1). I read
   `src/middleware.ts:149-185` and `internal_hq.pb.js:2875-2878`; I did not
   observe a real calendar client being refused.
7. **The seven routes in §9.** Not in this repository in any form. Everything
   said about them comes from `next.config.mjs`'s own comments and from
   `migration/d1/GAPS.md`.
8. **Whether production runs this file at all.** §9 shows the live HQ page calls
   at least two routes that no code here registers. Treat
   `backend/pb_hooks/internal_hq.pb.js` as *a* version of HQ, not necessarily
   *the deployed* one, until item 2 of §9.1 is answered.
