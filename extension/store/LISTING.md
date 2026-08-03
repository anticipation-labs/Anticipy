# Chrome Web Store — Anticipy listing package

Status: PREPARED, ONE BLOCKER LEFT. Every claim below is written against code
I opened and read, and carries the file and the thing in it I checked. Upload
is one submission at https://chrome.google.com/webstore/devconsole ($5 one-time
fee, review typically 1–3 days). Expect extra scrutiny for `debugger` — the
justifications are written for that reviewer.

*A note on the citations: I name the file and the symbol or the sentence I
verified, not a line number. `extension/agent_loop.js` and `background.js` are
being edited by other work in parallel and line numbers drift under you; a
symbol name still finds it.*

## The one thing still blocking submission

**The privacy policy page does not exist.** The listing needs a policy URL, and
the URL I have been carrying —
`https://backend-production-61e0a.up.railway.app/privacy.html` — returns 404.
`ls backend/pb_public/` holds exactly two files: `setup.html` and
`anticipy-extension.zip`. There is no policy page to link to, and I can't
create one from the front end: PocketBase serves that directory statically, so
publishing it means deploying the backend service.

I can't submit without it. Chrome asks for a policy URL on any listing that
handles user data, and this one does. Exactly what has to be on that page is
written out under "What the privacy policy has to say" at the bottom — drawn
from the code, so it can be written once and be true.

Everything else in this file is ready.

---

## Name
Anticipy — your hands on the computer

## Summary (132 chars max)
Anticipy does the task you already approved, in your own logged-in Chrome —
and shows you every page she touches.

## Description
Anticipy is a personal assistant that listens to your day, remembers what
matters, and handles the follow-through. This extension is her hands: once you
approve a task in the Anticipy app or by text, she opens the pages, fills the
forms, and tells you plainly what happened — inside your own browser, with
your own logged-in accounts, never with your passwords.

- Pairs to your phone with a 6-digit code. Only your tasks run here.
- You approve the task before it starts, in the app or by text. The browser
  then carries out exactly that, without asking again for every step of it —
  and comes back to you if what it finds is materially different: a different
  price, date, place or person, or a cost nobody mentioned.
- It never types your password or your card number, hands the task back at
  logins and CAPTCHAs, and refuses to operate banking and brokerage sites at
  all.
- Everything happens in a tab group called "Anticipy" that you can open and
  watch, or take over.
- The text of the page Anticipy is working on, and a picture of that tab, are
  sent to an AI model so it can decide the next click — along with the name,
  email and phone you saved in Anticipy, when a form asks for them. Nothing
  else is collected, and nothing is sold or shared.

Requires the Anticipy iPhone app and an Anticipy account.

### Where every sentence above comes from

- **"once you approve … before it starts"** — approval is a flag on the job
  row, set before the run begins. `background.js` passes
  `authorized: params.authorized === true` into `runAgentGoal`, and
  `agent_loop.js` turns that into the model's standing authority (the
  `NOT YET AGREED` / `WHAT THEY AGREED TO` branch in the prompt builder).
- **"without asking again … comes back if materially different"** — the
  `AUTHORITY` block in `agent_loop.js`. It says the owner answered once, that
  the answer covers the whole task, and that ticking "I agree", accepting
  terms and confirmation dialogs all continue. The one stop condition is a
  material difference, and it lists what counts: price, place, date, person,
  extra cost, longer commitment, their saved card being charged.
  *I deleted the previous version of this bullet, which said every
  consequential action waits for a confirmation in the browser. The browser
  never asks. That was the one sentence in this listing the code contradicted
  outright, and it also appears on three other surfaces that still need the
  same correction.*
- **"never types your password or your card number"** — `agent_loop.js`
  instructs the model "never fill payment or password fields", twice: in the
  standing `Rules:` line and again in the owner-profile block. See the honest
  caveat under Permissions, and the `form_submit_demo` note in the test
  instructions.
- **"hands the task back at logins and CAPTCHAs"** — `looksLikeCaptcha()` in
  `agent_loop.js` detects a challenge page and the loop returns
  `stopped at a CAPTCHA/robot check on … — needs a human`. A login wall is one
  of only two permitted `needs_user` reasons in the prompt.
- **"refuses banking and brokerage sites"** — `BLOCKED_DOMAINS` in
  `agent_loop.js`, a hard-coded list outside the model, checked by
  `blockedDomain()` against the current page and again before every
  navigation. It returns `refused: … is a protected financial site`.
- **"a tab group called Anticipy"** — `chrome.tabGroups.update(group, { title:
  "Anticipy", color: "yellow", collapsed: true })`, in `agent_loop.js` for
  autonomous runs and `background.js` for prefilled pages.
