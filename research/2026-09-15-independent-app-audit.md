# Independent app audit — 15 September 2026

## Outcome and scope

Baseline: `cloudflare-backend` at `6de6527d160a175f431ecb82f9aef4250c6b0fff`.
Local candidate: build **178**, on `codex/audit-app-20260915`. It is not a
TestFlight, production API, extension, or Mac distribution release.

**Later evidence: Mac candidate crash remains unresolved.** A crash report from
16:26:53 local time identifies Mac build 178, `EXC_BAD_ACCESS`/`SIGSEGV`, on
the main thread during a SwiftUI button gesture through `MainActor.assumeIsolated`.
The process was no longer running when checked after the owner's report. This
does not identify the root cause, and these local repairs are not a crash fix.
The earlier candidate build reused its initial build directory; subsequent
builds used a separate directory. Clean-launch reproduction and inspection of
the loaded binary identities are required before attributing the failure.

The app compiles and its offline suites pass, but the evidence does not establish
that the complete pendant-to-result product works for a new customer. The
pendant audio path is disconnected, the speaker engine is deliberately unlinked,
and a live customer journey remains unproven. Local passing tests do not waive
those gates.

Five organization repositories and 38 remote branch trees were inventoried.
The checked-out trees contain 1,080 documentation candidates, including archived
notes, vendor files and tables. This is an inventory, **not 1,080 verified
documents**. Current app architecture, testing, release, readiness, native-app
guides and the recent changes were checked against source and executable
evidence. Selected Drive documents were compared with that evidence. Notion
could not be read because its connector requires reauthentication; the live
internal document workspace also requires an authenticated session.

Raw local logs, download hashes, inventories, claim ledger and the preserved
original checkout delta are held in the separate dated audit directory. Private
cloud-document contents and CI logs are not copied into this repository.

## Git and Tejas's changes

The held checkout was at `a1724fcc`, with two modified iOS files and three
untracked research notes. After fetching all advertised heads it is 35 commits
behind `origin/cloudflare-backend`. Its files were preserved; this candidate was
made in a separate worktree. The original modifications add pendant maintenance
commands and status UI. They do not provide an Opus decoder or pendant
transcription, and are not included in this candidate.

GitHub's default `main` is a different lineage: at this snapshot there are 479
commits unique to `main` and 1,120 unique to `cloudflare-backend`. The release
workflow and current README select `cloudflare-backend` for the app. A default
branch checkout is not an equivalent app baseline.

The latest history attributed to Tejas includes:

| Change | Verified scope |
| --- | --- |
| `6de6527d`, PR 68 | Deployment evidence, changelog, root documentation cleanup. Moving/removing current files does not erase reachable history. |
| `2a3fdf17`, PR 66 | Architecture, testing, release, security and license documentation. |
| `0c22445a`, PR 67 | Browser identity/release/re-pair repair, brain non-response handling and truthful connect-code sending; extension 0.18.3, iOS 177. |
| PRs 65, 64, 63 | Readiness board, D1 CLI transport, account-safe connector/browser harness integration. |
| PRs 62, 61, 59 | Mac window/library, PocketBase retirement in the app backend, Mac capture work. |

Commit attribution is repository metadata, not an independent account of who
personally performed every test described in a commit message.

## Reproduced defects and local repairs

### 1. Mac edits could appear saved after the disk write failed

`MeetingStore.save` updated the visible record before attempting an atomic write,
and discarded write errors. The notes pane always said “Saved on this Mac”.
Changing selection or restarting could therefore lose an edit presented as saved.
The Trash path also removed a meeting from the visible list after a failed
filesystem operation.

The regression uses a real temporary `MeetingArchive` and the production
`MeetingStore`. A directory at `owner.json` forces a write failure; moving a
temporary meeting folder forces a Trash failure. The original implementation
failed three assertions. A second pass caught URL aliases for the same folder
creating separate pending drafts; two more regression assertions failed before
normalizing keys by filesystem path. The repaired store passes all twelve:

- Only a successful atomic write updates the saved record.
- Failed title/notes edits stay in memory across selection/reload and can be retried.
- A pending edit shows “Not saved yet” and a visible Retry action.
- Failed Trash operations retain the row and report failure.

