# MOUTH — the done-text carries the picture, or says nothing about one

> Status: SPEC. Not a plan, not a sequence, no code, no task list.
> Card: WIRE IT ALL step 1 — "verify loop end-to-end (act → evidence →
> done-text with photo)" (`docs/BOARD-STATE-2026-08-24.md:52-53`). MOUTH's
> "DONE = EVIDENCE" is the same rung.
> The red leg: `overnight/stranger_gate.py:leg_8_done_text_can_carry_the_photo`.
> Survey this checks rather than inherits: `research/2026-08-24-evidence-host.md`.
> Laws that bind: `HARNESS-LAWS.md` 1, 2, 3, 4, 6. `design/LOCAL-FIRST.md`
> rule 3 decides §3.6.
>
> **The host is built and the leg is still red for a reason that is not the
> host.** `backend/pb_hooks/evidence.pb.js` and
> `backend/pb_migrations/1700000045_evidence.js` shipped on 2026-08-24/25: a
> place for the byte, an anonymous fetch door that is closed by default, and a
> service-token mint that opens it for minutes. What is missing is at both
> ends. Nothing in `extension/` ever takes the picture at the moment that
> matters, and nothing in `brain/` carries it — and the carry is five function
> signatures long, not one. An implementer who widens
> `brain/voice_arm.py:text` alone turns leg 8 green and ships a product where
> no photo ever attaches, because the production done-text does not go through
> that function directly. §7 is that trap, and it is the largest thing in this
> document.

---

## 1. What leg 8 says, checked against the code

Every row read this session at the file, not inherited from the survey.

| The leg says | The code says | Verdict |
|---|---|---|
| "`text()` posts From, To and Body and nothing else" | `brain/voice_arm.py:text` posts `data={"From": self.from_number, "To": to, "Body": body}` and nothing else. | **True.** |
| "`MediaUrl` appears in no .py, .js or .swift" | Only in `overnight/stranger_gate.py` (`MEDIA_KEY`) and `tests/test_stranger_gate.py`. Zero hits in shipped code. | **True.** |
| "the browser captures evidence" | It captures *strings*. `extension/agent_loop.js:verificationEvidence` builds `url:`, `title:`, `page:<fingerprint>`, `facts:`, `proof:`, `journal:` — an audit index, not a picture. `extension/workflow_state.js:110-130` truncates each to 1000 chars, at most 12. | **True but not what a reader assumes.** There is no image anywhere in a receipt today. |
| "`workflow_guard.pb.js` refuses `done` without it" | `backend/pb_hooks/workflow_guard.pb.js:227-231` — parseable receipt, `verified` truthy, `effect_key` equal to the row's, `Array.isArray(evidence) && length > 0`. It never inspects an element. | **True, and load-bearing:** an `evidence:<id>` entry can be added to that array without touching the guard. |
| "as URLs in `receipt.evidence`" | The `url:` entries are pages the *browser* stood on, reachable only with that browser's session. Handing one to Twilio would fetch a login wall or a 404. | **The leg's own wording is misleading.** They are not URLs anything else can fetch. §3. |
| "Nothing carries them onward" | True, and understated. See §7. | **True.** |

**Two things the leg does not say, which change the work.**

**The picture is not taken.** `extension/agent_loop.js:screenshot` (`:105-143`)
is called at exactly one site, `:5003`, and only when `needsEyes()` says the
page is a calendar, seat map or slider. It is a half-scale quality-45 JPEG
capped at 400 KB (`:129`), handed to one model call and dropped. **There is no
capture at the verified-done page.** Until `extension/` takes one, everything
in this spec has nothing to attach. That is the prerequisite, it lives in a
tree this spec does not touch, and it is named again in §12.

**The recipient is the owner, not a third party.** The done-text is composed at
`brain/worker.py:1573-1585` and delivered by
`brain/anticipy_core.py:notify_owner`, which sends to `self.owner_phone` and to
nothing else. The "stranger" of the stranger gate is the *new account holder*,
not somebody the errand was performed against. **No third party's phone
receives an evidence photo on any path in this design.** That narrows the
exposure in §3 honestly, and it is not the same as removing it.

---

## 2. Non-goals

- **No implementation.** This spec is written to be executed by somebody else.
- **No change to `extension/`'s capture.** It is a prerequisite (§12), not
  scope. Whoever holds that tree decides how the picture is taken.
- **No decision that the owner wants photos sent at all.** The host was
  deliberately built switched off (`research/2026-08-24-evidence-host.md` §3)
  and this spec keeps it a mechanism, not a policy. §3.6.
