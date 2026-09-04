# Re-encrypt the company vault BEFORE PocketBase is switched off

> ## ⛔ THE ONE-WAY DOOR IN THIS MIGRATION
>
> `internal_passwords.secret_enc` is ciphertext written by PocketBase's **Go**
> `$security.encrypt`, keyed by the environment variable `ANTICIPY_VAULT_KEY`
> — `backend/pb_hooks/internal_hq.pb.js:3079`. The only thing that has ever
> read it back is `$security.decrypt` at
> `backend/pb_hooks/internal_hq.pb.js:3140`, running inside that same
> PocketBase binary.
>
> **Plan on nothing in a Cloudflare Worker being able to open those bytes.**
> The wire format is an undocumented internal of a dependency you are
> decommissioning. Betting the company's tool logins on a guess about its
> nonce placement, key derivation and tag layout is not a migration plan, and
> the guess cannot be re-run after the instance is gone.
>
> **The vault must therefore be re-wrapped on the PocketBase side, while
> `$security.decrypt` still exists, before that instance is decommissioned.**
> There is no later. Once the container is deleted, every row in
> `internal_passwords` is a service name, a username, and noise.
>
> `migration/runbooks/import_d1.py` enforces this: it refuses to import a
> non-empty `secret_enc` unless `<export>/vault/vault_rewrapped.json` — the
> receipt this procedure writes — is present.

**Blast radius if this is skipped:** every company tool login in HQ.
`backend/pb_migrations/1700000050_expenses_vault.js:12-18` describes what is in
there: "the company vault for tool logins". `/internal/state` deliberately
carries metadata only (`internal_hq.pb.js:263`), so there is no second copy
anywhere in the product, and the encrypted column is 2 000 characters wide
(`1700000050_expenses_vault.js:42`) — it is the only copy.

---

## What this procedure does

```
PocketBase ($security.decrypt, ANTICIPY_VAULT_KEY)
        │  plaintext, over TLS, to the operator's machine, never to disk
        ▼
rewrap_vault.mjs   AES-256-GCM · random 12-byte IV · 128-bit tag · AAD = record id
        │  key: ANTICIPY_VAULT_KEY_GCM (32 raw bytes, base64 in env)
        ▼
<export>/vault/vault_rewrapped.json          ← the receipt
        │
        ▼
import_d1.py   writes secret_gcm into D1, and writes secret_enc as ''
        │
        ▼
Worker: crypto.subtle.decrypt({name:"AES-GCM", …})
```

Three properties this shape buys, each of which the current scheme lacks:

1. **A documented, standard format.** AES-256-GCM through `SubtleCrypto` is
   the same primitive on Workers, in Node, in Python and in the browser. The
   token can be opened by a person with the key and no Anticipy code at all.
2. **Ciphertext bound to its row.** The record id is the GCM *additional
   authenticated data*, so a ciphertext copied from one vault row onto another
   fails to decrypt instead of silently revealing the wrong service's password.
   `$security.encrypt` passes no AAD, so today that swap succeeds.
3. **A new key.** `ANTICIPY_VAULT_KEY` has lived in Railway's environment,
   in PocketBase's process memory and in every settings snapshot for the life
   of the service. Cutover is the moment to stop using it.

**Nothing is written back to PocketBase.** This procedure only *reads* the
dying instance. If it goes wrong, re-run it; the source is untouched.

---

## Credentials the owner must supply

| Name | Where it lives | Why |
|---|---|---|
| `PB_SUPERUSER_EMAIL` / `PB_SUPERUSER_PASSWORD` | a `_superusers` record on the live backend | the reveal route below is superuser-gated |
| Railway access to the `backend` service | Railway dashboard / CLI | to set `ANTICIPY_VAULT_REWRAP=1` and redeploy the temporary hook, then remove both |
| `ANTICIPY_VAULT_KEY` | already set on the `backend` service | **you never read or type it.** It stays where it is; PocketBase uses it in-process |
| `ANTICIPY_VAULT_KEY_GCM` | **you generate it in step 2** | the new key. It goes into Cloudflare secrets and into the password manager. If it is lost, so is the vault |

Do not paste any of these into a shell that records history. Use
`read -rs VAR` or a `.env` file with mode `600` that you delete afterwards.

---

## Step 1 — deploy the temporary reveal route

Save as `backend/pb_hooks/vault_rewrap.pb.js`. It is **temporary**; step 6
deletes it.

