# Publication redaction inventory — 2026-09-14

A read-only inventory of **already-tracked** files (`git ls-files` on
`cloudflare-backend`) that still carry personal absolute paths, e-mail
addresses, or phone-like numbers. It lists file path, category and count
only — never the strings — so the follow-up that redacts or removes them can
be scoped without re-scanning, and so nothing in this note is itself a leak.

## Method

- Personal absolute paths: macOS and Linux home-directory prefixes followed
  by a user name.
- E-mail addresses: address-shaped tokens, excluding placeholder and
  reserved domains (`example.*`, `.invalid`, `.test`, `localhost`), the
  product's own domain and its subdomains, `noreply` addresses, and asset
  names that merely contain an at-sign (image density suffixes).
- Phone-like numbers: North-American `NNN NNN NNNN` shapes with any
  separator, with or without a country code, and `+` followed by 10–14
  digits; the fictional `555` exchange used by fixtures is excluded.
- Binary files were skipped except PDFs, whose raw text was counted.
- Counts are pattern hits, not confirmed personal data; a test fixture can
  hit an e-mail pattern with an invented address. Every listed file needs a
  human look before the public branch is cut.

Totals: 354 files; 540 path hits, 431 e-mail hits, 177 phone-like hits.

## Remove from the public branch (follow-up PR)

**Status 2026-09-15:** done. The eight `*.jsonl` harness dumps and
`HANDOFF-TRANSCRIPT.md` were removed from `cloudflare-backend`, and the dated
session notes that sat in the repository root (`AUDIT-2026-07-21.md`,
`BACKLOG.md`, `CLAUDE-INTAKE-PROMPT.md`, `CLAUDE-ONBOARDING.md`,
`HANDOFF-2026-08-08.md`, `HANDOFF.md`, `ORCHESTRATOR-HANDOFF.md`,
`PROOF_REPORT.md`, both `TESTING-PASS-2026-08-21*.md`, `WHAT-CHANGED-2026-08-02.md`,
`WHAT-I-FOUND-2026-08-11.md`) now live under `research/archive-root-2026-09-15/`
with their history. The counts in the table below still refer to those files
under their new paths; the redaction of their contents remains to do.

These are harness dumps and a raw session transcript at the repository root.
They carry no product source and should be removed from the public branch in
a separate, path-limited PR (moving them out of the tree is a git operation
this note deliberately does not perform):

| File | Why |
| --- | --- |
| `HANDOFF-TRANSCRIPT.md` | Raw session transcript; personal paths, addresses and phone-like numbers (counts below). |
| `formdiag.jsonl` | Harness run dump. |
| `formfix.jsonl` | Harness run dump. |
| `formfix2.jsonl` | Harness run dump. |
| `formfix3.jsonl` | Harness run dump. |
| `formfix4.jsonl` | Harness run dump. |
| `formfix5.jsonl` | Harness run dump. |
| `formfresh.jsonl` | Harness run dump. |
| `fullbattery.jsonl` | Harness run dump. |

Also recommended: add `.pytest_cache/` to `.gitignore`. It is not tracked
today, but it is created by every local pytest run at the repository root and
nothing ignores it. (This note does not edit `.gitignore`.)

The private operational note excluded from publication by the 13 September
workspace reconciliation is not tracked and is not listed here.

## Tracked files with hits

