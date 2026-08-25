# MOUTH — the done-text carries the picture: what was built, and what is not proven

> Built against `docs/superpowers/specs/2026-08-25-mouth-photo-receipt.md`
> (commit `03e727ea`). Closes the tree half of stranger-gate leg 8.
> Commits: `04387066` (the chain), and this file.
> Branch `jose_anticipy_system`.

## 1. The trap, and how it was avoided

Leg 8 reads `brain/voice_arm.py:text` and asks whether the POST payload can
carry Twilio's `MediaUrl`. **That question can be answered in one line while
shipping nothing.** `brain/worker.py` builds a `Conversation`
unconditionally, so the path production actually runs is

    worker -> Anticipy.notify_owner -> Conversation.reach_out
           -> Conversation.say -> TwilioTransport.send -> VoiceArm.text

and the direct `self.voice.text(...)` inside `notify_owner` is a fallback the
worker never takes. Widening `text()` alone turns the leg green and leaves a
product where no photo is ever attached.

All five hops carry it. Two tests hold that, and they hold it differently on
purpose:

* `test_every_hop_between_the_worker_and_twilio_can_carry_a_picture` reads
  `brain/` as a **syntax tree** — each hop must ACCEPT the parameter and PASS
  one on, and the value handed to `notify_owner` is FOLLOWED to the call that
  produced it. A comment saying the chain is wired is not a node in a tree.
* `test_the_shipped_chain_puts_the_picture_on_the_wire` **drives** the five
  hops with a real `Conversation`, a real `TwilioTransport`, a real `VoiceArm`
  and a recorded `requests.post`, and asserts `MediaUrl` on the wire.

Breaking any one hop was measured: each of the four `media=` hand-offs was
deleted in place, and both tests went red every time (§5).

## 2. What was built

| File | What it does |
|---|---|
| `brain/evidence.py` (new) | Reads `evidence:<id>` out of the job's own receipt; opens a share window for exactly one picture; returns `[]` for everything else and **never raises**. |
| `brain/voice_arm.py` | `text(to, body, media=None)`. One post site, one retry, the `+1` restriction, the single-URL floor. |
| `brain/conversation.py` | `MockTransport.send`, `TwilioTransport.send`, `Conversation.say`, `Conversation.reach_out` all carry it. |
| `brain/anticipy_core.py` | `notify_owner(message, channel, media=None)` — **both** branches. |
| `brain/worker.py` | The done-text site resolves the picture in the moment of sending; `owner_wants_evidence_photos()` reads the owner's stored answer. |
| `proof/twilio_outbound_proof.py` | The smuggling assertion WIDENED, plus the media, foreign-number, retry and non-retry proofs over real HTTP. |
| `tests/test_done_text_carries_the_photo.py` (new) | 33 tests. |

Suite: **1824 passing**, 0 failing (`tests/test_day_zero_oracle.py` does not
collect — `playwright` is not installed; pre-existing and not mine).
`proof/twilio_outbound_proof.py` exits 0 with 10 recorded requests, 0 sent.
Leg 8: **RED -> GREEN**, with delivery green.

## 3. The decisions, and the laws they answer to

**Law 1 — nobody downstream picks the picture.** The browser model answers
"which image is the proof of this errand" at the moment it declares the effect
verified-done, depositing exactly one row named in the receipt as
`evidence:<id>`. `brain/evidence.py` reads that key out of **our own record
format** — the same act as reading `proof:` or `effect_key`, which the spec
calls out as the "senses" category — and then:

* exactly one id -> share it;
* zero -> no picture, not an error;
* **more than one -> no picture, said loudly.** A floor, not a tie-break.
  "The last one" or a URL pattern would be a rule deciding what an image
  MEANS, and it would hide the depositor's bug forever.

The same floor is enforced again at the wire (`one_url`), so it reads the same
way at both ends.

The `+1` test reads a **number's country code** — transport addressing, the
same kind of check `e164` itself is. It decides nothing about what anyone
meant.

