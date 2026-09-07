# Private external TestFlight handoff

2026-09-07. The owner explicitly requested build access for one named tester.
His exact address and the raw Apple receipts are in private work/audit files.

The existing Internal group refused assignment with HTTP 409, "Tester(s) cannot
be assigned" (run 34094694510). Apple's internal groups require App Store Connect
users; an app-testing invitation does not authorize granting a developer role.

The existing manual asc-query.yml workflow now also accepts INVITE_EXTERNAL.
It creates/reuses a private, dedicated external group, attaches the exact valid
unexpired build, adds the named tester, requests beta review when required and
reads back Apple's group, build and tester state. It refuses an internal/public
group or a group containing an unrelated tester. It creates no developer-user
account and uploads no binary. An empty confirmation still only reads.

Verification: all 63 iOS logic suites passed before the release-tool commit;
20 release-helper tests passed, including wrong-audience refusal, idempotent
retry, no mutation without confirmation, and pending review not called ready.
No iOS app source changed, so the existing build 159 is reused.

Apple run 34095101764 created the dedicated external group with public link off,
attached build 159 and confirmed the requested tester as its sole member. Apple
accepted the beta review submission. Actual status:

- Build 159: VALID, unexpired.
- External distribution: WAITING_FOR_BETA_REVIEW.
- Named tester: NOT_INVITED (invitation waits for beta availability).
- Automatic notification was enabled on the selected build.
- It is not yet installable by this external tester. A successful workflow is
  not evidence of Apple approval or invitation delivery.

Remaining dependency: Apple must approve external beta testing. No developer
role, alternative email, older build, or public link was used to bypass review.

Apple reference: https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers
