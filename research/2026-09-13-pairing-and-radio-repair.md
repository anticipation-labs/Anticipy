# Pairing identity and radio transport repair

Date: 2026-09-13. Candidate after `c7b02117` (documentation-only PR65).
Candidate labels: iOS 1.1.1 (177), extension 0.18.3.
**Not a live-release or whole-product acceptance claim.** The released client
at the start of this work was iOS176 / extension0.18.2.

## Reproduced failures

1. A legacy browser record with no usable per-agent credential repeatedly tried
   a service-only upgrade route. The setup surface could still claim it was
   linked without a usable pairing code. Manual re-pairing retained stale
   owner/profile state alongside the replacement identity.
2. Awaited owner-profile/model responses could outlive identity replacement.
   A delayed cached-key fallback could continue an old job, and old completions
   could overwrite a new owner's active task mirror.
3. The popup rendered retained task/hand-back records without proving they
   belonged to the currently paired owner. A stale Stop button read the newest
   stored job instead of the one the person had actually seen. Delayed live-step
   text could repaint an old owner's task after re-pairing.
4. The BLE assembler could emit a truncated previous Opus frame when a missing
   tail fragment was followed by the next frame's counter-zero notification.
   Duplicate/reordered sequence values also produced a false near-full-wrap
   duration, and a header-only packet could incorrectly witness completion.
5. Sequence counts are BLE fragments (plus intentional discard gaps), not
   ten-millisecond audio frames. The old gap-duration conversion was not valid
   across negotiated MTUs.
6. A new transport diagnostic tally initially trapped on `Int.max + 1`.
   The regression was reproduced before release; unrepresentable new diagnostic
   totals now become unknown, not a wrapped, zero or saturated exact claim.
7. Actual retry testing found an existing mismatch: an explicit queued resume
   requested attempt zero, but the workflow serializer applied that option only
   to a running transition. The exhausted attempt count could survive a
   successful-looking resume. This repair requires a genuine owner resume and
   must not reset the automatic retry budget.
8. A notification already submitted to Chrome could appear after replacement
   pairing completed. Clearing it afterwards was too late. Notification
   presentation now settles on the identity write queue before retirement;
   unconfirmed notification removal prevents a replacement registration.
9. An active job's liveness read treated a server authentication refusal like
   a transient outage. A 401/403 now stops that run, without interpreting a
   network error or 503 as credential revocation.

## Implementation boundaries

Pairing uses the existing public registration flow for an uncredentialed legacy
identity, requires a fresh phone pairing, and never grants service authority.
Transient outages with a valid identity do not rotate it. Captured identity
fences delayed work; popup actions carry the displayed owner/job identity and
are checked again by the worker. Retained history is owner-tagged and unknown
legacy ownership stays hidden; no customer job is deleted to make recovery pass.

Radio reassembly rejects malformed/ambiguous sequence transitions before emitting
frames. Diagnostics carry missing-sequence/local-discard counts with **unknown
duration**. Stream boundaries clear pending transport diagnostics. Existing
`airtimeLost` journal entries remain readable as historical estimates; they are
not silently rewritten or converted into newly measured loss.

No Opus decoder, raw-audio upload or pendant capture was enabled. The held
TranscriptCursor experiment and firmware images remain untouched. These repairs
are prerequisites for the missing physical pendant-to-phone transcription bridge,
not a substitute for building and testing it.

## Evidence and acceptance scope

- Browser pairing/worker tests execute the actual message handlers with a local
  synthetic backend. Delayed response and account-switch schedules are explicit.
- Popup tests execute the actual module against DOM IDs read from popup.html,
  with only Chrome/network/DOM simulated. Original code failed ten of the first
  eleven cases. The final thirteen include refused/undefined worker responses,
  blank credentials, wrong-owner narration, stale displayed actions and keeping
  the popup open when opening a parked task is refused.
- Native transport:36 checks;34 gap/journal/tally integration assertions;
  9 extracted actual-source manager/session presentation assertions;22 journal
  and48 existing tally checks. Four compiled mutants were killed. Ten-million-item
  assembler and queue stress checks passed. Overflow was red before correction.
- Real Chrome frame/hit-testing:7/7 passed on isolated synthetic sites under
  external-network denial. The model was scripted; this proves targeting and
  refusal mechanics, not model judgment, live login or extension installation.
- Full local native gate: all 75 registered runners passed on candidate177.
  The first attempt stopped because its isolated PATH omitted the existing
  Node runtime; the complete rerun passed after correcting PATH. Full Xcode is
  absent on the local Mac; the PR simulator compile remains a separate gate.
