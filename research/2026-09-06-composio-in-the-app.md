# Composio in the app — what a person can now do, what is live, what is owed

2026-09-06. Written after the round that closed the four gaps three audits named
and DEPLOYED the result. Every number below was measured on the day, against
production where the claim is about production.

Deployed Worker version: **`8439b076-139d-436c-93db-c422e40533b7`** (`anticipy-api`).
iOS build: **148**. 147 was taken by another session's commit while this change
was still in the working tree — the number was staged, the source was not, so two
different apps would have called themselves 147. The build-number gate caught it.
Not committed by this round.

---

## 1. The one-paragraph answer

A person opening Anticipy for the first time now reaches a setup card that has
their own most-lived-in apps already ticked, ticks or unticks what they like,
taps **one** Connect button, and gets **one** page with a card per app on it.
Skip is on the screen the whole time and buys seven days of quiet. On the server
side all of that is live. Two things are not: the sentences the page draws
cannot be photographed from here without an owner session, and a skipped setup
card cannot yet be recorded on the server, because one CHECK constraint on one
production table has not been widened. Both are named below with the exact
command that closes them.

---

## 2. What landed

### Gap A — the setup card had nothing to pre-select from

`GET /me/connections/signals` answers this owner's ranked apps with each app's
catalog row attached, and says which KIND of empty it is when it is empty
(`ranked` / `none` / `unreadable` / `catalog-unreadable`). The phone reads
`state` as a closed token and never reads `message`.

`OnboardingView.connectDetection` used to be
`ConnectOnboardingPolicy.detected(from: [], catalog: [], …)` — two literal empty
arrays, so "detected apps pre-selected" pre-selected nothing for every person
alive while the ranking beside it passed 154 checks proving it would have ordered
them correctly if anything had ever handed it a row. It now reads the route.

**Live**: `https://api.anticipy.ai/me/connections/signals` answers `401 Sign in
first.` It answered `404 There's nothing at this address.` before the deploy.

### Gap B — the mail-host seam

`ToolkitMeta` (Swift) gained `mailHosts`; `ConnectedAppsClient.toolkit(_:)`
decodes `mail_hosts` off the catalog row; `OnboardingView` carries it into
`ConnectOnboardingPolicy.CatalogEntry`. That is the last hop of a seam whose
other three hops already existed and which therefore did nothing.

**It seeds nothing, and that is a measurement of the vendor rather than a gap in
the code.** The union of every key path over twelve detail rows and fifty listing
rows of the live catalog contains no mail, mx, exchanger or dns field. `mail_hosts`
comes back `[]` on every app. The column is carried anyway, empty rather than
absent, because "the catalog names no mail host" and "this server is too old to
have the column" are different facts and a missing key makes the phone guess
which one it holds.

The honest path to a working MX seed is unchanged and unbuilt: a resolved
exchanger, or the shortlist a registrable name produces, put to a MODEL against
the catalog. Writing a domain into `signals.ts` or `provider.ts` instead is the
law-1 violation this feature has dodged three times, and the Worker's suite now
goes red on that exact edit.

### Gap C — Skip only ever reached UserDefaults

Half closed, and the half that is closed is the server's.

`recordDecline` no longer advances the ladder for a setup-card skip. It writes
`state: "declined_soft"`, `level: 0` and a seven-day snooze. `POST
/me/connections/skip` answers `{state:"recorded", level:0, soft:true,
snooze_until:…}`, which is exactly what `ConnectOnboardingPolicy
.serverAgreedWithSkip` demands.

**What shipped before this was worse than it looked, and the suite was passing
over it.** A setup-card skip stamped `declined` at level 1. `LEVEL_THRESHOLD[1]`
is 0.80 against a STRICT `score > threshold`, and `TRIGGER_SCORE` gives in_task
0.80, onboarding 0.70 and repeated_use 0.60 — so one tap on a card during setup
permanently silenced the three triggers that can name a task which already cost
this person real time. The check that should have caught it
(`connect-routes.test.ts`, "THE ROW'S OWN MOMENT decides the snooze") asserted
`level === 1` and measured only the number of days. It now asserts the level, the
state, `acted_at`, and — in five new checks — that the soft snooze applies once,
that silence is never soft, and that seven days later every trigger is licensed
again with a level-1 control beside it that stays refused.

**The phone still does not send.** `serverRecordsTheSoftSnooze` is `false`, on
purpose, because of §4 below.

### Gap D — one Connect button, one link

`mintConnectPage` (nudge.ts) writes N `connect_links` rows on ONE token at the
handles `routes/connect.ts` derives (`pageHandle`), in ONE `putAll` batch — all of
it or none of it. `mintConnectLink` is now one line that calls it with one app, so
a page of one is byte-identical to every link in the wild (`pageHandle(token, 0)`
IS `tokenHandle(token)`).