```js
/// <reference path="../pb_data/types.d.ts" />
//
// TEMPORARY. Exists only for the Cloudflare migration, and only to hand the
// vault's plaintext to the operator once, so it can be re-wrapped in a format
// that outlives this binary. DELETE THIS FILE AND UNSET ANTICIPY_VAULT_REWRAP
// THE MOMENT migration/runbooks/reencrypt_vault.md step 6 is reached.
//
// TWO INDEPENDENT GATES, because one gate on a route that returns every
// company password is not a gate:
//   1. a PocketBase superuser session, and
//   2. ANTICIPY_VAULT_REWRAP=1 in the environment.
// The env flag is the one that is switched off afterwards, so revoking this
// route does not depend on remembering to redeploy.
//
// EVERY CONST IS DECLARED INSIDE THE HANDLER. A top-level const is not in
// scope inside a pb_hooks callback -- the JSVM gives each handler its own
// context. That cost the whole account-delete feature once
// (account_delete.pb.js:42-56) and is warned about again at
// evidence.pb.js:48-53 and password_reset.pb.js:23-26.
routerAdd("POST", "/internal/vault/rewrap-export", (e) => {
  const PAGE = 200;
  const MAX_ROWS = 5000;

  if (String($os.getenv("ANTICIPY_VAULT_REWRAP") || "") !== "1") {
    return e.json(404, { error: "not found" });
  }
  // Ordering matters: PocketBase's load-auth-token middleware fills e.auth for
  // ANY auth record, superusers included, so a bare `if (e.auth)` is not a
  // superuser check (guard.pb.js:383-392).
  let su = false;
  try { su = e.hasSuperuserAuth(); } catch (_) { su = false; }
  if (!su) return e.json(401, { error: "superuser only" });

  const vk = $os.getenv("ANTICIPY_VAULT_KEY") || "";
  if (vk.length !== 32) return e.json(503, { error: "the vault is not configured" });

  const items = [];
  let offset = 0;
  while (offset < MAX_ROWS) {
    let rows = [];
    // Same call shape as worker_owners.pb.js:20, which is proven on 0.30.4.
    try {
      rows = e.app.findRecordsByFilter("internal_passwords", "id != ''", "+id", PAGE, offset);
    } catch (err) {
      return e.json(500, { error: "could not read the vault: " + String(err) });
    }
    if (!rows || rows.length === 0) break;
    for (const row of rows) {
      const id = row.get("id");
      const service = row.getString("service") || "";
      const enc = row.getString("secret_enc") || "";
      if (enc === "") { items.push({ id: id, service: service, secret: "" }); continue; }
      // A row that will not decrypt HERE will never decrypt anywhere. Report
      // it as an error rather than dropping it, so the operator finds out now
      // -- while the key and the binary both still exist -- instead of after
      // the container is deleted.
      try {
        items.push({ id: id, service: service, secret: $security.decrypt(enc, vk) });
      } catch (err) {
        items.push({ id: id, service: service, error: String(err) });
      }
    }
    if (rows.length < PAGE) break;
    offset += PAGE;
  }
  console.log("vault rewrap export: handed out " + items.length + " row(s)");
  return e.json(200, { count: items.length, items: items });
});
```

Set `ANTICIPY_VAULT_REWRAP=1` on the `backend` service, then deploy. The
backend deploys from a **git-free copy** — `railway up` from `backend/` uploads
the git root and the builder cannot find the `Dockerfile`
(`ORCHESTRATOR-HANDOFF.md:216-221`):

```sh
rm -rf /tmp/backend-deploy
cp -R backend /tmp/backend-deploy
cd /tmp/backend-deploy
railway link --project anticipy-production
railway service backend
railway up --service backend
```

Confirm the route exists and is gated (expect `401`, not `404`):

```sh
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$PB_URL/internal/vault/rewrap-export"
```

`404` means the env flag is not set or the hook did not deploy. `401` is the
correct answer to an unauthenticated caller.

---

## Step 2 — generate the new key

```sh
export ANTICIPY_VAULT_KEY_GCM="$(openssl rand -base64 32)"
```

Put it in the team password manager **now**, before it is used for anything.
It will also become a Cloudflare secret:

```sh
# after the Worker exists
wrangler secret put ANTICIPY_VAULT_KEY_GCM
```

The receipt records a *fingerprint* — `sha256("anticipy-vault-key-id" ‖ key)`,
first 16 hex — so a later operator can tell which key a ciphertext belongs to
without holding the key. The key itself is never written to any file this
procedure produces.

---

## Step 3 — write the re-wrap tool