- **No object-storage migration.** R2 is priced and declined in §3.2, not
  because it is wrong but because it is a different card.
- **No new tape.** Nothing here is a string patch, so nothing here needs a
  `TAPE:` comment or a `tape_gate` entry. If an implementer finds themselves
  wanting one, §10 says what to do instead.
- **No rule that reads a URL, a filename or a page title to decide which
  picture is the right one.** §4 is the whole answer to that, and it is a
  refusal.
- **Not a plan.** No tasks, no ordering, no estimates.

---

## 3. (a) Where the image is hosted, and what that exposes

### 3.1 The host exists. I checked rather than assumed.

Present in the working tree, read this session:

- `backend/pb_migrations/1700000045_evidence.js` — an `evidence` collection
  with `owner_ref` (required), `job` (required), `effect_key`, `image`
  (`type: "file"`, `maxSelect: 1`, `maxSize: 400000`, `mimeTypes:
  ["image/jpeg", "image/png"]`), `share_expires`, `fetches`. `listRule`,
  `viewRule` and `createRule` are `""`; `updateRule` and `deleteRule` are
  `null` (superuser only). The migration reads itself back and throws if the
  file field or the null rules did not land.
- `backend/pb_hooks/evidence.pb.js` — the fetch door (`routerUse` over
  `/api/files/`), the mint (`routerAdd("POST", "/evidence/share")`), and a
  retention sweep (`onRecordAfterCreateSuccess`, `KEEP_PER_OWNER = 20`,
  `KEEP_TOTAL = 60`).
- `backend/pb_hooks/guard.pb.js:342-343` lets the browser credential POST one
  evidence record bound to its own owner; `:416` lets the signed-in owner list
  and view their own rows so the app can find them.
- `backend/pb_hooks/account_delete.pb.js:75-77` erases evidence rows on account
  deletion, with a comment saying out loud that the sweep is a disk defence and
  not a privacy control.

The bytes land under `--dir`, which `backend/start.sh:15` sets to `/pb_data` —
the attached Railway volume. **Unverified and on the LIVE list:** that a
PocketBase file field actually writes to `/pb_data/storage`. There is no
PocketBase binary in this tree. `backend/start.sh:9` prints `df -Pk /pb_data`
every boot; the first upload settles it.

### 3.2 R2 exists as a credential and does not exist as a host

`.env.local` carries `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`, `R2_BUCKET`, `R2_PUBLIC_URL`, verified
live with a hand-signed SigV4 `ListObjectsV2`. **Three facts stop it from being
the answer tonight, and none of them is "R2 is bad".**

1. **Its public door is not known to work.** The file's own audit note: "the
   `pub-*.r2.dev` URL returns 403 for that object, so public access is off or
   the object is private — do not assume that link works for a download page
   without checking." A `MediaUrl` that 403s fails the *whole message*, so
   shipping onto an unverified public door trades a missing photo for a missing
   text. That is the wrong direction (§5).
2. **It is the Mac-DMG bucket.** Putting a screenshot of somebody's booking in
   the same bucket as a public installer is one misconfigured bucket policy
   away from a permanent public link, and bucket policy is not in this repo.
3. **Nothing in the tree can talk to it.** Zero `boto3`/`botocore` imports
   anywhere; no requirements file at the repo root. Using R2 from `brain/`
   means a new dependency or a hand-rolled SigV4 signer, for one screenshot per
   completed errand.

R2 remains the correct long-term answer for the reason
`1700000037_backup_footprint.js` already gives about backups, and it is a
separate card. **The `evidence` collection is the host this spec builds on.**

### 3.3 The exposure, in plain words

Twilio does not accept bytes, a `data:` URI, or an authenticated URL. It takes
a URL, fetches it from its own infrastructure with no credential of ours, and
attaches what comes back. **So for the feature to exist at all, there must be
an https URL that answers an anonymous GET with a photograph of a page the
owner was logged into** — their booking, their address, the last four of their
card, whatever the confirmation page happened to show. Anyone holding that URL,
during its window, gets the picture. No password, no session, no account.

Anyone who reads this spec and does not carry that sentence away has read it
wrong.

### 3.4 What makes it small

- **Default deny.** `share_expires` empty means **no public URL exists**. A row
  nobody deliberately shared is unreachable to somebody holding the exact path.
  The normal state of an evidence photo is "not on the internet".
- **Unguessable, but nothing rests on that.** PocketBase's 15-character record
  id plus the 10 random characters appended to every stored filename.
  Unguessability is a delay, not a lock, and `evidence.pb.js` treats it as one.
