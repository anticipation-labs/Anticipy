# ROTATION.md — what is exposed, ranked, with the action for each

**The repository is public**: `github.com/anticipation-labs/Anticipy`
(`git remote -v`). Everything in the working tree and everything in the commit
history of every branch has been readable by anyone, for as long as it has been
pushed. Deleting a file does not unpublish it; force-pushing does not unpublish
it. **Rotation is the only remediation. History cleanup is hygiene that comes
after.**

**No secret VALUE appears in this file.** Each item is identified by its
`file:line` and by what it is. Values were verified by length and by hashing —
never printed. Where a value's identity had to be confirmed as byte-identical
to a historical one, that was done with `shasum` on both and comparing the
digests, not by displaying either.

Companion: `SECRETS.md` (the full inventory and the Cloudflare storage design).

---

## The ranking

| # | Item | Exposure | Urgency | One-line action |
|---|---|---|---|---|
| 1 | Cerebras API key, full value, **still in the working tree** | public repo, 7 commits, since 2026-05-30 | **P0 — today** | Revoke at Cerebras, then scrub the two lines |
| 2 | The owner's real extension access code, which unlocks five live LLM keys | public repo, 6 files, since 2026-05-09 | **P0 — today** | Invalidate the code in `engine_users`, rotate all five keys, make the endpoint a proxy |
| 3 | `devin-anticipy` SSH key + permanent `bore.pub` tunnel on any Mac that ran `mac.sh` | served unauthenticated 2026-08-04 → 2026-08-24 (20 days) | **P0 — today, per machine** | Run §3's revocation on every affected Mac |
| 4 | Apple code-signing identity exported by `mac2.sh` with its password in a world-readable-by-tunnel file | same 20-day window, on any Mac that ran both | **P0 if both were run** | Revoke and reissue the certificate |
| 5 | Three hardcoded default HMAC secrets in shipped source | public repo, live now | **P1 — before the first Cloudflare deploy** | Set the real env vars, delete the literals |
| 6 | `NEXT_PUBLIC_CRON_SECRET` — a "secret" compiled into the browser bundle | live now | **P1** | Make `CRON_SECRET ≠ NEXT_PUBLIC_CRON_SECRET`, or delete the client caller |
| 7 | The former production `/analytics` password, now a dev literal at `src/lib/analytics-auth.ts:41` | public repo, 6 commits, 2026-05-28 → 2026-05-30 | **P1** | Confirm it is used nowhere else and set `ANALYTICS_PASSWORD` |
| 8 | `ANTICIPY_VAULT_KEY` custody | not exposed — but a **single point of total data loss** | **P1 at cutover** | Escrow it before touching the backend |
| 9 | `ANTICIPY_SERVICE_TOKEN` fails open when unset | live now; becomes acute on a fresh Cloudflare env | **P1 — must be fixed in the port** | Invert the polarity in the Worker |
| 10 | Hardcoded default tokens in test/proof harnesses | public repo | **P2** | Make the default a refusal, not a string |
| 11 | Supabase `anon` JWT and project ref in an archived client | public repo | **P2 — verify, don't rotate** | Audit RLS; the key is public by design |
| 12 | 13 `embedded.mobileprovision` files, deleted but in history | public repo | **P3** | Note only; no private key is in them |
| 13 | PostHog project key in a removed doc | public repo | **P3 — no action** | Public by design |

Items 1–4 are real exposures of live credentials. Items 5–9 are latent: they
are not leaks yet, but each becomes one under a condition the migration is
about to create. Items 10–13 are recorded so the next person does not have to
re-derive that they are harmless.

---

## 1. Cerebras API key — still in the working tree (P0)

**What.** A Cerebras Cloud API key (`csk-` prefix, 52 characters).

**Where, right now, on `cloudflare-migration`:**

* `planning/00-handoff/BUG_LIST.md:121` — quoted in full inside the finding
  that reports it.
* `planning/00-handoff/BUG_LIST.md:251` — quoted in full again, in the
  duplicate finding.

I confirmed byte-identity with the value committed in `b9602058` by comparing
SHA-256 digests of the extracted tokens (`2afc2d62506fe1ad…` on both sides).
The bug report that documented the leak reproduced the leak.

**History.** 7 commits contain it:

```
b9602058  Cerebras key in /api/extension/auth response (hardcoded fallback) …
2f2de4d3  Cerebras hardcoded fallback in lib so Vercel routes get free Cerebras …
4e3e2236  bug-hunter: iter 1 — first 65 bugs cataloged …
7ef293c9  bug-hunter: iter 6 — B178-B194 (duplicate Cerebras key in lib/cerebras.ts) …
472fd282  bug-hunter: add executive summary + top 28 P0 findings …
8009497e  overnight: dispatch claude headless per failing CHECK …
ab86f28f  security: fix four confirmed issues found by audit          ← removed it from source
```

