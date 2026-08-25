# MOUTH — the picture is taken where the judgement was made, or it is not taken

> Status: SPEC. Not a plan, not a sequence, no code, no task list.
> Card: HANDS 3 step 2 — "screenshot capture at milestones → stored as evidence
> rows" — meeting WIRE IT ALL step 1, "act → evidence → done-text with photo"
> (`docs/BOARD-STATE-2026-08-24.md:52-53`). The Brief's moments 28, 30 and 31
> are the same rung: *"The 'done' text carries evidence: the confirmation
> screenshot, the receipt, the calendar entry. Done without proof doesn't
> exist."*
> Sibling: `docs/superpowers/specs/2026-08-25-mouth-photo-receipt.md` settles
> the CARRY (receipt → share window → `MediaUrl`). This one settles the
> CAPTURE. Its handed-back item 7 — "When and how does `extension/` take the
> picture?" — is this document.
> Laws that bind: `HARNESS-LAWS.md` 1, 2, 3, 5, 6. `design/LOCAL-FIRST.md`
> rules 3 and 5.
>
> **Read this before anything else: the capture is not missing. It landed ten
> hours before this spec was written** — commit `4d123e08`, 2026-08-25
> 02:09:00 -0700, which introduced `captureMilestone`, `takeEvidenceShot` and
> `depositEvidence` in one go. Every sentence in the sibling spec, in
> `research/2026-08-24-evidence-host.md` and in
> `backend/pb_migrations/1700000045_evidence.js` that says the browser never
> takes a picture at the moment that matters is **now false**, and each of
> those documents is still in the tree saying it.
>
> So this spec is not a proposal for work nobody has done. It is three things:
> the settlement of a design that is already in the tree, written down where
> Law 4 says it goes; **one defect I reproduced by execution**, in which a
> done-text ships a photograph of an *unsubmitted form* as proof of a completed
> booking (§6); and the fact that **production has none of it** — I fetched
> production today and the extension it serves is 0.8.4 with zero occurrences
> of any of this, and the backend answers `/evidence/share` with PocketBase's
> own 404 (§2).

---

## 0. The three sentences

1. **The picture is taken at the instant a done claim was BELIEVED**, by
   `screenshot()` through `captureMilestone("verified-done", …)`, immediately
   after `verifyDone` returned verified against a freshly re-read page.
2. **Exactly one row is deposited per errand**, by `depositEvidence`, as a
   multipart POST on the browser's own agent credential, and its id is
   **prepended** to the receipt as `evidence:<id>`.
3. **A capture that fails costs nothing**, at five separate points — but today
   there is a sixth point where a capture that fails costs something worse than
   nothing: it silently substitutes an older frame. That is §6, and it is the
   only defect in this document.

---

## 1. What is in the tree, checked line by line this session

Every row read at the file. Nothing inherited from the sibling spec or from
`research/2026-08-24-evidence-host.md`, both of which are stale on this.

| Piece | Where | State |
|---|---|---|
| The camera | `extension/agent_loop.js:112-143` `screenshot(tabId)` | Built long before this work — one JPEG over CDP `Page.captureScreenshot`, with a blank-frame floor (`:130`) and a ceiling with one quality-25 retry (`:133-139`). |
| The milestones | `agent_loop.js:4141-4155` — `milestoneMarks`, `milestoneShot`, `captureMilestone` | **New (`4d123e08`).** Two named moments, one frame kept, one text mark per milestone whether or not the frame arrived. |
| Where they fire | `agent_loop.js:5370` and `:5726` (`verified-done`); `:6074` and `:6304` (`before-commit`) | **New.** Four call sites, two per milestone, because there are two done exits and two ways a form is submitted. |
| The frame leaving the run | `agent_loop.js:5371-5374`, `:5727-5730` — `evidenceShot: milestoneShot` | **New.** |
| The frame being TAKEN, not copied | `extension/background.js:1239-1244` `takeEvidenceShot` | **New**, and it exists because a mutation deleting the old inline `delete out.evidenceShot` turned **zero** checks red (`research/2026-08-25-hands3.md:216-238`, mutation M8). |
| The bytes | `background.js:1215-1228` `jpegBytes` | **New.** `atob` rather than `fetch("data:…")`, deliberately, so the one function that must work while `fetch` is a scripted stub is testable. |
| The deposit | `background.js:1254-1291` `depositEvidence` | **New.** Multipart, agent credential, `owner_ref` from `chrome.storage.local`, every failure returns `""`. |
| The wiring | `background.js:1568-1570`, `:1594` | **New.** Deposit before the receipt is written; id prepended to the evidence array. |
| The receipt cap | `extension/workflow_state.js:116-118` | Pre-existing. Keeps the **first** 12 entries — which is why the prepend at `:1594` is load-bearing and not a style choice. |
| The door for the upload | `backend/pb_hooks/guard.pb.js:342-346` | Pre-existing (2026-08-24). CREATE only, and only when the body's `owner_ref` equals the one this credential resolves to. |
| Somewhere to put it | `backend/pb_migrations/1700000045_evidence.js` | Pre-existing. `image` is `type:"file"`, `maxSelect:1`, `maxSize:400000`, jpeg/png only; `updateRule`/`deleteRule` are `null`. |
| The public door | `backend/pb_hooks/evidence.pb.js:56-147` (fetch), `:157-224` (mint), `:244-…` (sweep) | Pre-existing. Default-deny, 15 minutes, 5 fetches, one 404 for every refusal. |
| The carry | `brain/evidence.py`, `brain/worker.py:1876-1877`, `brain/voice_arm.py:413-459` | **Also new, also today.** The sibling spec's five-signature chain is threaded end to end; `MediaUrl` is posted at `voice_arm.py:426`. |
| Tests | `extension/tests/test_evidence_capture.mjs`, registered at `extension/tests/run_all.mjs:21` | **New**, 24 checks. |
| Gate | `overnight/stranger_gate.py:1593` leg 8 | Pre-existing, tree-only, and I ran it: **PASS** — "the outgoing text can carry the evidence picture". |