- **Fifteen minutes.** `SHARE_WINDOW_MS = 15 * 60 * 1000`, opened one record at
  a time by `POST /evidence/share`, service token only, in the moment the
  worker is about to send. Twilio fetches within seconds.
- **Five fetches.** `SHARE_FETCH_LIMIT = 5`, because expiry alone leaves a
  leaked URL an unlimited download until it lapses. Retries are covered; a
  scraper is not. A fetch that cannot be *counted* is refused rather than
  served.
- **One shape of refusal.** Every public denial is the same `404` with the same
  body, so an anonymous caller cannot tell "no such row" from "never shared"
  from "expired" from "spent" and walk record ids with the difference.
- **Every other collection is refused outright** at the same door, so a later
  migration that adds a file field cannot inherit an anonymous public URL by
  accident.

### 3.5 How long it lives, and who can delete it

Three separate clocks, and they are worth keeping apart.

| The thing | How long | Who can end it |
|---|---|---|
| The **public window** | 15 minutes, or 5 fetches, whichever first | Nobody has to act; it closes itself. A superuser can clear `share_expires`. |
| The **stored row and its byte** | Until the sweep evicts it — `KEEP_PER_OWNER = 20` newest per owner, `KEEP_TOTAL = 60` overall, run on every create | The sweep, account deletion (`account_delete.pb.js:77`), or a superuser. `updateRule`/`deleteRule` are `null`, so **no API caller can delete one — including the owner whose screenshot it is.** |
| **Twilio's copy, the carrier's, and the handset's** | Forever, as far as this product is concerned | **Nobody.** Shortening our window does not shorten theirs. |

Two of those rows are uncomfortable and both are true. The owner cannot erase
their own picture without deleting their account or asking a human, and the
copy that actually persists is the one on the phone, which is also the copy the
feature exists to deliver. **The decision to send a picture at all is therefore
the owner's**, and §3.6 keeps it that way.

### 3.6 The switch, and why it is a switch

`design/LOCAL-FIRST.md` rule 3 — "what travels is the smallest conclusion that
works" — does not obviously permit a full-page capture, and this backend's own
posture on image bytes elsewhere is to redact and hash them
(`agent_key.pb.js:70-90` replaces every screenshot passing through the model
proxy with `[IMAGE_BYTES_REDACTED]` plus a sha256). The host was deliberately
shipped closed for that reason.

**This spec does not decide the law question, and it must not smuggle an answer
in by shipping the feature switched on.** The implementer adds one account-level
setting — a boolean on the owner, off by default, whose name says what it does
("send a photo of the confirmation with the done text"). When it is off,
everything below still runs and simply never asks for a share window; the text
goes exactly as it does today. When nobody has answered, it is off, because
this is a FLOOR — *does anything authorise attaching this picture?* — and a
floor that lifts itself is not a floor (`HARNESS-LAWS.md` Law 1).

Not a rule reading anybody's words. A stored answer to a question the owner was
asked.

---

## 4. (b) Which picture, and whose judgement picks it

### 4.1 The rule this repo would otherwise ship, and why it is illegal

"Attach the last entry in `receipt.evidence`." "Attach the one whose URL
matches `/receipt|confirm|booking/`." "Attach the largest." Each of these is a
pattern deciding **which image is the proof of what happened** — a judgement
about meaning, made by a string check, exactly the shape `_READ_ONLY_RE` had
when it decided a timezone conversion was consequential. `HARNESS-LAWS.md`
Law 1 forbids it, and the repo has torn out sixty-one of them
(`research/2026-08-24-law1-audit.md`).

### 4.2 There is no choice at send time, because the choice was already made

**The browser model picks the picture, at the moment it declares the effect
verified-done, with the page in front of it.**

That is not a new decision and it is not a new model call. The same model, in
the same call, on the same page, is already deciding "this is the confirmation,
this errand is done" — which is what `extension/workflow_state.js:110-130`
refuses to write a receipt without, and what
`backend/pb_hooks/workflow_guard.pb.js:227-231` refuses to accept a `done`
without. The picture is a photograph of the page that judgement was made about.
Taking it at that instant and depositing **exactly one row** makes "which
picture" a question nobody downstream has to ask.

The receipt then carries the answer by id — one more entry in the array it
already carries, in the same `key:value` shape as the entries beside it:

```
evidence:<pocketbase record id>
```

`workflow_guard` needs no change; it counts the array, it does not inspect it.

### 4.3 What the sender is allowed to do with that, and what it is not

The brain reads `jobs.receipt`, parses it, and looks for an entry whose key is
`evidence`. **That is parsing this product's own record format, not
interpreting anybody's words** — the same act as reading `proof:` or
`effect_key`, and it is Law 1's "senses" category. It is worth saying so
explicitly here, because a reviewer scanning for `startswith(` will otherwise
flag it, and because an implementer who is unsure will invent something worse.