`ab86f28f` did the right thing to the source files —
`src/app/api/extension/auth/route.ts:92-97` and `src/lib/cerebras.ts:29-34` now
carry an empty fallback and a comment explaining why. It did not touch the bug
report.

**Action.**

1. **Revoke first, edit second.** Cerebras Cloud → API Keys → delete the key
   whose prefix matches `BUG_LIST.md:121`. Create a replacement only if
   `CEREBRAS_API_KEY` is genuinely still wanted; §2 argues it should not be
   distributed to clients at all.
2. Scrub the two lines. The finding stays; the value goes:

   ```sh
   # From the repo root. Replaces the 52-char csk- token with a placeholder,
   # keeps every other character of the two findings intact.
   perl -i -pe 's/csk-[A-Za-z0-9]{40,}/csk-<REVOKED-SEE-ROTATION-MD>/g' \
     planning/00-handoff/BUG_LIST.md
   git diff --stat planning/00-handoff/BUG_LIST.md   # expect 2 lines changed
   ```
3. Confirm nothing else holds it:

   ```sh
   git grep -lI 'csk-[A-Za-z0-9]\{40,\}' -- . | grep -v node_modules   # expect empty
   ```
4. Add a guard so it cannot come back — see §14.

**Do not** rely on "it was only the free tier". The account can be upgraded, and
a free quota burned by a stranger is a denial of service against your own
product. That reasoning was in the original comment and it is why the key
survived two audits.

---

## 2. The owner's extension access code, and the five keys behind it (P0)

This is the highest-consequence item, because it is a *chain*: a committed
bearer token plus an endpoint that trades that token for five live API keys.

**The endpoint.** `src/app/api/extension/auth/route.ts`:

* `:20-23` — `Access-Control-Allow-Origin: *` on every response from this route.
* `:69` — looks the code up in `engine_users` using
  `SUPABASE_SERVICE_ROLE_KEY`.
* `:88-97` — reads `GROQ_API_KEY`, `GOOGLE_API_KEY`, `MISTRAL_API_KEY`,
  `DEEPSEEK_API_KEY`, `CEREBRAS_API_KEY`.
* `:109-121` — **returns all five as plaintext JSON.**

The only gate is the access code, plus rate limits of 60/min/IP (`:30`) and
200/day/code (`:58`). 200 fetches a day is 200 times more than an attacker
needs; the limits protect the quota, not the keys.

**The committed code.** A code is named in six tracked places:

* `engine/test_real_machine.py:247` — the comment states it is the owner's own
  row: *"Omar's actual user_id (engine_users where access_code='…')"*.
* `engine/test_real_machine.py:249` — assigned to `DEFAULT_ACCESS_CODE`.
* `engine/test_real_machine.py:25` — in the human instructions.
* `engine/test_multi_agent_brain.py:31` — with the comment "Omar's access code".
* `STATUS.md:47` and `AUTONOMY_PLAN.md:95`.
* `src/app/api/extension/auth/route.ts:51` — repeated in a comment explaining
  case normalisation, which also documents that lower- and upper-case both
  authenticate.

Present in 7 commits, earliest `1a83efa3` (2026-05-09). It is an 8-character
lowercase-hex string, from an older generation scheme than the current one
(`src/app/api/extension/access-code/route.ts:7-8` now generates 10 characters
from a 31-symbol alphabet ≈ 49 bits, which is fine — the problem is not
guessability, it is publication).

**Action, in this order.**

1. **Invalidate the code.** In Supabase, on the `engine_users` row whose
   `access_code` matches `engine/test_real_machine.py:249`, replace it with a
   freshly generated one. The generator is already in the tree
   (`src/app/api/extension/access-code/route.ts:10-17`); hitting
   `POST /api/extension/access-code` as that user is the supported path.

2. **Rotate all five provider keys**, because anyone who fetched them still has
   them and invalidating the code does not reach into their machine:

   | Key | Where to rotate |
   |---|---|
   | `GROQ_API_KEY` | console.groq.com → API Keys |
   | `GOOGLE_API_KEY` | Google AI Studio → API keys |
   | `MISTRAL_API_KEY` | console.mistral.ai → API Keys |
   | `DEEPSEEK_API_KEY` | platform.deepseek.com → API keys |
   | `CEREBRAS_API_KEY` | see §1 — revoke, and consider not reissuing |

3. **Scrub the six locations.** The comment at
   `src/app/api/extension/auth/route.ts:51` can make its point with an invented
   example; the tests should read the code from `ANTICIPY_ACCESS_CODE` with no
   default at all (`engine/test_real_machine.py:251` already prefers the env
   var — delete the fallback).

