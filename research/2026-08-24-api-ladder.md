# The API ladder — which platform, and whether the ladder should exist

**Date:** 2026-08-24 · **Tree:** `/Users/josegaelcruzlopez/Desktop/anticipy-omize`
· **Branch:** `jose_anticipy_system` · **Method:** read-only. No product code
touched, no dependency added, no account created with any vendor.

**Card:** PART 4 of 5 — HER HANDS (b). APIs. Its first subtask is this research,
and its own words are *"Composio is a candidate, NOT the decision."*

**One-line verdict:** three of the four candidates are disqualified before price
is discussed, and the named candidate is disqualified by evidence rather than by
theory — Composio was breached on 2026-05-21 and lost ~5,001 GitHub OAuth tokens
and ~5,241 API keys, with affected connections across Gmail, Google Calendar,
Slack, Notion and Drive, which is the exact service list on this card. The
recommendation is **native per-service OAuth, one write-shaped sensitive scope
at a time**, and the ladder is much shorter than the card assumes.

All prices below were checked on **2026-08-24**. Vendor pricing and vendor
security claims are marked as vendor claims where they are uncorroborated.

---

## 1. The law question — who survives LOCAL-FIRST

`design/LOCAL-FIRST.md` does not say "no cloud." Its scoreboard keeps a
server-side research arm and calls it *"fine in the cloud FOREVER: it reads the
public web, not him."* In the same table it kills Deepgram: *"the earlier idea
of moving phone STT to Deepgram is DEAD on this law."* The line the law draws is
not cloud-vs-local. It is **whose material the cloud component gets to see**,
stated in the opening sentence: *"the cloud is a courier and a pair of hands,
never the archive of who he is."*

So the test, written down so the next agent can re-apply it rather than
re-derive it:

1. **Custody** — does the vendor hold a credential that lets it read the
   owner's material without the owner doing anything further?
2. **Transit** — does the owner's material pass through the vendor's
   infrastructure?
3. **Reversibility** — can the owner end it without us, and can we end it
   without a migration?

A vendor holding a Gmail refresh token fails (1) permanently and (2)
continuously. That is not a cost trade-off. A refresh token to a mailbox is a
standing invitation to the archive of who he is, held by a party the owner never
chose, and it is precisely the thing LOCAL-FIRST rule 3 — *"what travels is the
smallest conclusion that works"* — exists to prevent.

### The verdicts

| Candidate | Custody | Transit | Survives LOCAL-FIRST |
|---|---|---|---|
| **Composio** (managed) | Composio stores and refreshes the tokens | Tool calls are proxied | **No** |
| **Arcade** (Cloud) | Arcade Engine stores and refreshes the tokens | Proxied | **No** |
| **Arcade** (Helm / marketplace self-host) | You hold them | Yours | **Yes** — but see §5.5 |
| **Pipedream Connect** | Pipedream stores encrypted tokens | Proxied | **No** |
| **Native per-service OAuth** | Anticipy holds them | Anticipy's own worker | **Yes, conditionally** — §3 |

