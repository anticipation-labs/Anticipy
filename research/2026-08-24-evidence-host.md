# The evidence host — where a receipt photo lives

Built 2026-08-24/25 on `jose_anticipy_system`. Scope: `backend/` and `tests/`.
Unblocks MOUTH's "DONE = EVIDENCE" step and WIRE IT ALL's step 2
("act → evidence → done-text with photo"), which were both waiting on a place
for an image byte to exist.

New: `backend/pb_migrations/1700000045_evidence.js`,
`backend/pb_hooks/evidence.pb.js`, `tests/test_evidence_host.py`,
`tests/test_workflow_guard_fails_closed.py`.
Edited: `backend/pb_hooks/guard.pb.js`, `backend/pb_hooks/account_delete.pb.js`,
`backend/pb_hooks/workflow_guard.pb.js`.

---

## 1. What I verified myself, against what the card said

Every claim in the brief was re-checked at file:line before anything was built.
All four were **true**, and two of them were true in a way that changes the
design.

**`receipt.evidence` is a list of short strings, not URLs to anything, and not
a picture.** Built at `extension/workflow_state.js:110-130`: each entry is
`String(x).trim().slice(0, 1000)`, at most 12 of them, and the shapes come from
`verificationEvidence` at `extension/agent_loop.js:1728-1748` —
`url:<page url>`, `title:…`, `page:<content fingerprint>`, `facts:<keys>`,
`proof:<kind>`, `journal:<url#hash,…>`. The `url:` entries are the pages the
browser stood on. They are reachable by anyone with that browser's session and
by nobody else; they are an audit index, not something a person reads and
believes. The file's own comment (`workflow_state.js:111-114`) says the receipt
is deliberately "a compact proof index" because duplicating the full result
overflowed PocketBase's text validation and turned verified successes into
HTTP 400.

**`workflow_guard.pb.js` demands exactly three things and no shape beyond
them** (`workflow_guard.pb.js:202-211`, now :222-231 after my edit): a parseable
`receipt`, `receipt.verified` truthy, `receipt.effect_key` equal to the row's
`effect_key`, and `Array.isArray(receipt.evidence) && evidence.length > 0`. It
never inspects an element. So an image reference can be added to that array
without touching the guard at all.

**PocketBase can hold a file, and nothing here has ever used one.** Zero
`type: "file"` across all 44 prior migrations, confirmed. The house pattern for
a migration is `new Collection({...})` with a plain field array
(`1700000001_jobs.js`), or `fields.add(new Field({...}))` for a column
(`1700000025_job_workflows.js`), and — this is the part that matters — the
newest migrations **read themselves back and throw when the change did not
land** (`1700000044_purges_markable.js:39-47`, with a comment saying a rule
that did not land is invisible until the next real request). Column-migration
machinery does now exist; the brief's caution was already stale.

**`VoiceArm.text()` is strictly `From`/`To`/`Body`** (`brain/voice_arm.py:410-420`).
`MediaUrl` appears nowhere outside `overnight/stranger_gate.py` and its tests.

### The two things that changed the design, which the card did not say

**The screenshot is not taken at the moment that matters.** `screenshot(tabId)`
(`extension/agent_loop.js:105-143`) is called at one site only,
`agent_loop.js:5003`, and only when `needsEyes()` says the page is a calendar,
seat map or slider. It is a half-scale, quality-45 JPEG, capped at 400 KB, and
it is passed to `llmStep` and dropped. **There is no capture at the confirmation
page**, so even with this host in place there is nothing to upload until the
extension takes one. That is extension-tree work and it is named in §5.

**Peak disk cost is 3×, not 8×.** `1700000018_daily_backups.js` set
`cronMaxKeep = 7`, but `1700000037_backup_footprint.js` cut it to **2** —
because PocketBase zips pb_data (storage included) into `/pb_data/backups`, on
the same volume it is a snapshot of. Peak is two kept plus the one being
written. I had the 7 in my first draft of every comment and corrected it; the
ceilings below are sized on 3.

---

## 2. Where the bytes live, and why

**A PocketBase `file` field on a new `evidence` collection, on the existing
Railway volume.**

### Is the filesystem ephemeral?

For the container image, yes. For `/pb_data`, **no — it is an attached volume**,
and the whole product already bets its life on that. The evidence is in the
repo, not in a Railway config (there is no `railway.json`/`railway.toml` in the
tree at all; volumes are configured in the dashboard):