4. **Then fix the shape, or this recurs.** Rotating keys that the endpoint will
   hand out again buys one cycle. The correct fix is the one the backend
   already implements: `backend/pb_hooks/agent_key.pb.js` exposes `/agent/llm`,
   which reads `GEMINI_API_KEY`/`OPENROUTER_API_KEY` at `:202-203`, calls the
   provider server-side, enforces a per-agent meter (`:195-200`) and a model
   allowlist (`:212-215`), and returns **completions**. Port
   `/api/extension/auth` to that shape on the new Worker: it returns a session
   identity and nothing else, and a second route proxies inference. This is a
   migration-shaped change, not a security-cleanup-shaped one, which is exactly
   why now is the moment to make it.

5. While the old shape still exists, tighten `Access-Control-Allow-Origin` from
   `*` to the extension's own origin (`chrome-extension://<id>`). It is a small
   speed bump, not a fix, and it should not delay steps 1–4.

---

## 3. The `devin-anticipy` SSH backdoor (P0, per machine)

**What happened.** `backend/ops/mac.sh` and `mac2.sh` lived at
`backend/pb_public/mac.sh` and `.../mac2.sh` from `0ca38713` (2026-08-04) to
`9fcdf5ae` (2026-08-24) — 20 days. PocketBase serves `pb_public/` as static
files with no gate; nothing in `pb_hooks/` guards that directory. Nothing linked
them (`grep -rn 'mac\.sh' backend/pb_public/` is empty), but the filenames were
in a public repository alongside the recipe.

`backend/ops/README.md` documents this accurately and the move out of
`pb_public/` is confirmed by `backend/Dockerfile:8-10`, which copies only
`pb_migrations`, `pb_public` and `pb_hooks` — `backend/ops/` is not in the
image. **The scripts are no longer reachable. That changes nothing on a Mac
that already ran one**, and the README says so.

**What `mac.sh` leaves behind** (`backend/ops/mac.sh`, line by line):

| Line | Residue |
|---|---|
| `:4` | Remote Login (sshd) enabled |
| `:8` | `/etc/ssh/sshd_config.d/100-anticipy.conf` forcing key-only auth |
| `:13-14` | an `ssh-ed25519` public key commented `devin-anticipy` in `~/.ssh/authorized_keys` |
| `:19` | `bore-cli` installed via Homebrew |
| `:22-34` | `~/.anticipy/tunnel.sh` — an infinite loop |
| `:36-53` | `~/Library/LaunchAgents/ai.anticipy.tunnel.plist`, `RunAtLoad` + `KeepAlive` |
| `:27` | fixed ports 48222 / 48223 / 48224 on `bore.pub`, a relay that needs no account |
| `:48-49` | `/tmp/anticipy-tunnel.log` |
| **`:57-58`** | **`security set-keychain-settings` on the login keychain with no `-l` and no `-t` — the login keychain is left with auto-lock disabled, permanently.** |

The README's revocation block covers the LaunchAgent, the tunnel script and the
authorized key. It does **not** cover `:8` or `:57-58`. Both matter: the sshd
config persists, and an unlocked login keychain is the whole point of having
gotten in.

**Full revocation, on each affected Mac.** Run as the user who ran `mac.sh`;
the `sudo` lines will prompt.

```sh
#!/bin/bash
# Revoke everything backend/ops/mac.sh established. Idempotent.
set -u

# 1. Kill the tunnel and stop it coming back.
launchctl bootout "gui/$(id -u)/ai.anticipy.tunnel" 2>/dev/null
rm -f ~/Library/LaunchAgents/ai.anticipy.tunnel.plist
rm -f ~/.anticipy/tunnel.sh
pkill -f 'bore local 22' 2>/dev/null
rm -f /tmp/anticipy-tunnel.log

# 2. Remove the authorized key (mac.sh:13-14).
if [ -f ~/.ssh/authorized_keys ]; then
  cp ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak.$(date +%s)
  sed -i '' '/devin-anticipy/d' ~/.ssh/authorized_keys
fi
echo "--- remaining authorized keys (comments only) ---"
awk '{print $NF}' ~/.ssh/authorized_keys 2>/dev/null || echo "(none)"

# 3. Remove the sshd drop-in (mac.sh:8) — the README omits this.
sudo rm -f /etc/ssh/sshd_config.d/100-anticipy.conf
sudo launchctl kickstart -k system/com.openssh.sshd 2>/dev/null

# 4. Turn Remote Login back off, IF nothing else on this Mac needs sshd.
sudo systemsetup -getremotelogin
# sudo systemsetup -setremotelogin off      # uncomment once you have checked

# 5. Re-lock the login keychain (mac.sh:57-58 disabled auto-lock permanently).
security set-keychain-settings -l -u -t 3600 ~/Library/Keychains/login.keychain-db
security lock-keychain ~/Library/Keychains/login.keychain-db
security show-keychain-info ~/Library/Keychains/login.keychain-db   # expect a timeout

# 6. Uninstall the tunnel client if nothing else uses it.
command -v bore >/dev/null && echo "bore still installed: brew uninstall bore-cli"
```

