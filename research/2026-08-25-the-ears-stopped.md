# The ears stopped, and it was not the server — 2026-08-25

Investigation into ~30 hours of one-directional silence: phone → server dead,
everything else healthy. Read-only against production plus the tree. Nothing
under `app/ios/**`, `brain/**`, `extension/**` or `docs/**` was modified. The
one thing built is `overnight/are_the_ears_live.py`.

Follow-up to `research/2026-08-25-voice-tests-verified.md`, which localised the
fault to the phone and left the server half unexamined. This examines the server
half, and it clears it.

---

## The one-line answer

**The failure is BUILD-KEYED, not time-keyed. Build 75 delivered 313 rows and
stopped at the exact minute it was replaced. Builds 76, 77, 78, 79 and 80 have
delivered ZERO rows to production — not one transcript, not one profile, not one
app_reply, not one of any kind, ever.**

A server that had changed would have broken build 75 too. Nothing did: b75 was
working right up to its last second. Only a client-side change can produce "this
build always worked, that build has never once worked."

The boundary commit is **`6e277694`** — *"harness fixes 1-5 of 6: exemplars,
compute, mouth guard, shard tape, iOS ears"*, authored **2026-08-23 20:48:35
-0700 = 2026-08-24 03:48:35Z**, which set `CURRENT_PROJECT_VERSION` 75 → 76.

The last line ever heard arrived at **2026-08-24 03:34:24.685Z** — **fourteen
minutes and eleven seconds before that commit was authored.**

---

## The leading hypothesis was wrong, and here is the measurement that kills it

The brief's hypothesis: production runs an uncommitted `railway up` from ~08-17,
so `guard.pb.js` predates something the phone now sends and refuses its POSTs.

**Production is not 08-17 code.** Fingerprinted live, four independent ways:

| probe | result | means |
|---|---|---|
| `POST /me/delete` (no auth) | **401** `{"message":"Sign in first."}` | `account_delete.pb.js` is LIVE — added `cf4b5e3f`, **2026-08-21 21:35** |
| `events.importance` field | **present** | migration `1700000040` ran — `cf4b5e3f`, 08-21 |
| `jobs.watching_until` field | **present** | migration `1700000041` ran — `cf4b5e3f`, 08-21 |
| `purges` collection | **present** | migration `1700000039` ran — `cf4b5e3f`, 08-21 |
| `POST /evidence/share` | **404** | `evidence.pb.js` absent — `0d2ee640`, 08-25 00:25, never deployed |

So the deployed backend is **on or after `cf4b5e3f` (2026-08-21 21:35)** and
**before `0d2ee640` (2026-08-25 00:25)**. The 0.8.4 extension zip is a stale
build artifact carried up in somebody's working tree; it dates the *file*, not
the *deployment*. `research/2026-08-25-voice-tests-verified.md`'s conclusion that
the backend is "roughly eight days stale" and predates 2026-08-22 is **wrong on
the hooks and migrations**, and the correction is owed there.

`/me/delete` returning 401 is safe to probe: `if (!auth) return e.json(401, …)`
is the first statement in the handler (`account_delete.pb.js:80`), before any
table is touched.

### And it could not have been the server anyway

Two further reasons, either of which is sufficient:

1. **The wire shape did not change.** `git diff 54157bba 6e277694 --
   app/ios/Anticipy/Backend/ app/ios/Anticipy/AnticipyApp.swift` is **empty**.
   `pushEvent`, `authorize`, `post` — byte-identical between b75 and b76. b76
   sends exactly what b75 sent, so there is nothing new for a guard to refuse.
2. **Every field the phone sends exists live.** Production's `events` carries
   `device_id, kind, text, decision, goal, capture_started_at, spoken_at,
   capture_ended_at, parent_line, speaker, explicit, source, importance,
   owner_ref` — the complete set `pushEvent` can emit. No unknown-field 400 is
   available.

There is no rejection to reproduce. **The phone is not being refused; it is not
POSTing.**

---

## The evidence, as measured

`device_id` is the build number: `AnticipyApp.swift:236` —
`deviceID: "iphone-b\(Bundle.main.infoDictionary?["CFBundleVersion"] …)"`.

| device_id | rows | newest |
|---|---|---|
| `iphone-b74` | 0 | — |
| **`iphone-b75`** | **313** | **2026-08-24 03:34:24.685Z** |
| `iphone-b76` | **0** | never |
| `iphone-b77` | **0** | never |
| `iphone-b78` | **0** | never |
| `iphone-b79` | **0** | never |
| `iphone-b80` | **0** | never |

Every event row created after `2026-08-24 03:34:25Z`, grouped by device:

    anticipy-brain    5    {'anticipy_says': 5}
    total: 5

Five rows, all written by the server itself. Nothing from any phone under any
device id — so this is not a `device_id` that changed format and slipped a
filter.