Then, exactly three outcomes, and the sender never picks:

- **Exactly one `evidence:` id** → resolve it (§5), attach it if it resolves.
- **Zero** → send the text with no media. Not an error. §5.
- **More than one** → **send the text with no media, and log loudly enough that
  somebody finds it.** More than one is a defect in the depositor, not a menu
  for the sender. This is a floor: *is there a picture this text is authorised
  to carry?* Without a single unambiguous answer, the answer is no. A sender
  that broke the tie by rule would be the Law-1 violation this section exists
  to prevent, and it would hide the depositor bug forever.

### 4.4 One structural check that is legal and should be there

Before a window is opened, the evidence row's `effect_key` must equal the
receipt's `effect_key`, so a picture of one action can never be attached to a
text about another. That is checking what a record **is bound to**, not what
anything **means** — the seatbelt's own territory, and the same leash
`workflow_guard` already puts on the receipt.

`POST /evidence/share` does not check it today: it takes an id and mints a
window. Adding the check belongs in `backend/` and is named in §12.

---

## 5. (c) No picture, a failed upload, a rejected media — the text still arrives

**The rule, and nothing in an implementation may weaken it: a confirmation that
vanishes because a screenshot failed is strictly worse than today's
confirmation with no screenshot.** Today the stranger gets a sentence. The
floor is that they still get the sentence.

This is not rhetorical. `brain/worker.py` carries a comment about the day the
opposite happened: the browser had drafted the invoice email, and the only
sentence that said so was composed, refused and recomposed for hours while the
owner was never told his errand was finished. "Two failures, and the silent one
is the worse one."

### 5.1 The order of operations