**Then check whether it was ever used.** On the same Mac:

```sh
# SSH logins, if any survive in the unified log's retention window.
log show --predicate 'process == "sshd"' --last 30d --info 2>/dev/null \
  | grep -iE 'accepted|publickey' | tail -50
# Anything the tunnel logged before step 1 deleted it is already gone; that is
# itself worth knowing — there is no durable record of who connected.
```

There is no server-side access log for `bore.pub`, and `/tmp/anticipy-tunnel.log`
was overwritten continuously. **Absence of evidence here is not evidence of
absence.** Treat every credential that was reachable from that Mac's shell
during the window as potentially exposed, which is what §4 is about.

**One more thing, and it is not optional.** The private key matching the
`devin-anticipy` public key is held by whoever set this up. Removing the line
from `authorized_keys` removes their access to *this* Mac. If that key is
authorized anywhere else — other laptops, a server, a deploy account — search
for it there too:

```sh
grep -rl 'devin-anticipy' ~/.ssh/ /etc/ssh/ 2>/dev/null
```

---

## 4. The Apple code-signing identity that `mac2.sh` exported (P0 if both ran)

`backend/ops/mac2.sh` was served from the same unauthenticated directory over
the same 20-day window. On a Mac that ran it:

* `:14-16` — a random password is generated and written **in plaintext** to
  `~/.anticipy/build_keychain_pw`, mode 600.
* `:27` — `security export -k "$LOGIN" -t identities -f pkcs12 -P "$PW"` exports
  **every code-signing identity in the login keychain, private keys included**,
  to a PKCS#12 file in `$TMP`.
* `:28-31` — imports it into `~/Library/Keychains/anticipy-build.keychain-db`
  and runs `set-key-partition-list` so `codesign` can use it **without
  prompting**.
* `:29` — `rm -rf "$TMP"` removes the p12, but the build keychain and its
  plaintext password file remain.

Net effect: a shell on that Mac — which §3's tunnel provides — can read
`~/.anticipy/build_keychain_pw` and then export the Apple Developer signing
identity from `anticipy-build.keychain-db` with no prompt. That is the private
key that signs the Mac app users download from `anticipy.ai/app`.

**Action, if a Mac ran both scripts:**

1. Do §3 first. Close the door before inventorying the room.
2. Treat the signing identity as compromised. Apple Developer → Certificates →
   revoke the Developer ID Application / Apple Distribution certificate, create
   a new one, and re-sign and re-notarise the current DMG and the iOS build.
3. Remove the residue:

   ```sh
   security delete-keychain ~/Library/Keychains/anticipy-build.keychain-db 2>/dev/null
   rm -P -f ~/.anticipy/build_keychain_pw 2>/dev/null || rm -f ~/.anticipy/build_keychain_pw
   security list-keychains -d user -s ~/Library/Keychains/login.keychain-db
   security find-identity -v -p codesigning     # expect the new identity only
   ```
4. Check whether the App Store Connect key was on that machine too. CI holds it
   as `ASC_KEY_P8` (`.github/workflows/ios-testflight.yml:38`), but
   `clients/ios/scripts/app_store_connect.py:88` reads `ASC_KEY_PATH` from a
   local file — if a `.p8` was ever left on the affected Mac, revoke it at App
   Store Connect → Users and Access → Integrations → Keys and issue a new one.

If the honest answer is "we do not know whether that Mac ran `mac2.sh`", the
cost of revoking and reissuing a signing certificate is a rebuild. The cost of
being wrong is a signed binary you did not build.

---

## 5. Three hardcoded default HMAC secrets (P1 — before first Cloudflare deploy)

Each is reached only when its environment variables are unset. A brand-new
Cloudflare Worker starts with *every* variable unset, which is precisely why
this is a migration-blocking item rather than a background one.

| File:line | Literal defends | Reached when |
|---|---|---|
| `src/lib/engine-transfer-gate.ts:12` | the engine-transfer gate cookie | `GATE_COOKIE_SECRET` and `JWT_SECRET` both unset |
| `src/lib/confirm-token.ts:30` | confirm-link tokens, 7-day TTL (`:20`) | `JWT_SECRET` and `SUPABASE_SERVICE_ROLE_KEY` both unset |
| `src/lib/analytics-auth.ts:6` | the `/analytics` session cookie | `ANALYTICS_SECRET` and `SUPABASE_SERVICE_ROLE_KEY` both unset |

The literals are in the public repo. Anyone can compute
`HMAC-SHA256(literal, "valid")` and mint a cookie.