**Every kind the phone originates stopped together**, which is why this is not
an ears-only fault:

| kind | last seen | from |
|---|---|---|
| `anticipy_says` | 2026-08-24 16:10:20Z | `anticipy-brain` (server) |
| `transcript` | 2026-08-24 03:34:24Z | `iphone-b75` |
| `profile` | 2026-08-24 01:25:45Z | `iphone-b75` |
| `app_reply` | 2026-08-20 00:43:04Z | `iphone-b65` |

`profile` and `app_reply` have nothing to do with the microphone. They stopped
too. The whole client → server channel is down, not the recogniser.

The final cadence: a dense burst 01:28–01:30, a 2h04m gap, then three rows at
03:34:19, 03:34:21, 03:34:24 — and nothing, ever again. A stop, not a fade.

### A false lead, recorded so nobody re-chases it

`GET /api/collections/owners/records` returns `200` with `totalItems: 0`, and
both owner ids 404. **The accounts are not gone.** `1700000008_owners.js:50`
sets `listRule: "id = @request.auth.id"`; the service token is not an auth
record, so the rule matches nothing. `owner_profile` confirms the accounts exist
(Omar = `3tjzbdptx85mpsp`, which carries 194 of the 200 newest events).

---

## What changed in build 76, and the precedent that makes it the prime suspect

`git diff 54157bba 6e277694 -- app/ios/` is five files:

    project.pbxproj                     44 +-      package linkage
    project.yml                         23 +-      SherpaOnnx package + build 76
    Audio/AnticipyVocabulary.swift      59 +        new
    Audio/LocalTranscriber.swift         3 +        contextualStrings
    Audio/PhoneListener.swift            3 +        contextualStrings

`AnticipyVocabulary` is entirely defensive (`try?` on both the file read and the
decode, a 60-word cap, empty-safe) and cannot crash. `contextualStrings` is two
assignments. Neither touches the network.

The remaining change is the one with teeth. `project.yml` **links sherpa-onnx
into the app target for the first time**, and its own comment says the target's
`packageProductDependencies` had been an *empty list* until then.

**This repo has already proved, by controlled experiment, that this is fatal.**
Commit `9069765a` (2026-08-08), *"Apple's 'bug' was ours: the sherpa-onnx
frameworks were killing every build"*:

    build 47   SherpaOnnxC.framework + onnxruntime.framework   VANISHED (x2)
    build 48   no embedded frameworks, nothing else changed    VALID in 2 min

    One variable. That is the cause.

Builds uploaded cleanly, were accepted, and were then **rejected during Apple's
processing** — a failure mode the commit notes is "invisible except by email",
and "ZERO emails from apple.com have ever arrived in the mailbox we can read."
Its conclusion was explicit: **"SherpaOnnx stays out."**

Build 76 put it back. Build 76 onward has never checked in.

Corroborating: `87c2be2b` (2026-08-24 10:30), *"ExportOptions for TestFlight
uploads"* — the morning after, somebody was reworking the distribution path.

---

## What I could not see, and what settles it in ten seconds

**The device.** I cannot tell which build is installed, whether the app
launches, or whether it is signed in. Three hypotheses survive my evidence, and
all three predict exactly what production shows (zero rows of every kind from
b76+):

- **A — b76+ never installed.** sherpa-onnx makes the upload vanish during
  Apple's processing, as in builds 46/47. The phone still holds b75, which was
  deleted or superseded. Root cause `6e277694`.
- **B — b76+ installed and cannot run.** The newly linked sherpa-onnx binary
  fails at launch. Root cause `6e277694`.
- **C — b76+ installed and never signed in.** `authToken`/`accountID` are
  `@AppStorage` (`AnticipyApp.swift:1096-1097`) — UserDefaults, in the app
  container, discarded by a delete-and-reinstall or a change of distribution
  channel. `isSignedIn` goes false, the window swaps to `AuthView`, and
  `heard()`'s `guard !accountID.isEmpty else { return }` drops every line
  **before both the push and the journal write**, leaving no trace of any kind.
  Root cause is the install, not the commit.

**Whoever holds the phone, in this order:**

1. **The build number the app shows.** If it says **75**, it is hypothesis A —
   the new build never arrived. If **76+**, A is dead.
2. **Does it open to the sign-in screen?** Yes → hypothesis C. Sign in; lines
   should start arriving immediately.
3. **Does it launch at all?** No → hypothesis B.
4. **Settings → Listening → "Find out what listening actually did".**
   - `Words sent` **0 / not rising** → the phone never heard (recogniser, mic,
     permission, listening off).
   - `Words sent` **large** + `Lines that did not reach the server` **rising** →
     heard but refused. *My evidence says this will NOT be what you see*, and if
     it is, the server half needs re-opening — send the raw journal.
   - `Words sent` **large** + failed posts **0** → posts are not being attempted:
     hypothesis C.