1. **Compose the text.** Unchanged (`brain/worker.py:1573-1585`).
2. **Resolve the media, best effort, bounded.** Parse the receipt; if there is
   exactly one `evidence:` id and the owner's setting is on, `POST
   /evidence/share` with the service token. One attempt, short timeout, and
   **every failure returns "no media"** — a non-200, a timeout, a connection
   error, an unparseable body, an `ok: false`.
3. **Send.** With `MediaUrl` if step 2 produced one, without it otherwise.
4. **On a non-ok response to a send that carried media: retry once, without
   the media.** Then stop.
5. **Record.** Delivery is recorded from the send that actually succeeded.

### 5.2 `POST /evidence/share` already never errors for an absent picture

`backend/pb_hooks/evidence.pb.js` returns `200 {ok: false, reason, url: "",
expires: ""}` for every absence — no such record, no image on the record, no id
named, no https base configured. The caller's contract, from the host's own
research note:

```
r = post("/evidence/share", {"id": evidence_id})
media = [r["url"]] if r.get("ok") else []       # and the text still goes
```

The brain must honour the same shape for the failures the host cannot see for
it — a timeout, a 5xx, a socket error. **Never raise out of media resolution.**

### 5.3 The retry, and why it is not a list of error codes

Twilio has media-specific error codes (an unfetchable `MediaUrl`, an unsupported
content type, too many attachments) and the obvious design is to retry
without media on those codes. **Do not enumerate them.** A code list rots the
day Twilio adds one, and the failure mode when it rots is a lost confirmation.

The simpler rule is also the safer one: **if a send that carried media comes
back not-ok, retry once without the media.** A not-ok response means Twilio
queued nothing, so the retry cannot double-text. If the real problem was the
number or the account rather than the picture, the retry fails too and surfaces
the real reason — one extra HTTP call, bounded, once.

**The one thing that must not be retried** is a response Twilio *accepted*.
`brain/voice_arm.py:_result` raises `SendFailed` both for a non-ok HTTP status
*and* for a 201 whose body carries a dead status or an `error_code`. Only the
first case is safe to resend. An implementer who retries on `SendFailed`
generally will double-text the owner on a 201 with `error_code` set. Retry on
the response, not on the exception.

### 5.4 The picture is never a precondition for `done`

Nothing about upload, share or media may gate marking a job complete. The job
is done when `workflow_guard` says the receipt is good. A missing photo is a
poorer text, never a stuck job.

---

## 6. (d) Cost and limits — and what a UK number gets

### 6.1 Foreign strangers are in scope, because the gate says they are

`overnight/stranger_gate.py` leg 3 compiles and executes the shipped
`app/ios/Anticipy/AnticipyApp.swift:e164` and it **passes**: a bare 10-digit
local number is now refused rather than silently made American, and `+44…` /
`0044…` normalise to `+442079460958`. So a London stranger reaches production
with a real UK number in `owner_phone`, and the done-text goes to it.

### 6.2 What Twilio does with media to a UK number, honestly

Twilio documents MMS as US/Canada only on standard long codes. **What happens
to a message carrying `MediaUrl` addressed to +44 is one of three things — the
whole message rejected, the media silently dropped and the SMS delivered, or
the media replaced by a link — and I could not determine which from this
machine.** No Twilio account is attached to this checkout and I did not send a
message to find out.

**The design makes the unknown irrelevant, which is the right response to an
unknown that costs a person their confirmation.** Media is attached only when
the destination is a `+1` number. Every other destination gets the plain text,
today's behaviour, with no experiment run on somebody's live week. If the
measurement later shows a benign degrade, the restriction can be relaxed with
evidence; the reverse — discovering the failure mode by losing a London
stranger's confirmations for a week — is not recoverable.

**Is a `+1` prefix test a Law-1 violation?** No. It reads a *number's* country
code, which is transport addressing — the "senses" category, and the same kind
of check `e164` itself is. It decides nothing about what anybody meant.

### 6.3 The sending number

`.env.local` records `TWILIO_PHONE_NUMBER=+16196584447` with the audit note
"Account 200; +16196584447 confirmed owned by this account with
**sms+mms+voice**". Area code 619 is San Diego. **This corrects
`research/2026-08-24-evidence-host.md` §6.5, which says "the `From` number is
Canadian".** MMS capability on the sending number is the one prerequisite that
is already verified, and it is verified from the wrong document.

### 6.4 What it costs

MMS is priced per message and is several times an SMS in the US; the exact
figure depends on the account and is not in this repo. At one picture per
completed errand the bill is not the constraint.

**Disk is the constraint that already took the product down.** The 5 GB Railway
volume filled on 2026-08-15 and PocketBase could not open its database
(`audit_retention.pb.js:3-11`). PocketBase zips `pb_data` — storage included —
into `/pb_data/backups` on the same volume and keeps two
(`1700000037_backup_footprint.js`), so peak footprint is three copies of every
stored byte. At the field's 400 KB ceiling and `KEEP_TOTAL = 60` that is 24 MB
live, ~72 MB at peak; realistically a quality-45 half-scale JPEG is 40–120 KB,
so ~5 MB live. Sized to be unable to take the product down by itself. **Do not
raise `maxSize` past 400000** — it matches `extension/agent_loop.js:129`
exactly, so a capture that succeeded in Chrome never fails at the door for a
reason neither side can see.

### 6.5 Trial accounts

On a Twilio trial account every unverified destination fails silently. The
stranger gate names this in its own "what this gate cannot see" section. It is
not this feature's bug and it will look exactly like this feature's bug.

---

## 7. The carry is five signatures, and four of them are not in the leg

**This is the largest correction in the document.** Leg 8 reads
`brain/voice_arm.py:text` and asks whether its POST payload can carry
`MediaUrl`. Satisfying that is one line. It would also ship nothing, because
**the done-text does not reach `text()` directly on the path production
runs.**

Traced this session:

```
brain/worker.py:1585            anticipy.notify_owner(said)
brain/anticipy_core.py:2862       -> self.conversation.reach_out(owner_phone, message)   # PREFERRED
brain/conversation.py:348            -> self.say(phone, body)
brain/conversation.py:330               -> self.transport.send(phone, body)
brain/conversation.py:232                  -> TwilioTransport.send -> self.voice.text(to, body)

brain/anticipy_core.py:2873       -> self.voice.text(owner_phone, message)               # only when
                                                                                         # there is no
                                                                                         # Conversation