**The honest summary of that table: everything is built and everything is
green, and none of it has ever run.** That is precisely the state Law 3 was
written about.

---

## 2. What is LIVE, which is nothing — verified today, not inherited

Three probes against `https://backend-production-61e0a.up.railway.app`, run
this session.

**The extension production serves has none of this.** I fetched
`/anticipy-claude-version-extension.zip` (200, 122,423 bytes) and opened it:
manifest version **0.8.4**, **12 files**, and in its `agent_loop.js` and
`background.js` the strings `captureMilestone`, `evidenceShot` and
`depositEvidence` occur **zero times each**. The committed artifact in the tree
is a different package — 273,372 bytes, 20 files, 0.11.0, byte-identical to
`extension/` — and it *does* carry the capture (5 and 2 occurrences). Stranger
gate leg 1, run this session, says the same thing in its own words: *"the app
tells the stranger to press Reload to get 0.11.0; the only download in the
product serves 0.8.4."*

**The evidence host is not deployed either.** `POST /evidence/share` returns
`404 {"message":"The requested resource wasn't found."}` — PocketBase's own
body, not the hook's `{"error":"forbidden"}`, so `routerAdd` at
`evidence.pb.js:157` is not registered on that server.
`GET /api/files/evidence/<id>/<name>` returns `404 {"message":"Missing or
invalid collection context."}` — again PocketBase's body, not the hook's
`{"error":"that evidence is not available"}`, so the `routerUse` fetch door at
`:56` is not running either. **The live backend predates `evidence.pb.js`
entirely.**

**What that means for every claim in this document.** Nothing here is fixed.
Two deploys stand between the tree and the first photograph: a backend deploy
carrying `1700000045_evidence.js` and `evidence.pb.js`, and a `pb_public`
deploy carrying the 0.11.0 zip. Both are `railway up`, which
`CLAUDE.md` records as reporting success while failing.

**What does NOT block it: a working iOS build.** The ears are dead — zero
transcript rows in ~31 hours, builds 76-80 delivered none, build 82 is compiled
and not installed — and that blocks everything downstream of the microphone.
This loop is not downstream of the microphone. A job reaches the planner from
the inbound SMS lane as well (`brain/worker.py:709` `WEBHOOK_PATH`, into
`brain/anticipy_core.py:3522` → `brain/workflow.py:991`), so act → evidence →
done-text can be exercised from a text message with no phone build at all.
**I traced that path; I did not run it.** Anyone who claims this feature is
blocked on build 82 should be asked which line they read.

---

## 3. Non-goals

- **No implementation.** Written to be executed by somebody else.
- **No second picture per errand.** The 60-row global cap
  (`evidence.pb.js:246`) is a disk ceiling, not a preference; two rows per
  errand halves how far back the photos go without doubling what anyone can
  see. §17 hands the question back rather than answering it.
- **No new capture site.** Not on failure, not on `needs_user`, not on cancel —
  even though the Brief's moment 30 asks for one (§17, item 2). Adding capture
  sites is a decision about what may be photographed, and it is not mine.
- **No change to `screenshot()`'s CDP parameters** beyond correcting the
  comment that describes them (§8). The camera works; the frame it produces has
  never been measured on a real confirmation page and will not be until §2's
  deploys happen.
- **No new tape.** Nothing here is a string patch on meaning, so nothing needs
  a `TAPE:` comment or a `tape_gate` entry. §14.
- **No rule anywhere that picks between candidate pictures.** §12 is a refusal,
  and the defect in §6 is precisely such a rule that got in by accident.
- **Not a plan.** No tasks, no ordering, no estimates.

---

## 4. (a) Where the screenshot is taken

**At two named moments, and only at those two.**

**`verified-done` — the one this feature exists for.** `agent_loop.js:5370` and
`:5726`. It fires *after* `verifyDone` has re-read the page from scratch and
returned `verified: true`, and after `recordCleanRun`. Not when the step model
announced done — when a second model, given a fresh page map and no step
history to anchor on, agreed. The code comment says it in one line: *"the page
as it stood when the claim was BELIEVED — after verifyDone re-read it, not when
the model announced it."*

Two sites and not one because there are two done exits: the ordinary one at
`:5362-5375`, and the stuck-loop re-audit at `:5721-5733` where a previously
rejected claim is re-verified after the page settled. A single site would leave
the second exit photographing nothing, which is the same class of bug as
`recordCleanRun` being a function rather than two copies.

**`before-commit` — the last frame before something irreversible.**
`agent_loop.js:6074` (the click path) and `:6304` (the Enter path). Taken after
every gate has passed and before the click, so the picture is of the form that
actually goes out, and so a run a gate stopped never leaves a photo suggesting
it did not.

**Where the picture is NOT taken, and why each absence is correct.**

