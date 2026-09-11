# Connector acceptance readiness — 2026-09-11

Reviewer: Tom. Read-only product review on `cloudflare-backend`, base commit
`943cd79c9d380dfe2b363224908e089b5d7270f0`, with the reviewed, uncommitted connector
liveness candidate present. No live provider/account reads, OAuth, pairing,
credentials, sends, deployment, or Git writes were performed in this review.

## Outcome

The local connector infrastructure passes the targeted checks below. This is
not proof that every vendor, OAuth grant, deployed Worker, installed client, or
real-account task works. Start live acceptance with one explicitly selected test
account and synthetic read-only fixture; do not start with a send or other write.

Anticipy has one catalogue-driven Composio adapter, not separately verified
implementations of every app in the vendor catalogue. A toolkit is a viable
candidate only when the current catalogue supplies usable identity, tool
schemas, and permission metadata, OAuth completes for the correct owner, and an
actual tool operation succeeds with its receipt checked.

Two current restrictions need to be visible in any demo claim:

- Missing scope metadata blocks permission copy rather than inventing consent.
- Normal brain hand selection currently supplies ledger rung 0, while API writes
  require rung 3 and the connection's write opt-in. Connecting an account or
  switching writes on is therefore not proof of a normal API-write task flow.
  The reachability review below confirms an intentional, unimplemented
  capability-history ladder; do not bypass the floor.

## Actual integration surfaces

| Stage | Current source/path | What a pass would establish |
| --- | --- | --- |
| Discover and explain | `GET /me/connections/catalog`; `POST /me/connections/sentences` | Current toolkit metadata exists and consent copy is grounded in declared scopes. Catalogue availability is not account access. |
| Authorize | `POST /me/connections/link`; `/c/{token}` begin/done; `/c/{token}/code` and `/verify` | Correct owner, toolkit, state, alias, and OAuth completion. The code path sends a real SMS when exercised, so it is not a read-only probe. |
| Confirm connected account | Owner-scoped provider account readback in `routes/connect.ts` | An exact connected account is confirmed and stored with writes off by default, not merely a callback or link-mint success. |
| Brain access discovery | `GET /hands/api/connections?owner=<exact owner>` | Service-authenticated, exact-owner connection metadata, without account credentials; this current route is implemented and covered. |
| Plan and execute a tool | `/hands/api/tools`; `POST /hands/api/run`; `brain/hands.py` | Catalogue-backed tool/schema, allowed effect, exact account/alias, result and receipt. `/run` is an effect route, not a general health check. |
| Connection commands | `POST /worker/connection-command` | Intent/planner/executor integration. A command can mint a link or disconnect, so even a text fixture is not automatically read-only. |
| Lifecycle | Signed `/connections/events` expiry webhook | Valid expiry event changes the owned connection state; it does not prove incoming email/Slack triggers or an automatic reconnect text. |
| Browser alternative | Existing paired browser-agent route and approval/device gates | Separate browser pairing/execution proof. A successful API connector does not prove the browser extension and vice versa. |

Provider wire paths are pinned to `https://backend.composio.dev/api/v3.1`:
`POST /tool_router/session`, session `/link`, owner-filtered
`GET /connected_accounts`, `GET /toolkits`, `GET /tools`, and
`POST /tools/execute/{catalogue slug}`. Session management tools must be disabled;
session-to-owner and connected-account owner checks are enforced. Revocation and
deletion are effects and must not be used as an automatic "health check."

The current iOS handoff allows both `anticipy.ai` and `api.anticipy.ai`
(`app/ios/Anticipy/Backend/ConnectHandoff.swift:161`). The older API-host rejection
is not a current source blocker. This still does not prove the installed build.

## Vendor candidate matrix

These are catalogue-backed candidates, not an assertion that the current live
Anticipy account has them enabled. Resolve exact toolkit/tool slugs and declared
permissions from current metadata; do not guess a tool's effect from its name.

