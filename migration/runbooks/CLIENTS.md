# CLIENTS — who is holding the old address, and how each one lets go

Measured 2026-09-03 against the merged tree on `cloudflare-migration`. Every
row was read, not inferred; every claim carries `file:line`.

---

## The finding, before the tables

**Two clients cannot be repointed by any deploy you make.** The iPhone app and
the Mac app have `backend-production-61e0a.up.railway.app` compiled into
binaries that are already on people's devices, and neither has a setting, a
deep link, a remote config, or an environment variable that can change it. For
those two, the only repointing mechanism is *ship a new build and wait for the
user to install it.*

Everything else — the extension, the firmware, the website, the brain, the
harnesses — can be repointed the same day.

**Therefore the old address must keep answering until the last iPhone and the
last Mac have taken a new build.** That is not a scheduling preference; it is
the shape of the problem. The rest of this document is about making that
window short, safe, and — this is the part that matters — *never necessary
again.*

---

## §1. Every hardcoded backend URL

### 1.1 Baked into shipped binaries — CANNOT be repointed remotely

| File:line | What it is |
|---|---|
| `clients/ios/Anticipy/AnticipyApp.swift:554` | `@AppStorage("backendURL")` default — the app-wide value |
| `clients/ios/Anticipy/AnticipyApp.swift:728` | fallback if the stored string fails to parse as a URL |
| `clients/ios/Anticipy/Views/SettingsView.swift:13` | same key, second declaration |
| `clients/ios/Anticipy/Views/SettingsView.swift:726` | privacy link, `…/privacy.html` |
| `clients/ios/Anticipy/Views/SettingsAdvancedView.swift:12` | same key, `#if DEBUG` only |
| `clients/ios/Anticipy/Views/SettingsConnectorsView.swift:85` | same key |
| `clients/ios/Anticipy/Views/SettingsConnectorsView.swift:190` | same key |
| `clients/ios/Anticipy/Views/OnboardingView.swift:103` | same key |
| `clients/macos/AnticipyMac/PocketBase.swift:78` | `init(baseURL: URL = …railway.app)` default argument |

**Why iOS is genuinely stuck.** `@AppStorage("backendURL")` reads UserDefaults,
so a *stored* value would win — but nothing in a release build can write one:

- The only editor is `TextField("Backend URL", text: $backendURL)` at
  `SettingsView.swift:594`, inside `#if DEBUG` (`:590`–`:598`). The second
  editor, `SettingsAdvancedView.swift:50`, is likewise `#if DEBUG` (`:47`–`:53`).
  TestFlight builds are Release. **There is no UI.**
- The only deep link is `anticipy://listen` (`AnticipyApp.swift:132`–`:137`),
  which calls `session.startListening()` and nothing else. It cannot set a key.
- The one non-DEBUG write path is a launch argument
  (`clients/ios/UITests/WalkTests.swift:81` passes `-backendURL`), which is a
  UI-test affordance. A user on a device cannot pass launch arguments.

**Why macOS is stuck harder.** `PocketBase.shared = PocketBase()`
(`clients/macos/AnticipyMac/PocketBase.swift:66`) calls the initializer with no
argument, so the default at `:78` is the *only* value that ever exists. There
is no UserDefaults key, no settings pane, no env var. It is a compile-time
constant in practice.

### 1.2 Repointable without a new build

| File:line | Mechanism | Who can change it |
|---|---|---|
| `extension/config.js:12` | `DEFAULT_BASE`, overridden by `chrome.storage.local.backendUrl` | the **user**, in the extension's own onboarding page |
| `next.config.mjs:9-10` | `process.env.FELLOWSHIP_ORIGIN \|\| "…railway.app"` | a **redeploy** — env var, no code change |
| `brain/worker.py:43` | `os.environ.get("ANTICIPY_PB", "http://127.0.0.1:8090")` | a **restart** |
| `brain/supervisor.py:29` | same | a restart |
| `brain/evidence.py:75` | same, via `_PB_DEFAULT` | a restart |
| `brain/voice_arm.py:325` | same | a restart |
| `firmware/src/config.h:61` | `API_BASE_URL "https://anticipy.ai"` | **already on the stable domain** — see §2.5 |