| Not taken | Why |
|---|---|
| At every step | `screenshot()` had exactly one caller before today — the vision step at `:5226`, gated by `needsEyes()` — and the comment at `:118-123` records why: a frame per step is bytes for no extra understanding, and it once killed a run outright on a failed upload. |
| On a `needs_user` hand-back | `takeEvidenceShot` still strips the frame (`background.js:1239`, unconditional), but `depositEvidence` is gated on `canonicalState === "succeeded"` (`:1569`). A parked run has proven nothing. |
| On failure | Same gate. **This is the one that contradicts the Brief** — moment 30 is *"their site died at the payment step — nothing went through (screenshot)"*. §17, item 2. |
| In the supervised-read lane | `runSupervisedReadJob` (`background.js:1330`) returns before the executor and never sets `evidenceShot`. A mail read is not an errand with a confirmation page. |

---

## 5. (b) By which existing function — and why it is not `takeEvidenceShot`

The question as posed names `takeEvidenceShot` as the candidate. **It is not
the capture, and the confusion is worth spending a paragraph on**, because an
implementer who reaches for it will wire the wrong end.

- **`screenshot(tabId)` — `extension/agent_loop.js:112`** is the camera. It is
  the only function in the product that produces an image byte.
- **`captureMilestone(name, tabId, url)` — `agent_loop.js:4143`** is the
  shutter: it calls `screenshot`, keeps the frame, and writes the mark. It is a
  closure over the run, not a module function, because both things it writes
  belong to one errand.
- **`takeEvidenceShot(out)` — `background.js:1239`** is the opposite of a
  capture: it **removes** the frame from the run's result and hands it over
  once. Its whole reason for existing is deletion — a mutation removing the old
  inline `delete out.evidenceShot` turned zero checks red, so the deletion
  became a named function with a suite. Calling it "the capture" inverts it.
- **`depositEvidence(job, shot, deps)` — `background.js:1254`** is the courier.

The chain, in the order it runs:

```
screenshot()            agent_loop.js:112     one JPEG data URL, or null
  <- captureMilestone() agent_loop.js:4143    keeps it, writes the mark
  -> evidenceShot       agent_loop.js:5371    rides out on the run's result
  <- takeEvidenceShot() background.js:1568    takes it, and deletes it
  -> depositEvidence()  background.js:1570    one multipart POST
  -> "evidence:<id>"    background.js:1594    prepended to the receipt
```

---

## 6. The defect: a frame nobody judged, offered as the proof

**This is the only thing in this document that is wrong today, and I did not
find it by reading. I reproduced it by running the shipped loop.**

`captureMilestone` keeps the newest frame that *worked*:

```js
// extension/agent_loop.js:4148-4149
try { got = await screenshot(tabId); } catch (_) { got = null; }
if (got) milestoneShot = got;
```

`if (got)` is a rule — *keep the last frame that came back* — and it is the
difference between a fallback and a substitution. A blank or timed-out capture
at `verified-done` does not leave `milestoneShot` empty; it leaves it holding
the **`before-commit`** frame, which the done exit then offers for deposit as
if it were the picture of the confirmation.

Both halves of that failure are documented as normal in the file itself
(`:113-117`): a hidden background tab may not render, and the capture is
wrapped in an 8-second timeout.

### The probe

I drove the shipped `runAgentGoal` under `extension/tests/chrome_mock.mjs` with
the booking fixture from `test_evidence_capture.mjs`, changing exactly one
thing: the camera answers the first capture and returns a blank frame for the
second.

```
status: done   verified: true
captures attempted: 2
marks: [ 'shot:before-commit@https://fixture.test/book',
         'shot:verified-done(none)@https://fixture.test/book' ]
a frame IS offered for deposit: true
that frame is the BEFORE-COMMIT one: true
```

So the shipped code produces a receipt that says, in its own marks, **"there is
no photo of the moment this was verified"** — beside a photograph it deposited
anyway, of the form before it was submitted. The owner's text reads *"Table
booked"* and carries a picture of an unsubmitted booking form. On the failure
mode this whole design exists to prevent — a page that looked done and was not
— it is the *most* convincing wrong picture available.

Nothing catches it. `test_evidence_capture.mjs`'s blank-camera case is a
research goal with no external effect, so there is no earlier frame to
substitute; the mutation table in `research/2026-08-25-hands3.md:210-220` kills
the captures outright (M6, M7) rather than failing one of two.

### What the repair must be, and what it must not be

**A floor, not a better rule.** Each done exit offers the frame **its own**
`captureMilestone` call returned, or none. `captureMilestone` already returns
`got` (`agent_loop.js:4154`); the done exits read the module-scope
`milestoneShot` instead. That is the entire defect.