| Candidate family | User choice / preparation | First safe live read | Must remain out of that test |
| --- | --- | --- | --- |
| Gmail or Outlook | Dedicated test mailbox; user-created synthetic message; correct personal/work identity | Find the exact test message and answer a factual question with its source identity | Send/reply/forward, provider draft creation, real inbox sweep, or assuming Outlook is connected from the user's email address |
| Google Calendar | Dedicated synthetic calendar/event, with no attendees | Read one bounded date window; verify event title, time and timezone | Create/update/delete events or invite anyone |
| Google Drive / Docs / Sheets | A synthetic file or sheet the user deliberately makes available | Read the specified document or cells and verify a known value | Upload, create, share, overwrite, or broad file search over customer content |
| Slack | Test workspace and synthetic channel/thread with permission to read it | Summarize that exact thread and verify the source | Post, invite, join channels, or enumerate unrelated private conversations |
| GitHub / Linear / HubSpot | Disposable repository/project/CRM fixture | Read one specified issue/record and identify a known field | Comments, issue/record creation, workflow changes, or changes to a real sales pipeline |
| Notion / Asana | First confirm usable permission metadata and correct OAuth resources | Read a deliberately shared synthetic page/task only after consent can be truthfully shown | Guessing missing permissions or claiming catalogue support implies the consent flow works |

Historical source measurements from September 6 recorded empty scopes for Notion
and Asana, unlike several Google/Microsoft/Slack/GitHub toolkits. That is a reason
to check current metadata, not a claim about today's vendor response. Current
Notion documentation advertises managed OAuth, but that alone does not prove the
shape consumed by Anticipy's permission-copy reader.

