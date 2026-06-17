# 11 — Acceptance Gates

## Gate A — Truth and continuity

Must prove:

- Constitution exists and is loaded first.
- Current truth file exists.
- Receipts ledger exists.
- Failure ledger exists.
- Model route verified.
- Suite baseline known.

Receipt:

- command output saved,
- current commit/branch,
- model route response,
- startup docs committed.

## Gate B — No-lie receipt floor

Must prove:

- API writes re-read artifacts.
- Browser actions produce screenshot + DOM/URL proof.
- Voice/text reads provider logs.
- `_verify` rejects self-attested proof.

Receipt:

- write call ID != read call ID,
- phantom artifact fails closed,
- tests fail when read-back removed.

## Gate C — Core messy-day owner slice

Must prove:

- messy transcript processed,
- real tasks remembered/inferred,
- vents ignored or inert-only,
- safe prep cards generated,
- approval UI shows parked work,
- no triggers from inert memory.

Receipt:

- input transcript,
- expected vs actual table,
- review UI screenshot,
- no false-action report.

## Gate D — API arm live proof

Must prove:

- Gmail draft created, re-read.
- Calendar hold/event created, re-read.
- Nothing externally sent without approval.
- Wrong/missing read fails closed.

Receipt:

- artifact IDs,
- read-back JSON redacted,
- screenshot if useful.

## Gate E — Browser arm live Chrome proof

Must prove:

- extension/local bridge connected to real Chrome.
- browser-use/CDP can read page.
- browser-use can prepare reversible state.
- no submit/buy/pay/delete.

Receipt:

- connection state,
- final URL,
- screenshot,
- DOM proof,
- guard log.

## Gate F — Onboarding/profile mesh

Must prove:

- onboarding asks questions,
- browser/API scan discovers services,
- profile is source-backed,
- uncertainty list created,
- clarification flow works.

Receipt:

- profile JSON,
- source list,
- mesh file,
- clarification transcript.

## Gate G — Voice/text loop

Must prove:

- outbound text/call delivered,
- user reply maps to exact ask ID,
- no backlog flood,
- provider read-back done.

Receipt:

- provider SID,
- redacted logs,
- exact ask resolution.

## Gate H — Downloadable app

Must prove:

- Vercel page live,
- download artifact current,
- app opens,
- engine boots,
- extension connects,
- main page can process input.

Receipt:

- URL,
- checksum,
- launch log,
- screenshots,
- version/commit.

## Gate I — Five-day owner proof

Must prove for five consecutive days:

- real inputs processed,
- real tasks prepared/executed safely,
- receipts collected,
- zero vent actions,
- acceptable annoyance level,
- user trusts it.

Receipt:

- day reports,
- artifact receipts,
- failure notes,
- final owner signoff.