- **"page text and a picture of that tab go to an AI model"** — the numbered
  element map is built by `page_map.js` (injected by `agent_loop.js` via
  `files: ["page_map.js"]`), the screenshot by `screenshot()` in
  `agent_loop.js`, which is called on every step ("ALWAYS look"). Both are
  posted to `OPENROUTER_URL`, `https://openrouter.ai/api/v1/chat/completions`.
- **"your name, email and phone when a form asks"** —
  `backend/pb_hooks/agent_key.pb.js:30-43` returns the saved owner profile,
  `background.js` re-reads it at the start of every run, and `agent_loop.js`
  puts it in the prompt under `THE OWNER`.
- **"nothing else is collected"** — the only hosts the extension ever contacts
  are the Anticipy backend (`DEFAULT_BASE` in `background.js`), OpenRouter,
  and — if a key were ever present — CapSolver (see "Before you upload"). A
  grep of `extension/` for analytics, telemetry, gtag, Segment, Mixpanel,
  Sentry and Amplitude returns nothing.
- **"requires the Anticipy iPhone app"** — the phone claims the pair code
  (`ensureRegistered()` in `background.js` mints it,
  `backend/pb_hooks/guard.pb.js:63-80` is the claim route), and nothing runs
  until an owner is set: `claimJob()` returns null on `if (!owner)`.

## Category
Productivity / Tools

## Permission justifications (reviewer form)

- **`debugger`**: Anticipy performs trusted user-gesture clicks and typing on
  pages the user asked it to operate. CDP input events are the only reliable
  way to drive modern event-delegated UIs — `agent_loop.js` dispatches
  `Input.dispatchMouseEvent` for clicks and `Input.dispatchKeyEvent` per
  character for typing. It attaches only for a user-approved task
  (`attachDebugger()`) and detaches in a `finally` when the task ends,
  whatever the outcome. If the user clicks Cancel on Chrome's debugging
  banner, the run stops and hands back rather than re-attaching
  (`userCancelledTabs`).
- **`tabs` / `tabGroups`**: the work happens in a labelled "Anticipy" tab group
  the user can open and take over. When a task ends with nothing for a human
  to look at, `agent_loop.js` closes the tab rather than leaving it behind;
  when it needs them, it activates and ungroups it so it can be found.
- **`scripting`**: reads page structure — a numbered element map — so the model
  can name what to click (`page_map.js`), and sets values that CDP typing
  can't reach, such as a native `<select>` option. No third-party code is
  injected.
- **`storage`**: holds the pairing identity, the model credentials fetched
  after pairing, and the ids of the tabs a run owns (`agentTabs`).
- **`alarms`**: polls the user's own job queue every 5 s and heartbeats every
  10 s while paired (`POLL_SECONDS`, `HEARTBEAT_SECONDS`, `anticipy-poll`,
  `anticipy-heartbeat`).
- **`<all_urls>`**: tasks are open-ended user requests ("book a table at…"), so
  the destination cannot be known in advance. Banking and brokerage domains
  are refused in code regardless.

Honest caveat I would rather the reviewer heard from me: "never fills passwords
or payment fields" is enforced as a model instruction, not as a code-level
field filter. What *is* enforced in code is the blocked-domain list, the
CAPTCHA hand-back, and the refusal of `file` and `range` inputs
(`refused: I don't operate ${type} inputs`).

## Privacy disclosures (data-use form)

- **What leaves the browser, and where it goes.** For each step of a task: the
  text and element map of the page being worked on, plus a downscaled JPEG
  screenshot of that one tab, go to OpenRouter. When a form asks for identity,
  the user's own saved first name, last name, email, phone, date of birth and
  any facts they told Anticipy go in the same request
  (`agent_key.pb.js:30-43` → the `THE OWNER` block in `agent_loop.js`). Task
  goals, statuses and results are written to the user's own Anticipy backend
  (`updateJob()` in `background.js`). Nothing else is transmitted. No
  analytics, no ads, no tracking, nothing sold, nothing shared with anyone
  else.
- **Whose API key and whose model — corrected.** An earlier draft of this file
  told the reviewer that page text goes "to the AI model chosen by the user's
  own account." That is not true and I have removed it. The key is mine, held
  server-side: `backend/pb_hooks/agent_key.pb.js:18` returns a single
  `OPENROUTER_API_KEY` env var to any paired agent. The model is mine too:
  `agent_key.pb.js:24` returns `ANTICIPY_BROWSER_MODEL` or defaults to
  `anthropic/claude-sonnet-4.6`, and `:49` returns the vision model, defaulting
  to `google/gemini-2.5-flash`. The extension fetches that bundle the moment
  pairing lands (`ensureLLMKey()` in `background.js`) and passes the model
  straight into the run. Users never supply, choose, or see a key or a model.