Save as `migration/runbooks/rewrap_vault.mjs` (Node 18+; uses `node:crypto`
only — no npm install):

```sh
cat > migration/runbooks/rewrap_vault.mjs <<'REWRAP_EOF'
#!/usr/bin/env node
// rewrap_vault.mjs -- take the company vault out of PocketBase's Go crypto and
// put it into a format a Worker can open, WITHOUT writing plaintext to disk.
//
//   node rewrap_vault.mjs <export-dir>
//
// env: PB_URL, PB_SUPERUSER_EMAIL, PB_SUPERUSER_PASSWORD,
//      ANTICIPY_VAULT_KEY_GCM  (base64 of 32 random bytes; `openssl rand -base64 32`)
import { createCipheriv, randomBytes, createHash, webcrypto, timingSafeEqual } from "node:crypto";
import { mkdirSync, writeFileSync, chmodSync } from "node:fs";
import { join } from "node:path";

const die = (m) => { console.error("FATAL: " + m); process.exit(2); };
const exportDir = process.argv[2] || die("usage: node rewrap_vault.mjs <export-dir>");
const PB = (process.env.PB_URL || "").replace(/\/+$/, "") || die("PB_URL is not set");
const EMAIL = process.env.PB_SUPERUSER_EMAIL || die("PB_SUPERUSER_EMAIL is not set");
const PASS = process.env.PB_SUPERUSER_PASSWORD || die("PB_SUPERUSER_PASSWORD is not set");
const KEY_B64 = process.env.ANTICIPY_VAULT_KEY_GCM || die("ANTICIPY_VAULT_KEY_GCM is not set");
if (!/^https:/.test(PB) && !/^http:\/\/(127\.0\.0\.1|localhost)/.test(PB)) {
  die("PB_URL must be https -- plaintext secrets cross this connection");
}
const KEY = Buffer.from(KEY_B64, "base64");
if (KEY.length !== 32) die("ANTICIPY_VAULT_KEY_GCM must decode to exactly 32 bytes, got " + KEY.length);

const b64u = (b) => Buffer.from(b).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const b64uDec = (s) => Uint8Array.from(Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64"));

function seal(plain, aad) {
  const iv = randomBytes(12);
  const c = createCipheriv("aes-256-gcm", KEY, iv);
  c.setAAD(Buffer.from(aad, "utf8"));
  const ct = Buffer.concat([c.update(Buffer.from(plain, "utf8")), c.final()]);
  return "v1." + b64u(iv) + "." + b64u(Buffer.concat([ct, c.getAuthTag()]));
}

// The verification below runs through WebCrypto on purpose: it is the same
// SubtleCrypto the Worker will use, so a token that opens here is a token that
// opens in production. A rewrap proven only against the library that wrote it
// has proven nothing.
async function open_(token, aad) {
  const [v, ivB, ctB] = String(token).split(".");
  if (v !== "v1") throw new Error("unknown vault token version: " + v);
  const k = await webcrypto.subtle.importKey("raw", KEY, { name: "AES-GCM" }, false, ["decrypt"]);
  const pt = await webcrypto.subtle.decrypt(
    { name: "AES-GCM", iv: b64uDec(ivB), additionalData: new TextEncoder().encode(aad), tagLength: 128 },
    k, b64uDec(ctB));
  return new TextDecoder().decode(pt);
}

const auth = await fetch(`${PB}/api/collections/_superusers/auth-with-password`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ identity: EMAIL, password: PASS }),
});
if (!auth.ok) die(`superuser sign-in failed: HTTP ${auth.status}`);
const token = (await auth.json()).token;
if (!token) die("superuser sign-in returned no token");

const res = await fetch(`${PB}/internal/vault/rewrap-export`, {
  method: "POST", headers: { Authorization: token, "Content-Type": "application/json" },
  body: "{}",
});
if (res.status === 404) {
  die("POST /internal/vault/rewrap-export is not deployed. Add backend/pb_hooks/vault_rewrap.pb.js\n" +
      "       and set ANTICIPY_VAULT_REWRAP=1 on the backend service, then redeploy. See reencrypt_vault.md.");
}
if (!res.ok) die(`rewrap-export refused: HTTP ${res.status} ${(await res.text()).slice(0, 300)}`);
const payload = await res.json();
const rows = payload.items || [];
if (!Array.isArray(rows)) die("rewrap-export did not return an items array");

const items = [];
const failures = [];
for (const row of rows) {
  const id = String(row.id || "");
  if (!id) { failures.push({ id: "(none)", why: "row has no id" }); continue; }
  if (row.error) { failures.push({ id, why: "PocketBase could not decrypt it: " + row.error }); continue; }
  const secret = String(row.secret ?? "");
  if (secret === "") { items.push({ id, service: row.service || "", secret_gcm: "" }); continue; }
  const tok = seal(secret, id);
  let back;
  try { back = await open_(tok, id); }
  catch (e) { failures.push({ id, why: "WebCrypto could not reopen the token: " + e.message }); continue; }
  const a = Buffer.from(back, "utf8"), b = Buffer.from(secret, "utf8");
  if (a.length !== b.length || !timingSafeEqual(a, b)) {
    failures.push({ id, why: "round trip did not match" }); continue;
  }
  items.push({ id, service: row.service || "", secret_gcm: tok });
}

if (failures.length) {
  for (const f of failures) console.error(`  ! ${f.id}: ${f.why}`);
  die(`${failures.length} of ${rows.length} vault row(s) did not re-wrap. Nothing was written.`);
}

const fingerprint = createHash("sha256")
  .update(Buffer.concat([Buffer.from("anticipy-vault-key-id"), KEY])).digest("hex").slice(0, 16);

const out = {
  format: "anticipy-vault-gcm-1",
  created_at: new Date().toISOString(),
  algorithm: "AES-256-GCM, 12-byte random IV, 128-bit tag, AAD = the record id",
  token_shape: "v1.<base64url iv>.<base64url ciphertext||tag>",
  key_env: "ANTICIPY_VAULT_KEY_GCM",
  key_fingerprint: fingerprint,       // sha256("anticipy-vault-key-id"||key), NOT the key
  source_rows: rows.length,
  items,
};
const dir = join(exportDir, "vault");
mkdirSync(dir, { recursive: true, mode: 0o700 });
const path = join(dir, "vault_rewrapped.json");
writeFileSync(path, JSON.stringify(out, null, 2) + "\n", { mode: 0o600 });
chmodSync(path, 0o600);
console.error(`re-wrapped ${items.length} vault row(s) -> ${path}`);
console.error(`key fingerprint ${fingerprint} -- record this where the key itself is stored`);
console.error("no plaintext was written to disk by this script.");
REWRAP_EOF
```