The share button on that screen exports the raw journal. It is the one artifact
that separates all four, and it is on the phone.

**Also unverifiable from here:** whether the app is pointed at this backend at
all, and whether Apple sent a processing-rejection email for build 76+ (the
mailbox that would hold it has never been readable — `9069765a`).

---

## Is it fixable from the repo?

**No, and no deploy will fix it.** Production is healthy, is newer than the brief
assumed, and accepted this phone's writes until the moment the build changed. It
needs a **working iOS build installed on the phone** — which, if hypothesis A or
B holds, means reverting the sherpa-onnx linkage from `project.yml` (restoring
`9069765a`'s decision) and shipping a build that installs.

`0d2ee640` and `afd4380a` are genuinely undeployed, and `evidence.pb.js` is
confirmed absent from production — but neither is on this path, and deploying
them would not move a single line.

---

## The liveness leg — `overnight/are_the_ears_live.py`

The instrument printed its own indictment: `is_the_brain_live.py` exits 0 on
exactly this shape, because every rule it has is an **over-speaking** rule. A
monitor that only notices when she says too much cannot see deaf ears.

**How it tells a deaf phone from a legitimately silent night, with no clock
arithmetic at all:**

> A silent night is silent on **both** halves. Deaf ears are silent on **one**.

Nobody speaks at 4am; she answers nobody at 4am either. Both counts sit at zero
together and the leg stays green. There is no quiet-hours calendar, no timezone
and no expected-words-per-hour — the count of **server-originated rows**
(`device_id="anticipy-brain"`) is the control, and it is a control the owner's
sleep cannot move.

Two ways to be red:

1. Zero transcripts over the window while the server wrote **≥ 5** rows of its
   own — the machine provably working while nothing arrives.
2. Silence spanning **more than two full day/night cycles** with the backend
   answering throughout. One quiet day happens to people; two consecutive ones
   is a microphone that is not working.

Rule 2 exists because **running the gate against this very outage exposed the
hole in rule 1**: at hour 30 the trailing day held only three server writes,
because with nothing coming in there was nothing to answer. The control half
evaporates as an outage ages — the same way the old instrument failed, reached
by a different road.

Exit codes: `0` proven alive, `1` EARS DEAF, `2` UNPROVEN (backend unreadable,
or the whole system idle — a leg that cannot be tested does not pass).

**Calibration is derived, not invented.** The floor of 5 separates two
populations the record actually contains, not one somebody imagined:

| day | transcripts | server writes | |
|---|---|---|---|
| 2026-08-03 | **0** | 16 | deaf, **missed** |
| 2026-08-09 | 0 | 1 | nobody using it — correctly NOT red |
| 2026-08-13 | **0** | **63** | deaf, **missed** |
| 2026-08-24→ | **0** | 15 then idle | deaf, missed for 30h |

**This failure has happened at least three times before and was never once
noticed.** 2026-08-13 had sixty-three server writes and not one word heard.

**Law 1.** Every number here is over the **existence and provenance** of rows —
how many, from which device — and never over their content. The file never
requests the `text` column (`fields=` on both counts), so it cannot read a word
of anybody's speech even by accident. It cannot be deciding meaning with a
threshold when it cannot see the words. Law 1 permits thresholds in
deterministic gates; this one decides how much evidence of a live machine makes
a silence one-directional, and nothing about what was said.

Verified: `--self-test` is 10/10 against real production days. Replayed against
the window ending `2026-08-25 03:34:25Z` it returns **exit 1, "NOTHING was
heard, while the server wrote 5 row(s) of its own"** — it would have gone red
**24 hours after the ears died**, the earliest moment a 24-hour window can be
empty, instead of thirty hours later by accident.

It also prints the line that is the whole finding tonight, for one extra
request:

    newest speech of all time   2026-08-24 03:34:24.685Z (30.4h ago) from iphone-b75

---

## Corrections owed to other files

1. `research/2026-08-25-voice-tests-verified.md` — its Law 3 section concludes
   production "was built before 2026-08-22" and is "roughly eight days stale" on
   `pb_hooks`/`pb_migrations`. Measured false: `/me/delete` (401), `purges`,
   `events.importance` and `jobs.watching_until` are all live, so the deploy is
   on or after `cf4b5e3f`, 2026-08-21 21:35. The served extension version dates
   the zip, not the deployment. Its narrower point stands: the deploy is from a
   working tree nobody can name, and `0d2ee640`/`afd4380a` are undeployed.
2. `overnight/is_it_live.py` — still has no iOS leg, and this incident is the
   second demonstration that it needs one. The cheapest version is not a build
   of anything: production already knows the newest `device_id` that ever wrote
   a row, and the tree knows `CURRENT_PROJECT_VERSION`. "The phone last seen was
   b75; this tree is b80" is one request and would have named this in a second.