The in-app and Markdown guides explain this behavior. The retained draft is
**memory-only if the filesystem cannot write**. The user must keep the app open
and retry; crash recovery for an unwritable disk is not claimed. Corrupt or
unreadable pre-existing sidecars still need separate recovery work.

Code: `app/macos/AnticipyMac/MeetingStore.swift`, `MainWindow.swift`.
Regression: `app/macos/Tests/MeetingStoreTests.swift`, included in `run_all.sh`.

### 2. Mac onboarding blocked access to the library until recording permissions

The permission page had no way to continue without granting both recording
permissions. The candidate adds **Set up later**, taking the user into the app.
Recording retains its existing permission gate. The full Mac suite and the final
candidate build pass. The candidate's new UI was not launched over the owner's
active recording, so a hands-on check of that new control remains open.

### 3. iPhone onboarding promised pendant audio that the app discards

The running build 177 said the pendant hears the room as the phone does.
`AnticipySession.startPendantTranscription` sets `onOpusFrame = nil` and
`pendantCapturing = false`; this target has no linked pendant Opus decoder.
Bluetooth pairing is not evidence of usable pendant speech.

Build 178 explains that pairing is available but pendant listening is not yet
supported, and points to the iPhone microphone. The offer, Bluetooth explanation
and closing copy were corrected. The existing onboarding assertions were updated
to require truthful capability copy, failed against the old text, and passed
after the change. The rebuilt candidate was installed and its corrected offer
was verified in the simulator's running UI.

Code: `app/ios/Anticipy/PendantOnboardingPolicy.swift`.
The remaining implementation work is local Opus decode, audio continuity,
supported on-device transcription and a physical-device end-to-end test.

## Verification performed

| Check | Result | Practical limit |
| --- | --- | --- |
| Python `pytest -q --tb=short` | 4,084 passed, 3 skipped, one warning | Outbound network denied; not a live-model test. |
| API Worker tests and typecheck | Passed | Local contracts and test stores. |
| Brain Worker tests and typecheck | Passed | Not proof of a running production brain answering a customer. |
| Extension offline suite | All 91 suites passed | Mock/runtime checks, not a real customer browser session. |
| Installed extension in real Chrome 152 | Eight verdict rows passed | Real local Worker/D1 and Chrome, scripted model and fixture website. Two additional rows are launch metadata, not tests. |
| iOS logic suite | Passed | Initial nested Preview-macro sandbox failure was resolved with a compiler wrapper; the outer network-denial sandbox remained active. |
| iOS candidate pendant suite | Passed after failing against old copy | Copy/routing contract, not physical BLE audio. |
| Mac suite, including new store regression | Passed | Final source typechecks and shell/guide checks pass. |
| iOS and Mac Debug builds | Baseline and final candidates built | Local unsigned builds, not distribution acceptance. |
| Firmware host suite | Passed | Not an embedded firmware build, flash, or hardware test. |
| Extension package check | Passed | Source/package consistency. |

The real-Chrome rig covered fresh registration, pairing, a two-hop fixture task,
restart, outage recovery, owner separation, phone-shaped release/re-pair, and
legacy release/re-pair. Every executed fixture task clicked the expected target
once. A scripted provider's “independent-model-audit” receipt text is not
independent evidence of model intelligence; the observable site effect and
identity assertions are the useful proof here.

The iPhone was also walked manually in an isolated iOS 26.5 simulator: offline
sign-in error; successful sign-in against the local Worker; in-app-only alerts;
skipped computer, pendant and connector setup; declined microphone access;
Home; and a typed message with no brain response. The UI correctly showed
listening off and “Nothing back on it yet”. No real SMS, email, purchase or
customer task was sent. Simulator speech and BLE behavior do not establish
physical iPhone performance.

The owner confirmed that the active Mac recording was theirs and asked that it
remain running. No subsequent stop was requested by the audit. The later crash
ended that app process; recording continuity must be checked. Its silent-input
display was not treated as proof of a microphone defect without a known
audible control.

## Live artifact checks and documentation corrections

At approximately 19:57 UTC on 15 September:

- `GET https://api.anticipy.ai/api/health` returned 200 and revision
  `2a3fdf1702a7492321355a27fa7b1f97243c19ac`. This is API liveness/revision evidence,
  not end-to-end service acceptance.
- All three public extension aliases returned version 0.18.3, SHA-256
  `a6a8259d95b5d352a9354795210921e7835e151ac83a888e209b4b5cf0652f07`.