There is a second, quieter problem in the same functions: the fallback chains
end at `SUPABASE_SERVICE_ROLE_KEY` before they reach the literal.
`src/lib/confirm-token.ts:28-30`, `src/lib/analytics-auth.ts:4-6` and
`src/lib/gate-cookie.ts:27-29` each reach for the service role key when their
own variable is unset. (`src/lib/engine-transfer-gate.ts:10-12` is the
exception: it chains `GATE_COOKIE_SECRET` → `JWT_SECRET` → its literal, and
never touches the service role key. That is why an unset `JWT_SECRET` puts it
straight onto the public literal.) So in the normal production case — dedicated
variables unset, service role key set — one Supabase credential is silently
HMAC-ing the site gate, the analytics session and every confirm link. That
couples three unrelated rotations to one credential and turns the site into an
HMAC oracle over it.

**Action.**

1. Generate and set all three on `anticipy-web` **before** the first deploy:

   ```sh
   for n in GATE_COOKIE_SECRET JWT_SECRET ANALYTICS_SECRET; do
     openssl rand -hex 32 | tr -d '\n' | wrangler secret put "$n" --name anticipy-web
   done
   ```
2. Delete the three literals and the `SUPABASE_SERVICE_ROLE_KEY` fallbacks.
   Replace each with a hard failure — the polarity `SECRETS.md §8` specifies.
3. Expect the deploy to log everyone out of the gate, the analytics dashboard
   and any outstanding confirm links. That is the change working.

---

## 6. `NEXT_PUBLIC_CRON_SECRET` (P1)

`src/app/crm/settings/page.tsx:150-151` sends `x-cron-secret:
process.env.NEXT_PUBLIC_CRON_SECRET` from a **client component**. Next.js
inlines `NEXT_PUBLIC_*` into the browser bundle at build time. The header that
`src/app/api/cron/daily-digest/route.ts:23` checks against `CRON_SECRET` is
therefore published to every visitor of `/crm/settings` — *if the two variables
hold the same string*.

**Action.** Verify in the Vercel and Railway variable sets whether they are
equal today. Then either:

* delete the client-side trigger and call the cron route from a Cloudflare Cron
  Trigger on `anticipy-web`, which needs no shared string at all (preferred, and
  it is one line of `wrangler.jsonc`); or
* keep the button but have it call an authenticated route that runs the digest
  server-side, so no secret crosses into the bundle.

Set `NEXT_PUBLIC_CRON_SECRET` to nothing at all on Cloudflare. If it must exist
for the build to typecheck, give it a value that is not `CRON_SECRET`.

---

## 7. The former production analytics password (P1)

Introduced at `7e01d9e2` (2026-05-28) as the fallback for
`ANALYTICS_PASSWORD` and live in production until `cef4dd76` (2026-05-30) made
it fail secure in production. `src/lib/analytics-auth.ts:37-41` still uses it as
the **development** default, and its own comment records the history.

It is in 6 commits and remains readable. Its blast radius is the `/analytics`
dashboard only — *unless a human reused it elsewhere*.

**Action.** Set `ANALYTICS_PASSWORD` explicitly on `anticipy-web` (`SECRETS.md
§6a`). Ask the owner directly whether that string was ever used for anything
else — an email account, a provider dashboard, a router — and rotate those if
so. Then delete the dev fallback: a developer who needs `/analytics` locally can
set the variable like everyone else.

Also removed from the tree but still in history from the same period:
`.env.example`. I checked every version of it — the only non-empty values were
`TWILIO_MOCK`, `STEEL_API_URL`, `PORT` and a one-character
`TWILIO_TEST_TO_REAL_NUMBER`. **It was clean.** No action.

---

## 8. `ANTICIPY_VAULT_KEY` — not a leak, a single point of total loss (P1 at cutover)

Nothing about this key is exposed. It is here because the migration is the
moment it is most likely to be destroyed, and destroying it is unrecoverable.

**What it protects.** `internal_passwords.secret_enc`
(`backend/pb_migrations/1700000050_expenses_vault.js:42`, whose header at `:14`
states the column never holds plaintext) is written with `$security.encrypt(…,
vk)` and read with `$security.decrypt(…, vk)` at
`backend/pb_hooks/internal_hq.pb.js:3052` and `:3126`, where
`vk = $os.getenv("ANTICIPY_VAULT_KEY")` and must be exactly 32 characters
(`:3053`, `:3127`). That is PocketBase's Go AES implementation. The ciphertext
is in `data.db`; the key is only in the Railway environment.

**The consequence, stated plainly.** Losing the environment variable is exactly
as destructive as losing the volume. The rows survive and are permanently
unreadable. The code even anticipates it —
`internal_hq.pb.js:3142` returns *"could not decrypt — was the vault key
rotated?"* — but anticipating it is not surviving it.

**A second thing worth knowing.** `internal_hq.pb.js:3143` returns the decrypted
secret as plaintext JSON to any caller holding `ANTICIPY_INTERNAL_KEY`. That
key is shared across the HQ team. It is not a leak, but it means the vault's
real perimeter is one shared string, and it should be rotated whenever anyone
leaves.

**Action, before any backend work.**