```

`brain/worker.py:3238` constructs `Conversation(anticipy, transport=
TwilioTransport(voice) if voice else MockTransport())` unconditionally. **So
the conversational branch is the branch that runs, and the direct
`voice.text` call at `anticipy_core.py:2873` is a fallback the worker does not
take.** A `media=` argument added to `text()` and to `notify_owner`'s direct
call would leave the shipped path unchanged, leg 8 green, and no photo ever
sent.

Every hop must carry it, defaulting to none:

- `brain/voice_arm.py:text` — `media` → `MediaUrl` in the form post.
- `brain/conversation.py:TwilioTransport.send` — the transport contract widens.
- `brain/conversation.py:MockTransport.send` — same signature, or the mock rig
  raises `TypeError` the first time a photo is sent and the failure looks like
  a Twilio problem.
- `brain/conversation.py:Conversation.say` — and note that `say` **dedupes on
  body text alone** (`:311-322`): the same sentence inside 600 seconds returns
  `{"deduped": True}` without sending. A second attempt that differs only by
  having a picture is deduped away. That is probably correct and it must be a
  decision somebody makes, not a surprise.
- `brain/anticipy_core.py:notify_owner` — both branches, or the one that
  matters is the one that misses.

**Leg 8 must be re-pointed to follow this chain** (§9.2), or it certifies a
parameter nobody passes. A leg that cannot fail is worse than no leg —
`overnight/stranger_gate.py`'s own docstring, and the reason four legs in this
repo were caught passing by matching nothing on 2026-08-24.

---

## 8. (e) How it is tested without sending a real MMS

### 8.1 What `TWILIO_MOCK` actually does — it is a muzzle, not a recorder

Established by reading, not assumed. `brain/voice_arm.py:muzzled` returns true
for `"1" | "true" | "yes" | "on"`, and it is read in exactly two places:
`has_credentials` (the worker's live/mock decision) and `_rig_reason` (the send
guard, **first, ahead of every exemption**). A muzzled process **refuses to
send at all** — `_guard` raises `SendFailed` and no HTTP request is built.

Therefore **`TWILIO_MOCK` proves nothing whatsoever about the payload.** It
cannot tell you whether `MediaUrl` was set, spelled correctly, or pointed
anywhere. It is a safety switch and this feature must not be tested with it.
(Its own history is worth knowing: for months nothing in the tree read it, so
anyone setting it to stop a process from texting got real texts and a false
sense of safety. Pinned now by
`tests/test_twilio_auth_and_delivery.py:295-311`.)

### 8.2 What does prove the payload: the loopback recorder

`proof/twilio_outbound_proof.py` stands up a `ThreadingHTTPServer` on
`127.0.0.1` that impersonates Twilio's REST API, points the real
`brain.voice_arm.VoiceArm` at it via `TWILIO_API_BASE`, sets
`TWILIO_ACCOUNT_SID` to Twilio's TEST account SID, sets `TWILIO_MOCK=false`,
and asserts the request the arm actually built — path, `Authorization` header,
content type, and every form parameter. Nothing leaves the machine.

It works precisely *because* `TWILIO_MOCK` is off:
`brain/voice_arm.py:_cannot_reach_a_phone` recognises a loopback
`TWILIO_API_BASE` and exempts it from the rig refusal, which is how the
outbound path is proved correct without a send.

**Extend this file.** The new checks it should carry:

- a send with media POSTs `MediaUrl` with the exact URL given, alongside
  `From`/`To`/`Body`;
- a send without media posts **no** `MediaUrl` key at all — not an empty one;
- a `+44` destination posts no `MediaUrl` even when a URL was resolved (§6.2);
- a first send that comes back 400 is followed by **exactly one** retry, and
  that retry carries no `MediaUrl` and the same `Body`;
- a 201 carrying an `error_code` is followed by **no** retry (§5.3).

### 8.3 The assertion that will go red, and must not be deleted

`proof/twilio_outbound_proof.py` asserts today:

```python
check("no extra parameters were smuggled in",
      set(sent["params"]) == {"From", "To", "Body"}, str(set(sent["params"])))