The extension's override is a real, shipped, user-visible control:
`extension/onboarding.js:100`–`:118` saves it, `:119`–`:130` resets it, and
`extension/config.js:56`–`:61` applies it live without a reload. It is
*user*-driven, not remote — an already-installed extension can be repointed
in about fifteen seconds by a person, and not at all by you.

### 1.3 Test harnesses and docs — cosmetic, but they lie after cutover

Hardcoded defaults, all overridable by env, none shipped to a user:

`proof/prod20.py:7` · `proof/dry_run_his_reply.py:62` ·
`proof/postdeploy_production.py:23` · `proof/capture_day.py:62` ·
`proof/is_it_live.py:29` · `proof/day_zero_20.py:675` ·
`proof/outcome_rate.py:120` · `proof/verify_all.py:25` ·
`proof/chrome_arm.mjs:23` · `overnight/are_the_ears_live.py:83` ·
`overnight/stranger_gate.py:104` · `overnight/is_it_live.py:30` ·
`overnight/turn_envelope_gate.py:71` · `overnight/is_the_brain_live.py:74` ·
`tests/test_inbound_sms_and_calls.py:584` ·
`extension/tests/test_config_backend_base.mjs:22` ·
`extension/tests/test_config_base.mjs:16` ·
`extension/tests/test_hosted_setup_bridge.mjs:19`

Plus one that is not a harness and *does* face a user:

| `website/index.html:408` | `<a href="https://backend-production-61e0a.up.railway.app/setup.html">` — a static page linking straight at Railway |

And the store listing, which will be submitted with a URL in it:
`extension/store/LISTING.md:18,176,201,238,323`.

Count: **75 references** to `railway.app` across the tree
(`grep -rn "railway\.app" --include=… | wc -l`), of which **9** are in shipped
binaries, **1** in a shipped static page, and the rest are defaults, docs, or
research notes.

---

## §2. How each client is updated

| Client | Channel | Lead time | Can a shipped build be repointed remotely? |
|---|---|---|---|
| **iPhone** | TestFlight (`.github/workflows/ios-testflight.yml`) | **hours to ~24h** — see §2.1 | **No.** §1.1 |
| **Mac** | notarized zip, hand-built, self-hosted | **~1 hour to build; unbounded to adopt** — §2.2 | **No.** §1.1 |
| **Chrome extension** | self-hosted zip, *load unpacked* | **minutes to publish; unbounded to adopt** — §2.3 | **No, but the user can, in 15 s.** §1.2 |
| **Website** | Vercel today, Workers after | **~2 minutes** | **Yes — it is the deploy.** |
| **brain** | Railway service restart | **~1 minute** | **Yes — env var.** |
| **Firmware** | DFU over BLE | n/a for this migration | **N/A — already points at `anticipy.ai`.** §2.5 |

### 2.1 iPhone — TestFlight, and it is *not* the App Store

`.github/workflows/ios-testflight.yml` does exactly four things: archive with
cloud signing (`:59`–`:69`), export with `method = app-store-connect`
(`clients/ios/ExportOptions.plist:5`), upload with `altool` (`:87`), and wait
for Apple's processing verdict (`:98`). **There is no submit-for-review step
anywhere** — `clients/ios/scripts/app_store_connect.py` exposes only
`next-build`, `wait-build`, and `free-signing-slot` (`:260`, `:264`, `:269`).

That is good news for lead time:

- **Internal testers** (up to 100 App Store Connect users): available as soon
  as processing finishes. **No review at all.** Typically 5–30 minutes.
- **External testers**: the *first* build of a version needs Beta App Review,
  typically under 24 hours; subsequent builds of the same version usually skip
  it. UNVERIFIED which group the current testers are in — check App Store
  Connect → TestFlight → Groups before you plan around this.

Two hazards in this workflow that will bite on cutover day:

1. **It only fires on `jose_anticipy_system`** (`:4`). On
   `cloudflare-migration` it will not run at all. Use `workflow_dispatch`
   (`:6`) or merge first.