1. Copy `ANTICIPY_VAULT_KEY` out of the Railway environment into a password
   manager, in two independent places, labelled with what it decrypts and with
   this file's path. Do this first, today, before anything else in the backend
   migration.
2. **Do not carry the key to D1.** D1 has no `$security.encrypt`, so the
   ciphertext in `secret_enc` is unreadable the moment PocketBase stops running.
   The port has to decrypt with PocketBase's Go AES and re-encrypt under a
   scheme a Worker can read — WebCrypto AES-GCM under a new key, held as a
   Worker secret. Rotating in place is not possible in either system.

   **The step-by-step procedure for this is `migration/runbooks/reencrypt_vault.md`**,
   which builds a temporary gated reveal route, generates
   `ANTICIPY_VAULT_KEY_GCM`, re-wraps every row and verifies the receipt
   independently. Follow it rather than improvising; the ordering it specifies —
   re-encrypt *before* PocketBase is switched off — is the whole point, and
   there is no second chance at it.
3. Add `ANTICIPY_VAULT_KEY_GCM` to the escrow in step 1 as soon as it exists.
   After the cutover it, not `ANTICIPY_VAULT_KEY`, is the key whose loss
   destroys the vault.

The identical hazard applies to two more keys — `ENCRYPTION_KEY`
(`src/lib/google-calendar.ts:6`, wrapping stored Google refresh tokens) and
`PROFILE_ENCRYPTION_KEY` (`engine/app/config.py:126`, a Fernet key over saved
browser cookies). Escrow both the same way, in the same session.

---

## 9. `ANTICIPY_SERVICE_TOKEN` fails open (P1 — a port requirement)

`backend/pb_hooks/guard.pb.js:25-26`:

```js
const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
if (!token) return e.next();
```

Unset variable → the guard passes every request. And `migration/d1/RULES.md`
establishes that 42 rule slots across 11 of the 12 product collections are `""`,
which in PocketBase means *public*. So an unset service token does not degrade
the system, it publishes it: every transcript, job, profile and receipt photo,
to anyone who can guess a URL.

Today the variable is set, so this is latent. It stops being latent the moment
a Worker is deployed before its secrets are, which is a normal thing to do by
accident on day one.

**Action.** Two parts, and the first is not optional.

1. In the Worker, a missing `ANTICIPY_SERVICE_TOKEN` binding must be a refusal:

   ```ts
   // guard.pb.js:26 returned e.next() here. That is the single most dangerous
   // line in the backend: 42 collection rules are "" (public) and this
   // middleware is the only thing standing in front of them.
   if (!env.ANTICIPY_SERVICE_TOKEN) {
     return Response.json({ error: "service is not configured" }, { status: 503 });
   }
   ```
2. Rotate the token itself at cutover, since `anticipy-api` and `anticipy-brain`
   are both being redeployed anyway and a coordinated change is free right now:
   set the new value on `anticipy-brain` first, then `anticipy-api`, then
   confirm the brain still reads (`brain/pb.py:24` is the only consumer in the
   brain) before removing the old one.

Compare with `internal_hq.pb.js:44`, which returns `503` when
`ANTICIPY_INTERNAL_KEY` is missing. The codebase already contains the correct
polarity; it is just not applied uniformly.

---

## 10. Hardcoded default tokens in test and proof harnesses (P2)

Not deployed, but they are real strings in a public repo that name themselves
as credentials, and at least one names a production-shaped default:

| File:line | Variable | Shape of the default |
|---|---|---|
| `proof/test_supervisor_isolation_live.py:19` | `RIG_SERVICE_TOKEN` | a fixed rig secret |
| `proof/day_zero_20.py:42` | `RIG_SERVICE_TOKEN` | a *different* fixed rig secret |
| `proof/test_workflow_security_rig.py:38` | `RIG_SERVICE_TOKEN` | a third fixed value |
| `proof/test_workflow_security_rig.py:39` | `RIG_TWILIO_AUTH_TOKEN` | a fixed fake Twilio token |
| `scripts/v7/plan_execution_validator.py:80` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `scripts/v7/test_vision_surface.py:47` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `scripts/v7/probe_real_surface_extension.py:783` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `scripts/v7/drive_transcript_paste_ui.py:205` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `scripts/v7/drive_computer_mic_ui.py:114` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `engine/app/product/universal_surface_runtime.py:32` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `engine/app/product/surface_dom_extractor.py:36` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `engine/app/product/surface_runtime.py:104` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `desktop/src-tauri/resources/anticipy-bridge.py:80` | `ANTICIPY_TRIGGER_SECRET` | `"local-dev"` |
| `engine/test_meta_monitor.py:283,295` | `META_MONITOR_TEST_SECRET` | `"test-secret"` |

`ANTICIPY_TRIGGER_SECRET` is the more interesting one: it authenticates to a
bridge listening on `127.0.0.1` on the **user's own Mac**. `"local-dev"` is
therefore the shipped default for every install that does not set it — meaning
any local process, including a web page's `fetch` to `127.0.0.1` if the bridge
has permissive CORS, can drive the bridge.