```

**This goes red the moment `MediaUrl` is wired, and deleting it is the wrong
repair.** It is the only thing standing between this codebase and a future
where an unnoticed parameter rides along on every outbound message. Widen it
deliberately: exact `{"From", "To", "Body"}` for a plain send, exact
`{"From", "To", "Body", "MediaUrl"}` for a media send. Two checks, both exact,
so "no extra parameters" keeps meaning something.

### 8.4 The share door, tested against a real PocketBase

Everything about the fetch door is currently asserted from documentation and a
node harness with a fake app, not from a running PocketBase
(`research/2026-08-24-evidence-host.md` §6). The behaviours that need a real
server, in order of what breaks worst if wrong:

1. an anonymous GET of a shared URL returns image bytes with an image
   content-type;
2. an anonymous GET of an **unshared** row's exact path returns 404;
3. the sixth fetch inside the window returns 404;
4. a fetch after 15 minutes returns 404;
5. re-sharing resets `fetches` to 0;
6. `e.requestInfo().body` is populated for a multipart upload — the branch
   binding `owner_ref` to the agent's own owner reads it, and it fails *closed*
   if wrong, which shows as the extension unable to deposit at all.

---

## 9. (f) The gate leg, written so a mock cannot pass it

Three legs, because three different things can be false and one leg that
conflates them will be satisfied by the cheapest of them.

### 9.1 Leg 8 stays as it is

`_post_payload` / `_carries_media` read the syntax tree and follow calls into
payload builders. That is the right shape and it should not be softened. It
proves the parameter can be posted.

### 9.2 A new tree leg: the media survives the whole chain

Reads `brain/` as a syntax tree, the way leg 8 already does, and follows the
done-text from `brain/worker.py`'s send site to the Twilio POST, asserting that
a media argument is threaded at **every** hop in §7 and is actually passed at
each call site, not merely accepted in each signature.

It must **not** grep for the word "media". A leg that matched a token would go
green on a comment saying media is not wired — the exact defect that retired
this gate's own quiet-hours and MediaUrl legs once already
(`overnight/stranger_gate.py` docstring).

Red when it cannot find the chain, per the gate's rule: a leg that cannot be
tested fails.

### 9.3 A new LIVE leg: Twilio's own records are the witness

Marked `LIVE` in the `LEGS` table alongside legs 1 and 9, and it is the one
that cannot pass on a mock, in two halves.

**Half one — the anonymous fetch, against production.** Using
`ANTICIPY_BACKEND_URL` (`overnight/stranger_gate.py:103`) and the service
token: `POST /evidence/share` for a named evidence row, then fetch the returned
URL **with no token, no cookie and no session** — the way Twilio's servers
would — and assert image bytes and an image content-type come back. Then assert
the closed door: the same path on a row that was never shared returns 404. A
mock cannot satisfy this because it is an anonymous HTTP fetch of a live URL;
an unreachable backend is RED, not skipped, exactly as leg 1 is.

**Half two — the message Twilio says it sent.** A read-only `GET` of the
account's Messages resource with the real Twilio credentials, asserting that
the most recent outbound message to the owner's number carries `num_media >=
1`. **This is the half a mock cannot fake**, because the record is written by
Twilio, not by us: it exists only if a real message with real media was really
accepted. A loopback recorder, a `TWILIO_MOCK` process and a stubbed HTTP layer
all produce nothing here.

Three constraints on how it is written:

- **Read `num_media`, `status`, `direction` and `date_sent` — never `body`.**
  A gate that prints the owner's texts into a terminal and a log has created a
  new leak while proving an old one closed.
- **Accepted is not delivered.** `brain/voice_arm.py:_result` already separates
  them and this leg must too: say which one it proved, in the leg's own message.
  `queued` is the honest answer to "did Twilio take it" and a dishonest answer
  to "did they get it".
- **No credentials, no network, no matching message → RED.** Not skipped, not
  green by default. The gate's first rule.

### 9.4 What green still will not mean

That an image reached a handset and rendered. Only a person looking at a phone
settles that, and `overnight/done_gate.py` leg 6 — the stranger's week — is
where it is settled. The leg's message should say so rather than leaving it
here.

---

## 10. Law compliance

- **Law 1.** The one meaning question — *which picture is the proof of this
  errand* — is answered by the browser model at the moment it declares done,
  and by nothing downstream (§4). Zero, and more-than-one, both mean no photo;
  the sender never breaks a tie. The two pattern-shaped checks in this design
  are named and defended: reading an `evidence:` key out of this product's own
  receipt format (parsing, not interpretation) and reading a destination's
  country code (transport addressing). Neither decides what anyone meant.
- **Law 2.** No tape. Nothing here is a string patch on meaning, so nothing
  needs a `TAPE:` comment or a `tape_gate` registry entry. If an implementer
  reaches for one — a filename pattern to pick a picture, a keyword to decide
  a page is a confirmation — that is the signal to come back to §4, not to
  write a `TAPE:` header.
- **Law 3.** Repo-green is not done. §9.3 is the live leg, and §8.4 lists six
  behaviours currently asserted from documentation rather than from a running
  PocketBase. The picture has not reached a phone and nothing may claim it has
  until it does.
- **Law 4.** This spec is in `docs/` the day it exists.
- **Law 5.** Senses (the capture) come before everything: §1 says the picture
  is not taken at the done page, and no amount of plumbing fixes that. Context
  next (the receipt carries the id). No new rule is written anywhere in the fix
  order's fifth position.
- **Law 6.** §11 is the adversarial pass. It is not the last one required.

---

## 11. What would kill this

- **One-line green.** Widening `voice_arm.text` alone, watching leg 8 go green,
  and shipping a product where the conversational path — the only path the
  worker takes — never carries a photo. §7 and §9.2 exist for this and it is
  the most likely single failure.
- **A picking rule.** "The last evidence entry", "the one that looks like a
  receipt". §4. It would work in testing, be wrong on the errand that mattered,
  and be defended for months because it is small.
- **A lost confirmation.** Any code path where a share failure, an upload
  failure or a Twilio media rejection results in **no text**. §5. This is the
  one regression that is strictly worse than doing nothing at all.
- **The deleted assertion.** `proof/twilio_outbound_proof.py`'s "no extra
  parameters were smuggled in" going red and being removed instead of widened.
  §8.3.
- **A double-text.** Retrying on `SendFailed` rather than on a not-ok response,
  and resending a message Twilio already accepted. §5.3. This product has a
  recorded incident of the same sentence going out repeatedly.
- **A `+44` experiment on a live week.** §6.2.
- **Trusting `TWILIO_MOCK` as a test harness.** It sends nothing and asserts
  nothing; a suite built on it is green and blind. §8.1.
- **A public URL that outlives its window.** Anything that sets `share_expires`
  speculatively, in advance, or in bulk. The mint is per message, in the moment,
  or the whole design in §3.4 is decoration.
- **Raising `maxSize`.** §6.4.

---

## 12. Decisions made without the owner

- **The `evidence` collection is the host; R2 is declined for now** (§3.2),
  because R2's public door is unverified and a `MediaUrl` that 403s costs the
  whole message.
- **The feature ships behind an owner setting that defaults to OFF** (§3.6).
  This is a refusal to decide the LOCAL-FIRST question on the owner's behalf.
- **No media to any non-`+1` destination** until somebody measures what Twilio
  actually does (§6.2), even though that means a London stranger gets exactly
  today's behaviour.
- **More than one candidate picture means no picture** (§4.3), rather than a
  tie-break of any kind.
- **One retry, on a not-ok response, without media** (§5.3), rather than a
  Twilio error-code list.
- **The gate leg reads Twilio's message records** (§9.3), which is a read
  against a live third-party account on every gate run.

---

## 13. Handed back

Each is open, each names who settles it. **An implementer who invents an answer
to any of these is producing the failure this section exists to prevent.**

1. **May a photograph of the owner's screen be sent through Twilio at all?**
   The whole feature rests on it and it is not an engineering question.
   `research/2026-08-24-evidence-host.md` §3 left it open; this spec leaves it
   open and ships it off by default. **→ Omar.**

2. **Should the owner be able to delete their own evidence photo?** Today they
   cannot: `updateRule`/`deleteRule` are `null`, so erasure is the sweep,
   account deletion, or a superuser (§3.5). **→ Omar, then whoever holds
   `backend/`.**

3. **What does Twilio actually do with `MediaUrl` to a `+44` number?** Reject
   the message, drop the media, or substitute a link. Nobody in this repo
   knows. It needs one deliberate send from the real account to a real foreign
   handset. Until then §6.2 stands. **→ whoever has the Twilio console and a
   foreign test number.**

4. **What does an MMS cost on this account, and what is the monthly ceiling
   anybody is comfortable with?** Not in the repo. **→ Omar.**

5. **Does a PocketBase file field actually land on `/pb_data/storage`?** All of
   §6.4's disk arithmetic assumes it, and there is no PocketBase binary in this
   tree. `backend/start.sh:9` prints `df -Pk /pb_data` every boot; the first
   upload settles it. **→ first live deploy.**

6. **Is `e.requestInfo().body` populated for a multipart upload?** The guard
   branch binding `owner_ref` to the agent's own owner reads it. It fails
   closed if wrong, which shows as the extension unable to deposit at all.
   **→ first live upload.**

7. **When and how does `extension/` take the picture?** There is no capture at
   the verified-done page (§1), and this spec does not touch that tree.
   Everything here has nothing to attach until it exists. **→ whoever holds
   `extension/` — HANDS 3 territory.**

8. **Should `POST /evidence/share` enforce `effect_key`?** §4.4 argues yes and
   the code does not do it. **→ whoever holds `backend/`.**

9. **Does `Conversation.say`'s 600-second body dedupe suppress a retry that
   differs only by its picture?** Reading `brain/conversation.py:311-322` says
   it does. Whether that is correct is a judgement nobody has made. **→ whoever
   holds `brain/`.**

10. **Is the sending number's MMS capability still true?** `.env.local` records
    `sms+mms+voice` on `+16196584447` (US, area code 619). This contradicts
    `research/2026-08-24-evidence-host.md` §6.5's claim that the number is
    Canadian, and one of the two documents is stale. Re-check against the
    Twilio console before anybody debugs a missing photo. **→ whoever runs the
    gate first.**

11. **Is the deployed brain this brain?** Prod has served stale code twice.
    Nothing above is true of production until an `is_it_live`-style check says
    the deployed worker is the one carrying this code. **→ Law 3, every
    deploy.**