The question this feature answers is *"is there a photograph of the page this
claim was believed against?"* — a FLOOR. No verdict means no picture, exactly
as `brain/evidence.py`'s zero-and-more-than-one rule and
`owner_wants_evidence_photos` are floors. A ceiling here ("is this picture
positively wrong?") never lifts, and "keep the last good frame" is what a
ceiling looks like when it is written by accident.

**Explicitly forbidden repairs**, because each one preserves the substitution
while looking like a fix: attaching the newest frame; attaching the largest;
attaching the one whose URL looks like a confirmation; adding a staleness
threshold in seconds. Every one of those is a rule choosing which image is the
proof, which is §12.

**A second, smaller thing the repair should settle:** the mark and the byte
must never disagree. `shot:verified-done(none)` beside a deposited row is a
receipt contradicting itself, and it is the only artifact anybody reading a job
six weeks later will have.

**And it leaves an open question I will not answer here:** if the done exit
only ever offers its own frame, the `before-commit` capture feeds nothing but
its mark. §17, item 1.

---

## 7. (c) What is POSTed to the evidence host, and in what form

`depositEvidence` (`background.js:1254-1291`), one `POST` to
`{backend}/api/collections/evidence/records`, `multipart/form-data`:

| Field | Value | Why |
|---|---|---|
| `owner_ref` | read from `chrome.storage.local` | A **claim**, compared server-side against the credential's own owner (`guard.pb.js:343-345`) and refused when it disagrees. With no `ownerRef` in storage, nothing is deposited at all (`:1266`) — an unowned row is a picture nobody can see and nobody can erase (`1700000045_evidence.js:55-58`). |
| `job` | `job.id` | The row this receipt proves. Indexed (`idx_evidence_job`). |
| `effect_key` | `job.effect_key`, when present | The leash. A picture of one action can never be attached to a text about another — the same binding `workflow_guard.pb.js:666-669` already puts on the receipt. |
| `image` | `Blob([bytes], {type:"image/jpeg"})`, filename `receipt.jpg` | The only byte. |

Three mechanical facts that are easy to get wrong and are already right:

1. **The JSON `Content-Type` is deleted before the send** (`:1277-1278`).
   `writeHeaders()` hardcodes `application/json` for every other call in the
   file; leaving it on makes PocketBase parse a multipart body as JSON and
   reject a valid upload. Pinned by a test.
2. **The agent credential, never the master token.** `X-Anticipy-Agent-ID` /
   `X-Anticipy-Agent-Token`, which is what makes `guard.pb.js:342` able to
   resolve an owner to compare against. Pinned by a test.
3. **PocketBase does the multipart parsing, the size ceiling and the mime
   allowlist**, which is why there is no bespoke upload route. The only thing
   left for the hook to decide is authorisation.

**Why the browser deposits directly rather than handing bytes to the brain.**
`design/LOCAL-FIRST.md` rule 3 — what travels is the smallest conclusion that
works. The bytes exist for a few seconds inside the extension and nowhere else
(`background.js:1206-1208`); routing them through the worker would put a
photograph of a logged-in page in a second process, a second log and a second
error path for no gain. The brain never sees an image; it sees a 15-character
id. **This spec moves no audio and no new class of data off any device — the
picture is of the *browser's* page, on the owner's own machine, and it travels
only because a text message cannot carry bytes.** That is rule 5's "state your
local-first posture explicitly", stated.

**One ordering hazard, verified by reading and not by running.** The deposit
happens at `:1570`, the `updateJob` that writes the receipt at `:1601`. If the
update fails — a 409, a lost lease, a deleted job — the row is stored with
nothing pointing at it, and it consumes one of the twenty slots that owner's
photos get. It is small, it is not a leak (the row is owner-scoped and
default-deny), and it is the price of the receipt being able to name the row.
Named so nobody rediscovers it as a mystery.

---

## 8. (d) What size and format, and why — plus two ceilings that are not the same number

**Format: JPEG, quality 45, one CDP call, with a quality-25 retry above the
ceiling** (`agent_loop.js:123-139`). JPEG because `quality` applies to JPEG
only in the protocol; the collection's mime allowlist accepts jpeg and png and
the depositor refuses anything that is not jpeg (`jpegBytes` returns `null` for
a png data URL, and a test pins that a png is "not silently renamed one").

**Size: whatever the viewport gives, and nobody has measured one.** This is
where four documents in this repo are wrong together.

`agent_loop.js:118` says *"HALF SCALE, modest quality."*
`1700000045_evidence.js:11` repeats it. `research/2026-08-24-evidence-host.md:60`
and `:116` repeat it, and price disk on it ("a quality-45 half-scale JPEG of a
confirmation page is 40–120 KB"). The sibling spec repeats it at `:44` and
`:398`.

**The code does not halve anything.** The call is

```js
{ format: "jpeg", quality: 45, captureBeyondViewport: false,
  clip: undefined, fromSurface: true, optimizeForSpeed: true }
```

and `Page.captureScreenshot` **has no top-level scale parameter** — scale
exists only inside `clip` as `Viewport.scale`, and `clip` is explicitly
`undefined` here ([Chrome DevTools Protocol,
Page.captureScreenshot](https://chromedevtools.github.io/devtools-protocol/tot/Page/)).
`optimizeForSpeed: true` is documented as optimising encoding *for speed, not
for resulting size*, which pushes the other way. So the frame is a
full-viewport capture at the tab's own device pixel ratio, and the 40–120 KB
figure is an estimate of a picture nothing in this product has ever taken.
Not dangerous — the ceilings below are what protect the disk — but the number
should stop being repeated as measured.

**The two ceilings are the same digits in different units.**

| Check | Line | Unit | Effective limit |
|---|---|---|---|
| blank-frame floor | `agent_loop.js:130` `data.length < 4000` | base64 characters | ~3 KB of image |
| capture ceiling | `agent_loop.js:133` `data.length > 400000` | base64 characters | **~300 KB of image** |
| deposit ceiling | `background.js:1224` `bin.length > 400000` | decoded bytes | 400 KB |
| collection ceiling | `1700000045_evidence.js:72` `maxSize: 400000` | bytes | 400 KB |

Base64 is 4/3 of the bytes it encodes, so the first ceiling binds at about
300,000 bytes, not 400,000. Three comments in three files assert these are "the
same number on purpose" so that "a frame that got past the first must not die
silently at the second". **The invariant they describe holds — the browser
ceiling is stricter, so nothing dies at the far door — but not for the reason
stated, and the safety margin is a units bug rather than a design.** (PocketBase
documents the file field's default maximum as "~5MB"
([Files handling](https://pocketbase.io/docs/files-handling/)); that `maxSize`
is expressed in bytes is my own knowledge of the field, not something that page
states.)

The consequence worth writing down is the *repair* direction: an implementer
who "fixes" `agent_loop.js:133` to compare decoded bytes raises the effective
ceiling by a third and lands it exactly on the far door, where an off-by-one
becomes an upload that fails for a reason neither side can see. **Do not raise
`maxSize` past 400000, and do not align the browser check upward.** Align the
comments downward instead.

---

## 9. (e) How the id reaches the receipt as `evidence:<id>`

`depositEvidence` returns the string `evidence:<row id>` (`background.js:1286`),
or `""`. The call site prepends it:

```js
// extension/background.js:1594
evidence: [...(shotRef ? [shotRef] : []), ...(out.receipt?.evidence || [])],
```

**Prepended, not appended, and that is the whole design.**
`workflow_state.js:116-118` keeps the **first** 12 entries after trimming each
to 1000 characters, because duplicating a long result there overflows
PocketBase's text validation and turns a verified success into an HTTP 400.
Every other entry in that array — `url:`, `title:`, `page:<fingerprint>`,
`facts:`, `proof:`, `journal:`, and the new `shot:` marks — is a proof index a
verifier can rebuild from the page. `evidence:<id>` names a row **nothing else
in the product can reconstruct**. Appending it is a silent loss on any run with
a long index, and the existing suite pins both directions.

**The server never inspects an element.** `workflow_guard.pb.js:662-670`
requires a parseable receipt, `verified` truthy, `receipt.effect_key` equal to
the row's `effect_key`, and `Array.isArray(receipt.evidence) &&
receipt.evidence.length > 0`. It counts. So the pointer rides in with no
backend change at all — which is why this half needed no migration and why the
whole feature was ever mistaken for a Twilio problem.

**What reads it back:** `brain/evidence.py:78-101` `ids_in_receipt`, which
splits each entry on the first `:` and collects those whose key is exactly
`evidence`. That is parsing this product's own record format — the same act as
reading `proof:` or `effect_key` — and it interprets nobody's words. Said out
loud because a reviewer scanning for `partition(` will otherwise flag it, and
because the file already says so in its header.

---

## 10. (f) When the capture fails — and the binding constraint the text still arrives

**The rule, unchanged from the sibling spec and not weakened here: a
confirmation that vanishes because a screenshot failed is strictly worse than
today's confirmation with no screenshot.** `brain/worker.py` carries the
recorded incident — the browser had drafted the invoice email, and the only
sentence saying so was composed, refused and recomposed for hours while the
owner was never told. *"Two failures, and the silent one is the worse one."*

Traced end to end, every point where a capture can fail and what it costs:

| Failure | Where it is absorbed | Cost |
|---|---|---|
| CDP throws (debugger detached, tab gone) | `screenshot`'s own `catch` (`agent_loop.js:141`) and again at `captureMilestone` (`:4148`) | none — `null` |
| Capture times out at 8 s | `withTimeout(…, 8000)` (`:123-127`) → `catch` | none |
| Blank frame (hidden tab did not render) | `:130` returns `null` rather than feeding a white rectangle onward | none |
| Frame over the ceiling, and the retry also fails | `:133-139` returns `null` | none |
| Not a jpeg data URL / undecodable / empty / over 400 KB | `jpegBytes` returns `null`; `depositEvidence` returns `""` (`:1261`) | none |
| No `ownerRef` in storage | `:1266` returns `""` | none |
| Backend refuses the upload (403, 400, 5xx) | `:1281-1284` logs *"the errand still stands"*, returns `""` | none |
| Anything throws (offline, DNS, aborted) | `:1287-1289` returns `""` | none |
| Receipt names no evidence | `brain/evidence.py:152-153` returns `[]` | text sends with no media |
| Share door refuses or times out | `open_share_window` returns `""` for every failure, never raises (`brain/evidence.py:104-138`) | text sends with no media |
| Twilio refuses a send that carried media | `voice_arm.py:446-458` — one retry, same words, `MediaUrl` dropped | text arrives without the picture |

**Nothing in that column ever reaches "no text".** And nothing in it gates the
job: `depositEvidence`'s result is a string, the transition is written whatever
it is, and `workflow_guard` decides done on the receipt. A missing photo is a
poorer text, never a stuck job.

**The `catch`-everything at `depositEvidence:1287` is deliberate and must not
be narrowed to named exceptions.** A narrowed catch is a traceback where a
confirmation should be, and the exception list rots the first time Chrome
changes a rejection.

**The one failure that is NOT absorbed** is §6: a `verified-done` capture that
fails does not produce "no picture", it produces the wrong picture. That is
what makes §6 a defect rather than a nicety.

---

## 11. The exposure, said once, in plain words

For this feature to exist at all, **there must be an https URL that answers an
anonymous GET with a photograph of a page the owner was logged into** — their
booking, their address, whatever the confirmation page happened to show. Twilio
does not accept bytes, a `data:` URI, or an authenticated URL: it takes a URL,
fetches it from its own infrastructure with no credential of ours, and attaches
what comes back. Anyone holding that URL, during its window, gets the picture.
No password, no session, no account.

**I am honouring that rather than restating it as solved.** The window is
fifteen minutes and five fetches, opened one record at a time by
`POST /evidence/share` in the moment of sending, and closed by default
(`evidence.pb.js:157-224`); Twilio's copy, the carrier's and the handset's last
forever and nothing here can expire them. The capture side's contribution to
making that small is narrow and worth naming: **one row per errand, only on
success, only 400 KB, only jpeg, only owner-bound, and deposited by a
credential that cannot come back and re-point the share window** — the
collection's `updateRule` and `deleteRule` are `null`, so the browser can
deposit proof of what it did and can never mint itself a permanent public link
to it.

Anyone who reads this spec and does not carry the first sentence of this
section away has read it wrong.

---

## 12. Which picture is the proof — and the floor that is not a tie-break

**Stated as an honouring, not as a discovery: WHICH image is the proof of an
errand is the model's judgement at declare-done, and never a rule.**

The judgement is already made, once, by the model that has the page in front of
it. `verifyDone` re-reads the page and decides "this is the confirmation, this
errand is done"; `captureMilestone("verified-done", …)` photographs *that* page
at *that* instant; `depositEvidence` deposits **exactly one** row. There is no
choice left for anything downstream to make, which is the point — it is not
that the choice is made carefully later, it is that there is no later choice.

The rules this repo would otherwise reach for — the last evidence entry, the
one whose URL matches `/receipt|confirm|booking/`, the largest, the newest —
are patterns deciding what an image *means*. `HARNESS-LAWS.md` Law 1 forbids
them and this repo has torn out sixty-one
(`research/2026-08-24-law1-audit.md`). §6 is one that got in by accident, at
`agent_loop.js:4149`, wearing the clothes of a null check.

**Stated as an honouring: more than one id means NO photo — a floor, not a
tie-break.** Both ends already implement it and neither may be softened:

- `brain/evidence.py:154-162` — more than one `evidence:` id in a receipt logs
  loudly and returns `[]`.
- `brain/evidence.py:172-183` `one_url` and `voice_arm.py:461-490` — more than
  one candidate URL at the wire is also no picture.

The question being asked is *"is there a picture this text is authorised to
carry?"* Without a single unambiguous answer, the answer is no. A tie-break
would work in testing, be wrong on the errand that mattered, and hide the
depositor's bug for months.

**What the capture side owes that floor: never producing the second id.** Today
it cannot — `verificationEvidence` (`agent_loop.js:1743-1763`) builds `url:`,
`title:`, `page:`, `facts:`, `proof:` and `journal:` deterministically from the
page state, `milestoneMarks` are `shot:` entries, and the model's own words are
never copied into the array. The only `evidence:` entry is the one prepended at
`:1594`. **The floor is therefore defence in depth against a future depositor,
not a live tie-break**, and that is exactly the state it should be in. Any
change that lets a model's text reach `receipt.evidence` unfiltered turns the
floor from a backstop into a load-bearing wall.

---

## 13. The gate leg — written so a mock cannot pass it

Three legs, because three different things can be false and one leg that
conflates them is satisfied by the cheapest.

Rules inherited from `overnight/stranger_gate.py`'s own docstring and not
negotiable: **a leg that cannot be tested FAILS**; **a leg that cannot fail is
worse than no leg**; **a leg searches for behaviour, never for a token** — this
gate has already been driven green five times by a comment, including a
`# NOTE: MediaUrl is not wired yet` that retired the MediaUrl leg.

### 13.1 A tree leg: the frame offered is the frame taken at that exit

Reads `extension/agent_loop.js` as a syntax tree, comments stripped. For each
`return` whose object literal has `status: "done"`, assert the value bound to
`evidenceShot` is the result of the `captureMilestone` call **in the same
block**, not a free variable assigned elsewhere. Red when it cannot find the
binding, per the gate's rule.

It must not grep for `milestoneShot`, and it must not merely assert that
`captureMilestone` is called at a done exit — that is true today and §6 is
still true today. **The leg's subject is the data flow, not the call.** Watch it
go red against the current tree and green against the repair, and record that
in `tests/test_stranger_gate.py` the way every other leg here is recorded.

### 13.2 A behaviour leg: run the loop with a camera that fails once

The pattern leg 3 already uses for Swift `e164` — compile and execute the
shipped code rather than reading it. Drive `runAgentGoal` under
`extension/tests/chrome_mock.mjs` with the booking fixture, a camera that
answers the `before-commit` capture and returns a blank frame for
`verified-done`, and assert **nothing is offered for deposit** and the marks
and the byte agree. This is §6's probe, promoted from a scratch file to a leg.

It runs on a mock by construction, and that is fine — it is not the leg the
next section is.

### 13.3 A LIVE leg: a real picture, taken by real hands, fetched by a stranger

Marked `LIVE` in the `LEGS` table beside legs 1 and 9. **Four halves, and the
fourth is the one no mock can produce.**

1. **The deployed hands contain the capture.** Fetch
   `{BASE}/anticipy-claude-version-extension.zip`, parse the packaged
   `agent_loop.js` and `background.js` as syntax trees, and assert the
   `verified-done` capture and the deposit are present *in the served bytes* —
   not by token, by the same structural assertion as 13.1. Today: **RED**, and
   I have the answer already (0.8.4, zero occurrences).
2. **The host answers as itself.** `GET /api/files/evidence/<any>/<any>` must
   return the hook's own body, `{"error":"that evidence is not available"}` —
   not PocketBase's `{"message":"Missing or invalid collection context."}`. One
   string distinguishes "the door is shut" from "the door is not installed",
   and today it is the second. Today: **RED**.
3. **A real row exists, deposited by the hands.** Using the service token, find
   the newest `evidence` row; assert it has an image, assert its `job` names a
   job whose receipt contains `evidence:<that row's id>`, and assert the row's
   `effect_key` equals that job's `effect_key`. **The leg may not create the
   row it checks.** A leg that uploads its own picture and then fetches it
   proves the host and says nothing about the hands; the row must have arrived
   through `guard.pb.js:342-346` on an agent credential.
4. **A stranger can fetch it, and only during the window.** `POST
   /evidence/share` for that row, then fetch the returned URL **with no token,
   no cookie, no session** — the way Twilio's servers would — and assert image
   bytes with an image content-type. Then assert the closed door: a row that
   was never shared 404s at its exact path.

**Why a mock cannot pass half 4.** It is an anonymous HTTPS fetch of a
production URL returning bytes that a real Chrome encoded from a real page and
a real credential deposited. `chrome_mock.mjs`'s `FAKE_JPEG` never leaves the
machine; a stubbed `fetch` cannot make Railway serve anything; `TWILIO_MOCK`
sends nothing and asserts nothing (`voice_arm.py:muzzled` refuses to build a
request at all, so it proves nothing about any payload). The only way this leg
goes green is that the loop ran.

**Constraints on how it is written.** Read `num_media`, `status`, `direction`
and `date_sent` if it reaches for Twilio's records at all — **never `body`**; a
gate that prints the owner's texts into a terminal has created a new leak while
proving an old one closed. (The Twilio half belongs to the sibling spec's §9.3;
this leg should call it rather than duplicate it.) Unreachable backend, missing
token, no evidence rows, a receipt that names none — all **RED**, never
skipped, never green by default.

### 13.4 What green will still not mean

That the picture is of the right page. Nothing in this gate looks at pixels,
and nothing should: that is the judgement §12 gives to the model and to the
person holding the phone. `overnight/done_gate.py` leg 6 — the stranger's week
— is where it is settled, and the leg's own message should say so rather than
leaving it in this document.

---

## 14. Law compliance

- **Law 1.** The one meaning question — *which picture is the proof of this
  errand* — is answered by the browser model at the instant it declares done,
  and by nothing downstream (§12). §6 is a Law 1 violation that got in wearing
  a null check, and §6's repair is a refusal rather than a better rule. The
  pattern-shaped checks in this area are named and defended: `jpegBytes`
  sniffing a data-URL prefix (a format check on a byte string, no words
  involved), `ids_in_receipt` splitting this product's own record format
  (parsing, not interpretation), and the `+1` country-code test at
  `voice_arm.py:487` (transport addressing). None decides what anybody meant.
- **Law 2.** No tape. Nothing here is a string patch on meaning, so nothing
  needs a `TAPE:` comment or a `tape_gate` entry. If an implementer reaches for
  one — a filename pattern to pick a picture, a keyword to decide a page is a
  confirmation, a staleness threshold to decide a frame is "close enough" —
  that is the signal to come back to §12, not to write a `TAPE:` header.
- **Law 3.** §2 is the whole of this law's answer: production serves an
  extension with none of this and a backend that has never heard of the
  evidence collection, verified by me today against the live URL. Every green
  thing in §1 is repo-green. §13.3 is the leg that will say otherwise, and it
  is red for a reason that is not the code.
- **Law 4.** This spec is in `docs/` the day it exists, and it corrects three
  in-tree documents that are now stale (§0, §8).
- **Law 5.** Senses first — this is a capture, and it is the floor of its own
  loop: no context, examples, tier or structure recovers a photograph that was
  never taken. **But it is not the Brief's floor.** `docs/BRIEF.html` §9 lists
  "Capture is the floor" first and means **audio** — ~67% word loss, no VAD, a
  dictation-grade recognizer on ambient speech, `CAPTURE-ARCHITECTURE.md`
  Steps 2–5 unbuilt. A screenshot at a confirmation page is a different organ's
  capture and does not compete with that one for the metronome. Anyone using
  this spec to argue the ears can wait is misreading it.
- **Law 6.** §15 is the adversarial pass. It is not the last one required — the
  defect in §6 survived a 24-check suite, a mutation table and a shipped
  review, and was found by running the code with one parameter changed.

---

## 15. What would kill this

- **Fixing §6 with a better rule.** "Attach the newest frame if it is less than
  N seconds old." It would pass every test, be wrong on the errand that
  mattered, and be defended for months because it is small. §6.
- **Fixing §6 by deleting the `before-commit` capture and calling it done.**
  The substitution is the bug; the second milestone is only its ammunition.
  Removing it hides §6 until somebody adds a third capture site.
- **A lost confirmation.** Any path where a capture, upload, share or media
  failure results in **no text**. §10. This is the one regression strictly
  worse than doing nothing at all.
- **Narrowing `depositEvidence`'s catch** to named exceptions, so that the next
  Chrome change puts a traceback where a confirmation should be. §10.
- **Aligning the browser's ceiling upward** to "match" the collection's,
  raising the effective limit by a third and landing it exactly on the far
  door. §8.
- **Letting model text reach `receipt.evidence`.** The moment an `evidence:`
  entry can be authored by something other than `depositEvidence`, §12's floor
  stops being defence in depth and starts firing on real errands — and a floor
  that fires produces *no photo*, silently, forever.
- **Deploying one half.** The backend without the extension is a host with
  nothing to store; the extension without the backend is a deposit that 404s on
  every errand and logs "the errand still stands" forever. §2.
- **Reading a version number as a deploy check.** The committed zip has been
  byte-stale at a matching version before
  (`research/2026-08-25-hands3.md:254-262`); leg 1 compares bytes for exactly
  that reason, and §13.3 half 1 must too.
- **Believing this document about a picture nobody has taken.** Every size
  figure in §8 is an estimate. The first real capture settles them.

---

## 16. Decisions made without the owner

- **One picture per errand, at `verified-done`**, rather than one per milestone
  — because the host keeps 60 rows across every errand this product ever runs,
  and a second row is indistinguishable from the first at the point anybody
  reads it (`agent_loop.js:4130-4140`). Recorded here as a decision, not a
  constraint.
- **No capture on failure or on a hand-back**, even though the Brief's moment
  30 asks for one. §17, item 2.
- **The deposit happens from the browser, not the brain** (§7), so the bytes
  never enter a second process.
- **The `before-commit` frame is deposited today only by accident** (§6). This
  spec says it should not be, and does not say the milestone should be removed.
- **The gate reads production evidence rows on every run** (§13.3), which is a
  service-token read against live data on a schedule.

---

## 17. Handed back

Each is open, each names who settles it. **An implementer who invents an answer
to any of these is producing the failure this section exists to prevent.**

1. **Once the done exit offers only its own frame, what is `before-commit`
   for?** Its mark is genuinely useful — "there was a form, here is where it
   was" — and its byte then feeds nothing. Options: keep the mark and drop the
   capture; keep both and add a `milestone` column to `evidence` so two rows
   are distinguishable, at the cost the code already prices; keep it in memory
   for a failure path that does not exist yet. **→ whoever holds `extension/`,
   with `backend/` if a column is wanted.**
2. **Should a failed errand carry a photograph?** The Brief's moment 30 says
   yes in the owner's own words — *"their site died at the payment step —
   nothing went through (screenshot)"* — and moment 28 asks for proof of a
   *cancellation*. Today `background.js:1569` deposits only on `succeeded`.
   This is a decision about what may be photographed and texted, not an
   engineering gap. **→ Omar, then `extension/` and `brain/`.**
3. **May a photograph of the owner's screen be sent through Twilio at all?**
   The whole feature rests on it; `owner_wants_evidence_photos`
   (`brain/worker.py:263-297`) is a floor that is off until somebody answers,
   and there is no screen anywhere that asks. **→ Omar, then whoever holds the
   app.**
4. **Should `POST /evidence/share` enforce `effect_key`?** The depositor
   already binds it (`background.js:1272`) and the receipt already carries it,
   but the mint takes an id and opens a window without comparing. The sibling
   spec argues yes. **→ whoever holds `backend/`.**
5. **What does a real confirmation page actually weigh?** Every number in §8 is
   an estimate of a picture nothing has taken. The first live capture settles
   it, and it decides whether the 300 KB effective ceiling ever bites. **→
   first live errand.**
6. **Does a PocketBase file field land on `/pb_data/storage`?** All the disk
   arithmetic assumes it and there is no PocketBase binary in this tree.
   `backend/start.sh:9` prints `df -Pk /pb_data` every boot; the first upload
   settles it. **→ first live deploy.**
7. **Is `e.requestInfo().body` populated for a multipart upload?**
   `guard.pb.js:344` reads `body().owner_ref` to compare against the
   credential's owner. It fails **closed** if wrong, which shows up as the
   extension being unable to deposit at all — a symptom easy to misread as a
   capture bug. **→ first live upload.**
8. **Who deploys, and how is the deploy verified?** Two `railway up`s (§2), and
   `CLAUDE.md` records that `railway up` reports success while failing. Until
   `is_it_live`-style checks say otherwise, nothing in this document is true of
   production. **→ Law 3, every deploy.**
9. **Do the three stale documents get corrected, or annotated?**
   `1700000045_evidence.js:10-12`, `research/2026-08-24-evidence-host.md:57-60`
   and `docs/superpowers/specs/2026-08-25-mouth-photo-receipt.md:42-48` all
   state that the browser never captures at the done page, which stopped being
   true at 02:09 today, and all three repeat "half-scale", which was never
   true. A migration comment is not editable after it has run. **→ whoever
   holds `docs/` and `backend/`.**

---

## Handed back

The capture exists, it is well built, and it has never run. What this spec
adds to the tree is one executed failure and one gate that cannot be satisfied
from a laptop: **§6** — a `verified-done` capture that comes back blank ships
the pre-submit frame as the proof of a completed booking, reproduced under
`chrome_mock` against the shipped loop, caught by nothing — and **§13.3**, the
live leg that stays red until a photograph a real Chrome took of a real page is
fetched anonymously off a production URL. Everything else in here is a
description of code somebody else already wrote well, and a correction to four
documents that describe it wrongly.