**Action.** Not a rotation. In `desktop/src-tauri/resources/anticipy-bridge.py`,
generate a per-install random secret at first run, store it in `~/.anticipy/`
mode 600, and refuse to start if the variable is neither set nor generatable.
In the three `engine/app/product/*.py` readers and the `scripts/v7/*` drivers,
delete the `"local-dev"` default so a missing secret is an error, not a
silently-shared one. The proof harness rigs can keep fixed values but should
read them from a single module so three files stop disagreeing about what the
rig's token is.

---

## 11. Supabase `anon` key in the archived extension (P2 — verify, do not rotate)

`_archive/legacy_extension_v1/background.js:9` holds a Supabase `anon` JWT, and
`:8` the project URL. Decoding only the payload (never the signature) gives
`{"iss":"supabase","ref":"ogbxpqkmsdrcuilafycn","role":"anon", …}`. The same
project ref is in `CLAUDE.md` and in `NEXT_PUBLIC_SUPABASE_URL` across 32 files.

An `anon` key is **public by Supabase's design** — it ships in every browser
bundle by construction (`SECRETS.md §2b`). Publishing it is not the leak.

**The thing to verify instead:** an `anon` key grants exactly what Row Level
Security permits, so RLS is the entire perimeter. Supabase stays in this
migration (an explicit decision), so this is worth an hour:

```sql
-- In the Supabase SQL editor. Any 'f' here is world-readable/writable
-- to anyone holding the anon key, which is everyone.
select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
order by rowsecurity, tablename;

-- And the policies that are actually in force:
select tablename, policyname, cmd, roles, qual, with_check
from pg_policies
where schemaname = 'public'
order by tablename, cmd;
```

Pay particular attention to `engine_users` — it holds the access codes from §2 —
and to `browser_profiles`, which holds Fernet-encrypted cookies. No rotation
action; if RLS is correct there is nothing to fix, and if it is not, the fix is
policies, not keys.

---

## 12. Thirteen `embedded.mobileprovision` files in history (P3)

`app/ios/build/Anticipy-b18…b30.xcarchive/Products/Applications/Anticipy.app/embedded.mobileprovision`,
added and later deleted, still in history.

A provisioning profile contains the team identifier, the app id, the entitlements,
the device UDIDs on the profile, and the **public** certificates. It does not
contain a private key. The Apple Team ID is public anyway — it is hardcoded at
`.github/workflows/ios-testflight.yml:19`.

**Action.** None required. If the profiles were development profiles, the device
UDIDs of whoever was testing are exposed, which is minor PII rather than a
credential. Add `*.mobileprovision` and `**/build/` to `.gitignore` so build
output stops entering the repo — see §14.

---

## 13. PostHog project key in a removed document (P3)

A 48-character `phc_` token appears in history at `PENDING_FOR_OMAR.md`
(commit `ea084900`). It is not in the working tree.

`phc_` is a PostHog **project API key**: write-only ingest, designed to ship in
the browser, and this repo does exactly that via `NEXT_PUBLIC_POSTHOG_KEY`
(`src/components/PostHogProvider.tsx:8`). **No action.** It would matter only if
it were a personal API key (`phx_`), which it is not.

---

## 14. Stopping the next one

Rotation without a guard buys one cycle. Three cheap, durable measures:

**1. Turn on GitHub's own scanning.** Repository → Settings → Code security:
enable **Secret scanning** and **Push protection**. On a public repository both
are free. Push protection blocks a commit containing a recognised provider key
at `git push` time, which would have stopped items 1 and 13 at the source.
Cerebras (`csk-`) may not be a recognised pattern — add it as a **custom
pattern** (`csk-[A-Za-z0-9]{48}`) at the organisation level.

**2. A pre-commit guard for the patterns this repo has actually leaked.**

```sh
# .githooks/pre-commit — chmod +x, then: git config core.hooksPath .githooks
#!/bin/sh
# Patterns this repository has leaked before. Add, never remove.
if git diff --cached -U0 | grep -nE \
    'csk-[A-Za-z0-9]{40,}|sk-or-v1-[A-Za-z0-9]{40,}|sk-ant-[A-Za-z0-9-]{40,}|sk_live_[A-Za-z0-9]{20,}|whsec_[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{40,}|AKIA[0-9A-Z]{16}|ssh-ed25519 AAAA' \
    >/dev/null; then
  echo "pre-commit: a credential-shaped string is in the staged diff." >&2
  echo "Nothing is printed here on purpose. Run:  git diff --cached" >&2
  exit 1
fi
```

**3. Close the two doors that let build output and operator scripts into a
public tree.** Append to `.gitignore`:

