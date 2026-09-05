# Composio: what the Connections spec changes, and what is actually connected

**Date:** 2026-09-05 (late evening)
**Source:** `Anticipy-Two-Hands-and-Connections.pdf`, memo 2 and spec 4
(pages 18–31), read end to end.
**Companion:** `research/2026-09-05-two-hands-signatures.md` (account, project,
key), `spike/two-hands/` (the week-1 spike).

## Four things the spec contradicted in what was already set up

Reading it changed the setup rather than confirming it. Each of these was live
and wrong before the read.

**1. `manage_connections` was ON.** The spec's decision is explicit — "Create
sessions with `manage_connections` off so the model can never paste a raw
Composio link into a text" — and the first sessions had it enabled, so
`COMPOSIO_MANAGE_CONNECTIONS` was in the model's tool list. The accepted input
shape is **`{"manage_connections": {"enable": false}}`** (note: `enable` on the
way in, `enabled` in the config that comes back; `{"enabled": false}` is a 400,
and a bare boolean is a 400). With it off the tool list is
`COMPOSIO_MULTI_EXECUTE_TOOL, COMPOSIO_SEARCH_TOOLS, COMPOSIO_GET_TOOL_SCHEMAS,
COMPOSIO_REMOTE_WORKBENCH, COMPOSIO_REMOTE_BASH_TOOL` — the connection tool is
gone, which is the point.

**2. `user_id` was `omar`, a name.** The spec: "Our PocketBase user id is
Composio's `user_id`. One session per user, restored by stored `session_id`."
And the owner's own answer when asked: it binds to *whoever is using the iOS
app*. So it is the owner row id, resolved per user, never a constant. It is
`sxkotd1h02qb6gw` here because that is the owner record for the person at this
machine. Changed before any connection existed, which is the only cheap moment
to change it.

**3. The links were sent before they were tapped.** Four connect links were
generated and handed over to be clicked later. Composio's links expire in **10
minutes**, and all four expired unused — the spec says exactly this ("generate
it when they tap, not when we send the text") and it proved itself within the
hour. Generate at tap time.

**4. Raw Composio links were used as the ask.** `connect.composio.dev/link/...`
went straight into a message. The spec forbids it: every link must be
`anticipy.ai/c/{token}`, single-use, 10 minutes, bound to the user, needing a
signed-in session or a one-tap phone code, "Never the raw Composio or Google URL
in a text." Acceptable for the week-1 spike, where the memo asks for the Connect
Link directly — but it is Week A work and must not survive into any user-facing
path.

## What is connected, measured

Owner `sxkotd1h02qb6gw`, project `anticipy_two_hands`, alias `work`:

| toolkit | status | account | note |
|---|---|---|---|
| `gmail` | **ACTIVE** | jose@anticipy.ai | `ca_BNgvxQtJ703C` |
| `googlecalendar` | **ACTIVE** | jose@anticipy.ai | `ca_sHENw6KtQ8Kx` |
| `notion` | INITIATED | — | this Chrome is not signed in to Notion |
| `slack` | INITIATED | — | signed in, but see below |

**Slack is blocked by workspace policy, not by us.** The account is signed in to
the **Base44** workspace and Slack answers *"You are not authorized to install
Composio on Base44 — you do not have the appropriate permissions to install this
app on this Workspace."* It needs a Slack App Manager on that workspace, or a
workspace where this account has rights. No amount of retrying fixes it.

**Notion stopped deliberately.** The connect flow lands on Notion's login. The
only no-password route is "Continue with Google", and if no Notion account
exists for that address that *creates* one. Creating accounts is not something
Claude does, so it stopped there. Sign in to Notion in that Chrome and the
connect completes in one click.

## The Gmail scope, recorded because it needs undoing

Composio's **managed** Google app requested `https://mail.google.com/` — read,
compose, send **and permanently delete** all mail. The owner accepted it for the
spike explicitly, and the reasoning is worth keeping: the spec says the opposite
("Scopes are the minimum"; start with sensitive scopes only; add restricted
Gmail read scopes "only when a real use needs them", because they trigger a paid
CASA lab assessment, ~6 weeks, repeated yearly). The ten spike tasks are
read-only and do not need it.

So this is a **debt with a name**: when Anticipy's own Google OAuth app is filed,
this connection is disconnected and remade against narrow scopes. Until then a
full-delete token exists on a real mailbox. Calendar, by contrast, asked only for
`calendar` and `calendar.events` — appropriately narrow, nothing owed.

## What the spec requires that does not exist yet

Week A and B in the memo, none of it built. Listed because the spike currently
does none of it and a reader should not mistake a working key for a working
product.

- `brain/connections/` — `signals.ts`, `policy.ts`, `nudges.ts`, `composio.ts`,
  `connect_page.ts`, `text_commands.ts`
- four tables — `app_usage_signals`, `connections`, `connect_nudges`,
  `connect_links`
- the `anticipy.ai/c/{token}` page: single-use token, 10 min, signed-in check,
  generic render from toolkit metadata, three plain permission sentences
  generated from scopes, callback + `wait_for_connection` (Composio has **no**
  success webhook, only `expired`)
- disconnect = **revoke then delete**; delete alone leaves the token live at the
  provider, and ~5% cannot be revoked programmatically
- the nudge state machine: `never_asked → asked → declined L1/L2/L3 →
  connected → needs_reconnect`, snoozes 14/45/stop, one ask per user per 7 days
  across all apps, never mid-step, never before the task result, 72h silence is
  a soft no
- Settings "Connected apps" with the per-app **"let Anticipy make changes"**
  toggle, off by default — this is the write opt-in the Two Hands ladder needs
  for rung 3, and `spike/two-hands/src/ledger.ts` already expects it
  (`writesOptedIn`)
- iOS: OAuth in Safari or `ASWebAuthenticationSession` only, never a web view,
  or Google refuses with `disallowed_useragent`

## Owner-only, from the compliance list

- Accept the **DPA** on the Composio billing page
- Turn on the **"Don't store data"** log switch (default is store everything)
- File Anticipy's own Google OAuth app + brand verification
- 10DLC (US) and a verified toll-free number (Canada) before launch texts