`POST /me/connections/link` takes `{"toolkits": [...]}` as well as
`{"toolkit": "..."}`, refuses a body naming both, refuses a duplicate or an
over-long page with a **400** rather than letting the minter throw a 503, and
echoes the set back so the phone can check it got the page it asked for.

On the phone, `OnboardingView` mints once for the whole ticked set and gathers
every app's three sentences — concurrently, in page order — for the disclosure in
front of it. It used to walk the queue one app at a time: four tokens, four
hand-overs, four returns for one decision, and closing the browser after the
second lost the other two.

**A budget bug found on the way, which would have shipped as an outage.** The
mint budget counted `connect_links` ROWS, and a four-app page writes four of them.
Ticking four apps, changing your mind and ticking four again put a person over a
six-an-hour ceiling and locked them out of connecting anything for an hour — and
`MAX_PAGE_APPS` (12) being larger than `MAX_LINKS_PER_OWNER` (6) meant any page
past six apps was refused before the minter ever saw it. The budget now counts
MINTS (distinct mint instants in the window), and the test that guarded it was
rewritten to advance the clock, because six HTTP requests do not share a
millisecond and the old fixture only passed by pretending they did.

---

## 3. Which surfaces are live

| surface | state |
| --- | --- |
| `GET /me/connections/signals` | LIVE — 401 signed out (was 404) |
| `POST /me/connections/skip` | LIVE — 401 signed out, 405 on GET (was 404) |
| `POST /me/connections/link`, multi-app | LIVE |
| the six other `/me/connections` routes | LIVE, unchanged |
| `/c/{token}` on `api.anticipy.ai` | LIVE, and it is the host links are minted on |
| `/c/{token}` on `anticipy.ai` | **DEAD** — see §5 |
| the expiry webhook | LIVE and verifying |
| the five-minute cron | **OFF**, deliberately — see §4 |
| iOS build 148 | in the tree, NOT on a phone |

`overnight/is_connect_live.py`, run against production after the deploy — exit 1,
fourteen legs: **10 PASS, 3 UNPROVEN (3, 9, 11), 1 RED (13)**. Legs 12, 13 and 14
are new in this round; 13 is red on purpose and 14 found §5.

A real three-app page was written to production `connect_links` for probe owner
`qeuy6sv1raof9rw`, read back app by app at its own derived handle (one owner,
one expiry, none spent), fetched over HTTPS, and deleted — with the deletion
verified. Nothing was left behind.

---

## 4. What is owed, and who has to say yes

### (a) ONE SQL FILE, and it is the owner's yes, not an agent's

```
cd migration/workers
npx wrangler d1 execute anticipy-backend --remote \
  --file=../d1/2026-09-06-connect-nudges-declined-soft.sql
```

Live `connect_nudges` carries the CHECK constraint it shipped with — five states,
no `declined_soft` — and SQLite cannot widen a CHECK, so the table is rebuilt
(rename, create, insert-select, drop). **`connect_nudges` held ZERO rows when
this was written**, measured immediately before, so there is nothing to migrate;
the INSERT..SELECT is kept only so the script is correct if it is ever replayed.

Until it runs, the row a skipped setup card produces is refused by the DATABASE:
`recordSkip` answers `not-recorded` and the route answers 503. Nothing is broken
today because the phone is holding its skip back for exactly this reason, and
because no live path can reach the soft branch (the connect page's own Skip sends
`onboarding: false`, and the ask engine that would stamp `trigger: onboarding` is
not running).

**In the same change, flip `ConnectOnboardingPolicy.serverRecordsTheSoftSnooze`
to `true`.** `overnight/is_connect_live.py` leg 13 is RED until the migration
lands and names the file in its own failure text; `run_connect_onboarding_step_tests.sh`
refuses to let the phone hold back at all unless that red leg exists. Nobody has
to remember.

I did not run it: the harness refused the command as a destructive production
schema write, and that refusal is correct.

### (b) ONE LINE IN `wrangler.jsonc`, if the owner wants the sweep back

```
"crons": ["*/5 * * * *", "17 4 * * *"]
```

The repo file carried `*/5 * * * *`, committed in the ask round and never
deployed. The LIVE Worker had only `17 4 * * *` — read from the Cloudflare API,
not assumed:

```
GET /accounts/…/workers/scripts/anticipy-api/schedules
-> { "schedules": [ { "cron": "17 4 * * *" } ] }
```

So deploying the file as it stood would have STARTED the HQ reminder sweep, which
has been dark since 2026-09-05, and its first tick would drain a backlog of
claims that came due while nothing ran — a burst of real texts to the team for
events days old. I removed the line, deployed everything else, and wrote the
history and the rollback into the file. The connect-ask half of that trigger
would send nothing today anyway: `app_usage_signals` is empty in production,
measured the same day.

---

## 5. A live defect this round found, and the leg that now watches it

```
GET https://anticipy.ai/c/<43 chars>
  -> 301 https://www.anticipy.ai/c/<43 chars>
  -> 307 https://www.anticipy.ai/
  -> 200  the marketing home page
```