| File | Category and count |
| --- | --- |
| `.agents/skills/testing-anticipy/SKILL.md` | paths 1 |
| `.github/workflows/ios-testflight.yml` | emails 1 |
| `AUDIT-2026-07-21.md` | paths 8 |
| `CLAUDE-ONBOARDING.md` | phones 1 |
| `HANDOFF-2026-08-08.md` | emails 1 |
| `HANDOFF-TRANSCRIPT.md` | paths 39; emails 4; phones 17 |
| `HANDOFF.md` | paths 2; emails 3; phones 6 |
| `PROOF_REPORT.md` | paths 1 |
| `app/ios/Anticipy/AnticipyApp.swift` | phones 2 |
| `app/ios/Anticipy/Views/AuthView.swift` | emails 3 |
| `app/ios/Anticipy/Views/OnboardingView.swift` | emails 1 |
| `app/ios/Anticipy/Views/SettingsProfileView.swift` | emails 1 |
| `app/ios/Anticipy/Views/SettingsView.swift` | emails 2 |
| `app/ios/Tests/CalendarHandPolicyTests.swift` | emails 1 |
| `app/ios/Tests/FieldCaptionTests.swift` | phones 5 |
| `app/ios/Tests/PhoneNumberTests.swift` | phones 5 |
| `app/ios/Tests/ResetMessageTests.swift` | emails 1 |
| `app/ios/UITests/DashboardShots.swift` | paths 1 |
| `app/ios/UITests/FrontendShots.swift` | paths 1 |
| `brain/conversation.py` | emails 1 |
| `brain/worker.py` | phones 1 |
| `design/CONSUMER-FEEL-DIRECTION-2026-08-03.md` | paths 1; emails 2 |
| `design/LOGIN-DESIGN-2026-08-03.md` | paths 2 |
| `docs/BRIEF.html` | emails 1 |
| `docs/HANDOFF-NOW.md` | paths 1 |
| `docs/LOCAL-DEVELOPMENT-MAC.md` | paths 4 |
| `docs/LOCAL-DEVELOPMENT-TEJAS.md` | paths 3 |
| `docs/TAKEOVER-2026-08-30.md` | paths 7 |
| `docs/WORKSPACE-SYNC-2026-09-07.md` | paths 1 |
| `docs/spec-connections.txt` | emails 1 |
| `docs/superpowers/specs/2026-08-25-mouth-photo-receipt.md` | phones 4 |
| `extension/agent_loop.js` | emails 1 |
| `extension/side_trip.js` | emails 3 |
| `extension/store/LISTING.md` | emails 1 |
| `extension/tests/test_authored_draft.mjs` | emails 2 |
| `extension/tests/test_code_sent_is_not_a_word_match.mjs` | emails 2 |
| `extension/tests/test_inbox_consent.mjs` | emails 4 |
| `extension/tests/test_live_progress.mjs` | emails 1 |
| `extension/tests/test_narration_is_not_a_word_match.mjs` | emails 2 |
| `extension/tests/test_otp_wall.mjs` | emails 14 |
| `extension/tests/test_planner.mjs` | emails 2 |
| `extension/tests/test_private_places.mjs` | emails 1 |
| `extension/tests/test_question_reaches_him.mjs` | emails 1 |
| `extension/tests/test_side_trip.mjs` | emails 13 |
| `extension/tests/test_supervised_read.mjs` | emails 5 |
| `firmware/BUILD_RECEIPT.json` | paths 4 |
| `firmware/source/DUAL_HATCH_RECEIPT.json` | paths 1 |
| `migration/recovered/fellowship.pb.js` | emails 3 |
| `migration/runbooks/FINISH-MIGRATION-CHECKLIST.md` | paths 1 |
| `migration/spec/CONTRACT.md` | emails 1 |
| `migration/spec/contract_tests.py` | emails 2 |
| `migration/workers/public/mac.html` | emails 1 |
| `migration/workers/public/privacy.html` | emails 2 |
| `migration/workers/public/setup.html` | emails 1 |
| `migration/workers/src/cron.ts` | emails 1 |
| `migration/workers/src/routes/fellows_base.ts` | emails 1 |
| `migration/workers/src/routes/hq_assistant.ts` | emails 1 |
| `output/pdf/Anticipy-audit-2026-09-07.pdf` | emails 3 |
| `output/pdf/Anticipy-codebase-map-2026-09-07.pdf` | emails 1 |
| `output/pdf/Anticipy-engineer-field-brief-500-scenarios.pdf` | emails 16; phones 2 |
| `output/pdf/Anticipy-harness-audit-2026-09-07.pdf` | emails 235; phones 7 |
| `output/pdf/Anticipy-harness-explained-2026-09-07.pdf` | emails 1 |
| `output/pdf/Anticipy-in-real-life-100-conversation-exemplars.pdf` | emails 6; phones 2 |
| `output/pdf/Anticipy-synthetic-brain-lab-2026-09-07.pdf` | emails 1 |
| `overnight/after_dev_convo.json` | emails 1 |
| `overnight/corpus_dev.json` | emails 2 |
| `overnight/does_she_reach_them.py` | phones 1 |
| `overnight/gold_dev.json` | emails 2 |
| `overnight/stranger_gate.py` | phones 1 |
| `proof/agent-v2-report.md` | paths 2 |
| `proof/agent_defaults_chrome.py` | paths 1 |
| `proof/agent_generic_chrome.py` | paths 1 |
| `proof/agent_identity_chrome.py` | paths 1 |
| `proof/agent_iframe_chrome.py` | paths 1 |
| `proof/agent_readonly_resume_chrome.py` | paths 1 |
| `proof/ambient/baseline.jsonl` | phones 1 |
| `proof/ambient/rounds/abA/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/abA/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/abB/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/abC/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/costprobe/voice-1.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-2.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-3.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-4.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-5.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-6.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-7.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-8.run.log` | paths 2 |
| `proof/ambient/rounds/costprobe/voice-9.run.log` | paths 2 |
| `proof/ambient/rounds/k1/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k1/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k2/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/k3/results.jsonl` | emails 1 |
| `proof/ambient/rounds/k3/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-15.jsonl` | emails 1 |
| `proof/ambient/rounds/k3/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k3/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k4/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k5/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k6/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k7/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-10.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-11.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-12.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-13.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-14.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-15.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-16.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-6.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-7.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-8.run.log` | paths 1 |
| `proof/ambient/rounds/k8/voice-9.run.log` | paths 1 |
| `proof/ambient/rounds/smoke/voice-1.run.log` | paths 1 |
| `proof/ambient/rounds/smoke/voice-2.run.log` | paths 1 |
| `proof/ambient/rounds/smoke/voice-3.run.log` | paths 1 |
| `proof/ambient/rounds/smoke/voice-4.run.log` | paths 1 |
| `proof/ambient/rounds/smoke/voice-5.run.log` | paths 1 |
| `proof/ambient/rounds/smoke/voice-6.run.log` | paths 1 |
| `proof/anticipy-core-report.md` | phones 1 |
| `proof/audit/report.py` | paths 1 |
| `proof/audit/repository_state_report.py` | paths 1 |
| `proof/browser_battery.py` | paths 1 |
| `proof/dry_run_his_reply.py` | emails 1; phones 2 |
| `proof/hands_battery.py` | phones 2 |
| `proof/ios-build-report.md` | emails 1 |
| `proof/navigation-report.md` | paths 4 |
| `proof/prod20.py` | paths 1 |
| `proof/profiles5-report.md` | paths 2 |
| `proof/profiles5_ingest.py` | paths 6 |
| `proof/rerun_browse.py` | paths 3 |
| `proof/run_conversational.py` | paths 4; emails 1 |
| `proof/run_e2e_round2.py` | paths 4 |
| `proof/run_e2e_scenarios.py` | paths 4 |
| `proof/run_full_chain.py` | paths 1 |
| `proof/run_postfix2.py` | paths 4 |
| `proof/scenario-report.md` | paths 1 |
| `proof/sendblue_outbound_proof.py` | phones 1 |
| `proof/sw_monitor.py` | paths 2 |
| `proof/test-report.md` | paths 2 |
| `proof/test_anticipy.py` | paths 1 |
| `proof/test_anticipy_live.py` | paths 1 |
| `proof/test_ask_remember_resume.py` | phones 5 |
| `proof/test_extension.py` | paths 2 |
| `proof/test_full_chain.py` | paths 3 |
| `proof/test_memory.py` | paths 1 |
| `proof/test_never_silent.py` | phones 3 |
| `proof/test_pairing_live.py` | paths 1 |
| `proof/test_requirement_survives.py` | phones 1 |
| `proof/test_resume_the_right_one.py` | phones 2 |
| `proof/test_scenarios.py` | paths 1 |
| `proof/test_sms_flows.py` | phones 9 |
| `proof/twilio_outbound_proof.py` | phones 1 |
| `proof/verify_all.py` | phones 1 |
| `research/2026-08-24-api-ladder.md` | paths 8 |
| `research/2026-08-24-battery-and-ear.md` | paths 1 |
| `research/2026-08-24-cold-stranger-walkthrough.md` | paths 1 |
| `research/2026-08-24-deepgram-leak.md` | paths 1 |
| `research/2026-08-24-inbox-consent-nonce.md` | emails 1 |
| `research/2026-08-24-stranger-gate-fixes.md` | phones 2 |
| `research/2026-08-24-stranger-gate.md` | paths 1; phones 4 |
| `research/2026-08-25-call-detection.md` | paths 1 |
| `research/2026-08-25-claim-audit.md` | paths 9 |
| `research/2026-08-25-inbound-sms-reply.md` | phones 28 |
| `research/2026-08-25-mouth-photo-build.md` | phones 1 |
| `research/2026-08-26-hands2-better-answer.md` | paths 2 |
| `research/2026-09-01-reservation-agent-incident.md` | paths 1 |
| `research/2026-09-05-browser-region-audit.md` | emails 2 |
| `research/2026-09-05-release-0.15.0.md` | phones 1 |
| `research/2026-09-05-website-cutover-in-progress.md` | paths 1 |
| `research/2026-09-06-every-phone-number.md` | phones 5 |
| `research/2026-09-06-mac-development-setup.md` | paths 2 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/ARCHITECTURE.md` | emails 1; phones 4 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/AUTONOMOUS_LOOP_WAKE_UP_REPORT.md` | paths 2 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/BUG_LIST.md` | emails 5 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/CONTEXT_HANDOFF.md` | paths 2; phones 1 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/DEMO_RECORDING_PLAYBOOK.md` | paths 1 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/E2E_STRANGER_FLOW_VERIFY.md` | paths 2 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/E2E_VULN_FIX_REPORT.md` | phones 4 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/HANDOFF.md` | paths 5 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/HANDOFF_COMPLETE.md` | emails 3 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/HANDOFF_HONEST.md` | emails 1 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/INTEGRATION_WALK_REPORT.md` | paths 1 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/MASTER_HANDOFF.md` | paths 83; emails 2; phones 8 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/NORTH_STAR_v2.md` | emails 1 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/OMAR_LEAK_HUNT.md` | paths 1; emails 1 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/ORCHESTRATOR.md` | paths 3; emails 5 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/QUEUE_AUDIT.md` | emails 2 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/RESEARCH/a2p-10dlc.md` | phones 5 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/ROADMAP.md` | paths 1 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/SESSION_HANDOFF_2026_05_30.md` | paths 4 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/SURFACE_AUDIT.md` | paths 17 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/TWILIO_DELIVERY_TEST.md` | phones 8 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/USER_E2E_TESTS.md` | paths 1; emails 2 |
| `research/archive-2026-09-04/deploy-preorder/planning/00-handoff/VERCEL_DEPLOY_RUNBOOK.md` | paths 1 |
| `research/archive-2026-09-04/hoe-build/ANTICIPY_DISTRIBUTION_OPERATING_LEDGER_2026-06-22.md` | paths 5 |
| `research/archive-2026-09-04/hoe-build/ANTICIPY_ENGINE_AUDIT_2026-06-15.md` | paths 20; phones 1 |
| `research/archive-2026-09-04/hoe-build/CANON/00_START_HERE.md` | paths 1 |
| `research/archive-2026-09-04/hoe-build/CANON/05_CURRENT_STATE.md` | emails 2 |
| `research/archive-2026-09-04/hoe-build/CANON/THE_MAP.md` | paths 2 |
| `research/archive-2026-09-04/hoe-build/CANON/UI_SPEC.md` | paths 7 |
| `research/archive-2026-09-04/hoe-build/CURRENT_STATE.md` | emails 1 |
| `research/archive-2026-09-04/hoe-build/MISSION_LOCK.md` | paths 1 |
| `research/archive-2026-09-04/hoe-build/STATUS.md` | emails 1 |
| `research/archive-2026-09-04/recon-engine-state/ENGINE_STATE.md` | paths 1 |
| `research/archive-2026-09-04/recon-engine-state/recon/anticipy_funded.html` | emails 1 |
| `research/archive-2026-09-04/recon-engine-state/recon/test_output.log` | paths 2 |
| `research/overnight-2026-09-07/repository-integration-evidence.json` | paths 1 |
| `research/overnight-2026-09-07/repository-state-evidence.json` | paths 1 |
| `research/solutions-2026-08-24/designs.json` | paths 28; emails 1 |
| `research/solutions-2026-08-24/judgments.json` | paths 2 |
| `spike/two-hands/src/onboarding.ts` | emails 1 |
| `spike/two-hands/test/observer.test.ts` | paths 1; emails 1 |
| `tests/fixtures/googlecalendar_tools_2026-09-06.json` | emails 30 |
| `tests/test_done_text_carries_the_photo.py` | phones 2 |
| `tests/test_earls_live_failures.py` | emails 2 |
| `tests/test_invented_names.py` | emails 1 |
| `tests/test_live_extension_package_gate.py` | paths 1 |
| `tests/test_one_answer_path.py` | phones 1 |
| `tests/test_phone_route_identity.py` | phones 12 |
| `tests/test_profile_seed.py` | emails 2 |
| `tests/test_reach_gate.py` | phones 3 |
| `tests/test_research_gate.py` | emails 1 |
| `tests/test_sendblue_arm.py` | phones 1 |
| `tests/test_stranger_gate.py` | phones 3 |

## Reading the table

- `proof/` dominates by file count because it holds tracked run logs and
  corpora from live proof sessions; most hits there are recorded
  conversations, not code. Decide per directory whether the logs belong on a
  public branch at all.
- `research/archive-2026-09-04/` is a dated archive of earlier planning; the
  path hits are historical machine paths in prose.
- Test files under `tests/`, `migration/workers/test/`, `extension/tests/`
  and `app/ios/Tests/` mostly hit the phone pattern with invented numbers
  outside the `555` exchange; confirm they are synthetic and leave them, or
  move them onto the `555` exchange so the scan stays quiet.
- `output/pdf/` PDFs embed text from the documents they render; regenerate
  from redacted sources rather than editing the PDF.
- Source files under `app/`, `brain/`, `extension/`, `migration/` and
  `overnight/` with path hits carry machine paths in comments; those are
  one-line edits.