2. Current version is `1.1.0` build `121` (`clients/ios/project.yml:15`, `:545`).
   The workflow bumps the build above Apple's latest automatically (`:54`).

**Adoption is still not instant.** TestFlight users must open the app or accept
the update. Budget days, not minutes, for the last device.

### 2.2 Mac — a zip you build by hand

`clients/macos/Tools/build_release.sh` signs (`:27`), zips with `ditto`
(`:30`), notarizes with `notarytool submit --wait` (`:34`), staples, re-zips
(`:38`), and prints a SHA-256 (`:43`). The output lands at
`backend/pb_public/mac/Anticipy-for-Mac.zip` and is served by `mac.html:66`
and `:83`.

**There is no auto-update.** No Sparkle, no appcast, no version check — grep
for `sparkle|appcast|autoupdate|checkForUpdate` across `clients/macos` returns
nothing. A Mac user updates by visiting the page again and re-downloading. If
they never do, their app talks to the old host forever.

This is the single worst tail in the migration, and §4 is written around it.

### 2.3 Chrome extension — self-hosted, *load unpacked*, never auto-updates

`backend/pb_public/setup.html:144` instructs: turn on **Developer mode**,
choose **Load unpacked**, select the folder. The zip is at `:102` and `:138`.

Consequences, all of them load-bearing:

- **No Chrome Web Store review, because it is not in the store.**
  `extension/store/LISTING.md:1` says "PREPARED FOR FINAL STORE ASSET REVIEW";
  `:5` describes the submission as a future act. `manifest.json` has no
  `update_url` and no `key`. So there is no store gate to wait for — and no
  store update channel either.
- **A load-unpacked extension never auto-updates.** Chrome does not update it.
  Publishing a new zip changes nothing on any installed browser.
- **But the user can repoint the one they have**, without reinstalling, via the
  backend field in the extension's onboarding page
  (`extension/onboarding.js:100`–`:118`). That makes the extension the *easiest*
  client to migrate — it just needs the user to act.

If the store listing *is* submitted before cutover, budget 1–3 days review and
expect extra scrutiny on the `debugger` permission (`LISTING.md:5`–`:7`).
Note `extension_v4/manifest.json:31` pins a `key` (a stable extension ID) —
`extension/manifest.json` does not.

### 2.4 Website — the easy one

`next.config.mjs:9`–`:10` already reads `FELLOWSHIP_ORIGIN` from env with the
Railway host only as a fallback. **35** rewrite destinations interpolate it:

    $ grep -c 'destination: `${FELLOWSHIP_ORIGIN}' next.config.mjs
    35
    $ grep -c FELLOWSHIP_ORIGIN next.config.mjs
    37          # 35 destinations + the 2-line declaration at :9-:10

They all move together when that env var changes. No code edit, no client
action.

The 35 break down as **33 `/internal/*` destinations** plus `/r/:code` (`:82`)
and `/c/:code` (`:83`), the two referral redirects:

    $ grep -n FELLOWSHIP_ORIGIN next.config.mjs | grep -c internal
    33

(The brief for this work said 34 rewrites. The counts that are actually in the
file are 33 and 35; nothing in it counts 34.)

`website/index.html:408` is the exception — a hardcoded anchor in a static
file. One-line fix, but do not forget it: it is the page a stranger lands on.

### 2.5 Firmware — already correct, and a lesson

`firmware/src/config.h:61`:

    #define API_BASE_URL            "https://anticipy.ai"

The pendant does **not** talk to Railway. It talks to the stable product
domain, and `firmware/DESIGN.md:260` and `:482` confirm the endpoints are
`https://anticipy.ai/api/...`. Firmware — the client that is *hardest* of all
to update, requiring a BLE DFU session per device — is the one client this
migration does not have to touch.

That is not luck. It is what happens when a client is given a stable name
instead of a provider's hostname. Which is §3.

---

## §3. `api.anticipy.ai` — pay once, never do this again

**Recommendation: introduce a stable custom domain now, before the backend
moves, and point every client at it.**