- `backend/start.sh:4-15` measures `df -Pk /pb_data` at every boot and serves
  with `--dir /pb_data`.
- `audit_retention.pb.js:3-11` records the 2026-08-15 outage: the audit ledger
  "filled the 5GB production volume to 4996MB", SQLite could not write any row,
  and the fix was deleting rows — which only makes sense on storage that
  survives a restart.
- `1700000037_backup_footprint.js:4-11` says it outright: backups land on "the
  same 5GB Railway volume", and "restarting the container cannot undo it".

PocketBase writes file-field uploads under `<dataDir>/storage/...`, i.e. the
same volume as `data.db`. **That is the one thing here I could not execute** —
there is no PocketBase binary in this tree — so it is on the LIVE list (§6).

### Why not the alternatives

| Option | Verdict |
|---|---|
| **PocketBase file field** (chosen) | Persistent, free, no new vendor or credential, and PocketBase already does the multipart parsing, the size ceiling and the mime allowlist. Costs volume headroom, priced below. |
| A bespoke route writing to a Railway path | Same bytes, same volume, more code, and it would need `$filesystem`/base64 JSVM APIs I cannot verify without a PocketBase binary. No advantage. |
| Object storage (S3/R2) | Correct long-term answer and `1700000037` already says so about backups. Needs credentials this image does not have and a monthly bill, for one screenshot per completed errand. **Owner decision, not mine — priced in §7.** |

### The disk cost, priced

`maxSize: 400000` matches the extension's own screenshot ceiling
(`agent_loop.js:129`) exactly, so an upload never fails at a different
threshold than the capture. `KEEP_TOTAL = 60`, `KEEP_PER_OWNER = 20`, swept on
every create (the `audit_retention.pb.js` pattern — a sweep at the write door,
not a cron, because the recorded outage happened between crons).

Worst case: 60 × 400 KB = **24 MB live, ~72 MB at peak** with both backup
snapshots. Realistic case is far smaller — a quality-45 half-scale JPEG of a
confirmation page is 40–120 KB, so ~5 MB live. On a 5 GB volume that has
already been to 4 MB free, 72 MB is a number that cannot take the product down
by itself. That was the design constraint.

---

## 3. Who may fetch it — the exposure decision, and what it costs

**The exposure is real and it is unavoidable if the photo is to reach a phone
at all.** Twilio does not accept bytes, a `data:` URI, or an authenticated URL
for `MediaUrl`. It takes a URL, fetches it from its own infrastructure with no
credential of ours, and attaches what comes back. So somewhere there has to be
an https URL that answers an anonymous GET with a photograph of a page the
owner was logged into.

**What I chose: default-deny, with an expiring, fetch-capped window minted one
message at a time.** Not an unguessable path alone, and not a permanent
capability token.

- **Default deny.** `share_expires` empty means **no public URL exists**. A row
  nobody deliberately shared is unreachable to somebody holding the exact path.
  The normal state of an evidence photo is "not on the internet".
- **The path is unguessable anyway** — PocketBase's 15-character record id plus
  the 10 random characters it appends to every stored filename — but
  unguessability is a delay, not a lock, so nothing rests on it.
- **A window is 15 minutes** (`SHARE_WINDOW_MS`) and is opened by
  `POST /evidence/share`, **service token only**, on one named record, in the
  moment the worker is about to send. Twilio fetches within seconds.
- **A window also dies after 5 fetches** (`SHARE_FETCH_LIMIT`), because expiry
  alone leaves a leaked URL an unlimited download until it lapses. Retries are
  covered; a scraper is not.
- **Two other doors, neither of which spends the ceiling or needs a window:**
  the service token (the worker), and the owner's own account auth checked
  against `owner_ref` **and** against the auth record's collection being
  `owners` — `e.auth` is populated for any auth record in PocketBase 0.30.4,
  superusers included (`guard.pb.js:358-366`).
- **Every refusal answers identically** (`404`, same body). Telling an anonymous
  caller apart "no such row" / "never shared" / "expired" / "spent" is an oracle
  for walking record ids.
- **Every other collection's `/api/files/` path is refused outright.** None has
  a file field today; if one is added it has to come and say so in
  `evidence.pb.js` rather than inheriting an anonymous public URL by accident.

### What this does NOT protect against, said plainly