`anticipy.ai/c/*` **is** a registered Worker route pointing at `anticipy-api` —
confirmed against the Cloudflare API for the zone, and `wrangler deploy` prints
it back on every deploy. It never runs: a zone-level apex-to-www redirect fires
in front of the route, and the website then 307s an unknown `/c/` path to its own
home page. **A route can be present, correct, printed by the deploy tool, and
dead.**

It costs nothing today, because links are minted on `CONNECT_URL_BASE` =
`api.anticipy.ai/c`, which serves the real page, and `ConnectHandoff
.connectLinkHosts` accepts that host. It is one environment variable from costing
everything: the spec (page 26) says the link is `anticipy.ai/c/{token}`,
`words.ts` pins `CONNECT_LINK_PREFIX` to exactly that, and `nudge.ts` carries a
documented duplicate of `askText` (`askMessage`) whose entire reason for existing
is that those two constants disagree. Moving `CONNECT_BASE_URL` to the host the
spec asks for would send every connect link in every text message to a marketing
page, with every suite still green.

`is_connect_live.py` **leg 14** now measures it. RED is reserved for the host
links are actually minted on; every other host the phone would open is measured
and NAMED in the sentence. Four mutations against it, all caught.

The repair is a Cloudflare configuration change (exclude `/c/*` from the
apex→www redirect rule), not a code change, and it is the owner's call.

---

## 6. What a person still cannot get from us

**The actual sentences the connect page draws.** They need a signed-in owner
session and no owner credential exists in this environment — `ANTICIPY_AUTH_SECRET`
is a Worker secret, not a local one, and the probe owner has no password here. The
page answers `401` with connect.ts's own sign-in wall, which is the correct answer
to a stranger holding somebody's link, and claiming more than that would be
inventing a measurement. `is_connect_live.py` leg 3 has said the same thing about
the catalog since it was written; one exported credential turns both green.

**Anything on a phone.** Build 148 is in the tree. The iOS logic gate is green at
2,441 checks, but the UI walks (`FrontendShots.swift`, `WalkTests.swift`) were
EDITED and not RUN — they need a simulator, and no simulator run happened in this
session. The setup card and the Connected apps screen are now in both walks; that
they are captured correctly is unproven.

**Anybody being asked.** Leg 11 is unproven and says why: of the six ingest doors
in `src/connections/signals.ts` only the connected-apps sweep has a caller. The
two that name a MOMENT — the browser hand's post-run host, and a model resolving
the owner's own words — are what turn it green, and neither exists.

---

## 7. The numbers

| gate | result |
| --- | --- |
| `cd migration/workers && npm test` | exit 0 — 1,052 checks over 23 reporting suites |
| `npx tsc --noEmit` | exit 0, clean |
| `sh app/ios/Tests/run_all.sh` | exit 0 — 2,441 PASS lines, build 148 |
| `python3 overnight/is_connect_live.py` | exit 1 — leg 13 red on purpose (§4a) |
| `python3 overnight/is_connect_live.py --self-test` | 115/115 |
| `python3 -m pytest tests/test_is_connect_live.py` | 119 passed |

**Mutation testing.** 18 mutations over the Worker change, each anchored on a
literal asserted to occur EXACTLY ONCE in its file (the harness ABORTS on an
anchor that does not match exactly once). 18 of 18 caught. Two survived a first
run and both taught something:

* removing the route's duplicate-app refusal survived, because `mintConnectPage`
  refused it too — as a 503, for a body that will never be acceptable, which a
  phone retries forever. The route now refuses it with a 400 and the test demands
  that status rather than "400 or 503".
* removing the LIBRARY's page-length ceiling survived once the route grew its
  own, because the route's shadows it. `mintConnectPage` is exported and has
  other callers, so the invariant is now pinned where it lives.

Eight more over `is_connect_live.py`'s new legs, all caught, by both the pytest
file and the gate's own `--self-test`.

Files restored from copies held OUTSIDE the repository. No `git stash`, no
`git checkout --`, no `git add -A`.

---

## 8. Two things I changed that were not on my list, flagged rather than hidden

**`app/ios/Tests/run_connections_policy_tests.sh`** — its union reader stripped
`//` line comments but not `/** */` blocks, so `contract.ts`'s new JSDoc note on
`declined_soft` (which quotes the spec twice) made it report the union as
`never_asked asked " Page 25: " " not a real decline" declined_soft …` and fail
over an English sentence. It now strips any line whose first non-space character
opens or continues a block comment, which is every line of a JSDoc and cannot be
a line of a union.

**`spike/two-hands/src/connections/contract.ts`, `store.ts`, `migration/d1/schema.sql`,
`ConnectionsPolicy.swift`** — all four carry `declined_soft`, because a sixth
state is a change to a shared declaration and a state on one side and not the
other does not fail to compile: it decodes as nil and the surface silently
disappears for whoever is in it. Both Swift enums and both census lists were
updated in the same change, and both runners that compare them to the TypeScript
are green.