- **Privacy policy URL:** *not yet published — this is the blocker at the top
  of this file.* Intended home:
  `https://backend-production-61e0a.up.railway.app/privacy.html`.

---

## Test instructions (reviewer form)

Anticipy normally pairs to an iPhone app, and I know you don't have one. You
don't need it. Pairing is a 6-digit code claimed over a deliberately open
endpoint, and you can claim it yourself in about two minutes with nothing but
Chrome. The whole path is below. It talks to my live production backend, so
what you see is the real product, not a demo mode.

If any step doesn't behave as written, email me and I'll answer the same day:
hello@anticipationlabs.com

**1 — Install, and read the code.**
Installing opens a welcome tab by itself. Within a few seconds it shows a
6-digit pair code. Write it down. (`chrome.runtime.onInstalled` opens
`onboarding.html`; the code is minted and stored by `ensureRegistered()` in
`background.js`.)

**2 — Find this browser's record.**
Open a new tab and go to this address, replacing `123456` with your code:

```
https://backend-production-61e0a.up.railway.app/api/collections/agents/records?filter=pair_code="123456"
```

You get back one JSON record. Copy its `id`. This lookup is intentionally open
without a token — it's how a brand-new device bootstraps itself — and it only
works when you name the exact 6-digit code that is on screen:
`backend/pb_hooks/guard.pb.js:50-61`.

**3 — Claim this browser as yours.**
Stay on that same page, so you're on the right origin. Open DevTools →
Console, paste this with the `id` from step 2, and press Enter:

```js
await (await fetch(location.origin + "/api/collections/agents/records/PASTE_ID_HERE", {
  method: "PATCH",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ owner: "cws-reviewer", paired: true })
})).json()
```

That is exactly what the iPhone app does when someone types the code into it.
It is allowed without a token only on a record that isn't paired yet, and only
for those fields — once claimed, it can never be re-claimed or re-read
(`backend/pb_hooks/guard.pb.js:63-80`).

**4 — Watch it go live.**
Return to the welcome tab. Within about half a minute it changes to "Paired",
because the worker's heartbeat reads the record back and stores the result. At
that moment it also fetches its model credentials, which the server refuses to
anything unpaired (`agent_key.pb.js:13`).
To skip the wait: `chrome://extensions` → Anticipy → click **service worker**.
Opening it wakes the worker, which polls immediately.

**5 — Give it a real task.**
In that same **service worker** console, paste this once:

```js
const BASE = "https://backend-production-61e0a.up.railway.app";
const { serviceToken, owner } = await chrome.storage.local.get(["serviceToken", "owner"]);
const H = { "Content-Type": "application/json", ...(serviceToken ? { "X-Anticipy-Token": serviceToken } : {}) };
async function anticipyTask(goal, params) {
  const job = await (await fetch(`${BASE}/api/collections/jobs/records`, {
    method: "POST", headers: H,
    body: JSON.stringify({ goal, status: "queued", owner, params: JSON.stringify(params) }),
  })).json();
  const t = setInterval(async () => {
    const j = await (await fetch(`${BASE}/api/collections/jobs/records/${job.id}`, { headers: H })).json();
    console.log(j.status, j.result || "");
    if (["done", "failed", "needs_user", "awaiting_confirm"].includes(j.status)) clearInterval(t);
  }, 3000);
  return job.id;
}
```

Then queue a task:

```js
await anticipyTask("agent_goal", {
  task: "On en.wikipedia.org, search for 'Chrome extension' and tell me the first sentence of the article.",
  start_url: "https://en.wikipedia.org",
  authorized: true
});
```

`authorized: true` is the flag the phone sets when the owner says yes; setting
it here stands in for that approval. Any goal string works — it's a plain
English instruction — so please try your own.

**What you should see.** Within about five seconds — or instantly, since the
backend also pushes new jobs over SSE — a collapsed tab group named "Anticipy"
appears. Expand it to watch. Chrome will show its yellow *"Anticipy started
debugging this browser"* banner; please leave it up. If it's cancelled, the run
stops and hands the task back rather than fighting you. The console prints
`running`, then `done` with a one-line result. The working tab closes itself
when there's nothing left for a human to look at.

**How to stop it.** Set the job's status to anything else. The loop checks
before every step (`jobStillLive()` in `background.js`) and abandons the run:

```js
await fetch(`${BASE}/api/collections/jobs/records/PASTE_JOB_ID`, {
  method: "PATCH", headers: H, body: JSON.stringify({ status: "cancelled" }) });
```

Closing the tab, or removing the extension, also ends it immediately.

**Optional smoke test with no AI involved.**
`await anticipyTask("form_submit_demo", {})` runs a fixed built-in routine: it
opens `the-internet.herokuapp.com/login`, fills the demo username and password
that site publishes on its own page, submits, reads the green banner back, and
closes the tab (`ACTIONS.form_submit_demo` and the `form_submit_demo` branch in
`background.js`). It is a self-test for the tab and scripting path — no AI
model, no real account. Worth knowing when you read the source: those two
hard-coded strings are that test site's own public fixtures, not a credential,
and this is the only code path in the extension that types into a password
field at all.

---

## Before you upload

- [ ] **Publish the privacy policy** (below). Nothing else can proceed.
- [ ] **Confirm `OPENROUTER_API_KEY` is set and funded on the backend.** Without
      it `/agent/key` returns 503 (`agent_key.pb.js:19`) and the first task a
      reviewer queues fails with "no LLM key". The test instructions above are
      worthless if that env var is empty.
- [x] **CapSolver: removed, 2026-08-03.** `solveCaptcha()`/`detectCaptcha()` in
      `agent_loop.js` could pay a third-party service to defeat a CAPTCHA, and
      the loop called it before handing back. It was dead in every shipped build
      (nothing ever wrote `capsolverKey`), but it contradicted this project's own
      non-negotiable rule — "No CAPTCHA/bot-detection bypass. Login walls →
      needs_user, always" (HANDOFF §11) — and a reviewer reading the source would
      have found it sitting against the "always stops at CAPTCHAs" justification.
      Both functions, the option plumbing in `background.js`, and the solver
      branch are gone; `grep -rn capsolver extension/` returns nothing. A CAPTCHA
      now does exactly one thing: stop and hand back to the person.
- [ ] **Decide whether `form_submit_demo` ships.** It's development scaffolding
      that hard-codes a login-form fill. Harmless and public, but it is the one
      place the extension types into a password field, and it will be read as
      one.
- [ ] **Confirm the packaged manifest requests exactly:** `storage`, `tabs`,
      `tabGroups`, `scripting`, `alarms`, `debugger`, and `<all_urls>`. The
      `notifications` permission and its justification are gone from this
      document — there was never a `chrome.notifications` call to justify. If
      the uploaded package still asks for it, this listing is wrong again.
- [ ] **Rebuild `backend/pb_public/anticipy-extension.zip` from the final
      `extension/` folder** so the sideload path and the store package are the
      same software.
- [ ] **Click through the popup on a clean profile before submitting.** A
      reviewer opens it first, and a popup that says the product is broken
      reads as a broken product.

## What the privacy policy has to say

Drawn from the code, so it can be written once and be true. It needs to be a
plain page, publicly reachable with no login, returning 200 — dropped in as
`backend/pb_public/privacy.html` and served at
`https://backend-production-61e0a.up.railway.app/privacy.html`. It is a static
file that touches no hooks and no migrations, but publishing it means deploying
the backend service.

It has to say, at minimum:

1. **What is sent off the machine, and to whom.** The page text and element
   map, plus a downscaled screenshot of the working tab, on every step of a
   task, to OpenRouter. The saved owner profile — first name, last name, email,
   phone, date of birth, and any facts the user told Anticipy — when a form
   asks for them. Task goals, statuses and results, to the user's own Anticipy
   backend. The pairing identity, the browser's user-agent string and a
   liveness timestamp, to the same backend.
2. **What is stored, where, and for how long.** Job rows and agent rows live in
   the Anticipy backend (`backend/pb_migrations/1700000001_jobs.js`,
   `1700000002_agents.js`); locally the extension keeps the pairing identity
   and model credentials in `chrome.storage.local`. Name a retention period.
3. **What it is never used for:** no advertising, no sale, no sharing with
   third parties beyond the model provider named above, no analytics — true
   today, and it needs to stay true.
4. **How to get it deleted,** and a human address that answers.
5. **The iPhone side too,** if this is the product's only policy: the app
   transcribes speech and uploads the text of every finalized line
   (`app/ios/Anticipy/AnticipyApp.swift`, the `heard(_:)` push), and outbound
   texts go through Twilio (`backend/pb_hooks/sms.pb.js`).

## Assets still needed

- Screenshots: 1280×800, 3–5 — the popup, a task running in an expanded
  "Anticipy" tab group, and the pairing page.
- A promo tile (440×280), only if we want to be considered for featuring.