**Law 2 — no tape.** Nothing here is a string patch on meaning, so nothing
here carries a `TAPE:` comment or a `tape_gate` entry.

**Law 3 — repo-green is not done.** §4 is the whole list.

**Law 6 — the adversarial pass.** §5. Two of my own tests were found unable to
fail and were repaired before this was written.

**The words are the floor.** No evidence, an owner who never said yes, a share
door that 500s or times out or answers `ok: false`, a body that is not JSON, a
Twilio media rejection — every one of them still sends the sentence. This was
also the shape of a regression I introduced and fixed mid-build: passing
`media=` unconditionally into `notify_owner` raised `TypeError` inside its own
`except`, which reads as "he was not told", and **silenced every SMS-lane
answer** for one run. Caught by `tests/test_research_worker.py` and
`tests/test_backlog_and_delivery.py`, not by anything I wrote. Every hop now
passes the keyword only when there is a picture, because transports and arms
that predate it are still in the tree (`proof/smoke_worker.py`, the in-app
suppressing transport, a dozen `def text(self, to, body)` doubles in `tests/`).

**One retry, on the response, never on the exception.** Not-ok means Twilio
queued nothing, so re-sending the same words without the picture cannot
double-text. A 201 carrying an `error_code` is a message Twilio **accepted**;
`_result` raises for it and it never reaches the retry. No list of media error
codes: a code list rots the day Twilio adds one, and the failure mode when it
rots is a lost confirmation.

**One post site.** The retry reuses the same `requests.post` through a
two-iteration loop rather than adding a second credential-bearing send.
`tests/test_twilio_auth_and_delivery.py::test_the_arm_never_authenticates_a_send_with_a_hardcoded_pair`
pins this file at two authenticated sends (Messages.json, Calls.json) so that
every send goes through one reviewed path; three would have been a second path
nobody read. The expected count was **not** edited. (A first attempt at this
failed the same test for a funny reason worth recording: my explanatory
comment contained the literal `auth=self.auth`, and the test counts
occurrences in the source text. A comment defeating a test is the exact defect
this repo keeps finding; the comment was reworded, not the test.)

**`Conversation.say` still dedupes on body text alone** (spec §13 question 9,
handed to whoever holds `brain/`; settled here). A second attempt that differs
only by having a picture is deduped away within 600 seconds. That is the right
way round: the owner reading the same sentence twice is a worse day than the
owner reading it once without a photo, and his own app serves his evidence
rows to his signed-in session with no public window at all.

**The owner setting defaults OFF and is a stored answer, not a rule.**
`owner_wants_evidence_photos()` reads `photo_with_done_text` off the owner's
profile row, then off the account. An absent column, an unreachable backend
and a profile row that does not exist yet are all **off**, deliberately: the
question is "does anything authorise attaching this picture", and a floor that
lifts itself is not a floor.

## 4. NOT PROVEN — what is true of tests and not of the world

Every line of this is repo-green only. **Nothing below has run against
production, and it cannot from here.**

1. **No picture exists to attach, on any account, today.** `extension/` takes
   no capture at the verified-done page (spec §1); `screenshot()` fires only
   for calendars, seat maps and sliders and is dropped after one model call.
   Until HANDS ships that capture, no receipt carries `evidence:<id>` and this
   entire chain resolves to `[]` on every real job. **The plumbing is live and
   the payload does not exist yet.** -> whoever holds `extension/`.
2. **The owner's switch has no column and no screen.** `photo_with_done_text`
   is read and is absent, so the answer is always no. Live behaviour today is
   therefore byte-for-byte today's behaviour. -> `backend/` for the migration,
   `app/ios/` for the question. Both outside my lane.
3. **`POST /evidence/share` still does not check `effect_key`** (spec §4.4),
   so a picture of one action could in principle be shared for a text about
   another. The brain does not compensate with an extra fetch. -> `backend/`.
4. **Nothing has been measured against a running PocketBase.** All six
   behaviours in spec §8.4 — anonymous fetch of a shared URL, 404 on an
   unshared one, the sixth fetch, the expired window, re-share resetting
   `fetches`, and `e.requestInfo().body` on a multipart upload — are still
   asserted from documentation and a node harness with a fake app. There is no
   PocketBase binary in this tree.