- The public Mac ZIP reported version 1.1.1, build 171, SHA-256
  `c27dd01e3257e2d8df99e2f5ff1a80f943b53eab01a5d9ab8431bed8186e1cbb`.
  Its universal binary passed strict code-signature verification, Gatekeeper's
  notarized Developer ID assessment and stapler validation. It was inspected,
  not launched. A signed distribution baseline exists; this does not show that
  the latest local candidate has been signed or shipped.
- CI logs corroborate API deployment, a brain fleet deployment and a VALID
  processing result for iOS 177. The audience-access workflow is red; those logs
  do not establish a successful install and day-long journey for a new tester.

Corrections to apply when reading other documents:

| Source | Correction |
| --- | --- |
| September 13 readiness board, Mac distribution | A signed/notarized/stapled build 171 exists. Distinguish that verified baseline from exact-source acceptance for a new release. |
| Readiness board, installed-client rig “10/10” | The run has eight verdict rows and two metadata rows. All eight passed locally; it is not a ten-scenario live customer proof. |
| iOS README, nothing to keep in Keychain | Absence of vendor keys does not remove the account token. `AnticipySession.authToken` is in `AppStorage`/UserDefaults. The README is corrected; migration is not implemented. |
| `.agents/skills/testing-anticipy/SKILL.md` | Its PocketBase startup path, local Desktop path and old suite counts are historical. Use `docs/TESTING.md` and the current Worker rig. |
| Website README, pendant-system PocketBase backend | The app backend is now the Cloudflare Worker. Website Supabase imports still exist; do not remove those references merely because the site deploys on Cloudflare. |
| Hardware root README | Its September 6 “no Gerber” overview predates the September 9 E1P1 package. Gerber/drill/CAD/firmware files are present; all 242 supplied manifest entries independently match size and SHA-256. This is byte fidelity, not hardware qualification. |
| Selected Drive product/launch documents | Historical claims such as no cloud, no app/chat, battery life, shipping and compliance must not be promoted to current facts without matching evidence. An app/chat surface and a cloud brain demonstrably exist. Battery life, sales, fulfillment and compliance were not verified by this software audit. |
| Drive AI Model Orchestration System Overview | Its “fully implemented” description names `src/lib/orchestration` files absent from the current app and website checkouts. Treat it as an older architecture account, not evidence of the current brain's implementation or acceptance. |

The local September 6 archive index records 95 old Anticipy repositories or
worktrees, 24 with local changes/untracked files. The current Drive listing
contains all 91 expected ZIP names; the 45 still present in local staging match
their reported Drive sizes. Remote ZIP contents were not re-downloaded or
restored in this audit. Historical archive prose saying uploads are in progress
does not substitute for that current metadata check, and size agreement alone
does not establish a complete verified offload. No archive data was reclaimed.

## Acceptance gates still open

`tejas_gate` remains red on its explicitly unlinked speaker engine. Its own
instruction says to investigate the prior App Store Connect binary rejections
before re-linking the package. `tape_gate` remains red on three standing tapes;
no predicates or expiry requirements were weakened.

`done_gate`, `stranger_gate` and `are_the_ears_live` could not establish their
live/model-dependent legs in the offline test environment. Missing live evidence
is **unproven**, not proof of a production outage and not permission to call a
local repair fixed in production.

## Suggested order for app changes

1. **Capture and continuity:** make the phone/pendant/Mac tell the truth about
   what they can hear, preserve recoverable data and prove a known spoken input
   reaches the correct account. Finish physical pendant decode before describing
   pairing as working audio.
2. **Account safety:** migrate the iOS account token to Keychain with existing
   session migration, failed-write, sign-out and account-switch regression checks.
3. **A first useful result:** complete a cold install → capture/type → proposed
   task → approval → observable result journey on both experiences. Exercise
   restart, sleep, offline, denied permissions and owner change along the way.
4. **Evidence-backed documentation:** keep dated history, link current findings,
   and give each product or release claim a version, scope and reproducible proof.

The local repairs and open crash are recorded for code review. Live shipping
and the outstanding hardware/account/crash acceptance work are not marked
complete. The owner's next priority is the assembled Sense-board pendant,
button-free closed-case firmware maintenance, distinct LED states and tests
with the memory hardware present but its SD card absent.