Available scope metadata is not the same as the scopes actually granted to an
account. The current session request passes `user_id` and disabled connection
management but no explicit auth-config selection. Composio documents defining
least-privilege scopes in an auth config and selecting that config for the
session; scope changes require reauthorization of existing connections. Review
the actual OAuth screen with the user instead of promising mailbox/folder-only
access from a narrowly worded task. [Composio scope controls](https://docs.composio.dev/docs/authentication/controlling-scopes)

For Outlook in particular, check each tool's documented scopes and tenant-consent
requirements: a read-shaped tool name is not sufficient proof of least-privilege
authorization. [Outlook integration guide](https://docs.composio.dev/kb/guide/toolkits-outlook)

## Thin-slice task list and evidence gates

1. **Completed autonomously: deterministic local contracts.** The eight suites
   below establish fixture-level owner isolation, route/state gates, callback
   handling, catalogue/executor contracts, expiry authentication, and transport
   failure behavior. Native loopback HTTP stalls are included; real OAuth and
   provider permissions are not.
2. **Available autonomously within the parent's approved model budget:** run a
   reviewed current-gateway version of the connection-command intent fixture
   suite. Test connect, list, decline, quoted/reported text, ambiguous references,
   and disconnect intent without real accounts or SMS. Label this model intent
   proof, not provider connectivity. The historical helper needs adaptation
   described below before reuse.
3. **Requires user choice:** choose one provider, the exact test account and
   work/personal alias, and one synthetic artifact. User completes OAuth and any
   tenant-admin consent personally. Never request pasted access tokens. Do not
   connect every app or grant broader scopes merely to increase test coverage.
4. **Scoped live read after authorization:** inspect only this owner's selected
   toolkit/account metadata; confirm active state and writes off. Verify the
   deployed source/configuration relevant to that path. Names/presence alone do
   not prove a credential is valid. Do not enumerate other owners or print
   credentials, authorization URLs, or real message bodies.
5. **One actual read-only task:** start from normal in-app input; do not seed a
   production job. Require exact lineage through input event, owned planned job,
   catalogue tool and connected-account selection, tool result, verified receipt,
   and the app's answer/source. Record timings, source version and scoped test
   identifiers. Verify the expected synthetic value, not merely HTTP 200.
6. **Variations:** then use an unseen paraphrase and an ambiguous two-account
   request that must ask which account. Continue deterministic wrong-owner,
   missing-scope, timeout, pagination and uncertain-write tests locally. A real
   expiry/revocation/reconnect exercise requires a disposable grant and separate
   agreement; never expire or revoke a working grant as implicit cleanup.
7. **Writes:** local negative and receipt/permission fixtures can run without
   external effects. Real provider drafts, calendar events, sends, comments,
   deletion and connector revocation are all writes. No normal planner API-write
   acceptance claim is possible while the rung gate is unresolved. Do not insert
   jobs, forge a ledger rung, or directly call `/hands/api/run` to manufacture a
   passing end-to-end demo. A future approved write test needs a specific
   reversible test artifact, exact permitted action, readback proof, and explicit
   cleanup scope; a generic "dry run" must not execute the provider call.

The smallest user question is: **Which provider and dedicated test account or
synthetic artifact should we connect first?** An email address already supplied
for TestFlight is not permission to inspect that mailbox.

## Existing helper reuse limits

- `proof/audit/run_connection_commands.ts` uses real command/query/match models
  with a fake Composio catalogue and fixture database. Its eleven scenarios do
  not perform OAuth or prove real disconnection. It currently assumes an old
  gateway state path/port and accepts an unrestricted report label; adapt and
  review it for the parent's current bounded gateway before running it. Do not
  accidentally route an unrecognized fetch as an ordinary provider call.
- `proof/audit/live_connection_commands.py` targets the live API, creates a
  phone-less owner/events/job, mints links, and deletes its fixture. It reads
  older private budget/configuration paths. It is not a read-only connector
  smoke test and was not run here.
- `work/metadata_own_reply_canary.py` has a one-use input journal and intentionally
  requires zero connections and zero paired agents. It cannot be reused after
  connecting a provider. Do not loosen its old baseline or reset its journal;
  any new connector observation needs a separately scoped scenario and exact
  owner/account/job lineage.
- Browser queue seeding or pairing can expose unrelated existing jobs. Use a
  fresh isolated owner/profile for synthetic browser execution; a paired user's
  actual browser/account requires a separately scoped test. No pairing was done.

## Local verification performed in this review

Each listed command completed with actual exit code 0 on September 11, using
Node 24, a scrubbed environment, dotenv autoload off, npm offline and macOS
`sandbox-exec` denying outbound network except loopback. Provider accounts and
responses in the general suites are fixtures. The liveness suite additionally
uses real native `fetch` against disposable loopback HTTP servers.

| Suite in `migration/workers/test/` | Reported result | Private ignored log |
| --- | --- | --- |
| `connections-provider.test.ts` | 203 cases; its nested liveness suite reports 28 cases | `work/tom-readiness-connections-provider-20260911.log` |
| `connect-routes.test.ts` | 99 passed, 0 failed | `work/tom-readiness-connect-routes-20260911.log` |
| `connect-auth.test.ts` | 61 passed, 0 failed | `work/tom-readiness-connect-auth-20260911.log` |
| `connections-api.test.ts` | 118 passed, 0 failed | `work/tom-readiness-connections-api-20260911.log` |
| `connections-webhook.test.ts` | 61 passed, 0 failed | `work/tom-readiness-connections-webhook-20260911.log` |
| `connections-api-hand.test.ts` | 83 passed, 0 failed | `work/tom-readiness-connections-api-hand-20260911.log` |
| `hands-api-connections.test.ts` | 29 passed | `work/tom-readiness-hands-api-connections-20260911.log` |
| `connections-endtoend.test.ts` | 40 passed, 0 failed | `work/tom-readiness-connections-endtoend-20260911.log` |

Do not sum the nested liveness count as if it were an independent flat test
count. Expected failure-path messages in these logs are fixtures, not evidence
of live provider incidents. The full Worker test/typecheck evidence for the
liveness change remains in `research/2026-09-11-connector-liveness-repair.md`.

Reviewed provider SHA-256:
`0ee0d628b07d49ad2c74f9684675d5e56ab9c231bd026344714664081720f61a`.
This report does not assert that candidate bytes are deployed or installed.

## Other primary documentation checked

Composio's catalogue and toolkit reference establish the available provider
mechanism, not Anticipy's tested support matrix. [Toolkit catalogue](https://docs.composio.dev/toolkits),
[toolkit API reference](https://docs.composio.dev/reference/api-reference/toolkits),
[Notion toolkit](https://docs.composio.dev/toolkits/notion).

Connection expiry subscriptions and event triggers are separate capabilities.
Anticipy's inspected webhook handles authenticated expiry events; it is not a
general implementation of every vendor trigger. [Webhook subscriptions](https://docs.composio.dev/reference/api-reference/webhook-subscriptions),
[provider triggers](https://docs.composio.dev/docs/triggers).

The eval-harness skill influenced this report's explicit evidence gates and
separation of fixture, model, provider and human/device proof. No new connector
framework, application changes or remote actions were introduced.

## Follow-up: are approved API writes reachable?

**Verdict: not through the normal current planner. This is a documented missing
capability, not a missing user approval or a regression caused by the liveness
patch.** The low-level executor supports authorized write fixtures, but that is
not the same as a user task reaching it.

Source trace:

1. `brain/anticipy_core.py:4013` mints a task using `job_lane`, unless a separate
   typed device capability chooses a device lane. `job_lane` calls
   `hands.choose_hand(..., hands.gather_context(...))` at line 1084.
2. `brain/hands.py:1192` gathers connection and browser facts, but line 1211
   supplies `rung=NO_LEDGER_RUNG` unconditionally. `HandContext` is frozen; no
   production caller found supplies a different rung. Its module explanation
   explicitly states that no ledger exists yet and no API write reaches the
   hand today (lines 46–52 and 158–163).
3. `_floors` at line 552 permits a write only with an active connection, write
   opt-in and rung at least 3. Failure returns the browser verdict before tool
   planning. The same floor runs again if catalogue tool metadata tightens a
   declared read into a write (`plan_api_step`, line 1052).
4. `POST /me/connections/writes` changes only the owned connection's
   `writes_enabled` field (`connections_api.ts:932`, `store.ts:1144`). It does
   not create capability-history evidence or promote the rung.
5. Conversational approval in `brain/conversation.py:1768` records authorized
   scope, invokes `workflow.approve`, and requeues that same task. It neither
   changes the lane nor reruns the hand selector. `workflow.approve` at line
   1151 binds the exact plan/version/scope and changes its state; it does not
   establish an API capability rung. Even an explicit replan would still gather
   rung 0.
6. `brain/worker.py:1991` consumes only queued API-lane jobs with an API hand
   note. `routes/hands_api.ts:504` independently requires the matching API lane
   and claimant. Approval is also passed to the low-level hand as confirmation,
   but it does not turn a browser-lane job into an API-lane job.
7. `spike/two-hands/src/router.ts` has a separate experimental ledger-aware
   implementation; no production runtime import or production reader of its
   capability ledger was found. The specification requires verified outcomes
   and per-signature/app progression, not "user clicked yes, set rung 3"
   (`docs/spec-connections.txt:598`, 610 and 658).

This does **not** mean all external writes are impossible: an approved browser
task may use a paired browser, and the separate typed native calendar capability
has its own workflow. Those are different execution paths requiring their own
acceptance proof. The current API read route is reachable.

### Measured reproduction and minimal regression

An independent stdin-only Python probe used actual `job_lane`, `gather_context`,
`choose_hand`, `new_plan` and `approve`, while replacing only the model, connection
facts, browser heartbeat and catalogue with offline fixtures. No product/test
source was edited. Five controls passed, actual exit 0:

- Connected account, writes enabled, no task approval: browser, rung 0.
- Same account and exact version-bound approved plan: still browser, rung 0.
- Same approved plan plus forged `rung=4`/`ledger_rung=4` request params: still
  browser, rung 0. These untrusted values correctly cannot grant authority.
- Equivalent synthetic read: API lane with actual catalogue tool selection.
- Model initially declares read, tool declares write: tightened to write and
  returned to browser at rung 0.

Evidence: `work/tom-connector-rung-reachability-20260911.log`. A fresh complete
router suite also returned **59 passed, 2 explicit live-model skips**, exit 0,
in `work/tom-connector-rung-router-20260911.log`; no live model leg was enabled.

The minimal general regression should preserve this actual caller chain, rather
than constructing `HandContext(rung=3)` as the only positive control. Until a
capability-history implementation is explicitly in scope, assert the current
safe browser result and explain the product limitation. When implementing that
missing feature, add one red-to-green case where a trusted, durable,
owner/signature/app-scoped capability record earned rung 3 and the exact write
opt-in and version-bound payload approval are both present. Require API selection
only for that case; keep absent/stale/foreign records, user-supplied rungs, writes
off and mismatched approval negative controls. The execution boundary must verify
the same authority before a provider effect. A constant change or promotion on
an OAuth/write toggle is not a valid repair.
