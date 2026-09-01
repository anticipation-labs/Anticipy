# Founder identity reset — 2026-08-31

## Requested outcome

The founder asked to remove the consumer-account association for one supplied
phone number and three possible email addresses, then reinstall from TestFlight
and enter onboarding as a new person. The browser agent and shipped iOS build
also had to be checked against their live authorities rather than inferred from
the repository.

## Version proof

- `jose_anticipy_system` was fetched before the operation. Local HEAD and
  `origin/jose_anticipy_system` were both `446260ef`.
- Railway serves extension `0.11.1`, and the served ZIP is byte-for-byte the
  committed artifact. The first run of `overnight/is_it_live.py` nevertheless
  produced a false Chrome pass because its installed-copy leg compared only
  `agent_loop.js`. Both folders Chrome had recorded contained that current
  file while still carrying a `0.11.0` manifest, a stale `background.js`, and
  no current `setup_bridge.js`. Both on-disk folders were synchronized to the
  complete `0.11.1` package. The gate now compares every packaged file in
  every recorded Anticipy folder and has a regression test reproducing the
  partial-match failure. A direct check of `chrome://extensions` then showed
  that the active Default profile has no Anticipy card at all: the two paths
  in Secure Preferences are removed-extension tombstones, not live installs.
  The gate and sync script now require a real stored manifest and refuse to
  call a tombstone loaded. The old `0.5.1` text in one leftover folder name is
  not its extension version.
- App Store Connect now reports iOS `1.1.0 (115)` as `VALID`, unexpired, and
  `IN_BETA_TESTING`. It contains the audio-route crash fix, the Mac recorder,
  browser/Mac onboarding, extension `0.11.1` compatibility, and the anchored
  listening-indicator repair from `a8a3c128`.
- The automatic TestFlight upload is no longer blocked. Eleven unusable
  `DEVELOPMENT / Created via API` records left by ephemeral GitHub runners were
  revoked; no named development, distribution, or Developer ID certificate was
  touched. The serialized release workflow now cleans only those exact CI
  leftovers and chooses its build number from App Store Connect's live history.

## Recovery point and process failure

Before erasure, PocketBase created
`pre_identity_reset_20260901t041213z.zip` in the private production backup
bucket. It was downloaded through the restricted backup credential and checked
independently:

- 63,911,395 bytes
- SHA-256
  `0cf9991ee8bf9ed734d944a5305de2ce932aca8474818bae6efad07310b81a20`
- ZIP CRC: OK
- extracted `data.db` `PRAGMA quick_check`: OK
- owner count: 9

During the first erasure attempt, a temporary PocketBase superuser was written
with a second PocketBase CLI process while the production server still had the
same SQLite database open. The account route then reported `database disk image
is malformed` while deleting the auth record. The operation stopped rather
than accepting a partial deletion. The verified recovery point above was
restored through PocketBase's native restore API, the service returned healthy,
and owner discovery again showed all nine pre-reset accounts.

All later one-off superuser operations paused PID 1 before opening the database,
resumed it, and restarted the service before API work. Never run a second
PocketBase writer against the live database concurrently.

## Erasure performed

Two auth accounts were attached to the supplied phone. Both were closed through
`POST /me/delete`, so the normal privacy path cleared account-scoped rows and
scheduled the worker-volume purge.

| Scope | Removed |
| --- | ---: |
| Account A events / jobs / segments / agents / profile | 954 / 33 / 67 / 1 / 1 |
| Account B events / jobs / segments / agents / profile | 14 / 14 / 5 / 0 / 1 |
| Unowned pre-account events containing a supplied identifier | 81 |
| Remaining rows for the unowned founder legacy UUID | 8 jobs, 16 segments, 1 agent, 1 profile |
| Internal founder-directory phone links cleared | 1 |

The worker completed both purge rows. Both account state directories are gone,
and the configured founder memory file was removed. Four surviving clock-state
files had inherited the founder number in `welcomed_phones`; that value was
removed atomically, and the worker was restarted from the cleaned state.

`ANTICIPY_OWNER_PHONE` was deleted from both Railway services. The founder phone
was also removed from local operational/test destinations in `.env.local`; the
test fixture now uses a reserved `+1 555` number. The services were restarted
after the environment change.

## Final proof

- Full production scan: zero occurrences of the supplied phone.
- Consumer identity tables: zero records matching the supplied phone or the
  three supplied email addresses.
- Owners: 7 total, zero selector matches; the removed phone and supplied emails
  are available for a genuinely new signup.
- Worker volume: zero occurrences of the supplied phone or three emails across
  every JSON and SQLite file; both removed-account directories are absent.
- Both purge rows report `memory_purged=true`.
- A disposable post-reset native backup passed ZIP CRC and SQLite
  `PRAGMA quick_check`, with 7 owners, then was deleted. The next scheduled
  clean production backup is at 09:00 UTC. The pre-reset recovery point remains
  under the normal fourteen-generation private-backup retention policy.
- All temporary `codex-*` superusers used for the operation were removed while
  the server was paused.
- Backend health, the live download, and the served/source package byte gates
  passed last. The Chrome leg is correctly red: there is presently no enabled
  Anticipy install in the active Chrome profile. Installing one fresh unpacked
  copy from `extension/` is the remaining browser step; browser-extension
  installation requires action-time user confirmation.

The supplied work emails still appear in the separate `internal_people`,
`fellows`, and `fellow_applications` business records. Those are not Anticipy
consumer accounts and do not reserve an app login; deleting them would erase
unrelated company/fellowship records, so they were deliberately left in place.
Five browser-test jobs owned by a separate test account mention a different old
Gmail spelling; they likewise do not own the founder phone or reserve any of the
three requested login addresses.

## Phone ceremony

To exercise the new-user path, delete Anticipy from the iPhone rather than
updating it in place, then install build 115 from TestFlight. Credentials,
onboarding state and the pre-account UUID are stored in the app's UserDefaults,
so removing the app is the step that clears the phone-side copy. The server-side
accounts and durable memory are already gone.

Chrome's Default profile has two removed Anticipy preference records but no
installed Anticipy card. The two old folders were synchronized defensively, yet
Chrome does not run either one. Load `extension/` once with **Load unpacked**;
that creates one new `0.11.1` card with a fresh extension identity and empty
local pairing storage, avoiding both the dead credential and duplicate-agent
state. Enter its new six-digit pairing code in the freshly installed iPhone
app.