5. **No MMS has ever been sent by this code.** `TWILIO_MOCK` cannot prove a
   payload — it refuses to send at all, so it asserts nothing. The loopback
   recorder proves the request we BUILD; only Twilio's own Messages resource
   (`num_media >= 1`) proves one was accepted, and that leg is not written
   (§6).
6. **What Twilio does with `MediaUrl` to a `+44` number is still unknown** —
   reject the message, drop the media, or substitute a link. We refuse to
   attach rather than find out on a stranger's live week. Relax only with a
   measurement. -> whoever has the console and a foreign test number.
7. **The sending number's MMS capability is asserted by a stale document.**
   `.env.local` says `sms+mms+voice` on `+16196584447` (US, area code 619);
   `research/2026-08-24-evidence-host.md` §6.5 says the From number is
   Canadian. One of the two is wrong. Re-check before anybody debugs a missing
   photo.
8. **The ears have been dead ~30 hours** (zero transcript rows in 24h,
   verified twice against live) and **production is running code that was
   never committed.** Prod has served stale code twice. Nothing above is true
   of production until a deploy and an `is_it_live`-style check say the
   deployed worker is this worker.
9. **Green here does not mean an image rendered on a handset.** Only a person
   looking at a phone settles that — `overnight/done_gate.py` leg 6, the
   stranger's week.

## 5. The adversarial pass (Law 6)

Every new test was watched going red against a mutated tree and green against
the real one. Mutation, targeted test, restore — twelve of them:

| Mutation | Caught by |
|---|---|
| drop `media` at `reach_out -> say` | both chain tests |
| drop `media` at `notify_owner -> reach_out` | both chain tests |
| drop `media` at `say -> transport` | both chain tests |
| drop `media` at `TwilioTransport -> text` | both chain tests |
| worker hands `notify_owner` a literal `[]` | the worker chain test |
| `one_url` takes the first of many | the two-pictures floor |
| remove the `+1` restriction | the foreign-number test |
| never retry a refused media send | the retry test |
| retry a send that carried no picture | the non-retry test |
| retry a message Twilio ACCEPTED | the double-text test |
| ignore the owner's stored answer | the switch test |
| share a picture nobody named | the no-window test |

**Two tests were found unable to fail and were repaired.** Both had the same
cause and it is worth writing down: the doubles that were supposed to prove
"no share window was opened" *raised* to signal the call, and
`open_share_window` swallows every exception on purpose — so the raise was
swallowed, the result was `[]` either way, and the test passed no matter what
the code did. They now use a door that WOULD hand back a URL and assert the
call list is empty. Separately, the two share-door failure tests were passing
off `picture_for_done_text`'s outer net rather than the handler under test, so
they now exercise `open_share_window` directly as well. A leg that cannot fail
is worse than no leg, and that rule applies to tests.

## 6. Handed on

* **The §9.2 gate leg was NOT added.** The spec asks for a new tree leg in
  `overnight/stranger_gate.py` that follows the media through all five hops,
  so leg 8 cannot certify a parameter nobody passes. `overnight/` is outside
  my lane and is being edited concurrently tonight; a lost edit there is worse
  than a missing leg. **The equivalent lives in
  `tests/test_done_text_carries_the_photo.py` as the two chain tests**, and it
  is the same reading (syntax tree, calls followed, never a token match).
  Whoever owns the gate should lift it across.
* **The §9.3 LIVE leg was not written** for the same reason: it reads
  production and Twilio's Messages resource. It must read `num_media`,
  `status`, `direction` and `date_sent` and **never `body`** — a gate that
  prints the owner's texts into a terminal has created a new leak while
  proving an old one closed.
* Spec §13's open questions 1, 2, 3, 4, 5, 6, 7, 8 and 11 remain open and
  unanswered. Question 9 (the dedupe) is settled above; question 10 (the
  sending number) is §4.7.