**Once Twilio has fetched the image it holds its own copy and delivers it to a
handset. Nothing here can expire that.** Shortening our window does not shorten
theirs, and the recipient's phone keeps the picture forever. So the decision to
send a picture *at all* is the owner's; this design only ensures the picture is
not *also* sitting on an open URL for the rest of its life.

### LOCAL-FIRST

`design/LOCAL-FIRST.md` rule 3: "What travels is the smallest conclusion that
works." A full-page capture is not a conclusion, and this backend's own posture
on image bytes elsewhere is to **redact and hash** them — `agent_key.pb.js:70-90`
replaces every screenshot passing through the model proxy with
`[IMAGE_BYTES_REDACTED]` plus a sha256 and a byte count.

I do not read LOCAL-FIRST as forbidding this, and here is the reasoning, so it
can be overruled: rule 1 forbids raw audio leaving a device absolutely; rule 3
is a minimisation principle, and the doc's own SMS row accepts Twilio because
"message content is already the conclusion". A screenshot of a confirmation
page is closer to a conclusion than to a raw stream — it is the artefact the
errand produced. But it is not *small*, and it is not *distilled*.

**So the host is built closed.** Nothing in this tree uploads a picture, and no
window is ever opened unless something holding the service token asks for one,
deliberately, per message. The law question — *may a photograph of the owner's
screen be sent through Twilio at all* — is left to the owner, and it is now a
one-line decision in the brain rather than an architecture project. That is the
honest split: the mechanism is not a policy, and I did not smuggle a policy in
by shipping it switched on.

---

## 4. What happens when it is gone

An expired, swept, deleted or never-uploaded picture **must not break the text**,
and a broken link is worse than no link: `MediaUrl` pointing at a 404 makes
Twilio fail the *whole message*, so the person gets nothing instead of the
sentence.

`POST /evidence/share` therefore never returns an error for an absent picture.
It returns `200 {ok: false, reason: "...", url: ""}` for every absence — no such
record, no image on the record, no id named, no https base URL configured. The
caller's contract is:

```
r = post("/evidence/share", {"id": evidence_id})
media = [r["url"]] if r.get("ok") else []       # and the text still goes
```

Pinned by `test_a_missing_picture_is_an_answer_not_a_broken_link` and
`test_without_a_public_base_url_no_link_is_invented`. A fetch that cannot be
*counted* is also refused rather than served (the pair-code throttle's posture,
`guard.pb.js:127-138`) — the cost is a text arriving without its picture, which
is this same fallback.

---

## 5. What the app, the brain and the extension still owe

None of these is in my scope. Each is small and each is named precisely.

**`extension/` — capture and deposit (the biggest missing piece).**
1. Call `screenshot(tab.id)` at the *verified done* milestone, not only when
   `needsEyes()` fires. Today the only call site is `agent_loop.js:5003`.
2. POST it to `/api/collections/evidence/records` as multipart, with the agent
   credential headers it already sends, `owner_ref` = its own owner, `job` = the
   job id, `effect_key` = the job's effect key. `guard.pb.js` now allows exactly
   that one request and refuses an `owner_ref` naming anybody else.
3. Put the returned record id into the receipt it already builds at
   `workflow_state.js:110-130` — e.g. an `evidence:<record id>` entry. The
   backend guard needs no change: it counts the array, it does not inspect it.

**`brain/` — carry it.**
4. `VoiceArm.text(to, body, media=None)` → add `MediaUrl` to the form post at
   `voice_arm.py:410-420`. This is `stranger_gate` leg 8 and it is small.
5. Before sending a done-text, read `receipt.evidence` for an `evidence:` entry,
   call `POST /evidence/share`, and pass the URL through — **falling back to no
   media on `ok: false`**, per §4.
6. `worker.py:1573-1583` composes the done text from `{"task": goal,
   "what_you_found": result}`. `result` is the browser model's own done-claim
   sentence, which is the "model grading a model" the card names. It should be
   fed the server-verified `receipt`, not `result`.

**`app/ios/` — render it.**
7. `AgentJob` (`AnticipyBackend.swift:5-46`) has no `receipt`. Add
   `let receipt: String?` plus its `init`/`withStatus`, decode it, and feed it
   to `JobReceiptPolicy.doneCard` (`ContentView.swift:1889`). That is
   `stranger_gate` leg 7.
