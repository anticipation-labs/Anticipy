# V7 verifier-first proposals (Omar review queue)

These are PROPOSED verifier scripts. They live under
`state/v7/proposed_verifiers/` because `verifier/` is a frozen path
per `AGENTS.md` and `docs/OPERATING_MANUAL.md`. Edits to `verifier/`
require Omar sign-off via `state/decisions/queue.md`. Until Omar
copies a script into `verifier/`, it is not on the V7 gate path.

## The verifier-first contract

A V7 verifier is verifier-first when it:

1. Asserts a user-visible behaviour required by `ANTICIPY_V7.md`
   PART 0 through PART 7.
2. Calls real engine endpoints (or reads real on-disk artifacts) and
   does NOT mock anything.
3. Fails on the CURRENT engine state, so that landing the assertion
   is what motivates the frozen-path edit.
4. Passes only after the frozen path is fixed to honour the asserted
   behaviour.
5. Cleans up every probe row, queue item, tab, or memory entry it
   created, even on partial failure.
6. Writes a structured verdict to
   `state/v7/proposed_verifier_runs/<name>/result.json`.

## What lives here today

| File | Frozen paths it unlocks | V7 gate guarded |
| --- | --- | --- |
| `verify_memory_account_device_scoping.py` | `engine/app/anticipy/memory.py`, `engine/app/product/server.py` | V7.20 |
| `verify_canonical_proactive_runtime.py` | `engine/app/proactive_day/pipeline.py`, `engine/app/proactive/decider.py`, `engine/app/proactive/dispatcher.py` | V7.6 / V7.7 / V7.8 / V7.20 |
| `verify_action_dispatcher_visible_receipt.py` | `engine/app/middle/dispatcher.py`, `engine/app/proactive/dispatcher.py`, `engine/app/product/server.py` action call sites | V7.10 / V7.20 |

### Memory scoping

Today every memory entry returned by `/api/memory` carries only
`kind`, `value`, and `ts`. There is no `account_id`, `device_id`,
`source`, `confidence`, `active`, or `provenance`. The frozen module
`engine/app/anticipy/memory.py` defines `USER_ID = "anticipy-user"`
and the scoped router in `engine/app/product/scoped_memory_endpoints.py`
exists but is not wired. Two accounts share one memory file. The
proposed verifier exposes all four leaks at once: schema, isolation,
pronoun resolution, do-not-touch enforcement.

### Canonical proactive runtime

Today an utterance can take more than one proactive code path between
text-inject, MP3 upload, and live mic. Hard negatives (jokes,
hypotheticals, third-party speech, song lyrics) are not deterministic
silent-or-decline decisions, and no `decisions.jsonl` row records
them. The proposed verifier asserts a single canonical runtime, equal
shape across input sources, decline/silent on hard negatives, and
durable decision records.

### Action dispatcher visible receipt

Today `_try_direct_browser_action` in `engine/app/product/server.py`
returns `ran=True, status=SUCCESS` based on a substring match in the
Chrome JSON tab list, without requiring a DOM dump, screenshot, AX
read, file diff, or non-empty `surface_receipt.proof`. Two dispatcher
classes (`engine/app/middle/dispatcher.py` and
`engine/app/proactive/dispatcher.py`) coexist. The proposed verifier
asserts visible-receipt-required, single shared dispatcher, provider
callbacks alone do not count, and no double-fire.

## How Omar accepts a proposal

1. Read the proposal's top docstring (section cite, gate, frozen
   paths) and the assertions block.
2. Run it once against the current engine:
   `python3 state/v7/proposed_verifiers/<name>.py`
3. Confirm it fails for the expected reasons (the verdict's
   `failed_count` and the failure strings on each assertion).
4. Copy it into `verifier/v7/<name>.py` and wire it into
   `scripts/v7/check_done.sh` as a new gate, or extend an existing
   gate to call it.
5. Log the acceptance in `state/decisions/queue.md` with the line
   `accepted: state/v7/proposed_verifiers/<name>.py -> verifier/v7/<name>.py`.

After step 4 the verifier becomes load-bearing. Until then it is a
proposal Omar can ignore without breaking the gate flow.

## Run convention

Each script is standalone:

```bash
cd /Users/omarebrahim/Developer/Anticipy-V7
ANTICIPY_ENGINE_URL=http://127.0.0.1:8731 \
  python3 state/v7/proposed_verifiers/verify_memory_account_device_scoping.py
```

Exit `0` on full pass, `1` on any assertion failure. Verdict JSON is
always written, pass or fail.

## Hard rules in every proposal

- Standard library only (no third-party imports).
- No em-dashes; periods, commas, and parentheses only.
- Cleans up every probe row, queue item, and tab it created, in a
  `finally` block.
- Cites a specific `ANTICIPY_V7.md` section and the V7 gate it guards.
- File under 400 lines.
