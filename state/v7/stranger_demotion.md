# V7.20 Stranger Demotion Notes

Date: 2026-05-27
Author: claude (per Omar's explicit directive on the W2L finding)

## Rationale

The V7.20 `probe_no_fake_receipts` audit found 3 strangers whose
`verdict.json` and `trace.json` reference `real_chrome_screenshot.png`
paths that do not exist on disk. The verdicts themselves reason correctly
about the captured surfaces and competent declines, but the underlying
PNG bytes are gone (likely from a stale `/private/tmp/anticipy-ship-...`
build directory in one case, and from a workspace move/rename in the
others).

Re-running the strangers would re-execute persona + script through the
live engine and bridge, which would change every receipt-bound field in
the verdict (ingest_id, transcript_boundary_sha256, marker, window_id,
service URL chosen by the heuristic mapping, evaluator reasoning) and
also requires three different driver paths (transcript_paste for two,
audio_upload for the third) plus a real Canva/Amazon/HubSpot Chrome
surface capture. That is more invasive than the integrity problem
warrants.

The cleaner fix is to demote the three strangers from
`successful_interactions` so V7.11, V7.14, and V7.20 are honestly held
at 43 strangers, not 46. The other 43 verified passes remain untouched.

## Demoted UUIDs

The exact list lives in `state/v7/stranger_demotion_list.json` so both
the breadth audit and the no-fake-receipts probe load it directly.

- `7d25a993-ad89-4a30-b2f2-2f4badde7cb4` (commerce_cart_or_order_prep)
  Missing PNGs under `screenshots/proofs/public_app_after_manual_transcript_decline/`
  and `screenshots/proofs/service_precheck_1_amazon_proof/`.

- `20198a5c-fa7a-4e7b-8824-2681bdcf8d30` (crm_followup_task_or_note)
  Trace screenshot_path points at `/private/tmp/anticipy-ship-8c4935a/`
  which no longer exists. Both the PNG and the page_metadata sibling
  are missing.

- `8ee08723-ad73-4016-bf0e-fc48f742d78a` (canvas_design_edit_or_comment)
  Missing PNG under `screenshots/proofs/public_app_after_transcript_decline/`.

## Effect on gates

- V7.11 `strangers_100_ok` is the relaxed gate `successful_interactions >= 25`.
  Post-demote: 43. Still well above 25. No threshold change required.
- V7.14 `last20_ok` uses the last 20 rows in the breadth audit. None of
  the 3 demoted UUIDs are in the last 20, so this gate is unaffected.
- V7.20 `no_fake_receipts_ok` excludes the 3 demoted UUIDs from the
  probe, so the probe now passes honestly with 43 counted rows.

## How the exclusion works

`scripts/v6/breadth_audit.py` reads `state/v7/stranger_demotion_list.json`
at startup. Any UUID in `demoted_uuids` has its `verified_pass` forced to
`false` with `verification_failures += ["demoted_v7_20_missing_screenshot_bytes"]`.
The `pass` field reported in the row stays whatever the verdict says,
so existing audit consumers see the truth: verdict said pass, but the
proof is incomplete.

`scripts/v7/probe_no_fake_receipts.py` reads the same list and skips
demoted UUIDs entirely from `counted_passes_checked`. The demoted UUIDs
are still recorded in the output JSON under a separate `demoted` field
for audit transparency, but they do not count toward `pass`.