8. **`AsyncImage` will not work here** and this is worth saying loudly: the
   evidence URL requires an `Authorization` header, and `AsyncImage` cannot set
   one. The app must fetch with `URLSession` + the account token and hand the
   data to `Image(uiImage:)`. The alternative — making the file publicly
   readable so `AsyncImage` works — would delete the entire protection in §3.
9. `guard.pb.js` now lets the signed-in owner list and view `evidence` rows
   scoped to their own account, so the app can find the row for a job.

---

## 6. What waits on LIVE (Law 3 — repo-green is not done)

**Nothing here is proven until an image actually reaches a phone.** There is no
PocketBase binary in this tree and no Twilio account attached to it, so these
are assertions from documentation and from this repo's own recorded behaviour,
not measurements:

1. **That a PocketBase `file` field lands on `/pb_data/storage`.** Everything
   about the disk arithmetic assumes it. Check `du -sk /pb_data/*` in the boot
   log after the first upload — `start.sh:9` already prints it every boot.
2. **That the migration applies.** It is executed in a node harness with a fake
   app (`test_the_migration_runs_and_creates_what_it_says_it_does`), which
   catches syntax and shape errors but not PocketBase's real `Collection`
   validation. Watch the boot log for
   `evidence: a place a receipt photo can live…`; the migration throws rather
   than logging if the file field or the null rules did not land.
3. **That `e.requestInfo().body` is populated for multipart.** The guard branch
   that binds `owner_ref` to the agent's owner reads it. PocketBase's own API
   rules use the same struct for `@request.body` on file uploads, so this should
   hold — but if it does not, the branch fails *closed* (the comparison against
   `ownerRef` fails and the upload is refused), which is the right direction to
   be wrong in. It would show as the extension unable to deposit at all.
4. **That Twilio fetches the URL inside the window.** Watch for a `fetches`
   value of 1 on the row after the first MMS.
5. **MMS deliverability at all.** The `From` number is Canadian; Twilio MMS is
   US/Canada only and is not enabled on every long code. Worth checking before
   anyone concludes the host is broken.
6. **That `railway up` actually shipped it.** Prod has served stale code twice.

---

## 7. If the owner wants a different answer

Reported as options rather than chosen for him, because two of them cost money
and one changes what leaves his machine:

| Option | Cost | What changes |
|---|---|---|
| **What is built** — PocketBase file field, 15-minute default-deny window | £0, ~72 MB peak volume | A photo is fetchable by Twilio for 15 minutes, 5 fetches, per message. Twilio keeps its own copy. |
| **App-only, never Twilio** | £0, same disk | The photo appears on the done card and is *never* on a public URL. Delete `POST /evidence/share`. The text says "photo in the app". Strictly safer; `stranger_gate` leg 8 stays red. |
| **Object storage (R2/S3)** | ~$0–5/mo + credentials | Removes the volume risk entirely; PocketBase supports S3 natively. Same public-fetch exposure. Also fixes the backup-on-the-same-volume problem `1700000037` documents. |
| **No photo at all** | £0 | The done-text carries the receipt's *words* — the confirmation number is already in `receipt.evidence` as a `page:` fingerprint and in `jobs.result`. Cheapest, and honest. |

---

## 8. The `workflow_guard` fail-open (additive, from the coordinator)

Verified independently before changing anything, then driven.

`workflow_guard.pb.js:167` demanded owner approval before `queued` only when
`consequence === "consequential"` — **one exact string**. Anything else skipped
the entire approval block and reached `queued` unapproved: a typo, an empty
value, a truncated write, an older client, or any third enum member added
later. Driven at `tests/test_workflow_guard_fails_closed.py`, before the fix:

```
consequence="consequentia"  -> {'outcome': 'next'}   # reached queued unapproved
consequence=""              -> {'outcome': 'next'}
consequence="reversible"    -> {'outcome': 'next'}
```

and after:

```
8 passed
```

Every other layer already failed the other way — `brain/workflow.py:64-68`
(`_consequence_or_safe`, unreadable → CONSEQUENTIAL), `extension/background.js:1062`
and `:1300-1301` (`!== "read_only"`, an allowlist), `AnticipyApp.swift:1352`
(missing key → `"consequential"`). **The database guard, the layer this
architecture calls the final authority, was the only one that failed open.**