Composio's docs say plainly that *"Composio stores and refreshes those
credentials against that `userID`"*
([docs.composio.dev/docs/managed-authentication](https://docs.composio.dev/docs/managed-authentication)).
Arcade's engine *"stores and refreshes the tokens"*
([docs.arcade.dev/en/home/hosting-overview](https://docs.arcade.dev/en/home/hosting-overview)).
Pipedream Connect *"handles OAuth flows, stores encrypted tokens for your end
users"* ([pipedream.com/docs/connect](https://pipedream.com/docs/connect/)).
None of that is a criticism of their engineering — it is the product they sell.
It is simply the thing this architecture's founding sentence refuses.

### The evidence, not the theory

On **2026-05-21** an attacker compromised a Composio employee's Gmail OAuth
token, used inbox access to intercept magic-link sign-in emails, escalated
through an internal agentic monitoring tool and a sandboxed execution
environment over roughly eight hours, and reached a credential cache holding
customer secrets. Reported exfiltration: **5,001 GitHub OAuth tokens and 5,241
API keys**, plus 12 Gmail tokens and smaller numbers of Jira, Slack, HubSpot,
Linear, Notion and Google Calendar tokens. Composio revoked every user's GitHub
tokens as a precaution and mandated an API-key rotation.
([material.security, 2026-06-03](https://material.security/resources/the-composio-breach-one-token-10242-doors);
[metorial.com, 2026-05-22](https://metorial.com/blog/composio-security-incident-mcp-security))

Two things matter about this beyond "a vendor got breached."

- **The initial vector was the exact asset this card proposes to hand over.** A
  single Gmail OAuth token was the door. The card's rung 1 is Gmail.
- **It is the standing shape of the risk, not a one-off.** The Salesloft Drift
  compromise (Aug 2025) took OAuth tokens from an integration vendor and used
  them against **700+** organisations' Salesforce tenants — Cloudflare, Google,
  PagerDuty, Palo Alto, Proofpoint, Tanium, Zscaler among them — until Salesloft
  and Salesforce revoked every Drift token.
  ([AppOmni](https://appomni.com/blog/drift-breach-salesforce-unc6395-saas-prevention/);
  [WTW](https://www.wtwco.com/en-us/insights/2025/09/the-drift-oauth-breach-a-cybersecurity-wake-up-call))

A token vault holding thousands of customers' mailbox keys is a target with a
value no individual customer's mailbox has. Centralising is the whole appeal and
the whole risk, and it is the same fact twice.

### The finding that reframes the card

The card assumes a platform buys you out of the auth work. **It does not.** All
three vendors require you to register your own OAuth app before production:

- Composio: *"In production, users should see your app name, not 'Composio.'"*
  Managed apps also *"share quota across all Composio users"* and enforce *"a
  15-minute minimum polling interval."*
  ([docs.composio.dev](https://docs.composio.dev/docs/authentication/custom-app-vs-managed-app))
- Arcade: *"For a multi-user production app, add your own OAuth app credentials
  … Arcade's default OAuth apps only support the Arcade user verifier"*, which
  requires every end user to hold an Arcade account in your project.
  ([docs.arcade.dev](https://docs.arcade.dev/en/home/auth/secure-auth-production))

So the Google verification, the scope justification, the demo video, the annual
CASA re-certification if a restricted scope is involved — **the expensive half
— is yours either way.** What the vendor saves is the token vault and the
refresh loop: a few hundred lines. The trade on offer is *a vendor in the trust
path, in exchange for the cheap half of the job.*

---

## 2. The comparison

Seven axes: the five the card names, plus the two it implies.

### Auth UX

Indistinguishable in the case that matters. Every route ends at the same Google
consent screen, and — per §1 — every route ends at *your own* consent screen in
production. The vendors ship a drop-in connect widget; writing one against a
provider's own OAuth endpoints is a redirect, a callback and a code exchange.

The real UX constraint is not the platform, it is Google's publishing status. An
external-type OAuth app in **Testing** issues *"a refresh token expiring in 7
days"*
([developers.google.com/identity/protocols/oauth2](https://developers.google.com/identity/protocols/oauth2)),
with a 100-test-user cap. **No cold stranger can be onboarded on their own
accounts until the app is verified** — and the done-gate's leg 6
(`overnight/done_gate.py:431`) is exactly that stranger. Verification is on the
critical path regardless of which candidate wins, and no candidate shortens it.

### Token security and storage

| | Where the token rests | Who can read it |
|---|---|---|
| Composio | Composio's cloud | Composio, plus anyone who reaches it (see 2026-05-21) |
| Arcade Cloud | Arcade's cloud | Arcade |
| Arcade self-host | Your cluster | You |
| Pipedream | Pipedream's cloud, *"encrypted at rest"* | Pipedream |
| Native | Anticipy's Railway volume | Anticipy — see §3, and it is not currently ready |

Composio's enterprise page claims *"zero-day log retention by default"* and *"end-to-end
encryption"*, and a KMS proxy on Enterprise only so *"Composio never sees your
API keys or tokens in plaintext"* — **vendor claims, uncorroborated**
([composio.dev/enterprise](https://composio.dev/enterprise),
[composio.dev/pricing](https://composio.dev/pricing)). Note also that
zero-retention is a claim about *storage*, not about *transit*: a proxied tool
call still carries the mail body through the vendor's process. For LOCAL-FIRST,
transit is the leg that fails.

### Per-call cost (checked 2026-08-24)

| | Free tier | Paid | Unit cost |
|---|---|---|---|
| Composio | 100K tool calls + 50K triggers/mo | $29/mo Pro | $0.0003/tool call, $0.003/trigger event |
| Arcade | 2,000 auth events + 2,000 tool calls/mo | $25/mo Team | $0.10/auth event, $0.01/tool call |
| Pipedream Connect | free in development mode only | ~$99/mo (annual) | 100 external users included, **$2/additional user** |
| Native | — | $0 | $0 |

Composio and Arcade pricing are from their own pages, fetched today
([composio.dev/pricing](https://composio.dev/pricing),
[arcade.dev/pricing](https://www.arcade.dev/pricing)). **Pipedream's pricing page
would not render for me**; the $99 / 100 users / $2-per-additional figures come
from secondary sources
([Zapier, 2026](https://zapier.com/blog/pipedream-pricing/)) and are
**uncorroborated against Pipedream's own page**.

At Anticipy's volume — one owner, tens of actions a day — every one of these
numbers is noise except Pipedream's floor, which is ~$1,200/yr for custody you
do not want. Cost is not the deciding axis and pretending it is would be padding.

### Service coverage

Composio advertises 1000+ toolkits; Arcade 7,000+ integrations; Pipedream
thousands. Coverage is the vendors' genuine advantage and it is real.

It is also aimed at a problem Anticipy does not have. `docs/BRIEF.html`'s fifty
moments name six services (moment 46: email and calendar; 47: an airline).
Six adapters is not a platform problem. Coverage pays when you have a long tail
of API-having services and no idea which ones customers will want. Anticipy has
a short head and knows exactly what is on it.

And coverage is worth *less than it looks* here, because §4 shows the services
most likely to trip this card's repeated-chore detector are the ones with no API
at all.

### Reliability

Composio's public status history for 2026 shows a steady drip:
API latency degradation on **2026-08-24 — today** (~29 min, with *"Slack triggers
turned off as part of remediation"*), QuickBooks rate limits from the shared
managed app (Aug 22–23), a dashboard outage caused by their auth provider WorkOS
(Jul 16), and a Gmail-trigger polling regression affecting ~2% of new-message
triggers (Jul 1–2)
([status.composio.dev/history/1](https://status.composio.dev/history/1)).
Uptime is quoted at 99.79–100% per component.

That is not a bad record for an early platform. It is a bad record for a
component sitting between an ambient assistant and its hands. Anticipy already
carries the Law-3 lesson — *production has served stale code at least twice* —
and adding a dependency whose Gmail path had a silent 2% failure rate seven
weeks ago adds a failure mode nobody in this repo can see, diagnose or fix.

The QuickBooks entry is worth reading twice: it is the shared-managed-app quota
problem from §1 showing up as a production incident.

### What happens when the vendor is down or gone

Down: the hands stop, and — because a proxied call is the *only* path — they
stop with no fallback. LOCAL-FIRST rule 4 requires that *"cloud components must
degrade gracefully when unreachable."* A vendor-proxied hand degrades to nothing
unless the browser hand is kept live behind it, at which point you are
maintaining both and the API path is an optimisation, not an architecture.

Gone: Composio has raised ~$29M (Seed $4M + $25M Series A, Lightspeed, Mar 2025;
[Crunchbase](https://www.crunchbase.com/organization/composio-b822)). Arcade
raised a $60M Series A in June 2026, ~$72M total
([businesswire](https://www.businesswire.com/news/home/20260615229631/en/Arcade-Raises-$60M-to-Become-the-Secure-Action-Layer-Behind-Every-Production-AI-Agent)).
Neither is at risk today. But the exit that matters is not bankruptcy — it is
the vendor changing terms, pricing, or scope policy, and a migration that means
**re-consenting every owner**, because the tokens were issued to the vendor's
client and cannot be moved. That is the reversibility test, and every hosted
candidate fails it in the same way.

A native adapter is ~300 lines you can delete.

### What the owner has to agree to

This is the axis the card does not name and it is the one that decides.

- **Vendor, managed app:** the owner sees *"Composio wants to access your
  account"*. A stranger onboarding onto an ambient assistant is asked to grant
  their mailbox to a company they have never heard of, whose name is not on the
  product. That is a trust event the product cannot afford, and Composio's own
  docs say so: not for production.
- **Vendor, own OAuth app:** the owner sees *Anticipy*, and a third party they
  are never told about holds the token. That is worse than the first case, not
  better — the disclosure has gone away but the custody has not.
- **Native:** the owner sees Anticipy, and Anticipy holds the token. Honest, and
  it puts the whole obligation on the party the owner actually chose.

`docs/BRIEF.html`'s definition of done is *"a cold stranger … onboards on their
own accounts."* On their own accounts, with their own consent, to the product
they installed. The vendor routes all put a fourth party inside that sentence.

---

## 3. Question 1 — what "tokens live server-side, never in the app or the extension" actually costs

The rule is right. The cost is that **Anticipy becomes a credential custodian
for strangers, and the current backend is not close to ready.** What follows is
measured against the tree, not estimated.

### What the server holds today

Every secret in the backend is **Anticipy's own**: `DEEPGRAM_API_KEY`,
`OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `TWILIO_*`, `CAPSOLVER_API_KEY`,
`ANTICIPY_SERVICE_TOKEN`. If they leak, Anticipy loses money and has to rotate.
It holds **zero** per-owner third-party credentials — `grep -rni
"oauth|refresh_token|client_secret|access_token" brain backend extension app`
returns six hits and not one of them is a stored owner token. A stranger's Gmail
refresh token is a different class of object: losing it costs *the stranger their
mail*, and it is durable — a Google refresh token does not expire on a clock.

### Five specific gaps, with file references

1. **No encryption at rest for collection data.** `backend/start.sh` runs
   `pocketbase serve` with no `--encryptionEnv`. PocketBase's `encryptionEnv`
   only covers app *settings* anyway
   ([pocketbase.io/jsvm](https://pocketbase.io/jsvm/functions/_app.encryptionEnv.html));
   there is no field-level encryption in PocketBase, only an AES-256-GCM
   primitive (`$security.encrypt`) you must call yourself in a hook. A token
   written to a collection today lands in `data.db` in the clear.
2. **The backups make it eight copies, not one.**
   `backend/pb_migrations/1700000018_daily_backups.js` sets `backups.cron =
   "0 9 * * *"`, `cronMaxKeep = 7`, *"stored on the same volume."* Unencrypted
   snapshots of the token store, sitting next to the token store.
3. **One shared secret is the whole wall.** `backend/pb_hooks/guard.pb.js` gates
   every collection read/write on a single server-wide `ANTICIPY_SERVICE_TOKEN`
   that the worker carries in its env. One leaked env var reads every owner's
   tokens. There is no per-owner key separation at the storage layer.
4. **That volume has already taken production down.** `backend/Dockerfile` and
   `backend/start.sh` document the 2026-08-15 fill: *"PocketBase could not even
   open its database: 'disk I/O error', crash loop, hard outage."* The disk that
   would hold the credentials is the repo's known fragile component.
5. **There is a live channel that already ships owner PII toward the
   extension.** `backend/pb_hooks/agent_key.pb.js` returns `first_name,
   last_name, email, phone, birthday, facts` to a paired browser agent on the
   strength of a per-agent token. The card's *"never in the app or the
   extension"* rule is aimed exactly at this shape, and PII already flows down
   it. Any token work must not reuse this endpoint, and someone should look at
   what it already sends.

### What would actually have to be built

- Envelope encryption: a per-owner data key, wrapped by a key that does **not**
  live on the Railway volume. `$security.encrypt` is the primitive; key
  management is the work.
- Backups moved off-volume and encrypted, or the token store deliberately kept
  out of the backed-up collections.
- A revoke path per provider, an owner-visible disconnect, and a mass-revoke
  runbook. `account_delete.pb.js` deletes rows; it would need to revoke upstream
  too, or deleting an account leaves a live grant behind.
- Rotation, and a decision about what happens on a suspected compromise. The
  honest answer for a one-person operation is "revoke everything and re-consent
  every owner" — which should be written down before it is needed, not during.

**Estimate: this is not a day's work and it is not a side effect of writing an
adapter.** It is the larger half of this card, and it is invisible in the card's
step list.

One more, and it is not optional: Google's own rule is *"If you store or
transmit restricted scope data on servers, then you need to complete a security
assessment"*
([restricted-scope-verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)),
re-certified *"at least every 12 months after your assessor's Letter of
Assessment (LOA) approval date."* Holding a Gmail *read* token server-side puts
Anticipy inside that sentence. Assessor prices reported in the $500–$4,500 range
(secondary sources; not quoted, see §7).

### The precedent already in the tree, flagged

`backend/pb_hooks/transcription_token.pb.js` is live in production — an
unauthenticated probe returns `401 {"error":"sign in first"}`, not `404`
(`research/2026-08-24-deepgram-leak.md`). It mints short-lived credentials for
**Deepgram**, the one vendor `design/LOCAL-FIRST.md` names by name and refuses.
That endpoint is what "a server-side vendor credential broker" looks like once
it has shipped, and it is the reason this section is written with file
references rather than estimates. Flagging it here per Law 6 and CLAUDE.md:
extending this pattern to owner tokens without closing that one first would be
building the second floor on an unresolved first.

---

## 4. Question 2 — is the premise true?

The card asserts: *"an API is always faster, cheaper, and safer than driving a
website."* Tested leg by leg, **it is true in a narrow band and false outside
it**, and the falsity is concentrated exactly where this card wants to point.

### Faster — usually true, for calls that exist

Not disputed. One HTTPS round trip beats a page load, a page map and a model
call.

### Cheaper — unmeasured here, and probably false for the case that triggers the card

This repo cannot currently price a browser errand. The only meter is
`llm_calls` / `llm_hour` on the agents row
(`backend/pb_migrations/1700000035_agent_llm_meter.js`), which counts calls
because *"the audit ledger already filled the 5GB volume once."* No dollars
anywhere.

And the card's own trigger undercuts the claim. `extension/recipes.js`: *"a
shape that has run cleanly twice compiles into a script: the same clicks, in
the same order, with no model in the loop"* — its stated target is *"an errand
that costs three cents and takes fifteen seconds"* versus *"thirty and four
minutes."* The card fires when *"she's driven the same airline's clunky site
four times this month."* By run four, recipes.js has already removed the model
from the loop. **The chores most likely to trip the repeated-chore detector are
the ones the browser has already made cheap.** That is uncomfortable for the
card and it should change what the detector is for (see §5).

### Safer — false in three shapes, and the third is fatal to "always"

**(a) Scope inflation.** Gmail has no scope for "the subject lines of this one
thread." Per Google's own scopes table
([gmail/api/auth/scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)):
`gmail.metadata` is **Restricted** and is still the whole mailbox's metadata;
`gmail.readonly` is **Restricted** and is the whole mailbox, forever, from a
server. The supervised browser read already shipped in
`extension/supervised_read.js` takes *one page the person opened themselves,
once, while they watch*, with a lease that *"stops itself inside thirty
seconds"* when the app leaves the foreground. Judged as *how much access does
this errand need*, the browser read is **narrower than the narrowest available
API scope**. `design/day-zero.md` §2 reached this conclusion, the code enforces
it, and `ContextGrant.swift` documents it in the type.

**(b) Rate limits that make the API the worse hand.** Not everywhere — Gmail is
generous, at 6,000 quota units per minute per user with `messages.send` costing
100 and `messages.get` 20
([Gmail API quotas](https://developers.google.com/workspace/gmail/api/reference/quota)),
so Gmail's problem is the scope, not the throughput. Slack is the opposite. It
now limits
`conversations.history` and `conversations.replies` for non-Marketplace apps to
**1 request per minute, maximum 15 objects per request**
([docs.slack.dev changelog, 2025-05-29](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/)),
with Marketplace apps and internal apps exempt (the latter keep 50+ req/min and
1,000 objects). Secondary reporting says existing non-Marketplace installations
came under the new limits on 2026-03-03 — a date now past. For "catch me up on
this channel", a human scrolling the Slack web UI outperforms the API by more
than an order of magnitude. **Slack is a service where the browser is the better
hand until Anticipy is a Marketplace app.**

**(c) No API at all.** This is the one that kills "always". The card's own
moment 47 is an airline site — airlines have no consumer booking API. OpenTable
has no self-serve developer key; partner APIs are under commercial agreement and
partners *cannot complete a reservation on their own side*
([OpenTable API partners](https://www.opentable.com/restaurant-solutions/api-partners/)).
`extension/learn.js` exists because *"nobody knows [how to dispute a utility
bill, claim a warranty, file a government form, cancel an obscure subscription]
from memory."* None of those have APIs and none ever will.

### What is actually true

Rewritten so it survives:

> An API is faster and safer than driving a website **when the service has a
> public API, exposes a scope no wider than the errand, and does not rate-limit
> third parties below what a browser gets.** Outside that band the browser is the
> better hand — sometimes the only hand.

Which means the ladder is not per-service. It is **per-scope-class**:

| Rung | What | Verdict |
|---|---|---|
| 1 | **Sensitive-scope, write-shaped** — `gmail.send` (**Sensitive**), Calendar event create | **Build.** 3–5 business-day verification, *no security assessment*. The browser is genuinely bad at these. |
| 2 | **Calendar and contacts reads** | **Already have a better hand.** `design/day-zero.md` §1: on-device `EventKit` / `Contacts`, only the derived list travels. Strictly more local-first than any API. |
| 3 | **Restricted scopes** — `gmail.readonly`, `gmail.modify`, `gmail.metadata`, `mail.google.com`, Drive | **Refuse.** CASA + annual re-cert + §1's law question. `day-zero.md` already refuses this. |
| 4 | **No API / partner-only API / punitive third-party limits** — airlines, OpenTable, utilities, government forms, Slack history | **Browser forever.** |

Rung 3 needs saying out loud: **executing this card literally reverses a shipped
decision.** `design/day-zero.md` §2 and §6, `extension/supervised_read.js:47-52`
and `app/ios/Anticipy/ContextGrant.swift:32-45` all refuse the Gmail API route
by name, with reasoning, enforced in code. The card names Gmail first. That
reversal is an owner decision, not something an adapter should do quietly, and
this document is where it gets flagged rather than absorbed.

---

## 5. Recommendation

**Native per-service OAuth. First adapter: Google Calendar event-create.
Second: `gmail.send`. No platform.**

The reasoning, visible:

1. **Three candidates fail the law, and the named one fails on evidence.**
   Custody and transit are not negotiable against `LOCAL-FIRST`, and Composio's
   2026-05-21 breach is what the abstract risk looks like when it lands.
2. **The vendors don't save the expensive half.** Bring-your-own OAuth app is
   required in production by all three, so Google verification, scope
   justification and any CASA obligation stay yours. You would be paying a
   vendor in the trust path for the cheap half.
3. **Coverage — their real advantage — buys the least here.** Six named
   services, of which two are on rung 1 and most of the rest are on rung 4.
4. **Cost decides nothing** at this volume, which is why it is not the argument.
5. **Arcade self-hosted is the only vendor shape that survives the law, and it
   is the wrong trade.** *"Deploy the platform with Helm on your own Kubernetes
   cluster"* — Anticipy runs one Railway container. Self-hosting Arcade *is*
   native OAuth, with a Kubernetes cluster and an enterprise contract attached.
6. **Reversibility.** An adapter is ~300 lines you delete. A platform is a
   migration that re-consents every owner.

**Scope the ladder to rung 1 only, and re-aim the repeated-chore detector.**
Because of §4's cheapness finding, "she has done this four times" is a poor
trigger — recipes.js has already made run four cheap. The detector's real signal
is **"she has done this four times and the site keeps breaking the replay"**
(`recipes.js` already surfaces `checkpointFailed` in plain English). That is the
chore an API actually fixes. The suggestion text stays; what it watches changes
from a repetition count to a *replay-failure* count, which is a structural
signal about the site rather than a threshold over a number — and, worth noting,
keeps this out of Law-1 territory since it measures a mechanism's outcome, not
what anybody meant.

**What would change this answer.** If the service count ever passes ~15 and they
are all API-having, re-open **Nango**: Elastic License v2, with a free
self-hosted edition that covers *auth and the API proxy* — the only candidate
found where the token vault runs on your own metal at the free tier
([nango.dev/docs/guides/platform/self-hosting](https://nango.dev/docs/guides/platform/self-hosting)).
Not evaluated in practice here, and its free-tier feature boundary is a vendor
claim (§7). It is named so the next agent does not have to rediscover it.

---

## 6. The one-day experiment

**Question:** for one real errand, does an API adapter beat the browser — and
what does holding one refresh token safely actually cost?

**Errand:** *"put dinner with Priya Thursday 7pm on my calendar."* Chosen because
it is on rung 1, it is write-shaped, it is in the fifty moments, and its scope
(`calendar.events`) is **sensitive, not restricted** — so no CASA is in scope
for the experiment.

**Two arms, same errand, same day.**

- **Arm A (incumbent):** the existing browser hand drives calendar.google.com.
  Run it 10 times. Record the cold run *and* the `recipes.js` replay separately —
  the replay is the honest baseline, not the cold run.
- **Arm B (candidate):** one `calendar.events` insert from the worker, against a
  token obtained by a hand-written OAuth exchange. Run it 10 times.

**Four measurements, and the fourth is the real one:**

1. Wall-clock, cold and warm, both arms.
2. Model spend per errand — read `llm_calls` off the agents row before and
   after, multiply by the posted price of the model in
   `ANTICIPY_BROWSER_MODEL`. This produces the first dollar figure this repo has
   ever had for an errand, which is worth the day on its own.
3. Failure modes across 10 runs each.
4. **The custody bill, written down as it is incurred**: what it took to hold
   *one* refresh token safely — the encryption hook, where the key lives, the
   revoke endpoint, what happened to the backup problem. If that half takes more
   than a day, **that is the result**, and it is the answer to the card.

**Preconditions that keep it a day and not a project:**

- Google Cloud project in **Testing** publishing status, developer's own account
  as the sole test user. Refresh tokens expire in 7 days in that mode — fine for
  an experiment, and itself a finding to record: no stranger can be onboarded
  until the app is verified.
- Scope: `https://www.googleapis.com/auth/calendar.events` and nothing else.
- Store the token in the worker's existing per-owner state directory
  (`brain/supervisor.py:119`, created `mode=0o700`), **not** in PocketBase — so
  the experiment does not create the backup problem in §3 before anyone has
  solved it. Note that this directory is container-local, so the token dies on
  redeploy; for a one-day experiment that is a feature, and for production it is
  the reason §3 exists.
- Nothing touches the extension or the iOS app. No new dependency in
  `brain/`. No vendor account created.

**Kill criteria, stated before running rather than after:**

- If Arm A's replay lands within ~5 s and under a cent, the "faster and cheaper"
  premise is dead for repeated chores, and the card should be rewritten around
  *write-shaped errands the browser is bad at* rather than around repetition.
- If the custody half (measurement 4) runs past two days, the ladder should not
  be built before `done_gate` leg 6 is green. A credential custodian with an
  unfinished stranger path is the wrong order.
- If either arm needs a restricted scope to complete the errand, stop: that is
  rung 3 and it goes back to the owner, not into an adapter.

---

## 7. What I could not determine

- **Composio's own incident report** (`composio.dev/blog/composio-may-2026-security-incident`)
  returned metadata only, and the `.ghost.io` mirror returned HTTP 402. Every
  breach number in §1 comes from two independent secondary sources, not from
  Composio's primary disclosure. Someone should read the primary before this is
  cited onward.
- **Pipedream Connect pricing.** `pipedream.com/pricing` and `/docs/pricing`
  would not render the figures. $99/mo, 100 external users, $2 per additional
  user, 10,000 credits — all secondary. Treat as approximate.
- **Whether Composio's token vault is genuinely self-hostable.** The OSS
  repository is SDKs and provider adapters only, MIT
  ([github.com/ComposioHQ/composio](https://github.com/ComposioHQ/composio));
  the auth backend is not in it. `composio.dev/enterprise` claims *"Run Composio
  on your own cloud"* — vendor claim, unverified, and search results conflating
  "self-host the MCP server" with "self-host the vault" are not evidence.
- **Google's authoritative sensitive-vs-restricted list.**
  `support.google.com/cloud/answer/9110914` did not render its tables. Gmail
  classifications in §4 come from Google's own Gmail scopes page. Calendar's
  "sensitive" classification comes from Google's sensitive-scope-verification
  page using calendar reading as its worked example — **not** from an enumerated
  list, and it should be confirmed before anyone budgets on it.
- **Current CASA assessor pricing.** The $500–$4,500 range is from secondary
  write-ups. The repo's existing `~$540–$4,500+/yr` figure
  (`day-zero.md:122-124`) is of unknown vintage. Nobody has a quote.
- **Whether Slack's 2026-03-03 date for existing installations landed as
  announced.** Slack's own changelog page contains no 2026 date; that date comes
  from secondary reporting of the same policy.
- **Anticipy's actual per-errand browser cost.** Never measured. The meter counts
  calls, not dollars. §6 measurement 2 is the fix.
- **Whether Railway encrypts its volumes at rest.** Not checked — and it would
  not change §3, since the PocketBase process reads the volume in the clear.
- **Arcade and Pipedream incident history.** I found Composio's public status
  history; I did not locate equivalent published histories for the other two, so
  the reliability section is one-sided by availability, not by selection.

---

## Sources

- [design/LOCAL-FIRST.md](../design/LOCAL-FIRST.md) · [design/day-zero.md](../design/day-zero.md) · [HARNESS-LAWS.md](../HARNESS-LAWS.md) · [docs/BRIEF.html](../docs/BRIEF.html) · [research/2026-08-24-deepgram-leak.md](2026-08-24-deepgram-leak.md)
- Composio: [pricing](https://composio.dev/pricing) · [enterprise](https://composio.dev/enterprise) · [managed auth](https://docs.composio.dev/docs/managed-authentication) · [custom vs managed app](https://docs.composio.dev/docs/authentication/custom-app-vs-managed-app) · [status history](https://status.composio.dev/history/1) · [GitHub](https://github.com/ComposioHQ/composio) · [Crunchbase](https://www.crunchbase.com/organization/composio-b822)
- Composio breach: [Material Security, 2026-06-03](https://material.security/resources/the-composio-breach-one-token-10242-doors) · [Metorial, 2026-05-22](https://metorial.com/blog/composio-security-incident-mcp-security)
- Arcade: [pricing](https://www.arcade.dev/pricing) · [hosting overview](https://docs.arcade.dev/en/home/hosting-overview) · [secure auth in production](https://docs.arcade.dev/en/home/auth/secure-auth-production) · [Series A](https://www.businesswire.com/news/home/20260615229631/en/Arcade-Raises-$60M-to-Become-the-Secure-Action-Layer-Behind-Every-Production-AI-Agent)
- Pipedream: [Connect docs](https://pipedream.com/docs/connect/) · [pricing (secondary)](https://zapier.com/blog/pipedream-pricing/)
- Nango: [self-hosting](https://nango.dev/docs/guides/platform/self-hosting)
- Google: [restricted scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification) · [sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification) · [Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes) · [Gmail API quotas](https://developers.google.com/workspace/gmail/api/reference/quota) · [OAuth 2.0 overview](https://developers.google.com/identity/protocols/oauth2)
- Slack: [rate limit changes for non-Marketplace apps](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps/)
- OpenTable: [API partners](https://www.opentable.com/restaurant-solutions/api-partners/)
- Salesloft Drift breach: [AppOmni](https://appomni.com/blog/drift-breach-salesforce-unc6395-saas-prevention/) · [WTW](https://www.wtwco.com/en-us/insights/2025/09/the-drift-oauth-breach-a-cybersecurity-wake-up-call)
- PocketBase: [encryptionEnv](https://pocketbase.io/jsvm/functions/_app.encryptionEnv.html) · [security.encrypt](https://pocketbase.io/jsvm/functions/_security.encrypt.html)