```gitignore
# Signing and provisioning material never belongs in a public repo.
*.mobileprovision
*.p8
*.p12
*.pem
*.pfx
*.keystore
**/build/*.xcarchive/
```

And keep `backend/ops/README.md`'s closing instruction in force: *"Do not put an
operator script back under `pb_public/`."* On Cloudflare the equivalent mistake
is putting one in the Worker's static assets directory, which is served the same
way and just as ungated. Say so in whatever replaces that README.

---

## 15. On rewriting history

Tempting, and mostly beside the point.

`git filter-repo` plus a force-push would remove these strings from the branches
you control. It would not reach: existing clones, forks, GitHub's own cached
object views for old SHAs, Software Heritage and similar archivers, the GitHub
Events API record, or anyone's local `git fsck --lost-found`. **Assume every
value listed above is permanently public and act accordingly — that is what
§§1–4 are for.**

Rewriting is still worth doing for one narrower reason: it stops the next
reader of this repository from finding a live-looking credential and using it.
If you do it:

1. Complete every rotation in §§1–4 first. Never rewrite before revoking; the
   rewrite is the loud part and the revocation is the effective part.
2. Coordinate — every open branch, PR and working copy must be re-cloned. There
   are 15+ `origin/claude/*` branches; they will all need rebasing or deleting.
3. Do it in one pass over all refs, not per-file over time.
4. Afterwards, ask GitHub Support to purge cached views for the affected SHAs.
   Only they can do that.
5. Rotate again if any window opened between the rewrite and the rotation.

Given the count — one live key in the tree (§1), one live access code (§2), and
three public HMAC literals (§5) — the honest cost-benefit is: rotate everything
today, scrub the working tree today, and treat the history rewrite as optional
tidying that must not delay either.

---

## 16. Unverified

* **Whether the repository is public was taken as given** from the task brief
  and from `git remote -v` showing `github.com/anticipation-labs/Anticipy.git`.
  I did not make an unauthenticated request to confirm the visibility setting.
  Everything here is written on that assumption; if the repository is in fact
  private, items 1, 2, 7, 11, 12 and 13 drop by roughly one severity band each
  and items 3 and 4 do not move at all, because those were exposed by
  `pb_public/`, not by GitHub.
* **Whether any Mac actually ran `mac.sh` or `mac2.sh`.** Nothing in this tree
  records that. §§3–4 are written as "on each affected Mac" because the set of
  affected Macs can only be established by asking. If the answer is none, both
  items close immediately.
* **Whether the tunnel was ever connected to.** `bore.pub` keeps no log you can
  read and `/tmp/anticipy-tunnel.log` was continuously overwritten. Unknowable
  from here.
* **Whether the access code in §2 is still live** in `engine_users`. I read the
  code and the comment that identifies it as the owner's; I did not query
  Supabase. Check before assuming it is dead — and note that even if that row is
  gone, step 2 of §2 (rotating the five keys) still stands, because the keys
  were handed out under it.
* **Whether `CRON_SECRET` and `NEXT_PUBLIC_CRON_SECRET` currently hold the same
  value.** Only the deployed variable sets can answer that. §6 gives the action
  for both cases.
* **Prefix coverage.** The value sweep used the provider prefixes this stack
  plausibly uses (`sk_live_`, `sk_test_`, `whsec_`, `sk-or-v1-`, `sk-ant-`,
  `gsk_`, `re_`, `AKIA`, `AC`/`SK` Twilio SIDs, `xox[baprs]-`, `ghp_`/`gho_`/
  `ghs_`/`github_pat_`, `csk-`, `tvly-`, `phc_`, `SG.`, `AIza`, PEM headers,
  `ssh-ed25519`/`ssh-rsa`, `"type": "service_account"`, and hardcoded
  `Authorization: Bearer` literals) across the working tree and, via
  `git log --all -S`, across history. A credential with no recognisable prefix —
  a bare hex or base64 blob assigned to a plainly-named variable — would not be
  caught by prefix matching. The `||`-fallback and `getenv(…, default)` sweeps
  in §5 and §10 are the partial answer to that, but they are not exhaustive.
  A run of `gitleaks detect --no-git` and `trufflehog git file://.` over the
  full history is the right belt-and-braces follow-up; neither tool was
  available in this environment.
* **`Stripe sk_live_` and `whsec_`** matches at commit `c002e92f` were verified
  as **placeholders**, by measuring token length (18 and 16 characters against
  a real Stripe key's 100-plus) and character diversity — not by reading them.
  Likewise the `sk-or-v1-` matches (12 characters — a truncated log prefix) and
  the `tvly-` matches (9 and 11 characters). The `AIza` hits in
  `state/v7/integration_runs/**/proof.json` are substrings of base64 screenshot
  payloads, confirmed by inspecting the 80 characters preceding each match. The
  `service_role` hits in `engine/app/supabase_client.py` are the Python
  parameter name `service_role: bool`, not a key.