- The unchanged Python/API/brain sources passed their full offline regressions:
  4,047 Python tests with three skips, API and brain Worker suites and both
  TypeScript checks. Browser changes made afterwards still require the final
  frozen-source extension and browser checks.
- Final combined review, CI and publication results must be recorded below
  after completion. A version bump or archive alone is not a passing release gate.

One owner reported build176 installed and a greeting replied to in-app and in
Messages during this work. That is acceptance of that interaction on176, not
of candidate177, phone audio, other users or arbitrary connector tasks.

## Review and remaining work

Root coordinated and implemented the popup reader/action boundary. Waterloo
implemented the background writer/recovery boundary. Ben implemented transport
and reconciled the old checkout. A separate CEO-review agent challenged both
source slices and added malformed-response, empty-payload and overflow cases.
The full combined browser patch still needs its final frozen-source review.

Use the [readiness board](../docs/EOD-READINESS-2026-09-13.md) and
[firmware handoff](../docs/FIRMWARE-COLLABORATION.md) for the complete scope.
Real installed-browser reconnect, selected Google/Meet connector journeys,
broader latency, API-write effect ledger, consentful local-source onboarding,
signed Mac distribution and physical firmware acceptance remain open.

## 2026-09-14 review and repair (continuity run)

**Adversarial review of the uncommitted 0.18.3 patch:** 12 findings, 11
confirmed, all fixed red-first in `extension/background.js` / `extension/popup.js`
(identity generation fencing of late replies, owner-change wipe in
`stampLastSeen`, presentation retirement on owner change, legacy hand-back
adoption, identity-queue ordering for `currentOwnerScope`, the liveness refusal
streak in `jobStillLive`, closed-tab unpairing, popup live-step epoch); ten
mutants killed. Recorded in full in the continuity note for the day.

**The release shape (found by the installed-client rig, pass 3):** an unpaired
row whose `owner_ref` column still holds the old owner (an older app, or a
release made while signed out) read as "same owner" and nothing was wiped: the
popup stayed "Linked" with the old key and profile. Fix: `stampLastSeen` treats
an unpaired row as ownerless whatever the column holds (one line). New red case
`phone-release-legacy` in `test_pairing_lifecycle_races.mjs` (31 cases); the
reverted-line mutant is red; popup boundary 15/15; extension gate 90 suites green.

**Installed-client evidence (real unpacked extension, real Chrome 152, loopback
Worker/D1, scripted model):** `proof/audit/installed_extension/` — pass 5 on
2026-09-14 22:05–22:10 UTC: **8/8 verdict rows green**, plus two informational
rows (`launch`, `launch:targets`) that carry no pass/fail field and so cannot
go red. The eight are register, pair, a task with one site click and a verified
receipt, restart on the same identity, a ~100 s Worker outage without identity
rotation, owner separation with no leaked text and no cross-owner claim,
phone-driven release → "Not linked" → same-code re-pair → task, and the same
with the legacy release shape. The stand-in phone mirrors the signed-in app's
release body and can produce the older shape on request.

**Radio transport (BLE assembler):** a jump past the half-range sequence window
stalls the assembler until the 16-bit counter laps or the radio disconnects. A
repair was written — adopt the mark after two consecutive out-of-window packets
that continue each other — and then **reverted after review**: "behind the
mark" and "far ahead of the mark" are the same delta in serial arithmetic, so
two stale or replayed packets re-origin the stream backward, and the genuine
stream's next packet is then billed tens of thousands of phantom missing
notifications. Telling the two apart needs a session epoch on the wire, which
belongs with the firmware work rather than a release-day patch. The stall is
now an explicit test case pinning the behaviour that actually ships, and a
named open defect on the readiness board. Dead code (`finish()`, the timed
`GapMarker.text`) was removed with its test-only uses. Transport 43/43, gap
engine and presentation legs green, audio stress green over ten million packets.

**Packages:** the three download ZIP aliases are rebuilt from this exact source
before commit; `proof/audit/check_extension_package.py` must exit 0 (the deploy
job runs the same checker).

**What is NOT proven by any of the above (Law 3):** the served ZIP in anyone's
Chrome; the owner's own profile and real sites; the phone journey release →
"Not linked" → same-code re-pair on a real iPhone build; anything on the live
API until the api dispatch lands and the board's addendum says `deployed`.

**Final combined review, CI and publication:** the combined diff goes through an
adversarial review workflow before commit; PR checks (`system-invariants`,
`ios-candidate`) and the deployment steps are recorded in the readiness board's
2026-09-14 addendum as they happen. Until that addendum says otherwise every
line above is `not deployed`.