Fixed by enumerating the safe set: `const NO_APPROVAL_NEEDED = ["read_only"]`,
and everything else — including anything unrecognised — needs approval bound to
the exact plan version. **An array, not an object-as-set**: `{read_only:1}[x]`
is truthy for `constructor`, `toString`, `valueOf` and every other name on
`Object.prototype`, so the obvious lookup would have shipped with half a dozen
undocumented exemption keywords an attacker can simply type. Pinned by
`test_an_inherited_property_name_is_not_an_exemption_keyword`.

**There was no test driving this hook at all before tonight.** That is why it
survived: `tests/test_approved_card_is_closed_to_edits.py` and
`tests/test_goal_spelling_matches_the_plan.py` both cite `workflow_guard` by
line number and neither has ever executed a byte of it.

**On the `cancel` note** (not mine to fix): confirmed at
`brain/anticipy_core.py:98` — `cancel(?:s|led|ling|ed|ing)?` is inside
`_VERBS`, which feeds `_IRREVERSIBLE_RE` at `:118`. So a one-tap undo of an
errand is classified world-changing and, after this fix as before it, is held
for a second tap. That was already true; my change does not make it worse, and
the right repair is in `brain/` — undoing something Anticipy did is not the
same kind of act as doing it.

---

## 9. Mutation testing — and the harness that lied

**33 mutations, 33 caught, 0 survivors.** Each breaks one behaviour, names the
check that goes red, and is restored.

The first run reported **all 29 mutations surviving**, including one the very
first test in the file asserts. The mutation harness itself was fail-open: it
passed a stripped `PATH` to the pytest subprocess, Xcode's python3 was picked
up, `No module named pytest`, stdout was empty, no line began with `FAILED`, and
an empty failure set was read as "nothing broke". It now inherits the real
environment and **refuses to return a verdict unless pytest printed a summary
line**. This repo has found nineteen fail-open rules tonight and mine had the
disease too.

Six real gaps in my own tests were then found by the fixed harness and closed:

1. **The migration tests read the header comment, not the code.** The header
   explains the bug by quoting `type: "file"` in a sentence about there being
   none, so `re.search(r'type:\s*"file"')` passed with the field mutated away.
   All migration assertions now strip `//` comments first.
2. **The readback test could not tell "checked" from "mentioned"** — mutating
   the condition to `if (false)` left `fresh.updateRule` intact inside the
   error *message*. Replaced with a node harness that **executes the migration**
   against a fake app which drops the file field, downgrades its type, or opens
   a rule, and asserts the migration throws each time.
3. **No test for an unset service token** on the fetch door (`"" === ""`).
4. **Re-sharing a spent picture** never checked that the ceiling resets.
5. **The per-owner cap was masked by the global one** — a test with 200 rows
   for one owner passed on the global sweep alone. Now two owners, 35 rows
   total, under the global ceiling, so only the per-owner cap can fire.
6. **The collection-id bypass mutation pointed the wrong way** (it made the gate
   stricter, not looser); rewritten to the actual bypass.

Suite: **1596 passed, 0 failed** (`--ignore=tests/test_day_zero_oracle.py
--ignore=tests/test_outcome_rate.py`; the latter is another agent's in-flight
work — it imports `proof.outcome_rate`, which does not exist yet, and errors at
collection).

---

## 10. Concerns

- **Law 3.** Nothing above is proven. An image has not reached a phone, and it
  cannot until the extension captures one and the brain carries it. §6 is the
  list.
- **The scratchpad is shared between the parallel agents, not session-isolated.**
  A plain `mutate.py` I wrote there was overwritten by another agent's script
  between my patching it and my running it, and I ran their mutation suite
  believing it was mine. Anything left in
  `/private/tmp/claude-501/.../scratchpad` under a generic name is at risk.
- **`guard.pb.js` grew two branches.** It is the most dangerous file in the
  backend and I widened it. Both changes are narrow (one POST path bound to the
  credential's own owner; one name added to a collection allowlist whose
  owner-scoping already existed) and both are mutation-tested, but they deserve
  a second pair of eyes.
- **`e.requestInfo().body` on multipart** is the one unverified assumption in
  the write path. It fails closed if wrong (§6.3).
- **The oracle-suppression choice costs debuggability.** Every public refusal is
  an identical 404, so a real "why is the picture missing" investigation has to
  read the row, not the response. The `console.log` on an uncountable fetch is
  the only breadcrumb.