---

## Step 4 — run it

Run it against the same export directory `export_pocketbase.sh` wrote, so the
receipt travels with the data it belongs to.

```sh
export PB_URL="https://<the live backend>"
read -rs PB_SUPERUSER_EMAIL     # or set from a mode-600 env file
read -rs PB_SUPERUSER_PASSWORD
export PB_SUPERUSER_EMAIL PB_SUPERUSER_PASSWORD

node migration/runbooks/rewrap_vault.mjs ~/anticipy-export-YYYYMMDD
```

Expected output:

```
re-wrapped N vault row(s) -> ~/anticipy-export-YYYYMMDD/vault/vault_rewrapped.json
key fingerprint 0123456789abcdef -- record this where the key itself is stored
no plaintext was written to disk by this script.
```

If any row reports `PocketBase could not decrypt it`, **stop.** That row was
already unreadable before the migration started — most likely
`ANTICIPY_VAULT_KEY` was rotated at some point without re-encrypting
(`internal_hq.pb.js:3141` anticipates exactly this: *"could not decrypt — was
the vault key rotated?"*). Nothing is written, and you now know, while the old
instance is still alive, that the plaintext has to be re-entered by hand from
whoever owns that tool.

**The script writes no plaintext to disk. Do not add a `--dump` flag.**

---

## Step 5 — verify the receipt independently

Never trust the writer to grade its own work. This opens the receipt with a
second implementation:

```sh
node --input-type=module -e '
import { readFileSync } from "node:fs";
const r = JSON.parse(readFileSync(process.argv[1], "utf8"));
const key = Buffer.from(process.env.ANTICIPY_VAULT_KEY_GCM, "base64");
const dec = (s) => Uint8Array.from(Buffer.from(s.replace(/-/g,"+").replace(/_/g,"/"), "base64"));
let ok = 0, empty = 0;
for (const it of r.items) {
  if (!it.secret_gcm) { empty++; continue; }
  const [v, iv, ct] = it.secret_gcm.split(".");
  if (v !== "v1") throw new Error("bad version on " + it.id);
  const k = await crypto.subtle.importKey("raw", key, {name:"AES-GCM"}, false, ["decrypt"]);
  const pt = await crypto.subtle.decrypt(
    {name:"AES-GCM", iv: dec(iv), additionalData: new TextEncoder().encode(it.id), tagLength:128}, k, dec(ct));
  if (new TextDecoder().decode(pt).length === 0) throw new Error("empty plaintext on " + it.id);
  ok++;
}
console.log(`opened ${ok} secret(s), ${empty} row(s) legitimately empty, of ${r.source_rows} source row(s)`);
' ~/anticipy-export-YYYYMMDD/vault/vault_rewrapped.json
```

Then prove the binding actually binds — this **must** throw:

```sh
node --input-type=module -e '
import { readFileSync } from "node:fs";
const r = JSON.parse(readFileSync(process.argv[1], "utf8"));
const it = r.items.find(x => x.secret_gcm);
const key = Buffer.from(process.env.ANTICIPY_VAULT_KEY_GCM, "base64");
const dec = (s) => Uint8Array.from(Buffer.from(s.replace(/-/g,"+").replace(/_/g,"/"), "base64"));
const [, iv, ct] = it.secret_gcm.split(".");
const k = await crypto.subtle.importKey("raw", key, {name:"AES-GCM"}, false, ["decrypt"]);
try {
  await crypto.subtle.decrypt({name:"AES-GCM", iv: dec(iv),
    additionalData: new TextEncoder().encode("not-this-row"), tagLength:128}, k, dec(ct));
  console.log("FAIL: the ciphertext is NOT bound to its row");
  process.exit(1);
} catch { console.log("ok: ciphertext is bound to its record id"); }
' ~/anticipy-export-YYYYMMDD/vault/vault_rewrapped.json
```

Acceptance gate — all three must hold before step 6:

- [ ] `opened N secret(s)` where `N` equals the number of non-empty
      `secret_enc` values seen in `records/internal_passwords.ndjson`
- [ ] `ok: ciphertext is bound to its record id`
- [ ] `ANTICIPY_VAULT_KEY_GCM` is in the team password manager, and its
      fingerprint matches `key_fingerprint` in the receipt

Count the source side with:

```sh
jq -r 'select((.secret_enc // "") != "") | .id' \
  ~/anticipy-export-YYYYMMDD/records/internal_passwords.ndjson | wc -l
```

---

## Step 6 — close the door

Do this the same day. A route that hands out every company password is not
allowed to outlive its errand.

```sh
# 1. remove the env flag on the backend service (this alone kills the route: it
#    answers 404 without ANTICIPY_VAULT_REWRAP=1)
railway variables --service backend --unset ANTICIPY_VAULT_REWRAP   # verify the exact
                                                                    # flag with `railway variables --help`

# 2. delete the hook and redeploy from the git-free copy
rm -f backend/pb_hooks/vault_rewrap.pb.js
rm -rf /tmp/backend-deploy && cp -R backend /tmp/backend-deploy
cd /tmp/backend-deploy && railway link --project anticipy-production \
  && railway service backend && railway up --service backend

# 3. prove it is gone
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$PB_URL/internal/vault/rewrap-export"   # expect 404

# 4. clear the plaintext-adjacent shell
unset PB_SUPERUSER_PASSWORD PB_SUPERUSER_EMAIL
```

`ANTICIPY_VAULT_KEY` itself can stay on the backend until the service is
deleted — it is doing no harm and removing it breaks
`/internal/passwords/reveal` for anyone still on the old HQ.

---

## Step 7 — the Worker side

`import_d1.py` puts the token in `internal_passwords.secret_gcm` and writes
`secret_enc` as an empty string. This is the reader. It has been round-tripped
against tokens produced by `rewrap_vault.mjs`.

```ts
// src/vault.ts -- opening a re-wrapped vault entry inside a Worker.
//
// Token shape: v1.<base64url iv>.<base64url ciphertext||tag>
// AES-256-GCM, 12-byte IV, 128-bit tag, AAD = the record id.
//
// The AAD is why `id` is a parameter and not a convenience: a ciphertext lifted
// from another row will not open, so a row-id mix-up upstream fails loudly
// instead of revealing the wrong service's password.

const b64urlToBytes = (s: string): Uint8Array => {
  const padded = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
};

let cachedKey: CryptoKey | null = null;

async function vaultKey(env: { ANTICIPY_VAULT_KEY_GCM: string }): Promise<CryptoKey> {
  if (cachedKey) return cachedKey;
  const raw = b64urlToBytes(env.ANTICIPY_VAULT_KEY_GCM.replace(/\+/g, "-").replace(/\//g, "_"));
  if (raw.byteLength !== 32) {
    throw new Error("ANTICIPY_VAULT_KEY_GCM must decode to exactly 32 bytes");
  }
  cachedKey = await crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["decrypt"]);
  return cachedKey;
}

/** Returns the plaintext secret, or "" when the row legitimately holds none. */
export async function openVaultSecret(
  env: { ANTICIPY_VAULT_KEY_GCM: string },
  recordId: string,
  token: string,
): Promise<string> {
  if (!token) return "";
  const parts = token.split(".");
  if (parts.length !== 3 || parts[0] !== "v1") {
    // A row still holding PocketBase's old ciphertext lands here. Say so
    // precisely: "wrong password" would send someone hunting the wrong bug.
    throw new Error(
      `vault row ${recordId} is not in the v1 GCM format; it was never re-wrapped ` +
      `(see migration/runbooks/reencrypt_vault.md)`,
    );
  }
  const key = await vaultKey(env);
  const plain = await crypto.subtle.decrypt(
    {
      name: "AES-GCM",
      iv: b64urlToBytes(parts[1]),
      additionalData: new TextEncoder().encode(recordId),
      tagLength: 128,
    },
    key,
    b64urlToBytes(parts[2]),
  );
  return new TextDecoder().decode(plain);
}
```

Writing a *new* secret from the Worker is the same primitive in reverse:

```ts
export async function sealVaultSecret(
  env: { ANTICIPY_VAULT_KEY_GCM: string },
  recordId: string,
  secret: string,
): Promise<string> {
  const raw = b64urlToBytes(env.ANTICIPY_VAULT_KEY_GCM.replace(/\+/g, "-").replace(/\//g, "_"));
  const key = await crypto.subtle.importKey("raw", raw, { name: "AES-GCM" }, false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = new Uint8Array(await crypto.subtle.encrypt(
    { name: "AES-GCM", iv, additionalData: new TextEncoder().encode(recordId), tagLength: 128 },
    key,
    new TextEncoder().encode(secret),
  ));
  const b64u = (b: Uint8Array) =>
    btoa(String.fromCharCode(...b)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `v1.${b64u(iv)}.${b64u(ct)}`;
}
```

Two rules that carry over from the PocketBase implementation and must not be
dropped:

- **Never put the secret in list state.** `internal_hq.pb.js:263` — "Metadata
  only. `secret_enc` never rides in state." The Worker's `/internal/state`
  equivalent returns service, username, url and notes; the secret leaves only
  through a per-item reveal call by a signed-in teammate.
- **An empty `secret` on an update means "keep what is there."**
  `internal_hq.pb.js:3077-3082` — an edit that fixes a typo in the URL must
  never blank the password.

---

## Ordering against the rest of the migration

```
freeze writes ─▶ export_pocketbase.sh ─▶ rewrap_vault.mjs ─▶ import_d1.py ─▶ cutover ─▶ decommission
                        │                      │                  │
                        │                      └── writes vault/vault_rewrapped.json
                        └── records/internal_passwords.ndjson (secret_enc, unreadable)
                                               │
                     import_d1.py REFUSES to proceed without the receipt ◀────┘
```

The rewrap can be done any time before decommissioning, and can be re-run
freely — it only reads. It **cannot** be done after. If cutover slips by weeks
and someone adds a vault entry through the old HQ in the meantime, re-run
steps 1–6; the receipt is regenerated from scratch each time, and the new key
can be the same one (its fingerprint will match).

---

## Unverified

- The exact wire format of PocketBase 0.30.4's `$security.encrypt` was not
  read: the binary is fetched at image build time
  (`backend/Dockerfile:3-6`) and is not in this tree. The claim in the banner
  is therefore stated as a *plan*, not a proof: **do not rely on a Worker
  being able to read `secret_enc`.** If someone later demonstrates a
  byte-exact decrypt of a real `secret_enc` value from a Worker, that changes
  nothing about this procedure — the vault still gets a documented format, an
  AAD binding and a fresh key, none of which the old ciphertext has.
- The precise `railway variables --unset` flag spelling was not verified
  against the installed Railway CLI. Confirm with `railway variables --help`,
  or remove the variable in the Railway dashboard.
- `crypto.subtle` availability in the Workers runtime and `atob`/`btoa` in the
  Workers global scope are assumed from the Web Platform surface Workers
  implement; the code above was round-tripped on Node 24's `webcrypto`, which
  is the same SubtleCrypto API but not the same runtime.