The current situation is that nine lines across two binaries name a *Railway
deployment*. Railway is the vendor; `61e0a` is a deployment identifier. When
the vendor changes, every one of those clients breaks — which is precisely the
problem this document exists to solve. Solve it once.

### 3.1 What it costs to introduce now

| Item | Cost |
|---|---|
| DNS record | £0 |
| Cloudflare zone | £0 (Free plan) |
| Certificate | £0 (Universal SSL, or Railway's own ACME) |
| **Nameserver migration `anticipy.ai` → Cloudflare** | **the real cost — see below** |
| Engineering | ~1 hour: add the record, change 9 lines, rebuild two clients |
| Schedule | **one iPhone build and one Mac build**, which you are spending anyway |

**The nameserver migration is the catch, and it is not small.** `anticipy.ai`
is on Porkbun today:

    $ dig +short anticipy.ai NS
    salvador.ns.porkbun.com.   fortaleza.ns.porkbun.com.
    curitiba.ns.porkbun.com.   maceio.ns.porkbun.com.

    $ dig +short anticipy.ai A            -> 76.76.21.21          (Vercel)
    $ dig +short www.anticipy.ai CNAME    -> cname.vercel-dns.com.
    $ dig +short api.anticipy.ai          -> (nothing; does not exist)

Cloudflare Workers custom domains and Workers routes both require the zone to
be **on Cloudflare's nameservers**. So `api.anticipy.ai` on Workers means
moving the whole zone off Porkbun — including MX, SPF/DKIM/DMARC, and the
Vercel records, all of which must be transcribed correctly *before* the NS
switch or mail stops. That is `CUTOVER.md` Phase 2, and it is deliberately
early and deliberately alone.

**You do not have to wait for that to get the benefit.** `api.anticipy.ai` can
be created on Porkbun *today* as a CNAME to the Railway host, and the clients
rebuilt against it immediately. The name becomes stable now; where it points
becomes Cloudflare's problem later. This decouples the two hard things — "give
clients a stable name" and "move the zone" — which otherwise have to happen on
the same day.

### 3.2 The record, today, on Porkbun

    Type   Name              Value                                        TTL
    CNAME  api.anticipy.ai   backend-production-61e0a.up.railway.app      300

TTL **300, not the default**. §5 of `CUTOVER.md` depends on it. Add
`api.anticipy.ai` as a custom domain on the Railway service so it provisions a
certificate for that name; without it, TLS fails on the new name and every
client that just adopted it is dead.

Verify before touching a single client:

    dig +short api.anticipy.ai
    curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' \
      https://api.anticipy.ai/api/health          # want: 200 0

### 3.3 The nine lines

Change all nine in §1.1 to `https://api.anticipy.ai`. Recommended shape — one
constant per client, not nine literals:

```swift
// clients/ios/Anticipy/AnticipyApp.swift — declare once, near the top
enum Backend {
    /// The product's own name for its backend. NOT a vendor hostname: the
    /// last one named a Railway deployment id, and moving providers meant
    /// shipping a build to every phone and every Mac before the old host
    /// could be switched off. This name is ours, so the next move is a DNS
    /// record and nobody has to install anything.
    static let defaultURL = "https://api.anticipy.ai"
}
```

```swift
// clients/macos/AnticipyMac/PocketBase.swift:78 — and give it an escape hatch,
// which this client currently does not have at all.
init(baseURL: URL? = nil) {
    self.baseURL = baseURL
        ?? UserDefaults.standard.string(forKey: "backendURL").flatMap(URL.init)
        ?? URL(string: "https://api.anticipy.ai")!
    …
}
```

That `UserDefaults` read is worth more than the URL change. It turns the Mac
app from *unrepointable* into *repointable with one `defaults write`* — which
means the next migration can be handled over a support call instead of a
release:

    defaults write ai.anticipy.mac backendURL https://api.anticipy.ai

**Do this in the same build.** It costs one line and it retires this entire
class of problem for the client that has no update channel.

---

## §4. The dual-run window

### 4.1 How long

`api.anticipy.ai` changes the question. Without it, the old host must live
until the last device updates — unbounded, because of §2.2. With it, the old
*name* must live only until DNS moves, and DNS is under your control.

| Phase | Old Railway host answers | Because |
|---|---|---|
| **A. Stable-name rollout** | yes, on both names | clients are being rebuilt against `api.anticipy.ai` |
| **B. Adoption** | yes, on both names | old builds still ask for the Railway hostname by name |
| **C. Backend cutover** | `api.` moves to Workers; Railway host stays up | old builds keep working, unchanged |
| **D. Decommission** | no | see the condition in §4.3 |

**Phase B is the long one, and only Phase B.** Target **30 days**, on this
reasoning:

- iPhone: TestFlight, small tester group, prompts on launch. Days.
- Extension: the user must re-download or retype a URL. Weeks, but the
  extension can be *told* — see §4.4.
- **Mac: no update channel at all.** This is what sets 30 days, and 30 days is
  a guess dressed as a number unless you measure it. Measure it: §4.5.

### 4.2 How the two backends stay consistent — they do not, and must not

**Do not run two writable backends.** There is exactly one database. During
Phases A–C both hostnames must resolve to **the same backend process**, not to
two synchronised copies.

This is not a simplification, it is a requirement. `backend/pb_hooks/` holds 55
routes, 6 global middlewares, and 2 cron jobs over one SQLite file. Two live
copies would need bidirectional replication of a database whose authorization
is implemented by *parsing filter strings*
(`guard.pb.js`, `research_lane.pb.js`) — the reconciliation semantics for that
do not exist and would have to be invented. There is no version of this that
is safer than not doing it.

So the dual-run is **two names, one backend**:

```
Phase A/B:  api.anticipy.ai  ─┐
            railway host     ─┴─►  PocketBase on Railway     (one process)

Phase C:    api.anticipy.ai  ────►  Worker + D1 on Cloudflare
            railway host     ────►  PocketBase on Railway     (frozen, read-mostly)
```

Phase C is the one moment the two diverge, and it is the actual risk in this
migration. It is handled in `CUTOVER.md` Phase 6 by *freezing writes on the old
backend* rather than by replicating them — a client still on the old host after
the switch gets a degraded read-only experience, which is recoverable, instead
of writing rows into a database nobody will ever read again, which is not.

### 4.3 "Railway stays paid and running until…"

> **Railway stays paid and running until every one of these is true:**
>
> 1. `api.anticipy.ai` has served the Cloudflare backend for **14 consecutive
>    days** with no rollback.
> 2. The old Railway hostname has logged **zero requests from a real client**
>    for **14 consecutive days** — measured, per §4.5, not assumed.
> 3. The export in `migration/runbooks/EXPORT.md` is complete and **verified**:
>    row counts reconciled, file blobs downloaded, `internal_passwords`
>    re-encrypted per `reencrypt_vault.md`.
> 4. The brain's per-owner state (`/data/owners/<ref>/memory.db`, on a
>    **separate** Railway volume) is exported and verified — `EXPORT.md` §3.
> 5. The R2 backup bucket has been **listed by a human** and confirmed current.
>    `migration/BLOCKERS.md` flags that R2 may not even be enabled on this
>    account, which would mean these backups have been failing silently.
>
> Any one of these false ⇒ Railway keeps running. It is a rounding error
> against the cost of the data.

### 4.4 The one remote lever you do have

The extension polls the old backend for jobs. So the old backend can *answer*.
Before cutover, add a route to the **old** PocketBase that tells an extension
where to go:

```js
// backend/pb_hooks/relocate.pb.js — deploy to the OLD backend, in Phase A.
//
// The extension cannot be updated remotely and its users cannot be relied on
// to read email. But it does poll us, so we can answer. This is the only
// remote repointing lever any client in this tree has; it exists because the
// extension happens to have both a storage override and a poll loop.
routerAdd("GET", "/agent/relocate", (e) => {
  const to = String($os.getenv("ANTICIPY_RELOCATE_TO") || "").trim();
  // Unset means "stay put" -- NOT "go nowhere". An empty string written into
  // an extension's backendUrl bricks that install until a human retypes it.
  if (!to) return e.json(200, { relocate: false });
  return e.json(200, { relocate: true, base: to });
});
```

**This requires an extension build to consume it** (a fetch in
`background.js`'s alarm, writing `chrome.storage.local.backendUrl`), so it does
not help installs that exist *today*. Ship it in the same extension release
that adopts `api.anticipy.ai`, so that *the next* move needs no user action.
Same logic as §3.3's `defaults write`: spend one line now to retire the
problem permanently.

Do not build this for iOS or macOS — a server that can retarget a client is a
server that can be made to retarget a client at an attacker's host. For the
extension the blast radius is one browser profile with a user-visible reset
button (`onboarding.js:119`–`:130`); for the phone it is the whole account.

### 4.5 Measure the tail; do not guess it

The 30 days in §4.1 is a placeholder until this exists. Add a one-line access
log on the **old** hostname keyed by `Host` and `User-Agent`, and read it
weekly. You need to know, specifically:

- how many distinct agent ids still poll the Railway hostname
  (`X-Anticipy-Agent-ID`, `guard.pb.js:200`–`:232`) — that is the extension tail
- how many distinct account tokens (`guard.pb.js:404`) — the iPhone tail
- whether `PocketBase.swift`'s user agent still appears — the Mac tail

Condition 2 in §4.3 cannot be evaluated without this. **Build it in Phase 1**,
before anything moves — a tail you did not measure at the start is a tail you
cannot prove has ended.

---

## §5. Order of operations

1. **Create `api.anticipy.ai` on Porkbun**, CNAME → Railway host, TTL 300. Add
   it as a Railway custom domain. Verify TLS. *(§3.2 — no client changes yet.)*
2. **Add the tail-measurement log** to the old backend. *(§4.5.)*
3. **Change the nine lines** to `api.anticipy.ai`; add the `UserDefaults`
   escape hatch to macOS and the `/agent/relocate` consumer to the extension.
   Fix `website/index.html:408`. *(§3.3, §4.4.)*
4. **Ship all three clients.** iPhone via `workflow_dispatch`; Mac via
   `build_release.sh`; extension zip to `pb_public`. Tell users, in the app and
   by email, that the Mac app and the extension need re-downloading.
5. **Watch the tail.** Do not proceed to the zone move until §4.3 condition 2
   is trending to zero.
6. Everything after this is `CUTOVER.md`.

Steps 1–4 are worth doing **even if the Cloudflare migration is cancelled**.
They are how you stop being locked to a vendor hostname by two binaries you
cannot recall.

---

## Unverified

- **Which TestFlight group the testers are in** (internal vs external). This
  decides whether §2.1's lead time is 30 minutes or 24 hours. Check App Store
  Connect → TestFlight → Groups. Not derivable from the repo.
- **How many devices are actually in the field** — iPhone installs, Mac
  installs, extension installs. `migration/BLOCKERS.md` mentions 7 accounts;
  whether that is 7 phones, 7 Macs, or 7 of each is not stated anywhere I read.
  The whole of §4.1 is a guess until this is known.
- **Whether the extension was ever submitted to the Chrome Web Store.**
  `LISTING.md:1` says prepared; there is no store ID or `update_url` in either
  manifest. If a store version *does* exist, it has its own update path and its
  own review lead time, and §2.3 is wrong for those users.
- **Whether Cloudflare offers CNAME-only ("partial") zone setup on a plan this
  account holds.** If it does, §3.1's nameserver migration may be avoidable. I
  did not verify current plan requirements and did not want to assert a
  Cloudflare feature I had not checked. Confirm in the dashboard before
  committing to the NS move.
- **Railway's behaviour when a service has two custom domains** and one is
  later removed — specifically whether removing one disturbs the certificate
  for the other. Verify on a staging service before doing it in production.
- **The `_archive/`, `extension_v4/`, `chrome/`, and `desktop/` trees** were not
  audited for backend URLs. `extension_v4` is a different product (native
  messaging, pinned key) and may or may not be shipped; if it is, it needs its
  own row in §1.
